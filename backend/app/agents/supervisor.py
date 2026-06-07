from __future__ import annotations

import asyncio
import logging
import re as _re
import time
from typing_extensions import TypedDict

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import StateGraph, START, END
from langgraph.types import Command

from app.config import settings
from app.rag.rag_utils import get_llm
from app.rag.query_classifier import aclassify_query
from app.rag.retrieval_strategy import resolve_retrieval_strategy
from app.rag.rag_utils import normalize_query_text, extract_query_terms
from app.agents.knowledge_agent import create_knowledge_agent
from app.agents.question_agent import create_question_agent
from app.agents.grading_agent import create_grading_agent
from app.agents.path_agent import create_path_agent
from app.agents.answer_governance import govern_answer
from app.agents.reflection_agent import areflect, apply_reflection_to_answer
from app.agents.retrieval_guard import run_retrieval_guard
from app.agents.memory_manager import build_scoped_context, extract_current_query, format_history_from_messages
from app.agents.trace_utils import extract_sources_from_text
from app.agents.prompts import (
    SINGLE_AGENT_FAST_PATH_SYSTEM_PROMPT, SINGLE_AGENT_FAST_PATH_USER_TEMPLATE,
    SUPERVISOR_FEW_SHOT_PROMPT,
)

logger = logging.getLogger(__name__)

# ── Shared helpers (eliminate retrieval/formatting/query-extraction duplication) ──

# Direct-generation prompts for L1/L2/L3 fast-path (NOT ReAct — no tool calling)
_DIRECT_GEN_PROMPTS = {
    "grading_agent": (
        "你是408考研批改评估助手。参考资料已为你检索好，请严格基于参考资料批改学生答案。\n"
        "评分0-100，逐项对比标准答案与知识依据，给出命中要点、主要问题、改进建议。\n"
        "使用结构化Markdown格式。若参考资料不足，明确说明'参考评分（标准答案库不足）'。"
    ),
    "question_agent": (
        "你是408考研出题助手。参考资料已为你检索好，请严格基于参考资料生成练习题。\n"
        "支持选择题、填空题、简答题、综合应用题，每道题必须给出标准答案与简明解析。\n"
        "使用结构化Markdown格式。若参考资料不足，明确说明'题库模板不足'，不要编造题目。"
    ),
    "path_agent": (
        "你是408考研学习路径推荐助手。参考资料已为你检索好，请基于参考资料推荐循序渐进的学习路径。\n"
        "先补前置知识，再学目标知识，最后安排巩固。每步说明'为什么学'和'学什么'。\n"
        "使用结构化Markdown格式。若参考资料不足，基于已有信息做保守建议。"
    ),
}

_AGENT_PROMPT_MAP = {
    "grading_agent": _DIRECT_GEN_PROMPTS["grading_agent"],
    "question_agent": _DIRECT_GEN_PROMPTS["question_agent"],
    "path_agent": _DIRECT_GEN_PROMPTS["path_agent"],
}


def _format_docs(docs, max_docs: int = 5, content_limit: int = 800) -> str:
    """Format retrieved docs into [来源:...] prefixed text."""
    parts = []
    for doc in docs[:max_docs]:
        src = doc.metadata.get("source_file", doc.metadata.get("_collection", ""))
        parts.append(f"[来源:{src}]\n{doc.page_content[:content_limit]}")
    return "\n\n".join(parts) if parts else ""


async def _quick_retrieve(
    query: str,
    *,
    k: int = 5,
    use_rerank: bool = True,
    depth,
    timeout: float | None = None,
) -> str:
    """One-shot retrieval: classify → aretrieve_documents → format.
    Returns formatted context string or empty string on failure."""
    from app.rag.retriever import aretrieve_documents
    from app.rag.query_classifier import classify_query
    _terms = extract_query_terms(normalize_query_text(query))
    _cat = classify_query(query, _terms)
    try:
        docs = await asyncio.wait_for(
            aretrieve_documents(query, k=k, use_rerank=use_rerank, depth=depth, cat=_cat),
            timeout=timeout or settings.PRE_RETRIEVAL_TIMEOUT,
        )
        if docs:
            return _format_docs(docs, max_docs=k)
    except Exception as e:
        logger.warning("_quick_retrieve failed: %s", e)
    return ""


