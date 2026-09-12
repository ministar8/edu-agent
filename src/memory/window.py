"""短期对话窗口：裁剪送入 LLM 的消息，防止长 thread 撑爆上下文。

只影响本轮模型输入；checkpointer 仍保存完整历史，/history 与断点续跑不受影响。
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    SystemMessage,
    ToolMessage,
)


def _has_tool_calls(message: BaseMessage) -> bool:
    return bool(getattr(message, "tool_calls", None))


def trim_conversation(
    messages: Sequence[Any],
    *,
    max_messages: int,
) -> list[Any]:
    """保留全部 System + 最近 max_messages 条对话；修正工具孤儿。

    max_messages <= 0 时不裁剪。
    """
    if max_messages <= 0:
        return list(messages)

    system_msgs = [m for m in messages if isinstance(m, SystemMessage)]
    chat = [m for m in messages if not isinstance(m, SystemMessage)]
    if len(chat) <= max_messages:
        trimmed = list(chat)
    else:
        trimmed = chat[-max_messages:]

    # 去掉开头孤立的 ToolMessage（其 AI tool_calls 已被裁掉）
    while trimmed and isinstance(trimmed[0], ToolMessage):
        trimmed = trimmed[1:]

    # 若以带 tool_calls 的 AI 开头但后续 Tool 不完整，整段丢掉，避免工具结果错位
    if trimmed and isinstance(trimmed[0], AIMessage) and _has_tool_calls(trimmed[0]):
        needed = len(trimmed[0].tool_calls or [])
        following_tools = 0
        for m in trimmed[1:]:
            if isinstance(m, ToolMessage):
                following_tools += 1
            else:
                break
        if following_tools < needed:
            # 从第一条非该 AI 的消息继续；若整段都是问题则可能变空，再退回
            rest = trimmed[1 + following_tools :]
            while rest and isinstance(rest[0], ToolMessage):
                rest = rest[1:]
            trimmed = rest

    return [*system_msgs, *trimmed]
