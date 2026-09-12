"""短期消息窗口裁剪。"""

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from memory.window import trim_conversation


def test_trim_disabled_when_zero():
    msgs = [HumanMessage(str(i)) for i in range(10)]
    assert trim_conversation(msgs, max_messages=0) == msgs


def test_trim_keeps_recent_and_system():
    msgs = [
        SystemMessage("card"),
        *[HumanMessage(f"h{i}") for i in range(10)],
        AIMessage("a"),
    ]
    out = trim_conversation(msgs, max_messages=3)
    assert out[0].content == "card"
    assert [m.content for m in out[1:]] == ["h8", "h9", "a"]


def test_trim_drops_orphan_tool_message():
    ai = AIMessage("", tool_calls=[{"name": "t", "args": {}, "id": "1"}])
    msgs = [
        HumanMessage("old"),
        ai,
        ToolMessage("orphan-result", tool_call_id="1"),
        HumanMessage("q1"),
        HumanMessage("q2"),
        HumanMessage("q3"),
    ]
    out = trim_conversation(msgs, max_messages=2)
    contents = [m.content for m in out if not isinstance(m, SystemMessage)]
    assert contents == ["q2", "q3"]
    assert not any(isinstance(m, ToolMessage) for m in out)


def test_trim_drops_incomplete_ai_tool_call_prefix():
    ai = AIMessage("", tool_calls=[{"name": "t", "args": {}, "id": "1"}])
    # 窗口落在 [AI(tool_calls), Human]，Tool 已被裁掉 → 丢掉残缺 AI
    msgs = [HumanMessage("h1"), HumanMessage("h2"), ai, HumanMessage("h3")]
    out = trim_conversation(msgs, max_messages=2)
    assert [m.content for m in out if not isinstance(m, SystemMessage)] == ["h3"]


def test_no_trim_when_short():
    msgs = [HumanMessage("a"), AIMessage("b")]
    assert trim_conversation(msgs, max_messages=20) == msgs
