"""检索流水线的各阶段函数（从 pipeline.py 拆出，行为等价）。

★ 这些阶段函数**必须**住在本模块：`aretrieve_documents` 经由本模块命名空间调用它们，
  而 `probe_tracing` / `evidence_chain_gate` / `threshold_sensitivity` 通过 `setattr`
  在本模块上打猴子补丁来拦截真实调用。因此 `_apply_rerank_threshold` / `dedup_same_section`
  / `rerank` 也须在本模块可见（被阶段函数以模块全局方式调用）——前者的**定义**住在
  `_helpers`，但 import 进本模块后，`setattr(_stages, "_apply_rerank_threshold", w)` 仍有效。
"""

from __future__ import annotations

import asyncio
import logging
import time

from langchain_core.documents import Document

from core.settings import settings
from rag.common.rag_utils import extract_query_terms, normalize_query_text
from rag.retrieval.hyde import should_trigger_hyde
from rag.retrieval.postprocess import (
    dedup_same_section,
    downgrade_window_noise,
    merge_window_into_anchors,
    weighted_rrf_merge,
)
from rag.retrieval.query_classifier import QueryCategory, RetrievalDepth, aclassify_query
from rag.retrieval.query_decomposer import decompose
from rag.retrieval.reranker import rerank
from rag.retrieval.retrieval_plan import resolve_retrieval_plan, strategy_from_depth
from rag.retrieval.routes import (
    _amulti_route_search,
    _log_final_retrieval_summary,
    _safe_to_thread,
)

from ._constants import _COMPACT_SUBQUERY_ROUTES, _RERANK_UNSET
from ._helpers import (
    _apply_rerank_threshold,
    _empty_result_fallback,
    _expand_windows_session,
    _generate_hyde_query,
    _merge_hyde_docs,
    _top_rerank_score,
    _warn_rerank_disabled_once,
)
from ._support import _derive_rerank_status, _resolve_thresholds
from ._types import _HydeContext, _HydeOutcome, _RecallRequest, _RetrievalPlan, _WindowOutcome

logger = logging.getLogger(__name__)

# `_safe_to_thread` 超时上限（与既有口径一致：TOOL_CALL_TIMEOUT 再按阶段封顶）
_DEDUP_TIMEOUT_CAP = 3.0
_RRF_MERGE_TIMEOUT_CAP = 5.0
_WINDOW_TIMEOUT_CAP = 5.0


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
        strategy = resolve_retrieval_plan(cat)
        depth = strategy.depth
    else:
        strategy = strategy_from_depth(depth)

    if k == 5 and depth.k != 5:
        k = depth.k
    # ── 重排判定链 · 第 1 环（共 3 环，跨 retriever / reranker 两个模块）──────
    # ① 此处：SHALLOW 深度**有意**跳过重排（省延迟）→ 把 use_rerank 降为 False
    # ② `_stage_rerank` 入口：叠加部署开关（`settings.RERANK_ENABLED`）→ `rerank_active`
    # ③ `reranker.rerank()`：同一开关的防御网，正常不可达（触达即 warning）
    # ⚠️ `use_rerank` 兼着「候选池大小」的职责（见 `_resolve_thresholds`），
    #    所以 ② 刻意**不回写**它 —— 否则一个部署开关会静默改变召回策略。
    #    完整分析见 docs/RERANK_SWITCH_ANALYSIS.md。
    if depth.skip_rerank and use_rerank:
        use_rerank = False

    effective_threshold, coarse_k = _resolve_thresholds(
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
        timeout=min(float(getattr(settings, "TOOL_CALL_TIMEOUT", 30) or 30), _DEDUP_TIMEOUT_CAP),
        default=results,
        max_per_section=max_per_section,
    )

    filtered = [doc for doc, score in deduped if score >= effective_threshold]

    if not filtered and deduped:  # 空结果保底，详见 _empty_result_fallback
        filtered = _empty_result_fallback(deduped, query, effective_threshold)

    _log_final_retrieval_summary("async-post-threshold", query, filtered)
    return filtered, len(deduped), len(filtered)


async def _recall_branch(
    label: str,
    branch_query: str,
    branch_cat: QueryCategory | None,
    branch_terms: list[str] | None,
    req: _RecallRequest,
    route_allowlist: set[str] | None = None,
) -> tuple[str, list[tuple[Document, float]]]:
    """分解路径的一个分支：多路召回 → 每章节去重(2) → 过阈值。"""
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
        timeout=min(float(getattr(settings, "TOOL_CALL_TIMEOUT", 30) or 30), _DEDUP_TIMEOUT_CAP),
        default=branch_results,
        max_per_section=2,
    )
    return label, [
        (doc, score) for doc, score in branch_results if score >= req.effective_threshold
    ]


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

    tasks = [_recall_branch("original", req.query, req.cat, req.terms, req)]
    route_allowlist = _COMPACT_SUBQUERY_ROUTES if req.cat.is_comparison else None
    for sq in [sq for sq in req.sub_queries if sq != req.query]:
        tasks.append(_recall_branch("sub", sq, None, None, req, route_allowlist=route_allowlist))
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
        timeout=min(
            float(getattr(settings, "TOOL_CALL_TIMEOUT", 30) or 30), _RRF_MERGE_TIMEOUT_CAP
        ),
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


