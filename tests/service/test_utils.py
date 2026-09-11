from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from service.utils import (
    convert_message_content_to_string,
    langchain_to_chat_message,
    remove_tool_calls,
)


def test_convert_string():
    assert convert_message_content_to_string("hi") == "hi"


def test_convert_content_list():
    content = [{"type": "text", "text": "a"}, "b"]
    assert convert_message_content_to_string(content) == "ab"


def test_human_message():
    msg = langchain_to_chat_message(HumanMessage(content="hi"))
    assert msg.type == "human"
    assert msg.content == "hi"


def test_ai_message():
    msg = langchain_to_chat_message(AIMessage(content="yo"))
    assert msg.type == "ai"
    assert msg.content == "yo"


def test_tool_message_carries_call_id():
    msg = langchain_to_chat_message(ToolMessage(content="r", tool_call_id="c1"))
    assert msg.type == "tool"
    assert msg.tool_call_id == "c1"


def test_remove_tool_calls_string_passthrough():
    assert remove_tool_calls("plain") == "plain"


def test_remove_tool_calls_filters_tool_use():
    content = [{"type": "text", "text": "x"}, {"type": "tool_use", "id": "1"}]
    assert remove_tool_calls(content) == [{"type": "text", "text": "x"}]
