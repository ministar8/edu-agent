from __future__ import annotations

import time
from collections import Counter
from typing import Any

from langchain_core.documents import Document

from app.config import settings
from app.rag.hyde import generate_hyde_query, should_trigger_hyde
from app.rag.postprocess import (
    dedup_same_section,
    merge_route_results,
    sentence_window_expand,
    weighted_rrf_merge,
)
from app.rag.query_decomposer import decompose_sync
from app.rag.query_classifier import classify_query
from app.rag.retrieval_strategy import resolve_retrieval_strategy
from app.rag.recall import (
    build_metadata_routes,
    build_recall_queries,
    get_route_weight,
    resolve_collection_routes,
)
from app.rag.rag_utils import extract_query_terms, normalize_query_text
from app.rag.reranker import rerank
from app.rag.retriever import (
    SCORE_THRESHOLD,
    _COMPACT_SUBQUERY_ROUTES,
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
        "_collection": metadata.get("_collection") or "",
        "section.path": metadata.get("section.path") or metadata.get("heading_path") or "",
        "section.chunk_role": metadata.get("section.chunk_role") or "",
        "content_type": metadata.get("content_type") or "",
        "recall_routes": metadata.get("recall_routes") or "",
        "recall_score": metadata.get("recall_score") or 0.0,
        "rerank_score": metadata.get("rerank_score") or 0.0,
        "_window_expanded": metadata.get("_window_expanded") or "",
        "_parent_expanded": metadata.get("_parent_expanded") or "",
        "_hyde_fallback": metadata.get("_hyde_fallback") or "",
        "_hyde_query": metadata.get("_hyde_query") or "",
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


def _score_stats(docs: list[Document]) -> dict[str, float]:
    scores = []
    for doc in docs:
        metadata = dict(doc.metadata or {})
        value = metadata.get("rerank_score") or metadata.get("recall_score") or metadata.get("score") or 0.0
        scores.append(float(value or 0.0))
    if not scores:
        return {"top": 0.0, "avg": 0.0, "min": 0.0, "max": 0.0}
    return {
        "top": round(max(scores), 6),
        "avg": round(sum(scores) / len(scores), 6),
        "min": round(min(scores), 6),
        "max": round(max(scores), 6),
    }


def _window_size_for_depth(depth_name: str) -> int:
    if depth_name == "shallow":
        return 0
    if depth_name == "standard":
        return 1
    return 2


def _expand_by_collection(docs: list[Document], collection_name: str, window_size: int) -> list[Document]:
    if collection_name:
        return sentence_window_expand(docs, collection_name, window_size=window_size)

    grouped_docs: dict[str, list[Document]] = {}
    for doc in docs:
        doc_collection = str(doc.metadata.get("_collection") or "")
        if doc_collection:
            grouped_docs.setdefault(doc_collection, []).append(doc)

    if not grouped_docs:
        return docs

    expanded_docs: list[Document] = []
    for doc_collection, docs_in_collection in grouped_docs.items():
        expanded_docs.extend(sentence_window_expand(docs_in_collection, doc_collection, window_size=window_size))
    return expanded_docs


def _route_summary(routes: list[dict[str, Any]]) -> dict[str, Any]:
    by_route = Counter(str(route.get("route") or "") for route in routes)
    by_collection = Counter(str(route.get("collection") or "") for route in routes)
    hits_by_route: Counter[str] = Counter()
    hits_by_collection: Counter[str] = Counter()
    for route in routes:
        hits = int(route.get("hits") or 0)
        hits_by_route[str(route.get("route") or "")] += hits
        hits_by_collection[str(route.get("collection") or "")] += hits
    return {
        "total_routes": len(routes),
        "total_hits": sum(int(route.get("hits") or 0) for route in routes),
        "route_count": dict(by_route),
        "collection_count": dict(by_collection),
        "hits_by_route": dict(hits_by_route),
        "hits_by_collection": dict(hits_by_collection),
    }


def _execute_route_search(
    query: str,
    collection_name: str,
    coarse_k: int,
    use_rerank: bool,
    filter: dict | None,
    cat,
    terms: list[str],
    depth,
    branch: str,
    route_allowlist: set[str] | None = None,
) -> tuple[list[tuple[Document, float]], list[dict[str, Any]], list[str], list[str]]:
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
    if route_allowlist is not None:
        route_specs = [spec for spec in route_specs if spec[0] in route_allowlist]
        if not route_specs:
            route_specs = [("semantic", query, filter)]

    route_results: list[tuple[str, list[tuple[Document, float]]]] = []
    route_trace: list[dict[str, Any]] = []
    for target_collection in collection_routes:
        collection_count = _get_collection_count(target_collection)
        for route_name, route_query, route_filter in route_specs:
            route_k = _route_adaptive_k(coarse_k, collection_count, use_rerank, route_name)
            results = _raw_search(
                route_query,
                target_collection,
                route_k,
                filter=route_filter,
                route_name=route_name,
            )
            route_results.append((f"{target_collection}:{route_name}", results))
            top_doc = results[0][0] if results else None
            top_score = results[0][1] if results else 0.0
            route_trace.append({
                "branch": branch,
                "collection": target_collection,
                "route": route_name,
                "route_query": route_query,
                "filter": route_filter,
                "requested_k": route_k,
                "collection_count": collection_count,
                "weight": get_route_weight(route_name, cat),
                "hits": len(results),
                "top_score": float(top_score or 0.0),
                "top_source": _source_from_metadata(top_doc.metadata) if top_doc else "",
                "top_samples": [
                    {
                        "source": _source_from_metadata(doc.metadata),
                        "score": float(score or 0.0),
                    }
                    for doc, score in results[:3]
                ],
            })
    return merge_route_results(route_results, cat=cat), route_trace, collection_routes, [name for name, _, _ in route_specs]


def _kg_trace(query: str, category: str, skip_kg: bool) -> dict[str, Any]:
    trace = {
        "skipped": bool(skip_kg),
        "used": False,
        "category": "" if skip_kg else category,
        "nodes_count": 0,
        "edges_count": 0,
        "paths_count": 0,
        "sample_nodes": [],
        "sample_paths": [],
        "resolved_topics": [],
        "matched_candidates": [],
        "error": "",
    }
    if skip_kg:
        return trace
    try:
        from app.rag.evidence import kg_evidence_from_query
        kg_ev = kg_evidence_from_query(query, category=category)
        if kg_ev:
            trace.update({
                "used": True,
                "nodes_count": len(kg_ev.nodes),
                "edges_count": len(kg_ev.edges),
                "paths_count": len(kg_ev.paths),
                "sample_nodes": kg_ev.nodes[:8],
                "sample_paths": kg_ev.paths[:3],
                "resolved_topics": kg_ev.metadata.get("resolved_topics", []),
                "matched_candidates": kg_ev.metadata.get("matched_candidates", []),
            })
    except Exception as e:
        trace["error"] = e.__class__.__name__
    return trace


def _trace_kg_category(collection_name: str, docs: list[Document], collection_routes: list[str]) -> str:
    if collection_name:
        return collection_name
    route_set = {route for route in collection_routes if route}
    if len(route_set) > 1:
        return ""
    if route_set:
        return next(iter(route_set))
    counts = Counter(
        str((doc.metadata or {}).get("_collection") or "")
        for doc in docs
        if (doc.metadata or {}).get("_collection")
    )
    return counts.most_common(1)[0][0] if counts else ""


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
    strategy = resolve_retrieval_strategy(cat)
    depth = strategy.depth
    if k == 5 and depth.k != 5:
        k = depth.k
    if depth.skip_rerank:
        use_rerank = False
    effective_threshold, coarse_k = _resolve_retrieval_policy(query, k, score_threshold, use_rerank, cat=cat)

    if depth.skip_decompose:
        sub_queries = [query]
        decomposed = False
    else:
        sub_queries = decompose_sync(query, cat=cat)
        decomposed = len(sub_queries) > 1

    route_trace: list[dict[str, Any]] = []
    branch_trace: list[dict[str, Any]] = []
    route_names: list[str] = []
    collection_routes: list[str] = []

    if decomposed:
        all_route_results: list[tuple[str, list[tuple[Document, float]]]] = []
        original_results, original_routes, collection_routes, route_names = _execute_route_search(
            query, collection_name, coarse_k, use_rerank, filter, cat, terms, depth, "original"
        )
        original_deduped = dedup_same_section(original_results, max_per_section=2)
        original_filtered = [(doc, score) for doc, score in original_deduped if score >= effective_threshold]
        all_route_results.append(("original", original_filtered))
        route_trace.extend(original_routes)
        branch_trace.append({
            "branch": "original",
            "query": query,
            "raw": len(original_results),
            "after_dedup": len(original_deduped),
            "after_threshold": len(original_filtered),
        })
        for sub_query in [sq for sq in sub_queries if sq != query]:
            sub_terms = extract_query_terms(normalize_query_text(sub_query))
            route_allowlist = _COMPACT_SUBQUERY_ROUTES if cat.is_comparison else None
            sub_results, sub_routes, _, sub_route_names = _execute_route_search(
                sub_query, collection_name, coarse_k, use_rerank, filter, None,
                sub_terms, depth, "sub", route_allowlist=route_allowlist
            )
            sub_deduped = dedup_same_section(sub_results, max_per_section=2)
            sub_filtered = [(doc, score) for doc, score in sub_deduped if score >= effective_threshold]
            all_route_results.append(("sub", sub_filtered))
            route_trace.extend(sub_routes)
            route_names.extend(name for name in sub_route_names if name not in route_names)
            branch_trace.append({
                "branch": "sub",
                "query": sub_query,
                "raw": len(sub_results),
                "after_dedup": len(sub_deduped),
                "after_threshold": len(sub_filtered),
            })
        merged = weighted_rrf_merge(all_route_results, weights={"original": 1.5, "sub": 1.0}, cat=cat)
    else:
        merged, route_trace, collection_routes, route_names = _execute_route_search(
            query, collection_name, coarse_k, use_rerank, filter, cat, terms, depth, "original"
        )

    max_per_section = 4 if (cat.is_exercise or cat.is_answer) else (3 if (cat.is_comparison or cat.is_long) else 2)
    deduped = dedup_same_section(merged, max_per_section=max_per_section)
    threshold_pairs = [(doc, score) for doc, score in deduped if score >= effective_threshold]
    filtered = [doc for doc, _score in threshold_pairs]

    rerank_trace = {
        "enabled": bool(use_rerank),
        "top_k": k * 2 if decomposed else k,
        "top_score": 0.0,
        "min_score": 0.0,
        "kept": 0,
        "fallback": False,
    }
    if use_rerank and filtered:
        raw_reranked = rerank(query, filtered, top_k=k * 2 if decomposed else k, lightweight=depth.lightweight_rerank)
        top_score = raw_reranked[0].metadata.get("rerank_score", 0) if raw_reranked else 0
        # 双重阈值过滤（相对 + 绝对），兜底保留 top-2
        from app.rag.retriever import _apply_rerank_threshold
        reranked = _apply_rerank_threshold(raw_reranked, min_keep=2)
        rerank_trace["fallback"] = len(reranked) < len(raw_reranked)
        _rel_min = top_score * settings.RERANK_MIN_SCORE if top_score > 0 else 0
        _abs_min = settings.RERANK_ABSOLUTE_MIN_SCORE
        rerank_trace.update({
            "top_score": float(top_score or 0.0),
            "min_score": float(max(_rel_min, _abs_min)),
            "kept": len(reranked),
        })
    else:
        reranked = filtered[:k * 2] if decomposed and not use_rerank else filtered[:k]
        rerank_trace["kept"] = len(reranked)

    top_rerank_score_for_hyde = 0.0
    rerank_scores_for_hyde = [
        float(doc.metadata.get("rerank_score") or 0.0)
        for doc in reranked
        if doc.metadata.get("rerank_score") is not None
    ]
    if rerank_scores_for_hyde:
        top_rerank_score_for_hyde = max(rerank_scores_for_hyde)

    hyde_trace = {
        "skipped": bool(depth.skip_hyde),
        "triggered": False,
        "generated_query": "",
        "added_count": 0,
        "top_rerank_score": float(top_rerank_score_for_hyde or 0.0),
        "error": "",
    }
    before_hyde = list(reranked)
    if not depth.skip_hyde and should_trigger_hyde(query, len(reranked), top_rerank_score_for_hyde, cat):
        hyde_query = generate_hyde_query(query)
        hyde_trace["generated_query"] = hyde_query[:160] if hyde_query else ""
        if hyde_query and hyde_query != query:
            hyde_trace["triggered"] = True
            try:
                hyde_terms = extract_query_terms(normalize_query_text(hyde_query))
                hyde_results, hyde_routes, _, _ = _execute_route_search(
                    hyde_query, collection_name, coarse_k, use_rerank, filter, cat, hyde_terms, depth, "hyde"
                )
                route_trace.extend(hyde_routes)
                hyde_results = dedup_same_section(hyde_results, max_per_section=2)
                hyde_docs = [doc for doc, score in hyde_results if score >= effective_threshold * 0.8]
                if use_rerank and hyde_docs:
                    hyde_docs = rerank(query, hyde_docs, top_k=k, lightweight=depth.lightweight_rerank)
                for doc in hyde_docs:
                    doc.metadata["_hyde_fallback"] = True
                    doc.metadata["_hyde_query"] = hyde_query[:120]
                existing_keys = {
                    str(doc.metadata.get("content_hash") or f"{doc.metadata.get('source', '') or doc.metadata.get('source_file', '')}:{doc.page_content[:80]}")
                    for doc in reranked
                }
                merged_hyde_docs = []
                for doc in hyde_docs:
                    key = str(doc.metadata.get("content_hash") or f"{doc.metadata.get('source', '') or doc.metadata.get('source_file', '')}:{doc.page_content[:80]}")
                    if key not in existing_keys:
                        merged_hyde_docs.append(doc)
                        existing_keys.add(key)
                if merged_hyde_docs:
                    reranked = (reranked + merged_hyde_docs)[:max(k, len(reranked))]
                    hyde_trace["added_count"] = len(merged_hyde_docs)
            except Exception as e:
                hyde_trace["error"] = e.__class__.__name__

    window_size = _window_size_for_depth(depth.depth)
    expanded = _expand_by_collection(reranked, collection_name, window_size) if reranked else []
    for doc in expanded:
        doc.metadata["_retrieval_depth"] = depth.depth
        doc.metadata["_effective_k"] = k
        doc.metadata["_coarse_k"] = coarse_k
    final_docs = expanded
    window_expanded_count = sum(1 for doc in final_docs if doc.metadata.get("_window_expanded"))
    kg_category = _trace_kg_category(collection_name, final_docs, collection_routes)
    kg = _kg_trace(query, kg_category, depth.skip_kg or not final_docs)

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
            "retrieval_layer": strategy.layer,
            "route_type": strategy.route_type,
            "skip_bm25": depth.skip_bm25,
            "skip_metadata_routes": depth.skip_metadata_routes,
            "skip_decompose": depth.skip_decompose,
            "skip_hyde": depth.skip_hyde,
            "skip_kg": depth.skip_kg,
        },
        "routes": route_trace,
        "route_summary": _route_summary(route_trace),
        "decomposition": {
            "enabled": not depth.skip_decompose,
            "decomposed": decomposed,
            "sub_queries": sub_queries,
            "branches": branch_trace,
        },
        "rerank": rerank_trace,
        "hyde": hyde_trace,
        "kg": kg,
        "window": {
            "window_size": window_size,
            "expanded_count": window_expanded_count,
            "added_count": len(final_docs) - len(reranked),
        },
        "counts": {
            "raw": len(merged),
            "after_dedup": len(deduped),
            "after_threshold": len(filtered),
            "after_rerank": len(before_hyde),
            "after_hyde": len(reranked),
            "after_window": len(expanded),
            "final": len(final_docs),
        },
        "score_stats": {
            "after_threshold": _score_stats(filtered),
            "after_rerank": _score_stats(before_hyde),
            "after_hyde": _score_stats(reranked),
            "final": _score_stats(final_docs),
        },
        "samples": {
            "after_merge": [document_to_trace_item(doc, score) for doc, score in merged[:5]],
            "after_dedup": [document_to_trace_item(doc, score) for doc, score in deduped[:5]],
            "after_threshold": [document_to_trace_item(doc, score) for doc, score in threshold_pairs[:5]],
            "after_rerank": [document_to_trace_item(doc) for doc in before_hyde[:5]],
            "after_hyde": [document_to_trace_item(doc) for doc in reranked[:5]],
            "final": [document_to_trace_item(doc) for doc in final_docs[:5]],
        },
        "route_names": sorted(set(route_names)),
        "duration_ms": round((time.perf_counter() - start) * 1000, 3),
    }
    return final_docs, trace
