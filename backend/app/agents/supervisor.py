import asyncio
import inspect
import logging
import time
import operator
from typing import Optional
from typing_extensions import Annotated, TypedDict

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import StateGraph, START, END
from langgraph.types import Command, Send

from app.rag.rag_utils import get_llm
from app.rag.retriever import retrieve_evidence
from app.rag.query_classifier import classify_query, resolve_retrieval_depth
from app.rag.rag_utils import normalize_query_text, extract_query_terms
from app.agents.knowledge_agent import create_knowledge_agent
from app.agents.question_agent import create_question_agent
from app.agents.grading_agent import create_grading_agent
from app.agents.path_agent import create_path_agent
from app.agents.answer_governance import govern_answer
from app.agents.reflection_agent import reflect, apply_reflection_to_answer
from app.agents.retrieval_guard import (
    GuardResult, run_retrieval_guard, build_grounding_message, extract_tool_outputs_from_messages,
)
from app.agents.memory_manager import build_scoped_context, extract_current_query, format_history_from_messages
from app.agents.trace_utils import extract_agent_steps_from_messages
from app.agents.kg_tools import akg_search

logger = logging.getLogger(__name__)


# -- State --

class AgentState(TypedDict, total=False):
    messages: list
    current_agent: str
    agent_steps: list[dict]
    final_answer: str
    guard_result: dict
    governance: dict
    # Phase 3: Planner + fan-out
    execution_plan: dict | None
    agent_outputs: Annotated[list[dict], operator.add]
    use_planner: bool
    # Per-subtask state (injected by Send)
    sub_task: dict | None


_GROUNDING_FORCE_SEARCH_PROMPT = """[System Requirement]
You MUST call at least one retrieval tool (e.g. knowledge_search, text_search, kg_search) to fetch knowledge base content,
then answer based on the retrieval results. Do NOT fabricate answers without retrieval.
If the knowledge base has no relevant content, explicitly state "No relevant content found in knowledge base".
"""

SUPERVISOR_FEW_SHOT_PROMPT = """Based on the student's question, determine which Agent should handle it. Return only the Agent name, nothing else.

Agent descriptions:
- knowledge_agent: knowledge explanation, concept clarification, principle understanding
- question_agent: generate questions, practice, tests
- grading_agent: grade answers, scoring, correctness checking
- path_agent: learning advice, study roadmap, learning planning

Examples:
Student: What is process deadlock? -> knowledge_agent
Student: Difference between TCP and UDP? -> knowledge_agent
Student: Give me 3 binary tree questions -> question_agent
Student: Test me on OS process management -> question_agent
Student: Is my answer correct? Deadlock conditions -> grading_agent
Student: Grade my homework -> grading_agent
Student: How to study computer organization? -> path_agent
Student: Recommend a study path -> path_agent
Student: Difference between process and thread? -> knowledge_agent
Student: Give me questions and grade them -> question_agent
Student: I finished process management, what's next? -> path_agent"""

_VALID_AGENTS = ("knowledge_agent", "question_agent", "grading_agent", "path_agent")


# -- Supervisor Router --

async def route_question(state: AgentState, config: Optional[RunnableConfig] = None) -> Command[str]:
    """Supervisor router with complexity detection.

    Simple queries -> direct agent routing (existing fast path).
    Complex queries -> planner_node for decomposition + parallel execution.
    """
    start_time = time.perf_counter()
    last_msg = state["messages"][-1] if state["messages"] else ""
    content = last_msg.content if hasattr(last_msg, "content") else str(last_msg)

    llm = get_llm(streaming=False, temperature=0.0)
    response = await llm.ainvoke(
        [HumanMessage(content=f"{SUPERVISOR_FEW_SHOT_PROMPT}\n\nStudent: {content}")],
        config=config,
    )
    agent_name = response.content.strip().lower()

    chosen = "knowledge_agent"
    for agent in _VALID_AGENTS:
        if agent in agent_name:
            chosen = agent
            break

    # Complexity detection for knowledge_agent queries only
    use_planner = False
    if chosen == "knowledge_agent":
        normalized = normalize_query_text(content)
        terms = extract_query_terms(normalized)
        cat = classify_query(content, terms)
        depth = resolve_retrieval_depth(cat)
        flags = [k for k in ("comparison", "long", "learning_path", "structured")
                 if getattr(cat, f"is_{k}", False)]
        if depth.depth == "deep" or "comparison" in flags:
            use_planner = True

    elapsed_ms = (time.perf_counter() - start_time) * 1000
    logger.info(
        "Supervisor route agent=%s use_planner=%s elapsed_ms=%.2f",
        chosen, use_planner, elapsed_ms,
    )

    if use_planner:
        return Command(
            goto="planner_node",
            update={"current_agent": chosen, "use_planner": True},
        )

    return Command(
        goto=chosen,
        update={"current_agent": chosen, "use_planner": False},
    )


