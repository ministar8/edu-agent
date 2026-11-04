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

# 单路查询失败后的重试预算：首次 + 1 次。读操作幂等，重试安全。
# ★ 只对**瞬时故障**有效（embedding 服务抖动、连接被重置）；HNSW 段文件
#   未落盘的 "Nothing found on disk" 不可在进程内恢复，重试后仍会失败并记账。
_QUERY_ATTEMPTS = 2
_QUERY_RETRY_BACKOFF_S = 0.2


async def _retry_async(fn, *, attempts: int, backoff_s: float, on_error=None):
    """按次数重试一个协程工厂；全部失败时抛出最后一个异常。

    抽成模块级纯函数是为了可单测：预算（deadline）与失败记账由调用方负责。
    ``CancelledError`` 继承 BaseException，不会被 `except Exception` 吞掉。
    """
    last_exc: BaseException | None = None
    for attempt in range(1, attempts + 1):
        try:
            return await fn()
        except Exception as exc:
            last_exc = exc
            if on_error is not None:
                on_error(attempt, exc)
            if attempt >= attempts:
                break
            await asyncio.sleep(backoff_s)
    if last_exc is None:
        raise TimeoutError("retry budget exhausted")
    raise last_exc


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
        deadline = start + timeout

        async def _attempt() -> list[tuple[Document, float]]:
            remaining = deadline - time.perf_counter()
            if remaining <= 0:
                raise TimeoutError(f"query budget exhausted: {collection_name}")
            embedding = await asyncio.wait_for(
                self.embeddings.aembed_query(query), timeout=remaining
            )
            remaining = max(0.1, deadline - time.perf_counter())
            return await asyncio.wait_for(
                asyncio.to_thread(
                    self._similarity_search_by_embedding_sync,
                    collection_name,
                    embedding,
                    k,
                    filter,
                ),
                timeout=remaining,
            )

        def _on_error(attempt: int, exc: Exception) -> None:
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
                values={"k": k, "error_type": exc.__class__.__name__, "attempt": attempt},
            )
            logger.warning(
                "Async Chroma query failed for %s (attempt %d/%d): %s",
                collection_name,
                attempt,
                _QUERY_ATTEMPTS,
                exc,
            )

        try:
            results = await _retry_async(
                _attempt,
                attempts=_QUERY_ATTEMPTS,
                backoff_s=_QUERY_RETRY_BACKOFF_S,
                on_error=_on_error,
            )
        except Exception as e:
            # 重试耗尽才记账：一次故障 = 一条记录（record_query_failure 亦按异常身份去重）
            logger.warning(
                "Async Chroma query failed for %s after %d attempts: %s",
                collection_name,
                _QUERY_ATTEMPTS,
                e,
            )
            self.record_query_failure(f"{collection_name}: {e.__class__.__name__}", exc=e)
            return []

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
