"""VectorStoreManager 的共享状态与基础方法（从 vectorstore.py 拆出，行为等价）。

★ 以「基类 + mixin」形式拆类：各子类共享同一实例状态，公开 API 不变。
"""

from __future__ import annotations

import hashlib
import logging
import socket
import threading
from contextlib import contextmanager

import chromadb
from langchain_chroma import Chroma

from core.settings import settings
from rag.common.embeddings import get_embeddings

logger = logging.getLogger(__name__)

# ── HNSW 索引参数（针对 bge-m3 1024 维向量优化） ─────
# bge-m3 输出 1024 维 dense vector，配置 HNSW 参数确保召回精度
_HNSW_M = 32  # 每节点最大连接数（默认 16，高维数据用 32）
_HNSW_EF_CONSTRUCTION = 300  # 索引构建候选数（越大质量越高，构建稍慢）
_HNSW_EF_SEARCH = 100  # 检索候选数（≈ k × 15~20，k=5~8 时 100 合理）
_HNSW_SPACE = "cosine"  # bge-m3 官方推荐余弦距离

_HNSW_COLLECTION_METADATA = {
    "hnsw:M": _HNSW_M,
    "hnsw:construction_ef": _HNSW_EF_CONSTRUCTION,
    "hnsw:search_ef": _HNSW_EF_SEARCH,
    "hnsw:space": _HNSW_SPACE,
}

_LEGACY_HNSW_KEYS = {
    "hnsw:ef_construction": "hnsw:construction_ef",
    "hnsw:ef_search": "hnsw:search_ef",
}

# 就绪探针查询：只要求"能查通"，不关心命中什么，故用一个与语料无关的短词
_READINESS_PROBE_QUERY = "索引就绪探针"

# `record_query_failure(..., exc=...)` 挂在异常对象上的属性名（F3 的**幂等标记**）：
# 同一个异常穿过「生产者记录 + 路由收敛记录」两层时，只落**一条**记录。
# ★ 用异常对象身份而不是文案匹配做去重（文案随 Chroma 版本变，见 `record_query_failure`）。
_FAILURE_NOTE_ATTR = "_edu_query_failure_note"


def _content_hash(content: str) -> str:
    """生成内容的 SHA256 哈希，用于去重"""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


def _is_http_endpoint_available(host: str, port: int, timeout: float = 0.25) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