def _extract_retrieval_query(current_query: str, agent_name: str) -> str:
    """Extract retrieval-optimized query for non-knowledge agents.

    - grading: strip student answer, keep topic stem
    - path: extract subject + append learning keywords
    - question: extract knowledge point from question-generation prompt
    - knowledge: return as-is
    """
    if agent_name == "grading_agent":
        topic_match = _re.split(r"学生答案|我的答案|我答的", current_query)
        return topic_match[0].replace("题目：", "").replace("题目:", "").strip()[:200]
    elif agent_name == "path_agent":
        _subject_kw = _re.sub(r"应该怎么学|怎么学|怎么复习|学习路线|学习路径|学习建议|学习规划|如何学", "", current_query).strip()
        return f"{_subject_kw} 学习路线 重点章节" if _subject_kw else current_query
    elif agent_name == "question_agent":
        _m = _re.search(r"关于(.+?)(?:的选择题|的填空题|的简答题|的综合题|的题)", current_query)
        if _m:
            return _m.group(1).strip()
        _m2 = _re.search(r"涉及(.+?)(?:的|题)", current_query)
        if _m2:
            return _m2.group(1).strip()
        return _re.sub(r"出一道|出几道|给我出|来几道|综合题|选择题|填空题|简答题", "", current_query).strip()
    return current_query


def _get_agent_prompt(agent_name: str) -> str:
    """Return agent-specific system prompt, fallback to fast-path prompt."""
    return _AGENT_PROMPT_MAP.get(agent_name, SINGLE_AGENT_FAST_PATH_SYSTEM_PROMPT)


async def _llm_generate(
    system_prompt: str,
    evidence: str,
    query: str,
    *,
    use_fast: bool = False,
    timeout: float | None = None,
) -> str | None:
    """Single LLM generation call with evidence context. Returns answer or None."""
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=SINGLE_AGENT_FAST_PATH_USER_TEMPLATE.format(evidence=evidence, query=query)),
    ]
    llm = get_llm(streaming=False, temperature=settings.TEMP_PRECISE, use_fast=use_fast)
    try:
        result = await asyncio.wait_for(llm.ainvoke(messages), timeout=timeout or settings.AGENT_PRIMARY_TIMEOUT)
        answer = result.content if hasattr(result, "content") else str(result)
        return answer if answer else None
    except Exception as e:
        logger.warning("_llm_generate failed: %s", e)
        return None


# -- State --

class AgentState(TypedDict, total=False):
    messages: list
    current_agent: str
    agent_steps: list[dict]
    final_answer: str
    guard_result: dict
    governance: dict
    pre_retrieval_result: str | None
    # Phase 1: Retrieval strategy context
    retrieval_layer: str          # "L1" | "L2" | "L3"
    route_type: str               # e.g. "l1_fast", "l2_standard", "l3_deep"
    route_source: str             # "rule" | "llm" | "fallback"


# _GROUNDING_FORCE_SEARCH_PROMPT and SUPERVISOR_FEW_SHOT_PROMPT are now imported from prompts.py

_VALID_AGENTS = ("knowledge_agent", "question_agent", "grading_agent", "path_agent")


# -- Supervisor Router --

# ── 规则预路由：关键词 → Agent 映射，命中则跳过 LLM ──
_AGENT_RULES: list[tuple[str, list[str]]] = [
    # grading_agent（最明确的批改信号，优先匹配：含"学生答案"/"我的答案"一定是批改）
    ("grading_agent", [
        "批改", "评分", "对吗", "判断对错", "判对错", "打分", "检查答案",
        "我的回答", "我答的", "帮我看", "批作业", "纠错",
        "学生答案", "我的答案", "题目：",
    ]),
    # question_agent（出题信号，"题目"单独出现时才是出题）
    ("question_agent", [
        "出题", "练习", "测试", "考考我", "刷题", "给我出", "出几道", "来几道",
        "测验", "模拟题", "真题", "选择题", "填空题", "简答题",
    ]),
    # path_agent
    ("path_agent", [
        "怎么学", "学习路线", "推荐路线", "学习路径", "怎么复习", "从哪开始",
        "学习建议", "学习规划", "备考建议", "复习计划", "接下来学",
    ]),
    # knowledge_agent（兜底，信号最宽泛）
    ("knowledge_agent", [
        "什么是", "解释", "原理", "区别", "对比", "定义", "是什么",
        "为什么", "如何理解", "介绍一下", "讲一下", "说明", "概念",
        "过程", "方法", "算法", "机制", "条件", "特点",
    ]),
]


