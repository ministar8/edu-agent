"""检索流水线编排层：`aretrieve_documents` + 收尾指标（从 pipeline.py 拆出，行为等价）。

★ 编排层**经由 `_stages` 模块命名空间**调用阶段函数（`_stages._stage_xxx(...)`），
  这样 `_stages` 上的猴子补丁才能拦住真实调用。
"""

from __future__ import annotations

import time

from langchain_core.documents import Document

from rag.common.metrics import metrics
from rag.retrieval.query_classifier import QueryCategory, RetrievalDepth
from rag.retrieval.routes import _cache_stats_fields

from . import _stages
from ._constants import SCORE_THRESHOLD, StageSink
from ._support import _emit_stage
from ._types import _RecallRequest, _RetrievalContext, _RetrievalCounters, _RunState


async def _run_stages_early(
    query: str,
    collection_name: str,
    score_threshold: float,
    filter: dict | None,
    precomputed_sub_queries: list[str] | None,
    on_stage: StageSink | None,
    stage_ms: dict[str, float],
    state: _RunState,
) -> tuple[list[tuple[Document, float]], QueryCategory]:
    """阶段 1~4：分类 → 策略 → 分解 → 多路召回。就地更新 state/stage_ms，返回 (召回结果, 类别)。"""
    _emit_stage(on_stage, "classify")
    _t = time.perf_counter()
    terms, cat = await _stages._stage_classify_query(query, state.cat)
    stage_ms["classification_ms"] = round((time.perf_counter() - _t) * 1000, 3)

    _emit_stage(on_stage, "plan")
    plan = _stages._stage_resolve_plan(
        query, cat, state.k, score_threshold, state.use_rerank, state.depth
    )
    state.depth = plan.depth
    state.k = plan.k
    state.use_rerank = plan.use_rerank
    state.effective_threshold = plan.effective_threshold
    state.coarse_k = plan.coarse_k
    state.retrieval_layer = plan.retrieval_layer
    state.route_type = plan.route_type
    state.cat = cat

    _emit_stage(on_stage, "decompose")
    _t = time.perf_counter()
    state.sub_queries, state.decomposed = await _stages._stage_decompose_query(
        query, cat, plan.depth, precomputed_sub_queries
    )
    stage_ms["decompose_ms"] = round((time.perf_counter() - _t) * 1000, 3)

    _emit_stage(on_stage, "recall")
    _t = time.perf_counter()
    results = await _stages._stage_recall_and_merge(
        _RecallRequest(
            query=query,
            collection_name=collection_name,
            coarse_k=plan.coarse_k,
            filter=filter,
            cat=cat,
            terms=terms,
            use_rerank=plan.use_rerank,
            depth=plan.depth,
            sub_queries=state.sub_queries,
            decomposed=state.decomposed,
            effective_threshold=plan.effective_threshold,
        )
    )
    stage_ms["route_merge_ms"] = round((time.perf_counter() - _t) * 1000, 3)
    state.raw_results_count = len(results)
    return results, cat


