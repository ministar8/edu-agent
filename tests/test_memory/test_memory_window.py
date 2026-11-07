"""memory.window.trim_conversation 的单测（短期窗口裁剪 + 工具孤儿修复）。

invariants：
- System 消息全部保留，不受裁剪影响；
- 裁剪后的开头不得出现孤立 ToolMessage（其 AI 已被裁掉）；
- 带 tool_calls 的 AI 若后续 Tool 数量不足 → 整段丢弃（工具结果错位防线）。
"""

from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from memory.window import trim_conversation


def msgs() -> list:  # noqa: ANN201 — 测试构造器
    return [
        SystemMessage("你是助教"),
        HumanMessage("Q1"),
        AIMessage(
            "调用工具",
            tool_calls=[{"name": "search", "args": {}, "id": "c1"}],
        ),
        ToolMessage("工具结果1", tool_call_id="c1"),
        HumanMessage("追问"),
        AIMessage("第二条回答", tool_calls=[{"name": "a", "args": {}, "id": "c2"}]),
        ToolMessage("工具结果2", tool_call_id="c2"),
        AIMessage("最终回答"),
    ]


def test_under_limit_keeps_all() -> None:
    out = trim_conversation(msgs(), max_messages=100)
    assert len(out) == len(msgs())


def test_zero_or_negative_max_disables_trimming() -> None:
    for m in (0, -3):
        assert trim_conversation(msgs(), max_messages=m) == list(msgs())


def test_system_messages_always_kept() -> None:
    raw = msgs()
    out = trim_conversation(raw, max_messages=2)
    systems = [m for m in out if isinstance(m, SystemMessage)]
    assert systems == [m for m in raw if isinstance(m, SystemMessage)]
    # last2 = [ToolMessage(c2), AIMessage(最终回答)] → 孤立 Tool 先被丢 → 仅剩最终回答
    chat = [m for m in out if not isinstance(m, SystemMessage)]
    assert [m.content for m in chat] == ["最终回答"]


def test_trim_keeps_most_recent_chat() -> None:
    out = trim_conversation(msgs(), max_messages=3)
    chat = [m for m in out if not isinstance(m, SystemMessage)]
    # last3 = [AIMessage(tc2), ToolMessage(c2), AIMessage(最终回答)] → 工具对完整，全保留
    assert [m.content for m in chat] == ["第二条回答", "工具结果2", "最终回答"]


def test_leading_orphan_tool_messages_dropped() -> None:
    # 裁剪窗口切到 [T, H]：Tool 的 AI 已被裁掉 → 孤立 Tool 必须丢
    raw = [
        SystemMessage("s"),
        AIMessage("调", tool_calls=[{"name": "f", "args": {}, "id": "c9"}]),
        ToolMessage("结果", tool_call_id="c9"),
        HumanMessage("后续问题"),
    ]
    out = trim_conversation(raw, max_messages=2)
    non_system = [m for m in out if not isinstance(m, SystemMessage)]
    assert [m.content for m in non_system] == ["后续问题"]


def test_all_orphan_slice_can_empty_out() -> None:
    # max=1 把窗口切到 [T] → Tool 的 AI 已被裁掉 → 整段孤儿，允许清空对话侧（System 仍在）
    raw = [
        SystemMessage("s"),
        AIMessage("调", tool_calls=[{"name": "f", "args": {}, "id": "c9"}]),
        ToolMessage("结果", tool_call_id="c9"),
    ]
    out = trim_conversation(raw, max_messages=1)
    non_system = [m for m in out if not isinstance(m, SystemMessage)]
    assert non_system == []


def test_incomplete_tool_pair_after_ai_with_calls_is_discarded() -> None:
    # AI 带 1 个 tool_calls 但窗口切到中间缺 ToolMessage → 该段整体丢弃
    raw = [
        SystemMessage("s"),
        AIMessage("带工具", tool_calls=[{"name": "f", "args": {}, "id": "c1"}]),
        HumanMessage("备用话题"),
        AIMessage("收尾"),
    ]
    out = trim_conversation(raw, max_messages=3)
    non_system = [m for m in out if not isinstance(m, SystemMessage)]
    # 首条 AI 的 tool_calls 没有后续 Tool → 丢弃其与后续 Tool；剩 [H, A]
    assert [m.content for m in non_system] == ["备用话题", "收尾"]


def test_complete_tool_pair_survives_trim() -> None:
    raw = [
        SystemMessage("s"),
        HumanMessage("问"),
        AIMessage("带工具", tool_calls=[{"name": "f", "args": {}, "id": "c1"}]),
        ToolMessage("结果", tool_call_id="c1"),
    ]
    out = trim_conversation(raw, max_messages=3)
    non_system = [m for m in out if not isinstance(m, SystemMessage)]
    assert len(non_system) == 3  # 成对的 AI+Tool 不应被误删
