"""custom 流模式：schema / 转换 / 真实 graph 转发。"""

import json
from unittest.mock import patch

import httpx
import pytest
from langchain_core.messages import AIMessage
from langchain_core.messages import ChatMessage as LangchainChatMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, MessagesState, StateGraph
from langgraph.types import StreamWriter

from agents.utils import CustomData
from schema import ChatMessage
from service.service import app
from service.utils import langchain_to_chat_message


def test_chat_message_accepts_custom_type():
    msg = ChatMessage(type="custom", content="", custom_data={"status": "running"})
    assert msg.type == "custom"
    assert msg.custom_data == {"status": "running"}


def test_langchain_custom_message_maps_to_custom_data():
    raw = LangchainChatMessage(content=[{"status": "running", "step": 1}], role="custom")
    msg = langchain_to_chat_message(raw)
    assert msg.type == "custom"
    assert msg.content == ""
    assert msg.custom_data == {"status": "running", "step": 1}


def test_langchain_custom_data_dispatch_roundtrip():
    payload = CustomData(data={"phase": "retrieval"})
    raw = payload.to_langchain()
    msg = langchain_to_chat_message(raw)
    assert msg.custom_data == {"phase": "retrieval"}


async def report_progress(state: MessagesState, writer: StreamWriter) -> MessagesState:
    CustomData(data={"status": "running"}).dispatch(writer)
    return {"messages": [AIMessage(content="all done")]}


def build_custom_data_agent():
    graph = StateGraph(MessagesState)
    graph.add_node("report", report_progress)
    graph.set_entry_point("report")
    graph.add_edge("report", END)
    return graph.compile(checkpointer=MemorySaver())


@pytest.mark.asyncio
async def test_stream_forwards_custom_data(auth_user):
    agent = build_custom_data_agent()
    transport = httpx.ASGITransport(app=app)
    with (
        patch("service.service.get_agent", return_value=agent),
        patch("service.service.agent_registry", {"edu-assistant": object()}),
    ):
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test", headers=auth_user.headers
        ) as client:
            events = []
            async with client.stream(
                "POST",
                "/api/edu-assistant/stream",
                json={"message": "hi", "thread_id": "t-custom"},
            ) as response:
                assert response.status_code == 200
                async for line in response.aiter_lines():
                    if not line.startswith("data: ") or line == "data: [DONE]":
                        continue
                    events.append(json.loads(line.removeprefix("data: ")))

    messages = [e["content"] for e in events if e["type"] == "message"]
    types = [m["type"] for m in messages]
    assert "custom" in types
    custom = next(m for m in messages if m["type"] == "custom")
    assert custom["custom_data"] == {"status": "running"}
    # 最终 AI 消息仍在
    assert any(m["type"] == "ai" and m["content"] == "all done" for m in messages)
