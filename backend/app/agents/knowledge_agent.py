import logging

from langchain_core.tools import tool

from app.rag.retriever import aretrieve_evidence_with_retry
from app.rag.query_classifier import TEXT_ONLY_DEPTH
from app.agents.kg_tools import akg_search
from app.agents.prompts import KNOWLEDGE_AGENT_SYSTEM_PROMPT as KNOWLEDGE_AGENT_PROMPT
from app.agents.agent_factory import ReactAgentSpec, create_react_tool_agent

logger = logging.getLogger(__name__)


# -- Tool 1: Pure text retrieval (no KG) --

@tool("text_search")
async def atext_search(query: str) -> str:
    """Pure textbook text retrieval (multi-recall + BM25 + Reranker).
    No knowledge graph involved. Use for quick concept definitions, principle explanations.
    For knowledge dependencies or learning paths, use kg_search instead."""
    try:
        fused, verification = await aretrieve_evidence_with_retry(
            query=query,
            k=5,
            use_rerank=True,
            depth=TEXT_ONLY_DEPTH,
            max_retries=1,
            use_llm_verify=False,
        )
        if not fused.final_context:
            return "No relevant textbook content found."
        result = fused.final_context
        if fused.sources:
            result += f"\n\nSources: {', '.join(fused.sources[:5])}"
        if verification.verdict.value != "pass" and verification.reasons:
            result += f"\n\nEvidence quality: {verification.verdict.value}; {'; '.join(verification.reasons[:2])}"
        return result
    except Exception as e:
        logger.error("Text search failed: %s", e, exc_info=True)
        return f"Text search failed: {e}"


# -- Tool 2: Aggregate retrieval (text + KG) --

@tool("knowledge_search")
async def aknowledge_search(query: str) -> str:
    """Aggregate knowledge base search (text + knowledge graph).
    One-stop retrieval for both textbook content and knowledge relationships.
    Best for most queries needing both concept explanation and dependency context.
    For text-only, use text_search. For KG-only, use kg_search."""
    try:
        fused, verification = await aretrieve_evidence_with_retry(
            query=query,
            k=5,
            use_rerank=True,
            max_retries=1,
            use_llm_verify=False,
        )
        if not fused.final_context:
            return "No relevant content found in knowledge base."
        result = fused.final_context
        if fused.sources:
            result += f"\n\nSources: {', '.join(fused.sources[:5])}"
        if verification.verdict.value != "pass" and verification.reasons:
            result += f"\n\nEvidence quality: {verification.verdict.value}; {'; '.join(verification.reasons[:2])}"
        return result
    except Exception as e:
        logger.error("Knowledge search failed: %s", e, exc_info=True)
        return f"Knowledge search failed: {e}"


def create_knowledge_agent():
    """Create knowledge agent with 3-tool layered retrieval."""
    return create_react_tool_agent(
        ReactAgentSpec(
            name="knowledge_agent",
            prompt=KNOWLEDGE_AGENT_PROMPT,
            tools=[
                aknowledge_search,
                atext_search,
                akg_search,
            ],
        )
    )
