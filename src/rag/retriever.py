"""RAG 检索门面模块

统一检索入口：多路召回 → 同 section 去重 → 阈值过滤 → Reranker 重排 → Sentence Window 展开。

**对外入口**（agent 经 `agents/tools.py` 调用）：
  - aretrieve_evidence_with_retry(): 带重试的异步检索，返回 FusedEvidence

内部分层：
  - aretrieve_evidence():  异步检索主实现（语义缓存 → 召回 → 融合 → 证据校验）
  - aretrieve_documents(): 异步底层检索
  - retrieve_documents():  同步底层检索，**仅供 ingest 后的缓存预热**（见 warmup_query_cache）

LLM 工厂在 `core.llm`；RAG 层统一的带超时调用入口见 `rag/llm_calls.py`。

子模块职责划分：
  - recall.py:     查询归一化、同义词扩展、关键词提取、召回路由构建、元数据路由
  - bm25.py:       BM25 全文检索
  - postprocess.py: RRF 合并、同 section 去重、层级上下文展开、连续补齐
  - fusion.py:     证据融合与预算裁剪
  - llm_calls.py:  带超时与统一失败语义的 LLM 调用
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

from langchain_core.documents import Document

from core.cache import BoundedCache
from core.settings import settings
from rag.bm25 import bm25_search
from rag.evidence import FusedEvidence
from rag.hyde import generate_hyde_query, should_trigger_hyde
from rag.metrics import metrics
from rag.postprocess import (
    dedup_same_section,
    downgrade_window_noise,
    merge_route_results,
    sentence_window_expand,
    weighted_rrf_merge,
)
from rag.query_classifier import (
    QueryCategory,
    RetrievalDepth,
    aclassify_query,
    classify_query,
)
from rag.query_decomposer import decompose
from rag.rag_utils import extract_query_terms, normalize_query_text
from rag.recall import (
    build_metadata_routes,
    build_recall_queries,
    resolve_collection_routes,
)
from rag.reranker import rerank
from rag.retrieval_strategy import L2_STANDARD, resolve_retrieval_strategy, strategy_from_depth
from rag.verifier import VerificationResult


def _apply_rerank_threshold(
    reranked: list[Document],
    *,
    min_keep: int = 2,
) -> list[Document]:
    """对 Rerank 结果应用双重阈值过滤（相对 + 绝对），兜底保留 top-N。

    策略：
    1. 相对阈值：保留 rerank_score >= top_score * RERANK_MIN_SCORE
    2. 绝对阈值：丢弃 rerank_score < RERANK_ABSOLUTE_MIN_SCORE
    3. 兜底：过滤后不足 min_keep 个时，强制保留 rerank 排序最靠前的 min_keep 个
    """
    if not reranked:
        return reranked

    top_score = reranked[0].metadata.get("rerank_score", 0) or 0

    # 相对阈值
    rel_min = top_score * settings.RERANK_MIN_SCORE if top_score > 0 else 0
    # 绝对阈值
    abs_min = settings.RERANK_ABSOLUTE_MIN_SCORE

    # 取两者中更高的作为最终阈值
    final_min = max(rel_min, abs_min)

    high_confidence = [d for d in reranked if (d.metadata.get("rerank_score", 0) or 0) >= final_min]

    if len(high_confidence) >= min_keep:
        return high_confidence

    # 兜底：保留 top-min_keep
    fallback = reranked[:min_keep]
    logger.info(
        "Rerank threshold fallback: only %d/%d >= %.3f (rel=%.3f, abs=%.3f), keeping top-%d",
        len(high_confidence),
        len(reranked),
        final_min,
        rel_min,
        abs_min,
        min_keep,
    )
    return fallback


logger = logging.getLogger(__name__)

# RRF 融合分数阈值（基于采样校准，非余弦距离）
# RRF(k=20): 排名1≈0.048, 排名5≈0.040（权重 1.0 时）
# 权重 1.5 的路由第 10 名 = 1.5/(20+10) = 0.05 → 刚好过旧阈值
# 0.06 ≈ "至少1路前7" 或 "2路前15"，过滤掉排名#8+的单路噪声
SCORE_THRESHOLD = 0.06

# 查询缓存（有界 + TTL，线程安全；命中计数由缓存自带）
_MAX_CACHE_SIZE = 200
_CACHE_TTL = 300  # 5 minutes TTL
_query_cache: BoundedCache[str, list[tuple[Document, float]]] = BoundedCache(
    max_size=_MAX_CACHE_SIZE, ttl=_CACHE_TTL, name="retriever_query"
)


def _copy_results(results: list[tuple[Document, float]]) -> list[tuple[Document, float]]:
    """缓存命中时返回浅拷贝：新 list + 每篇 Document 复制一份 metadata。

    下游会往 Document.metadata 写东西（`_collection`、窗口展开、噪声降级等），
    直接返回缓存里的原对象会让这些写入污染缓存。
    """
    return [
        (Document(page_content=d.page_content, metadata=dict(d.metadata)), s) for d, s in results
    ]


def _cache_stats_fields() -> dict[str, int | float]:
    """查询缓存的命中统计（并发下近似，仅用于观测）。"""
    stats = _query_cache.stats
    return {
        "cache_hits": stats["hits"],
        "cache_misses": stats["misses"],
        "cache_hit_rate": stats["hit_rate"],
    }


# Reranker 扩展倍数：知识库扩充后需要更大候选池
# k=5 时 coarse_k=25，k=8 时 coarse_k=40
_RERANK_EXPAND_FACTOR = 5


# ── 诊断日志 ──────────────────────────────────────────


def _summarize_document(doc: Document) -> str:
    source = str(doc.metadata.get("source_file") or doc.metadata.get("source") or "unknown")
    heading = str(doc.metadata.get("heading_title") or doc.metadata.get("heading") or "")
    content_type = str(doc.metadata.get("content_type") or "unknown")
    routes = str(doc.metadata.get("recall_routes") or "")
    return f"source={source} heading={heading[:30]} type={content_type} routes={routes[:80]}"


def _log_route_diagnostics(
    query: str,
    route_specs: list[tuple[str, str, dict | None]],
    route_results: list[tuple[str, list[tuple[Document, float]]]],
) -> None:
    spec_map = {
        route_name: (route_query, route_filter)
        for route_name, route_query, route_filter in route_specs
    }
    for route_name, results in route_results:
        route_query, route_filter = spec_map.get(route_name, ("", None))
        if not results:
            logger.info(
                "Retrieval route query=%s route=%s hits=0 filter=%s route_query=%s",
                query[:50],
                route_name,
                route_filter,
                route_query[:60],
            )
            continue
        top_doc, top_score = results[0]
        logger.info(
            "Retrieval route query=%s route=%s hits=%d top_score=%.4f filter=%s route_query=%s top_doc=%s",
            query[:50],
            route_name,
            len(results),
            top_score,
            route_filter,
            route_query[:60],
            _summarize_document(top_doc),
        )


def _log_final_retrieval_summary(stage: str, query: str, docs: list[Document]) -> None:
    preview = [_summarize_document(doc) for doc in docs[:3]]
    logger.info(
        "Retrieval summary stage=%s query=%s count=%d preview=%s",
        stage,
        query[:50],
        len(docs),
        preview,
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
    # 确定性 cache key：filter dict 排序后序列化，避免 {"a":1,"b":2} vs {"b":2,"a":1} 不一致
    filter_key = json.dumps(filter, sort_keys=True, ensure_ascii=False) if filter else ""
    cache_key = f"{collection_name}:{route_name}:{query}:{filter_key}:k={k}"
    cached_results = _query_cache.get(cache_key)
    if cached_results is not None:
        stats = _query_cache.stats
        logger.debug(
            "Cache hit for query: %s (hits=%s misses=%s rate=%s%%)",
            query,
            stats["hits"],
            stats["misses"],
            stats["hit_rate"],
        )
        return _copy_results(cached_results)

    if route_name == "keyword_bm25":
        import jieba

        from rag.recall import _BM25_STOP_WORDS

        # cut_for_search 同时保留全词和子词：
        # "进程同步机制" → "进程"、"同步"、"机制"、"进程同步"、"同步机制"
        _BM25_SINGLE_CHAR_ALLOW = {
            "栈",
            "堆",
            "树",
            "图",
            "串",
            "队",
            "链",
            "表",
            "网",
            "库",
            "锁",
            "页",
            "段",
            "核",
            "集",
        }
        terms = [
            w
            for w in jieba.cut_for_search(query)
            if w.strip()
            and w not in _BM25_STOP_WORDS
            and (len(w) >= 2 or w in _BM25_SINGLE_CHAR_ALLOW)
        ]
        # 限制最多 6 个 term，优先保留复合词（长词更精准）
        if len(terms) > 6:
            terms = sorted(terms, key=len, reverse=True)[:6]
        # 过滤后若为空（jieba 把短 query 分成停用词），回退用原始 query
        if not terms:
            terms = [query.strip()]
        results = bm25_search(terms, collection_name, k, filter=filter)
    else:
        from rag.vectorstore import get_vector_store_manager

        store = get_vector_store_manager().get_store(collection_name)
        search_kwargs = {"k": k}
        if filter:
            search_kwargs["filter"] = filter
        results = store.similarity_search_with_score(query, **search_kwargs)

    # 注入集合来源，供 RRF 合并区分跨集合的同名文档
    for doc, _score in results:
        doc.metadata["_collection"] = collection_name

    _query_cache.set(cache_key, results)
    return results


# ── 检索策略 ──────────────────────────────────────────


def _resolve_retrieval_policy(
    query: str,
    k: int,
    score_threshold: float,
    use_rerank: bool,
    cat: QueryCategory | None = None,
) -> tuple[float, int]:
    if cat is None:
        normalized = normalize_query_text(query)
        terms = extract_query_terms(normalized)
        cat = classify_query(query, terms)
    else:
        normalized = normalize_query_text(query)

    effective_threshold = score_threshold

    # 阈值校准：按最活跃路由权重缩放
    # 原理：w/(k+rank) < threshold 等价于 rank > w/threshold - k
    # 高权重路由(w=2.5)的 rank-20 噪声分数 = 2.5/40 = 0.0625 > 0.05，直接通过
    # 缩放后 threshold × (max_w / baseline_w) 让高权重路由的噪声也被过滤
    from rag.recall import get_route_weight

    _BASELINE_WEIGHT = 1.5  # semantic default 权重作为基准
    _active_routes = (
        "semantic",
        "keyword_bm25",
        "focus",
        "expanded",
        "code_meta",
        "exercise_meta",
        "answer_meta",
        "concept_meta",
        "comparison_meta",
        "structured_meta",
        "section_meta",
        "formula_meta",
        "table_meta",
        "merged_qa_meta",
    )
    _max_w = max(get_route_weight(r, cat) for r in _active_routes)
    effective_threshold *= _max_w / _BASELINE_WEIGHT

    # 阈值自适应：在权重校准基础上，按查询类型微调
    # 注意：权重校准已收紧高权重路由，此处只需小幅调整
    if cat.is_exercise or cat.is_answer:
        effective_threshold *= 1.2  # 习题/答案适度收紧
    elif cat.is_short:
        effective_threshold *= 0.75  # 短查询结果少，放宽阈值保召回
    elif cat.is_long or cat.is_comparison:
        effective_threshold *= 1.1  # 长查询/对比查询适度收紧

    if use_rerank:
        expand_factor = _RERANK_EXPAND_FACTOR
        if cat.is_short:
            expand_factor = 6  # 短查询检索命中少，需要更大候选池
        elif cat.is_code or cat.is_long:
            expand_factor = 6
        elif cat.is_answer or cat.is_exercise:
            expand_factor = 5  # 答案/习题适度扩大
        coarse_k = max(k, min(k * expand_factor, 50))
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
        normalized[:50],
        effective_threshold,
        coarse_k,
        use_rerank,
        cat,
    )
    return effective_threshold, coarse_k


# BM25 路由 k 倍率：知识库扩充后 BM25 命中量已增加，降低倍率避免噪声淹没语义信号
_BM25_K_MULTIPLIER = 1.2
_COMPACT_SUBQUERY_ROUTES = {"keyword_bm25", "concept_meta", "structured_meta", "section_meta"}


def _route_adaptive_k(k: int, use_rerank: bool, route_name: str = "") -> int:
    """按路由类型调整 k

    BM25 路由按倍率放大候选（关键词命中覆盖面窄，需要更多候选），
    semantic/metadata 路由保持基础 k（语义检索精度高，小 k 足够）。
    """
    base_k = k
    if route_name == "keyword_bm25":
        base_k = int(base_k * _BM25_K_MULTIPLIER)
    elif route_name == "expanded":
        base_k = max(3, int(base_k * 0.8))
    elif route_name.endswith("_meta"):
        # metadata 路由是精准过滤，不需要大候选池
        # 知识库扩充后 meta 路由命中激增，限制上限为 10 避免噪声
        base_k = max(3, min(int(base_k * 0.6), 10))
    return min(base_k, 40 if use_rerank else 20)


def _multi_route_search(
    query: str,
    collection_name: str,
    k: int,
    filter: dict | None = None,
    cat: QueryCategory | None = None,
    use_rerank: bool = True,
    terms: list[str] | None = None,
    depth: RetrievalDepth | None = None,
    route_allowlist: set[str] | None = None,
) -> list[tuple[Document, float]]:
    """同步多路召回（支持 Adaptive Depth 跳过不必要路由）"""
    collection_routes = resolve_collection_routes(query, collection_name, cat=cat)
    route_queries = build_recall_queries(query, cat=cat)

    # Adaptive Depth: shallow 模式跳过 BM25 路由
    if depth and depth.skip_bm25:
        route_queries = [(name, rq) for name, rq in route_queries if name != "keyword_bm25"]

    route_specs: list[tuple[str, str, dict | None]] = [
        (route_name, route_query, filter) for route_name, route_query in route_queries
    ]

    # Adaptive Depth: shallow 模式跳过元数据路由；standard/deep/code 限制条数去冗余
    if not (depth and depth.skip_metadata_routes):
        meta_routes = build_metadata_routes(query, base_filter=filter, cat=cat, terms=terms)
        if depth and depth.max_metadata_routes < len(meta_routes):
            meta_routes = meta_routes[: depth.max_metadata_routes]
        route_specs.extend(meta_routes)
    if route_allowlist is not None:
        route_specs = [spec for spec in route_specs if spec[0] in route_allowlist]
        if not route_specs:
            route_specs = [("semantic", query, filter)]
    # Build flat list of all route specs (collection x route cross product)
    all_specs: list[tuple[str, str, str, dict | None]] = [
        (target_collection, route_name, route_query, route_filter)
        for target_collection in collection_routes
        for route_name, route_query, route_filter in route_specs
    ]

    def _search_one(spec):
        target_collection, route_name, route_query, route_filter = spec
        route_k = _route_adaptive_k(k, use_rerank, route_name)
        result = _raw_search(
            route_query, target_collection, route_k, filter=route_filter, route_name=route_name
        )
        return (f"{target_collection}:{route_name}", result)

    max_workers = min(len(all_specs), 8)
    route_results: list[tuple[str, list[tuple[Document, float]]]] = []
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_search_one, spec): spec for spec in all_specs}
        for future in as_completed(futures):
            try:
                route_results.append(future.result())
            except Exception as e:
                spec = futures[future]
                logger.warning("Route search failed: %s/%s: %s", spec[0], spec[1], e)
    logger.info(
        "Multi-route retrieval query=%s collections=%s routes=%s",
        query[:50],
        collection_routes,
        [route_name for route_name, _, _ in route_specs],
    )
    _log_route_diagnostics(
        query,
        route_specs=[
            (f"{target_collection}:{route_name}", route_query, route_filter)
            for target_collection in collection_routes
            for route_name, route_query, route_filter in route_specs
        ],
        route_results=route_results,
    )
    return merge_route_results(route_results, cat=cat)


def _route_timeout_seconds(route_name: str) -> float:
    base = float(getattr(settings, "TOOL_CALL_TIMEOUT", 30) or 30)
    if route_name == "keyword_bm25":
        return min(base, 15.0)
    if route_name.endswith("_meta"):
        return min(base, 15.0)
    return min(base, 20.0)


async def _safe_to_thread(
    name: str,
    func,
    *args,
    timeout: float,
    default=None,
    **kwargs,
):
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(func, *args, **kwargs),
            timeout=timeout,
        )
    except TimeoutError:
        logger.warning("Async route timed out: %s after %.1fs", name, timeout)
        return default
    except Exception as e:
        logger.warning("Async route failed: %s: %s", name, e)
        return default


async def _amulti_route_search(
    query: str,
    collection_name: str,
    k: int,
    filter: dict | None = None,
    cat: QueryCategory | None = None,
    use_rerank: bool = True,
    terms: list[str] | None = None,
    depth: RetrievalDepth | None = None,
    route_allowlist: set[str] | None = None,
) -> list[tuple[Document, float]]:
    collection_routes = resolve_collection_routes(query, collection_name, cat=cat)
    route_queries = build_recall_queries(query, cat=cat)
    if depth and depth.skip_bm25:
        route_queries = [(name, rq) for name, rq in route_queries if name != "keyword_bm25"]

    route_specs: list[tuple[str, str, dict | None]] = [
        (route_name, route_query, filter) for route_name, route_query in route_queries
    ]
    if not (depth and depth.skip_metadata_routes):
        meta_routes = build_metadata_routes(query, base_filter=filter, cat=cat, terms=terms)
        if depth and depth.max_metadata_routes < len(meta_routes):
            meta_routes = meta_routes[: depth.max_metadata_routes]
        route_specs.extend(meta_routes)
    if route_allowlist is not None:
        route_specs = [spec for spec in route_specs if spec[0] in route_allowlist]
        if not route_specs:
            route_specs = [("semantic", query, filter)]

    all_specs: list[tuple[str, str, str, dict | None]] = [
        (target_collection, route_name, route_query, route_filter)
        for target_collection in collection_routes
        for route_name, route_query, route_filter in route_specs
    ]
    if not all_specs:
        return []

    sem = asyncio.Semaphore(min(len(all_specs), 4))

    async def _search_one(spec: tuple[str, str, str, dict | None]):
        target_collection, route_name, route_query, route_filter = spec
        route_id = f"{target_collection}:{route_name}"

        def _run():
            route_k = _route_adaptive_k(k, use_rerank, route_name)
            result = _raw_search(
                route_query,
                target_collection,
                route_k,
                filter=route_filter,
                route_name=route_name,
            )
            return route_id, result

        async with sem:
            if route_name != "keyword_bm25":
                try:
                    from rag.vectorstore import get_vector_store_manager

                    route_k = _route_adaptive_k(k, use_rerank, route_name)
                    result = await get_vector_store_manager().asimilarity_search_with_score(
                        target_collection,
                        route_query,
                        route_k,
                        filter=route_filter,
                        timeout=_route_timeout_seconds(route_name),
                    )
                    for doc, _score in result:
                        doc.metadata["_collection"] = target_collection
                    return route_id, result
                except Exception as e:
                    logger.warning("Async vector route failed: %s: %s", route_id, e)
                    return route_id, []
            return await _safe_to_thread(
                route_id,
                _run,
                timeout=_route_timeout_seconds(route_name),
                default=(route_id, []),
            )

    gathered = await asyncio.gather(
        *(_search_one(spec) for spec in all_specs),
        return_exceptions=True,
    )
    route_results: list[tuple[str, list[tuple[Document, float]]]] = []
    for item in gathered:
        if isinstance(item, Exception):
            logger.warning("Async route gather failed: %s", item)
            continue
        if item is not None:
            route_results.append(item)

    logger.info(
        "Async multi-route retrieval query=%s collections=%s routes=%s",
        query[:50],
        collection_routes,
        [route_name for route_name, _, _ in route_specs],
    )
    _log_route_diagnostics(
        query,
        route_specs=[
            (f"{target_collection}:{route_name}", route_query, route_filter)
            for target_collection in collection_routes
            for route_name, route_query, route_filter in route_specs
        ],
        route_results=route_results,
    )
    merged = await _safe_to_thread(
        "async_route_merge",
        merge_route_results,
        route_results,
        timeout=min(float(getattr(settings, "TOOL_CALL_TIMEOUT", 30) or 30), 5.0),
        default=[],
        cat=cat,
    )
    return merged or []


# ── 公开 API ──────────────────────────────────────────


def _emit_evidence_metric(
    *,
    query: str,
    collection_name: str,
    start: float,
    fused,
    status: str = "ok",
    error_type: str = "",
    retry_count: int = 0,
    max_retries: int = 0,
    use_llm_verify: bool = False,
) -> None:
    meta = getattr(fused, "metadata", {}) or {}
    verdict = meta.get("evidence_verdict") if isinstance(meta, dict) else {}
    if not isinstance(verdict, dict):
        verdict = {}
    text_evidences = getattr(fused, "text_evidences", []) or []
    kg_evidences = getattr(fused, "kg_evidences", []) or []
    final_context = getattr(fused, "final_context", "") or ""
    metrics.emit_evidence_summary(
        query=query,
        collection=collection_name,
        status=status,
        duration_ms=round((time.perf_counter() - start) * 1000, 3),
        values={
            "k": meta.get("k", 0),
            "use_rerank": meta.get("use_rerank", False),
            "retrieval_depth": meta.get("retrieval_depth", ""),
            "retrieval_layer": meta.get("retrieval_layer", ""),
            "route_type": meta.get("route_type", ""),
            "score_threshold": meta.get("score_threshold", 0.0),
            "text_evidence_count": len(text_evidences),
            "kg_evidence_count": meta.get("kg_evidence_count", len(kg_evidences)),
            "kg_used": meta.get("kg_used", bool(kg_evidences)),
            "kg_skipped": meta.get("kg_skipped", False),
            "kg_category": meta.get("kg_category", ""),
            "kg_nodes_count": meta.get("kg_nodes_count", 0),
            "kg_edges_count": meta.get("kg_edges_count", 0),
            "kg_paths_count": meta.get("kg_paths_count", 0),
            "source_count": len(getattr(fused, "sources", []) or []),
            "context_chars": len(final_context),
            "context_tokens": getattr(fused, "used_token_budget", 0),
            "retrieval_latency_ms": meta.get("retrieval_latency_ms", None),
            "rerank_latency_ms": meta.get("rerank_latency_ms", None),
            "kg_latency_ms": meta.get("kg_latency_ms", None),
            "generation_latency_ms": None,
            "governance_latency_ms": None,
            "verifier_used": bool(verdict),
            "evidence_verdict": verdict.get("verdict", ""),
            "evidence_score": verdict.get("overall_score", 0.0),
            "retry_count": retry_count,
            "max_retries": max_retries,
            "use_llm_verify": use_llm_verify,
            "semantic_cache_hit": meta.get("semantic_cache_hit", False),
            "semantic_cache_similarity": meta.get("semantic_cache_similarity", 0.0),
            "error_type": error_type,
        },
    )


def retrieve_documents(
    query: str,
    collection_name: str = "",
    k: int = 5,
    score_threshold: float = SCORE_THRESHOLD,
    use_rerank: bool = True,
    filter: dict | None = None,
    depth: RetrievalDepth | None = None,
    cat: QueryCategory | None = None,
    precomputed_sub_queries: list[str] | None = None,
) -> list[Document]:
    """同步检索入口：**委托给 aretrieve_documents**，不再维护第二份流水线逻辑。

    这里原本有一份 448 行的同步副本，与 ``aretrieve_documents`` 逐段对应（"双胞胎"）。
    实测两者当前行为一致（15 条 query 的条数 / 集合 / 顺序完全相同），但双份实现迟早漂移，
    且它唯一的调用方是 ``warmup_query_cache``（入库后的缓存预热）——
    为这一个场景维护 448 行重复逻辑不划算，故改为委托。

    ⚠️ 不能在**已运行的事件循环**里调用（``asyncio.run`` 会抛 RuntimeError）。
    这与它唯一的使用场景（同步 CLI 入库后预热）不冲突；
    异步上下文请直接 ``await aretrieve_documents(...)``。
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        pass
    else:
        raise RuntimeError(
            "retrieve_documents() 是同步入口，不能在已运行的事件循环中调用；"
            "请改用 await aretrieve_documents(...)"
        )

    return asyncio.run(
        aretrieve_documents(
            query,
            collection_name,
            k,
            score_threshold,
            use_rerank,
            filter,
            depth,
            cat,
            precomputed_sub_queries,
        )
    )


