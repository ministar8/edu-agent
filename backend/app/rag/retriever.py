"""RAG 检索门面模块

统一检索入口：多路召回 → 同 section 去重 → 阈值过滤 → Reranker 重排 → 层级展开 → 连续补齐。
同时提供 get_llm() 供 LangChain Agent 使用（ChatOpenAI 实例）。

子模块职责划分：
  - recall.py:    查询归一化、同义词扩展、关键词提取、召回路由构建、元数据路由、集合路由
  - bm25.py:      BM25 全文检索
  - postprocess.py: RRF 合并、同 section 去重、层级上下文展开、连续补齐
  - context.py:   KG 关联知识补充、RAG 上下文拼接
"""

from __future__ import annotations

import logging
import time

from langchain_core.documents import Document

from app.config import settings
from app.rag.metrics import metrics
from app.rag.query_classifier import classify_query, QueryCategory
from app.rag.reranker import rerank

# 子模块导入
from app.rag.recall import (
    build_recall_queries,
    build_metadata_routes,
    resolve_collection_routes,
    normalize_query_text,
    extract_query_terms,
)
from app.rag.bm25 import bm25_search
from app.rag.postprocess import (
    merge_route_results,
    dedup_same_section,
    expand_hierarchical_context,
    contiguous_fill,
)
from app.rag.context import (
    kg_context_supplement as _kg_context_supplement,
    build_rag_context,
)

logger = logging.getLogger(__name__)

# 相似度阈值
SCORE_THRESHOLD = 0.012

# 查询缓存
_query_cache: dict[str, list[tuple[Document, float]]] = {}
_MAX_CACHE_SIZE = 200

# Reranker 扩展倍数
_RERANK_EXPAND_FACTOR = 3


def get_llm():
    """获取LLM实例（单例缓存）"""
    from langchain_openai import ChatOpenAI

    if not hasattr(get_llm, "_instance"):
        get_llm._instance = ChatOpenAI(
            api_key=settings.LLM_API_KEY,
            base_url=settings.LLM_API_BASE,
            model=settings.LLM_MODEL,
            temperature=0.3,
            streaming=True,
        )
    return get_llm._instance


# ── 诊断日志 ──────────────────────────────────────────

def _summarize_document(doc: Document) -> str:
    source = str(doc.metadata.get("source_file") or "unknown")
    heading = str(doc.metadata.get("heading_title") or doc.metadata.get("heading") or "")
    content_type = str(doc.metadata.get("content_type") or "unknown")
    routes = str(doc.metadata.get("recall_routes") or "")
    return f"source={source} heading={heading[:30]} type={content_type} routes={routes[:80]}"


def _log_route_diagnostics(
    query: str,
    route_specs: list[tuple[str, str, dict | None]],
    route_results: list[tuple[str, list[tuple[Document, float]]]],
) -> None:
    spec_map = {route_name: (route_query, route_filter) for route_name, route_query, route_filter in route_specs}
    for route_name, results in route_results:
        route_query, route_filter = spec_map.get(route_name, ("", None))
        if not results:
            logger.info(
                "Retrieval route query=%s route=%s hits=0 filter=%s route_query=%s",
                query[:50], route_name, route_filter, route_query[:60],
            )
            continue
        top_doc, top_score = results[0]
        logger.info(
            "Retrieval route query=%s route=%s hits=%d top_score=%.4f filter=%s route_query=%s top_doc=%s",
            query[:50], route_name, len(results), top_score,
            route_filter, route_query[:60], _summarize_document(top_doc),
        )


def _log_final_retrieval_summary(stage: str, query: str, docs: list[Document]) -> None:
    preview = [_summarize_document(doc) for doc in docs[:3]]
    logger.info(
        "Retrieval summary stage=%s query=%s count=%d preview=%s",
        stage, query[:50], len(docs), preview,
    )


# ── 底层检索 ──────────────────────────────────────────

