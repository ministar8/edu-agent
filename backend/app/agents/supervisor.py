from __future__ import annotations

from typing_extensions import TypedDict

from langchain_core.messages import HumanMessage
from langgraph.graph import StateGraph, START, END
from langgraph.types import Command

from app.rag.retriever import get_llm
from app.agents.knowledge_agent import create_knowledge_agent
from app.agents.question_agent import create_question_agent
from app.agents.grading_agent import create_grading_agent
from app.agents.path_agent import create_path_agent


class AgentState(TypedDict):
    messages: list
    current_agent: str
    agent_steps: list[dict]
    final_answer: str


SUPERVISOR_PROMPT = """你是一个教学辅导系统的调度主管(Supervisor)。

你的职责是根据学生的问题类型，将任务分发给最合适的Agent：

- **knowledge_agent**: 当学生询问知识点、概念解释、原理理解时分发
  触发词：什么是、怎么理解、解释一下、原理是什么、概念

- **question_agent**: 当学生要求出题、练习、测试时分发
  触发词：出题、练习题、测试、考考我、给我出几道题

- **grading_agent**: 当学生提交答案需要批改时分发
  触发词：批改、检查答案、对不对、评分、我的答案

- **path_agent**: 当学生需要学习建议、不知道怎么学时分发
  触发词：怎么学、学习路线、推荐、从哪里开始、学习建议

如果问题涉及多个方面，选择最主要的意图对应的Agent。
请只返回Agent名称，不要返回其他内容。
"""


def route_question(state: AgentState) -> Command[str]:
    """Supervisor路由：判断应该由哪个Agent处理，同时更新state"""
    llm = get_llm()
    last_msg = state["messages"][-1] if state["messages"] else ""
    content = last_msg.content if hasattr(last_msg, "content") else str(last_msg)

    response = llm.invoke(
        [HumanMessage(content=f"{SUPERVISOR_PROMPT}\n\n学生问题: {content}")]
    )

    agent_name = response.content.strip().lower()

    valid_agents = ["knowledge_agent", "question_agent", "grading_agent", "path_agent"]
    chosen = "knowledge_agent"
    for agent in valid_agents:
        if agent in agent_name:
            chosen = agent
            break

    return Command(
        goto=chosen,
        update={"current_agent": chosen},
    )


def _wrap_agent(agent, name: str):
    """包装Agent：执行后提取final_answer写入state"""
    async def wrapped(state: AgentState) -> dict:
        result = await agent.ainvoke({"messages": state["messages"]})
        answer = ""
        if result and "messages" in result:
            last = result["messages"][-1]
            answer = last.content if hasattr(last, "content") else str(last)
        return {
            "messages": result.get("messages", []),
            "final_answer": answer,
        }
    wrapped.__name__ = name
    return wrapped


def build_multi_agent_graph():
    """构建多Agent协作图"""
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
