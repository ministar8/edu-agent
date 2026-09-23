import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langgraph.types import StateSnapshot
from pydantic_core import ValidationError

from schema import StreamInput
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


# ── message_generator（SSE 生成器本体）────────────────────────
#
# ★ 它此前**没有直接测试**（覆盖率 69%），未覆盖的正好包括 `__interrupt__` 分支 ——
#   而 backlog #36 第三步要动那段逻辑，所以先补安全网。


class _FakeAgent:
    """最小 agent 替身：只实现 `message_generator` 用到的 `astream`。"""

    def __init__(self, events):
        self._events = list(events)

    async def astream(self, **_kwargs):
        for event in self._events:
            yield event


async def _collect(events, *, stream_tokens: bool = True, message: str = "问题"):
    """跑一遍 `message_generator`，返回它 yield 的全部 SSE 字符串。"""
    from service.service import message_generator

    user_input = StreamInput(message=message, thread_id="t-stream", stream_tokens=stream_tokens)
    return [c async for c in message_generator(user_input, _FakeAgent(events), {}, "run-1")]


def _types(chunks) -> list[str]:
    """把 SSE 字符串解析成事件类型列表（`[DONE]` 记作 `done`）。"""
    out: list[str] = []
    for chunk in chunks:
        payload = chunk.removeprefix("data: ").strip()
        out.append("done" if payload == "[DONE]" else json.loads(payload)["type"])
    return out


class TestMessageGenerator:
    @pytest.mark.asyncio
    async def test_updates_event_yields_visible_message(self):
        events = [("updates", {"agent": {"messages": [AIMessage(content="专家答案")]}})]
        assert _types(await _collect(events)) == ["message", "done"]

    @pytest.mark.asyncio
    async def test_interrupt_event_becomes_ai_message(self):
        """`__interrupt__` 节点的 value 被包成 `AIMessage` 后照常下发。"""
        events = [("updates", {"__interrupt__": [SimpleNamespace(value="请确认")]})]
        chunks = await _collect(events)
        assert _types(chunks) == ["message", "done"]
        payload = json.loads(chunks[0].removeprefix("data: ").strip())
        assert payload["content"]["content"] == "请确认"

    @pytest.mark.asyncio
    async def test_three_tuple_event_unpacks_subgraph_namespace(self):
        """带 subgraphs 时事件是 3 元组 `(namespace, mode, event)`。"""
        events = [("inner", "updates", {"agent": {"messages": [AIMessage(content="子图答案")]}})]
        assert _types(await _collect(events)) == ["message", "done"]

    @pytest.mark.asyncio
    async def test_non_tuple_event_is_skipped(self):
        assert _types(await _collect(["不是元组"])) == ["done"]

    @pytest.mark.asyncio
    async def test_custom_event_is_forwarded(self):
        assert _types(await _collect([("custom", AIMessage(content="自定义"))])) == [
            "message",
            "done",
        ]

    @pytest.mark.asyncio
    async def test_same_message_id_is_deduplicated(self):
        """同 ID 消息会从内层/外层节点各报一次 —— 只发一次。"""
        msg = AIMessage(content="答案", id="dup-1")
        events = [
            ("updates", {"inner": {"messages": [msg]}}),
            ("updates", {"outer": {"messages": [msg]}}),
        ]
        assert _types(await _collect(events)) == ["message", "done"]

    @pytest.mark.asyncio
    async def test_human_echo_is_filtered(self):
        events = [("updates", {"agent": {"messages": [HumanMessage(content="问题")]}})]
        assert _types(await _collect(events)) == ["done"]

    @pytest.mark.asyncio
    async def test_handoff_back_message_is_filtered(self):
        events = [
            ("updates", {"agent": {"messages": [AIMessage(content="Transferring back to sup")]}})
        ]
        assert _types(await _collect(events)) == ["done"]

    @pytest.mark.asyncio
    async def test_token_stream_is_forwarded(self):
        events = [("messages", (AIMessageChunk(content="你好"), {"tags": []}))]
        assert _types(await _collect(events)) == ["token", "done"]

    @pytest.mark.asyncio
    async def test_token_stream_disabled_yields_nothing(self):
        events = [("messages", (AIMessageChunk(content="你好"), {"tags": []}))]
        assert _types(await _collect(events, stream_tokens=False)) == ["done"]

    @pytest.mark.asyncio
    async def test_skip_stream_tag_suppresses_token(self):
        events = [("messages", (AIMessageChunk(content="你好"), {"tags": ["skip_stream"]}))]
        assert _types(await _collect(events)) == ["done"]

    @pytest.mark.asyncio
    async def test_empty_token_content_is_suppressed(self):
        events = [("messages", (AIMessageChunk(content=""), {"tags": []}))]
        assert _types(await _collect(events)) == ["done"]

    @pytest.mark.asyncio
    async def test_agent_exception_yields_error_then_done(self):
        class _Boom:
            async def astream(self, **_kwargs):
                raise RuntimeError("炸了")
                yield  # pragma: no cover — 只为让它成为 async generator

        from service.service import message_generator

        user_input = StreamInput(message="问题", thread_id="t-stream")
        chunks = [c async for c in message_generator(user_input, _Boom(), {}, "run-1")]
        assert _types(chunks) == ["error", "done"]

    @pytest.mark.asyncio
    async def test_always_ends_with_done(self):
        assert (await _collect([]))[-1].strip() == "data: [DONE]"
