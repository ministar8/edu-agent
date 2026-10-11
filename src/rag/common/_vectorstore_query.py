"""VectorStoreManager 的查询路径（从 vectorstore.py 拆出，行为等价）。"""

from __future__ import annotations

import asyncio
import logging
import time

from langchain_core.documents import Document

from core.settings import settings
from rag.common._vectorstore_base import _VectorStoreBase
from rag.common.metrics import metrics

logger = logging.getLogger(__name__)


class _QueryMixin(_VectorStoreBase):
    """向量检索：同步/异步相似度查询。"""

    def similarity_search_with_score(
        self,
        collection_name: str,
        query: str,
        k: int,
        filter: dict | None = None,
    ):
        store = self.get_store(collection_name)
        search_kwargs = {"k": k}
        if filter:
            search_kwargs["filter"] = filter
        if self.client_mode == "persistent":
            with self._rw_lock.read_lock():
                return store.similarity_search_with_score(query, **search_kwargs)
        return store.similarity_search_with_score(query, **search_kwargs)

    def _similarity_search_by_embedding_sync(
        self,
        collection_name: str,
        embedding: list[float],
        k: int,
        filter: dict | None = None,
    ) -> list[tuple[Document, float]]:
        collection = self.client.get_collection(collection_name)
        # ★ B1（§1.5 R4）：距离→相似度的**唯一**换算点。space 从集合元数据读，**不给默认值**
        #   （`"l2"` 那种默认就是猜）；未知 space 由 `similarity_from_distance` 抛错。
        #   放在 try 外 ⇒ 方向未知时是**硬失败**，不会被下面的 `except` 静默折成 0.0。
        from rag.common.embeddings import similarity_from_distance

        space = (collection.metadata or {}).get("hnsw:space")
        if not space:
            raise ValueError(f"{collection_name}: 集合元数据里没有 hnsw:space，方向无法确定")
        query_kwargs = {
            "query_embeddings": [embedding],
            "n_results": max(1, int(k)),
            "include": ["documents", "metadatas", "distances"],
        }
        if filter:
            query_kwargs["where"] = filter

        def _query():
            return collection.query(**query_kwargs)

        if self.client_mode == "persistent":
            with self._rw_lock.read_lock():
                raw = _query()
        else:
            raw = _query()

        docs = (raw.get("documents") or [[]])[0] or []
        metadatas = (raw.get("metadatas") or [[]])[0] or []
        distances = (raw.get("distances") or [[]])[0] or []
        results: list[tuple[Document, float]] = []
        for content, metadata, distance in zip(docs, metadatas, distances):
            doc = Document(page_content=str(content or ""), metadata=dict(metadata or {}))
            try:
                d = float(distance)
            except (TypeError, ValueError):
                # ★ 回退路径（用户点名「不能只修主路径而遗漏回退路径」）：距离不可解析时
                #   取**最低相似度** 0.0（新语义下排在最后），而不是旧稿把原始距离当 score
                #   那种「数值合法但方向反了」的取值。
                score = 0.0
            else:
                # 主路径：经唯一换算点把 Chroma 距离转成相似度（越高越相似）。
                score = similarity_from_distance(d, space)
            results.append((doc, score))
        return results

    async def asimilarity_search_with_score(
        self,
        collection_name: str,
        query: str,
        k: int,
        filter: dict | None = None,
        timeout: float | None = None,
    ) -> list[tuple[Document, float]]:
        start = time.perf_counter()
        timeout = timeout or float(settings.TOOL_CALL_TIMEOUT or 30)
        try:
            embedding = await asyncio.wait_for(self.embeddings.aembed_query(query), timeout=timeout)
            remaining_timeout = max(0.1, timeout - (time.perf_counter() - start))
            results = await asyncio.wait_for(
                asyncio.to_thread(
                    self._similarity_search_by_embedding_sync,
                    collection_name,
                    embedding,
                    k,
                    filter,
                ),
                timeout=remaining_timeout,
            )
            metrics.emit(
                event="chroma_query",
                stage="vectorstore",
                duration_ms=round((time.perf_counter() - start) * 1000, 3),
                tags={
                    "collection": collection_name,
                    "client_mode": self.client_mode,
                    "query_mode": "query_embeddings",
                },
                values={"k": k, "result_count": len(results)},
            )
            return results
        except Exception as e:
            metrics.emit(
                event="chroma_query",
                stage="vectorstore",
                status="error",
                duration_ms=round((time.perf_counter() - start) * 1000, 3),
                tags={
                    "collection": collection_name,
                    "client_mode": self.client_mode,
                    "query_mode": "query_embeddings",
                },
                values={"k": k, "error_type": e.__class__.__name__},
            )
            logger.warning("Async Chroma query failed for %s: %s", collection_name, e)
            self.record_query_failure(f"{collection_name}: {e.__class__.__name__}", exc=e)
            return []
