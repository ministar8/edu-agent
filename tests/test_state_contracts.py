"""State 的三条冻结契约（改动破坏任何一条，这里就红）。

1. Schema 边界：边界 A 的入参/出参白名单；
2. SupervisorState 必须有 prebuilt AgentState 的托管 channel；
3. context_mode 真的从旧 checkpoint 读到上一轮值。
"""

from __future__ import annotations

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from agents.state import SupervisorState, TeachingState


class _StubSupervisor:
    """替身内层图：记录入参，返回固定结果。"""

    def __init__(self, result):
        self.result = result
        self.payload = None

    async def ainvoke(self, payload, config=None):
        self.payload = payload
        return self.result


def _state(**overrides):
    base = {
        "messages": [HumanMessage(content="你好")],
        "task_id": "t:r",
        "task_mode": "unknown",
        "task_context": {"kp": "进程调度"},
        "context_mode": "practice",
        "active_agent": None,
        "task_status": "pending",
        "task_result": None,
        "error": None,
    }
    base.update(overrides)
    return base


@pytest.mark.asyncio
async def test_run_supervisor_inbound_whitelist(monkeypatch) -> None:
    stub = _StubSupervisor({"messages": [AIMessage(content="答")]})
    monkeypatch.setattr("agents.teaching_graph.inner_supervisor", stub)

    from agents.teaching_graph import run_supervisor

    await run_supervisor(_state(), {"configurable": {}})

    # 只允许 messages / task_context / context_mode 进内层
    assert set(stub.payload) == {"messages", "task_context", "context_mode"}
    assert stub.payload["task_context"] == {"kp": "进程调度"}
    assert stub.payload["context_mode"] == "practice"


@pytest.mark.asyncio
async def test_run_supervisor_outbound_mapping(monkeypatch) -> None:
    stub = _StubSupervisor(
        {
            "messages": [
                HumanMessage(content="你好"),
                AIMessage(content="答", name="grading_agent"),
            ],
            "task_context": {"kp": "不应回传"},
        }
    )
    monkeypatch.setattr("agents.teaching_graph.inner_supervisor", stub)

    from agents.teaching_graph import run_supervisor

    out = await run_supervisor(_state(), {"configurable": {}})

    assert set(out) == {"messages", "active_agent", "task_mode"}
    assert out["active_agent"] == "grading_agent"
    assert out["task_mode"] == "grading"


def test_supervisor_state_has_required_channels() -> None:
    hints = set(SupervisorState.__annotations__)
    # create_react_agent 的硬校验
    assert {"messages", "remaining_steps"} <= hints
    assert {"task_context", "context_mode", "task_result"} <= hints


def test_teaching_state_is_plain_typed_dict() -> None:
    hints = set(TeachingState.__annotations__)
    assert "messages" in hints
    # 外层不继承 AgentState：不应出现 ReAct 托管值
    assert "remaining_steps" not in hints
    assert "jump_to" not in hints
    assert "structured_response" not in hints


@pytest.mark.asyncio
async def test_context_mode_survives_checkpoint() -> None:
    """上一轮 practice + 本轮"答案是 A" ⇒ grade；证明读到了 checkpoint 里的旧值。"""
    from langgraph.checkpoint.memory import InMemorySaver

    from agents.teaching_graph import build_teaching_graph

    graph = build_teaching_graph()
    graph.checkpointer = InMemorySaver()

    base = {"thread_id": "ctx", "user_id": "1"}
    out1 = await graph.ainvoke(
        {"messages": [HumanMessage(content="帮我出几道进程调度的题")]},
        config={"configurable": {**base, "request_id": "r1"}},
    )
    assert out1["context_mode"] == "practice"

    out2 = await graph.ainvoke(
        {"messages": [HumanMessage(content="答案是 A")]},
        config={"configurable": {**base, "request_id": "r2"}},
    )
    # 若没读到上一轮的 practice，这里会落回默认 learn
    assert out2["context_mode"] == "grade"