# ── aretrieve_documents 的阶段函数 ────────────────────────────
#
# 这组函数把原本 428 行的单体编排按**已有的阶段边界**拆开。每个函数都有明确的
# 输入输出，因此可以单独测试 —— 这正是此前覆盖率上不去的结构性原因
# （见 ENGINEERING.md §1 P0：单体函数让纯函数有"结构性上限"）。
#
# 拆分原则：**只搬代码，不改行为**。原实现里的测量点仍由调用方负责，
# `stage_ms` 的所有权留在编排层，保证计时口径与拆分前逐字一致。


@dataclass(frozen=True)
class _RetrievalPlan:
    """阶段 2 的产物：一次检索实际采用的策略与阈值。

    把 `depth` / `k` / `use_rerank` 也放进返回值，是因为阶段 2 会**就地调整**它们
    （`depth=None` 时由分类推导；策略要求时覆盖 `k`、关掉重排）。
    原实现靠闭包变量隐式传递，拆开后显式化，避免调用方漏用调整后的值。
    """

    depth: RetrievalDepth
    k: int
    use_rerank: bool
    effective_threshold: float
    coarse_k: int
    retrieval_layer: str
    route_type: str


async def _stage_classify_query(
    query: str, cat: QueryCategory | None
) -> tuple[list[str], QueryCategory]:
    """阶段 1：归一化 → 词项抽取 → 分类。

    归一化文本只用于抽词项，不向下游传递（下游要的是词项本身，不是归一化串）。
    分类优先复用调用方传入的 `cat`，避免重复走一次规则/LLM 分类。
    """
    normalized = normalize_query_text(query)
    terms = extract_query_terms(normalized)
    resolved = cat or await aclassify_query(query, terms)
    return terms, resolved


