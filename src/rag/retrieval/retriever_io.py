"""检索证据包的量测/缓存/组装辅助（从 retriever.py 拆出，行为等价）。

★ 本模块不与 `rag.retrieval.retriever` 互相导入（无环）。
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Sequence
from dataclasses import dataclass

from core.settings import settings
from rag.common.metrics import metrics
from rag.retrieval.evidence import FusedEvidence
from rag.retrieval.query_classifier import QueryCategory, RetrievalDepth

logger = logging.getLogger(__name__)


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
