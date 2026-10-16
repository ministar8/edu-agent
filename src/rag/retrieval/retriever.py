"""RAG 检索门面（对外入口）。

论文架构图 ↔ 代码文件：
  查询理解  → query_classifier / query_decomposer / retrieval_plan
  多路召回  → routes.py + recall.py
  融合      → fusion.py
  重排      → reranker.py
  HyDE/窗口 → hyde.py / postprocess.py
  流水线    → pipeline.py（classify→…→finalize）
  证据出包  → evidence_policy.py / layer_recall.py

**对外入口**（agent 经 `agents/tools.py` 调用）：
  - aretrieve_evidence_with_retry() / aretrieve_evidence() / warmup_query_cache()

**参数 `use_rerank` 的语义**：它不是「是否重排」开关，而是「是否按重排口径准备候选」
（决定 coarse_k）。真正重排判定见 `docs/RERANK_SWITCH_ANALYSIS.md`。

**参数 `k` 的语义**：目标条数，不是硬上限；分解路径最多返回 `2k`。
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Sequence

from core.settings import settings
from rag.common.rag_utils import extract_query_terms, normalize_query_text
from rag.retrieval.evidence import FusedEvidence
from rag.retrieval.pipeline import (  # noqa: F401  兼容评测脚本 `R._resolve_thresholds`
    SCORE_THRESHOLD,
    StageSink,
    _resolve_thresholds,
    aretrieve_documents,
)
from rag.retrieval.query_classifier import RetrievalDepth, aclassify_query
from rag.retrieval.query_decomposer import decompose
from rag.retrieval.retrieval_plan import resolve_retrieval_plan, strategy_from_depth
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
from rag.retrieval.retriever_retry import (
    _evidence_kwargs,
    _verdict_from,
)
from rag.retrieval.verifier import VerificationResult

__all__ = [
    "StageSink",
    "aretrieve_documents",
    "aretrieve_evidence",
    "aretrieve_evidence_with_retry",
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


async def _resolve_evidence_plan(query: str, depth: RetrievalDepth | None, k: int) -> _EvidencePlan:
    """阶段 1-2：分类 → 解析策略 → 查询分解，返回本次检索实际采用的计划。"""
    terms = extract_query_terms(normalize_query_text(query))
    cat = await aclassify_query(query, terms)
    resolved_depth = depth
    if resolved_depth is None:
        strategy = resolve_retrieval_plan(cat)
        resolved_depth = strategy.depth
    else:
        strategy = strategy_from_depth(resolved_depth)
    effective_k = resolved_depth.k if k == 5 and resolved_depth.k != 5 else k

    decompose_start = time.perf_counter()
    if resolved_depth.skip_decompose:
        sub_queries = [query]
    else:
        sub_queries = await decompose(query, cat=cat)
    decompose_ms = round((time.perf_counter() - decompose_start) * 1000, 3)

    return _EvidencePlan(
        cat=cat,
        depth=resolved_depth,
        layer=strategy.layer,
        route_type=strategy.route_type,
        effective_k=effective_k,
        sub_queries=sub_queries,
        decompose_ms=decompose_ms,
    )


async def _run_retrieval(
    query: str,
    collection_name: str,
    score_threshold: float,
    use_rerank: bool,
    filter: dict | None,
    plan: _EvidencePlan,
    on_stage: StageSink | None,
) -> tuple[list, float, dict]:
    """调底层检索；返回 (docs, 延迟 ms, rerank 状态旁路出参)。"""
    stage_start = time.perf_counter()
    # ★ 修复批 Important-3（B2 送达断链）：空包时没有文档可挂 `_rerank_status`，
    #   改由 `rerank_status_out` 这个**旁路出参**把 `_stage_rerank` 已算出的状态带回桥接处。
    rerank_status_bridge: dict[str, str] = {}
    docs = await aretrieve_documents(
        query=query,
        collection_name=collection_name,
        k=plan.effective_k,
        score_threshold=score_threshold,
        use_rerank=use_rerank,
        filter=filter,
        depth=plan.depth,
        cat=plan.cat,
        precomputed_sub_queries=plan.sub_queries,
        on_stage=on_stage,
        rerank_status_out=rerank_status_bridge,
    )
    latency_ms = round((time.perf_counter() - stage_start) * 1000, 3)
    return docs, latency_ms, rerank_status_bridge


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
    plan = await _resolve_evidence_plan(query, depth, k)
    docs, latency_ms, rerank_bridge = await _run_retrieval(
        query, collection_name, score_threshold, use_rerank, filter, plan, on_stage
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
    preferred_layers: Sequence[str] | None = None,
    eligible_layers: Sequence[str] | None = None,
) -> tuple[FusedEvidence, VerificationResult]:
    """异步检索入口（agent / 检索门禁 / RAGAS / 探针同口）。

    路径（2026-10-15 B5 后唯一路径）：

        retrieve → 规则 verify（在 aretrieve_evidence 内）→ 返回

    ★ 函数名 `with_retry` 是**历史遗留**：原「可选 LLM verify + 最多一次 retry」分支
      已随 LLM 校验层删除（owner 裁定 B5，2026-10-15；全调用点恒 `use_llm_verify=False`、
      从未启用）。保留函数名不改，是为避免六处调用点与文档锚点连带改写；重命名
      （如 `aretrieve_evidence_entry`）列为冻结后清理项，须走 EFFECT_PLAN §6 新版本流程。
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