def _rule_based_route(query: str) -> str | None:
    """规则预路由：关键词匹配返回 Agent 名，未命中返回 None"""
    q_lower = query.lower()
    for agent_name, keywords in _AGENT_RULES:
        if any(kw in q_lower for kw in keywords):
            return agent_name
    return None


def _is_useful_retrieval_result(result: object) -> bool:
    if not result:
        return False
    prefix = str(result)[:200].lower()
    no_result_signals = (
        "no relevant", "not found", "no results", "未找到", "暂无相关",
        "知识库中暂无", "检索失败", "failed", "timed out", "timeout",
    )
    return not any(sig in prefix for sig in no_result_signals)


def _build_synthetic_agent_step(
    agent_name: str,
    tool_name: str,
    query: str,
    output: object,
    sources: list[str] | None = None,
) -> dict:
    output_text = str(output or "")
    return {
        "agent_name": agent_name,
        "action": "tool_call",
        "tool_name": tool_name,
        "input_data": str(query or "")[:600],
        "output_data": output_text[:1200],
        "sources": sources if sources is not None else extract_sources_from_text(output_text),
        "timestamp": time.time(),
    }


async def _pre_retrieve_for_route(query: str) -> str | None:
    """Supervisor 预检索：供 knowledge_agent fast-path 复用，失败时静默降级。"""
    if not query:
        return None
    from app.rag.query_classifier import TEXT_ONLY_DEPTH
    start = time.perf_counter()
    result = await _quick_retrieve(query, k=5, use_rerank=True, depth=TEXT_ONLY_DEPTH)
    elapsed_ms = (time.perf_counter() - start) * 1000
    if result:
        logger.info("Supervisor pre-retrieval OK elapsed_ms=%.2f", elapsed_ms)
    else:
        logger.info("Supervisor pre-retrieval empty elapsed_ms=%.2f", elapsed_ms)
    return result or None


# -- Router Sub-steps --

async def _select_agent(content: str, config: RunnableConfig | None = None) -> tuple[str, str, asyncio.Task[str | None] | None]:
    """Step 1: Select target agent via rule → LLM → fallback.

    Returns (chosen_agent, route_source, pre_retrieval_task).
    pre_retrieval_task is non-None only when LLM routing was used (rule miss).
    """
    start_time = time.perf_counter()
    pre_retrieval_task: asyncio.Task[str | None] | None = None

    # ── 规则预路由：命中则跳过 LLM，省 1-3s ──
    rule_result = _rule_based_route(content)
    if rule_result:
        elapsed_ms = (time.perf_counter() - start_time) * 1000
        logger.info(
            "Supervisor rule-route agent=%s elapsed_ms=%.2f (skipped LLM)",
            rule_result, elapsed_ms,
        )
        return rule_result, "rule", None

    # 规则未命中时，路由 LLM 与 knowledge 预检索并行启动。
    pre_retrieval_task = asyncio.create_task(_pre_retrieve_for_route(content))
    try:
        llm = get_llm(streaming=False, temperature=0.0, use_fast=True)
        response = await asyncio.wait_for(
            llm.ainvoke(
                [HumanMessage(content=f"{SUPERVISOR_FEW_SHOT_PROMPT}\n\nStudent: {content}")],
                config=config,
            ),
            timeout=settings.ROUTER_TIMEOUT,
        )
        agent_name = response.content.strip().lower()
    except asyncio.TimeoutError:
        logger.warning("Supervisor LLM route timed out after %ds, falling back to knowledge_agent", settings.ROUTER_TIMEOUT)
        agent_name = "knowledge_agent"
    except Exception as e:
        logger.warning("Supervisor LLM route failed: %s, falling back to knowledge_agent", e)
        agent_name = "knowledge_agent"

    chosen = "knowledge_agent"
    for agent in _VALID_AGENTS:
        if agent in agent_name:
            chosen = agent
            break

    elapsed_ms = (time.perf_counter() - start_time) * 1000
    logger.info(
        "Supervisor LLM-route agent=%s elapsed_ms=%.2f",
        chosen, elapsed_ms,
    )
    return chosen, "llm", pre_retrieval_task


