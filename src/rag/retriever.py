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
from collections.abc import Callable
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
    ALL_ROUTES,
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
# 数值来自 `settings.RETRIEVAL_SCORE_THRESHOLD`（可经 .env 覆盖，backlog #14）。
# 保留模块级别名是为了不动下面 4 处函数签名的默认值。
SCORE_THRESHOLD = settings.RETRIEVAL_SCORE_THRESHOLD

# 查询缓存（有界 + TTL，线程安全；命中计数由缓存自带）
_MAX_CACHE_SIZE = 200
_CACHE_TTL = 300  # 5 minutes TTL
_query_cache: BoundedCache[str, list[tuple[Document, float]]] = BoundedCache(
    max_size=_MAX_CACHE_SIZE, ttl=_CACHE_TTL, name="retriever_query"
)

# 语义检索的过采样倍数。
#
# Chroma 是**近似**索引，top-k 边界会抖：实测同一查询、同一索引，
# 偶尔少返回一个本该进 top-k 的候选（约 10 次 1 次），而且会**传导到最终结果** ——
# 表现为"同一个问题返回不同证据"。
#
# 多取几倍候选、再按 (分数, 内容键) 确定性排序取前 k，让边界抖动不再影响最终集合，
# 顺带把被漏掉的候选捞回来。HNSW 检索是 ~O(log n)，多取 3 倍的代价可忽略。
_SEMANTIC_OVERSAMPLE = 3


def _copy_results(results: list[tuple[Document, float]]) -> list[tuple[Document, float]]:
    """缓存命中时返回浅拷贝：新 list + 每篇 Document 复制一份 metadata。

    下游会往 Document.metadata 写东西（`_collection`、窗口展开、噪声降级等），
    直接返回缓存里的原对象会让这些写入污染缓存。
    """
    return [
        (Document(page_content=d.page_content, metadata=dict(d.metadata)), s) for d, s in results
    ]


def cache_stats() -> dict[str, int | float]:
    """查询缓存的命中统计（并发下近似，仅用于观测）。

    键名与 `SemanticCache.stats()` 对齐（`hits` / `misses` / `hit_rate`），
    这样 `/api/metrics` 能把多个缓存并排展示而不用做字段映射。
    """
    stats = _query_cache.stats
    return {
        "hits": stats["hits"],
        "misses": stats["misses"],
        "hit_rate": stats["hit_rate"],
    }


def _cache_stats_fields() -> dict[str, int | float]:
    """指标日志用：给 `cache_stats()` 的键加 `cache_` 前缀。

    **为什么保留这层**：`cache_hits` / `cache_misses` / `cache_hit_rate`
    已经写进历史指标日志，改名会让新旧数据对不上（无声破坏已有看板）。
    所以对外用对齐后的键名，日志沿用旧键名 —— 由这里保证两者同源。
    """
    return {f"cache_{k}": v for k, v in cache_stats().items()}


# Reranker 扩展倍数：知识库扩充后需要更大候选池
# k=5 时 coarse_k=25，k=8 时 coarse_k=40
_RERANK_EXPAND_FACTOR = settings.RERANK_EXPAND_FACTOR


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

        # 走 manager 的检索方法而**不是**直接调 store —— 前者持有 `_rw_lock` 读锁。
        # 直接调 store 会绕过读锁，与 `add_documents` 的写锁形不成互斥：
        # Chroma 的 Rust 后端在 add 返回后可能仍在落盘 HNSW 段，
        # 此时并发的查询会打开一个半成品段，抛
        # `Error creating hnsw segment reader: Nothing found on disk`。
        # 症状是间歇性的（取决于查询是否与写入重叠）、命中的集合随机、
        # 且**就绪探测能过而首个真实查询失败**（探测走的是加锁路径）。
        #
        # **过采样 + 确定性截断**：Chroma 是近似索引，top-k 边界会抖 ——
        # 实测同一查询偶尔少返回一个本该进 top-k 的候选（约 10 次 1 次），
        # 且会传导到最终结果，表现为"同一个问题返回不同证据"。
        # 多取 `_SEMANTIC_OVERSAMPLE` 倍候选、再按 (分数, 内容键) 确定性排序取前 k，
        # 让边界抖动不再影响最终集合 —— 顺带把被漏掉的候选捞回来（提升召回）。
        # 次级键用内容键而非原始顺序：后者依赖 Chroma 的返回次序，本身就不确定。
        oversampled = get_vector_store_manager().similarity_search_with_score(
            collection_name, query, k=k * _SEMANTIC_OVERSAMPLE, filter=filter
        )
        results = sorted(oversampled, key=lambda pair: (-pair[1], _content_key(pair[0])))[:k]

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

    _BASELINE_WEIGHT = settings.RRF_BASELINE_WEIGHT  # semantic default 权重作为基准
    # 路由名单来自 `recall.ALL_ROUTES`（单一真源）——
    # 这里曾内联抄了一份 13 个路由名的元组，与 `recall.py` 的权重表各自维护。
    # 抄漏/抄多**都不会报错**，只会让 `_max_w` 静默偏掉、进而让阈值偏掉。
    _active_routes = ALL_ROUTES
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
            "source_count": len(getattr(fused, "sources", []) or []),
            "context_chars": len(final_context),
            "context_tokens": getattr(fused, "used_token_budget", 0),
            "retrieval_latency_ms": meta.get("retrieval_latency_ms", None),
            "rerank_latency_ms": meta.get("rerank_latency_ms", None),
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


