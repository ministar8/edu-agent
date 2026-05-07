"""BM25 全文检索模块

基于 ChromaDB where_document $contains + 词频评分的 BM25 风格全文检索。
"""

from __future__ import annotations

import logging
import math

from langchain_core.documents import Document

logger = logging.getLogger(__name__)


def bm25_search(
    query_terms: list[str],
    collection_name: str,
    k: int,
    filter: dict | None = None,
) -> list[tuple[Document, float]]:
    """BM25 风格全文检索

    策略：
    1. 用 ChromaDB where_document $contains 逐词匹配文档
    2. 根据 TF（词频）+ 文档长度归一化计算 BM25 风格分数
    3. 多个关键词取 OR 匹配，分数叠加
    """
    if not query_terms:
        return []

    try:
        from app.rag.vectorstore import get_vector_store_manager
        collection = get_vector_store_manager().client.get_collection(collection_name)
    except Exception:
        return []

    scored_docs: dict[str, tuple[Document, float]] = {}
    total_docs = collection.count()
    if total_docs == 0:
        return []

    # 估算平均文档长度
    sample_size = min(total_docs, 200)
    sample_result = collection.get(limit=sample_size, include=["documents"])
    sample_docs = sample_result.get("documents") or []
    avgdl = sum(len(d) for d in sample_docs) / len(sample_docs) if sample_docs else 100.0

    # BM25 参数
    b = 0.75
    k1 = 1.5

    for term in query_terms:
        try:
            query_kwargs: dict = {
                "where_document": {"$contains": term},
                "limit": k * 3,
                "include": ["documents", "metadatas"],
            }
            if filter:
                query_kwargs["where"] = filter
            result = collection.get(**query_kwargs)
        except Exception:
            logger.debug("BM25 $contains failed for term '%s'", term, exc_info=True)
            continue

        ids = result.get("ids") or []
        documents = result.get("documents") or []
        metadatas = result.get("metadatas") or []

        df = len(ids)
        idf = math.log((total_docs - df + 0.5) / (df + 0.5) + 1) if df > 0 else 0.0

        for i, doc_id in enumerate(ids):
            doc_text = documents[i] or ""
            doc_meta = metadatas[i] or {}

            tf = doc_text.count(term)
            dl = len(doc_text)

            tf_norm = (tf * (k1 + 1)) / (tf + k1 * (1 - b + b * dl / avgdl))
            score = idf * tf_norm

            if doc_id in scored_docs:
                existing_doc, existing_score = scored_docs[doc_id]
                scored_docs[doc_id] = (existing_doc, existing_score + score)
            else:
                doc = Document(page_content=doc_text, metadata=doc_meta)
                scored_docs[doc_id] = (doc, score)

    results = sorted(scored_docs.values(), key=lambda x: x[1], reverse=True)[:k]

    # 归一化到 [0, 1]
    if results:
        max_score = results[0][1]
        if max_score > 0:
            results = [(doc, score / max_score) for doc, score in results]

    if results:
        logger.debug(
            "BM25 search terms=%s collection=%s hits=%d top_score=%.4f",
            query_terms, collection_name, len(results), results[0][1],
        )

    return results
