"""证据校验与重试参数辅助（从 retriever.py 拆出，行为等价）。"""

from __future__ import annotations

import logging

from rag.retrieval.evidence import FusedEvidence
from rag.retrieval.pipeline import StageSink
from rag.retrieval.query_classifier import RetrievalDepth
from rag.retrieval.retrieval_plan import L2_STANDARD
from rag.retrieval.verifier import VerificationResult

logger = logging.getLogger(__name__)


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