def _stage_resolve_plan(
    query: str,
    cat: QueryCategory,
    k: int,
    score_threshold: float,
    use_rerank: bool,
    depth: RetrievalDepth | None,
) -> _RetrievalPlan:
    """阶段 2：解析检索策略，并据此调整 k / use_rerank / 阈值。

    `depth` 为 None 时由分类推导；显式传入时反向取出对应策略。
    注意 `k` 与 `use_rerank` 会被调整，调整后的值在返回值里。
    """
    if depth is None:
        strategy = resolve_retrieval_strategy(cat)
        depth = strategy.depth
    else:
        strategy = strategy_from_depth(depth)

    if k == 5 and depth.k != 5:
        k = depth.k
    if depth.skip_rerank and use_rerank:
        use_rerank = False

    effective_threshold, coarse_k = _resolve_retrieval_policy(
        query, k, score_threshold, use_rerank, cat=cat
    )
    return _RetrievalPlan(
        depth=depth,
        k=k,
        use_rerank=use_rerank,
        effective_threshold=effective_threshold,
        coarse_k=coarse_k,
        retrieval_layer=strategy.layer,
        route_type=strategy.route_type,
    )


async def _stage_decompose_query(
    query: str,
    cat: QueryCategory,
    depth: RetrievalDepth,
    precomputed_sub_queries: list[str] | None,
) -> tuple[list[str], bool]:
    """阶段 3：查询分解。

    返回 ``(子查询列表, 是否真的分解成多条)``。
    三条分支的优先级不能换：**预计算 > 策略要求跳过 > 真去分解**。
    """
    if precomputed_sub_queries is not None:
        sub_queries = precomputed_sub_queries
    elif depth.skip_decompose:
        sub_queries = [query]
    else:
        sub_queries = await decompose(query, cat=cat)
    return sub_queries, len(sub_queries) > 1


