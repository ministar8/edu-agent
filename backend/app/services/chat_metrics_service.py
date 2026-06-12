from __future__ import annotations

import time
from collections.abc import Callable

from app.rag.metrics import metrics
from app.rag.rag_utils import estimate_tokens


def make_metric_emitter(
    *,
    endpoint: str,
    query: str,
    route_type: str,
    start_time: float,
) -> Callable:
    def emit(
        agent_name: str,
        final_answer: str = "",
        sources: list[str] | None = None,
        first_token_at: float | None = None,
        governance: dict | None = None,
        evidence_metadata: dict | None = None,
        agent_steps: list[dict] | None = None,
        status: str = "ok",
        error_type: str = "",
    ) -> None:
        emit_chat_baseline_metric(
            endpoint=endpoint,
            query=query,
            route_type=route_type,
            agent_name=agent_name,
            start_time=start_time,
            final_answer=final_answer,
            sources=sources,
            first_token_at=first_token_at,
            governance=governance,
            evidence_metadata=evidence_metadata,
            agent_steps=agent_steps,
            status=status,
            error_type=error_type,
        )

    return emit


def emit_chat_baseline_metric(
    *,
    endpoint: str,
    query: str,
    route_type: str,
    agent_name: str,
    start_time: float,
    final_answer: str = "",
    sources: list[str] | None = None,
    first_token_at: float | None = None,
    governance: dict | None = None,
    evidence_metadata: dict | None = None,
    agent_steps: list[dict] | None = None,
    status: str = "ok",
    error_type: str = "",
) -> None:
    sources = sources or []
    governance = governance or {}
    evidence_metadata = evidence_metadata or {}
    agent_steps = agent_steps or []
    total_ms = round((time.perf_counter() - start_time) * 1000, 3)
    first_token_ms = round((first_token_at - start_time) * 1000, 3) if first_token_at is not None else None
    prompt_tokens = estimate_tokens(query or "")
    completion_tokens = estimate_tokens(final_answer or "")
    raw_evidence_verdict = governance.get("evidence_verdict", evidence_metadata.get("evidence_verdict", ""))
    if isinstance(raw_evidence_verdict, dict):
        evidence_verdict = raw_evidence_verdict.get("verdict", "")
        evidence_score = raw_evidence_verdict.get("overall_score", evidence_metadata.get("evidence_score", 0.0))
    else:
        evidence_verdict = raw_evidence_verdict
        evidence_score = governance.get("evidence_score", evidence_metadata.get("evidence_score", 0.0))
    metrics.emit_chat_baseline(
        endpoint=endpoint,
        query=query,
        route_type=route_type,
        agent_name=agent_name,
        status=status,
        duration_ms=total_ms,
        values={
            "total_latency_ms": total_ms,
            "first_token_ms": first_token_ms,
            "answer_chars": len(final_answer or ""),
            "answer_tokens_est": completion_tokens,
            "query_tokens_est": prompt_tokens,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "llm_call_count": evidence_metadata.get("llm_call_count", 1 if final_answer else 0),
            "embedding_call_count": evidence_metadata.get("embedding_call_count", 0),
            "reranker_call_count": evidence_metadata.get("reranker_call_count", 1 if evidence_metadata.get("use_rerank") else 0),
            "source_count": len(sources),
            "agent_step_count": len(agent_steps),
            "governance_confidence": governance.get("confidence", ""),
            "governance_passed": governance.get("passed", None),
            "governance_flags": governance.get("flags", []),
            "evidence_verdict": evidence_verdict,
            "evidence_score": evidence_score,
            "retrieval_depth": evidence_metadata.get("retrieval_depth", ""),
            "retrieval_layer": evidence_metadata.get("retrieval_layer", ""),
            "retrieval_route_type": evidence_metadata.get("route_type", ""),
            "text_evidence_count": evidence_metadata.get("text_evidence_count", 0),
            "hit_docs_count": evidence_metadata.get("result_count", evidence_metadata.get("text_evidence_count", 0)),
            "used_evidence_count": evidence_metadata.get("text_evidence_count", 0),
            "kg_used": evidence_metadata.get("kg_used", False),
            "kg_skipped": evidence_metadata.get("kg_skipped", False),
            "hyde_triggered": evidence_metadata.get("hyde_triggered", False),
            "verifier_retry_triggered": bool(evidence_metadata.get("retry_count", 0)),
            "agentic_path_triggered": route_type in {"graph_stream", "graph_non_stream"},
            "context_tokens": evidence_metadata.get("context_tokens", 0),
            "retrieval_latency_ms": evidence_metadata.get("retrieval_latency_ms", None),
            "rerank_latency_ms": evidence_metadata.get("rerank_latency_ms", None),
            "kg_latency_ms": evidence_metadata.get("kg_latency_ms", None),
            "generation_latency_ms": evidence_metadata.get("generation_latency_ms", None),
            "governance_latency_ms": evidence_metadata.get("governance_latency_ms", None),
            "semantic_cache_hit": evidence_metadata.get("semantic_cache_hit", False),
            "semantic_cache_similarity": evidence_metadata.get("semantic_cache_similarity", 0.0),
            "error_type": error_type,
        },
    )
