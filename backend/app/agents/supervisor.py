import asyncio
import logging
import time
from typing_extensions import TypedDict

from langchain_core.messages import HumanMessage
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
from app.agents.chain_runners import quick_retrieve, wrap_agent
from app.agents.prompts import SUPERVISOR_FEW_SHOT_PROMPT

logger = logging.getLogger(__name__)


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


async def _pre_retrieve_for_route(query: str) -> str | None:
    """Supervisor 预检索：供 knowledge_agent fast-path 复用，失败时静默降级。"""
    if not query:
        return None
    from app.rag.query_classifier import TEXT_ONLY_DEPTH
    start = time.perf_counter()
    result = await quick_retrieve(query, k=5, use_rerank=True, depth=TEXT_ONLY_DEPTH)
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
    builder.add_node("knowledge_agent", wrap_agent(knowledge_agent, "knowledge_agent"))
    builder.add_node("question_agent", wrap_agent(question_agent, "question_agent"))
    builder.add_node("grading_agent", wrap_agent(grading_agent, "grading_agent"))
    builder.add_node("path_agent", wrap_agent(path_agent, "path_agent"))

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