async def aretrieve_documents(
    query: str,
    collection_name: str = "",
    k: int = 5,
    score_threshold: float = SCORE_THRESHOLD,
    use_rerank: bool = True,
    filter: dict | None = None,
    depth: RetrievalDepth | None = None,
    cat: QueryCategory | None = None,
    precomputed_sub_queries: list[str] | None = None,
) -> list[Document]:
    start = time.perf_counter()
    raw_results_count = 0
    post_dedup_count = 0
    post_threshold_count = 0
    post_rerank_count = 0
    post_window_count = 0
    window_added_count = 0
    effective_threshold = score_threshold
    coarse_k = k
    stage_ms: dict[str, float] = {}
    decomposed = False
    sub_queries: list[str] = []
    rerank_used = False
    hyde_triggered = False
    hyde_added_count = 0
    hyde_error = ""
    retrieval_layer = ""
    route_type = ""
    try:
        _stage_start = time.perf_counter()
        _terms, _cat = await _stage_classify_query(query, cat)
        stage_ms["classification_ms"] = round((time.perf_counter() - _stage_start) * 1000, 3)

        _plan = _stage_resolve_plan(query, _cat, k, score_threshold, use_rerank, depth)
        depth = _plan.depth
        k = _plan.k
        use_rerank = _plan.use_rerank
        effective_threshold = _plan.effective_threshold
        coarse_k = _plan.coarse_k
        retrieval_layer = _plan.retrieval_layer
        route_type = _plan.route_type

        _stage_start = time.perf_counter()
        sub_queries, decomposed = await _stage_decompose_query(
            query, _cat, depth, precomputed_sub_queries
        )
        stage_ms["decompose_ms"] = round((time.perf_counter() - _stage_start) * 1000, 3)

        _stage_start = time.perf_counter()
        if decomposed:

            async def _branch_search(
                label: str,
                branch_query: str,
                branch_cat: QueryCategory | None,
                branch_terms: list[str] | None,
                route_allowlist: set[str] | None = None,
            ):
                branch_results = await _amulti_route_search(
                    branch_query,
                    collection_name,
                    coarse_k,
                    filter=filter,
                    cat=branch_cat,
                    use_rerank=use_rerank,
                    terms=branch_terms,
                    depth=depth,
                    route_allowlist=route_allowlist,
                )
                branch_results = await _safe_to_thread(
                    f"async_{label}_dedup",
                    dedup_same_section,
                    branch_results,
                    timeout=min(float(getattr(settings, "TOOL_CALL_TIMEOUT", 30) or 30), 3.0),
                    default=branch_results,
                    max_per_section=2,
                )
                return label, [
                    (doc, score) for doc, score in branch_results if score >= effective_threshold
                ]

            tasks = [_branch_search("original", query, _cat, _terms)]
            route_allowlist = _COMPACT_SUBQUERY_ROUTES if _cat.is_comparison else None
            for sq in [sq for sq in sub_queries if sq != query]:
                tasks.append(_branch_search("sub", sq, None, None, route_allowlist=route_allowlist))
            gathered = await asyncio.gather(*tasks, return_exceptions=True)
            all_route_results: list[tuple[str, list[tuple[Document, float]]]] = []
            for item in gathered:
                if isinstance(item, Exception):
                    logger.warning("Async sub-query branch failed: %s", item)
                    continue
                all_route_results.append(item)
            results = await _safe_to_thread(
                "async_weighted_rrf_merge",
                weighted_rrf_merge,
                all_route_results,
                {"original": 1.5, "sub": 1.0},
                timeout=min(float(getattr(settings, "TOOL_CALL_TIMEOUT", 30) or 30), 5.0),
                default=[],
                cat=_cat,
            )
            results = results or []
            logger.info(
                "Async decomposed retrieval query=%s sub_queries=%d merged=%d",
                query[:50],
                len(sub_queries),
                len(results),
            )
        else:
            results = await _amulti_route_search(
                query,
                collection_name,
                coarse_k,
                filter=filter,
                cat=_cat,
                use_rerank=use_rerank,
                terms=_terms,
                depth=depth,
            )
        stage_ms["route_merge_ms"] = round((time.perf_counter() - _stage_start) * 1000, 3)

        raw_results_count = len(results)
        _max_per = (
            4
            if (_cat.is_exercise or _cat.is_answer)
            else (3 if (_cat.is_comparison or _cat.is_long) else 2)
        )
        results = await _safe_to_thread(
            "async_section_dedup",
            dedup_same_section,
            results,
            timeout=min(float(getattr(settings, "TOOL_CALL_TIMEOUT", 30) or 30), 3.0),
            default=results,
            max_per_section=_max_per,
        )
        post_dedup_count = len(results)

        filtered = [doc for doc, score in results if score >= effective_threshold]
        post_threshold_count = len(filtered)
        _log_final_retrieval_summary("async-post-threshold", query, filtered)

        _rerank_ms = 0.0
        if not decomposed:
            if use_rerank and filtered:
                _stage_start = time.perf_counter()
                reranked = await _safe_to_thread(
                    "async_rerank",
                    rerank,
                    query,
                    filtered,
                    timeout=float(getattr(settings, "RERANK_TIMEOUT", 30) or 30),
                    default=filtered[:k],
                    top_k=k,
                )
                _rerank_ms += (time.perf_counter() - _stage_start) * 1000
                rerank_used = True
                # 双重阈值过滤（异步），兜底保留 top-2
                filtered = _apply_rerank_threshold(reranked, min_keep=2)
                _log_final_retrieval_summary("async-post-rerank", query, filtered)
            elif not use_rerank:
                filtered = filtered[:k]
        else:
            if use_rerank and filtered:
                _stage_start = time.perf_counter()
                reranked = await _safe_to_thread(
                    "async_rerank_decomposed",
                    rerank,
                    query,
                    filtered,
                    timeout=float(getattr(settings, "RERANK_TIMEOUT", 30) or 30),
                    default=filtered[:k],
                    top_k=k * 2,
                )
                _rerank_ms += (time.perf_counter() - _stage_start) * 1000
                rerank_used = True
                # 双重阈值过滤（异步分解查询），兜底保留 top-2
                filtered = _apply_rerank_threshold(reranked, min_keep=2)
                _log_final_retrieval_summary("async-post-rerank-decomposed", query, filtered)
            elif not use_rerank:
                filtered = filtered[: k * 2]
        stage_ms["rerank_ms"] = round(_rerank_ms, 3)
        post_rerank_count = len(filtered)

        top_rerank_score_for_hyde = 0.0
        rerank_scores_for_hyde = [
            float(doc.metadata.get("rerank_score") or 0.0)
            for doc in filtered
            if doc.metadata.get("rerank_score") is not None
        ]
        if rerank_scores_for_hyde:
            top_rerank_score_for_hyde = max(rerank_scores_for_hyde)

        if not depth.skip_hyde and should_trigger_hyde(
            query, len(filtered), top_rerank_score_for_hyde, _cat
        ):
            _stage_start = time.perf_counter()
            hyde_query = await _safe_to_thread(
                "async_hyde_generate",
                generate_hyde_query,
                query,
                timeout=min(float(getattr(settings, "LLM_TIMEOUT", 60) or 60), 10.0),
                default="",
            )
            if hyde_query and hyde_query != query:
                hyde_triggered = True
                try:
                    hyde_terms = extract_query_terms(normalize_query_text(hyde_query))
                    hyde_results = await _amulti_route_search(
                        hyde_query,
                        collection_name,
                        coarse_k,
                        filter=filter,
                        cat=_cat,
                        use_rerank=use_rerank,
                        terms=hyde_terms,
                        depth=depth,
                    )
                    hyde_results = await _safe_to_thread(
                        "async_hyde_dedup",
                        dedup_same_section,
                        hyde_results,
                        timeout=min(float(getattr(settings, "TOOL_CALL_TIMEOUT", 30) or 30), 3.0),
                        default=hyde_results,
                        max_per_section=2,
                    )
                    hyde_docs = [
                        doc for doc, score in hyde_results if score >= effective_threshold * 0.8
                    ]
                    if use_rerank and hyde_docs:
                        hyde_docs = await _safe_to_thread(
                            "async_hyde_rerank",
                            rerank,
                            query,
                            hyde_docs,
                            timeout=float(getattr(settings, "RERANK_TIMEOUT", 30) or 30),
                            default=hyde_docs[:k],
                            top_k=k,
                        )
                        rerank_used = True
                    for doc in hyde_docs:
                        doc.metadata["_hyde_fallback"] = True
                        doc.metadata["_hyde_query"] = hyde_query[:120]
                    existing_keys = {
                        str(
                            doc.metadata.get("content_hash")
                            or f"{doc.metadata.get('source', '') or doc.metadata.get('source_file', '')}:{doc.page_content[:80]}"
                        )
                        for doc in filtered
                    }
                    merged_hyde_docs = []
                    for doc in hyde_docs:
                        key = str(
                            doc.metadata.get("content_hash")
                            or f"{doc.metadata.get('source', '') or doc.metadata.get('source_file', '')}:{doc.page_content[:80]}"
                        )
                        if key not in existing_keys:
                            merged_hyde_docs.append(doc)
                            existing_keys.add(key)
                    if merged_hyde_docs:
                        filtered = (filtered + merged_hyde_docs)[: max(k, len(filtered))]
                        hyde_added_count = len(merged_hyde_docs)
                        _log_final_retrieval_summary("async-post-hyde", query, filtered)
                except Exception as e:
                    hyde_error = e.__class__.__name__
                    logger.warning("Async HyDE fallback retrieval failed: %s", e)
            stage_ms["hyde_ms"] = round((time.perf_counter() - _stage_start) * 1000, 3)
        else:
            stage_ms["hyde_ms"] = 0.0

        before_window = len(filtered)
        if filtered:
            _stage_start = time.perf_counter()

            def _expand_windows():
                if collection_name:
                    adaptive_wsize = (
                        0
                        if (depth and depth.depth == "shallow")
                        else (1 if depth and depth.depth == "standard" else 2)
                    )
                    return sentence_window_expand(
                        filtered, collection_name, window_size=adaptive_wsize
                    )
                grouped_docs: dict[str, list[Document]] = {}
                for doc in filtered:
                    doc_collection = str(doc.metadata.get("_collection") or "")
                    if doc_collection:
                        grouped_docs.setdefault(doc_collection, []).append(doc)
                if not grouped_docs:
                    return filtered
                expanded_docs: list[Document] = []
                for doc_collection, docs_in_collection in grouped_docs.items():
                    adaptive_wsize = (
                        0
                        if (depth and depth.depth == "shallow")
                        else (1 if depth and depth.depth == "standard" else 2)
                    )
                    expanded_docs.extend(
                        sentence_window_expand(
                            docs_in_collection, doc_collection, window_size=adaptive_wsize
                        )
                    )
                return expanded_docs

            filtered = await _safe_to_thread(
                "async_window_expand",
                _expand_windows,
                timeout=min(float(getattr(settings, "TOOL_CALL_TIMEOUT", 30) or 30), 5.0),
                default=filtered,
            )
            # Negative Sampling: 对 window 展开的噪声 chunk 软降级
            _is_cmp = bool(_cat and _cat.is_comparison)
            filtered = downgrade_window_noise(filtered, query, is_comparison=_is_cmp)
            _log_final_retrieval_summary("async-post-window", query, filtered)
            stage_ms["window_ms"] = round((time.perf_counter() - _stage_start) * 1000, 3)
        else:
            stage_ms["window_ms"] = 0.0
        post_window_count = len(filtered)
        window_added_count = post_window_count - before_window

        for doc in filtered:
            doc.metadata["_retrieval_depth"] = depth.depth
            doc.metadata["_retrieval_layer"] = retrieval_layer
            doc.metadata["_route_type"] = route_type
            doc.metadata["_effective_k"] = k
            doc.metadata["_coarse_k"] = coarse_k

        window_expanded_count = sum(1 for doc in filtered if doc.metadata.get("_window_expanded"))
        context_chars = sum(len(doc.page_content or "") for doc in filtered)
        role_counts = {
            "detail": sum(
                1 for doc in filtered if doc.metadata.get("section.chunk_role") == "detail"
            ),
        }
        rerank_scores = [
            float(doc.metadata.get("rerank_score") or 0.0)
            for doc in filtered
            if doc.metadata.get("rerank_score") is not None
        ]
        top_rerank_score = rerank_scores[0] if rerank_scores else 0.0
        avg_rerank_score = (
            round(sum(rerank_scores) / len(rerank_scores), 6) if rerank_scores else 0.0
        )
        metrics.emit_retrieve_summary(
            query=query,
            collection=collection_name,
            duration_ms=round((time.perf_counter() - start) * 1000, 3),
            values={
                "k": k,
                "coarse_k": coarse_k,
                "threshold": effective_threshold,
                "retrieval_depth": depth.depth if depth else "",
                "retrieval_layer": retrieval_layer,
                "route_type": route_type,
                "classifier_source": getattr(_cat, "source", ""),
                "decomposed": decomposed,
                "sub_query_count": len(sub_queries),
                "use_rerank": use_rerank,
                "rerank_used": rerank_used,
                "hyde_triggered": hyde_triggered,
                "hyde_added_count": hyde_added_count,
                "hyde_error": hyde_error,
                "skip_bm25": depth.skip_bm25 if depth else False,
                "skip_metadata_routes": depth.skip_metadata_routes if depth else False,
                "skip_kg": depth.skip_kg if depth else False,
                "before_threshold": raw_results_count,
                "after_section_dedup": post_dedup_count,
                "after_threshold": post_threshold_count,
                "after_rerank": post_rerank_count,
                "after_window": post_window_count,
                "window_added": window_added_count,
                "window_expanded_count": window_expanded_count,
                "hit": bool(filtered),
                "context_chars": context_chars,
                "top_rerank_score": top_rerank_score,
                "avg_rerank_score": avg_rerank_score,
                "detail_hits": role_counts["detail"],
                **_cache_stats_fields(),
                "async_routes": True,
                **stage_ms,
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
                "after_window": post_window_count,
                "window_added": window_added_count,
                "retrieval_layer": retrieval_layer,
                "route_type": route_type,
                "decomposed": decomposed,
                "sub_query_count": len(sub_queries),
                "use_rerank": use_rerank,
                "rerank_used": rerank_used,
                "hyde_triggered": hyde_triggered,
                "hyde_added_count": hyde_added_count,
                "hyde_error": hyde_error,
                "async_routes": True,
                **stage_ms,
                "error_type": e.__class__.__name__,
            },
        )
        raise


