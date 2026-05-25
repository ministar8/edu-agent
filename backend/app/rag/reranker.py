"""Reranker 重排序模块

使用阿里云百炼 qwen3-rerank API 对向量检索结果进行精排。
基于跨编码器模型，效果优于本地 ColBERT，零本地依赖。

通过 RERANK_ENABLED 开关控制。
API 使用与 LLM 相同的 API Key（LLM_API_KEY）。
"""

from __future__ import annotations

import logging
import time

import httpx
from langchain_core.documents import Document

from app.config import settings

logger = logging.getLogger(__name__)

# 文档截断长度：rerank API 单条最大 4000 token，截断前段语义即可
_MAX_DOC_CHARS = 800

# API 单次最大文档数
_MAX_API_DOCS = 100


def rerank(
    query: str,
    documents: list[Document],
    top_k: int = 5,
) -> list[Document]:
    """对检索结果进行 qwen3-rerank API 重排序

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

    if not settings.LLM_API_KEY:
        logger.warning("Rerank skipped: LLM_API_KEY not configured")
        return documents[:top_k]

    start = time.perf_counter()

    # ── 预筛选：按 recall_score 保留 top N 候选 ──
    # 从 20 → 30 配合 coarse_k 扩大，给 reranker 更大甄别空间
    _RERANK_MAX_CANDIDATES = 30
    original_count = len(documents)
    if len(documents) > _RERANK_MAX_CANDIDATES:
        documents = sorted(
            documents,
            key=lambda d: float(d.metadata.get("recall_score") or 0),
            reverse=True,
        )[:_RERANK_MAX_CANDIDATES]
        logger.info("Rerank pre-filter: %d -> %d candidates", original_count, len(documents))

    # 截断文档内容
    texts = [doc.page_content[:_MAX_DOC_CHARS] for doc in documents]

    # ── 调用 qwen3-rerank API ──
    api_url = f"{settings.RERANK_API_BASE}/reranks"
    headers = {
        "Authorization": f"Bearer {settings.LLM_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": settings.RERANK_MODEL,
        "query": query,
        "documents": texts,
        "top_n": min(top_k, len(documents)),
    }

    try:
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(api_url, json=payload, headers=headers)
            resp.raise_for_status()
        data = resp.json()
    except httpx.HTTPStatusError as e:
        logger.error("Rerank API HTTP error: %s %s", e.response.status_code, e.response.text[:200])
        return documents[:top_k]
    except Exception as e:
        logger.error("Rerank API call failed: %s", e)
        return documents[:top_k]

    # ── 解析结果 ──
    results = data.get("results", [])
    if not results:
        logger.warning("Rerank API returned empty results, using original order")
        return documents[:top_k]

    result: list[Document] = []
    for item in results:
        idx = item.get("index", -1)
        score = item.get("relevance_score", 0.0)
        if 0 <= idx < len(documents):
            doc = documents[idx]
            doc.metadata["rerank_score"] = round(score, 4)
            doc.metadata["rerank_method"] = "qwen3-rerank"
            result.append(doc)

    # 如果 API 返回不足 top_k，补充未排序的文档
    ranked_indices = {item.get("index", -1) for item in results}
    if len(result) < top_k:
        for i, doc in enumerate(documents):
            if i not in ranked_indices and len(result) < top_k:
                doc.metadata["rerank_score"] = 0.0
                doc.metadata["rerank_method"] = "qwen3-rerank-fallback"
                result.append(doc)

    elapsed_ms = (time.perf_counter() - start) * 1000
    top_score = result[0].metadata.get("rerank_score", 0) if result else 0
    logger.info(
        "qwen3-rerank query=%s input=%d output=%d top=%.4f elapsed=%.1fms",
        query[:30], len(documents), len(result), top_score, elapsed_ms,
    )

    return result