async def _resolve_strategy_for_agent(chosen: str, content: str) -> tuple["RetrievalStrategy", "QueryCategory"]:
    """Step 2: Resolve retrieval strategy for the chosen agent.

    All agents get strategy context; knowledge_agent uses it for execution path,
    other agents use it for metrics/tracing only.
    """
    from app.rag.retrieval_strategy import RetrievalStrategy

    normalized = normalize_query_text(content)
    terms = extract_query_terms(normalized)
    cat = await aclassify_query(content, terms)
    strategy = resolve_retrieval_strategy(cat)
    return strategy, cat


# -- Supervisor Router --

async def route_question(state: AgentState, config: RunnableConfig | None = None) -> Command[str]:
    """Supervisor router: select agent → resolve strategy.

    Outputs structured route context (retrieval_layer, route_type, route_source)
    into AgentState for downstream consumption.
    """
    last_msg = state["messages"][-1] if state["messages"] else ""
    content = last_msg.content if hasattr(last_msg, "content") else str(last_msg)

    # Step 1: Agent selection
    chosen, route_source, pre_retrieval_task = await _select_agent(content, config)

    # Step 2: Strategy resolution
    strategy, cat = await _resolve_strategy_for_agent(chosen, content)

    # Step 3: Pre-retrieval (planner currently disabled)
    pre_retrieval_result: str | None = None
    if chosen == "knowledge_agent" and pre_retrieval_task:
        pre_retrieval_result = await pre_retrieval_task
    elif pre_retrieval_task and not pre_retrieval_task.done():
        pre_retrieval_task.cancel()

    route_update = {
        "current_agent": chosen,
        "pre_retrieval_result": pre_retrieval_result,
        "retrieval_layer": strategy.layer,
        "route_type": strategy.route_type,
        "route_source": route_source,
    }

    logger.info(
        "Supervisor route: agent=%s layer=%s route_type=%s source=%s",
        chosen, strategy.layer, strategy.route_type, route_source,
    )
    return Command(goto=chosen, update=route_update)



# -- Shared helpers for agent execution --

def _build_agent_messages(state: AgentState, name: str, config: RunnableConfig | None = None) -> list:
    """Build scoped context messages with profile injection."""
    current_query = extract_current_query(state["messages"])
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
    return messages


async def _apply_governance_and_reflection(
    answer: str,
    tool_outputs: list[str],
    result_messages: list,
    agent_steps: list[dict],
    name: str,
    current_query: str,
    start_time: float,
    retry_a: int = 0,
    retry_b: int = 0,
    rag_fallback: bool = False,
    retrieval_layer: str = "",
    route_type: str = "",
) -> dict:
    """Apply governance + reflection + build final agent output."""
    gov = govern_answer(answer, name, tool_outputs=tool_outputs)
    if not agent_steps and tool_outputs:
        agent_steps = [
            _build_synthetic_agent_step(
                name,
                "knowledge_search" if name == "knowledge_agent" else "retrieval",
                current_query,
                "\n\n".join(tool_outputs),
            )
        ]

    evidence_for_reflection = " ".join(tool_outputs) if tool_outputs else ""
    try:
        reflection = await asyncio.wait_for(
            areflect(
                answer=gov.answer,
                evidence_text=evidence_for_reflection,
                query=current_query,
                agent_name=name,
                use_llm=True,
            ),
            timeout=settings.AGENT_RETRY_TIMEOUT,
        )
    except Exception as e:
        logger.warning("Agent %s reflection skipped or downgraded: %s", name, e)
        reflection = await areflect(
            answer=gov.answer,
            evidence_text=evidence_for_reflection,
            query=current_query,
            agent_name=name,
            use_llm=False,
        )
    if reflection.suggestion:
        gov.answer = apply_reflection_to_answer(gov.answer, reflection)

    guard = run_retrieval_guard(tool_outputs, name)
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
        "retrieval_layer": retrieval_layer,
        "route_type": route_type,
    }