# -- Planner Node --

async def planner_node(state: AgentState, config: Optional[RunnableConfig] = None) -> dict:
    """Decompose complex query into ExecutionPlan."""
    from app.agents.planner_agent import create_plan

    last_msg = state["messages"][-1] if state["messages"] else ""
    query = last_msg.content if hasattr(last_msg, "content") else str(last_msg)

    # Get category context
    normalized = normalize_query_text(query)
    terms = extract_query_terms(normalized)
    cat = classify_query(query, terms)
    flags = [k for k in ("comparison", "long", "concept", "code", "learning_path")
             if getattr(cat, f"is_{k}", False)]
    category_str = "+".join(flags) if flags else "general"

    plan = await create_plan(query=query, category=category_str)
    logger.info(
        "Planner: %d subtasks, strategy=%s",
        len(plan.sub_tasks), plan.synthesis_strategy,
    )

    return {
        "execution_plan": plan.model_dump(mode="json"),
        "agent_outputs": [],
    }


# -- Fan-out dispatch --

def continue_to_agents(state: AgentState):
    """Fan-out: dispatch each subtask to its recommended agent."""
    plan_dict = state.get("execution_plan")
    if not plan_dict:
        return []

    sub_tasks = plan_dict.get("sub_tasks", [])
    if not sub_tasks:
        return []

    # Single subtask -> route directly to that agent
    if len(sub_tasks) == 1:
        task = sub_tasks[0]
        agent = task.get("recommended_agent", "knowledge_agent")
        parallel_agent = {
            "knowledge_agent": "parallel_knowledge",
            "text_retrieval": "text_retrieval",
            "kg_retrieval": "kg_retrieval",
        }.get(agent, "parallel_knowledge")
        logger.info("Planner fan-out: single subtask -> %s (node: %s)", agent, parallel_agent)
        return [Send(parallel_agent, {"sub_task": task})]

    sends = []
    for task in sub_tasks:
        agent = task.get("recommended_agent", "knowledge_agent")
        # Map to parallel node names (avoid conflict with fast-path agents)
        parallel_agent = {
            "knowledge_agent": "parallel_knowledge",
            "text_retrieval": "text_retrieval",
            "kg_retrieval": "kg_retrieval",
        }.get(agent, "parallel_knowledge")
        sends.append(Send(parallel_agent, {"sub_task": task}))

    logger.info("Planner fan-out: %d sends to %s",
                len(sends), [t.get("recommended_agent") for t in sub_tasks])
    return sends


# -- Parallel Agent Nodes (Phase 3) --

async def _run_agent_node(
    state: AgentState,
    name: str,
    tool_call,
    config: Optional[RunnableConfig] = None,
) -> dict:
    """Generic parallel agent node: call tool, format output."""
    sub_task = state.get("sub_task", {})
    query = sub_task.get("query", "") if sub_task else ""
    task_id = sub_task.get("id", "unknown") if sub_task else "unknown"

    if not query:
        last_msg = state["messages"][-1] if state["messages"] else ""
        query = last_msg.content if hasattr(last_msg, "content") else str(last_msg)

    logger.info("Parallel agent %s: subtask=%s query=%s", name, task_id, query[:60])

    try:
        if inspect.iscoroutinefunction(tool_call):
            result = await tool_call(query)
        else:
            result = await asyncio.to_thread(tool_call, query)
            if inspect.isawaitable(result):
                result = await result
        content = str(result) if result else f"No results from {name}."
        confidence = 0.7 if result and "No " not in str(result)[:50] else 0.3
    except Exception as e:
        logger.error("Parallel agent %s failed: %s", name, e)
        content = f"{name} retrieval failed: {e}"
        confidence = 0.0

    output = {
        "agent_name": name,
        "subtask_id": task_id,
        "content": content,
        "confidence": confidence,
    }

    # Return single-item list; operator.add reducer merges across parallel nodes
    return {"agent_outputs": [output]}


