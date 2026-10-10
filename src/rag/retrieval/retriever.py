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
import json
import logging
import time
from collections.abc import Sequence
from dataclasses import dataclass

from core.settings import settings
from rag.common.metrics import metrics
from rag.common.rag_utils import extract_query_terms, normalize_query_text
from rag.retrieval.evidence import FusedEvidence
from rag.retrieval.pipeline import (  # noqa: F401  兼容评测脚本 `R._resolve_thresholds`
    SCORE_THRESHOLD,
    StageSink,
    _resolve_thresholds,
    aretrieve_documents,
)
from rag.retrieval.query_classifier import QueryCategory, RetrievalDepth, aclassify_query
from rag.retrieval.query_decomposer import decompose
from rag.retrieval.retrieval_plan import L2_STANDARD, resolve_retrieval_plan, strategy_from_depth
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


@dataclass(frozen=True)
class _EvidencePlan:
    """`aretrieve_evidence` 阶段 1-2 的产物：分类 + 策略 + 查询分解。"""

    cat: QueryCategory
    depth: RetrievalDepth
    layer: str
    route_type: str
    effective_k: int
    sub_queries: list[str]
    decompose_ms: float


def _cache_signatures(
    filter: dict | None,
    use_rerank: bool,
    k: int,
    score_threshold: float,
    depth: RetrievalDepth | None,
    max_tokens: int,
) -> tuple[str, str]:
    """构造语义缓存的 filter / params 签名。

    检索结果取决于这些参数，必须全部进缓存 key，否则不同参数会互相污染。
    `ren`（RERANK_ENABLED）也要进：同一 query 在开关开/关时结果是两种证据。
    """
    filter_sig = json.dumps(filter, sort_keys=True) if filter else ""
    params_sig = (
        f"rr={int(use_rerank)}|ren={int(settings.RERANK_ENABLED)}|k={k}|"
        f"thr={score_threshold}|depth={depth.depth if depth else 'auto'}|mt={max_tokens}"
    )
    return filter_sig, params_sig


async def _lookup_cached(
    query: str, collection_name: str, filter_sig: str, params_sig: str
) -> FusedEvidence | None:
    """语义缓存命中则标注并返回；缓存异常只记 debug，不影响检索。"""
    try:
        from rag.retrieval.semantic_cache import get_semantic_cache

        cached_fused, sim = await get_semantic_cache().alookup(
            query,
            collection_name=collection_name,
            filter_sig=filter_sig,
            params_sig=params_sig,
        )
        if cached_fused is not None:
            cached_fused.metadata["semantic_cache_hit"] = True
            cached_fused.metadata["semantic_cache_similarity"] = round(sim, 4)
            _emit_evidence_metric(
                query=query,
                collection_name=collection_name,
                start=time.perf_counter(),
                fused=cached_fused,
            )
            return cached_fused
    except Exception as _sc_err:
        logger.debug("Async semantic cache lookup skipped: %s", _sc_err)
    return None


async def _store_cached(
    query: str, fused: FusedEvidence, collection_name: str, filter_sig: str, params_sig: str
) -> None:
    """把本次结果写入语义缓存；缓存异常只记 debug。"""
    try:
        from rag.retrieval.semantic_cache import get_semantic_cache

        await get_semantic_cache().astore(
            query,
            fused,
            collection_name=collection_name,
            filter_sig=filter_sig,
            params_sig=params_sig,
        )
    except Exception as _sc_err:
        logger.debug("Async semantic cache store skipped: %s", _sc_err)


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


async def _verify_fused(fused: FusedEvidence, query: str) -> None:
    """规则验证并写入 `evidence_verdict`；失败只 warning。"""
    from rag.retrieval.verifier import averify_evidence

    try:
        verification = await averify_evidence(fused, query=query, use_llm=False)
        fused.metadata["evidence_verdict"] = verification.model_dump(mode="json")
    except Exception as e:
        logger.warning("Async evidence verification failed: %s", e)