# -- L1 Agent: fast-path only (pre-retrieval → LLM, no ReAct, no retry) --

def _run_l1_agent(agent, name: str):
    """L1 strategy: pre-retrieval → direct LLM generation → governance + reflection.

    No ReAct loop, no retry, no RAG fallback. Fastest path for simple queries.
    """
    async def wrapped(state: AgentState, config: RunnableConfig | None = None) -> dict:
        start_time = time.perf_counter()
        logger.info("L1 agent execution started agent=%s", name)
        current_query = extract_current_query(state["messages"])

        # Pre-retrieval (from supervisor or fresh) — ALL agent types need retrieval
        pre_retrieval_result = state.get("pre_retrieval_result")
        if current_query and not pre_retrieval_result:
            from app.rag.query_classifier import TEXT_ONLY_DEPTH
            retrieval_query = _extract_retrieval_query(current_query, name)
            pre_retrieval_result = await _quick_retrieve(retrieval_query, k=5, use_rerank=True, depth=TEXT_ONLY_DEPTH)
            if pre_retrieval_result:
                logger.info("L1 pre-retrieval OK for %s", name)

        # Fast-path LLM generation (use agent-specific prompt for direct generation)
        answer = ""
        tool_outputs: list[str] = []
        result_messages: list = []
        if pre_retrieval_result:
            fast_answer = await _llm_generate(
                _get_agent_prompt(name), pre_retrieval_result, current_query, use_fast=True,
            )
            if fast_answer:
                answer = fast_answer
                tool_outputs = [pre_retrieval_result]
                result_messages = [AIMessage(content=fast_answer)]

        if not answer:
            answer = "未在知识库中找到相关内容。请换一种问法，或明确学科与知识点。"
            result_messages = [AIMessage(content=answer)]

        return await _apply_governance_and_reflection(
            answer=answer, tool_outputs=tool_outputs, result_messages=result_messages,
            agent_steps=[], name=name, current_query=current_query, start_time=start_time,
            retrieval_layer=state.get("retrieval_layer", "L1"),
            route_type=state.get("route_type", "l1_fast"),
        )
    wrapped.__name__ = name
    return wrapped


# -- L2 Agent: fast-path → fallback ReAct → retry-A → RAG fallback --