async def _run_stages_late(
    query: str,
    collection_name: str,
    filter: dict | None,
    results: list[tuple[Document, float]],
    cat: QueryCategory,
    on_stage: StageSink | None,
    stage_ms: dict[str, float],
    state: _RunState,
) -> list[Document]:
    """阶段 5~9：去重/阈值 → 重排 → HyDE → 窗口展开。就地更新 state/stage_ms，返回最终文档。"""
    _emit_stage(on_stage, "dedup")
    (
        filtered,
        state.post_dedup_count,
        state.post_threshold_count,
    ) = await _stages._stage_dedup_and_threshold(results, query, cat, state.effective_threshold)

    _emit_stage(on_stage, "rerank")
    filtered, state.rerank_status, _rerank_ms = await _stages._stage_rerank(
        filtered, query, state.k, state.use_rerank, state.decomposed
    )
    stage_ms["rerank_ms"] = round(_rerank_ms, 3)
    state.post_rerank_count = len(filtered)

    _emit_stage(on_stage, "hyde")
    hyde = await _stages._stage_hyde(
        filtered,
        query=query,
        collection_name=collection_name,
        coarse_k=state.coarse_k,
        filter=filter,
        cat=cat,
        use_rerank=state.use_rerank,
        depth=state.depth,
        k=state.k,
        effective_threshold=state.effective_threshold,
        rerank_status=state.rerank_status,
    )
    filtered = hyde.docs
    state.hyde_triggered = hyde.triggered
    state.hyde_added_count = hyde.added_count
    state.hyde_error = hyde.error
    state.rerank_status = hyde.rerank_status
    stage_ms["hyde_ms"] = hyde.elapsed_ms

    _emit_stage(on_stage, "expand")
    window = await _stages._stage_expand_windows(
        filtered, query=query, collection_name=collection_name, cat=cat, depth=state.depth
    )
    filtered = window.docs
    stage_ms["window_ms"] = window.elapsed_ms
    state.post_window_count = len(filtered)
    state.window_added_count = window.window_merged_count
    return filtered


def _build_context(
    state: _RunState, query: str, collection_name: str, cat: QueryCategory
) -> _RetrievalContext:
    """把一次检索的事实打包成收尾上下文。"""
    return _RetrievalContext(
        query=query,
        collection_name=collection_name,
        k=state.k,
        coarse_k=state.coarse_k,
        effective_threshold=state.effective_threshold,
        depth=state.depth,
        retrieval_layer=state.retrieval_layer,
        route_type=state.route_type,
        cat=cat,
        decomposed=state.decomposed,
        sub_queries=state.sub_queries,
        use_rerank=state.use_rerank,
        rerank_status=state.rerank_status,
        hyde_triggered=state.hyde_triggered,
        hyde_added_count=state.hyde_added_count,
        hyde_error=state.hyde_error,
        counters=_RetrievalCounters(
            raw_results=state.raw_results_count,
            after_dedup=state.post_dedup_count,
            after_threshold=state.post_threshold_count,
            after_rerank=state.post_rerank_count,
            after_window=state.post_window_count,
            window_added=state.window_added_count,
        ),
    )


def _tag_evidence_provenance(filtered: list[Document], ctx: _RetrievalContext) -> None:
    """给证据打溯源标记，随证据流向生成阶段（回答"这条证据是怎么来的"）。"""
    for doc in filtered:
        doc.metadata["_retrieval_depth"] = ctx.depth.depth if ctx.depth else ""
        doc.metadata["_retrieval_layer"] = ctx.retrieval_layer
        doc.metadata["_route_type"] = ctx.route_type
        doc.metadata["_effective_k"] = ctx.k
        doc.metadata["_coarse_k"] = ctx.coarse_k
        # 供上层（aretrieve_evidence → fused.metadata）与门禁断言读取：
        # 「本次重排的真实状态」+ 由其**派生**的「是否真的执行了重排」。
        # ★ `rerank_used` 不再是独立自报布尔，唯一真源是 `rerank_status`；仅 success ⇒ True。
        doc.metadata["_rerank_status"] = ctx.rerank_status
        doc.metadata["_rerank_used"] = ctx.rerank_status == "success"


def _retrieve_summary_values(
    ctx: _RetrievalContext, filtered: list[Document], stage_ms: dict[str, float]
) -> dict:
    """构建检索摘要指标（各阶段计数 + 有效性信号）。"""
    window_expanded_count = sum(1 for doc in filtered if doc.metadata.get("_window_merged"))
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

    return {
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
        "rerank_status": ctx.rerank_status,
        "rerank_used": ctx.rerank_status == "success",
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
    }


