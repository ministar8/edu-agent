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

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from langchain_core.documents import Document

from app.config import settings
from app.rag.metrics import metrics, record_decompose
from app.rag.query_classifier import (
    classify_query,
    QueryCategory,
    RetrievalDepth,
    STANDARD_DEPTH,
    resolve_retrieval_depth,
)
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
)
from app.rag.query_decomposer import decompose_sync
from app.rag.hyde import generate_hyde_query, should_trigger_hyde

logger = logging.getLogger(__name__)

# RRF 融合分数阈值（基于采样校准，非余弦距离）
# RRF(k=20): 排名1≈0.048, 排名5≈0.040（权重 1.0 时）
# 权重 1.5 的路由第 10 名 = 1.5/(20+10) = 0.05 → 刚好过旧阈值
# 0.06 ≈ "至少1路前7" 或 "2路前15"，过滤掉排名#8+的单路噪声
SCORE_THRESHOLD = 0.06

# 查询缓存
_query_cache: dict[str, list[tuple[Document, float]]] = {}
_MAX_CACHE_SIZE = 200
_cache_hits = 0
_cache_misses = 0

# 集合文档数缓存（5 分钟 TTL，避免重复 collection.count() 调用）
_COLLECTION_COUNT_TTL = 300  # seconds
_collection_count_cache: dict[str, tuple[int, float]] = {}

