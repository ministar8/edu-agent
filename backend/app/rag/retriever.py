"""RAG 检索门面模块

统一检索入口：多路召回 → 同 section 去重 → 阈值过滤 → Reranker 重排 → Sentence Window 展开。
get_llm() 已迁移至 rag_utils.py，供 LangChain Agent 使用（ChatOpenAI 实例）。

结构化 API：
  - retrieve_evidence(): 一步到位返回 FusedEvidence（含 sources/diversity/metadata）

兼容 API：
  - retrieve_documents(): 返回 list[Document]
  - build_rag_context(): 返回纯文本上下文

子模块职责划分：
  - recall.py:    查询归一化、同义词扩展、关键词提取、召回路由构建、元数据路由、集合路由
  - bm25.py:      BM25 全文检索
  - postprocess.py: RRF 合并、同 section 去重、层级上下文展开、连续补齐
  - context.py:   KG 关联知识补充、RAG 上下文拼接
"""

from __future__ import annotations

import json
import logging
import asyncio
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed

from langchain_core.documents import Document

from app.config import settings
from app.rag.metrics import metrics


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
        len(high_confidence), len(reranked), final_min, rel_min, abs_min, min_keep,
    )
    return fallback


from app.rag.query_classifier import (
    aclassify_query,
    classify_query,
    QueryCategory,
    RetrievalDepth,
)
from app.rag.retrieval_strategy import L2_STANDARD, resolve_retrieval_strategy, strategy_from_depth
from app.rag.reranker import rerank

# 子模块导入
from app.rag.recall import (
    build_recall_queries,
    build_metadata_routes,
    resolve_collection_routes,
)
from app.rag.rag_utils import normalize_query_text, extract_query_terms
from app.rag.bm25 import bm25_search
from app.rag.postprocess import (
    merge_route_results,
    weighted_rrf_merge,
    dedup_same_section,
    sentence_window_expand,
    downgrade_window_noise,
)
from app.rag.query_decomposer import decompose, decompose_sync
from app.rag.hyde import generate_hyde_query, should_trigger_hyde

logger = logging.getLogger(__name__)

# RRF 融合分数阈值（基于采样校准，非余弦距离）
# RRF(k=20): 排名1≈0.048, 排名5≈0.040（权重 1.0 时）
# 权重 1.5 的路由第 10 名 = 1.5/(20+10) = 0.05 → 刚好过旧阈值
# 0.06 ≈ "至少1路前7" 或 "2路前15"，过滤掉排名#8+的单路噪声
SCORE_THRESHOLD = 0.06

# 查询缓存（LRU + TTL）
_query_cache: dict[str, tuple[list[tuple[Document, float]], float]] = {}  # key → (results, timestamp)
_MAX_CACHE_SIZE = 200
_CACHE_TTL = 300  # 5 minutes TTL
_cache_hits = 0
_cache_misses = 0

