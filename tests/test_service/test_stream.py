"""service._sse SSE 消息流纯函数单测。

纯本地 I/O，不联网、不依赖外部服务。
"""

from __future__ import annotations

from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)

from schema import StreamInput
from service._sse import (
    _collect_stream_messages,
    _create_ai_message,
    _is_user_visible_message,
    _last_user_visible_message,
    _normalize_messages,
    _token_sse,
)


def _ai(content: str = "答", *, tool_calls: list | None = None) -> AIMessage:
    return AIMessage(content=content, tool_calls=tool_calls or [])


def test_is_user_visible_message_filters_system_and_tool() -> None:
    assert _is_user_visible_message(SystemMessage(content="工作记忆卡")) is False
    assert _is_user_visible_message(ToolMessage(content="工具结果", tool_call_id="1")) is False


def test_is_user_visible_message_filters_empty_or_tool_call_ai() -> None:
    assert _is_user_visible_message(_ai(content="")) is False
    assert _is_user_visible_message(_ai(content="   ")) is False
    assert _is_user_visible_message(_ai(content="中间决策", tool_calls=[{"name": "t", "args": {}, "id": "1"}])) is False


def test_is_user_visible_message_passes_plain_ai() -> None:
    assert _is_user_visible_message(_ai(content="最终回答")) is True


def test_create_ai_message_filters_invalid_keys() -> None:
    msg = _create_ai_message({"content": "答", "role": "assistant", "invalid_key": 123})
    assert msg.content == "答"
    assert not hasattr(msg, "invalid_key")


def test_last_user_visible_message_picks_tail_visible() -> None:
    msgs = [
        HumanMessage(content="用户问题"),
        _ai(content="中间步骤", tool_calls=[{"name": "t", "args": {}, "id": "1"}]),
        SystemMessage(content="工作记忆卡"),
        _ai(content="最终回答"),
    ]
    visible = _last_user_visible_message(msgs)
    assert visible.content == "最终回答"


def test_last_user_visible_message_falls_back_to_tail() -> None:
    # 全部不可见时回退到原始末条
    msgs = [SystemMessage(content="只有系统消息")]
    visible = _last_user_visible_message(msgs)
    assert visible.content == "只有系统消息"


def test_normalize_messages_joins_key_value_shards() -> None:
    # (key, value) 分片：最后一个同 key 值覆盖前一个，非 tuple 消息原样保留
    parts = [("content", "第一段"), ("content", "第二段"), HumanMessage(content="人类消息")]
    out = _normalize_messages(parts)
    assert isinstance(out[0], AIMessage)
    assert out[0].content == "第二段"
    assert isinstance(out[1], HumanMessage)


def test_collect_stream_messages_updates_mode() -> None:
    event = {
        "node_a": {"messages": [HumanMessage(content="a"), _ai(content="b")]},
        "node_b": {"messages": [_ai(content="c")]},
    }
    out = _collect_stream_messages("updates", event)
    contents = [getattr(m, "content", str(m)) for m in out]
    assert contents == ["a", "b", "c"]


def test_token_sse_skips_when_stream_tokens_false() -> None:
    ui = StreamInput(message="你好", stream_tokens=False)
    assert _token_sse((AIMessage(content="答"), {}), ui) == []


def test_token_sse_skips_non_chunk_or_skip_stream() -> None:
    ui = StreamInput(message="你好", stream_tokens=True)
    assert _token_sse((AIMessage(content="答"), {}), ui) == []
    assert (
        _token_sse(
            (AIMessageChunk(content="答"), {"tags": ["skip_stream"]}), ui
        )
        == []
    )


def test_token_sse_emits_token_frame() -> None:
    from langchain_core.messages import AIMessageChunk

    ui = StreamInput(message="你好", stream_tokens=True)
    frames = _token_sse((AIMessageChunk(content="hello"), {}), ui)
    assert len(frames) == 1
    assert frames[0].startswith("data: ")
    assert '"type": "token"' in frames[0]
    assert '"content": "hello"' in frames[0]