def _empty_fused(
    query: str,
    use_rerank: bool,
    plan: _EvidencePlan,
    score_threshold: float,
    latency_ms: float,
    rerank_bridge: dict,
) -> FusedEvidence:
    """无候选时的空证据包。"""
    return FusedEvidence(
        final_context="",
        sources=[],
        metadata={
            "query": query,
            "result_count": 0,
            "k": plan.effective_k,
            "use_rerank": use_rerank,
            "retrieval_depth": plan.depth.depth,
            "retrieval_layer": plan.layer,
            "route_type": plan.route_type,
            "score_threshold": score_threshold,
            "retrieval_latency_ms": latency_ms,
            "rerank_latency_ms": None,
            # ★ B2（修复批 Important-3）：**空包分支同样写 `rerank_status`** ——
            #   旧版这里根本没有该键，`_stage_rerank` 算出的 off/degraded/failed
            #   被整包丢弃（实测 28 份归档 / 433 条记录、9 份基线含该字段 = 0）。
            #   桥接处异常早于重排 ⇒ 出参没写 ⇒ 落 `""`（未知，不回填，与非空分支同律）。
            "rerank_status": rerank_bridge.get("rerank_status", ""),
        },
    )


async def _assemble_fused(
    docs: list,
    query: str,
    collection_name: str,
    max_tokens: int,
    score_threshold: float,
    use_rerank: bool,
    plan: _EvidencePlan,
    latency_ms: float,
    rerank_bridge: dict,
) -> FusedEvidence:
    """把底层检索到的 docs 组装成 FusedEvidence（空包分支同样写 `rerank_status`）。"""
    if not docs:
        return _empty_fused(query, use_rerank, plan, score_threshold, latency_ms, rerank_bridge)

    from rag.retrieval.fusion import afuse_documents

    fused = await afuse_documents(
        docs,
        query=query,
        max_tokens=max_tokens,
        depth=plan.depth.depth,
    )
    fused.metadata["query"] = query
    fused.metadata["collection"] = collection_name
    fused.metadata["result_count"] = len(docs)
    fused.metadata["k"] = docs[0].metadata.get("_effective_k", plan.effective_k)
    fused.metadata["use_rerank"] = use_rerank
    # 「实际是否重排」与「调用方是否要求重排」是两件事（部署开关可能否决后者）。
    # 门禁的 disabled 路由靠它断言 rerank_used 未被谎报。
    # ★ B2：新增 tier-0 `rerank_status`（off/success/degraded/failed），
    #   `rerank_used` 由 pipeline 侧从 `rerank_status == "success"` **派生**后传下来；
    #   这里读新字段缺 ⇒ ""（未知，按旧口径处理，**不回填**）。
    fused.metadata["rerank_status"] = docs[0].metadata.get("_rerank_status", "")
    fused.metadata["rerank_used"] = docs[0].metadata.get("_rerank_used")
    fused.metadata["retrieval_depth"] = docs[0].metadata.get("_retrieval_depth", plan.depth.depth)
    fused.metadata["retrieval_layer"] = docs[0].metadata.get("_retrieval_layer")
    fused.metadata["route_type"] = docs[0].metadata.get("_route_type")
    fused.metadata["coarse_k"] = docs[0].metadata.get("_coarse_k")
    fused.metadata["score_threshold"] = score_threshold
    fused.metadata["source_count"] = len(fused.sources)
    fused.metadata["async_decompose_ms"] = plan.decompose_ms
    fused.metadata["retrieval_latency_ms"] = latency_ms
    fused.metadata["rerank_latency_ms"] = None
    return fused


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


async def _with_topup(
    query: str,
    preferred_layers: Sequence[str] | None,
    allowed: list[str],
    fused: FusedEvidence,
    eligibility_where: dict | None,
) -> FusedEvidence:
    """候选池 top-up；preferred 层与资格冲突时收敛到合规层（保证池不空）。"""
    layers = list(preferred_layers or [])
    if not layers:
        return fused
    from rag.retrieval.layer_recall import topup_preferred_layers

    # ★ 资格一致（2026-10-01）：preferred 层若与 eligibility 矛盾（如 practice 偏好 exams，
    #   而 exam_resources 全 forbidden），top-up 只按 kb_depth 找会被 where 挡空 →
    #   主池可能**完全为空**（证据包被掏空）。此处把 preferred 收敛到合规层：
    #   全部冲突时回退到「全部合规层」，保证池不空。生产 policy 恒一致，不影响默认行为。
    if allowed and layers and all(ly not in allowed for ly in layers):
        layers = list(allowed)
    return await topup_preferred_layers(query, layers, fused, eligibility_where=eligibility_where)


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