class _RWLock:
    """读写锁：多读并发，写独占。

    PersistentClient 的读操作是线程安全的（HNSW 索引不可变），
    但写操作不是（并发写会损坏索引）。
    用读写锁替代全局 RLock，让多路并行召回的读查询真正并发执行。
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._can_read = threading.Condition(self._lock)
        self._can_write = threading.Condition(self._lock)
        self._readers = 0
        self._writers = 0
        self._write_waiting = 0

    @contextmanager
    def read_lock(self):
        with self._lock:
            while self._writers > 0 or self._write_waiting > 0:
                self._can_read.wait()
            self._readers += 1
        try:
            yield
        finally:
            with self._lock:
                self._readers -= 1
                if self._readers == 0:
                    self._can_write.notify()

    @contextmanager
    def write_lock(self):
        with self._lock:
            self._write_waiting += 1
            while self._readers > 0 or self._writers > 0:
                self._can_write.wait()
            self._write_waiting -= 1
            self._writers += 1
        try:
            yield
        finally:
            with self._lock:
                self._writers -= 1
                if self._write_waiting > 0:
                    self._can_write.notify()
                else:
                    self._can_read.notify_all()


class _VectorStoreBase:
    """共享实例状态 + 基础方法（初始化 / HNSW 参数 / get_store / 失败记录）。"""

    def __init__(self) -> None:
        self._embeddings = None
        self.client_mode = "persistent"
        if _is_http_endpoint_available(settings.CHROMA_HOST, settings.CHROMA_PORT):
            try:
                self.client = chromadb.HttpClient(
                    host=settings.CHROMA_HOST, port=settings.CHROMA_PORT
                )
                self.client.heartbeat()
                self.client_mode = "http"
                logger.info(
                    "ChromaDB HttpClient connected to %s:%d",
                    settings.CHROMA_HOST,
                    settings.CHROMA_PORT,
                )
            except Exception as e:
                logger.warning(
                    "ChromaDB HttpClient failed (%s), falling back to PersistentClient", e
                )
                self.client = chromadb.PersistentClient(path=settings.CHROMA_PERSIST_DIR)
        else:
            logger.info(
                "ChromaDB HTTP endpoint unavailable, using PersistentClient at %s",
                settings.CHROMA_PERSIST_DIR,
            )
            self.client = chromadb.PersistentClient(path=settings.CHROMA_PERSIST_DIR)
        self._stores: dict[str, Chroma] = {}
        self._hnsw_degraded: dict[str, str] = {}
        self._hash_cache: dict[str, tuple[set[str], float]] = {}
        self._hnsw_checked: set[str] = set()
        self._rw_lock = _RWLock()
        # 查询期失败的记录（见 query_failures）。**这是「静默降级」的可观测出口**：
        # 异步查询失败时返回 `[]`（多路召回容忍单路失败，这是有意的），但调用方
        # 若据此比对质量基线，就会把「索引坏了」误读成「检索质量下降」。
        self._query_failures: list[str] = []

    @property
    def embeddings(self):
        """懒加载 Embedding 模型，首次访问时才初始化"""
        if self._embeddings is None:
            self._embeddings = get_embeddings()
        return self._embeddings

    @property
    def query_failures(self) -> list[str]:
        """本次进程内查询失败的记录（`集合: 异常类型`），按发生顺序。

        ★ **为什么必须有这个出口**：异步查询失败会返回 `[]`，于是上游无法区分
        「知识库确实没有」与「索引坏了」。实测后果：HNSW 段文件未落盘时，
        集合可能**通过建索引期的就绪检查、却在检索期**才失败 —— 检索链静默返回空，
        门禁把这种**无意义的指标**当成正常指标去比对基线，
        既可能报出**巨大的假回归**（实测 hit@1 从 0.95 掉到 0.725），
        也可能**掩盖真实退化**。

        调用方（如 `evaluation.gates.retrieval_gate`）应在比对指标**之前**断言它为空。
        """
        return list(self._query_failures)

    def record_query_failure(self, note: str, *, exc: BaseException | None = None) -> None:
        """★ 全仓**唯一**的失败记录入口（B7），并给出「**一次失败 = 一条记录**」的机械保证。

        旧实现里向量路径直接 `self._query_failures.append(...)`，而 BM25 / 服务路由
        失败既不 append 也不抛 ⇒ 「记录失败」这件事没有单一去处，加门也无从加起。
        现在所有生产者都调这个方法（`vectorstore` 自身、`rag.retrieval.bm25`、`rag.retrieval.routes` 的两处收敛点）。

        ★★ `exc`（F3，覆盖面收进一处）：收敛点有**两层** ——
          ① 生产者就地记录（`rag.retrieval.bm25.bm25_search` 取 collection 失败 ⇒ 记录后 `raise`）；
          ② 路由包装收敛（`rag.retrieval.routes._safe_to_thread` **按路由逐个**把异常/超时收敛成空结果）。
          同一个异常穿过两层时，若两处各记一条，门禁那句「有 N 次检索期查询异常」会把
          **一次**故障数成两次 —— 计数虚高同样是「多套现实」。
          ⇒ 传入 `exc` 时以**异常对象身份**为去重键（已记过 ⇒ 第二条不落），
          ★ 刻意**不**用字符串前缀/文案匹配去重：那依赖 Chroma 的报错文案，升级即失效
          （本项目已有「靠字符串猜语义」的教训）。
          带 `__slots__`、无法挂属性的异常类型 ⇒ 宁可多记一条，也**绝不**丢证据
          （漏报会让「坏了」重新伪装成「没查到」，重复计数只是把 N 报大）。
        """
        if exc is not None and getattr(exc, _FAILURE_NOTE_ATTR, None) is not None:
            return
        self._query_failures.append(note)
        if exc is not None:
            try:
                setattr(exc, _FAILURE_NOTE_ATTR, note)
            except (AttributeError, TypeError):  # noqa: PERF203 — 极少数异常类型不可挂属性
                logger.debug("异常对象不可挂属性，跳过幂等标记: %s", note)

    def reset_query_failures(self) -> None:
        """★ 每个「独立取证单元」开跑前调一次，**只允许**在单元边界（不在单元内部）：
        ① `evaluation.gates.retrieval_gate` 每条 query 之前（`finally` 里紧接着收割）；
        ② `evaluation.task_eval.runner.run_case` 每次检索探针之前；
        ③ `evaluation.task_eval.cli._reprobe` 每条 record 的 reprobe 之前
           （修复批 Important-1：reprobe 与 ② 同构 —— 一次探针 = 一个单元，
           原先直接写 `probe.status` 会把路由故障吞掉并把 `error` 降回 ok/empty）。

        ★★ v1.3（checkpoint 8 裁定 R1-A）：原列的第三点（`rag/routes._amulti_route_search`
           每轮开头）已**撤销** —— 单元**内部**的清空会销毁本单元尚未被消费的失败证据
           （一条 query 跑多轮，后轮 reset 抹掉前轮的记录），实测净降低检测能力。
           回归锁：`scripts/gates/evidence_chain_gate.py` 的 `8k`（期望文件集随 ③ 同步）。
        """
        self._query_failures.clear()

    def _ensure_hnsw_params(self, collection_name: str) -> None:
        """确保已有集合的 HNSW 索引参数为目标配置

        ChromaDB 的 `get_or_create_collection(metadata=...)` 在集合已存在时
        不会更新 metadata，需要单独调用 `modify()` 写入。
        """
        try:
            collection = self.client.get_collection(collection_name)
            current = collection.metadata or {}
            if collection.count() > 0:
                missing = [key for key in _HNSW_COLLECTION_METADATA if key not in current]
                legacy = [key for key in _LEGACY_HNSW_KEYS if key in current]
                if missing or legacy:
                    logger.warning(
                        "Collection '%s' needs rebuild for HNSW params (missing=%s legacy=%s)",
                        collection_name,
                        missing,
                        legacy,
                    )
                    return
            # 只有当缺少目标字段时才更新（避免不必要的 I/O）
            needs_update = any(
                key not in current or str(current.get(key, "")) != str(val)
                for key, val in _HNSW_COLLECTION_METADATA.items()
            )
            if needs_update:
                merged = {**current, **_HNSW_COLLECTION_METADATA}
                collection.modify(metadata=merged)
                logger.info(
                    "Updated HNSW params for collection '%s': %s",
                    collection_name,
                    _HNSW_COLLECTION_METADATA,
                )
            self._hnsw_degraded.pop(collection_name, None)
        except Exception as e:
            self._hnsw_degraded[collection_name] = str(e)
            logger.debug("Could not update HNSW params for '%s': %s", collection_name, e)

    def get_store(self, collection_name: str = "data_structure") -> Chroma:
        """获取或创建向量存储（HNSW 索引参数在创建时写入，已有集合自动更新）"""
        if collection_name in self._stores:
            return self._stores[collection_name]
        # 新集合：创建时指定 HNSW 参数
        # 若集合已存在，get_or_create_collection 不会更新 metadata，
        # 因此无论新旧都通过 _ensure_hnsw_params 保证参数一致
        try:
            self._stores[collection_name] = Chroma(
                client=self.client,
                collection_name=collection_name,
                embedding_function=self.embeddings,
                collection_metadata=_HNSW_COLLECTION_METADATA,
            )
            if collection_name not in self._hnsw_checked:
                self._ensure_hnsw_params(collection_name)
                self._hnsw_checked.add(collection_name)
        except Exception as e:
            self._hnsw_degraded[collection_name] = str(e)
            # HNSW 参数解析失败（Chroma 版本不兼容或索引损坏），
            # 回退为不传 HNSW metadata，让 Chroma 使用默认参数
            logger.warning(
                "get_store('%s') with HNSW metadata failed (%s), retrying without",
                collection_name,
                e,
            )
            self._stores[collection_name] = Chroma(
                client=self.client,
                collection_name=collection_name,
                embedding_function=self.embeddings,
            )
        return self._stores[collection_name]