# ── 阶段进度回调 ──────────────────────────────────────────────
# 检索链是**纯计算层**，刻意不知道 SSE / StreamWriter 的存在：
# 这里只暴露一个可选回调，由 `agents/tools.py` 注入（那里才 import CustomData 并写 stream）。
# 好处：UI 关注点留在上层，`rag/` 仍可独立测试与复用 ——
# 门禁、离线评测、缓存预热都不传回调，走 no-op 分支。
StageSink = Callable[[str], None]


def _emit_stage(on_stage: StageSink | None, stage: str) -> None:
    """上报「即将进入某检索阶段」。

    **回调抛错绝不能影响检索结果** —— 进度是锦上添花，失败就跳过。
    所以这里吞异常只记 debug（有日志，不是静默 pass）。
    """
    if on_stage is None:
        return
    try:
        on_stage(stage)
    except Exception:
        logger.debug("阶段进度回调失败（已忽略）: stage=%s", stage, exc_info=True)


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
    on_stage: StageSink | None = None,
) -> list[Document]:
    """同步检索入口：**委托给 aretrieve_documents**，不再维护第二份流水线逻辑。

    这里原本有一份 448 行的同步副本，与 ``aretrieve_documents`` 逐段对应（"双胞胎"）。
    实测两者当前行为一致（15 条 query 的条数 / 集合 / 顺序完全相同），但双份实现迟早漂移，
    且它唯一的调用方是 ``warmup_query_cache``（入库后的缓存预热）——
    为这一个场景维护 448 行重复逻辑不划算，故改为委托。

    ⚠️ 不能在**已运行的事件循环**里调用（``asyncio.run`` 会抛 RuntimeError）。
    这与它唯一的使用场景（同步 CLI 入库后预热）不冲突；
    异步上下文请直接 ``await aretrieve_documents(...)``。

    ``on_stage`` 必须与 ``aretrieve_documents`` **保持签名一致**（有测试钉住），
    但预热场景不传，实际永远是 None。
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
            on_stage,
        )
    )


# ── aretrieve_documents 的阶段函数 ────────────────────────────
#
# 这组函数把原本 428 行的单体编排按**已有的阶段边界**拆开。每个函数都有明确的
# 输入输出，因此可以单独测试 —— 这正是此前覆盖率上不去的结构性原因：
# 单体函数让其中的纯逻辑无法被单独调用，覆盖率有结构性上限。
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


async def _stage_dedup_and_threshold(
    results: list[tuple[Document, float]],
    query: str,
    cat: QueryCategory,
    effective_threshold: float,
) -> tuple[list[Document], int, int]:
    """阶段 5+6：同章节去重 → 分数阈值过滤。

    去重的每章节保留数按查询类别浮动：练习/答案类放宽到 4（同一节里常有多道题），
    对比/长查询 3，其余 2。

    Returns:
        ``(过阈值文档, 去重后条数, 过阈值条数)`` —— 两个条数供调用方写指标，
        去重后的完整结果不向下游传递（下游只消费过阈值的文档）。
    """
    max_per_section = (
        4
        if (cat.is_exercise or cat.is_answer)
        else (3 if (cat.is_comparison or cat.is_long) else 2)
    )
    deduped = await _safe_to_thread(
        "async_section_dedup",
        dedup_same_section,
        results,
        timeout=min(float(getattr(settings, "TOOL_CALL_TIMEOUT", 30) or 30), 3.0),
        default=results,
        max_per_section=max_per_section,
    )

    filtered = [doc for doc, score in deduped if score >= effective_threshold]
    _log_final_retrieval_summary("async-post-threshold", query, filtered)
    return filtered, len(deduped), len(filtered)


@dataclass(frozen=True)
class _RecallRequest:
    """阶段 4 的全部输入。

    参数有 11 个，且明显分成两类（检索配置 / 查询状态）—— 直接铺成位置参数
    在调用处极易错位，故打包成一个不可变请求对象，顺带把契约写清楚。
    """

    query: str
    collection_name: str
    coarse_k: int
    filter: dict | None
    cat: QueryCategory
    terms: list[str]
    use_rerank: bool
    depth: RetrievalDepth
    sub_queries: list[str]
    decomposed: bool
    effective_threshold: float


async def _stage_recall_and_merge(req: _RecallRequest) -> list[tuple[Document, float]]:
    """阶段 4：多路召回 + 跨分支融合。

    两条路径：

    - **单路**：直接做一次多路召回（`_amulti_route_search`）。
    - **分解**：原查询与各子查询**并发**召回，每路先各自去重（每章节保留 2 条）
      并过阈值，再按 ``original=1.5 / sub=1.0`` 加权做 RRF 融合。
      对比类查询只允许子查询走精简路由集（`_COMPACT_SUBQUERY_ROUTES`），
      避免子查询把召回面摊得过宽。

    分支异常**只记 warning 不中断**：少一路召回远好过整条检索失败。

    Returns:
        召回结果（已融合，**尚未**做全局去重与阈值过滤）。
    """
    if not req.decomposed:
        return await _amulti_route_search(
            req.query,
            req.collection_name,
            req.coarse_k,
            filter=req.filter,
            cat=req.cat,
            use_rerank=req.use_rerank,
            terms=req.terms,
            depth=req.depth,
        )

    async def _branch_search(
        label: str,
        branch_query: str,
        branch_cat: QueryCategory | None,
        branch_terms: list[str] | None,
        route_allowlist: set[str] | None = None,
    ):
        branch_results = await _amulti_route_search(
            branch_query,
            req.collection_name,
            req.coarse_k,
            filter=req.filter,
            cat=branch_cat,
            use_rerank=req.use_rerank,
            terms=branch_terms,
            depth=req.depth,
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
            (doc, score) for doc, score in branch_results if score >= req.effective_threshold
        ]

    tasks = [_branch_search("original", req.query, req.cat, req.terms)]
    route_allowlist = _COMPACT_SUBQUERY_ROUTES if req.cat.is_comparison else None
    for sq in [sq for sq in req.sub_queries if sq != req.query]:
        tasks.append(_branch_search("sub", sq, None, None, route_allowlist=route_allowlist))
    gathered = await asyncio.gather(*tasks, return_exceptions=True)

    all_route_results: list[tuple[str, list[tuple[Document, float]]]] = []
    for item in gathered:
        if isinstance(item, Exception):
            logger.warning("Async sub-query branch failed: %s", item)
            continue
        all_route_results.append(item)

    merged = await _safe_to_thread(
        "async_weighted_rrf_merge",
        weighted_rrf_merge,
        all_route_results,
        {"original": 1.5, "sub": 1.0},
        timeout=min(float(getattr(settings, "TOOL_CALL_TIMEOUT", 30) or 30), 5.0),
        default=[],
        cat=req.cat,
    )
    merged = merged or []
    logger.info(
        "Async decomposed retrieval query=%s sub_queries=%d merged=%d",
        req.query[:50],
        len(req.sub_queries),
        len(merged),
    )
    return merged


async def _stage_rerank(
    filtered: list[Document],
    query: str,
    k: int,
    use_rerank: bool,
    decomposed: bool,
) -> tuple[list[Document], bool, float]:
    """阶段 7：重排（可选）+ 重排后的双重阈值过滤。

    分解路径的候选池是单路的两倍（``top_k=k*2``）：子查询合并后候选更多，
    仍按 k 截断会把原查询的证据挤掉。未启用重排时同样按这个倍数截断
    （``filtered[:k]`` vs ``filtered[:k*2]``），保持两条路径口径一致。

    Returns:
        ``(重排后的文档, 是否真的执行了重排, 重排耗时毫秒)``。
        耗时由调用方写进 ``stage_ms`` —— 指标的所有权留在编排层。
    """
    if not (use_rerank and filtered):
        # 未启用重排：仍要截断。注意这里**不**记录耗时（原本就没有计时窗口）
        if not use_rerank:
            return filtered[: k * 2 if decomposed else k], False, 0.0
        return filtered, False, 0.0

    top_k = k * 2 if decomposed else k
    log_label = "async-post-rerank-decomposed" if decomposed else "async-post-rerank"
    started = time.perf_counter()
    reranked = await _safe_to_thread(
        f"async_rerank{'_decomposed' if decomposed else ''}",
        rerank,
        query,
        filtered,
        timeout=float(getattr(settings, "RERANK_TIMEOUT", 30) or 30),
        # 兜底截断用 `top_k` 而不是 `k`，与候选池口径一致（backlog #33）。
        # 原实现两条分支都写 `filtered[:k]`，但候选池是 `top_k = k*2 if decomposed else k`：
        # 非分解路径 `top_k == k`，恰好等价；**分解路径重排失败时只兜住一半候选**。
        # 重排失败本就是降级场景，此时再把候选砍半，等于在降级上再降一级。
        default=filtered[:top_k],
        top_k=top_k,
    )
    elapsed_ms = (time.perf_counter() - started) * 1000

    # 双重阈值过滤，兜底保留 top-2
    out = _apply_rerank_threshold(reranked, min_keep=2)
    _log_final_retrieval_summary(log_label, query, out)
    return out, True, elapsed_ms


def _content_key(doc: Document) -> str:
    """HyDE 追加时的去重键：优先内容哈希，缺失时退回「来源 + 正文前 80 字」。

    原实现在同一段里内联了两次这个表达式，抽出来避免两处走样。
    """
    return str(
        doc.metadata.get("content_hash")
        or f"{doc.metadata.get('source', '') or doc.metadata.get('source_file', '')}:"
        f"{doc.page_content[:80]}"
    )


@dataclass(frozen=True)
class _HydeOutcome:
    """HyDE 阶段的产出。

    `rerank_used` 也在返回值里：HyDE 召回后若走了重排，会把整条链路的
    "用过重排"标记翻成 True —— 这是原实现的行为。拆开后显式返回，
    避免调用方漏掉这次翻转（漏了会让指标里的 rerank_used 少记）。
    """

    docs: list[Document]
    triggered: bool
    added_count: int
    error: str
    rerank_used: bool
    elapsed_ms: float


async def _stage_hyde(
    filtered: list[Document],
    *,
    query: str,
    collection_name: str,
    coarse_k: int,
    filter: dict | None,
    cat: QueryCategory,
    use_rerank: bool,
    depth: RetrievalDepth,
    k: int,
    effective_threshold: float,
    rerank_used: bool,
) -> _HydeOutcome:
    """阶段 8：HyDE 兜底召回。

    只在"结果偏少或最高重排分偏低"时触发（`should_trigger_hyde`）。
    触发后用 LLM 生成假设性答案再召回一次，把**新**文档追加到现有结果之后。

    三处刻意的设计：

    - 阈值放宽到 ``effective_threshold * 0.8``：HyDE 是兜底手段，
      用同一把尺子会把它的召回几乎全部滤掉；
    - 追加时按内容键去重，已存在的文档不重复计入；
    - 整段包在 try 里，**任何异常只记 `hyde_error` 不抛出** ——
      兜底机制失败不该影响已经拿到的正常结果。

    Returns:
        `_HydeOutcome`。未触发时 `elapsed_ms` 为 0（原实现不记录这段耗时）。
    """
    top_rerank_score_for_hyde = 0.0
    rerank_scores_for_hyde = [
        float(doc.metadata.get("rerank_score") or 0.0)
        for doc in filtered
        if doc.metadata.get("rerank_score") is not None
    ]
    if rerank_scores_for_hyde:
        top_rerank_score_for_hyde = max(rerank_scores_for_hyde)

    if depth.skip_hyde or not should_trigger_hyde(
        query, len(filtered), top_rerank_score_for_hyde, cat
    ):
        return _HydeOutcome(filtered, False, 0, "", rerank_used, 0.0)

    triggered = False
    added_count = 0
    error = ""
    started = time.perf_counter()
    hyde_query = await _safe_to_thread(
        "async_hyde_generate",
        generate_hyde_query,
        query,
        timeout=min(float(getattr(settings, "LLM_TIMEOUT", 60) or 60), 10.0),
        default="",
    )
    if hyde_query and hyde_query != query:
        triggered = True
        try:
            hyde_terms = extract_query_terms(normalize_query_text(hyde_query))
            hyde_results = await _amulti_route_search(
                hyde_query,
                collection_name,
                coarse_k,
                filter=filter,
                cat=cat,
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

            existing_keys = {_content_key(doc) for doc in filtered}
            merged_hyde_docs = []
            for doc in hyde_docs:
                key = _content_key(doc)
                if key not in existing_keys:
                    merged_hyde_docs.append(doc)
                    existing_keys.add(key)
            if merged_hyde_docs:
                filtered = (filtered + merged_hyde_docs)[: max(k, len(filtered))]
                added_count = len(merged_hyde_docs)
                _log_final_retrieval_summary("async-post-hyde", query, filtered)
        except Exception as e:
            error = e.__class__.__name__
            logger.warning("Async HyDE fallback retrieval failed: %s", e)

    return _HydeOutcome(
        filtered,
        triggered,
        added_count,
        error,
        rerank_used,
        round((time.perf_counter() - started) * 1000, 3),
    )


@dataclass(frozen=True)
class _WindowOutcome:
    docs: list[Document]
    elapsed_ms: float


async def _stage_expand_windows(
    filtered: list[Document],
    *,
    query: str,
    collection_name: str,
    cat: QueryCategory,
    depth: RetrievalDepth,
) -> _WindowOutcome:
    """阶段 9：句子窗口展开 + 噪声软降级。

    窗口大小按检索深度自适应：shallow=0（不展开）、standard=1、deep=2。

    两种展开方式：

    - 指定了单一集合 → 整个列表直接交给 `sentence_window_expand`；
    - 未指定集合（跨集合召回）→ 先按 `_collection` 分组**逐集合**展开。
      窗口要在各自集合内取相邻 chunk，跨集合混在一起会取到别的集合的邻居。

    展开后再做一次负采样软降级（`downgrade_window_noise`）：被窗口带进来的
    噪声 chunk 不该与直接命中的证据同等对待。
    """
    if not filtered:
        return _WindowOutcome(filtered, 0.0)

    def _adaptive_window_size() -> int:
        if depth and depth.depth == "shallow":
            return 0
        return 1 if (depth and depth.depth == "standard") else 2

    def _expand_windows():
        if collection_name:
            return sentence_window_expand(
                filtered, collection_name, window_size=_adaptive_window_size()
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
            expanded_docs.extend(
                sentence_window_expand(
                    docs_in_collection, doc_collection, window_size=_adaptive_window_size()
                )
            )
        return expanded_docs

    started = time.perf_counter()
    expanded = await _safe_to_thread(
        "async_window_expand",
        _expand_windows,
        timeout=min(float(getattr(settings, "TOOL_CALL_TIMEOUT", 30) or 30), 5.0),
        default=filtered,
    )
    # Negative Sampling: 对 window 展开的噪声 chunk 软降级
    expanded = downgrade_window_noise(
        expanded, query, is_comparison=bool(cat and cat.is_comparison)
    )
    _log_final_retrieval_summary("async-post-window", query, expanded)
    return _WindowOutcome(expanded, round((time.perf_counter() - started) * 1000, 3))


@dataclass(frozen=True)
class _RetrievalCounters:
    """一次检索各阶段的计数，供收尾写指标。"""

    raw_results: int
    after_dedup: int
    after_threshold: int
    after_rerank: int
    after_window: int
    window_added: int


@dataclass(frozen=True)
class _RetrievalContext:
    """收尾阶段需要的检索上下文（调用方请求 + 实际采用的策略）。

    参数很多，但都是"这一次检索的事实"—— 打包成一个不可变对象，
    避免 19 个关键字参数在调用处错位。
    """

    query: str
    collection_name: str
    k: int
    coarse_k: int
    effective_threshold: float
    depth: RetrievalDepth | None
    retrieval_layer: str
    route_type: str
    cat: QueryCategory
    decomposed: bool
    sub_queries: list[str]
    use_rerank: bool
    rerank_used: bool
    hyde_triggered: bool
    hyde_added_count: int
    hyde_error: str
    counters: _RetrievalCounters


def _finalize_retrieval(
    filtered: list[Document],
    *,
    ctx: _RetrievalContext,
    started_at: float,
    stage_ms: dict[str, float],
) -> list[Document]:
    """阶段 10：给证据打溯源标记，并写出检索摘要指标。

    溯源标记（`_retrieval_depth` / `_retrieval_layer` / `_route_type` /
    `_effective_k` / `_coarse_k`）会随证据一起流向生成阶段，
    用于回答"这条证据是怎么来的"。

    指标里刻意同时保留**各阶段计数**（before_threshold / after_dedup /
    after_threshold / after_rerank / after_window）—— 只看最终条数无法判断
    是召回不足还是被某一层过滤掉了。
    """
    for doc in filtered:
        doc.metadata["_retrieval_depth"] = ctx.depth.depth if ctx.depth else ""
        doc.metadata["_retrieval_layer"] = ctx.retrieval_layer
        doc.metadata["_route_type"] = ctx.route_type
        doc.metadata["_effective_k"] = ctx.k
        doc.metadata["_coarse_k"] = ctx.coarse_k

    window_expanded_count = sum(1 for doc in filtered if doc.metadata.get("_window_expanded"))
    context_chars = sum(len(doc.page_content or "") for doc in filtered)
    role_counts = {
        "detail": sum(1 for doc in filtered if doc.metadata.get("section.chunk_role") == "detail"),
    }
    rerank_scores = [
        float(doc.metadata.get("rerank_score") or 0.0)
        for doc in filtered
        if doc.metadata.get("rerank_score") is not None
    ]
    top_rerank_score = rerank_scores[0] if rerank_scores else 0.0
    avg_rerank_score = round(sum(rerank_scores) / len(rerank_scores), 6) if rerank_scores else 0.0

    metrics.emit_retrieve_summary(
        query=ctx.query,
        collection=ctx.collection_name,
        duration_ms=round((time.perf_counter() - started_at) * 1000, 3),
        values={
            "k": ctx.k,
            "coarse_k": ctx.coarse_k,
            "threshold": ctx.effective_threshold,
            "retrieval_depth": ctx.depth.depth if ctx.depth else "",
            "retrieval_layer": ctx.retrieval_layer,
            "route_type": ctx.route_type,
            "classifier_source": getattr(ctx.cat, "source", ""),
            "decomposed": ctx.decomposed,
            "sub_query_count": len(ctx.sub_queries),
            "use_rerank": ctx.use_rerank,
            "rerank_used": ctx.rerank_used,
            "hyde_triggered": ctx.hyde_triggered,
            "hyde_added_count": ctx.hyde_added_count,
            "hyde_error": ctx.hyde_error,
            "skip_bm25": ctx.depth.skip_bm25 if ctx.depth else False,
            "skip_metadata_routes": ctx.depth.skip_metadata_routes if ctx.depth else False,
            "before_threshold": ctx.counters.raw_results,
            "after_section_dedup": ctx.counters.after_dedup,
            "after_threshold": ctx.counters.after_threshold,
            "after_rerank": ctx.counters.after_rerank,
            "after_window": ctx.counters.after_window,
            "window_added": ctx.counters.window_added,
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
    on_stage: StageSink | None = None,
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
        _emit_stage(on_stage, "classify")
        _stage_start = time.perf_counter()
        _terms, _cat = await _stage_classify_query(query, cat)
        stage_ms["classification_ms"] = round((time.perf_counter() - _stage_start) * 1000, 3)

        _emit_stage(on_stage, "plan")
        _plan = _stage_resolve_plan(query, _cat, k, score_threshold, use_rerank, depth)
        depth = _plan.depth
        k = _plan.k
        use_rerank = _plan.use_rerank
        effective_threshold = _plan.effective_threshold
        coarse_k = _plan.coarse_k
        retrieval_layer = _plan.retrieval_layer
        route_type = _plan.route_type

        _emit_stage(on_stage, "decompose")
        _stage_start = time.perf_counter()
        sub_queries, decomposed = await _stage_decompose_query(
            query, _cat, depth, precomputed_sub_queries
        )
        stage_ms["decompose_ms"] = round((time.perf_counter() - _stage_start) * 1000, 3)

        _emit_stage(on_stage, "recall")
        _stage_start = time.perf_counter()
        results = await _stage_recall_and_merge(
            _RecallRequest(
                query=query,
                collection_name=collection_name,
                coarse_k=coarse_k,
                filter=filter,
                cat=_cat,
                terms=_terms,
                use_rerank=use_rerank,
                depth=depth,
                sub_queries=sub_queries,
                decomposed=decomposed,
                effective_threshold=effective_threshold,
            )
        )
        stage_ms["route_merge_ms"] = round((time.perf_counter() - _stage_start) * 1000, 3)

        raw_results_count = len(results)
        _emit_stage(on_stage, "dedup")
        filtered, post_dedup_count, post_threshold_count = await _stage_dedup_and_threshold(
            results, query, _cat, effective_threshold
        )

        _emit_stage(on_stage, "rerank")
        filtered, rerank_used, _rerank_ms = await _stage_rerank(
            filtered, query, k, use_rerank, decomposed
        )
        stage_ms["rerank_ms"] = round(_rerank_ms, 3)
        post_rerank_count = len(filtered)

        _emit_stage(on_stage, "hyde")
        _hyde = await _stage_hyde(
            filtered,
            query=query,
            collection_name=collection_name,
            coarse_k=coarse_k,
            filter=filter,
            cat=_cat,
            use_rerank=use_rerank,
            depth=depth,
            k=k,
            effective_threshold=effective_threshold,
            rerank_used=rerank_used,
        )
        filtered = _hyde.docs
        hyde_triggered = _hyde.triggered
        hyde_added_count = _hyde.added_count
        hyde_error = _hyde.error
        rerank_used = _hyde.rerank_used
        stage_ms["hyde_ms"] = _hyde.elapsed_ms

        before_window = len(filtered)
        _emit_stage(on_stage, "expand")
        _window = await _stage_expand_windows(
            filtered, query=query, collection_name=collection_name, cat=_cat, depth=depth
        )
        filtered = _window.docs
        stage_ms["window_ms"] = _window.elapsed_ms
        post_window_count = len(filtered)
        window_added_count = post_window_count - before_window

        return _finalize_retrieval(
            filtered,
            ctx=_RetrievalContext(
                query=query,
                collection_name=collection_name,
                k=k,
                coarse_k=coarse_k,
                effective_threshold=effective_threshold,
                depth=depth,
                retrieval_layer=retrieval_layer,
                route_type=route_type,
                cat=_cat,
                decomposed=decomposed,
                sub_queries=sub_queries,
                use_rerank=use_rerank,
                rerank_used=rerank_used,
                hyde_triggered=hyde_triggered,
                hyde_added_count=hyde_added_count,
                hyde_error=hyde_error,
                counters=_RetrievalCounters(
                    raw_results=raw_results_count,
                    after_dedup=post_dedup_count,
                    after_threshold=post_threshold_count,
                    after_rerank=post_rerank_count,
                    after_window=post_window_count,
                    window_added=window_added_count,
                ),
            ),
            started_at=start,
            stage_ms=stage_ms,
        )
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
    max_tokens: int = settings.CONTEXT_TOKEN_BUDGET,
    depth: RetrievalDepth | None = None,
    on_stage: StageSink | None = None,
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
        on_stage=on_stage,
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
    max_tokens: int = settings.CONTEXT_TOKEN_BUDGET,
    depth: RetrievalDepth | None = None,
    on_stage: StageSink | None = None,
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
        "max_tokens": max_tokens,
        "depth": depth,
        "on_stage": on_stage,
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