# 集合文档数缓存（5 分钟 TTL，避免重复 collection.count() 调用）
_COLLECTION_COUNT_TTL = 300  # seconds
_collection_count_cache: dict[str, tuple[int, float]] = {}

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
    # 确定性 cache key：filter dict 排序后序列化，避免 {"a":1,"b":2} vs {"b":2,"a":1} 不一致
    filter_key = json.dumps(filter, sort_keys=True, ensure_ascii=False) if filter else ""
    cache_key = f"{collection_name}:{route_name}:{query}:{filter_key}:k={k}"
    global _cache_hits, _cache_misses
    now = time.monotonic()
    cached_entry = _query_cache.get(cache_key)
    if cached_entry is not None:
        cached_results, cached_ts = cached_entry
        if now - cached_ts < _CACHE_TTL:
            _cache_hits += 1
            # LRU: 重新插入以更新访问时间
            _query_cache[cache_key] = (cached_results, now)
            logger.debug("Cache hit for query: %s (hits=%d misses=%d rate=%.1f%%)",
                         query, _cache_hits, _cache_misses,
                         100 * _cache_hits / max(_cache_hits + _cache_misses, 1))
            return cached_results
        else:
            # TTL 过期，删除
            del _query_cache[cache_key]
    _cache_misses += 1

    if route_name == "keyword_bm25":
        import jieba
        from app.rag.recall import _BM25_STOP_WORDS
        # cut_for_search 同时保留全词和子词：
        # "进程同步机制" → "进程"、"同步"、"机制"、"进程同步"、"同步机制"
        _BM25_SINGLE_CHAR_ALLOW = {"栈", "堆", "树", "图", "串", "队", "链", "表", "网", "库", "锁", "页", "段", "核", "集"}
        terms = [w for w in jieba.cut_for_search(query)
                 if w.strip() and w not in _BM25_STOP_WORDS and (len(w) >= 2 or w in _BM25_SINGLE_CHAR_ALLOW)]
        # 限制最多 6 个 term，优先保留复合词（长词更精准）
        if len(terms) > 6:
            terms = sorted(terms, key=len, reverse=True)[:6]
        # 过滤后若为空（jieba 把短 query 分成停用词），回退用原始 query
        if not terms:
            terms = [query.strip()]
        results = bm25_search(terms, collection_name, k, filter=filter)
    else:
        from app.rag.vectorstore import get_vector_store_manager
        store = get_vector_store_manager().get_store(collection_name)
        search_kwargs = {"k": k}
        if filter:
            search_kwargs["filter"] = filter
        results = store.similarity_search_with_score(query, **search_kwargs)

    # 注入集合来源，供 RRF 合并区分跨集合的同名文档
    for doc, _score in results:
        doc.metadata["_collection"] = collection_name

    if len(_query_cache) > _MAX_CACHE_SIZE:
        # LRU eviction: 按访问时间排序，删除最久未访问的 25%
        sorted_keys = sorted(_query_cache.keys(), key=lambda k: _query_cache[k][1])
        _evict_count = max(1, len(_query_cache) // 4)
        for _key in sorted_keys[:_evict_count]:
            del _query_cache[_key]
    _query_cache[cache_key] = (results, time.monotonic())
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
    from app.rag.recall import get_route_weight
    _BASELINE_WEIGHT = 1.5  # semantic default 权重作为基准
    _active_routes = ("semantic", "keyword_bm25", "focus", "expanded",
                      "code_meta", "exercise_meta", "answer_meta",
                      "concept_meta", "comparison_meta", "structured_meta",
                      "section_meta", "formula_meta", "table_meta", "merged_qa_meta")
    _max_w = max(get_route_weight(r, cat) for r in _active_routes)
    effective_threshold *= _max_w / _BASELINE_WEIGHT

    # 阈值自适应：在权重校准基础上，按查询类型微调
    # 注意：权重校准已收紧高权重路由，此处只需小幅调整
    if cat.is_exercise or cat.is_answer:
        effective_threshold *= 1.2   # 习题/答案适度收紧
    elif cat.is_short:
        effective_threshold *= 0.75  # 短查询结果少，放宽阈值保召回
    elif cat.is_long or cat.is_comparison:
        effective_threshold *= 1.1   # 长查询/对比查询适度收紧

    if use_rerank:
        expand_factor = _RERANK_EXPAND_FACTOR
        if cat.is_short:
            expand_factor = 6          # 短查询检索命中少，需要更大候选池
        elif cat.is_code or cat.is_long:
            expand_factor = 6
        elif cat.is_answer or cat.is_exercise:
            expand_factor = 5          # 答案/习题适度扩大
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
        normalized[:50], effective_threshold, coarse_k, use_rerank, cat,
    )
    return effective_threshold, coarse_k


def _get_collection_count(collection_name: str) -> int:
    """获取集合文档数，带 5 分钟 TTL 缓存"""
    global _collection_count_cache
    now = time.monotonic()
    cached = _collection_count_cache.get(collection_name)
    if cached is not None:
        count, ts = cached
        if now - ts < _COLLECTION_COUNT_TTL:
            return count
    try:
        from app.rag.vectorstore import get_vector_store_manager
        coll = get_vector_store_manager().client.get_collection(collection_name)
        count = coll.count()
    except Exception:
        count = 500  # 默认值
    _collection_count_cache[collection_name] = (count, now)
    return count


def _infer_kg_category(collection_name: str, docs: list[Document] | None = None) -> str:
    if collection_name:
        return collection_name
    counts = Counter(
        str((doc.metadata or {}).get("_collection") or "")
        for doc in (docs or [])
        if (doc.metadata or {}).get("_collection")
    )
    if not counts:
        return ""
    return counts.most_common(1)[0][0]


def _query_kg_evidence(query: str, category: str = ""):
    try:
        from app.rag.evidence import kg_evidence_from_query
        return kg_evidence_from_query(query, category=category)
    except Exception as e:
        logger.debug("KG evidence query failed: %s", e)
        return None


def _adaptive_k(k: int, collection_count: int, use_rerank: bool) -> int:
    """按集合大小自适应调整 k

    小集合（<200条）：k 上限为集合大小的 30%，避免全量扫描
    大集合（>800条）：k 可以放大到 k*factor
    """
    if collection_count <= 0:
        return k
    # 小集合保护：最多搜集合的 30%
    max_k_for_size = max(k, int(collection_count * 0.30))
    if use_rerank:
        expanded = min(k * _RERANK_EXPAND_FACTOR, 50)
    else:
        expanded = min(k * 2, 20)
    return min(expanded, max_k_for_size)


# BM25 路由 k 倍率：知识库扩充后 BM25 命中量已增加，降低倍率避免噪声淹没语义信号
_BM25_K_MULTIPLIER = 1.2
_COMPACT_SUBQUERY_ROUTES = {"keyword_bm25", "concept_meta", "structured_meta", "section_meta"}