async def aretrieve_evidence(
    query: str,
    collection_name: str = "",
    k: int = 5,
    score_threshold: float = SCORE_THRESHOLD,
    use_rerank: bool = True,
    filter: dict | None = None,
    student_profile: str = "",
    max_tokens: int = settings.CONTEXT_TOKEN_BUDGET,
    depth: RetrievalDepth | None = None,
) -> FusedEvidence:
    from rag.evidence import FusedEvidence
    from rag.fusion import afuse_documents
    from rag.verifier import averify_evidence

    try:
        from rag.semantic_cache import get_semantic_cache

        _sc = get_semantic_cache()
        _filter_sig = json.dumps(filter, sort_keys=True) if filter else ""
        _cached_fused, _semantic_cache_sim = await _sc.alookup(
            query,
            collection_name=collection_name,
            filter_sig=_filter_sig,
        )
        if _cached_fused is not None:
            _cached_fused.metadata["semantic_cache_hit"] = True
            _cached_fused.metadata["semantic_cache_similarity"] = round(_semantic_cache_sim, 4)
            _emit_evidence_metric(
                query=query,
                collection_name=collection_name,
                start=time.perf_counter(),
                fused=_cached_fused,
            )
            return _cached_fused
    except Exception as _sc_err:
        logger.debug("Async semantic cache lookup skipped: %s", _sc_err)

    metric_start = time.perf_counter()
    _terms = extract_query_terms(normalize_query_text(query))
    _cat = await aclassify_query(query, _terms)
    _resolved_depth = depth
    if _resolved_depth is None:
        strategy = resolve_retrieval_strategy(_cat)
        _resolved_depth = strategy.depth
    else:
        strategy = strategy_from_depth(_resolved_depth)
    retrieval_layer = strategy.layer
    route_type = strategy.route_type
    effective_k = _resolved_depth.k if k == 5 and _resolved_depth.k != 5 else k

    _decompose_start = time.perf_counter()
    if _resolved_depth.skip_decompose:
        precomputed_sub_queries = [query]
    else:
        precomputed_sub_queries = await decompose(query, cat=_cat)
    async_decompose_ms = round((time.perf_counter() - _decompose_start) * 1000, 3)

    _stage_start = time.perf_counter()
    docs = await aretrieve_documents(
        query=query,
        collection_name=collection_name,
        k=effective_k,
        score_threshold=score_threshold,
        use_rerank=use_rerank,
        filter=filter,
        depth=_resolved_depth,
        cat=_cat,
        precomputed_sub_queries=precomputed_sub_queries,
    )
    retrieval_latency_ms = round((time.perf_counter() - _stage_start) * 1000, 3)

    if not docs:
        fused = FusedEvidence(
            final_context="",
            sources=[],
            metadata={
                "query": query,
                "result_count": 0,
                "k": effective_k,
                "use_rerank": use_rerank,
                "retrieval_depth": _resolved_depth.depth,
                "retrieval_layer": retrieval_layer,
                "route_type": route_type,
                "score_threshold": score_threshold,
                "retrieval_latency_ms": retrieval_latency_ms,
                "rerank_latency_ms": None,
            },
        )
    else:
        fused = await afuse_documents(
            docs,
            query=query,
            student_profile=student_profile,
            max_tokens=max_tokens,
            depth=_resolved_depth.depth,
        )
        fused.metadata["query"] = query
        fused.metadata["collection"] = collection_name
        fused.metadata["result_count"] = len(docs)
        fused.metadata["k"] = (
            docs[0].metadata.get("_effective_k", effective_k) if docs else effective_k
        )
        fused.metadata["use_rerank"] = use_rerank
        fused.metadata["retrieval_depth"] = (
            docs[0].metadata.get("_retrieval_depth", _resolved_depth.depth)
            if docs
            else _resolved_depth.depth
        )
        fused.metadata["retrieval_layer"] = retrieval_layer
        fused.metadata["route_type"] = route_type
        fused.metadata["coarse_k"] = docs[0].metadata.get("_coarse_k") if docs else None
        fused.metadata["score_threshold"] = score_threshold
        fused.metadata["source_count"] = len(fused.sources)
        fused.metadata["async_decompose_ms"] = async_decompose_ms
        fused.metadata["retrieval_latency_ms"] = retrieval_latency_ms
        fused.metadata["rerank_latency_ms"] = None

    try:
        verification = await averify_evidence(fused, query=query, use_llm=False)
        fused.metadata["evidence_verdict"] = verification.model_dump(mode="json")
    except Exception as e:
        logger.warning("Async evidence verification failed: %s", e)

    try:
        from rag.semantic_cache import get_semantic_cache

        _filter_sig = json.dumps(filter, sort_keys=True) if filter else ""
        await get_semantic_cache().astore(
            query,
            fused,
            collection_name=collection_name,
            filter_sig=_filter_sig,
        )
    except Exception as _sc_err:
        logger.debug("Async semantic cache store skipped: %s", _sc_err)

    _emit_evidence_metric(
        query=query,
        collection_name=collection_name,
        start=metric_start,
        fused=fused,
    )
    return fused


