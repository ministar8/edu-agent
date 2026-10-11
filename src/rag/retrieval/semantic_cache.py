"""语义缓存（基于 ChromaDB）：缓存 RAG 检索结果。

按 query 语义相似度缓存 `FusedEvidence`：向量存于专用 ChromaDB 集合
``semantic_cache``。当收到语义相近的 query 时直接复用缓存的 FusedEvidence，
跳过整条检索链（向量检索、BM25、融合、验证）。

只缓存**检索层** —— LLM 生成、治理与反思仍在每次请求时执行，
保证答案新鲜度与用户画像感知。
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
from typing import Any

from core.settings import settings
from rag.retrieval._semantic_cache_codec import (
    _COLLECTION_NAME,
    _DATA_DIR,
    _JSONL_FILE,
    _MAX_ENTRIES,
    _SIMILARITY_THRESHOLD,
    _TTL,
    _cache_key,
)
from rag.retrieval._semantic_cache_io import _EvidenceIoMixin
from rag.retrieval.evidence import FusedEvidence

logger = logging.getLogger(__name__)


# ── SemanticCache 类 ──────────────────────────────────────


class SemanticCache(_EvidenceIoMixin):
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
