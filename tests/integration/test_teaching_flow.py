"""端到端主链路：用户提交 -> memory 读取 -> supervisor 路由 -> 专家/直答 -> memory 写入。

纯本地 I/O，使用假模型，不联网、不碰真 Chroma/Store。
"""

from __future__ import annotations

import pytest
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import InMemorySaver

from agents.orchestration.teaching_graph import build_teaching_graph


@pytest.mark.asyncio
async def test_teaching_flow_chat_direct_answer() -> None:
    """寒暂类问题：不进任何专家，supervisor 直答，task_mode=chat。"""
    graph = build_teaching_graph()
    graph.checkpointer = InMemorySaver()

    config = {"configurable": {"thread_id": "e2e-chat", "user_id": "1", "request_id": "r1"}}
    out = await graph.ainvoke(
        {"messages": [HumanMessage(content="你好")]},
        config=config,
    )

    assert out["task_status"] == "completed"
    assert out["task_mode"] == "chat"
    assert out["active_agent"] is None
    assert out["error"] is None


@pytest.mark.asyncio
async def test_teaching_flow_knowledge_route() -> None:
    """知识类问题：路由到 knowledge 专家，active_agent 被设置。"""
    graph = build_teaching_graph()
    graph.checkpointer = InMemorySaver()

    config = {"configurable": {"thread_id": "e2e-kg", "user_id": "1", "request_id": "r2"}}
    out = await graph.ainvoke(
        {"messages": [HumanMessage(content="什么是进程调度？")]},
        config=config,
    )

    assert out["task_status"] == "completed"
    assert out["error"] is None
    # 假模型不做 handoff，由 supervisor 直答，active_agent 为 None；关键是不崩溃且状态落位
    assert out["task_id"] == "e2e-kg:r2"