def _finalize_retrieval(
    filtered: list[Document],
    *,
    ctx: _RetrievalContext,
    started_at: float,
    stage_ms: dict[str, float],
) -> list[Document]:
    """阶段 10：给证据打溯源标记，并写出检索摘要指标。

    指标里刻意同时保留**各阶段计数**（before_threshold / after_dedup /
    after_threshold / after_rerank / after_window）—— 只看最终条数无法判断
    是召回不足还是被某一层过滤掉了。
    """
    _tag_evidence_provenance(filtered, ctx)
    metrics.emit_retrieve_summary(
        query=ctx.query,
        collection=ctx.collection_name,
        duration_ms=round((time.perf_counter() - started_at) * 1000, 3),
        values=_retrieve_summary_values(ctx, filtered, stage_ms),
    )
    return filtered


def _emit_error_metrics(
    exc: BaseException,
    *,
    query: str,
    collection_name: str,
    started_at: float,
    stage_ms: dict[str, float],
    state: _RunState,
) -> None:
    """异常路径指标：报告已知的部分计数（未走到的阶段计数保持初始 0）。"""
    metrics.emit_retrieve_summary(
        query=query,
        collection=collection_name,
        status="error",
        duration_ms=round((time.perf_counter() - started_at) * 1000, 3),
        values={
            "k": state.k,
            "coarse_k": state.coarse_k,
            "threshold": state.effective_threshold,
            "before_threshold": state.raw_results_count,
            "after_section_dedup": state.post_dedup_count,
            "after_threshold": state.post_threshold_count,
            "after_rerank": state.post_rerank_count,
            "after_window": state.post_window_count,
            "window_added": state.window_added_count,
            "retrieval_layer": state.retrieval_layer,
            "route_type": state.route_type,
            "decomposed": state.decomposed,
            "sub_query_count": len(state.sub_queries),
            "use_rerank": state.use_rerank,
            "rerank_status": state.rerank_status,
            "rerank_used": state.rerank_status == "success",
            "hyde_triggered": state.hyde_triggered,
            "hyde_added_count": state.hyde_added_count,
            "hyde_error": state.hyde_error,
            "async_routes": True,
            **stage_ms,
            "error_type": exc.__class__.__name__,
        },
    )


# ★ ``rerank_status_out``（修复批 Important-3，B2 送达断链的堵点）：非 None 时，
#   本函数**无论结果包是否为空**，都会把最终 ``rerank_status`` 写进这个调用方传入的
#   dict。此前状态只经 ``doc.metadata["_rerank_status"]`` 逐文档携带 —— 包空时没有文档可挂，
#   ``_stage_rerank`` 已算出的 ``off``/``degraded``/``failed`` 在 retriever 桥接这一跳被
#   **整包丢弃**。异常发生在重排阶段**之前** ⇒ 写入 ``""``（未知，不回填）。
#   写入点放在 `finally` ⇒ 异常路径同样要送达（回归锁见 `evidence_chain_gate.py` 的 `9m`）。
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
    rerank_status_out: dict[str, str] | None = None,
) -> list[Document]:
    """异步底层检索。``use_rerank`` 语义见模块文档串（**不是**「是否重排」的开关）；
    ``rerank_status_out`` 的送达语义见本函数上方注释。
    """
    start = time.perf_counter()
    stage_ms: dict[str, float] = {}
    state = _RunState(
        depth=depth,
        k=k,
        use_rerank=use_rerank,
        effective_threshold=score_threshold,
        coarse_k=k,
        cat=cat,
    )
    try:
        results, resolved_cat = await _run_stages_early(
            query,
            collection_name,
            score_threshold,
            filter,
            precomputed_sub_queries,
            on_stage,
            stage_ms,
            state,
        )
        filtered = await _run_stages_late(
            query, collection_name, filter, results, resolved_cat, on_stage, stage_ms, state
        )
        return _finalize_retrieval(
            filtered,
            ctx=_build_context(state, query, collection_name, resolved_cat),
            started_at=start,
            stage_ms=stage_ms,
        )
    except Exception as e:
        _emit_error_metrics(
            e,
            query=query,
            collection_name=collection_name,
            started_at=start,
            stage_ms=stage_ms,
            state=state,
        )
        raise
    finally:
        if rerank_status_out is not None:
            rerank_status_out["rerank_status"] = state.rerank_status