async def aretrieve_evidence_with_retry(
    query: str,
    collection_name: str = "",
    k: int = 5,
    score_threshold: float = SCORE_THRESHOLD,
    use_rerank: bool = True,
    filter: dict | None = None,
    student_profile: str = "",
    max_tokens: int = settings.CONTEXT_TOKEN_BUDGET,
    depth: RetrievalDepth | None = None,
    *,
    max_retries: int = 2,
    use_llm_verify: bool = False,
) -> tuple[FusedEvidence, VerificationResult]:
    from rag.verifier import Verdict, VerificationResult, averify_evidence

    retry_metric_start = time.perf_counter()
    retry_count = 0
    current_kwargs: dict = {
        "query": query,
        "collection_name": collection_name,
        "k": k,
        "score_threshold": score_threshold,
        "use_rerank": use_rerank,
        "filter": filter,
        "student_profile": student_profile,
        "max_tokens": max_tokens,
        "depth": depth,
    }

    fused = await aretrieve_evidence(**current_kwargs)
    existing_verdict = fused.metadata.get("evidence_verdict")
    if existing_verdict:
        try:
            result = VerificationResult.model_validate(existing_verdict)
        except Exception:
            result = await averify_evidence(fused, query=query, use_llm=use_llm_verify)
            fused.metadata["evidence_verdict"] = result.model_dump(mode="json")
    else:
        result = await averify_evidence(fused, query=query, use_llm=use_llm_verify)
        fused.metadata["evidence_verdict"] = result.model_dump(mode="json")

    for attempt in range(max_retries):
        if result.verdict == Verdict.PASS:
            break
        hints = result.retry_hints
        if not hints:
            logger.info("Async retry %d: no hints available, stopping", attempt + 1)
            break
        if "k" in hints:
            current_kwargs["k"] = hints["k"]
            if current_kwargs.get("depth") and current_kwargs["depth"].depth == "shallow":
                current_kwargs["depth"] = L2_STANDARD.depth
                logger.info("Async retry %d: depth upgraded shallow → L2 standard", attempt + 1)
        if "score_threshold" in hints:
            current_kwargs["score_threshold"] = hints["score_threshold"]
        if "max_tokens" in hints:
            current_kwargs["max_tokens"] = hints["max_tokens"]
        if "use_rerank" in hints:
            current_kwargs["use_rerank"] = hints["use_rerank"]

        logger.info(
            "Async retry %d/%d for query=%s verdict=%s hints=%s",
            attempt + 1,
            max_retries,
            query[:40],
            result.verdict.value,
            hints,
        )

        retry_count = attempt + 1
        fused = await aretrieve_evidence(**current_kwargs)
        result = await averify_evidence(fused, query=query, use_llm=use_llm_verify)
        fused.metadata["evidence_verdict"] = result.model_dump(mode="json")

    _emit_evidence_metric(
        query=query,
        collection_name=collection_name,
        start=retry_metric_start,
        fused=fused,
        retry_count=retry_count,
        max_retries=max_retries,
        use_llm_verify=use_llm_verify,
    )
    return fused, result


