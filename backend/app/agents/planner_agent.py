"""Planner Agent -- decompose complex student queries into parallel subtasks.

Triggered by supervisor when Adaptive Depth resolves to "deep" (comparison,
long structured, cross-discipline queries). Simple queries bypass the planner
and go directly to a single agent (existing fast path).

Output: ExecutionPlan consumed by LangGraph Send fan-out.
"""

from __future__ import annotations

import json
import logging

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class SubTask(BaseModel):
    id: str = Field(description="Unique subtask ID")
    query: str = Field(description="The specific sub-query to retrieve/answer")
    recommended_agent: str = Field(
        default="text_retrieval",
        description="Target agent: text_retrieval | kg_retrieval | knowledge_agent",
    )
    reasoning: str = Field(default="", description="Why this subtask is needed")


class ExecutionPlan(BaseModel):
    sub_tasks: list[SubTask] = Field(description="Decomposed subtasks")
    synthesis_strategy: str = Field(
        default="merge",
        description="merge | compare | chain",
    )
    stop_condition: str = Field(
        default="all_complete",
        description="all_complete | any_failed | timeout",
    )
    complexity: str = Field(default="standard", description="simple | standard | complex")


PLANNER_SYSTEM_PROMPT = """You are a query decomposition planner for a 408 CS exam tutoring system.
Break complex student questions into independent sub-tasks for parallel retrieval agents.

[Agent Types Available]
- text_retrieval: searches textbook content for concept definitions, principle explanations
- kg_retrieval: queries the knowledge graph for prerequisite relationships, learning paths
- knowledge_agent: general-purpose agent for both text and KG queries (fallback)

[Decomposition Rules]
1. Single-discipline concept question -> 1 subtask (text_retrieval)
2. Cross-discipline comparison -> 1 subtask per discipline + 1 comparison subtask (knowledge_agent)
3. Prerequisite/dependency question -> 1 subtask (kg_retrieval)
4. Learning path question -> 1 subtask (kg_retrieval) + 1 subtask (text_retrieval)
5. Code/algorithm question -> 1 subtask for steps + 1 for analysis

[Output Format]
Return ONLY a JSON object (no markdown):
{
  "sub_tasks": [{"id": "t1", "query": "...", "recommended_agent": "text_retrieval", "reasoning": "..."}],
  "synthesis_strategy": "merge",
  "complexity": "standard"
}
"""

PLANNER_USER_TEMPLATE = """Student question: {query}

Query classification: {category}

Decompose into parallel sub-tasks. If simple, return exactly 1 subtask."""



def _parse_plan(raw_text: str) -> ExecutionPlan | None:
    """Parse LLM output into ExecutionPlan, with error tolerance."""
    text = (raw_text or "").strip()
    if text.startswith("```"):
        lines = text.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines)

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}") + 1
        if start < 0 or end <= start:
            logger.warning("Planner: cannot extract JSON from output")
            return None
        try:
            data = json.loads(text[start:end])
        except json.JSONDecodeError:
            logger.warning("Planner: JSON parse failed after extraction")
            return None

    sub_tasks_raw = data.get("sub_tasks", [])
    if not sub_tasks_raw:
        return None

    sub_tasks: list[SubTask] = []
    for i, st in enumerate(sub_tasks_raw):
        sub_tasks.append(SubTask(
            id=str(st.get("id", f"t{i+1}")),
            query=str(st.get("query", "")).strip(),
            recommended_agent=str(st.get("recommended_agent", "text_retrieval")),
            reasoning=str(st.get("reasoning", "")),
        ))

    valid_agents = {"text_retrieval", "kg_retrieval", "knowledge_agent"}
    for st in sub_tasks:
        if st.recommended_agent not in valid_agents:
            st.recommended_agent = "knowledge_agent"

    return ExecutionPlan(
        sub_tasks=sub_tasks,
        synthesis_strategy=str(data.get("synthesis_strategy", "merge")),
        complexity=str(data.get("complexity", "standard")),
    )


async def create_plan(
    query: str,
    category: str = "",
) -> ExecutionPlan:
    """Decompose a student query into an ExecutionPlan."""
    try:
        from app.rag.rag_utils import get_llm

        llm = get_llm(streaming=False, temperature=0.0)
        user_prompt = PLANNER_USER_TEMPLATE.format(query=query, category=category)

        messages = [
            {"role": "system", "content": PLANNER_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]

        response = await llm.ainvoke(messages)
        raw = response.content if hasattr(response, "content") else str(response)

        plan = _parse_plan(str(raw))
        if plan is None:
            logger.warning("Planner: parse failed, falling back to single subtask")
            return ExecutionPlan(
                sub_tasks=[SubTask(
                    id="t1", query=query,
                    recommended_agent="knowledge_agent",
                    reasoning="Fallback: planner parse failed",
                )],
                synthesis_strategy="merge",
                complexity="simple",
            )

        logger.info(
            "Planner: %d subtasks, strategy=%s, complexity=%s",
            len(plan.sub_tasks), plan.synthesis_strategy, plan.complexity,
        )
        for st in plan.sub_tasks:
            logger.debug("  subtask %s -> %s: %s", st.id, st.recommended_agent, st.query[:60])

        return plan

    except Exception as e:
        logger.error("Planner failed: %s, falling back to single subtask", e)
        return ExecutionPlan(
            sub_tasks=[SubTask(
                id="t1", query=query,
                recommended_agent="knowledge_agent",
                reasoning=f"Fallback: planner error ({e})",
            )],
            synthesis_strategy="merge",
            complexity="simple",
        )


def should_use_planner(complexity: str, category_flags: list[str]) -> bool:
    """Determine if a query is complex enough to warrant the planner."""
    if complexity == "simple":
        return False
    if "comparison" in category_flags:
        return True
    if complexity == "complex":
        return True
    if "learning_path" in category_flags and "long" in category_flags:
        return True
    return False
