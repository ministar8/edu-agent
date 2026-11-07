"""Supervisor 调度机制的纯逻辑单测（四条出口 + 装配期校验）。

覆盖 supervisor.py 里最容易静默失效、且 state 测试碰不到的路径：

1. 专家终答 → ``Command(PARENT, goto=END)`` 短路（常态出口）；
2. 专家未闭环 tool_calls → ``UnclosedSpecialistOutput`` fail-fast；
3. 库回传控制消息（``__is_handoff_back``）与尾部 ToolMessage 被跳过，
   不误伤正常终答、不把控制消息当成专家输出；
4. 首轮 / 寒暄直答 → ``{}``，照常进 supervisor LLM；
5. 装配期白名单：缺 name / 重名 / hook 与专家集合脱节 → 启动期 ValueError。

不联网、不起服务、不调 create_supervisor 内的 LLM。
"""

from __future__ import annotations

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.graph import END
from langgraph.types import Command

from agents.orchestration.supervisor import (
    _HANDOFF_BACK_FLAG,
    UnclosedSpecialistOutput,
    _assert_hook_covers_specialists,
    _inspect_tail,
    _specialist_names,
    make_forward_after_agent,
)

_NAMES = frozenset({"knowledge_agent", "question_agent", "grading_agent"})
_HOOK = make_forward_after_agent(_NAMES)


def _expert_final(name: str = "knowledge_agent", content: str = "答") -> AIMessage:
    return AIMessage(content=content, name=name)


def _expert_unclosed(name: str = "question_agent") -> AIMessage:
    return AIMessage(
        content="",
        name=name,
        tool_calls=[{"name": "search_knowledge", "args": {"q": "栈"}, "id": "call_1"}],
    )


def _handoff_back_ai() -> AIMessage:
    """langgraph-supervisor 生成的「交还控制权」AI 消息（带 tool_calls + 标记）。"""
    return AIMessage(
        content="",
        name="supervisor",
        tool_calls=[{"name": "transfer_back_to_supervisor", "args": {}, "id": "hb_1"}],
        response_metadata={_HANDOFF_BACK_FLAG: True},
    )


# ───────────────────────── 出口 1：专家终答短路 ─────────────────────────


def test_final_answer_short_circuits_to_parent_end() -> None:
    out = _HOOK({"messages": [HumanMessage(content="什么是进程？"), _expert_final()]})
    assert isinstance(out, Command)
    assert out.graph == Command.PARENT
    assert out.goto == END


def test_final_answer_after_trailing_tool_message_still_short_circuits() -> None:
    # 专家答完后可能还挂着 ToolMessage（工具结果晚到 / 配对残留），仍应识别终答
    out = _HOOK(
        {
            "messages": [
                HumanMessage(content="什么是进程？"),
                _expert_final(),
                ToolMessage(content="工具结果", tool_call_id="call_0"),
            ]
        }
    )
    assert isinstance(out, Command)
    assert out.graph == Command.PARENT
    assert out.goto == END


def test_handoff_back_pair_is_skipped_not_treated_as_unclosed() -> None:
    # 尾部是库回传控制消息对（AI tool_call + ToolMessage）；
    # 不跳过会把带 tool_calls 的回传 AI 误判成「专家未闭环」而 fail-fast。
    out = _HOOK(
        {
            "messages": [
                HumanMessage(content="什么是进程？"),
                _expert_final(),
                _handoff_back_ai(),
                ToolMessage(content="control", tool_call_id="hb_1"),
            ]
        }
    )
    assert isinstance(out, Command)
    assert out.graph == Command.PARENT
    assert out.goto == END


def test_all_known_expert_names_short_circuit() -> None:
    for name in sorted(_NAMES):
        out = _HOOK({"messages": [HumanMessage(content="x"), _expert_final(name)]})
        assert isinstance(out, Command), name
        assert out.goto == END


# ───────────────────────── 出口 2：未闭环 fail-fast ─────────────────────────