async def text_retrieval_node(state: AgentState, config: Optional[RunnableConfig] = None) -> dict:
    """Text-only retrieval node for planner fan-out."""
    from app.agents.knowledge_agent import atext_search
    return await _run_agent_node(state, "text_retrieval", atext_search.func, config)


async def kg_retrieval_node(state: AgentState, config: Optional[RunnableConfig] = None) -> dict:
    """KG-only retrieval node for planner fan-out."""
    return await _run_agent_node(state, "kg_retrieval", akg_search.func, config)


async def parallel_knowledge_node(state: AgentState, config: Optional[RunnableConfig] = None) -> dict:
    """Specialist knowledge agent node for planner fan-out (uses full ReAct agent)."""
    sub_task = state.get("sub_task", {})
    query = sub_task.get("query", "") if sub_task else ""
    task_id = sub_task.get("id", "unknown") if sub_task else "unknown"

    if not query:
        last_msg = state["messages"][-1] if state["messages"] else ""
        query = last_msg.content if hasattr(last_msg, "content") else str(last_msg)

    logger.info("Parallel knowledge_agent: subtask=%s query=%s", task_id, query[:60])

    try:
        agent = create_knowledge_agent()
        result = await agent.ainvoke(
            {"messages": [SystemMessage(content="Answer this sub-query using the knowledge base. Be concise."),
                          HumanMessage(content=query)]},
            config=config,
        )
        if result and "messages" in result:
            answer = result["messages"][-1].content if hasattr(result["messages"][-1], "content") else str(result["messages"][-1])
        else:
            answer = "No response from knowledge_agent."
        confidence = 0.7
    except Exception as e:
        logger.error("Parallel knowledge_agent failed: %s", e)
        answer = f"knowledge_agent retrieval failed: {e}"
        confidence = 0.0

    output = {
        "agent_name": "knowledge_agent",
        "subtask_id": task_id,
        "content": answer,
        "confidence": confidence,
    }

    # Return single-item list; operator.add reducer merges across parallel nodes
    return {"agent_outputs": [output]}


# -- Synthesis Node --

async def synthesis_node(state: AgentState, config: Optional[RunnableConfig] = None) -> dict:
    """Synthesize parallel agent outputs into final answer."""
    from app.agents.synthesis_agent import synthesize, AgentOutput

    last_msg = state["messages"][-1] if state["messages"] else ""
    query = last_msg.content if hasattr(last_msg, "content") else str(last_msg)

    plan_dict = state.get("execution_plan", {})
    strategy = plan_dict.get("synthesis_strategy", "merge") if plan_dict else "merge"

    raw_outputs = state.get("agent_outputs", [])
    agent_outputs = [
        AgentOutput(
            agent_name=o.get("agent_name", "unknown"),
            subtask_id=o.get("subtask_id", "unknown"),
            content=o.get("content", ""),
            confidence=float(o.get("confidence", 0.5)),
        )
        for o in raw_outputs
    ]

    logger.info("Synthesis: %d outputs, strategy=%s", len(agent_outputs), strategy)

    result = await synthesize(query=query, agent_outputs=agent_outputs, strategy=strategy)

    # Apply governance + reflection to synthesized answer
    gov = govern_answer(result.final_answer, "knowledge_agent")
    evidence_text = "\n\n".join(o.content[:500] for o in agent_outputs if o.content)
    reflection = reflect(
        answer=gov.answer,
        evidence_text=evidence_text,
        query=query,
        agent_name="synthesis",
        use_llm=True,
    )
    if reflection.suggestion:
        gov.answer = apply_reflection_to_answer(gov.answer, reflection)

    return {
        "final_answer": gov.answer,
        "governance": {
            "confidence": gov.confidence,
            "has_source": gov.has_source,
            "passed": gov.passed,
            "flags": gov.flags,
            "reflection_confidence": reflection.confidence,
            "reflection_issues": reflection.issues,
            "synthesis_confidence": result.confidence,
        },
    }


# -- Existing Agent Wrapper (fast path, unchanged logic) --