async def _run_rerank(
    filtered: list[Document], query: str, top_k: int, decomposed: bool
) -> tuple[list[Document], bool, float]:
    """执行重排（带可辨识哨兵兜底）；返回 ``(reranked, raised, elapsed_ms)``。"""
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
        # ★ B2：default 换成可辨识哨兵 ⇒ 超时/抛错能落成 `failed` 而非被折成 `degraded`。
        default=_RERANK_UNSET,
        top_k=top_k,
    )
    raised = reranked is _RERANK_UNSET
    if raised:
        reranked = filtered[:top_k]  # 坏了：回落原序候选（与旧 default 行为一致）
    return reranked, raised, (time.perf_counter() - started) * 1000


async def _stage_rerank(
    filtered: list[Document],
    query: str,
    k: int,
    use_rerank: bool,
    decomposed: bool,
) -> tuple[list[Document], str, float]:
    """阶段 7：重排（可选）+ 重排后的双重阈值过滤。

    分解路径的候选池是单路的两倍（``top_k=k*2``）：子查询合并后候选更多，
    仍按 k 截断会把原查询的证据挤掉。未启用重排时同样按这个倍数截断
    （``filtered[:k]`` vs ``filtered[:k*2]``），保持两条路径口径一致。

    **重排判定链 · 第 2 环**（第 1 环见 `_resolve_thresholds`，第 3 环见
    `reranker.rerank()`）：部署开关（`.env` 的 ``RERANK_ENABLED``）在本函数入口生效，
    且**只决定「是否执行重排」**——刻意**不写回** ``use_rerank``：后者还兼着候选池
    大小（``coarse_k``）的职责，回写会让一个部署开关静默改变召回策略。
    详见 ``docs/RERANK_SWITCH_ANALYSIS.md``。

    Returns:
        ``(重排后的文档, rerank_status, 重排耗时毫秒)``。``rerank_status`` 是四态枚举
        ``off``/``success``/``degraded``/``failed``；耗时由调用方写进 ``stage_ms``。
    """
    rerank_active = use_rerank and settings.RERANK_ENABLED
    if not (rerank_active and filtered):
        # 未启用重排：仍要截断。注意这里**不**记录耗时（原本就没有计时窗口）
        if not rerank_active:
            _warn_rerank_disabled_once(use_rerank, filtered)
            return filtered[: k * 2 if decomposed else k], "off", 0.0
        # active 但无候选可重排 ⇒ 空结果降级（回落原序，本就是空）。
        return filtered, "degraded", 0.0

    top_k = k * 2 if decomposed else k
    log_label = "async-post-rerank-decomposed" if decomposed else "async-post-rerank"
    reranked, raised, elapsed_ms = await _run_rerank(filtered, query, top_k, decomposed)

    rerank_status = _derive_rerank_status(
        reranked, active=True, raised=raised, empty_result=(not raised and not reranked)
    )
    # 双重阈值过滤，兜底保留 top-2
    out = _apply_rerank_threshold(reranked, min_keep=2)
    _log_final_retrieval_summary(log_label, query, out)
    return out, rerank_status, elapsed_ms


async def _hyde_apply_rerank(
    hyde_docs: list[Document], query: str, use_rerank: bool, k: int, rerank_status: str
) -> tuple[list[Document], str]:
    """HyDE 补重排；`rerank_status` **只升不降**（成功可把主链拉回 success，失败维持原状）。"""
    if not (use_rerank and settings.RERANK_ENABLED and hyde_docs):
        return hyde_docs, rerank_status
    _hyde_pre = hyde_docs
    hyde_docs = await _safe_to_thread(
        "async_hyde_rerank",
        rerank,
        query,
        hyde_docs,
        timeout=float(getattr(settings, "RERANK_TIMEOUT", 30) or 30),
        default=_RERANK_UNSET,
        top_k=k,
    )
    _hyde_raised = hyde_docs is _RERANK_UNSET
    if _hyde_raised:
        hyde_docs = _hyde_pre[:k]
    if (
        _derive_rerank_status(
            hyde_docs,
            active=True,
            raised=_hyde_raised,
            empty_result=(not _hyde_raised and not hyde_docs),
        )
        == "success"
    ):
        rerank_status = "success"
    return hyde_docs, rerank_status


