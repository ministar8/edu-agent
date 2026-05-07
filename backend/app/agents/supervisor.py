import logging
import time
from typing import Optional
from typing_extensions import TypedDict

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import StateGraph, START, END
from langgraph.types import Command

from app.rag.retriever import get_llm
from app.agents.knowledge_agent import create_knowledge_agent
from app.agents.question_agent import create_question_agent
from app.agents.grading_agent import create_grading_agent
from app.agents.path_agent import create_path_agent
from app.agents.answer_governance import govern_answer
from app.agents.retrieval_guard import (
    run_retrieval_guard, build_grounding_message, extract_tool_outputs_from_messages,
)
from app.agents.memory_manager import build_scoped_context, extract_current_query
from app.agents.trace_utils import extract_agent_steps_from_messages

logger = logging.getLogger(__name__)

class AgentState(TypedDict):
    messages: list
    current_agent: str
    agent_steps: list[dict]
    final_answer: str
    guard_result: dict  # 前置守卫结果（序列化）

# 强制检索约束：当 Agent 未调用检索工具时注入
_GROUNDING_FORCE_SEARCH_PROMPT = """【系统强制要求】
你必须先调用至少一个检索工具（如 search_knowledge_base、query_knowledge_graph 等）获取知识库内容，
然后基于检索结果回答。不得在未检索的情况下直接凭空作答。
若知识库无相关内容，必须明确说明"知识库中暂无相关内容"。
"""

SUPERVISOR_FEW_SHOT_PROMPT = """根据学生问题，判断应该由哪个Agent处理。只返回Agent名称，不要其他内容。

Agent说明：
- knowledge_agent：知识点解释、概念说明、原理理解
- question_agent：出题、练习、测试、生成题目
- grading_agent：批改答案、评分、检查对错
- path_agent：学习建议、学习路线、学习规划

示例：
学生：什么是进程死锁？ → knowledge_agent
学生：TCP和UDP的区别是什么？ → knowledge_agent
学生：给我出3道数据结构二叉树题目 → question_agent
学生：考考我操作系统进程管理的知识 → question_agent
学生：我的答案对不对？进程死锁的四个必要条件 → grading_agent
学生：批改一下我的作业 → grading_agent
学生：怎么复习计算机组成原理？ → path_agent
学生：推荐一个学习路线 → path_agent
学生：进程和线程有什么区别？ → knowledge_agent
学生：帮我出题并批改 → question_agent
学生：我学完进程管理了，接下来学什么？ → path_agent"""


_VALID_AGENTS = ("knowledge_agent", "question_agent", "grading_agent", "path_agent")


async def route_question(state: AgentState, config: Optional[RunnableConfig] = None) -> Command[str]:
    """Supervisor路由：Few-Shot Prompting LLM 分类

    所有 Agent 统一直接路由，由 Agent 自主决定何时检索（ReAct 模式）。
    """
    start_time = time.perf_counter()
    last_msg = state["messages"][-1] if state["messages"] else ""
    content = last_msg.content if hasattr(last_msg, "content") else str(last_msg)

    llm = get_llm()
    response = await llm.ainvoke(
        [HumanMessage(content=f"{SUPERVISOR_FEW_SHOT_PROMPT}\n\n学生：{content}")],
        config=config,
    )
    agent_name = response.content.strip().lower()

    # 从 LLM 输出中提取有效 Agent 名称
    chosen = "knowledge_agent"
    for agent in _VALID_AGENTS:
        if agent in agent_name:
            chosen = agent
            break

    elapsed_ms = (time.perf_counter() - start_time) * 1000
    logger.info("Supervisor route completed agent=%s elapsed_ms=%.2f", chosen, elapsed_ms)

    return Command(
        goto=chosen,
        update={"current_agent": chosen},
    )