def _route_adaptive_k(k: int, collection_count: int, use_rerank: bool, route_name: str = "") -> int:
    """按路由类型和集合大小自适应调整 k

    BM25 路由 k × 1.5（关键词命中覆盖面窄，需要更多候选），
    semantic/metadata 路由保持基础 k（语义检索精度高，小 k 足够）。
    """
    if collection_count <= 0:
        base_k = k
    else:
        base_k = min(k, max(k, int(collection_count * 0.30)))
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
        (route_name, route_query, filter)
        for route_name, route_query in route_queries
    ]

    # Adaptive Depth: shallow 模式跳过元数据路由；standard/deep/code 限制条数去冗余
    if not (depth and depth.skip_metadata_routes):
        meta_routes = build_metadata_routes(query, base_filter=filter, cat=cat, terms=terms)
        if depth and depth.max_metadata_routes < len(meta_routes):
            meta_routes = meta_routes[:depth.max_metadata_routes]
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
        route_k = _route_adaptive_k(k, _get_collection_count(target_collection), use_rerank, route_name)
        result = _raw_search(route_query, target_collection, route_k,
                             filter=route_filter, route_name=route_name)
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
        query[:50], collection_routes,
        [route_name for route_name, _, _ in route_specs],
    )
    _log_route_diagnostics(query, route_specs=[(f"{target_collection}:{route_name}", route_query, route_filter) for target_collection in collection_routes for route_name, route_query, route_filter in route_specs], route_results=route_results)
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
    except (asyncio.TimeoutError, TimeoutError):
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
        (route_name, route_query, filter)
        for route_name, route_query in route_queries
    ]
    if not (depth and depth.skip_metadata_routes):
        meta_routes = build_metadata_routes(query, base_filter=filter, cat=cat, terms=terms)
        if depth and depth.max_metadata_routes < len(meta_routes):
            meta_routes = meta_routes[:depth.max_metadata_routes]
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
            route_k = _route_adaptive_k(k, _get_collection_count(target_collection), use_rerank, route_name)
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
                    from app.rag.vectorstore import get_vector_store_manager
                    collection_count = await _safe_to_thread(
                        f"{route_id}:count",
                        _get_collection_count,
                        target_collection,
                        timeout=min(_route_timeout_seconds(route_name), 1.0),
                        default=500,
                    )
                    route_k = _route_adaptive_k(k, int(collection_count or 500), use_rerank, route_name)
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
        query[:50], collection_routes,
        [route_name for route_name, _, _ in route_specs],
    )
    _log_route_diagnostics(
        query,
        route_specs=[(f"{target_collection}:{route_name}", route_query, route_filter) for target_collection in collection_routes for route_name, route_query, route_filter in route_specs],
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
    """检索相关文档，过滤低相关度结果，可选 Reranker 重排序

    Args:
        depth: Adaptive Depth 配置。为 None 时自动从查询分类推断。
    """
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
        _normalized = normalize_query_text(query)
        _terms = extract_query_terms(_normalized)
        _cat = cat or classify_query(query, _terms)
        stage_ms["classification_ms"] = round((time.perf_counter() - _stage_start) * 1000, 3)

        if depth is None:
            strategy = resolve_retrieval_strategy(_cat)
            depth = strategy.depth
        else:
            strategy = strategy_from_depth(depth)
        retrieval_layer = strategy.layer
        route_type = strategy.route_type
        if k == 5 and depth.k != 5:
            k = depth.k
        logger.info("Retrieval strategy: %s/%s %s → effective_k=%d", retrieval_layer, route_type, depth, k)

        if depth.skip_rerank and use_rerank:
            use_rerank = False
            logger.info("Adaptive Depth: skip_rerank=True, rerank disabled")

        effective_threshold, coarse_k = _resolve_retrieval_policy(query, k, score_threshold, use_rerank, cat=_cat)

        _stage_start = time.perf_counter()
        if precomputed_sub_queries is not None:
            sub_queries = precomputed_sub_queries
            decomposed = len(sub_queries) > 1
        elif depth.skip_decompose:
            sub_queries = [query]
            decomposed = False
        else:
            sub_queries = decompose_sync(query, cat=_cat)
            decomposed = len(sub_queries) > 1
        stage_ms["decompose_ms"] = round((time.perf_counter() - _stage_start) * 1000, 3)
        _stage_start = time.perf_counter()
        if decomposed:
            all_route_results: list[tuple[str, list[tuple[Document, float]]]] = []

            orig_results = _multi_route_search(query, collection_name, coarse_k, filter=filter, cat=_cat, use_rerank=use_rerank, terms=_terms, depth=depth)
            orig_results = dedup_same_section(orig_results, max_per_section=2)
            orig_filtered = [(doc, score) for doc, score in orig_results if score >= effective_threshold]
            all_route_results.append(("original", orig_filtered))

            sub_queries_to_run = [sq for sq in sub_queries if sq != query]
            if sub_queries_to_run:
                def _sub_search(sq):
                    route_allowlist = _COMPACT_SUBQUERY_ROUTES if _cat.is_comparison else None
                    sq_results = _multi_route_search(
                        sq,
                        collection_name,
                        coarse_k,
                        filter=filter,
                        cat=None,
                        use_rerank=use_rerank,
                        depth=depth,
                        route_allowlist=route_allowlist,
                    )
                    sq_results = dedup_same_section(sq_results, max_per_section=2)
                    return [(doc, score) for doc, score in sq_results if score >= effective_threshold]

                sub_max_workers = min(len(sub_queries_to_run), 6)
                with ThreadPoolExecutor(max_workers=sub_max_workers) as pool:
                    sub_futures = {pool.submit(_sub_search, sq): sq for sq in sub_queries_to_run}
                    for future in as_completed(sub_futures):
                        sq = sub_futures[future]
                        try:
                            sq_filtered = future.result()
                            all_route_results.append(("sub", sq_filtered))
                        except Exception as e:
                            logger.warning("Sub-query retrieval failed: %s -> %s", sq[:30], e)
            results = weighted_rrf_merge(all_route_results, weights={"original": 1.5, "sub": 1.0}, cat=_cat)
            logger.info(
                "Decomposed retrieval query=%s sub_queries=%d merged=%d",
                query[:50], len(sub_queries), len(results),
            )
        else:
            results = _multi_route_search(query, collection_name, coarse_k, filter=filter, cat=_cat, use_rerank=use_rerank, terms=_terms, depth=depth)
        stage_ms["route_merge_ms"] = round((time.perf_counter() - _stage_start) * 1000, 3)

        raw_results_count = len(results)
        _max_per = 4 if (_cat.is_exercise or _cat.is_answer) else (3 if (_cat.is_comparison or _cat.is_long) else 2)
        results = dedup_same_section(results, max_per_section=_max_per)
        post_dedup_count = len(results)

        # ── 双路比例保证：防止单路由垄断候选池 ──
        # 知识库扩充后，metadata 路由可能返回大量低相关但含关键词的文档，
        # 在 RRF 融合中挤掉语义检索的真正相关文档。
        # 策略：从 semantic 路由和 BM25 路由各保底取 min_quota 条，
        # 合并去重后追加到 results 尾部（低 RRF 分数，但 reranker 可识别）
        _DUAL_ROUTE_MIN_QUOTA = 5
        if use_rerank and len(results) > _DUAL_ROUTE_MIN_QUOTA * 2:
            semantic_docs = {id(doc): (doc, score) for doc, score in results
                            if "semantic" in str(doc.metadata.get("recall_routes", ""))}
            bm25_docs = {id(doc): (doc, score) for doc, score in results
                        if "keyword_bm25" in str(doc.metadata.get("recall_routes", ""))}
            # 如果某路由在 top 结果中占比过低，从该路由原始结果中补充
            existing_ids = {id(doc) for doc, _ in results}
            for route_label, route_docs in [("semantic", semantic_docs), ("keyword_bm25", bm25_docs)]:
                if len(route_docs) < _DUAL_ROUTE_MIN_QUOTA:
                    # 从原始多路搜索结果中补充该路由的文档
                    route_only = _multi_route_search(
                        query, collection_name, _DUAL_ROUTE_MIN_QUOTA,
                        filter=filter, cat=_cat, use_rerank=False,
                        terms=_terms, depth=depth,
                        route_allowlist={route_label},
                    )
                    for doc, score in route_only:
                        if id(doc) not in existing_ids:
                            doc.metadata["_quota_boost"] = route_label
                            results.append((doc, score * 0.5))  # 降权，让 reranker 决定
                            existing_ids.add(id(doc))
            results.sort(key=lambda item: item[1], reverse=True)

        filtered = [doc for doc, score in results if score >= effective_threshold]
        post_threshold_count = len(filtered)
        logger.info(
            "Retrieval filtering query=%s threshold=%.2f before=%d after=%d",
            query[:50], effective_threshold, len(results), len(filtered),
        )
        _log_final_retrieval_summary("post-threshold", query, filtered)

        _rerank_ms = 0.0
        if not decomposed:
            if use_rerank and filtered:
                _stage_start = time.perf_counter()
                reranked = rerank(query, filtered, top_k=k, lightweight=depth.lightweight_rerank)
                _rerank_ms += (time.perf_counter() - _stage_start) * 1000
                rerank_used = True
                # 双重阈值过滤（相对 + 绝对），兜底保留 top-2
                filtered = _apply_rerank_threshold(reranked, min_keep=2)
                _log_final_retrieval_summary("post-rerank", query, filtered)
            elif not use_rerank:
                filtered = filtered[:k]
                _log_final_retrieval_summary("final-no-rerank", query, filtered)
        else:
            if use_rerank and filtered:
                _stage_start = time.perf_counter()
                reranked = rerank(query, filtered, top_k=k * 2, lightweight=depth.lightweight_rerank)
                _rerank_ms += (time.perf_counter() - _stage_start) * 1000
                rerank_used = True
                # 双重阈值过滤（分解查询），兜底保留 top-2
                filtered = _apply_rerank_threshold(reranked, min_keep=2)
                _log_final_retrieval_summary("post-rerank-decomposed", query, filtered)
            elif not use_rerank:
                max_docs = k * 2
                if len(filtered) > max_docs:
                    filtered = filtered[:max_docs]
                _log_final_retrieval_summary("post-decompose-truncate", query, filtered)
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

        if not depth.skip_hyde and should_trigger_hyde(query, len(filtered), top_rerank_score_for_hyde, _cat):
            _stage_start = time.perf_counter()
            hyde_query = generate_hyde_query(query)
            if hyde_query and hyde_query != query:
                hyde_triggered = True
                try:
                    hyde_terms = extract_query_terms(normalize_query_text(hyde_query))
                    hyde_results = _multi_route_search(
                        hyde_query,
                        collection_name,
                        coarse_k,
                        filter=filter,
                        cat=_cat,
                        use_rerank=use_rerank,
                        terms=hyde_terms,
                        depth=depth,
                    )
                    hyde_results = dedup_same_section(hyde_results, max_per_section=2)
                    hyde_docs = [doc for doc, score in hyde_results if score >= effective_threshold * 0.8]
                    if use_rerank and hyde_docs:
                        hyde_docs = rerank(query, hyde_docs, top_k=k, lightweight=depth.lightweight_rerank)
                        rerank_used = True
                    for doc in hyde_docs:
                        doc.metadata["_hyde_fallback"] = True
                        doc.metadata["_hyde_query"] = hyde_query[:120]
                    existing_keys = {
                        str(doc.metadata.get("content_hash") or f"{doc.metadata.get('source', '') or doc.metadata.get('source_file', '')}:{doc.page_content[:80]}")
                        for doc in filtered
                    }
                    merged_hyde_docs = []
                    for doc in hyde_docs:
                        key = str(doc.metadata.get("content_hash") or f"{doc.metadata.get('source', '') or doc.metadata.get('source_file', '')}:{doc.page_content[:80]}")
                        if key not in existing_keys:
                            merged_hyde_docs.append(doc)
                            existing_keys.add(key)
                    if merged_hyde_docs:
                        filtered = (filtered + merged_hyde_docs)[:max(k, len(filtered))]
                        logger.info(
                            "HyDE fallback added=%d query=%s hyde_query=%s",
                            len(merged_hyde_docs), query[:50], hyde_query[:80],
                        )
                        hyde_added_count = len(merged_hyde_docs)
                        _log_final_retrieval_summary("post-hyde", query, filtered)
                except Exception as e:
                    hyde_error = e.__class__.__name__
                    logger.warning("HyDE fallback retrieval failed: %s", e)
            stage_ms["hyde_ms"] = round((time.perf_counter() - _stage_start) * 1000, 3)
        else:
            stage_ms["hyde_ms"] = 0.0

        before_window = len(filtered)
        if filtered:
            _stage_start = time.perf_counter()
            if collection_name:
                adaptive_wsize = 0 if (depth and depth.depth == "shallow") else (1 if depth and depth.depth == "standard" else 2)
                filtered = sentence_window_expand(filtered, collection_name, window_size=adaptive_wsize)
            else:
                grouped_docs: dict[str, list[Document]] = {}
                for doc in filtered:
                    doc_collection = str(doc.metadata.get("_collection") or "")
                    if doc_collection:
                        grouped_docs.setdefault(doc_collection, []).append(doc)
                if grouped_docs:
                    expanded_docs: list[Document] = []
                    for doc_collection, docs_in_collection in grouped_docs.items():
                        adaptive_wsize = 0 if (depth and depth.depth == "shallow") else (1 if depth and depth.depth == "standard" else 2)
                        expanded_docs.extend(sentence_window_expand(docs_in_collection, doc_collection, window_size=adaptive_wsize))
                    filtered = expanded_docs
            # Negative Sampling: 对 window 展开的噪声 chunk 软降级
            filtered = downgrade_window_noise(filtered, query, is_comparison=bool(_cat and _cat.is_comparison))
            _log_final_retrieval_summary("post-window", query, filtered)
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
                "cache_hits": _cache_hits,
                "cache_misses": _cache_misses,
                "cache_hit_rate": round(100 * _cache_hits / max(_cache_hits + _cache_misses, 1), 1),
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
                **stage_ms,
                "error_type": e.__class__.__name__,
            },
        )
        raise


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
        _normalized = normalize_query_text(query)
        _terms = extract_query_terms(_normalized)
        _cat = cat or await aclassify_query(query, _terms)
        stage_ms["classification_ms"] = round((time.perf_counter() - _stage_start) * 1000, 3)

        if depth is None:
            strategy = resolve_retrieval_strategy(_cat)
            depth = strategy.depth
        else:
            strategy = strategy_from_depth(depth)
        retrieval_layer = strategy.layer
        route_type = strategy.route_type
        if k == 5 and depth.k != 5:
            k = depth.k
        if depth.skip_rerank and use_rerank:
            use_rerank = False

        effective_threshold, coarse_k = _resolve_retrieval_policy(query, k, score_threshold, use_rerank, cat=_cat)

        _stage_start = time.perf_counter()
        if precomputed_sub_queries is not None:
            sub_queries = precomputed_sub_queries
        elif depth.skip_decompose:
            sub_queries = [query]
        else:
            sub_queries = await decompose(query, cat=_cat)
        decomposed = len(sub_queries) > 1
        stage_ms["decompose_ms"] = round((time.perf_counter() - _stage_start) * 1000, 3)

        _stage_start = time.perf_counter()
        if decomposed:
            async def _branch_search(label: str, branch_query: str, branch_cat: QueryCategory | None, branch_terms: list[str] | None, route_allowlist: set[str] | None = None):
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
                return label, [(doc, score) for doc, score in branch_results if score >= effective_threshold]

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
                query[:50], len(sub_queries), len(results),
            )
        else:
            results = await _amulti_route_search(query, collection_name, coarse_k, filter=filter, cat=_cat, use_rerank=use_rerank, terms=_terms, depth=depth)
        stage_ms["route_merge_ms"] = round((time.perf_counter() - _stage_start) * 1000, 3)

        raw_results_count = len(results)
        _max_per = 4 if (_cat.is_exercise or _cat.is_answer) else (3 if (_cat.is_comparison or _cat.is_long) else 2)
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
                filtered = filtered[:k * 2]
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

        if not depth.skip_hyde and should_trigger_hyde(query, len(filtered), top_rerank_score_for_hyde, _cat):
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
                    hyde_docs = [doc for doc, score in hyde_results if score >= effective_threshold * 0.8]
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
                        str(doc.metadata.get("content_hash") or f"{doc.metadata.get('source', '') or doc.metadata.get('source_file', '')}:{doc.page_content[:80]}")
                        for doc in filtered
                    }
                    merged_hyde_docs = []
                    for doc in hyde_docs:
                        key = str(doc.metadata.get("content_hash") or f"{doc.metadata.get('source', '') or doc.metadata.get('source_file', '')}:{doc.page_content[:80]}")
                        if key not in existing_keys:
                            merged_hyde_docs.append(doc)
                            existing_keys.add(key)
                    if merged_hyde_docs:
                        filtered = (filtered + merged_hyde_docs)[:max(k, len(filtered))]
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
                    adaptive_wsize = 0 if (depth and depth.depth == "shallow") else (1 if depth and depth.depth == "standard" else 2)
                    return sentence_window_expand(filtered, collection_name, window_size=adaptive_wsize)
                grouped_docs: dict[str, list[Document]] = {}
                for doc in filtered:
                    doc_collection = str(doc.metadata.get("_collection") or "")
                    if doc_collection:
                        grouped_docs.setdefault(doc_collection, []).append(doc)
                if not grouped_docs:
                    return filtered
                expanded_docs: list[Document] = []
                for doc_collection, docs_in_collection in grouped_docs.items():
                    adaptive_wsize = 0 if (depth and depth.depth == "shallow") else (1 if depth and depth.depth == "standard" else 2)
                    expanded_docs.extend(sentence_window_expand(docs_in_collection, doc_collection, window_size=adaptive_wsize))
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
                "cache_hits": _cache_hits,
                "cache_misses": _cache_misses,
                "cache_hit_rate": round(100 * _cache_hits / max(_cache_hits + _cache_misses, 1), 1),
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


