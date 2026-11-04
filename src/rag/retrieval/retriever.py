"""RAG 检索门面（对外唯一入口；命名 = retriever，不是 routes）。

主路径 6 步（与 `src/rag/README.md` / 论文第 3 章一致）：
  ① 查询理解  normalize → classify → TaskPolicy + RetrievalPlan →（可选）decompose
  ② 多路召回  routes 并发：semantic / BM25 / focus / expanded / 元数据
  ③ 融合      postprocess 加权 RRF
  ④ 过滤重排  去重 · 阈值 ·（可选）rerank · HyDE / 窗口 / top-up
  ⑤ 出包      evidence_policy（release 唯一出口）→ FusedEvidence
  ⑥ 缓存验证  semantic_cache + 规则 verifier + metrics

职责边界：
  - 本模块：编排门面、缓存读写、重试包装、指标
  - 不做：单路检索细节（`routes`）、路由拼装（`recall`）、权限裁剪（`evidence_policy`）

策略三层（勿混）：
  - TaskPolicy（`schema/task_policy`）：安全/披露——进不进池、包里能不能带答案
  - RetrievalPlan/depth：计算预算——k、coarse_k、跳不跳分解/重排准备
  - 部署开关（如 `settings.RERANK_ENABLED`）：环境是否真执行 rerank

★ 参数 `use_rerank` 的语义：**不是**「是否调用 rerank()」，而是「是否按重排口径
  准备候选（影响 coarse_k）」。真正是否重排还取决于 `depth.skip_rerank` 与
  `settings.RERANK_ENABLED`——细节见 `docs/RERANK_SWITCH_ANALYSIS.md`。

★ 参数 `k`：目标条数，不是硬上限；分解路径最多可返回约 `2k`。

论文架构图 ↔ 代码：
  查询理解 → query_classifier / task_policy / retrieval_plan / query_decomposer
  多路召回 → recall（拼）+ routes（跑）
  融合     → postprocess（RRF）
  重排     → reranker
  HyDE/窗  → hyde / postprocess
  流水线   → pipeline（classify→…→finalize）
  证据出包 → evidence + evidence_policy + layer_recall
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Sequence

from core.settings import settings
from rag.retrieval.evidence import FusedEvidence
from rag.retrieval.pipeline import (  # noqa: F401  兼容评测脚本 `R._resolve_thresholds`
    SCORE_THRESHOLD,
    StageSink,
    _PlanSink,
    _resolve_thresholds,
    aretrieve_documents,
)
from rag.retrieval.query_classifier import STANDARD_DEPTH, QueryCategory, RetrievalDepth
from rag.retrieval.retriever_io import (
    _assemble_fused,
    _cache_signatures,
    _emit_evidence_metric,
    _EvidencePlan,
    _lookup_cached,
    _store_cached,
    _verify_fused,
    _with_topup,
)
from rag.retrieval.verifier import VerificationResult

__all__ = [
    "StageSink",
    "aretrieve_documents",
    "aretrieve_evidence",
    "aretrieve_evidence_raw",
    "cache_stats",
    "warmup_query_cache",
]

logger = logging.getLogger(__name__)

# 兼容：部分评测脚本 `import rag.retrieval.retriever as R; R._resolve_thresholds`


def cache_stats() -> dict[str, int | float]:
    """查询缓存的命中统计（并发下近似，仅用于观测）。

    键名与 `SemanticCache.stats()` 对齐（`hits` / `misses` / `hit_rate`），
    这样 `/api/metrics` 能把多个缓存并排展示而不用做字段映射。
    """
    from rag.retrieval.routes import cache_stats as _stats

    return _stats()


# Reranker 扩展倍数：知识库扩充后需要更大候选池
# k=5 时 coarse_k=25，k=8 时 coarse_k=40
_RERANK_EXPAND_FACTOR = settings.RERANK_EXPAND_FACTOR


# ── 公开 API ──────────────────────────────────────────


async def _run_retrieval(
    query: str,
    collection_name: str,
    score_threshold: float,
    use_rerank: bool,
    filter: dict | None,
    k: int,
    depth: RetrievalDepth | None,
    on_stage: StageSink | None,
) -> tuple[list, float, dict, _PlanSink]:
    """调底层检索；返回 (docs, 延迟 ms, rerank 状态旁路, 计划旁路)。

    门面不再自己 classify/plan/decompose —— pipeline 是这些阶段的唯一所有者，
    通过 `_PlanSink` 把解析结果带回（空包/异常同样送达）。
    """
    stage_start = time.perf_counter()
    # ★ 修复批 Important-3（B2 送达断链）：空包时没有文档可挂 `_rerank_status`，
    #   改由 `rerank_status_out` 这个**旁路出参**把 `_stage_rerank` 已算出的状态带回桥接处。
    rerank_status_bridge: dict[str, str] = {}
    plan_out = _PlanSink()
    docs = await aretrieve_documents(
        query=query,
        collection_name=collection_name,
        k=k,
        score_threshold=score_threshold,
        use_rerank=use_rerank,
        filter=filter,
        depth=depth,
        on_stage=on_stage,
        rerank_status_out=rerank_status_bridge,
        plan_out=plan_out,
    )
    latency_ms = round((time.perf_counter() - stage_start) * 1000, 3)
    return docs, latency_ms, rerank_status_bridge, plan_out


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
    """异步检索主实现。参数 ``use_rerank`` 的语义见模块文档串（**不是**「是否重排」的开关）。"""
    filter_sig, params_sig = _cache_signatures(
        filter, use_rerank, k, score_threshold, depth, max_tokens
    )

    cached = await _lookup_cached(query, collection_name, filter_sig, params_sig)
    if cached is not None:
        return cached

    metric_start = time.perf_counter()
    docs, latency_ms, rerank_bridge, plan_out = await _run_retrieval(
        query, collection_name, score_threshold, use_rerank, filter, k, depth, on_stage
    )
    if plan_out.depth is None:
        logger.warning("plan_out 未填充 depth，回退 STANDARD_DEPTH（检查 pipeline 旁路）")
    plan = _EvidencePlan(
        cat=plan_out.cat or QueryCategory(source="rule"),
        depth=plan_out.depth or STANDARD_DEPTH,
        layer=plan_out.retrieval_layer,
        route_type=plan_out.route_type,
        effective_k=plan_out.k or k,
        sub_queries=plan_out.sub_queries or [query],
        decompose_ms=plan_out.decompose_ms,
    )
    fused = await _assemble_fused(
        docs,
        query,
        collection_name,
        max_tokens,
        score_threshold,
        use_rerank,
        plan,
        latency_ms,
        rerank_bridge,
    )
    await _verify_fused(fused, query)
    await _store_cached(query, fused, collection_name, filter_sig, params_sig)
    _emit_evidence_metric(
        query=query,
        collection_name=collection_name,
        start=metric_start,
        fused=fused,
    )
    return fused


def _verdict_from(fused: FusedEvidence) -> VerificationResult:
    """取 aretrieve_evidence 已写入的规则 verdict；缺失时兜底 PASS。"""
    from rag.retrieval.verifier import Verdict, VerificationResult

    raw = fused.metadata.get("evidence_verdict")
    if raw:
        try:
            return VerificationResult.model_validate(raw)
        except Exception as e:
            logger.debug("evidence_verdict 解析失败，按 PASS 兜底: %s", e)
    return VerificationResult(verdict=Verdict.PASS, overall_score=1.0)


def _evidence_kwargs(
    query: str,
    collection_name: str,
    k: int,
    score_threshold: float,
    use_rerank: bool,
    filter: dict | None,
    max_tokens: int,
    depth: RetrievalDepth | None,
    on_stage: StageSink | None,
) -> dict:
    """`aretrieve_evidence` 的调用参数字典（重试时按 hints 就地改）。"""
    return {
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


async def _finalize_evidence(
    fused: FusedEvidence,
    query: str,
    collection_name: str,
    *,
    retry_metric_start: float,
) -> tuple[FusedEvidence, VerificationResult]:
    """默认路径：不 verify / 不 retry —— 规则 verdict 已在 aretrieve_evidence 内写入 metadata。

    ★ 2026-10-15 owner 裁定 B5：原 `use_llm_verify=True` 分支（LLM verify + 最多一次
      retry，`_verify_with_optional_retry`）随 LLM 校验层整层删除；本函数只剩默认路径。
      参数 `max_retries` / `use_llm_verify` 已从入口一并移除（全调用点恒 False/0）。
    """
    result = _verdict_from(fused)
    _emit_evidence_metric(
        query=query,
        collection_name=collection_name,
        start=retry_metric_start,
        fused=fused,
    )
    return fused, result


async def aretrieve_evidence_raw(
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
    preferred_layers: Sequence[str] | None = None,
    eligible_layers: Sequence[str] | None = None,
) -> tuple[FusedEvidence, VerificationResult]:
    """异步检索入口（agent / 检索门禁 / RAGAS / 探针同口）。

    路径（2026-10-15 B5 后唯一路径）：

        retrieve → 规则 verify（在 aretrieve_evidence 内）→ 返回

    ★ 命名：原名 `aretrieve_evidence_with_retry` 中的 retry 分支已随 LLM 校验层删除
      （owner 裁定 B5，2026-10-15），名字与行为不符。2026-11-04 改名为 `_raw`，与产品
      路径 `retrieve_for_task`（已裁剪）对照；`raw` 指**未经 release 裁剪**，不是「未 top-up」。
    ★ 规则 verdict 仍在 `aretrieve_evidence` 内由 `_verify_fused` 写入 metadata，
      本入口只透出，不二次 verify。

    ``preferred_layers``：候选池 top-up（Candidate Pool Recall），保证目标层进池。
    ``eligible_layers``：policy 认定的**合规语义层**（`TaskPolicy.eligible_semantic_layers()`）。
    仅当 preferred 层与资格冲突（全不合规）时用于回退，保证候选池不空；None = 不做回退。
    """
    allowed = [ly for ly in (eligible_layers or []) if ly in ("basic", "advanced", "exams")]
    retry_metric_start = time.perf_counter()
    current_kwargs = _evidence_kwargs(
        query, collection_name, k, score_threshold, use_rerank, filter, max_tokens, depth, on_stage
    )

    fused = await _with_topup(
        query, preferred_layers, allowed, await aretrieve_evidence(**current_kwargs), filter
    )
    return await _finalize_evidence(
        fused,
        query,
        collection_name,
        retry_metric_start=retry_metric_start,
    )


# ── 入库后 smoke（非缓存预热）────────────────────────────
#
# 曾有 30+ 条「高频知识点」全量预热，对毕设主路径无收益（检索正确性由
# retrieval_gate / probe_gate 保证），却让入库尾巴拖到分钟级。
# 现在只保留 **1 条 smoke query**：证明「索引可查 → 多路召回 → 融合」全链能跑通。
# 依赖就绪由 `VectorStoreManager.wait_until_ready` 屏障负责，不靠预热探活。

_SMOKE_QUERIES = [
    "什么是栈和队列",
]


def warmup_query_cache(quiet: bool = False) -> dict:
    """入库后 smoke：跑 1 条查询，确认检索链可走通。

    原「缓存预热 30+ 条」已删除 —— 检索质量由门禁保证，这里只做冒烟。
    返回统计：{total, succeeded, failed, elapsed_ms}
    """
    total = len(_SMOKE_QUERIES)
    succeeded = 0
    failed = 0
    t0 = time.perf_counter()

    for q in _SMOKE_QUERIES:
        try:
            asyncio.run(aretrieve_documents(q, k=3, use_rerank=False))
            succeeded += 1
        except Exception:
            failed += 1

    elapsed_ms = round((time.perf_counter() - t0) * 1000, 1)
    if not quiet:
        logger.info(
            "Retrieval smoke done: %d/%d queries succeeded, %d failed, %.0f ms",
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