# Reranker 扩展倍数：k=5 时 coarse_k=15（原来 10），给 reranker 更多候选甄别
_RERANK_EXPAND_FACTOR = 3


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
    import json
    filter_key = json.dumps(filter, sort_keys=True, ensure_ascii=False) if filter else ""
    cache_key = f"{collection_name}:{route_name}:{query}:{filter_key}:k={k}"
    global _cache_hits, _cache_misses
    if cache_key in _query_cache:
        _cache_hits += 1
        logger.debug("Cache hit for query: %s (hits=%d misses=%d rate=%.1f%%)",
                     query, _cache_hits, _cache_misses,
                     100 * _cache_hits / max(_cache_hits + _cache_misses, 1))
        return _query_cache[cache_key]
    _cache_misses += 1

    if route_name == "keyword_bm25":
        import jieba
        from app.rag.recall import _BM25_STOP_WORDS
        # cut_for_search 同时保留全词和子词：
        # "进程同步机制" → "进程"、"同步"、"机制"、"进程同步"、"同步机制"
        terms = [w for w in jieba.cut_for_search(query)
                 if w.strip() and w not in _BM25_STOP_WORDS and len(w) >= 2]
        # 限制最多 6 个 term，优先保留复合词（长词更精准）
        if len(terms) > 6:
            terms = sorted(terms, key=len, reverse=True)[:6]
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
        # Partial eviction: delete oldest 25% to avoid cache stampede
        _evict_count = max(1, len(_query_cache) // 4)
        for _key in list(_query_cache.keys())[:_evict_count]:
            del _query_cache[_key]
    _query_cache[cache_key] = results
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
            expand_factor = 4          # 短查询检索命中少，需要更大候选池
        elif cat.is_code or cat.is_long:
            expand_factor = 4
        elif cat.is_answer or cat.is_exercise:
            expand_factor = 3          # 答案/习题适度扩大
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
        expanded = min(k * _RERANK_EXPAND_FACTOR, 40)
    else:
        expanded = min(k * 2, 20)
    return min(expanded, max_k_for_size)


# BM25 路由 k 倍率：BM25 top-N 质量低于 semantic，需要更大 k 补偿覆盖面
_BM25_K_MULTIPLIER = 1.5


def _route_adaptive_k(k: int, collection_count: int, use_rerank: bool, route_name: str = "") -> int:
    """按路由类型和集合大小自适应调整 k

    BM25 路由 k × 1.5（关键词命中覆盖面窄，需要更多候选），
    semantic/metadata 路由保持基础 k（语义检索精度高，小 k 足够）。
    """
    base_k = _adaptive_k(k, collection_count, use_rerank)
    if route_name == "keyword_bm25":
        base_k = _adaptive_k(int(k * _BM25_K_MULTIPLIER), collection_count, use_rerank)
    return base_k


def _multi_route_search(
    query: str,
    collection_name: str,
    k: int,
    filter: dict | None = None,
    cat: QueryCategory | None = None,
    use_rerank: bool = True,
    terms: list[str] | None = None,
    depth: RetrievalDepth | None = None,
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

    max_workers = min(len(all_specs), 6)
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


# ── 公开 API ──────────────────────────────────────────

def retrieve_documents(
    query: str,
    collection_name: str = "",
    k: int = 5,
    score_threshold: float = SCORE_THRESHOLD,
    use_rerank: bool = True,
    filter: dict | None = None,
    depth: RetrievalDepth | None = None,
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
    effective_threshold = score_threshold
    coarse_k = k
    try:
        # 计算一次分类结果，传递给下游避免重复调用
        _normalized = normalize_query_text(query)
        _terms = extract_query_terms(_normalized)
        _cat = classify_query(query, _terms)

        # Adaptive Depth：自动推断深度，覆盖 k
        if depth is None:
            depth = resolve_retrieval_depth(_cat)
        # depth.k 覆盖用户传入的 k（除非用户显式指定了非默认 k=5）
        if k == 5 and depth.k != 5:
            k = depth.k
        logger.info("Adaptive Depth: %s → effective_k=%d", depth, k)

        # Adaptive Depth: shallow 模式跳过 rerank（省 ~500ms）
        if depth.skip_rerank and use_rerank:
            use_rerank = False
            logger.info("Adaptive Depth: skip_rerank=True, rerank disabled")

        effective_threshold, coarse_k = _resolve_retrieval_policy(query, k, score_threshold, use_rerank, cat=_cat)

        # ── 查询分解 ──
        # Adaptive Depth: shallow/code 模式跳过分解
        if depth.skip_decompose:
            sub_queries = [query]
            decomposed = False
        else:
            sub_queries = decompose_sync(query, cat=_cat)
            decomposed = len(sub_queries) > 1
        if decomposed:
            # 多子查询：原始查询权重 1.5，子查询权重 1.0
            # 策略变更：子查询只召回+阈值过滤，不做 per-sub rerank
            # 合并后统一 1 次 rerank，省 2 次 API 调用
            all_route_results: list[tuple[str, list[tuple[Document, float]]]] = []

            # 原始查询召回（权重 1.5）
            orig_results = _multi_route_search(query, collection_name, coarse_k, filter=filter, cat=_cat, use_rerank=use_rerank, terms=_terms, depth=depth)
            orig_results = dedup_same_section(orig_results, max_per_section=2)
            orig_filtered = [(doc, score) for doc, score in orig_results if score >= effective_threshold]
            all_route_results.append(("original", orig_filtered))

            # 子查询召回（权重 1.0，仅召回+阈值过滤，不独立 rerank）
            # Sub-query parallel retrieval with ThreadPoolExecutor
            sub_queries_to_run = [sq for sq in sub_queries if sq != query]
            if sub_queries_to_run:
                def _sub_search(sq):
                    sq_results = _multi_route_search(sq, collection_name, coarse_k, filter=filter, cat=None, use_rerank=use_rerank, depth=depth)
                    sq_results = dedup_same_section(sq_results, max_per_section=2)
                    return [(doc, score) for doc, score in sq_results if score >= effective_threshold]

                sub_max_workers = min(len(sub_queries_to_run), 4)
                with ThreadPoolExecutor(max_workers=sub_max_workers) as pool:
                    sub_futures = {pool.submit(_sub_search, sq): sq for sq in sub_queries_to_run}
                    for future in as_completed(sub_futures):
                        sq = sub_futures[future]
                        try:
                            sq_filtered = future.result()
                            all_route_results.append(("sub", sq_filtered))
                        except Exception as e:
                            logger.warning("Sub-query retrieval failed: %s -> %s", sq[:30], e)
            # 统一加权 RRF 合并
            results = weighted_rrf_merge(all_route_results, weights={"original": 1.5, "sub": 1.0}, cat=_cat)
            logger.info(
                "Decomposed retrieval query=%s sub_queries=%d merged=%d",
                query[:50], len(sub_queries), len(results),
            )
        else:
            results = _multi_route_search(query, collection_name, coarse_k, filter=filter, cat=_cat, use_rerank=use_rerank, terms=_terms, depth=depth)

        # ── 统一后处理管线 ──
        raw_results_count = len(results)
        # dedup 放宽：习题解答可能跨 3-4 个 chunk，对比/长查询需多角度
        _max_per = 4 if (_cat.is_exercise or _cat.is_answer) else (3 if (_cat.is_comparison or _cat.is_long) else 2)
        results = dedup_same_section(results, max_per_section=_max_per)
        post_dedup_count = len(results)

        filtered = [doc for doc, score in results if score >= effective_threshold]
        post_threshold_count = len(filtered)
        logger.info(
            "Retrieval filtering query=%s threshold=%.2f before=%d after=%d",
            query[:50], effective_threshold, len(results), len(filtered),
        )
        _log_final_retrieval_summary("post-threshold", query, filtered)

        if not decomposed:
            # 非分解查询：统一 rerank
            if use_rerank and filtered:
                reranked = rerank(query, filtered, top_k=k)
                # rerank 二次阈值：按 top 分数比例过滤（RERANK_MIN_SCORE=0.3 即 < top*30% 视为低置信度）
                top_score = reranked[0].metadata.get("rerank_score", 0) if reranked else 0
                min_score = top_score * settings.RERANK_MIN_SCORE if top_score > 0 else 0
                high_confidence = [d for d in reranked if d.metadata.get("rerank_score", 0) >= min_score]
                if high_confidence:
                    filtered = high_confidence
                else:
                    filtered = reranked[:max(1, k // 2)]
                    logger.info("Rerank fallback: all scores < %.2f, keeping top-%d", min_score, len(filtered))
                _log_final_retrieval_summary("post-rerank", query, filtered)
            elif not use_rerank:
                filtered = filtered[:k]
                _log_final_retrieval_summary("final-no-rerank", query, filtered)
        else:
            # 分解查询：合并后统一 rerank
            if use_rerank and filtered:
                reranked = rerank(query, filtered, top_k=k * 2)
                top_score = reranked[0].metadata.get("rerank_score", 0) if reranked else 0
                min_score = top_score * settings.RERANK_MIN_SCORE if top_score > 0 else 0
                high_confidence = [d for d in reranked if d.metadata.get("rerank_score", 0) >= min_score]
                if high_confidence:
                    filtered = high_confidence
                else:
                    filtered = reranked[:max(1, k)]
                    logger.info("Rerank fallback (decomposed): all scores < %.2f, keeping top-%d", min_score, len(filtered))
                _log_final_retrieval_summary("post-rerank-decomposed", query, filtered)
            elif not use_rerank:
                max_docs = k * 2
                if len(filtered) > max_docs:
                    filtered = filtered[:max_docs]
                _log_final_retrieval_summary("post-decompose-truncate", query, filtered)
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
            hyde_query = generate_hyde_query(query)
            if hyde_query and hyde_query != query:
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
                        hyde_docs = rerank(query, hyde_docs, top_k=k)
                    for doc in hyde_docs:
                        doc.metadata["_hyde_fallback"] = True
                        doc.metadata["_hyde_query"] = hyde_query[:120]
                    existing_keys = {
                        str(doc.metadata.get("content_hash") or f"{doc.metadata.get('source_file', '')}:{doc.page_content[:80]}")
                        for doc in filtered
                    }
                    merged_hyde_docs = []
                    for doc in hyde_docs:
                        key = str(doc.metadata.get("content_hash") or f"{doc.metadata.get('source_file', '')}:{doc.page_content[:80]}")
                        if key not in existing_keys:
                            merged_hyde_docs.append(doc)
                            existing_keys.add(key)
                    if merged_hyde_docs:
                        filtered = (filtered + merged_hyde_docs)[:max(k, len(filtered))]
                        logger.info(
                            "HyDE fallback added=%d query=%s hyde_query=%s",
                            len(merged_hyde_docs), query[:50], hyde_query[:80],
                        )
                        _log_final_retrieval_summary("post-hyde", query, filtered)
                except Exception as e:
                    logger.warning("HyDE fallback retrieval failed: %s", e)

        before_window = len(filtered)
        if filtered:
            if collection_name:
                filtered = sentence_window_expand(filtered, collection_name, window_size=2)
            else:
                grouped_docs: dict[str, list[Document]] = {}
                for doc in filtered:
                    doc_collection = str(doc.metadata.get("_collection") or "")
                    if doc_collection:
                        grouped_docs.setdefault(doc_collection, []).append(doc)
                if grouped_docs:
                    expanded_docs: list[Document] = []
                    for doc_collection, docs_in_collection in grouped_docs.items():
                        expanded_docs.extend(sentence_window_expand(docs_in_collection, doc_collection, window_size=2))
                    filtered = expanded_docs
            _log_final_retrieval_summary("post-window", query, filtered)
        post_window_count = len(filtered)
        window_added_count = post_window_count - before_window

        for doc in filtered:
            doc.metadata["_retrieval_depth"] = depth.depth
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
    - metadata: CRAG 压缩统计、去重信息等

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

    _resolved_depth = depth
    if _resolved_depth is None:
        _terms = extract_query_terms(normalize_query_text(query))
        _resolved_depth = resolve_retrieval_depth(classify_query(query, _terms))
    effective_k = _resolved_depth.k if k == 5 and _resolved_depth.k != 5 else k

    docs = retrieve_documents(
        query=query,
        collection_name=collection_name,
        k=effective_k,
        score_threshold=score_threshold,
        use_rerank=use_rerank,
        filter=filter,
        depth=_resolved_depth,
    )

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
            },
        )
        try:
            from app.rag.verifier import verify_evidence
            verification = verify_evidence(fused, query=query, use_llm=False)
            fused.metadata["evidence_verdict"] = verification.model_dump(mode="json")
        except Exception as e:
            logger.warning("Evidence verification failed: %s", e)
        return fused

    # KG 结构化证据（Adaptive Depth: shallow 模式跳过）
    # Phase 4: derive category from collection for cross-discipline disambiguation
    kg_evidences = None
    kg_category = ""
    if not _resolved_depth.skip_kg:
        try:
            from app.rag.evidence import kg_evidence_from_query
            # Map collection to KG category for entity disambiguation
            kg_category = collection_name or str(docs[0].metadata.get("_collection") or "")
            kg_ev = kg_evidence_from_query(query, category=kg_category)
            if kg_ev:
                kg_evidences = [kg_ev]
                logger.debug(
                    "KG evidence structured: nodes=%d edges=%d paths=%d category=%s",
                    len(kg_ev.nodes), len(kg_ev.edges), len(kg_ev.paths), kg_category,
                )
        except Exception as e:
            logger.debug("KG evidence query failed during retrieve_evidence: %s", e)

    fused = fuse_documents(
        docs,
        query=query,
        student_profile=student_profile,
        max_tokens=max_tokens,
        kg_evidences=kg_evidences,
    )

    # 注入检索元数据
    fused.metadata["query"] = query
    fused.metadata["collection"] = collection_name
    fused.metadata["k"] = docs[0].metadata.get("_effective_k", effective_k)
    fused.metadata["use_rerank"] = use_rerank
    fused.metadata["retrieval_depth"] = docs[0].metadata.get("_retrieval_depth", _resolved_depth.depth)
    fused.metadata["kg_category"] = kg_category if not _resolved_depth.skip_kg else ""
    fused.metadata["coarse_k"] = docs[0].metadata.get("_coarse_k")
    try:
        from app.rag.verifier import verify_evidence
        verification = verify_evidence(fused, query=query, use_llm=False)
        fused.metadata["evidence_verdict"] = verification.model_dump(mode="json")
    except Exception as e:
        logger.warning("Evidence verification failed: %s", e)

    return fused


def retrieve_evidence_with_retry(
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
    """带质量校验与重试的结构化检索

    在 retrieve_evidence 基础上增加 EvidenceVerifier 校验：
    - PASS → 直接返回
    - SOFT_FAIL / HARD_FAIL → 根据 retry_hints 调整参数重试

    Args:
        与 retrieve_evidence 相同，额外：
        depth: Adaptive Depth 配置（None=自动推断）
        max_retries: 最大重试次数（0=不重试，只校验）
        use_llm_verify: 是否启用 LLM 相关性校验（有 token 成本）

    Returns:
        (FusedEvidence, VerificationResult) 元组
    """
    from app.rag.verifier import Verdict, VerificationResult, verify_evidence

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

    fused = retrieve_evidence(**current_kwargs)
    result = verify_evidence(fused, query=query, use_llm=use_llm_verify)
    fused.metadata["evidence_verdict"] = result.model_dump(mode="json")

    for attempt in range(max_retries):
        if result.verdict == Verdict.PASS:
            break

        # 根据 retry_hints 调整参数
        hints = result.retry_hints
        if not hints:
            logger.info("Retry %d: no hints available, stopping", attempt + 1)
            break

        if "k" in hints:
            current_kwargs["k"] = hints["k"]
            # 重试时升级 depth：shallow → standard，启用完整管线
            if current_kwargs.get("depth") and current_kwargs["depth"].depth == "shallow":
                current_kwargs["depth"] = STANDARD_DEPTH
                logger.info("Retry %d: depth upgraded shallow → standard", attempt + 1)
        if "score_threshold" in hints:
            current_kwargs["score_threshold"] = hints["score_threshold"]
        if "max_tokens" in hints:
            current_kwargs["max_tokens"] = hints["max_tokens"]
        if "use_rerank" in hints:
            current_kwargs["use_rerank"] = hints["use_rerank"]

        logger.info(
            "Retry %d/%d for query=%s verdict=%s hints=%s",
            attempt + 1, max_retries, query[:40], result.verdict.value, hints,
        )

        fused = retrieve_evidence(**current_kwargs)
        result = verify_evidence(fused, query=query, use_llm=use_llm_verify)
        fused.metadata["evidence_verdict"] = result.model_dump(mode="json")

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