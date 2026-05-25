from __future__ import annotations

import time
from typing import Any

from langchain_core.documents import Document

from app.rag.postprocess import (
    dedup_same_section,
    merge_route_results,
    sentence_window_expand,
)
from app.rag.query_classifier import classify_query, resolve_retrieval_depth
from app.rag.recall import (
    build_metadata_routes,
    build_recall_queries,
    resolve_collection_routes,
)
from app.rag.rag_utils import extract_query_terms, normalize_query_text
from app.rag.reranker import rerank
from app.rag.retriever import (
    SCORE_THRESHOLD,
    _get_collection_count,
    _raw_search,
    _resolve_retrieval_policy,
    _route_adaptive_k,
)


def _source_from_metadata(metadata: dict[str, Any]) -> str:
    return str(metadata.get("source_file") or metadata.get("source") or metadata.get("source_name") or "??")


def _safe_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_file": _source_from_metadata(metadata),
        "section.path": metadata.get("section.path") or metadata.get("heading_path") or "",
        "section.chunk_role": metadata.get("section.chunk_role") or "",
        "recall_routes": metadata.get("recall_routes") or "",
        "_window_expanded": metadata.get("_window_expanded") or "",
        "_parent_expanded": metadata.get("_parent_expanded") or "",
        "_retrieval_depth": metadata.get("_retrieval_depth") or "",
    }


def document_to_trace_item(doc: Document, score: float | None = None) -> dict[str, Any]:
    metadata = dict(doc.metadata or {})
    value = score
    if value is None:
        value = metadata.get("rerank_score") or metadata.get("recall_score") or metadata.get("score") or 0.0
    return {
        "content": (doc.page_content or "")[:500],
        "score": float(value or 0.0),
        "metadata": _safe_metadata(metadata),
    }


def _expand_by_collection(docs: list[Document], collection_name: str) -> list[Document]:
    if collection_name:
        return sentence_window_expand(docs, collection_name)

    grouped_docs: dict[str, list[Document]] = {}
    for doc in docs:
        doc_collection = str(doc.metadata.get("_collection") or "")
        if doc_collection:
            grouped_docs.setdefault(doc_collection, []).append(doc)

    if not grouped_docs:
        return docs

    expanded_docs: list[Document] = []
    for doc_collection, docs_in_collection in grouped_docs.items():
        expanded_docs.extend(sentence_window_expand(docs_in_collection, doc_collection))
    return expanded_docs


def retrieve_documents_with_trace(
    query: str,
    collection_name: str = "",
    k: int = 5,
    score_threshold: float = SCORE_THRESHOLD,
    use_rerank: bool = True,
    filter: dict | None = None,
) -> tuple[list[Document], dict[str, Any]]:
    start = time.perf_counter()
    normalized = normalize_query_text(query)
    terms = extract_query_terms(normalized)
    cat = classify_query(query, terms)
    depth = resolve_retrieval_depth(cat)
    if k == 5 and depth.k != 5:
        k = depth.k
    if depth.skip_rerank:
        use_rerank = False
    effective_threshold, coarse_k = _resolve_retrieval_policy(query, k, score_threshold, use_rerank, cat=cat)

    collection_routes = resolve_collection_routes(query, collection_name, cat=cat)
    route_queries = build_recall_queries(query, cat=cat)
    if depth.skip_bm25:
        route_queries = [(name, route_query) for name, route_query in route_queries if name != "keyword_bm25"]

    route_specs: list[tuple[str, str, dict | None]] = [
        (route_name, route_query, filter)
        for route_name, route_query in route_queries
    ]
    if not depth.skip_metadata_routes:
        meta_routes = build_metadata_routes(query, base_filter=filter, cat=cat, terms=terms)
        if depth.max_metadata_routes < len(meta_routes):
            meta_routes = meta_routes[:depth.max_metadata_routes]
        route_specs.extend(meta_routes)

    expanded_specs = [
        (target_collection, route_name, route_query, route_filter)
        for target_collection in collection_routes
        for route_name, route_query, route_filter in route_specs
    ]
    route_results = [
        (
            f"{target_collection}:{route_name}",
            _raw_search(
                route_query,
                target_collection,
                _route_adaptive_k(
                    coarse_k,
                    _get_collection_count(target_collection),
                    use_rerank,
                    route_name,
                ),
                filter=route_filter,
                route_name=route_name,
            ),
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
            "top_source": _source_from_metadata(top_doc.metadata) if top_doc else "",
        })

    merged = merge_route_results(route_results, cat=cat)
    max_per_section = 4 if (cat.is_exercise or cat.is_answer) else (3 if (cat.is_comparison or cat.is_long) else 2)
    deduped = dedup_same_section(merged, max_per_section=max_per_section)
    filtered = [doc for doc, score in deduped if score >= effective_threshold]
    reranked = rerank(query, filtered, top_k=k) if use_rerank and filtered else filtered[:k]
    expanded = _expand_by_collection(reranked, collection_name) if reranked else []
    for doc in expanded:
        doc.metadata["_retrieval_depth"] = depth.depth
        doc.metadata["_effective_k"] = k
        doc.metadata["_coarse_k"] = coarse_k
    final_docs = expanded

    trace = {
        "query": query,
        "collection": collection_name,
        "collections": collection_routes,
        "policy": {
            "threshold": effective_threshold,
            "coarse_k": coarse_k,
            "effective_k": k,
            "use_rerank": use_rerank,
            "category": cat.to_dict(),
            "retrieval_depth": depth.depth,
        },
        "routes": route_trace,
        "counts": {
            "raw": len(merged),
            "after_dedup": len(deduped),
            "after_threshold": len(filtered),
            "after_rerank": len(reranked),
            "after_window": len(expanded),
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
