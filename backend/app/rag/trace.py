from __future__ import annotations

import time
from typing import Any

from langchain_core.documents import Document

from app.rag.postprocess import contiguous_fill, dedup_same_section, expand_hierarchical_context, merge_route_results
from app.rag.query_classifier import classify_query
from app.rag.recall import (
    build_metadata_routes,
    build_recall_queries,
    extract_query_terms,
    normalize_query_text,
    resolve_collection_routes,
)
from app.rag.reranker import rerank
from app.rag.retriever import SCORE_THRESHOLD, _raw_search, _resolve_retrieval_policy


def _safe_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_file": metadata.get("source_file", "未知"),
        "section.path": metadata.get("section.path") or metadata.get("heading_path") or "",
        "section.chunk_role": metadata.get("section.chunk_role") or "",
        "recall_routes": metadata.get("recall_routes") or "",
        "_expanded_from": metadata.get("_expanded_from") or "",
        "_filled_gap": metadata.get("_filled_gap") or "",
    }


def document_to_trace_item(doc: Document, score: float | None = None) -> dict[str, Any]:
    metadata = dict(doc.metadata or {})
    value = score
    if value is None:
        value = metadata.get("rerank_score") or metadata.get("score") or 0.0
    return {
        "content": (doc.page_content or "")[:500],
        "score": float(value or 0.0),
        "metadata": _safe_metadata(metadata),
    }


def retrieve_documents_with_trace(
    query: str,
    collection_name: str = "",
    k: int = 5,
    score_threshold: float = SCORE_THRESHOLD,
    use_rerank: bool = True,
    filter: dict | None = None,
) -> tuple[list[Document], dict[str, Any]]:
    start = time.perf_counter()
    effective_threshold, coarse_k = _resolve_retrieval_policy(query, k, score_threshold, use_rerank)
    normalized = normalize_query_text(query)
    terms = extract_query_terms(normalized)
    cat = classify_query(query, terms)
    collection_routes = resolve_collection_routes(query, collection_name, cat=cat)
    route_specs: list[tuple[str, str, dict | None]] = [
        (route_name, route_query, filter)
        for route_name, route_query in build_recall_queries(query)
    ]
    route_specs.extend(build_metadata_routes(query, base_filter=filter, cat=cat))

    expanded_specs = [
        (target_collection, route_name, route_query, route_filter)
        for target_collection in collection_routes
        for route_name, route_query, route_filter in route_specs
    ]
    route_results = [
        (
            f"{target_collection}:{route_name}",
            _raw_search(route_query, target_collection, coarse_k, filter=route_filter, route_name=route_name),
        )
        for target_collection, route_name, route_query, route_filter in expanded_specs
    ]

    route_lookup = {
        f"{target_collection}:{route_name}": (target_collection, route_name, route_query, route_filter)
        for target_collection, route_name, route_query, route_filter in expanded_specs
    }
    route_trace = []
    for tag, results in route_results:
        target_collection, route_name, route_query, route_filter = route_lookup[tag]
        top_doc = results[0][0] if results else None
        top_score = results[0][1] if results else 0.0
        route_trace.append({
            "collection": target_collection,
            "route": route_name,
            "route_query": route_query,
            "filter": route_filter,
            "hits": len(results),
            "top_score": float(top_score or 0.0),
            "top_source": top_doc.metadata.get("source_file", "未知") if top_doc else "",
        })

    merged = merge_route_results(route_results)
    deduped = dedup_same_section(merged, max_per_section=2)
    filtered = [doc for doc, score in deduped if score >= effective_threshold]
    reranked = rerank(query, filtered, top_k=k) if use_rerank and filtered else filtered[:k]
    expanded = expand_hierarchical_context(reranked, collection_name) if reranked else []
    final_docs = contiguous_fill(expanded, collection_name, max_gap_fill=5) if expanded else []

    trace = {
        "query": query,
        "collection": collection_name,
        "collections": collection_routes,
        "policy": {
            "threshold": effective_threshold,
            "coarse_k": coarse_k,
            "use_rerank": use_rerank,
            "category": cat.to_dict(),
        },
        "routes": route_trace,
        "counts": {
            "raw": len(merged),
            "after_dedup": len(deduped),
            "after_threshold": len(filtered),
            "after_rerank": len(reranked),
            "after_expand": len(expanded),
            "final": len(final_docs),
        },
        "samples": {
            "after_threshold": [document_to_trace_item(doc) for doc in filtered[:5]],
            "after_rerank": [document_to_trace_item(doc) for doc in reranked[:5]],
            "final": [document_to_trace_item(doc) for doc in final_docs[:5]],
        },
        "duration_ms": round((time.perf_counter() - start) * 1000, 3),
    }
    return final_docs, trace