def _raw_search(
    query: str,
    collection_name: str,
    k: int,
    filter: dict | None = None,
    route_name: str = "",
) -> list[tuple[Document, float]]:
    """底层检索（带缓存），根据路由类型选择向量检索或 BM25"""
    cache_key = f"{collection_name}:{route_name}:{query}:{filter}"
    if cache_key in _query_cache:
        logger.debug("Cache hit for query: %s", query)
        return _query_cache[cache_key]

    if route_name == "keyword_bm25":
        terms = query.split()
        results = bm25_search(terms, collection_name, k, filter=filter)
    else:
        from app.rag.vectorstore import get_vector_store_manager
        store = get_vector_store_manager().get_store(collection_name)
        search_kwargs = {"k": k}
        if filter:
            search_kwargs["filter"] = filter
        results = store.similarity_search_with_score(query, **search_kwargs)

    if len(_query_cache) > _MAX_CACHE_SIZE:
        _query_cache.clear()
    _query_cache[cache_key] = results

    return results


# ── 检索策略 ──────────────────────────────────────────

def _resolve_retrieval_policy(
    query: str,
    k: int,
    score_threshold: float,
    use_rerank: bool,
) -> tuple[float, int]:
    normalized = normalize_query_text(query)
    terms = extract_query_terms(normalized)
    cat = classify_query(query, terms)

    effective_threshold = score_threshold

    if use_rerank:
        expand_factor = _RERANK_EXPAND_FACTOR
        if cat.is_short:
            expand_factor = 5
        elif cat.is_code or cat.is_long:
            expand_factor = 4
        elif cat.is_answer or cat.is_exercise:
            expand_factor = 2
        elif cat.is_structured:
            expand_factor = 3
        coarse_k = max(k, min(k * expand_factor, 40))
    else:
        if cat.is_short:
            coarse_k = max(k + 4, k * 2)
        elif cat.is_code or cat.is_long:
            coarse_k = max(k + 3, k * 2)
        elif cat.is_answer or cat.is_exercise:
            coarse_k = max(k + 1, k)
        else:
            coarse_k = k
        coarse_k = min(coarse_k, 20)

    logger.info(
        "Retrieval policy query=%s threshold=%.2f coarse_k=%d rerank=%s cat=%s",
        normalized[:50], effective_threshold, coarse_k, use_rerank, cat,
    )
    return effective_threshold, coarse_k


def _multi_route_search(
    query: str,
    collection_name: str,
    k: int,
    filter: dict | None = None,
    cat: QueryCategory | None = None,
) -> list[tuple[Document, float]]:
    """同步多路召回"""
    collection_routes = resolve_collection_routes(query, collection_name, cat=cat)
    route_queries = build_recall_queries(query)
    route_specs: list[tuple[str, str, dict | None]] = [
        (route_name, route_query, filter)
        for route_name, route_query in route_queries
    ]
    route_specs.extend(build_metadata_routes(query, base_filter=filter, cat=cat))
    route_results = [
        (
            f"{target_collection}:{route_name}",
            _raw_search(route_query, target_collection, k, filter=route_filter, route_name=route_name),
        )
        for target_collection in collection_routes
        for route_name, route_query, route_filter in route_specs
    ]
    logger.info(
        "Multi-route retrieval query=%s collections=%s routes=%s",
        query[:50], collection_routes,
        [route_name for route_name, _, _ in route_specs],
    )
    _log_route_diagnostics(query, route_specs=[(f"{target_collection}:{route_name}", route_query, route_filter) for target_collection in collection_routes for route_name, route_query, route_filter in route_specs], route_results=route_results)
    return merge_route_results(route_results)


# ── 公开 API ──────────────────────────────────────────

