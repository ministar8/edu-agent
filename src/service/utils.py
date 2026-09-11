from collections.abc import Mapping
from typing import Any, cast

from fastapi import HTTPException
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    ToolMessage,
)
from langchain_core.messages import (
    ChatMessage as LangchainChatMessage,
)

from core import settings
from schema import ChatMessage


def ensure_model_available(model: Any) -> None:
    """模型不在白名单时抛 400。"""
    if model not in settings.AVAILABLE_MODELS:
        raise HTTPException(
            status_code=400,
            detail=f"Model '{model}' is not available. Allowed: {sorted(settings.AVAILABLE_MODELS)}",
        )


def convert_message_content_to_string(content: str | list[str | dict]) -> str:
    if isinstance(content, str):
        return content
    text: list[str] = []
    for content_item in content:
        if isinstance(content_item, str):
            text.append(content_item)
            continue
        if content_item["type"] == "text":
            text.append(content_item["text"])
    return "".join(text)


def langchain_to_chat_message(message: BaseMessage) -> ChatMessage:
    """把 LangChain 消息转换为 ChatMessage。"""
    match message:
        case HumanMessage():
            return ChatMessage(
                type="human",
                content=convert_message_content_to_string(message.content),
            )
        case AIMessage():
            ai_message = ChatMessage(
                type="ai",
                content=convert_message_content_to_string(message.content),
            )
            if message.tool_calls:
                ai_message.tool_calls = message.tool_calls
            if message.response_metadata:
                ai_message.response_metadata = message.response_metadata
            return ai_message
        case ToolMessage():
            return ChatMessage(
                type="tool",
                content=convert_message_content_to_string(message.content),
                tool_call_id=message.tool_call_id,
            )
        case LangchainChatMessage():
            if message.role == "custom":
                return ChatMessage(
                    type="custom",
                    content="",
                    custom_data=cast(dict[str, Any], message.content[0]),
                )
            raise ValueError(f"Unsupported chat message role: {message.role}")
        case _:
            raise ValueError(f"Unsupported message type: {message.__class__.__name__}")


def messages_from_checkpoint(checkpoint: Mapping[str, Any]) -> list[BaseMessage]:
    """从原始 checkpoint 中取出会话消息（兼容 functional-API 的 __previous__）。"""
    channel_values = checkpoint.get("channel_values") or {}
    messages = channel_values.get("messages")
    if not messages:
        previous = channel_values.get("__previous__")
        if isinstance(previous, Mapping):
            messages = previous.get("messages")
        elif isinstance(previous, list):
            messages = previous
    return [m for m in (messages or []) if isinstance(m, BaseMessage)]


def remove_tool_calls(content: str | list[str | dict]) -> str | list[str | dict]:
    """去掉内容里的 tool_use 项。"""
    if isinstance(content, str):
        return content
    return [
        content_item
        for content_item in content
        if isinstance(content_item, str) or content_item["type"] != "tool_use"
    ]