def _wrap_agent(agent, name: str):
    """包装Agent：两阶段治理架构

    阶段1 — 前置守卫（预防幻觉）：
      Agent 执行 → 提取工具输出 → 检索结果预审 → Grounding 约束注入 → 重新执行
      若首次执行未调用任何检索工具，注入 Grounding 约束后重试一次。

    阶段2 — 后置治理（兜底校验）：
      Agent 回答 → 来源检查 → 伪造检查 → 格式检查 → 置信度判定 → 降级标注

    Agent 使用隔离上下文（当前问题），自主决定何时检索（ReAct 模式）。
    """
    async def wrapped(state: AgentState, config: Optional[RunnableConfig] = None) -> dict:
        start_time = time.perf_counter()
        logger.info("Agent execution started agent=%s", name)

        # ── Layer 3: 构建隔离上下文（避免其他 Agent 历史输出污染） ──
        current_query = extract_current_query(state["messages"])
        messages = build_scoped_context(
            current_query=current_query,
        )
        messages.insert(0, SystemMessage(content="输出必须使用结构清晰的 Markdown 中文排版：用标题、列表、表格或编号步骤组织内容；408题目必须包含题干、答案、解析；不要输出原始JSON、调试字段或无意义前缀。"))

        # 条件A/B 各自独立计数，各最多1次，允许 A→B 合法路径
        retry_a = 0  # 条件A（未调用检索工具）重试计数
        retry_b = 0  # 条件B（证据不足）重试计数

        # ── 阶段1：首次执行 + 前置守卫 ──
        result = await agent.ainvoke({"messages": messages}, config=config)

        # 提取工具输出，执行检索预审
        tool_outputs = []
        if result and "messages" in result:
            tool_outputs = extract_tool_outputs_from_messages(result["messages"])

        guard = run_retrieval_guard(tool_outputs, name)

        # 条件A：未调用检索工具 → 注入 Grounding 约束后重试（最多1次）
        if (
            not tool_outputs
            and name in ("knowledge_agent", "grading_agent", "path_agent")
            and retry_a < 1
        ):
            retry_a += 1
            logger.warning(
                "Agent %s did not call any retrieval tool, injecting grounding constraint and retrying (retry_a=%d)",
                name, retry_a,
            )
            grounding_msg = SystemMessage(
                content=_GROUNDING_FORCE_SEARCH_PROMPT,
            )
            retry_messages = [grounding_msg] + list(messages)
            result = await agent.ainvoke({"messages": retry_messages}, config=config)
            # 重新提取工具输出
            if result and "messages" in result:
                tool_outputs = extract_tool_outputs_from_messages(result["messages"])
            guard = run_retrieval_guard(tool_outputs, name)

        # 条件B：有工具输出但证据不足 → 注入 Grounding 约束重新生成（最多1次）
        # 跳过条件：已知所有检索均无结果(all_no_result)，无需再生成
        if (
            not guard.has_sufficient_evidence
            and tool_outputs
            and not guard.all_no_result
            and retry_b < 1
        ):
            retry_b += 1
            logger.warning(
                "Agent %s has insufficient evidence, injecting grounding constraint for regeneration (retry_b=%d)",
                name, retry_b,
            )
            grounding_content = build_grounding_message(guard, query=current_query)
            grounding_msg = SystemMessage(content=grounding_content)
            # 保留原始消息 + 追加 Grounding 约束
            regen_messages = list(messages) + [
                # 告诉 Agent 重新审视
                SystemMessage(content="请基于上方的【检索结果原文】和【系统强制约束】重新组织你的回答。"),
            ]
            # 在用户消息前插入 Grounding
            regen_messages = [grounding_msg] + regen_messages
            result = await agent.ainvoke({"messages": regen_messages}, config=config)
            # 重试后再次检查守卫，但不再重试
            if result and "messages" in result:
                tool_outputs = extract_tool_outputs_from_messages(result["messages"])
            guard = run_retrieval_guard(tool_outputs, name)

        # ── 阶段2：后置治理（兜底） ──
        answer = ""
        if result and "messages" in result:
            last = result["messages"][-1]
            answer = last.content if hasattr(last, "content") else str(last)

        gov = govern_answer(answer, name, tool_outputs=tool_outputs)
        result_messages = result.get("messages", []) if result else []
        agent_steps = extract_agent_steps_from_messages(result_messages, name)

        total_retries = retry_a + retry_b
        elapsed_ms = (time.perf_counter() - start_time) * 1000
        logger.info(
            "Agent execution finished agent=%s elapsed_ms=%.2f gov_confidence=%s gov_flags=%s guard_evidence=%s retries=%d(A=%d,B=%d)",
            name, elapsed_ms, gov.confidence, gov.flags, guard.has_sufficient_evidence,
            total_retries, retry_a, retry_b,
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
            },
            "guard_result": {
                "has_sufficient_evidence": guard.has_sufficient_evidence,
                "warnings": guard.warnings,
            },
        }
    wrapped.__name__ = name
    return wrapped


def build_multi_agent_graph():
    """构建多Agent协作图（ReAct 自主检索）

    协作拓扑：
    START → supervisor → [Agent] → END

    所有 Agent 统一直接路由，由 Agent 自主决定何时检索（ReAct 模式）。
    """
    knowledge_agent = create_knowledge_agent()
    question_agent = create_question_agent()
    grading_agent = create_grading_agent()
    path_agent = create_path_agent()

    builder = StateGraph(AgentState)

    builder.add_node("supervisor", route_question)
    builder.add_node("knowledge_agent", _wrap_agent(knowledge_agent, "knowledge_agent"))
    builder.add_node("question_agent", _wrap_agent(question_agent, "question_agent"))
    builder.add_node("grading_agent", _wrap_agent(grading_agent, "grading_agent"))
    builder.add_node("path_agent", _wrap_agent(path_agent, "path_agent"))

    builder.add_edge(START, "supervisor")

    # 所有 Agent 统一直接路由，执行后结束
    builder.add_edge("knowledge_agent", END)
    builder.add_edge("question_agent", END)
    builder.add_edge("grading_agent", END)
    builder.add_edge("path_agent", END)

    graph = builder.compile()
    return graph


_graph = None


def get_graph():
    """懒加载多Agent图，首次调用时才构建"""
    global _graph
    if _graph is None:
        _graph = build_multi_agent_graph()
    return _graph
