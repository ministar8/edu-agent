"""证据校验辅助（从 retriever.py 拆出，行为等价）。

★ 2026-10-15 owner 裁定 B5：随 LLM 校验层整层删除，原 `_llm_verify`（use_llm=True
  专用）与 `_apply_retry_hints`（重试 hints 落地，仅 LLM verify 路径消费）一并移除；
  本模块余下 `_verdict_from`（取 aretrieve_evidence 已写入的规则 verdict）与
  `_evidence_kwargs`（主路径调参字典）。
"""

from __future__ import annotations

import logging

from rag.retrieval.evidence import FusedEvidence
from rag.retrieval.pipeline import StageSink
from rag.retrieval.query_classifier import RetrievalDepth
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
