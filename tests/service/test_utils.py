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


# ── name 透传（专家身份对外可见）──────────────────────────────


def test_ai_message_preserves_expert_name():
    """AI 消息的 name 必须透传：前端据此区分「知识讲解 / 出题 / 批改」。

    此前该字段被丢弃，专家身份在对外契约里消失，前端拿不到数据。
    """
    msg = langchain_to_chat_message(AIMessage(content="进程是资源分配单位", name="knowledge_agent"))
    assert msg.name == "knowledge_agent"


def test_ai_message_without_name_is_none():
    msg = langchain_to_chat_message(AIMessage(content="路人回答"))
    assert msg.name is None


def test_human_and_tool_message_carry_name():
    human = langchain_to_chat_message(HumanMessage(content="q", name="alice"))
    tool = langchain_to_chat_message(
        ToolMessage(content="r", tool_call_id="c1", name="knowledge_search")
    )
    assert human.name == "alice"
    assert tool.name == "knowledge_search"


def test_remove_tool_calls_string_passthrough():
    assert remove_tool_calls("plain") == "plain"


def test_remove_tool_calls_filters_tool_use():
    content = [{"type": "text", "text": "x"}, {"type": "tool_use", "id": "1"}]
    assert remove_tool_calls(content) == [{"type": "text", "text": "x"}]
