"""Synthesis Agent -- merge multi-agent outputs into a unified final answer.

Receives outputs from parallel retrieval agents (text_retrieval, kg_retrieval,
knowledge_agent) and synthesizes them according to the ExecutionPlan's strategy.

Handles:
- Same-topic deduplication (keep most detailed version)
- Contradiction detection and annotation
- Gap identification (explicitly mark uncovered aspects)
- Full source attribution (every claim linked to its origin agent)
"""

from __future__ import annotations

import logging

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# -- Data Models --

class AgentOutput(BaseModel):
    agent_name: str = Field(description="Agent that produced this output")
    subtask_id: str = Field(description="Which subtask this answers")
    content: str = Field(description="Agent's answer text")
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)


class SynthesisResult(BaseModel):
    final_answer: str = Field(description="Merged and polished final answer")
    contradictions: list[str] = Field(default_factory=list)
    missing_aspects: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)


# -- Synthesis Prompt --

SYNTHESIS_SYSTEM_PROMPT = """You are an answer synthesis agent for a 408 CS exam tutoring system.
Your job is to merge outputs from multiple parallel retrieval agents into a single coherent answer.

[Synthesis Rules]
1. Same knowledge point from multiple agents -> keep the most detailed version, note which agent provided it.
2. Contradictory information -> explicitly mark "[There is debate]" and list both sides with their sources.
3. Missing/uncovered aspects -> explicitly mark "[Not found in knowledge base]" rather than fabricating.
4. Every source agent must be cited in the answer.
5. Use well-structured Markdown with Chinese formatting: headings, lists, tables where appropriate.

[Output Format]
Return ONLY the merged answer text (no JSON wrapper, no metadata).
Structure:
1. Direct answer to the student's question
2. Key points with source attribution (e.g. "[from text_retrieval]")
3. If contradictions exist: a "Controversy" section
4. If gaps exist: an "Uncovered aspects" section
5. Sources summary at the end
"""

SYNTHESIS_USER_TEMPLATE = """Original student question: {query}

Synthesis strategy: {strategy}

Agent outputs:
{agent_outputs}

Please synthesize these into a single coherent answer following the rules above."""


# -- Synthesis Logic --

def _format_agent_outputs(outputs: list[AgentOutput]) -> str:
    """Format agent outputs for the synthesis prompt."""
    parts: list[str] = []
    for i, out in enumerate(outputs, 1):
        parts.append(
            f"--- Agent {i}: {out.agent_name} (subtask: {out.subtask_id}, confidence: {out.confidence:.2f}) ---\n"
            f"{out.content}"
        )
    return "\n\n".join(parts)


def _deduplicate_outputs(outputs: list[AgentOutput]) -> list[AgentOutput]:
    """Remove near-duplicate outputs (same content, keep highest confidence)."""
    if len(outputs) <= 1:
        return outputs

    kept: list[AgentOutput] = []
    seen_signatures: set[str] = set()

    # Sort by confidence descending, so higher-confidence wins on duplicates
    sorted_outputs = sorted(outputs, key=lambda o: o.confidence, reverse=True)

    for out in sorted_outputs:
        # Signature: first 200 chars of content as dedup key
        sig = out.content[:200].strip()
        if sig and sig not in seen_signatures:
            kept.append(out)
            seen_signatures.add(sig)
        elif not sig:
            kept.append(out)  # Keep empty outputs (they indicate "not found")

    return kept


async def synthesize(
    query: str,
    agent_outputs: list[AgentOutput],
    strategy: str = "merge",
) -> SynthesisResult:
    """Synthesize multi-agent outputs into a unified answer.

    Args:
        query: Original student question
        agent_outputs: Outputs from each parallel agent
        strategy: merge | compare | chain

    Returns:
        SynthesisResult with final answer, contradictions, gaps, sources
    """
    if not agent_outputs:
        return SynthesisResult(
            final_answer="No results were retrieved from any agent. Please try rephrasing your question.",
            missing_aspects=["All agents returned empty results"],
            confidence=0.0,
        )

    # Single agent output -> no synthesis needed, just format
    if len(agent_outputs) == 1:
        out = agent_outputs[0]
        return SynthesisResult(
            final_answer=out.content,
            sources=[out.agent_name],
            confidence=out.confidence,
        )

    # Deduplicate before synthesis
    deduped = _deduplicate_outputs(agent_outputs)
    if len(deduped) == 1:
        out = deduped[0]
        return SynthesisResult(
            final_answer=out.content,
            sources=[out.agent_name],
            confidence=out.confidence,
        )

    try:
        from app.rag.rag_utils import get_llm

        llm = get_llm(streaming=False, temperature=0.0)

        formatted = _format_agent_outputs(deduped)
        user_prompt = SYNTHESIS_USER_TEMPLATE.format(
            query=query,
            strategy=strategy,
            agent_outputs=formatted,
        )

        messages = [
            {"role": "system", "content": SYNTHESIS_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]

        response = await llm.ainvoke(messages)
        final_answer = response.content if hasattr(response, "content") else str(response)

        # Collect sources
        sources = [out.agent_name for out in deduped]

        # Average confidence
        avg_confidence = sum(out.confidence for out in deduped) / len(deduped)

        logger.info(
            "Synthesis complete: %d inputs -> %d deduped, strategy=%s, confidence=%.2f",
            len(agent_outputs), len(deduped), strategy, avg_confidence,
        )

        return SynthesisResult(
            final_answer=str(final_answer).strip(),
            sources=sources,
            confidence=round(avg_confidence, 4),
        )

    except Exception as e:
        logger.error("Synthesis failed: %s, falling back to concatenation", e)
        # Fallback: simple concatenation with dividers
        parts: list[str] = [f"## Combined answer for: {query}\n"]
        sources = []
        for out in deduped:
            parts.append(f"### From {out.agent_name} (subtask: {out.subtask_id})\n{out.content}")
            sources.append(out.agent_name)

        return SynthesisResult(
            final_answer="\n\n".join(parts),
            sources=sources,
            confidence=0.3,
            missing_aspects=["Synthesis via LLM failed, showing raw agent outputs"],
        )
