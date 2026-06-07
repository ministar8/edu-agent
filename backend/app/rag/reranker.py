"""Reranker 重排序模块

使用本地 TEI bge-reranker-v2-m3 对向量检索结果进行精排。
通过 RERANK_ENABLED 开关控制。
"""

from __future__ import annotations

import hashlib
import logging
import time

import httpx
from langchain_core.documents import Document

from app.config import settings

logger = logging.getLogger(__name__)

# 文档截断长度：截断前段语义即可
_MAX_DOC_CHARS = 2000
_RERANK_CACHE_TTL = 300
_RERANK_CACHE_MAX = 128
_rerank_cache: dict[str, tuple[list[Document], float]] = {}


def _document_cache_id(doc: Document) -> str:
    metadata = doc.metadata or {}
    return str(
        metadata.get("content_hash")
        or metadata.get("chunk_id")
        or f"{metadata.get('source') or metadata.get('source_file') or ''}:{metadata.get('chunk_index') or ''}:{doc.page_content[:120]}"
    )


def _rerank_cache_key(query: str, documents: list[Document], top_k: int) -> str:
    raw = "\n".join([query, str(top_k), *[_document_cache_id(doc) for doc in documents]])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def rerank(
    query: str,
    documents: list[Document],
    top_k: int = 5,
    lightweight: bool = False,
) -> list[Document]:
    """对检索结果进行重排序

    Args:
        query: 用户查询
        documents: 候选文档列表
        top_k: 返回前 top_k 个结果

    Returns:
        按 relevance_score 降序排列的文档列表（metadata 含 rerank_score）
    """
    if not documents:
        return []

    if not settings.RERANK_ENABLED:
        return documents[:top_k]

    start = time.perf_counter()

    # ── 预筛选：按可用分数保留 top N 候选 ──
    # lightweight（L2）：候选池 10，省延迟；deep（L3）：候选池 30，高精度
    _RERANK_MAX_CANDIDATES = 10 if lightweight else 30
    original_count = len(documents)
    if len(documents) > _RERANK_MAX_CANDIDATES:
        def _sort_score(d: Document) -> float:
            rs = d.metadata.get("recall_score")
            if rs is not None and float(rs) > 0:
                return float(rs)
            rrs = d.metadata.get("rerank_score")
            if rrs is not None and float(rrs) > 0:
                return float(rrs)
            return 0.0
        documents = sorted(documents, key=_sort_score, reverse=True)[:_RERANK_MAX_CANDIDATES]
        logger.debug("Rerank pre-filter: %d → %d", original_count, len(documents))

    cache_key = _rerank_cache_key(query, documents, top_k)
    cached = _rerank_cache.get(cache_key)
    now = time.monotonic()
    if cached is not None:
        cached_docs, cached_at = cached
        if now - cached_at < _RERANK_CACHE_TTL:
            logger.debug("Rerank cache hit q=%s docs=%d top_k=%d", query[:30], len(documents), top_k)
            return cached_docs
        del _rerank_cache[cache_key]

    texts = [doc.page_content[:_MAX_DOC_CHARS] for doc in documents]

    # ── 调用本地 TEI /rerank ──
    api_url = f"{settings.RERANK_LOCAL_URL}/rerank"
    payload = {
        "query": query,
        "texts": texts,
        "top_n": min(top_k, len(documents)),
    }

    try:
        with httpx.Client(timeout=settings.RERANK_TIMEOUT) as client:
            resp = client.post(api_url, json=payload)
            resp.raise_for_status()
        results = resp.json()
    except httpx.HTTPStatusError as e:
        logger.error("Rerank HTTP error: %s %s", e.response.status_code, e.response.text[:200])
        return documents[:top_k]
    except Exception as e:
        logger.error("Rerank call failed: %s", e, exc_info=True)
        return documents[:top_k]

    if not results:
        logger.warning("Rerank returned empty results, using original order")
        return documents[:top_k]

    # TEI 返回格式: [{"index": 0, "score": 0.98, "text": "..."}, ...]
    result: list[Document] = []
    for item in results:
        idx = item.get("index", -1)
        score = item.get("score", 0.0)
        if 0 <= idx < len(documents):
            doc = documents[idx]
            doc.metadata["rerank_score"] = round(float(score), 4)
            doc.metadata["rerank_method"] = "bge-reranker-v2-m3"
            result.append(doc)

    # 补充未排序的文档
    ranked_indices = {item.get("index", -1) for item in results}
    if len(result) < top_k:
        for i, doc in enumerate(documents):
            if i not in ranked_indices and len(result) < top_k:
                doc.metadata["rerank_score"] = 0.0
                doc.metadata["rerank_method"] = "bge-reranker-v2-m3-fallback"
                result.append(doc)

    elapsed_ms = (time.perf_counter() - start) * 1000
    top_score = result[0].metadata.get("rerank_score", 0) if result else 0
    logger.debug(
        "Rerank q=%s in=%d out=%d top=%.4f %.1fms lw=%s",
        query[:30], len(documents), len(result), top_score, elapsed_ms, lightweight,
    )

    if len(_rerank_cache) > _RERANK_CACHE_MAX:
        _evict_count = max(1, len(_rerank_cache) // 4)
        for _key in list(_rerank_cache.keys())[:_evict_count]:
            del _rerank_cache[_key]
    _rerank_cache[cache_key] = (result, time.monotonic())

    return result