def retrieve_documents(
    query: str,
    collection_name: str = "",
    k: int = 5,
    score_threshold: float = SCORE_THRESHOLD,
    use_rerank: bool = True,
    filter: dict | None = None,
) -> list[Document]:
    """检索相关文档，过滤低相关度结果，可选 Reranker 重排序"""
    start = time.perf_counter()
    raw_results_count = 0
    post_dedup_count = 0
    post_threshold_count = 0
    post_rerank_count = 0
    post_expand_count = 0
    post_contiguous_count = 0
    effective_threshold = score_threshold
    coarse_k = k
    try:
        effective_threshold, coarse_k = _resolve_retrieval_policy(query, k, score_threshold, use_rerank)

        # 计算一次分类结果，传递给下游避免重复调用
        _normalized = normalize_query_text(query)
        _terms = extract_query_terms(_normalized)
        _cat = classify_query(query, _terms)

        results = _multi_route_search(query, collection_name, coarse_k, filter=filter, cat=_cat)
        raw_results_count = len(results)
        results = dedup_same_section(results, max_per_section=2)
        post_dedup_count = len(results)

        filtered = [doc for doc, score in results if score >= effective_threshold]
        post_threshold_count = len(filtered)
        logger.info(
            "Retrieval filtering query=%s threshold=%.2f before=%d after=%d",
            query[:50], effective_threshold, len(results), len(filtered),
        )
        _log_final_retrieval_summary("post-threshold", query, filtered)

        if use_rerank and filtered:
            filtered = rerank(query, filtered, top_k=k)
            _log_final_retrieval_summary("post-rerank", query, filtered)
        elif not use_rerank:
            filtered = filtered[:k]
            _log_final_retrieval_summary("final-no-rerank", query, filtered)
        post_rerank_count = len(filtered)

        before_expand = len(filtered)
        if filtered and collection_name:
            filtered = expand_hierarchical_context(filtered, collection_name)
            _log_final_retrieval_summary("post-expand", query, filtered)
        post_expand_count = len(filtered)

        before_contiguous = len(filtered)
        if filtered and collection_name:
            filtered = contiguous_fill(filtered, collection_name, max_gap_fill=5)
            _log_final_retrieval_summary("post-contiguous", query, filtered)
        post_contiguous_count = len(filtered)

        expanded_count = sum(1 for doc in filtered if doc.metadata.get("_expanded_from"))
        filled_gap_count = sum(1 for doc in filtered if doc.metadata.get("_filled_gap"))
        context_chars = sum(len(doc.page_content or "") for doc in filtered)
        role_counts = {
            "qa": sum(1 for doc in filtered if doc.metadata.get("section.chunk_role") == "qa"),
            "summary": sum(1 for doc in filtered if doc.metadata.get("section.chunk_role") == "summary"),
            "detail": sum(1 for doc in filtered if doc.metadata.get("section.chunk_role") == "detail"),
        }
        rerank_scores = [float(doc.metadata.get("rerank_score") or 0.0) for doc in filtered if doc.metadata.get("rerank_score") is not None]
        top_rerank_score = rerank_scores[0] if rerank_scores else 0.0
        avg_rerank_score = round(sum(rerank_scores) / len(rerank_scores), 6) if rerank_scores else 0.0
        metrics.emit_retrieve_summary(
            query=query,
            collection=collection_name,
            duration_ms=round((time.perf_counter() - start) * 1000, 3),
            values={
                "k": k,
                "coarse_k": coarse_k,
                "threshold": effective_threshold,
                "before_threshold": raw_results_count,
                "after_section_dedup": post_dedup_count,
                "after_threshold": post_threshold_count,
                "after_rerank": post_rerank_count,
                "after_expand": post_expand_count,
                "after_contiguous": post_contiguous_count,
                "expand_count": max(post_expand_count - before_expand, expanded_count),
                "filled_gap_count": max(post_contiguous_count - before_contiguous, filled_gap_count),
                "hit": bool(filtered),
                "context_chars": context_chars,
                "top_rerank_score": top_rerank_score,
                "avg_rerank_score": avg_rerank_score,
                "qa_hits": role_counts["qa"],
                "summary_hits": role_counts["summary"],
                "detail_hits": role_counts["detail"],
            },
        )
        return filtered
    except Exception as e:
        metrics.emit_retrieve_summary(
            query=query,
            collection=collection_name,
            status="error",
            duration_ms=round((time.perf_counter() - start) * 1000, 3),
            values={
                "k": k,
                "coarse_k": coarse_k,
                "threshold": effective_threshold,
                "before_threshold": raw_results_count,
                "after_section_dedup": post_dedup_count,
                "after_threshold": post_threshold_count,
                "after_rerank": post_rerank_count,
                "after_expand": post_expand_count,
                "after_contiguous": post_contiguous_count,
                "error_type": e.__class__.__name__,
            },
        )
        raise