async def _hyde_recall_and_rerank(
    hyde_query: str, query: str, ctx: _HydeContext, rerank_status: str
) -> tuple[list[Document], str]:
    """HyDE 假设文档召回 + 阈值放宽 + 可选补重排；返回 ``(docs, 更新后的 rerank_status)``。

    ★ 阈值放宽到 ``effective_threshold * 0.8``：HyDE 是兜底手段，用同一把尺子会把它的
      召回几乎全部滤掉。
    ★ `rerank_status` 只升不降（见 `_hyde_apply_rerank`）。
    """
    hyde_terms = extract_query_terms(normalize_query_text(hyde_query))
    hyde_results = await _amulti_route_search(
        hyde_query,
        ctx.collection_name,
        ctx.coarse_k,
        filter=ctx.filter,
        cat=ctx.cat,
        use_rerank=ctx.use_rerank,
        terms=hyde_terms,
        depth=ctx.depth,
    )
    hyde_results = await _safe_to_thread(
        "async_hyde_dedup",
        dedup_same_section,
        hyde_results,
        timeout=min(float(getattr(settings, "TOOL_CALL_TIMEOUT", 30) or 30), _DEDUP_TIMEOUT_CAP),
        default=hyde_results,
        max_per_section=2,
    )
    hyde_docs = [doc for doc, score in hyde_results if score >= ctx.effective_threshold * 0.8]
    return await _hyde_apply_rerank(hyde_docs, query, ctx.use_rerank, ctx.k, rerank_status)


async def _run_hyde_fallback(
    hyde_query: str, query: str, filtered: list[Document], rerank_status: str, ctx: _HydeContext
) -> tuple[list[Document], int, str, str]:
    """执行 HyDE 兜底召回/补重排/并入；异常只记 error 不抛出。

    Returns:
        ``(filtered, 净增条数, error, rerank_status)``。
    """
    try:
        hyde_docs, rerank_status = await _hyde_recall_and_rerank(
            hyde_query, query, ctx, rerank_status
        )
        filtered, added_count = _merge_hyde_docs(filtered, hyde_docs, hyde_query, ctx.k, query)
        return filtered, added_count, "", rerank_status
    except Exception as e:  # 兜底机制失败不该影响已经拿到的正常结果
        logger.warning("Async HyDE fallback retrieval failed: %s", e)
        return filtered, 0, e.__class__.__name__, rerank_status


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
    rerank_status: str,
) -> _HydeOutcome:
    """阶段 8：HyDE 兜底召回。

    只在"结果偏少或最高重排分偏低"时触发（`should_trigger_hyde`）；触发后用 LLM 生成
    假设性答案再召回一次，把**新**文档追加到现有结果之后。兜底失败不影响已拿到的结果
    （见 `_run_hyde_fallback`）。未触发时 `elapsed_ms` 为 0。
    """
    if depth.skip_hyde or not should_trigger_hyde(
        query, len(filtered), _top_rerank_score(filtered), cat
    ):
        return _HydeOutcome(filtered, False, 0, "", rerank_status, 0.0)

    started = time.perf_counter()
    hyde_query = await _generate_hyde_query(query)
    ctx = _HydeContext(
        collection_name=collection_name,
        coarse_k=coarse_k,
        filter=filter,
        cat=cat,
        use_rerank=use_rerank,
        depth=depth,
        k=k,
        effective_threshold=effective_threshold,
    )
    if hyde_query and hyde_query != query:
        triggered = True
        filtered, added_count, error, rerank_status = await _run_hyde_fallback(
            hyde_query, query, filtered, rerank_status, ctx
        )
    else:
        # 判定要触发、但没拿到可用的假设文档（LLM 超时 / 返回空 / 与原文相同）——
        # 同属「想兜底却没兜成」，也必须留痕，否则这条路径完全不可见。
        triggered = False
        added_count = 0
        error = ""
        logger.info("HyDE 判定触发但未生成可用假设文档，跳过（query=%s）", query[:40])

    return _HydeOutcome(
        filtered,
        triggered,
        added_count,
        error,
        rerank_status,
        round((time.perf_counter() - started) * 1000, 3),
    )


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
    展开后再做一次负采样软降级（`downgrade_window_noise`）：被窗口带进来的
    噪声 chunk 不该与直接命中的证据同等对待。
    """
    if not filtered:
        return _WindowOutcome(filtered, 0.0)

    started = time.perf_counter()
    expanded = await _safe_to_thread(
        "async_window_expand",
        _expand_windows_session,
        filtered,
        collection_name,
        depth,
        timeout=min(float(getattr(settings, "TOOL_CALL_TIMEOUT", 30) or 30), _WINDOW_TIMEOUT_CAP),
        default=filtered,
    )
    # Negative Sampling: 对 window 展开的噪声 chunk 软降级
    expanded = downgrade_window_noise(
        expanded, query, is_comparison=bool(cat and cat.is_comparison)
    )
    # 把窗口 chunk 合并回锚点，消除 score=0 独立证据对 top-k 的污染
    window_before = sum(
        1
        for d in expanded
        if d.metadata.get("_window_expanded") or d.metadata.get("_parent_expanded")
    )
    expanded = merge_window_into_anchors(expanded)
    window_merged = sum(1 for d in expanded if d.metadata.get("_window_merged"))
    if window_before:
        logger.debug(
            "Window merge: before=%d merged=%d dropped=%d",
            window_before,
            window_merged,
            window_before - window_merged,
        )
    _log_final_retrieval_summary("async-post-window", query, expanded)
    return _WindowOutcome(
        expanded,
        round((time.perf_counter() - started) * 1000, 3),
        window_merged_count=window_merged,
    )
