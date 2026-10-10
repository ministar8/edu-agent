"""语义缓存（基于 ChromaDB）：缓存 RAG 检索结果。

按 query 语义相似度缓存 `FusedEvidence`：向量存于专用 ChromaDB 集合
``semantic_cache``。当收到语义相近的 query 时直接复用缓存的 FusedEvidence，
跳过整条检索链（向量检索、BM25、融合、验证）。

只缓存**检索层** —— LLM 生成、治理与反思仍在每次请求时执行，
保证答案新鲜度与用户画像感知。
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import threading
import time
from pathlib import Path
from typing import Any

from core.settings import settings
from rag.retrieval.evidence import FusedEvidence

logger = logging.getLogger(__name__)

# ── 默认值（可被 settings 覆盖）──────────────────────────────
_COLLECTION_NAME = "semantic_cache"
_DATA_DIR = Path(settings.CHROMA_PERSIST_DIR) / "semantic_cache"
_JSONL_FILE = _DATA_DIR / "evidence.jsonl"
_TTL = 1800  # 30 分钟
_MAX_ENTRIES = 500
_SIMILARITY_THRESHOLD = 0.88


# ── 辅助函数 ────────────────────────────────────────────────


def _cache_key(
    query: str,
    collection_name: str = "",
    filter_sig: str = "",
    params_sig: str = "",
) -> str:
    """由归一化 query + collection + filter + 检索参数生成确定性 key。

    Different collections、filters 或检索参数（use_rerank / RERANK_ENABLED /
    k / score_threshold / depth / max_tokens）不得共享缓存条目，
    即使 query 语义相似也不行。

    ★★ **本 key 刻意不含 `task_mode` / `policy_version` / `cache_scope`** ★★
    （原先由 `schema/task_policy.TaskPolicy.cache_key_parts()` 声明「必含」，该方法已于
    2026-10-07 作为死代码删除，其不变量转移到此处 —— 因为它**依赖一个隐式前提**。）

    **为什么不含也不出事**：本缓存只存 **`aretrieve_evidence` 返回的「纯检索结果」**，
    而所有 **policy 相关处理都在缓存之外**执行：

        aretrieve_evidence_with_retry(...)   ← 缓存发生处（agents/tools.py）
          ├─ _with_topup(...)                ← 缓存之后（preferred_layers / eligible_layers）
          ├─ finalize_with_layer_ranking(...) ← 缓存之后（legacy 池策略 + 排序 + 截断）
          └─ apply_evidence_policy(...)       ← 缓存之后（**release 裁剪，安全出口**）

    且 `aretrieve_evidence` **不 import** `apply_evidence_policy`
    ⇒ 缓存命中**也无法绕过 release 裁剪**（每次都按当前 policy 重做）⇒ 无泄露。

    另：`task_mode` 已**间接**进 key —— 召回 filter 来自 `policy.eligibility_where()`，
    而各 mode 的 `exam_resources` 不同 ⇒ filter 不同 ⇒ `filter_sig` 不同。
    （实测仅 `explain` 的 `eligibility_where()` 返回 `None`，不存在两个 mode 同时为空。）

    ⚠️ **改动须知**：若将来把 `_with_topup` / `finalize_with_layer_ranking` /
    `apply_evidence_policy` **移进** `aretrieve_evidence`（看起来是很自然的重构），
    则本缓存会**连 policy 裁剪结果一起缓存** ⇒ 策略变更后旧缓存继续命中 ⇒ **真泄露**。
    **届时必须先把 `task_mode` / `policy_version` / `cache_scope` 加进本 key。**
    """
    normalized = query.strip().lower()
    raw = f"{normalized}|{collection_name}|{filter_sig}|{params_sig}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def _serialize_evidence(fused: FusedEvidence) -> str:
    """把 FusedEvidence 序列化为 JSON 字符串，用于落盘存储。"""
    return fused.model_dump_json()


def _deserialize_evidence(data: str) -> FusedEvidence:
    """从 JSON 字符串反序列化 FusedEvidence。"""
    return FusedEvidence.model_validate_json(data)


# ── SemanticCache ─────────────────────────────────────────


class SemanticCache:
    """基于 ChromaDB 的 FusedEvidence 语义缓存。

    - 向量索引：ChromaDB 集合 ``semantic_cache``（余弦相似度）
    - 证据数据：JSONL 文件 ``semantic_cache/evidence.jsonl``
    - 内存元数据：dict，用于 TTL / LRU / 命中统计
    """

    def __init__(
        self,
        similarity_threshold: float = _SIMILARITY_THRESHOLD,
        ttl: int = _TTL,
        max_entries: int = _MAX_ENTRIES,
    ):
        self._similarity_threshold = similarity_threshold
        self._ttl = ttl
        self._max_entries = max_entries
        self._lock = threading.Lock()

        # 内存元数据：key → {timestamp, hit_count, query}
        self._meta: dict[str, dict[str, Any]] = {}

        # JSONL 偏移索引：key → 文件字节偏移，用于 O(1) 查找
        self._jsonl_offsets: dict[str, int] = {}

        # ChromaDB 集合（惰性初始化）
        self._collection = None
        self._embedding_fn = None

        # JSONL 存储
        self._jsonl_path = _JSONL_FILE
        self._data_dir = _DATA_DIR

        # 统计
        self._hits = 0
        self._misses = 0

    # ── 惰性初始化 ─────────────────────────────────────────

    def _build_collection_sync(self, mgr) -> None:
        """同步取/建缓存集合 + 触发可读性校验 + 载入 JSONL 元数据（happy path）。"""
        self._embedding_fn = mgr.embeddings

        # 取或建专用缓存集合
        self._collection = mgr.client.get_or_create_collection(
            name=_COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
        # 触发一次 count() 验证 HNSW 索引可读
        _count = self._collection.count()
        logger.info(
            "Semantic cache collection '%s' initialized, existing entries=%d",
            _COLLECTION_NAME,
            _count,
        )

        # 从 JSONL 加载元数据
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._load_meta_from_jsonl()

    def _recover_corrupt_sync(self, mgr) -> None:
        """HNSW 损坏的同步恢复：删集合 + 清 JSONL + 清内存索引（调用方随后立即重试）。"""
        if mgr is None:
            # manager 都拿不到，删集合无从谈起 —— 如实记录并继续，
            # 不要在这里再抛一个异常把原始原因盖掉
            logger.warning(
                "无法获取 vector store manager，跳过损坏集合删除（原始异常见上一条日志）"
            )
        else:
            try:
                mgr.client.delete_collection(_COLLECTION_NAME)
                logger.info(
                    "Deleted corrupted semantic_cache collection, will recreate on next attempt"
                )
            except Exception as del_err:
                logger.warning("Failed to delete corrupted semantic_cache: %s", del_err)
        # 清空 JSONL 避免孤儿数据
        try:
            if self._jsonl_path.exists():
                self._jsonl_path.unlink()
        except Exception as unlink_err:
            # 删除失败会留下孤儿 JSONL —— 下次启动会加载到本该被清掉的条目。
            # 同段里"删集合失败"是有 warning 的，这里不该静默。
            logger.warning("Failed to unlink semantic_cache JSONL: %s", unlink_err)
        self._meta.clear()
        self._jsonl_offsets.clear()

    def _ensure_init(self):
        """惰性初始化 ChromaDB 集合与 JSONL 存储。"""
        if self._collection is not None:
            return

        # 提前绑定：**错误处理路径也要能安全引用 `mgr`**。
        # `get_vector_store_manager()` 本身就可能抛异常（那正是进入 except 的原因之一），
        # 若此时在 except 里直接用 `mgr.client...`，会抛 UnboundLocalError
        # **掩盖掉原始异常** —— 排查时只能看到 UnboundLocalError，看不到真正的原因（backlog #12）。
        mgr = None
        for attempt in range(3):
            try:
                from rag.common.vectorstore import get_vector_store_manager

                mgr = get_vector_store_manager()
                self._build_collection_sync(mgr)
                return

            except Exception as e:
                err_msg = str(e).lower()
                if "hnsw" in err_msg or "segment reader" in err_msg:
                    # HNSW 索引损坏：删除损坏集合并重建（重试无意义）
                    logger.warning(
                        "Semantic cache HNSW index corrupted, deleting and rebuilding: %s", e
                    )
                    self._recover_corrupt_sync(mgr)
                    continue  # 立即重试创建新集合
                if attempt < 2:
                    logger.warning(
                        "Semantic cache init attempt %d failed: %s, retrying...", attempt + 1, e
                    )
                    time.sleep(0.5 * (attempt + 1))
                else:
                    logger.warning(
                        "Semantic cache init failed after %d attempts, cache disabled: %s",
                        attempt + 1,
                        e,
                    )
                    self._collection = None

    async def _build_collection_async(self, mgr) -> None:
        """异步取/建缓存集合 + 可读性校验 + 载入 JSONL 元数据（happy path）。"""
        self._embedding_fn = mgr.embeddings
        self._collection = await asyncio.to_thread(
            mgr.client.get_or_create_collection,
            name=_COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
        existing_count = await asyncio.to_thread(self._collection.count)
        logger.info(
            "Semantic cache collection '%s' initialized, existing entries=%d",
            _COLLECTION_NAME,
            existing_count,
        )
        await asyncio.to_thread(self._data_dir.mkdir, parents=True, exist_ok=True)
        await asyncio.to_thread(self._load_meta_from_jsonl)

    async def _recover_corrupt_async(self, mgr) -> None:
        """HNSW 损坏的异步恢复：删集合 + 清 JSONL + 清内存索引（调用方随后立即重试）。"""
        if mgr is None:
            logger.warning(
                "无法获取 vector store manager，跳过损坏集合删除（async）（原始异常见上一条日志）"
            )
        else:
            try:
                await asyncio.to_thread(mgr.client.delete_collection, _COLLECTION_NAME)
                logger.info("Deleted corrupted semantic_cache collection (async)")
            except Exception as del_err:
                logger.warning("Failed to delete corrupted semantic_cache (async): %s", del_err)
        try:
            if self._jsonl_path.exists():
                self._jsonl_path.unlink()
        except Exception as unlink_err:
            # 删除失败会留下孤儿 JSONL —— 下次启动会加载到本该被清掉的条目。
            # 同段里"删集合失败"是有 warning 的，这里不该静默。
            logger.warning("Failed to unlink semantic_cache JSONL: %s", unlink_err)
        self._meta.clear()
        self._jsonl_offsets.clear()

    async def _aensure_init(self):
        """异步惰性初始化包装：重试等待不阻塞事件循环。"""
        if self._collection is not None:
            return

        # 与同步版同理：提前绑定，保证 except 里引用 `mgr` 不会 UnboundLocalError
        mgr = None
        for attempt in range(3):
            try:
                from rag.common.vectorstore import get_vector_store_manager

                mgr = await asyncio.to_thread(get_vector_store_manager)
                await self._build_collection_async(mgr)
                return
            except Exception as e:
                err_msg = str(e).lower()
                if "hnsw" in err_msg or "segment reader" in err_msg:
                    logger.warning(
                        "Semantic cache HNSW index corrupted (async), deleting and rebuilding: %s",
                        e,
                    )
                    await self._recover_corrupt_async(mgr)
                    continue
                if attempt < 2:
                    logger.warning(
                        "Semantic cache async init attempt %d failed: %s, retrying...",
                        attempt + 1,
                        e,
                    )
                    await asyncio.sleep(0.5 * (attempt + 1))
                else:
                    logger.warning(
                        "Semantic cache async init failed after %d attempts, cache disabled: %s",
                        attempt + 1,
                        e,
                    )
                    self._collection = None

    def _load_meta_from_jsonl(self):
        """启动时从 JSONL 文件加载元数据条目。

        `time.monotonic()` 重启后会归零，故**不可信**存储的单调时间戳；
        改用 ChromaDB 元数据里的 wall-clock `stored_at` 判断条目是否仍有效。
        """
        if not self._jsonl_path.exists():
            return
        try:
            count = 0
            now_wall = time.time()
            with open(self._jsonl_path, encoding="utf-8") as f:
                while True:
                    pos = f.tell()
                    line = f.readline()
                    if not line:
                        break
                    line = line.strip()
                    if not line:
                        continue
                    entry = json.loads(line)
                    key = entry.get("key", "")
                    query = entry.get("query", "")
                    if not key:
                        continue
                    # 有 wall-clock stored_at 则用其判定，否则视为已过期
                    stored_at = entry.get("stored_at", 0)
                    if stored_at and (now_wall - stored_at) < self._ttl:
                        self._meta[key] = {
                            "query": query,
                            "timestamp": time.monotonic(),  # 重置为当前单调时钟
                            "hit_count": entry.get("hit_count", 0),
                        }
                        self._jsonl_offsets[key] = pos
                        count += 1
            logger.info("Semantic cache loaded %d valid metadata entries from JSONL", count)
        except Exception as e:
            logger.warning("Failed to load semantic cache JSONL: %s", e)

    # ── 对外 API ───────────────────────────────────────────

    def _find_match(
        self, query: str, collection_name: str, filter_sig: str, params_sig: str, started: float
    ) -> tuple[float, str | None]:
        """嵌入 query 并找出过阈值、上下文匹配的缓存条目；返回 (similarity, match_id|None)。"""
        # 对 query 做嵌入
        query_embedding = self._embedding_fn.embed_query(query)

        # 在 ChromaDB 中检索相近 query
        results = self._query_collection(query_embedding)
        if not results or not results["distances"] or not results["distances"][0]:
            return 0.0, None

        # ★ B1（§1.5 R4）：删除本模块私有的 `1.0 - distance` 第二套实现，
        #   统一走 `embeddings.similarity_from_distance` 这**唯一**换算点。
        #   本类恒按 cosine 建集合（见 :154/:233 `metadata={"hnsw:space": "cosine"}`），
        #   故 `or "cosine"` 是**与本类自身创建口径对齐**，不是跨未知集合的瞎猜；
        #   cosine 下 `max(0,1-d)` 与旧 `1-d` 对「是否过阈值」的判定完全等价。
        from rag.common.embeddings import similarity_from_distance

        distance = results["distances"][0][0]
        _space = (self._collection.metadata or {}).get("hnsw:space") or "cosine"
        similarity = similarity_from_distance(distance, _space)

        if similarity < self._similarity_threshold:
            elapsed_ms = (time.perf_counter() - started) * 1000
            logger.debug(
                "Semantic cache miss: query='%s' best_sim=%.4f threshold=%.2f %.1fms",
                query[:50],
                similarity,
                self._similarity_threshold,
                elapsed_ms,
            )
            return similarity, None

        # 命中 —— 校验 collection 上下文一致
        match_meta = (results["metadatas"] or [[]])[0]
        match_meta = match_meta[0] if match_meta else {}
        # 校验 collection + filter 上下文匹配（避免跨集合 / 跨 filter 误命中）
        if (
            collection_name != match_meta.get("collection_name", "")
            or filter_sig != match_meta.get("filter_sig", "")
            or params_sig != match_meta.get("params_sig", "")
        ):
            return similarity, None
        return similarity, results["ids"][0][0]

    def _touch_hit(self, match_id: str) -> dict[str, Any] | None:
        """校验 TTL 并更新命中计数；缺失/过期返回 None（过期时顺带逐出）。"""
        with self._lock:
            meta = self._meta.get(match_id)
            if meta is None:
                # 元数据缺失（陈旧），按未命中处理
                return None
            if time.monotonic() - meta["timestamp"] > self._ttl:
                # TTL 过期，逐出
                self._evict(match_id)
                return None
            # 更新访问时间与命中计数
            meta["timestamp"] = time.monotonic()
            meta["hit_count"] = meta.get("hit_count", 0) + 1
            return meta

    def _log_hit(self, query: str, meta: dict[str, Any], similarity: float, started: float) -> None:
        elapsed_ms = (time.perf_counter() - started) * 1000
        logger.info(
            "Semantic cache HIT: query='%s' matched='%s' sim=%.4f hits=%d %.1fms",
            query[:50],
            meta["query"][:50],
            similarity,
            self._hits,
            elapsed_ms,
        )

    def lookup(
        self, query: str, collection_name: str = "", filter_sig: str = "", params_sig: str = ""
    ) -> tuple[FusedEvidence | None, float]:
        """查找语义相近的缓存结果。

        返回 (fused_evidence, similarity_score)；无超过阈值者返回 (None, 0.0)。
        """
        if not settings.SEMANTIC_CACHE_ENABLED:
            return None, 0.0

        self._ensure_init()
        if self._collection is None:
            return None, 0.0

        start = time.perf_counter()
        try:
            similarity, match_id = self._find_match(
                query, collection_name, filter_sig, params_sig, start
            )
            if match_id is None:
                self._misses += 1
                return None, similarity

            meta = self._touch_hit(match_id)
            if meta is None:
                self._misses += 1
                return None, similarity

            # 从 JSONL 加载 FusedEvidence
            fused = self._load_evidence(match_id)
            if fused is None:
                self._misses += 1
                return None, similarity

            self._hits += 1
            self._log_hit(query, meta, similarity, start)
            return fused, similarity

        except Exception as e:
            logger.warning("Semantic cache lookup error: %s", e)
            self._misses += 1
            return None, 0.0

    async def alookup(
        self, query: str, collection_name: str = "", filter_sig: str = "", params_sig: str = ""
    ) -> tuple[FusedEvidence | None, float]:
        """异步 lookup 包装：初始化不阻塞事件循环。"""
        if not settings.SEMANTIC_CACHE_ENABLED:
            return None, 0.0
        await self._aensure_init()
        if self._collection is None:
            return None, 0.0
        return await asyncio.to_thread(self.lookup, query, collection_name, filter_sig, params_sig)

    def store(
        self,
        query: str,
        fused: FusedEvidence,
        collection_name: str = "",
        filter_sig: str = "",
        params_sig: str = "",
    ) -> None:
        """把一次检索结果写入语义缓存。"""
        if not settings.SEMANTIC_CACHE_ENABLED:
            return

        self._ensure_init()
        if self._collection is None:
            return

        try:
            key = _cache_key(query, collection_name, filter_sig, params_sig)
            wall_now = time.time()
            query_embedding = self._embedding_fn.embed_query(query)

            # upsert 前校验集合有效
            if not self._check_collection_alive():
                return

            with self._lock:
                # 满容量时先逐出
                if len(self._meta) >= self._max_entries and key not in self._meta:
                    self._evict_oldest()

                # 存元数据
                self._meta[key] = {
                    "query": query,
                    "timestamp": time.monotonic(),
                    "hit_count": 0,
                    "stored_at": wall_now,
                }

                # 写入 ChromaDB
                self._collection.upsert(
                    ids=[key],
                    embeddings=[query_embedding],
                    metadatas=[
                        {
                            "query": query,
                            "stored_at": wall_now,
                            "collection_name": collection_name,
                            "filter_sig": filter_sig,
                            "params_sig": params_sig,
                        }
                    ],
                )

                # 把证据写入 JSONL（追加）
                self._save_evidence(key, query, fused)

            logger.debug("Semantic cache STORE: query='%s' key=%s", query[:50], key)

        except Exception as e:
            logger.warning("Semantic cache store error: %s", e)

    async def astore(
        self,
        query: str,
        fused: FusedEvidence,
        collection_name: str = "",
        filter_sig: str = "",
        params_sig: str = "",
    ) -> None:
        """异步 store 包装：初始化不阻塞事件循环。"""
        if not settings.SEMANTIC_CACHE_ENABLED:
            return
        await self._aensure_init()
        if self._collection is None:
            return
        await asyncio.to_thread(self.store, query, fused, collection_name, filter_sig, params_sig)

    def stats(self) -> dict[str, Any]:
        """返回缓存统计。"""
        total = self._hits + self._misses
        return {
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": round(100 * self._hits / max(total, 1), 1),
            "entries": len(self._meta),
            "max_entries": self._max_entries,
        }

    # ── 内部实现 ───────────────────────────────────────────

    def _is_stale_error(self, err: Exception) -> bool:
        """判断错误是否表示集合被外部删除 / 损坏。"""
        msg = str(err).lower()
        return "does not exist" in msg or "nothing found on disk" in msg

    def _reinit_if_stale(self, err: Exception) -> bool:
        """陈旧引用报错后尝试重建集合。

        重建成功（self._collection 现有效）返回 True；缓存仍禁用返回 False。
        """
        if not self._is_stale_error(err):
            return False
        logger.warning("Semantic cache collection stale, re-initializing: %s", err)
        self._collection = None
        self._ensure_init()
        return self._collection is not None

    def _query_collection(self, query_embedding: list[float]) -> dict:
        """查询缓存集合；陈旧时自动重建。"""
        try:
            return self._collection.query(
                query_embeddings=[query_embedding],
                n_results=1,
                include=["distances", "metadatas"],
            )
        except Exception as e:
            if self._reinit_if_stale(e):
                return self._collection.query(
                    query_embeddings=[query_embedding],
                    n_results=1,
                    include=["distances", "metadatas"],
                )
            raise

    def _check_collection_alive(self) -> bool:
        """校验集合仍可访问；陈旧时重建。

        集合存活返回 True；缓存已禁用返回 False。
        """
        try:
            _ = self._collection.count()
            return True
        except Exception as e:
            return self._reinit_if_stale(e)

    def _read_evidence_at_offset(self, key: str, offset: int) -> FusedEvidence | None:
        """快路径：按偏移读取并解析；失败/不匹配返回 None（调用方退回线性扫描）。"""
        try:
            with open(self._jsonl_path, encoding="utf-8") as f:
                f.seek(offset)
                line = f.readline().strip()
                if line:
                    entry = json.loads(line)
                    if entry.get("key") == key and "evidence" in entry:
                        return _deserialize_evidence(entry["evidence"])
        except Exception:  # noqa: S110 — 有意忽略：读偏移索引失败即退回线性扫描
            # 必须留痕（§2.2 规范 2：禁止无日志的 pass）。
            # 偏移索引若**持续**失效，每次 lookup 都会退化成线性扫描 ——
            # 这是**性能退化、不影响正确性**，所以用 DEBUG 而不是 WARNING；
            # 但完全不记的话，这个退化在日志里就彻底不可见。
            logger.debug("偏移索引读取失败，退回线性扫描 key=%s", key, exc_info=True)
        return None

    def _scan_evidence_jsonl(self, key: str) -> FusedEvidence | None:
        """慢路径：线性扫描 JSONL（并重建偏移索引），跳过损坏行。"""
        if not self._jsonl_path.exists():
            return None
        found = None
        corrupt = 0
        try:
            with open(self._jsonl_path, encoding="utf-8") as f:
                while True:
                    pos = f.tell()
                    line = f.readline()
                    if not line:
                        break
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                    except json.JSONDecodeError:
                        # **单行损坏不能让整个扫描失败。**
                        # 坏行的现实来源：上次 append 写到一半进程被杀。
                        # 原实现让 json.loads 的异常冒到外层 except，于是**一条坏行
                        # 使所有未进偏移索引的键全部查不到** —— 缓存静默变空，
                        # 只表现为"重启后命中率变低"，没有任何错误可见。
                        # 跳过坏行、继续扫描，并在最后统一告警。
                        corrupt += 1
                        continue
                    entry_key = entry.get("key", "")
                    # 扫描时顺带登记偏移
                    if entry_key not in self._jsonl_offsets:
                        self._jsonl_offsets[entry_key] = pos
                    if entry_key == key and "evidence" in entry:
                        try:
                            found = _deserialize_evidence(entry["evidence"])
                        except Exception:
                            logger.warning("Semantic cache 条目反序列化失败 key=%s，已跳过", key)
        except Exception as e:
            logger.warning("Failed to load evidence for key=%s: %s", key, e)
            return None
        if corrupt:
            logger.warning("Semantic cache JSONL 有 %d 行损坏，已跳过", corrupt)
        return found

    def _load_evidence(self, key: str) -> FusedEvidence | None:
        """从 JSONL 文件按键加载 FusedEvidence。

        用内存里的 key→offset 索引做 O(1) 查找而非线性扫描；索引失效时退回线性扫描。
        """
        # 快路径：走偏移索引
        offset = self._jsonl_offsets.get(key)
        if offset is not None:
            found = self._read_evidence_at_offset(key, offset)
            if found is not None:
                return found
        # 慢路径：线性扫描（并重建偏移索引）
        return self._scan_evidence_jsonl(key)

    def _save_evidence(self, key: str, query: str, fused: FusedEvidence) -> None:
        """把证据条目追加到 JSONL 文件。必须在 `_lock` 持有下调用。"""
        try:
            meta = self._meta.get(key, {})
            entry = {
                "key": key,
                "query": query,
                "stored_at": meta.get("stored_at", time.time()),
                "evidence": _serialize_evidence(fused),
            }
            with open(self._jsonl_path, "a", encoding="utf-8") as f:
                offset = f.tell()
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            self._jsonl_offsets[key] = offset
        except Exception as e:
            logger.warning("Failed to save evidence for key=%s: %s", key, e)

    def _evict(self, key: str) -> None:
        """从缓存中逐出单条。"""
        self._meta.pop(key, None)
        try:
            if self._collection is not None:
                self._collection.delete(ids=[key])
        except Exception as e:
            logger.debug("Failed to delete cache entry from ChromaDB: %s", e)
        # 注：JSONL 条目不删除（只追加）；陈旧条目在 lookup 时按 TTL 过滤。
        # 需要时后续再加定期压缩。

    def _evict_oldest(self) -> None:
        """逐出最旧（最久未访问）的条目。"""
        if not self._meta:
            return
        oldest_key = min(self._meta, key=lambda k: self._meta[k]["timestamp"])
        self._evict(oldest_key)

    def clear(self) -> None:
        """清空语义缓存（知识库全量重建时调用）。

        删除底层集合并重置引用，让下次访问时重新初始化；同时清内存索引与 JSONL。
        """
        with self._lock:
            self._meta.clear()
            self._jsonl_offsets.clear()
            self._collection = None
            try:
                from rag.common.vectorstore import get_vector_store_manager

                get_vector_store_manager().delete_collection(_COLLECTION_NAME)
            except Exception as e:
                logger.debug("Failed to delete semantic_cache collection: %s", e)
            try:
                if self._jsonl_path.exists():
                    self._jsonl_path.unlink()
            except Exception as unlink_err:
                # 同上：孤儿 JSONL 会被下次启动加载回来
                logger.warning("Failed to unlink semantic_cache JSONL: %s", unlink_err)


# ── 模块级单例 ──────────────────────────────────────────────

_semantic_cache: SemanticCache | None = None


def get_semantic_cache() -> SemanticCache:
    """获取或创建全局 SemanticCache 单例。"""
    global _semantic_cache
    if _semantic_cache is None:
        threshold = settings.SEMANTIC_CACHE_SIMILARITY_THRESHOLD
        _semantic_cache = SemanticCache(similarity_threshold=threshold)
    return _semantic_cache