def retrieve_evidence(
    query: str,
    collection_name: str = "",
    k: int = 5,
    score_threshold: float = SCORE_THRESHOLD,
    use_rerank: bool = True,
    filter: dict | None = None,
    student_profile: str = "",
    max_tokens: int = settings.CONTEXT_TOKEN_BUDGET,
    depth: RetrievalDepth | None = None,
) -> "FusedEvidence":
    """结构化检索 API：一步到位返回 FusedEvidence

    相比 retrieve_documents() + build_rag_context() 的两步调用，此 API 直接返回
    结构化的 FusedEvidence，包含：
    - final_context: 最终上下文文本
    - sources: 来源文件列表
    - text_evidences: 结构化文本证据（含 score/section_path/knowledge_points）
    - kg_evidences: KG 证据
    - diversity_score: 来源多样性分数
    - metadata: 去重信息、KG 统计等

    适用于 Agent 需要精细引用来源或做置信度判断的场景。

    Args:
        query: 用户查询
        collection_name: 向量集合名（空=自动路由）
        k: 返回文档数
        score_threshold: 分数阈值
        use_rerank: 是否使用 reranker
        filter: ChromaDB 元数据过滤
        student_profile: 学生画像摘要
        max_tokens: 上下文 token 预算
        depth: Adaptive Depth 配置（None=自动推断）

    Returns:
        FusedEvidence 结构化检索结果
    """
    from app.rag.evidence import FusedEvidence
    from app.rag.fusion import fuse_documents

    # ── Semantic cache lookup ──
    try:
        from app.rag.semantic_cache import get_semantic_cache
        _sc = get_semantic_cache()
        _filter_sig = json.dumps(filter, sort_keys=True) if filter else ""
        _cached_fused, _semantic_cache_sim = _sc.lookup(query, collection_name=collection_name, filter_sig=_filter_sig)
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
        logger.debug("Semantic cache lookup skipped: %s", _sc_err)

    metric_start = time.perf_counter()
    _resolved_depth = depth
    if _resolved_depth is None:
        _terms = extract_query_terms(normalize_query_text(query))
        strategy = resolve_retrieval_strategy(classify_query(query, _terms))
        _resolved_depth = strategy.depth
    else:
        strategy = strategy_from_depth(_resolved_depth)
    retrieval_layer = strategy.layer
    route_type = strategy.route_type
    effective_k = _resolved_depth.k if k == 5 and _resolved_depth.k != 5 else k

    _stage_start = time.perf_counter()
    docs = retrieve_documents(
        query=query,
        collection_name=collection_name,
        k=effective_k,
        score_threshold=score_threshold,
        use_rerank=use_rerank,
        filter=filter,
        depth=_resolved_depth,
    )
    retrieval_latency_ms = round((time.perf_counter() - _stage_start) * 1000, 3)

    kg_category = _infer_kg_category(collection_name, docs)
    _stage_start = time.perf_counter()
    kg_ev = None if _resolved_depth.skip_kg else _query_kg_evidence(query, kg_category)
    kg_latency_ms = round((time.perf_counter() - _stage_start) * 1000, 3) if not _resolved_depth.skip_kg else 0.0

    if not docs:
        if kg_ev:
            fused = fuse_documents(
                [],
                query=query,
                student_profile=student_profile,
                max_tokens=max_tokens,
                kg_evidences=[kg_ev],
                depth=_resolved_depth.depth,
            )
            fused.metadata["query"] = query
            fused.metadata["collection"] = collection_name
            fused.metadata["result_count"] = 0
            fused.metadata["k"] = effective_k
            fused.metadata["use_rerank"] = use_rerank
            fused.metadata["retrieval_depth"] = _resolved_depth.depth
            fused.metadata["retrieval_layer"] = retrieval_layer
            fused.metadata["route_type"] = route_type
            fused.metadata["score_threshold"] = score_threshold
            fused.metadata["kg_skipped"] = False
            fused.metadata["kg_category"] = kg_category
            fused.metadata["source_count"] = len(fused.sources)
            fused.metadata["retrieval_latency_ms"] = retrieval_latency_ms
            fused.metadata["kg_latency_ms"] = kg_latency_ms
            fused.metadata["rerank_latency_ms"] = None
            try:
                from app.rag.verifier import verify_evidence
                verification = verify_evidence(fused, query=query, use_llm=False)
                fused.metadata["evidence_verdict"] = verification.model_dump(mode="json")
            except Exception as e:
                logger.warning("Evidence verification failed: %s", e)
            _emit_evidence_metric(
                query=query,
                collection_name=collection_name,
                start=metric_start,
                fused=fused,
            )
            return fused
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
                "kg_skipped": _resolved_depth.skip_kg,
                "kg_category": kg_category if not _resolved_depth.skip_kg else "",
                "kg_used": False,
                "kg_evidence_count": 0,
                "kg_nodes_count": 0,
                "kg_edges_count": 0,
                "kg_paths_count": 0,
                "retrieval_latency_ms": retrieval_latency_ms,
                "kg_latency_ms": kg_latency_ms,
                "rerank_latency_ms": None,
            },
        )
        try:
            from app.rag.verifier import verify_evidence
            verification = verify_evidence(fused, query=query, use_llm=False)
            fused.metadata["evidence_verdict"] = verification.model_dump(mode="json")
        except Exception as e:
            logger.warning("Evidence verification failed: %s", e)
        _emit_evidence_metric(
            query=query,
            collection_name=collection_name,
            start=metric_start,
            fused=fused,
        )
        return fused

    # KG 结构化证据（Adaptive Depth: shallow 模式跳过）
    # Phase 4: derive category from collection for cross-discipline disambiguation
    kg_evidences = [kg_ev] if kg_ev else None
    if kg_ev:
        logger.debug(
            "KG evidence structured: nodes=%d edges=%d paths=%d category=%s",
            len(kg_ev.nodes), len(kg_ev.edges), len(kg_ev.paths), kg_category,
        )

    fused = fuse_documents(
        docs,
        query=query,
        student_profile=student_profile,
        max_tokens=max_tokens,
        kg_evidences=kg_evidences,
        depth=_resolved_depth.depth,
    )

    # 注入检索元数据
    fused.metadata["query"] = query
    fused.metadata["collection"] = collection_name
    fused.metadata["result_count"] = len(docs)
    fused.metadata["k"] = docs[0].metadata.get("_effective_k", effective_k)
    fused.metadata["use_rerank"] = use_rerank
    fused.metadata["retrieval_depth"] = docs[0].metadata.get("_retrieval_depth", _resolved_depth.depth)
    fused.metadata["retrieval_layer"] = retrieval_layer
    fused.metadata["route_type"] = route_type
    fused.metadata["kg_skipped"] = _resolved_depth.skip_kg
    fused.metadata["kg_category"] = kg_category if not _resolved_depth.skip_kg else ""
    fused.metadata["coarse_k"] = docs[0].metadata.get("_coarse_k")
    fused.metadata["score_threshold"] = score_threshold
    fused.metadata["source_count"] = len(fused.sources)
    fused.metadata["retrieval_latency_ms"] = retrieval_latency_ms
    fused.metadata["kg_latency_ms"] = kg_latency_ms
    fused.metadata["rerank_latency_ms"] = None
    try:
        from app.rag.verifier import verify_evidence
        verification = verify_evidence(fused, query=query, use_llm=False)
        fused.metadata["evidence_verdict"] = verification.model_dump(mode="json")
    except Exception as e:
        logger.warning("Evidence verification failed: %s", e)

    # ── Semantic cache store ──
    try:
        from app.rag.semantic_cache import get_semantic_cache
        _filter_sig = json.dumps(filter, sort_keys=True) if filter else ""
        get_semantic_cache().store(query, fused, collection_name=collection_name, filter_sig=_filter_sig)
    except Exception as _sc_err:
        logger.debug("Semantic cache store skipped: %s", _sc_err)

    _emit_evidence_metric(
        query=query,
        collection_name=collection_name,
        start=metric_start,
        fused=fused,
    )
    return fused


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
) -> "FusedEvidence":
    from app.rag.evidence import FusedEvidence
    from app.rag.fusion import afuse_documents
    from app.rag.verifier import averify_evidence

    try:
        from app.rag.semantic_cache import get_semantic_cache
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

    kg_category = _infer_kg_category(collection_name, docs)
    _stage_start = time.perf_counter()
    kg_ev = None if _resolved_depth.skip_kg else await asyncio.to_thread(_query_kg_evidence, query, kg_category)
    kg_latency_ms = round((time.perf_counter() - _stage_start) * 1000, 3) if not _resolved_depth.skip_kg else 0.0
    kg_degraded = bool((not _resolved_depth.skip_kg) and kg_ev is None)

    if not docs and not kg_ev:
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
                "kg_skipped": _resolved_depth.skip_kg,
                "kg_category": kg_category if not _resolved_depth.skip_kg else "",
                "kg_degraded": kg_degraded,
                "kg_used": False,
                "kg_evidence_count": 0,
                "kg_nodes_count": 0,
                "kg_edges_count": 0,
                "kg_paths_count": 0,
                "retrieval_latency_ms": retrieval_latency_ms,
                "kg_latency_ms": kg_latency_ms,
                "rerank_latency_ms": None,
            },
        )
    else:
        kg_evidences = [kg_ev] if kg_ev else None
        fused = await afuse_documents(
            docs,
            query=query,
            student_profile=student_profile,
            max_tokens=max_tokens,
            kg_evidences=kg_evidences,
            depth=_resolved_depth.depth,
        )
        fused.metadata["query"] = query
        fused.metadata["collection"] = collection_name
        fused.metadata["result_count"] = len(docs)
        fused.metadata["k"] = docs[0].metadata.get("_effective_k", effective_k) if docs else effective_k
        fused.metadata["use_rerank"] = use_rerank
        fused.metadata["retrieval_depth"] = docs[0].metadata.get("_retrieval_depth", _resolved_depth.depth) if docs else _resolved_depth.depth
        fused.metadata["retrieval_layer"] = retrieval_layer
        fused.metadata["route_type"] = route_type
        fused.metadata["kg_skipped"] = _resolved_depth.skip_kg
        fused.metadata["kg_category"] = kg_category if not _resolved_depth.skip_kg else ""
        fused.metadata["kg_degraded"] = kg_degraded
        fused.metadata["coarse_k"] = docs[0].metadata.get("_coarse_k") if docs else None
        fused.metadata["score_threshold"] = score_threshold
        fused.metadata["source_count"] = len(fused.sources)
        fused.metadata["async_decompose_ms"] = async_decompose_ms
        fused.metadata["retrieval_latency_ms"] = retrieval_latency_ms
        fused.metadata["kg_latency_ms"] = kg_latency_ms
        fused.metadata["rerank_latency_ms"] = None

    try:
        verification = await averify_evidence(fused, query=query, use_llm=False)
        fused.metadata["evidence_verdict"] = verification.model_dump(mode="json")
    except Exception as e:
        logger.warning("Async evidence verification failed: %s", e)

    try:
        from app.rag.semantic_cache import get_semantic_cache
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
) -> tuple["FusedEvidence", "VerificationResult"]:
    from app.rag.verifier import Verdict, VerificationResult, averify_evidence

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
            attempt + 1, max_retries, query[:40], result.verdict.value, hints,
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
    "什么是栈和队列", "二叉树的遍历方式", "图的深度优先搜索",
    "哈希表解决冲突的方法", "快速排序的原理", "最短路径Dijkstra算法",
    "最小生成树Prim算法", "B树和B+树的区别",
    # 计算机组成原理
    "Cache的映射方式", "虚拟存储器的工作原理", "指令流水线的三个阶段",
    "中断处理过程", "总线的分类和结构", "浮点数的表示",
    # 操作系统
    "进程死锁的四个必要条件", "银行家算法", "进程和线程的区别",
    "页面置换算法LRU", "信号量PV操作", "内存管理的分页和分段",
    "进程调度算法有哪些", "文件系统的结构",
    # 计算机网络
    "TCP三次握手过程", "TCP和UDP的区别", "拥塞控制的四个算法",
    "OSI七层模型", "IP地址的分类", "DNS的工作原理",
    "HTTP协议的特点", "路由协议OSPF和RIP的区别",
    # 跨学科对比
    "虚拟存储器和Cache的异同", "操作系统调度和网络拥塞控制的共同思想",
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
            succeeded, total, failed, elapsed_ms
        )

    return {
        "total": total,
        "succeeded": succeeded,
        "failed": failed,
        "elapsed_ms": elapsed_ms,
    }