"""教学图状态与生命周期节点（M1/M2 的核心判定）。

覆盖三类容易写错的口径：
1. infer_execution 的边界（无 AI / 直答 / 未知专家 / 异常）；
2. active_agent 与 task_mode 独立计算；
3. finalize 只看尾部的实际产出，不看"跑到了收尾节点"。
"""

from __future__ import annotations

import asyncio

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from agents.orchestration.state import (
    SupervisorState,
    TeachingState,
    has_final_answer,
    infer_execution,
)
from agents.orchestration.teaching_graph import finalize, prepare_task


def _human(text: str = "什么是进程调度？") -> HumanMessage:
    return HumanMessage(content=text)


def test_infer_execution_known_agent() -> None:
    messages = [_human(), AIMessage(content="答", name="knowledge_agent")]
    result = infer_execution(messages)
    assert result == {"active_agent": "knowledge_agent", "task_mode": "knowledge"}


def test_infer_execution_direct_chat() -> None:
    # supervisor 自己的直答：AIMessage 有内容但没有 name
    messages = [_human(), AIMessage(content="你好")]
    result = infer_execution(messages)
    assert result == {"active_agent": None, "task_mode": "chat"}


def test_infer_execution_supervisor_named_message_is_chat() -> None:
    # 实测 create_supervisor 会给自己的直答打 name="supervisor"（不是 None）
    messages = [_human(), AIMessage(content="你好", name="supervisor")]
    result = infer_execution(messages)
    assert result == {"active_agent": None, "task_mode": "chat"}


def test_infer_execution_no_ai_message_is_unknown_not_chat() -> None:
    # 没有 AI 消息 ≠ 直答：可能是截断 / 中断 / 空产出
    result = infer_execution([_human()])
    assert result == {"active_agent": None, "task_mode": "unknown"}


def test_infer_execution_unknown_agent_is_unknown_not_chat() -> None:
    messages = [_human(), AIMessage(content="答", name="some_future_agent")]
    result = infer_execution(messages)
    assert result == {"active_agent": None, "task_mode": "unknown"}


def test_infer_execution_not_ok_keeps_unknown() -> None:
    messages = [_human(), AIMessage(content="答")]
    result = infer_execution(messages, run_ok=False)
    assert result == {"active_agent": None, "task_mode": "unknown"}


def test_infer_execution_skips_trailing_tool_message() -> None:
    messages = [
        _human(),
        AIMessage(
            content="", name="grading_agent", tool_calls=[{"name": "t", "args": {}, "id": "1"}]
        ),
        ToolMessage(content="工具结果", tool_call_id="1"),
    ]
    result = infer_execution(messages)
    assert result == {"active_agent": "grading_agent", "task_mode": "grading"}


def test_infer_execution_task_result_is_authoritative() -> None:
    # 专家名说 knowledge，但结构化结果说 grading：以后者为准
    messages = [_human(), AIMessage(content="答", name="knowledge_agent")]
    result = infer_execution(messages, task_result={"kind": "grading"})
    assert result["active_agent"] == "knowledge_agent"
    assert result["task_mode"] == "grading"


def test_infer_execution_unknown_result_kind_falls_back_to_unknown() -> None:
    messages = [_human(), AIMessage(content="答")]
    result = infer_execution(messages, task_result={"kind": "something_new"})
    assert result["task_mode"] == "unknown"


def test_has_final_answer() -> None:
    assert has_final_answer([_human(), AIMessage(content="答")]) is True
    assert has_final_answer([_human()]) is False
    assert has_final_answer([_human(), AIMessage(content="   ")]) is False
    # 尾部 ToolMessage 要跨过，找到前面的 AI 终答
    assert has_final_answer(
        [_human(), AIMessage(content="答"), ToolMessage(content="x", tool_call_id="1")]
    )


@pytest.mark.asyncio
async def test_prepare_task_resets_task_fields() -> None:
    state = {"messages": [_human()], "context_mode": None}
    config = {"configurable": {"thread_id": "t1", "request_id": "r1"}}
    out = await prepare_task(state, config)

    assert out["task_id"] == "t1:r1"
    assert out["task_mode"] == "unknown"
    assert out["task_context"] == {}
    assert out["active_agent"] is None
    assert out["task_status"] == "pending"
    assert out["task_result"] is None
    assert out["error"] is None
    assert out["context_mode"] in {"learn", "method", "practice", "grade", "explain", "verify"}


@pytest.mark.asyncio
async def test_prepare_task_generates_task_id_without_request_id() -> None:
    out = await prepare_task({"messages": [_human()]}, {"configurable": {"thread_id": "t2"}})
    assert out["task_id"].startswith("t2:")
    assert len(out["task_id"]) > len("t2:")


@pytest.mark.asyncio
async def test_teaching_graph_smoke() -> None:
    """端到端接线：prepare → load_memory → supervisor → finalize（假模型，不联网）。"""
    from agents.orchestration.teaching_graph import edu_supervisor

    config = {"configurable": {"thread_id": "smoke", "user_id": "1", "request_id": "r1"}}
    out = await edu_supervisor.ainvoke({"messages": [_human("你好")]}, config=config)

    assert out["task_id"] == "smoke:r1"
    assert out["task_status"] == "completed"
    # 假模型不做 handoff，由 supervisor 直答
    assert out["task_mode"] == "chat"
    assert out["active_agent"] is None
    assert out["error"] is None


@pytest.mark.asyncio
async def test_finalize_requires_output() -> None:
    failed = await finalize({"messages": [_human()]})
    assert failed["task_status"] == "failed"
    assert failed["error"]["code"] == "EMPTY_RESULT"
    assert failed["error"]["stage"] == "finalize"

    completed = await finalize({"messages": [_human(), AIMessage(content="答")]})
    assert completed == {"task_status": "completed"}


def test_prepare_and_finalize_are_awaitable() -> None:
    # 防止有人把 async 节点改成同步函数而调用方未同步修改
    assert asyncio.iscoroutinefunction(prepare_task)
    assert asyncio.iscoroutinefunction(finalize)


# ─────────── 冻结契约：Schema 边界 / context_mode 持久 ───────────


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
    from agents.orchestration.teaching_graph import run_supervisor

    stub = _StubSupervisor({"messages": [AIMessage(content="答")]})
    monkeypatch.setattr("agents.orchestration.teaching_graph.inner_supervisor", stub)

    await run_supervisor(_state(), {"configurable": {}})

    # 只允许 messages / task_context / context_mode 进内层
    assert set(stub.payload) == {"messages", "task_context", "context_mode"}
    assert stub.payload["task_context"] == {"kp": "进程调度"}
    assert stub.payload["context_mode"] == "practice"


@pytest.mark.asyncio
async def test_run_supervisor_outbound_mapping(monkeypatch) -> None:
    from agents.orchestration.teaching_graph import run_supervisor

    stub = _StubSupervisor(
        {
            "messages": [
                HumanMessage(content="你好"),
                AIMessage(content="答", name="grading_agent"),
            ],
            "task_context": {"kp": "不应回传"},
        }
    )
    monkeypatch.setattr("agents.orchestration.teaching_graph.inner_supervisor", stub)

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

    from agents.orchestration.teaching_graph import build_teaching_graph

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
