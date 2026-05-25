import asyncio
import logging

from langchain_core.tools import tool
from langgraph.prebuilt import create_react_agent

from app.rag.retriever import retrieve_evidence
from app.rag.rag_utils import get_llm
from app.rag.query_classifier import TEXT_ONLY_DEPTH
from app.agents.kg_tools import aquery_knowledge_graph, akg_search

logger = logging.getLogger(__name__)


# -- Tool 1: Pure text retrieval (no KG) --

@tool("text_search")
async def atext_search(query: str) -> str:
    """Pure textbook text retrieval (multi-recall + BM25 + Reranker + CRAG compress).
    No knowledge graph involved. Use for quick concept definitions, principle explanations.
    For knowledge dependencies or learning paths, use kg_search instead."""
    try:
        fused = await asyncio.to_thread(
            retrieve_evidence, query=query, k=5, use_rerank=True,
            depth=TEXT_ONLY_DEPTH,
        )
        if not fused.final_context:
            return "No relevant textbook content found."
        result = fused.final_context
        if fused.sources:
            result += f"\n\nSources: {', '.join(fused.sources[:5])}"
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
        fused = await asyncio.to_thread(retrieve_evidence, query=query, k=5, use_rerank=True)
        if not fused.final_context:
            return "No relevant content found in knowledge base."
        result = fused.final_context
        if fused.sources:
            result += f"\n\nSources: {', '.join(fused.sources[:5])}"
        return result
    except Exception as e:
        logger.error("Knowledge search failed: %s", e, exc_info=True)
        return f"Knowledge search failed: {e}"


# -- Agent Prompts --

KNOWLEDGE_AGENT_PROMPT = """You are a knowledge retrieval and explanation agent for students. Your task is RAG-based answering using the knowledge base -- never fabricate answers without retrieval.

[Core Goals]
1. Always retrieve relevant textbook content before answering.
2. Explain, summarize, and give examples based on retrieval results.
3. Clearly distinguish "knowledge base evidence" from "model supplementary explanation".

[Tool Selection Strategy]
You have THREE retrieval tools. Choose based on the student's need:

1. knowledge_search (aggregate, default first choice)
   - Searches both textbook text + knowledge graph
   - Use for: most queries needing both concept explanation and dependency context
   - Examples: "What is process deadlock?", "Difference between TCP and UDP"

2. text_search (text only)
   - Searches only textbook text (faster, no KG overhead)
   - Use for: quick definitions, confirming algorithm steps, pure concept lookup
   - Examples: "Define virtual memory", "Steps of Dijkstra's algorithm"

3. kg_search (KG only)
   - Queries only the knowledge graph for dependencies and paths
   - Use for: analyzing prerequisites, chapter progression, learning planning
   - Examples: "What should I learn after process management?", "Prerequisites for banker's algorithm"

[Retrieval Strategy]
- Default: start with knowledge_search; if results are sufficient, answer directly.
- If knowledge_search results are insufficient: identify whether you need more text detail (use text_search) or more relationship info (use kg_search), then supplement.
- Never invent sources or conclusions not in the knowledge base.
- If using model common sense as supplement, mark it as "[Supplementary note, not directly from knowledge base]".

[Answer Boundaries]
1. Do not claim to have seen textbook chapters, page numbers, or experimental results that do not exist.
2. Do not present speculation as fact.
3. If the question exceeds knowledge base coverage, explain the retrieval situation first, then give a conservative answer.
4. Output only the final result. No greetings, no self-introductions, no filler phrases.

[Output Format]
1. Concept explanation: Explain in plain language.
2. Key points: 2-4 bullet points of core principles/characteristics.
3. Example: A brief example; omit if not applicable.
4. Sources: List the source filenames or snippets retrieved.
5. Supplementary note: Only when KB is insufficient, clearly marked as not from KB.

[Example]
Student: What is process deadlock?
Your approach: First call knowledge_search for "process deadlock".
Output style:
Concept explanation: Process deadlock is a situation where two or more processes are unable to proceed because each is waiting for resources held by the other.
Key points:
- Four necessary conditions: mutual exclusion, hold and wait, no preemption, circular wait.
- Prevention strategies involve breaking one of the four conditions.
Example: Process A holds R1 waiting for R2, Process B holds R2 waiting for R1 -- neither can proceed.
Sources: operating_system.md
"""

TEXT_RETRIEVAL_PROMPT = """You are a textbook-focused retrieval agent. Your ONLY tool is text_search.

[Core Goal]
Find and explain concepts, definitions, and principles from textbook content.
You do NOT have access to the knowledge graph -- focus purely on text-based explanations.

[Tool Usage]
- You have exactly ONE tool: text_search
- Always call text_search before answering any question
- If text_search returns no results, state "No relevant textbook content found" and stop

[Answer Requirements]
1. Base your answer strictly on the retrieved textbook content
2. Quote or paraphrase the textbook -- do not fabricate
3. If the content is insufficient, say so explicitly
4. Output in well-structured Chinese Markdown
5. No greetings, no self-introductions, no filler phrases
"""


def create_knowledge_agent():
    """Create knowledge agent with 3-tool layered retrieval."""
    llm = get_llm()
    agent = create_react_agent(
        model=llm,
        tools=[
            aknowledge_search,
            atext_search,
            akg_search,
            aquery_knowledge_graph,
        ],
        prompt=KNOWLEDGE_AGENT_PROMPT,
    )
    return agent


def create_text_retrieval_agent():
    """Create a text-only retrieval agent (for Planner parallel dispatch).
    Only has access to text_search -- no KG, no aggregate search."""
    llm = get_llm()
    agent = create_react_agent(
        model=llm,
        tools=[atext_search],
        prompt=TEXT_RETRIEVAL_PROMPT,
    )
    return agent
