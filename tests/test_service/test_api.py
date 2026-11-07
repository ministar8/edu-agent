"""service 层 API 辅助纯函数单测。

纯本地 I/O，不启动 FastAPI 服务器，不联网、不碰真数据库。
通过 monkeypatch 设置 settings.AVAILABLE_MODELS，避免依赖真实网关配置。
"""

from __future__ import annotations

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from service.service import _check_thread_owner
from service.utils import (
    convert_message_content_to_string,
    ensure_model_available,
    langchain_to_chat_message,
    messages_from_checkpoint,
    remove_tool_calls,
)


def test_check_thread_owner_allows_new_thread_without_metadata() -> None:
    # 新建 thread 尚无 checkpoint（metadata 为空且无历史）时放行
    _check_thread_owner(None, "user1", "agent1", has_history=False)


def test_check_thread_owner_rejects_history_without_metadata() -> None:
    # 已有历史却缺 metadata，说明归属信息缺失，拒绝
    with pytest.raises(Exception) as exc:
        _check_thread_owner(None, "user1", "agent1", has_history=True)
    assert exc.value.status_code == 404


def test_check_thread_owner_rejects_mismatched_owner() -> None:
    metadata = {"user_id": "other", "agent_id": "agent1"}
    with pytest.raises(Exception) as exc:
        _check_thread_owner(metadata, "user1", "agent1")
    assert exc.value.status_code == 404


def test_check_thread_owner_allows_matching_owner() -> None:
    metadata = {"user_id": "user1", "agent_id": "agent1"}
    _check_thread_owner(metadata, "user1", "agent1")  # 不抛异常


def test_ensure_model_available_allows_allowed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("service.utils.settings.AVAILABLE_MODELS", {"gpt-4o", "fake-model"})
    ensure_model_available("gpt-4o")  # 不抛异常


def test_ensure_model_available_rejects_disallowed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("service.utils.settings.AVAILABLE_MODELS", {"gpt-4o"})
    with pytest.raises(Exception) as exc:
        ensure_model_available("unknown-model")
    assert exc.value.status_code == 400


def test_convert_message_content_to_string_plain() -> None:
    assert convert_message_content_to_string("hello") == "hello"


def test_convert_message_content_to_string_list() -> None:
    content = ["hello", {"type": "text", "text": " world"}]
    assert convert_message_content_to_string(content) == "hello world"


def test_remove_tool_calls_keeps_strings() -> None:
    content = ["hello", {"type": "tool_use", "id": "1"}, {"type": "text", "text": " ok"}]
    result = remove_tool_calls(content)
    assert result == ["hello", {"type": "text", "text": " ok"}]


def test_langchain_to_chat_message_human() -> None:
    msg = HumanMessage(content="用户问题")
    cm = langchain_to_chat_message(msg)
    assert cm.type == "human"
    assert cm.content == "用户问题"


def test_langchain_to_chat_message_ai() -> None:
    msg = AIMessage(content="AI 回答")
    cm = langchain_to_chat_message(msg)
    assert cm.type == "ai"
    assert cm.content == "AI 回答"


def test_langchain_to_chat_message_tool() -> None:
    msg = ToolMessage(content="工具结果", tool_call_id="tc-1")
    cm = langchain_to_chat_message(msg)
    assert cm.type == "tool"
    assert cm.content == "工具结果"
    assert cm.tool_call_id == "tc-1"


def test_messages_from_checkpoint_channel_values() -> None:
    checkpoint = {"channel_values": {"messages": [HumanMessage(content="a"), AIMessage(content="b")]}}
    msgs = messages_from_checkpoint(checkpoint)
    assert [m.content for m in msgs] == ["a", "b"]


def test_messages_from_checkpoint_previous_fallback() -> None:
    previous = [HumanMessage(content="prev-a"), AIMessage(content="prev-b")]
    checkpoint = {"channel_values": {"__previous__": previous}}
    msgs = messages_from_checkpoint(checkpoint)
    assert [m.content for m in msgs] == ["prev-a", "prev-b"]