def _wrap_agent(agent, name: str):
    """Wrap agent: two-stage governance architecture.

    Stage 1 - Pre-guard: Agent executes -> extract tool outputs -> Grounding constraint -> re-execute.
    Stage 2 - Post-governance: source check -> fabrication check -> format check.
    Stage 3 - Reflection: semantic evidence validation.
    """
    async def wrapped(state: AgentState, config: Optional[RunnableConfig] = None) -> dict:
        start_time = time.perf_counter()
        logger.info("Agent execution started agent=%s", name)

        current_query = extract_current_query(state["messages"])
        msg_types = [type(m).__name__ for m in state["messages"]]
        logger.debug("extract_current_query agent=%s query='%s' state_msgs=%d types=%s",
                     name, current_query[:50], len(state["messages"]), msg_types)
        conversation_history = format_history_from_messages(state["messages"], max_turns=6)
        messages = build_scoped_context(
            current_query=current_query,
            conversation_history=conversation_history,
        )
        messages.insert(0, SystemMessage(content="Output must use well-structured Markdown with Chinese formatting: use headings, lists, tables, or numbered steps. 408 exam questions must include question stem, answer, and explanation. Do NOT output raw JSON, debug fields, or meaningless prefixes."))

        if name in ("knowledge_agent", "grading_agent", "path_agent"):
            try:
                thread_id = (config or {}).get("configurable", {}).get("thread_id", "")
                user_id_str = thread_id.split(":")[0] if thread_id else ""
                if user_id_str.isdigit():
                    from app.services.knowledge_tracker import get_knowledge_tracker
                    tracker = get_knowledge_tracker()
                    profile_text = tracker.build_cross_session_context(int(user_id_str))
                    if profile_text:
                        messages.insert(1, SystemMessage(content=profile_text))
            except Exception as e:
                logger.debug("Student profile injection skipped: %s", e)

        retry_a = 0
        retry_b = 0
        rag_fallback = False

        result = await agent.ainvoke({"messages": messages}, config=config)

        tool_outputs = []
        if result and "messages" in result:
            tool_outputs = extract_tool_outputs_from_messages(result["messages"])

        guard = run_retrieval_guard(tool_outputs, name)

        if (
            not tool_outputs
            and name in ("knowledge_agent", "grading_agent", "path_agent")
            and retry_a < 1
        ):
            retry_a += 1
            logger.warning("Agent %s did not call any retrieval tool, retrying (retry_a=%d)", name, retry_a)
            grounding_msg = SystemMessage(content=_GROUNDING_FORCE_SEARCH_PROMPT)
            retry_messages = [grounding_msg] + list(messages)
            result = await agent.ainvoke({"messages": retry_messages}, config=config)
            if result and "messages" in result:
                tool_outputs = extract_tool_outputs_from_messages(result["messages"])
            guard = run_retrieval_guard(tool_outputs, name)

            if not tool_outputs and name == "knowledge_agent":
                rag_fallback = True
                logger.warning("Agent %s still no retrieval, RAG fallback", name)
                evidence = await asyncio.to_thread(retrieve_evidence, query=current_query, k=5, use_rerank=True)
                logger.info("RAG fallback evidences=%d sources=%s", len(evidence.text_evidences), evidence.sources)
                if evidence.text_evidences:
                    context = evidence.final_context
                    rag_messages = [
                        SystemMessage(content="You are a 408 exam Q&A assistant. Answer based strictly on the given context."),
                        HumanMessage(content=f"Context:\n{context}\n\nQuestion: {current_query}\n\nAnswer directly and accurately."),
                    ]
                    llm = get_llm(streaming=False, temperature=0.0)
                    rag_result = await llm.ainvoke(rag_messages)
                    rag_answer = rag_result.content if hasattr(rag_result, "content") else str(rag_result)
                    result = {"messages": [AIMessage(content=rag_answer)]}
                    tool_outputs = [context[:500]]
                    guard = run_retrieval_guard(tool_outputs, name)
                else:
                    rag_answer = "No relevant content found in knowledge base."
                    result = {"messages": [AIMessage(content=rag_answer)]}
                    tool_outputs = []
                    guard = GuardResult(has_sufficient_evidence=False, all_no_result=True, warnings=["No KB content"])

        if (
            not guard.has_sufficient_evidence
            and tool_outputs
            and not guard.all_no_result
            and retry_b < 1
        ):
            retry_b += 1
            logger.warning("Agent %s insufficient evidence, regeneration (retry_b=%d)", name, retry_b)
            grounding_content = build_grounding_message(guard, query=current_query)
            grounding_msg = SystemMessage(content=grounding_content)
            regen_messages = list(messages) + [
                SystemMessage(content="Reorganize your answer based on the retrieval results and constraints above."),
            ]
            regen_messages = [grounding_msg] + regen_messages
            result = await agent.ainvoke({"messages": regen_messages}, config=config)
            if result and "messages" in result:
                tool_outputs = extract_tool_outputs_from_messages(result["messages"])
            guard = run_retrieval_guard(tool_outputs, name)

        answer = ""
        if result and "messages" in result:
            last = result["messages"][-1]
            answer = last.content if hasattr(last, "content") else str(last)

        gov = govern_answer(answer, name, tool_outputs=tool_outputs)
        result_messages = result.get("messages", []) if result else []
        agent_steps = extract_agent_steps_from_messages(result_messages, name)

        evidence_for_reflection = " ".join(tool_outputs) if tool_outputs else ""
        reflection = reflect(
            answer=gov.answer,
            evidence_text=evidence_for_reflection,
            query=current_query,
            agent_name=name,
            use_llm=True,
        )
        if reflection.suggestion:
            gov.answer = apply_reflection_to_answer(gov.answer, reflection)

        total_retries = retry_a + retry_b
        elapsed_ms = (time.perf_counter() - start_time) * 1000
        logger.info(
            "Agent finished agent=%s elapsed_ms=%.2f gov_confidence=%s gov_flags=%s guard=%s reflection=%s retries=%d(A=%d,B=%d) rag=%s",
            name, elapsed_ms, gov.confidence, gov.flags, guard.has_sufficient_evidence,
            reflection.confidence, total_retries, retry_a, retry_b, rag_fallback,
        )
        return {
            "messages": result_messages,
            "final_answer": gov.answer,
            "agent_steps": agent_steps,
            "governance": {
                "confidence": gov.confidence,
                "has_source": gov.has_source,
                "passed": gov.passed,
                "flags": gov.flags,
                "reflection_confidence": reflection.confidence,
                "reflection_issues": reflection.issues,
            },
            "guard_result": {
                "has_sufficient_evidence": guard.has_sufficient_evidence,
                "warnings": guard.warnings,
            },
        }
    wrapped.__name__ = name
    return wrapped


