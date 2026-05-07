"""Reranker 重排序模块

使用 Rerank 模型对向量检索结果进行精排，提升检索命中率。
向量检索是双编码器（粗排），Reranker 是交叉编码器（精排）。

支持远程 API（DashScope gte-rerank）和本地模式：
- 远程：调用 DashScope rerank API
- 本地（Ollama 等）：自动检测并跳过 rerank，返回原始顺序
"""

from __future__ import annotations

import logging
from urllib.parse import urlparse

from langchain_core.documents import Document

from app.config import settings

logger = logging.getLogger(__name__)

# Reranker API 参数（DashScope 专用）
_RERANK_MODEL = "gte-rerank-v2"
_RERANK_API_PATH = "/api/v1/services/rerank/text-rerank/text-rerank"


def _is_local_embedding() -> bool:
    """检测 Embedding 服务是否为本地部署（Ollama 等，不支持 rerank）"""
    base = settings.EMBEDDING_API_BASE.lower()
    return "localhost" in base or "127.0.0.1" in base or "0.0.0.0" in base


def _get_rerank_url() -> str:
    parsed = urlparse(settings.EMBEDDING_API_BASE)
    base = f"{parsed.scheme}://{parsed.netloc}" if parsed.scheme and parsed.netloc else "https://dashscope.aliyuncs.com"
    return f"{base}{_RERANK_API_PATH}"


def rerank(
    query: str,
    documents: list[Document],
    top_k: int = 5,
) -> list[Document]:
    """对检索结果进行重排序（同步）

    本地模式（Ollama）自动跳过 rerank，返回原始顺序。

    Args:
        query: 用户查询
        documents: 向量检索返回的文档列表
        top_k: 返回前 top_k 个结果

    Returns:
        按相关性重排序后的文档列表
    """
    if not documents:
        return []

    if _is_local_embedding():
        logger.debug("Local embedding detected, skipping rerank")
        return documents[:top_k]

    if len(documents) <= top_k:
        top_k = len(documents)

    import httpx

    texts = [doc.page_content for doc in documents]

    try:
        resp = httpx.post(
            _get_rerank_url(),
            headers={"Authorization": f"Bearer {settings.EMBEDDING_API_KEY}"},
            json={
                "model": _RERANK_MODEL,
                "input": {
                    "query": query,
                    "documents": texts,
                },
                "parameters": {
                    "top_n": top_k,
                    "return_documents": False,
                },
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()

        # results 按 relevance_score 降序排列
        results = data.get("output", {}).get("results", [])
        reranked_docs: list[Document] = []
        for item in results:
            idx = item.get("index", -1)
            score = item.get("relevance_score", 0.0)
            if 0 <= idx < len(documents):
                doc = documents[idx]
                doc.metadata["rerank_score"] = float(score)
                reranked_docs.append(doc)

        logger.info(
            "Rerank completed query=%s input=%d output=%d top_score=%.4f",
            query[:30], len(documents), len(reranked_docs),
            reranked_docs[0].metadata.get("rerank_score", 0) if reranked_docs else 0,
        )
        return reranked_docs

    except Exception as e:
        logger.warning("Rerank failed, fallback to original order: %s", e)
        # 降级：返回原始顺序的前 top_k 个
        return documents[:top_k]
