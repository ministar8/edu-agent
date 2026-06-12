import asyncio
import logging
import time

from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.types import Command

from app.agents.chain_runners import quick_retrieve
from app.agents.graph_state import AGENT_NODE_NAMES, AgentState
from app.agents.prompts import SUPERVISOR_FEW_SHOT_PROMPT
from app.config import settings
from app.rag.query_classifier import QueryCategory, TEXT_ONLY_DEPTH, aclassify_query
from app.rag.rag_utils import extract_query_terms, get_llm, normalize_query_text
from app.rag.retrieval_strategy import RetrievalStrategy, resolve_retrieval_strategy

logger = logging.getLogger(__name__)


AGENT_ROUTE_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "grading_agent",
        (
            "批改", "评分", "对吗", "判断对错", "判对错", "打分", "检查答案",
            "我的回答", "我答的", "帮我看", "批作业", "纠错",
            "学生答案", "我的答案", "题目：",
        ),
    ),
    (
        "question_agent",
        (
            "出题", "练习", "测试", "考考我", "刷题", "给我出", "出几道", "来几道",
            "测验", "模拟题", "真题", "选择题", "填空题", "简答题",
        ),
    ),
    (
        "path_agent",
        (
            "怎么学", "学习路线", "推荐路线", "学习路径", "怎么复习", "从哪开始",
            "学习建议", "学习规划", "备考建议", "复习计划", "接下来学",
        ),
    ),
    (
        "knowledge_agent",
        (
            "什么是", "解释", "原理", "区别", "对比", "定义", "是什么",
            "为什么", "如何理解", "介绍一下", "讲一下", "说明", "概念",
            "过程", "方法", "算法", "机制", "条件", "特点",
        ),
    ),
)


def rule_based_route(query: str) -> str | None:
    q_lower = query.lower()
    for agent_name, keywords in AGENT_ROUTE_RULES:
        if any(keyword in q_lower for keyword in keywords):
            return agent_name
    return None


async def pre_retrieve_for_route(query: str) -> str | None:
    if not query:
        return None
    start = time.perf_counter()
    result = await quick_retrieve(query, k=5, use_rerank=True, depth=TEXT_ONLY_DEPTH)
    elapsed_ms = (time.perf_counter() - start) * 1000
    if result:
        logger.info("Supervisor pre-retrieval OK elapsed_ms=%.2f", elapsed_ms)
    else:
        logger.info("Supervisor pre-retrieval empty elapsed_ms=%.2f", elapsed_ms)
    return result or None


async def select_agent(
    content: str,
    config: RunnableConfig | None = None,
) -> tuple[str, str, asyncio.Task[str | None] | None]:
    start_time = time.perf_counter()
    rule_result = rule_based_route(content)
    if rule_result:
        elapsed_ms = (time.perf_counter() - start_time) * 1000
        logger.info(
            "Supervisor rule-route agent=%s elapsed_ms=%.2f (skipped LLM)",
            rule_result, elapsed_ms,
        )
        return rule_result, "rule", None

    pre_retrieval_task = asyncio.create_task(pre_retrieve_for_route(content))
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
    for agent in AGENT_NODE_NAMES:
        if agent in agent_name:
            chosen = agent
            break

    elapsed_ms = (time.perf_counter() - start_time) * 1000
    logger.info("Supervisor LLM-route agent=%s elapsed_ms=%.2f", chosen, elapsed_ms)
    return chosen, "llm", pre_retrieval_task


async def resolve_strategy_for_agent(chosen: str, content: str) -> tuple[RetrievalStrategy, QueryCategory]:
    normalized = normalize_query_text(content)
    terms = extract_query_terms(normalized)
    cat = await aclassify_query(content, terms)
    strategy = resolve_retrieval_strategy(cat)
    return strategy, cat


async def route_question(state: AgentState, config: RunnableConfig | None = None) -> Command[str]:
    last_msg = state["messages"][-1] if state["messages"] else ""
    content = last_msg.content if hasattr(last_msg, "content") else str(last_msg)

    chosen, route_source, pre_retrieval_task = await select_agent(content, config)
    strategy, _cat = await resolve_strategy_for_agent(chosen, content)

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