def _run_l2_agent(agent, name: str):
    """L2 strategy: fast-path → direct retrieval fallback → governance.

    Standard path for most knowledge queries. Skips KG by default (via retrieval strategy).
    """
    async def wrapped(state: AgentState, config: RunnableConfig | None = None) -> dict:
        start_time = time.perf_counter()
        logger.info("L2 agent execution started agent=%s", name)
        current_query = extract_current_query(state["messages"])

        retry_a = 0
        rag_fallback = False

        # ── Fast-path: pre-retrieval → direct LLM ──
        pre_retrieval_result = state.get("pre_retrieval_result")
        if pre_retrieval_result:
            logger.info("L2 using supervisor pre-retrieval for %s: result_len=%d", name, len(str(pre_retrieval_result)))
        if current_query and not pre_retrieval_result:
            from app.rag.query_classifier import TEXT_ONLY_DEPTH
            retrieval_query = _extract_retrieval_query(current_query, name)
            pre_retrieval_result = await _quick_retrieve(retrieval_query, k=5, use_rerank=True, depth=TEXT_ONLY_DEPTH)
            if pre_retrieval_result:
                logger.info("L2 pre-retrieval OK for %s", name)

            # Fallback: try without rerank
            if not pre_retrieval_result:
                pre_retrieval_result = await _quick_retrieve(
                    retrieval_query, k=5, use_rerank=False, depth=TEXT_ONLY_DEPTH, timeout=15,
                )
                if pre_retrieval_result:
                    logger.info("L2 pre-retrieval fallback OK for %s (no rerank)", name)

        fast_path_answer = None
        fast_path_tool_outputs: list[str] = []
        if pre_retrieval_result:
            fast_path_answer = await _llm_generate(
                _get_agent_prompt(name), pre_retrieval_result, current_query, use_fast=True,
            )
            if fast_path_answer:
                fast_path_tool_outputs = [pre_retrieval_result]

        # Fast-path success → skip ReAct
        if fast_path_answer:
            answer = fast_path_answer
            tool_outputs = fast_path_tool_outputs
            result_messages = [AIMessage(content=fast_path_answer)]
            agent_steps: list[dict] = []
            logger.info("L2 fast-path: skipping ReAct for %s", name)
        else:
            # Fallback: direct retrieval + LLM (no ReAct, too slow)
            logger.info("L2 fallback: direct retrieval for %s", name)
            answer = ""
            tool_outputs = []
            result_messages = []

            retrieval_query = _extract_retrieval_query(current_query, name)

            # Step 1: Retrieve (with rerank)
            from app.rag.query_classifier import STANDARD_DEPTH
            retrieval_ctx = await _quick_retrieve(retrieval_query, k=5, use_rerank=True, depth=STANDARD_DEPTH)
            if retrieval_ctx:
                tool_outputs = [retrieval_ctx]

            # Step 1b: Fallback retrieval without rerank if no results
            if not retrieval_ctx:
                retrieval_ctx = await _quick_retrieve(retrieval_query, k=5, use_rerank=False, depth=STANDARD_DEPTH, timeout=15)
                if retrieval_ctx:
                    tool_outputs = [retrieval_ctx]
                    logger.info("L2 fallback no-rerank OK for %s", name)

            # Step 2: LLM generate (use agent-specific prompt)
            if tool_outputs:
                gen_answer = await _llm_generate(
                    _get_agent_prompt(name), tool_outputs[0], current_query,
                )
                if gen_answer:
                    answer = gen_answer
                    result_messages = [AIMessage(content=gen_answer)]

            if not answer:
                rag_fallback = True
                answer = "未在知识库中找到相关内容。请换一种问法，或明确学科与知识点。"
                result_messages = [AIMessage(content=answer)]
            agent_steps = []

        return await _apply_governance_and_reflection(
            answer=answer, tool_outputs=tool_outputs, result_messages=result_messages,
            agent_steps=agent_steps, name=name, current_query=current_query,
            start_time=start_time, retry_a=retry_a, rag_fallback=rag_fallback,
            retrieval_layer=state.get("retrieval_layer", "L2"),
            route_type=state.get("route_type", "l2_standard"),
        )
    wrapped.__name__ = name
    return wrapped


# -- L3 Agent: deep retrieval → LLM generation (no ReAct) --

