from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.types import StateSnapshot
from pydantic_core import ValidationError

from service.service import _create_ai_message, _is_user_visible_message


@pytest.mark.parametrize(
    "parts, expected",
    [
        # 1) 基础内容 + tool_calls
        (
            {"content": "Hello", "tool_calls": []},
            {"content": "Hello", "tool_calls": []},
        ),
        # 2) 未知键被丢弃
        (
            {"content": "Test", "foobar": 123, "tool_calls": []},
            {"content": "Test", "tool_calls": []},
        ),
        # 3) AIMessage 的其它合法参数（id / type）透传
        (
            {
                "content": "Hey",
                "id": "abc-123",
                "type": "ai",
                "tool_calls": [],
            },
            {"content": "Hey", "id": "abc-123", "type": "ai", "tool_calls": []},
        ),
    ],
)
def test_create_ai_message_filters_and_passes_through(parts, expected):
    """_create_ai_message 应丢弃未知键，保留 AIMessage 签名内的键。"""
    msg: AIMessage = _create_ai_message(parts)
    for key, val in expected.items():
        assert getattr(msg, key) == val


def test_create_ai_message_missing_required_content_raises():
    """缺少必需字段 content 时应抛出 pydantic ValidationError。"""
    with pytest.raises(ValidationError):
        _create_ai_message({"tool_calls": []})


def test_create_ai_message_empty_dict_raises():
    """空 dict 同样应构造失败。"""
    with pytest.raises(ValidationError):
        _create_ai_message({})


# ── SSE message 流的可见性过滤 ────────────────────────────────


def _transfer_ai() -> AIMessage:
    return AIMessage(
        content="",
        tool_calls=[{"name": "transfer_to_knowledge_agent", "args": {}, "id": "c1"}],
    )


@pytest.mark.parametrize(
    "message, visible",
    [
        pytest.param(SystemMessage(content="记忆卡"), False, id="system-card"),
        pytest.param(ToolMessage(content="检索结果", tool_call_id="c1"), False, id="tool-result"),
        pytest.param(_transfer_ai(), False, id="routing-ai-with-tool-calls"),
        pytest.param(AIMessage(content=""), False, id="empty-ai"),
        pytest.param(AIMessage(content="   "), False, id="blank-ai"),
        pytest.param(AIMessage(content="专家答案"), True, id="final-answer"),
        pytest.param(HumanMessage(content="问题"), True, id="human"),
        pytest.param(
            AIMessage(content=[{"type": "text", "text": "块内容"}]), True, id="content-blocks"
        ),
    ],
)
def test_is_user_visible_message(message, visible):
    """updates 流（含 subgraphs）同一消息会从内/外层节点各报一次，且夹带
    路由与工具中间消息；_is_user_visible_message + ID 去重负责只放行对话气泡。"""
    assert _is_user_visible_message(message) is visible


def test_history_skips_memory_card_system_message(test_client, auth_user):
    """/history 必须过滤记忆卡 SystemMessage：langchain_to_chat_message 不支持它，
    不过滤会对任何含记忆卡的线程抛 ValueError → 500。"""
    agent_mock = AsyncMock()
    agent_mock.checkpointer = None
    agent_mock.aget_state = AsyncMock(
        return_value=StateSnapshot(
            values={
                "messages": [
                    SystemMessage(content="记忆卡", id="edu_memory_card"),
                    HumanMessage(content="问题"),
                    AIMessage(content="专家答案"),
                ]
            },
            next=(),
            config={},
            metadata={"user_id": str(auth_user.user_id), "agent_id": "edu-assistant"},
            created_at=None,
            parent_config=None,
            tasks=(),
            interrupts=(),
        )
    )

    with (
        patch("service.service.get_agent", return_value=agent_mock),
        patch("service.service.agent_registry", {"edu-assistant": object()}),
    ):
        resp = test_client.post(
            "/api/history", json={"thread_id": "t-card"}, headers=auth_user.headers
        )

    assert resp.status_code == 200, resp.text
    types = [m["type"] for m in resp.json()["messages"]]
    assert types == ["human", "ai"]