def test_unclosed_tool_calls_raise_fail_fast() -> None:
    with pytest.raises(UnclosedSpecialistOutput) as exc_info:
        _HOOK({"messages": [HumanMessage(content="出题"), _expert_unclosed()]})
    # 报错要能指认是哪位专家断的
    assert "question_agent" in str(exc_info.value)


def test_unclosed_before_handoff_back_still_raises() -> None:
    # 专家未闭环 + 其后才是控制消息：回溯跳过控制消息后仍应命中未闭环 AI
    with pytest.raises(UnclosedSpecialistOutput) as exc_info:
        _HOOK(
            {
                "messages": [
                    HumanMessage(content="出题"),
                    _expert_unclosed("grading_agent"),
                    _handoff_back_ai(),
                    ToolMessage(content="control", tool_call_id="hb_1"),
                ]
            }
        )
    assert "grading_agent" in str(exc_info.value)


# ───────────────────────── 出口 3/4：不短路、照常进 LLM ─────────────────────────


def test_first_round_human_only_returns_empty_update() -> None:
    # 首轮路由：还没有专家输出，pre_model_hook 应放行给 supervisor LLM
    out = _HOOK({"messages": [HumanMessage(content="你好")]})
    assert out == {}


def test_supervisor_direct_answer_returns_empty_update() -> None:
    # 寒暄直答：supervisor 自己的 AIMessage（实测 name="supervisor"），不是专家
    out = _HOOK(
        {
            "messages": [
                HumanMessage(content="你好"),
                AIMessage(content="你好，我是 408 辅导助手", name="supervisor"),
            ]
        }
    )
    assert out == {}


def test_unknown_agent_name_is_neither_final_nor_unclosed() -> None:
    out = _HOOK(
        {
            "messages": [
                HumanMessage(content="x"),
                AIMessage(content="答", name="some_future_agent"),
            ]
        }
    )
    assert out == {}


def test_empty_messages_returns_empty_update() -> None:
    assert _HOOK({}) == {}
    assert _HOOK({"messages": []}) == {}


# ───────────────────────── _inspect_tail 边界 ─────────────────────────


def test_inspect_tail_flags_unclosed_name() -> None:
    inspection = _inspect_tail([HumanMessage(content="x"), _expert_unclosed()], _NAMES)
    assert inspection.is_final_answer is False
    assert inspection.unclosed_name == "question_agent"


def test_inspect_tail_final_answer_has_no_unclosed_name() -> None:
    inspection = _inspect_tail([HumanMessage(content="x"), _expert_final()], _NAMES)
    assert inspection.is_final_answer is True
    assert inspection.unclosed_name is None


# ───────────────────────── 装配期校验 ─────────────────────────


class _FakeAgent:
    def __init__(self, name: str | None) -> None:
        if name is not None:
            self.name = name


def test_specialist_names_missing_name_raises() -> None:
    with pytest.raises(ValueError, match="缺少 name"):
        _specialist_names((_FakeAgent(None),))


def test_specialist_names_duplicate_raises() -> None:
    with pytest.raises(ValueError, match="重复"):
        _specialist_names((_FakeAgent("a"), _FakeAgent("a")))


def test_hook_whitelist_mismatch_raises() -> None:
    # hook 白名单与真实专家集合脱节 → 短路会静默失效，必须启动期崩溃
    hook = make_forward_after_agent({"knowledge_agent"})  # 少了两个专家
    specialists = (_FakeAgent("knowledge_agent"), _FakeAgent("question_agent"))
    with pytest.raises(ValueError, match="不一致"):
        _assert_hook_covers_specialists(hook, specialists)


def test_hook_whitelist_match_passes() -> None:
    specialists = (_FakeAgent("knowledge_agent"), _FakeAgent("question_agent"))
    hook = make_forward_after_agent({"knowledge_agent", "question_agent"})
    _assert_hook_covers_specialists(hook, specialists)  # 不抛即通过


def test_module_level_hook_covers_real_specialists() -> None:
    # 装配期已跑过一次；这里再锁一次「生产 hook 的白名单 = 三专家」
    from agents.orchestration.supervisor import _SPECIALISTS, forward_after_agent

    assert set(forward_after_agent.agent_names) == set(_specialist_names(_SPECIALISTS))
