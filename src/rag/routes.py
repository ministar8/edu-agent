"""多路召回（论文架构图「候选生成」对应模块）。

职责：单条路由检索（语义 / BM25 / 元数据）→ 并发多路召回。
不负责：分类、分解、重排、融合、证据出包 —— 见 pipeline / 各专职模块。
"""

from __future__ import annotations

import asyncio
import json
import logging

from langchain_core.documents import Document

from core.cache import BoundedCache
from core.settings import settings
from rag.bm25 import bm25_search
from rag.postprocess import merge_route_results
from rag.query_classifier import QueryCategory, RetrievalDepth
from rag.rag_utils import content_key
from rag.recall import (
    build_metadata_routes,
    build_recall_queries,
    resolve_collection_routes,
)

logger = logging.getLogger(__name__)

# BM25 路由 k 倍率：知识库扩充后 BM25 命中量已增加，降低倍率避免噪声淹没语义信号
_BM25_K_MULTIPLIER = 1.2
_COMPACT_SUBQUERY_ROUTES = {"keyword_bm25", "concept_meta", "structured_meta", "section_meta"}

# 语义检索过采样倍数：Chroma 近似索引 top-k 边界会抖，多取再确定性截断
_SEMANTIC_OVERSAMPLE = 3


# 查询缓存（有界 + TTL，线程安全；命中计数由缓存自带）——
# 供 `_raw_search` 与门面 `cache_stats` 共用。
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


def cache_stats() -> dict[str, int | float]:
    """查询缓存的命中统计（并发下近似，仅用于观测）。"""
    stats = _query_cache.stats
    return {
        "hits": stats["hits"],
        "misses": stats["misses"],
        "hit_rate": stats["hit_rate"],
    }


def _cache_stats_fields() -> dict[str, int | float]:
    """指标日志用：给 `cache_stats()` 的键加 `cache_` 前缀（历史指标键名保持不变）。"""
    return {f"cache_{k}": v for k, v in cache_stats().items()}


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
        #
        # ★★ 排序方向（2026-10-01 修正）：Chroma 的 score 是**距离**（越小越相似），
        #    故必须**升序**取前 k。此处原为 `key=lambda pair: -pair[1]`（降序距离），
        #    等于**返回最不相似的 k 条** —— 实测同一 query：
        #      Chroma 原始 top-5 = [0.3318(目标), 0.3579, 0.3733, 0.3757, 0.3764]
        #      本函数返回      = [0.4212, 0.4208, 0.4198, 0.4196, 0.4152]  ← 取的是 15 条里最差的
        #    后果：语义/ focus / expanded 三条**向量路由全部返回最不相关候选**，
        #    目标 chunk（如 L2「逆置：三指针」）虽为最近邻却进不了包；L2 跨学科污染亦源于此。
        #    BM25 路由不受影响（`bm25_search` 返回相似度、天然降序，且不经此处重排）。
        oversampled = get_vector_store_manager().similarity_search_with_score(
            collection_name, query, k=k * _SEMANTIC_OVERSAMPLE, filter=filter
        )
        results = sorted(oversampled, key=lambda pair: (pair[1], content_key(pair[0])))[:k]

    # 注入集合来源，供 RRF 合并区分跨集合的同名文档
    for doc, _score in results:
        doc.metadata["_collection"] = collection_name

    _query_cache.set(cache_key, results)
    return results


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

    # ★ B7 的 reset 调用点 ③：本轮开始前清空 ⇒ 该轮结束后 `query_failures` 里只剩
    #   **本轮**的失败（`_query_failures` 是 append-only 的进程级列表，不清就是
    #   「上一条 query 的故障一路跟着这一条的指标」）。一轮内各路由共享同一份记录，
    #   这样「某条路由坏了」能被本轮的 `unexpected_query_failures` 看到。
    from rag.vectorstore import get_vector_store_manager

    get_vector_store_manager().reset_query_failures()
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
                    # ★ B7：只 `logger.warning` 不记失败 ⇒ 这条路由坏了在
                    #   `unexpected_query_failures` 里是隐形的（BM25 半边已由
                    #   `rag.bm25.bm25_search` 记录）。返回 `[]` 保留（单路失败可容忍），
                    #   但必须**留下证据**，否则「坏了」与「没查到」不可区分。
                    #   ★ 局部 import：`try` 里那次 import 若本身失败，except 里就不能
                    #   依赖那个还没绑定的名字（否则 UnboundLocalError 会把证据一起吞掉）。
                    from rag.vectorstore import get_vector_store_manager as _mgr

                    _mgr().record_query_failure(
                        f"{target_collection}: vector_route {e.__class__.__name__}"
                    )
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