# ── 缓存预热 ──────────────────────────────────────────

_WARMUP_QUERIES = [
    # 数据结构
    "什么是栈和队列",
    "二叉树的遍历方式",
    "图的深度优先搜索",
    "哈希表解决冲突的方法",
    "快速排序的原理",
    "最短路径Dijkstra算法",
    "最小生成树Prim算法",
    "B树和B+树的区别",
    # 计算机组成原理
    "Cache的映射方式",
    "虚拟存储器的工作原理",
    "指令流水线的三个阶段",
    "中断处理过程",
    "总线的分类和结构",
    "浮点数的表示",
    # 操作系统
    "进程死锁的四个必要条件",
    "银行家算法",
    "进程和线程的区别",
    "页面置换算法LRU",
    "信号量PV操作",
    "内存管理的分页和分段",
    "进程调度算法有哪些",
    "文件系统的结构",
    # 计算机网络
    "TCP三次握手过程",
    "TCP和UDP的区别",
    "拥塞控制的四个算法",
    "OSI七层模型",
    "IP地址的分类",
    "DNS的工作原理",
    "HTTP协议的特点",
    "路由协议OSPF和RIP的区别",
    # 跨学科对比
    "虚拟存储器和Cache的异同",
    "操作系统调度和网络拥塞控制的共同思想",
]


def warmup_query_cache(quiet: bool = False) -> dict:
    """预热查询缓存：对高频 408 知识点执行检索，填充缓存

    在索引构建完成后调用，消除首批用户的冷启动延迟。
    返回预热统计：{total, succeeded, failed, elapsed_ms}
    """
    import time as _time

    total = len(_WARMUP_QUERIES)
    succeeded = 0
    failed = 0
    t0 = _time.perf_counter()

    for q in _WARMUP_QUERIES:
        try:
            retrieve_documents(q, k=5, use_rerank=True)
            succeeded += 1
        except Exception:
            failed += 1

    elapsed_ms = round((_time.perf_counter() - t0) * 1000, 1)
    if not quiet:
        logger.info(
            "Cache warmup done: %d/%d queries succeeded, %d failed, %.0f ms",
            succeeded,
            total,
            failed,
            elapsed_ms,
        )

    return {
        "total": total,
        "succeeded": succeeded,
        "failed": failed,
        "elapsed_ms": elapsed_ms,
    }
