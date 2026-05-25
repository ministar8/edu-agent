"""KG shared tool definitions

Reusable across knowledge_agent / question_agent / grading_agent / path_agent.

Tool list:
  - query_knowledge_graph: Legacy KG query (returns structured text)
  - kg_search:             New KG retrieval (uses kg_evidence_from_query)
"""

import asyncio
import logging

from langchain_core.tools import tool

logger = logging.getLogger(__name__)


@tool("query_knowledge_graph")
async def aquery_knowledge_graph(topic: str) -> str:
    """Query knowledge graph for prerequisite and next-topic relationships."""
    try:
        from app.rag.knowledge_graph import get_kg_manager
        kg_manager = get_kg_manager()
        prerequisites, next_topics, learning_paths = await asyncio.gather(
            asyncio.to_thread(kg_manager.get_prerequisites, topic),
            asyncio.to_thread(kg_manager.get_next_topics, topic),
            asyncio.to_thread(kg_manager.get_learning_path, topic),
        )
        result_parts = []
        if prerequisites:
            names = [p["name"] for p in prerequisites]
            result_parts.append(f"Prerequisites: {', '.join(names)}")
        if next_topics:
            names = [n["name"] for n in next_topics]
            result_parts.append(f"Next topics: {', '.join(names)}")
        if learning_paths:
            for i, path in enumerate(learning_paths):
                steps = " -> ".join([n["name"] for n in path])
                result_parts.append(f"Learning path {i+1}: {steps}")
        if not result_parts:
            return f"No KG info found for '{topic}'."
        return "\n".join(result_parts)
    except Exception as e:
        logger.error("KG query failed for topic=%s: %s", topic, e, exc_info=True)
        return f"KG query failed (service unavailable): {e}"


@tool("kg_search")
async def akg_search(topic: str) -> str:
    """Pure KG retrieval: query prerequisites, next topics, and learning paths.
    Use for analyzing knowledge dependencies, concept relationships, and chapter progression.
    Does NOT search textbook text -- use text_search or knowledge_search for text explanations."""
    try:
        from app.rag.evidence import kg_evidence_from_query
        kg_ev = await asyncio.to_thread(kg_evidence_from_query, topic, max_depth=2)
        if kg_ev is None:
            return f"No KG match found for '{topic}'."
        parts = []
        if kg_ev.nodes:
            parts.append(f"Related topics ({len(kg_ev.nodes)}): {', '.join(kg_ev.nodes)}")
        if kg_ev.edges:
            edge_lines = [f"  {e['source']} -> {e['target']}" for e in kg_ev.edges]
            parts.append(f"Dependency edges ({len(kg_ev.edges)}):\n" + "\n".join(edge_lines))
        if kg_ev.paths:
            path_lines = [f"  Path {i+1}: {' -> '.join(p)}" for i, p in enumerate(kg_ev.paths)]
            parts.append(f"Learning paths ({len(kg_ev.paths)}):\n" + "\n".join(path_lines))
        if kg_ev.serialized:
            parts.append(f"\n{kg_ev.serialized}")
        return "\n".join(parts) if parts else f"No structured KG info for '{topic}'."
    except Exception as e:
        logger.error("KG search failed for topic=%s: %s", topic, e, exc_info=True)
        return f"KG search failed (service unavailable): {e}"


KG_RETRIEVAL_PROMPT = """You are a knowledge-graph-focused retrieval agent. Your ONLY tool is kg_search.

[Core Goal]
Query the knowledge graph to discover prerequisite topics, next topics, and learning paths.
You do NOT have access to textbook content -- focus purely on structural relationships.

[Tool Usage]
- You have exactly ONE tool: kg_search
- Always call kg_search before answering
- If kg_search returns no results, state "No KG relationships found" and stop

[Answer Format]
1. Topic resolution: What topic was matched in the KG
2. Dependencies: Prerequisites and next topics with their relationships
3. Learning paths: How this topic fits into the broader curriculum
4. Use arrow notation (A -> B) for relationships

[Answer Requirements]
1. Base your answer strictly on KG results -- do not fabricate
2. Output in well-structured Chinese Markdown
3. No greetings, no filler phrases
"""


def create_kg_retrieval_agent():
    """Create a KG-only retrieval agent (for Planner parallel dispatch)."""
    from langgraph.prebuilt import create_react_agent
    from app.rag.rag_utils import get_llm
    llm = get_llm()
    agent = create_react_agent(model=llm, tools=[akg_search], prompt=KG_RETRIEVAL_PROMPT)
    return agent