def _run_l3_agent(agent, name: str):
    """L3 strategy: deep retrieval (KG + HyDE enabled) → direct LLM generation → governance.

    No ReAct loop. Uses retrieve_evidence with deep config for maximum coverage,
    then generates answer in a single LLM call. Much faster than ReAct multi-round.
    """
    async def wrapped(state: AgentState, config: RunnableConfig | None = None) -> dict:
        start_time = time.perf_counter()
        logger.info("L3 agent execution started agent=%s", name)
        current_query = extract_current_query(state["messages"])

        retry_a = 0
        rag_fallback = False
        tool_outputs: list[str] = []
        answer = ""
        result_messages: list = []

        # ── Step 0: Extract retrieval query for non-knowledge agents ──
        retrieval_query = _extract_retrieval_query(current_query, name)

        # ── Step 1: Deep retrieval (with KG + HyDE) ──
        from app.rag.query_classifier import DEEP_DEPTH, STANDARD_DEPTH
        evidence_context = await _quick_retrieve(retrieval_query, k=8, use_rerank=True, depth=DEEP_DEPTH)
        if evidence_context:
            logger.info("L3 deep retrieval OK for %s", name)
        else:
            logger.warning("L3 deep retrieval empty for %s", name)

        # Step 1b: No-rerank fallback if deep retrieval empty
        if not evidence_context:
            evidence_context = await _quick_retrieve(retrieval_query, k=6, use_rerank=False, depth=STANDARD_DEPTH, timeout=15)
            if evidence_context:
                logger.info("L3 no-rerank fallback OK for %s", name)

        # ── Step 2: LLM generate answer (use agent-specific prompt) ──
        if evidence_context:
            tool_outputs = [evidence_context]
            gen_answer = await _llm_generate(_get_agent_prompt(name), evidence_context, current_query)
            if gen_answer:
                answer = gen_answer
                result_messages = [AIMessage(content=gen_answer)]

        # ── Step 3: Fallback if no answer (use aretrieve_documents) ──
        if not answer:
            rag_fallback = True
            retry_a = 1
            ctx_fb = await _quick_retrieve(retrieval_query, k=5, use_rerank=False, depth=STANDARD_DEPTH, timeout=15)
            if ctx_fb:
                tool_outputs = [ctx_fb]
                try:
                    rag_messages = [
                        SystemMessage(content="You are a 408 exam Q&A assistant. Answer based strictly on the given context."),
                        HumanMessage(content=f"Context:\n{ctx_fb}\n\nQuestion: {current_query}\n\nAnswer directly and accurately."),
                    ]
                    llm = get_llm(streaming=False, temperature=0.0)
                    rag_result = await asyncio.wait_for(llm.ainvoke(rag_messages), timeout=settings.RAG_FALLBACK_TIMEOUT)
                    rag_answer = rag_result.content if hasattr(rag_result, "content") else str(rag_result)
                    if rag_answer:
                        answer = rag_answer
                        result_messages = [AIMessage(content=rag_answer)]
                except Exception as e:
                    logger.warning("L3 RAG fallback failed for %s: %s", name, e)

        if not answer:
            answer = "未在知识库中找到相关内容。请换一种问法，或明确学科与知识点。"
            result_messages = [AIMessage(content=answer)]

        return await _apply_governance_and_reflection(
            answer=answer, tool_outputs=tool_outputs, result_messages=result_messages,
            agent_steps=[], name=name, current_query=current_query,
            start_time=start_time, retry_a=retry_a, rag_fallback=rag_fallback,
            retrieval_layer=state.get("retrieval_layer", "L3"),
            route_type=state.get("route_type", "l3_deep"),
        )
    wrapped.__name__ = name
    return wrapped


# -- Agent wrapper dispatcher --

def _wrap_agent(agent, name: str):
    """Dispatch to L1/L2/L3 agent runner based on state.retrieval_layer.

    Falls back to L2 if retrieval_layer is not set (backward compatibility).
    """
    async def wrapped(state: AgentState, config: RunnableConfig | None = None) -> dict:
        layer = state.get("retrieval_layer", "L2")
        if layer == "L1":
            runner = _run_l1_agent(agent, name)
        elif layer == "L3":
            runner = _run_l3_agent(agent, name)
        else:
            runner = _run_l2_agent(agent, name)
        return await runner(state, config)
    wrapped.__name__ = name
    return wrapped


# -- Graph Builder --

def build_multi_agent_graph():
    """Build multi-agent graph.

    Topology:
      START -> supervisor
                 |
                 +-- [knowledge_agent | question_agent | grading_agent | path_agent] -> END
    """
    knowledge_agent = create_knowledge_agent()
    question_agent = create_question_agent()
    grading_agent = create_grading_agent()
    path_agent = create_path_agent()

    builder = StateGraph(AgentState)

    # Supervisor
    builder.add_node("supervisor", route_question)

    # Agents
    builder.add_node("knowledge_agent", _wrap_agent(knowledge_agent, "knowledge_agent"))
    builder.add_node("question_agent", _wrap_agent(question_agent, "question_agent"))
    builder.add_node("grading_agent", _wrap_agent(grading_agent, "grading_agent"))
    builder.add_node("path_agent", _wrap_agent(path_agent, "path_agent"))

    # Edges
    builder.add_edge(START, "supervisor")
    builder.add_edge("knowledge_agent", END)
    builder.add_edge("question_agent", END)
    builder.add_edge("grading_agent", END)
    builder.add_edge("path_agent", END)

    graph = builder.compile()
    return graph


_graph = None


def get_graph():
    """Lazy-load multi-agent graph."""
    global _graph
    if _graph is None:
        _graph = build_multi_agent_graph()
    return _graph