# -- Graph Builder --

def build_multi_agent_graph():
    """Build multi-agent graph with planner + fan-out for complex queries.

    Topology:
      START -> supervisor
                 |
                 +-- simple -> [knowledge_agent | question_agent | grading_agent | path_agent] -> END
                 |
                 +-- complex -> planner_node
                                  |
                                  +-- fan-out (Send) -> text_retrieval | kg_retrieval | knowledge_agent
                                  |
                                  +-- synthesis_node -> END
    """
    knowledge_agent = create_knowledge_agent()
    question_agent = create_question_agent()
    grading_agent = create_grading_agent()
    path_agent = create_path_agent()

    builder = StateGraph(AgentState)

    # Supervisor
    builder.add_node("supervisor", route_question)

    # Fast-path agents (existing)
    builder.add_node("knowledge_agent", _wrap_agent(knowledge_agent, "knowledge_agent"))
    builder.add_node("question_agent", _wrap_agent(question_agent, "question_agent"))
    builder.add_node("grading_agent", _wrap_agent(grading_agent, "grading_agent"))
    builder.add_node("path_agent", _wrap_agent(path_agent, "path_agent"))

    # Phase 3 nodes
    builder.add_node("planner_node", planner_node)
    builder.add_node("text_retrieval", text_retrieval_node)
    builder.add_node("kg_retrieval", kg_retrieval_node)
    builder.add_node("parallel_knowledge", parallel_knowledge_node)
    builder.add_node("synthesis_node", synthesis_node)

    # Edges
    builder.add_edge(START, "supervisor")

    # Fast path: supervisor -> single agent -> END
    builder.add_edge("knowledge_agent", END)
    builder.add_edge("question_agent", END)
    builder.add_edge("grading_agent", END)
    builder.add_edge("path_agent", END)

    # Complex path: supervisor -> planner -> fan-out -> synthesis -> END
    builder.add_conditional_edges("planner_node", continue_to_agents)
    builder.add_edge("text_retrieval", "synthesis_node")
    builder.add_edge("kg_retrieval", "synthesis_node")
    builder.add_edge("parallel_knowledge", "synthesis_node")
    builder.add_edge("synthesis_node", END)

    graph = builder.compile()
    return graph


_graph = None


def get_graph():
    """Lazy-load multi-agent graph."""
    global _graph
    if _graph is None:
        _graph = build_multi_agent_graph()
    return _graph