async def _llm_verify(fused: FusedEvidence, query: str) -> VerificationResult:
    """跑 LLM 验证并把 verdict 写回 metadata。"""
    from rag.retrieval.verifier import averify_evidence

    result = await averify_evidence(fused, query=query, use_llm=True)
    fused.metadata["evidence_verdict"] = result.model_dump(mode="json")
    return result


def _apply_retry_hints(current_kwargs: dict, hints: dict) -> None:
    """把 verify 给出的 retry hints 落到下次检索参数上（就地改 `current_kwargs`）。"""
    if "k" in hints:
        current_kwargs["k"] = hints["k"]
        if current_kwargs.get("depth") and current_kwargs["depth"].depth == "shallow":
            current_kwargs["depth"] = L2_STANDARD.depth
    if "score_threshold" in hints:
        current_kwargs["score_threshold"] = hints["score_threshold"]
    if "max_tokens" in hints:
        current_kwargs["max_tokens"] = hints["max_tokens"]
    if "use_rerank" in hints:
        current_kwargs["use_rerank"] = hints["use_rerank"]


async def _verify_with_optional_retry(
    fused: FusedEvidence,
    query: str,
    *,
    current_kwargs: dict,
    allowed: list[str],
    preferred_layers: Sequence[str] | None,
    eligibility_where: dict | None,
    attempts_allowed: int,
) -> tuple[FusedEvidence, VerificationResult, int]:
    """LLM verify；命中 hints 时按 hints 重试**一次**。返回 (fused, result, 实际重试次数)。"""
    from rag.retrieval.verifier import Verdict

    result = await _llm_verify(fused, query)
    if not (attempts_allowed and result.verdict != Verdict.PASS and result.retry_hints):
        return fused, result, 0

    hints = result.retry_hints
    _apply_retry_hints(current_kwargs, hints)
    logger.info(
        "Async verify retry (once) for query=%s verdict=%s hints=%s",
        query[:40],
        result.verdict.value,
        hints,
    )
    fused = await _with_topup(
        query,
        preferred_layers,
        allowed,
        await aretrieve_evidence(**current_kwargs),
        eligibility_where,
    )
    result = await _llm_verify(fused, query)
    return fused, result, 1


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
    current_kwargs: dict,
    allowed: list[str],
    preferred_layers: Sequence[str] | None,
    eligibility_where: dict | None,
    max_retries: int,
    use_llm_verify: bool,
) -> tuple[FusedEvidence, VerificationResult]:
    """可选 LLM verify + 最多一次 retry，并上报检索入口指标。"""
    if use_llm_verify:
        # 可选路径：LLM verify + 最多 1 次 retry（设计定稿：不维护多轮重试）
        attempts_allowed = 1 if max_retries > 0 else 0
        fused, result, retry_count = await _verify_with_optional_retry(
            fused,
            query,
            current_kwargs=current_kwargs,
            allowed=allowed,
            preferred_layers=preferred_layers,
            eligibility_where=eligibility_where,
            attempts_allowed=attempts_allowed,
        )
    else:
        # 默认路径：不 verify / 不 retry —— 规则 verdict 已在 aretrieve_evidence 内写入 metadata
        result = _verdict_from(fused)
        attempts_allowed = retry_count = 0

    _emit_evidence_metric(
        query=query,
        collection_name=collection_name,
        start=retry_metric_start,
        fused=fused,
        retry_count=retry_count,
        max_retries=attempts_allowed,
        use_llm_verify=use_llm_verify,
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
    max_retries: int = 1,
    use_llm_verify: bool = False,
    preferred_layers: Sequence[str] | None = None,
    eligible_layers: Sequence[str] | None = None,
) -> tuple[FusedEvidence, VerificationResult]:
    """异步检索入口：默认**不走** verify/retry，可选 LLM verify + 最多 1 次 retry。

    路径：

        use_llm_verify?
           │
           ├─ False（默认）→ 直接返回
           │    规则 verdict 已在 aretrieve_evidence 内写入 metadata，
           │    不再二次 verify、不触发 retry。
           │
           └─ True → LLM verify → 必要时 retry **1 次** → 再 verify

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
        current_kwargs=current_kwargs,
        allowed=allowed,
        preferred_layers=preferred_layers,
        eligibility_where=filter,
        max_retries=max_retries,
        use_llm_verify=use_llm_verify,
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
