"""SSE 消息流的构造与筛选（从 service.py 拆出，行为等价）。"""

from __future__ import annotations

import inspect
import json
from typing import Any

from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    BaseMessage,
    SystemMessage,
    ToolMessage,
)

from schema import StreamInput
from service.utils import convert_message_content_to_string, remove_tool_calls

# 防御性兜底：langgraph-supervisor 的回传控制消息（英文），不应透传给用户。
#
# 当前 supervisor 装配为 add_handoff_back_messages=False，库不会产生此类消息，
# 因此这段过滤**没有活路径**。保留是为了在配置被改回 / 库版本变更时仍能挡住 ——
# 属于「有备无患」而非「正在生效」的防护，勿据此认为系统依赖它。
_HANDOFF_BACK_PREFIXES = (
    "Transferring back to ",
    "Successfully transferred back to ",
)


def _create_ai_message(parts: dict) -> AIMessage:
    sig = inspect.signature(AIMessage)
    valid_keys = set(sig.parameters)
    filtered = {k: v for k, v in parts.items() if k in valid_keys}
    return AIMessage(**filtered)


def _last_user_visible_message(messages: list[BaseMessage]) -> BaseMessage:
    """从消息尾部回溯，取最后一条用户可见的消息。

    ``values`` 流的末条消息未必是给用户看的最终回答：专家可能以空 content（或带
    tool_calls 的中间步骤）收尾，直接取 ``messages[-1]`` 会返回空气泡。这里复用 SSE
    侧的可见性判定（``_is_user_visible_message``），与流式路径保持同一口径。

    全部不可见时回退到原始末条，保证返回值类型仍是 BaseMessage、不会返回 None。
    """
    for message in reversed(messages):
        if _is_user_visible_message(message):
            return message
    return messages[-1]


def _is_user_visible_message(message: Any) -> bool:
    """SSE message 流只放行用户可见的对话内容。

    updates 流（含 subgraphs）会把同一最终消息从内层节点（model/agent）与外层包装
    节点各报一次，并夹带路由/工具中间消息：

    - SystemMessage：工作记忆卡，只进模型上下文
    - ToolMessage：工具结果与 handoff 控制消息，不是对话气泡
    - 带 tool_calls 或空内容的 AIMessage：分派决策与中间步骤，不是最终回答
    - 同 ID 消息只发一次（配合 message_generator 里的 seen_ids 去重）
    """
    if isinstance(message, SystemMessage | ToolMessage):
        return False
    if isinstance(message, AIMessage):
        content = message.content
        if not content or (isinstance(content, str) and not content.strip()):
            return False
        if message.tool_calls:
            return False
    return True


def _collect_stream_messages(stream_mode: str, event: Any) -> list[Any]:
    """按 stream_mode 从事件里收集候选消息（updates / custom；messages 走 token 支路）。"""
    if stream_mode == "updates":
        out: list[Any] = []
        for node, updates in event.items():
            if node == "__interrupt__":
                # 生成器代替「for + append」：少 1 判定点（backlog #36 第三步）
                out.extend(AIMessage(content=i.value) for i in updates)
                continue
            # 内层/外层节点统一收集，交给 _is_user_visible_message + ID 去重筛选
            out.extend((updates or {}).get("messages", []))
        return out
    if stream_mode == "custom":
        # CustomData.dispatch 写出的 LangChain ChatMessage(role=custom)
        return [event]
    return []


def _normalize_messages(new_messages: list[Any]) -> list[Any]:
    """把 (key, value) 分片拼成 AIMessage，其余消息原样保留。"""
    processed: list[Any] = []
    current: dict[str, Any] = {}
    for message in new_messages:
        if isinstance(message, tuple):
            key, value = message
            current[key] = value
        else:
            if current:
                processed.append(_create_ai_message(current))
                current = {}
            processed.append(message)
    if current:
        processed.append(_create_ai_message(current))
    return processed


def _token_sse(event: Any, user_input: StreamInput) -> list[str]:
    """把 messages 模式的一个 chunk 转成 token SSE 帧（该 stream 未开或无内容时返回空）。"""
    if not user_input.stream_tokens:
        return []
    msg, metadata = event
    if "skip_stream" in metadata.get("tags", []) or not isinstance(msg, AIMessageChunk):
        return []
    content = remove_tool_calls(msg.content)
    if not content:
        return []
    payload = {"type": "token", "content": convert_message_content_to_string(content)}
    return [f"data: {json.dumps(payload)}\n\n"]
