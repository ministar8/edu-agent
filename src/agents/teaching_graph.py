"""教学图：入口写入工作记忆（Graph State），再进 supervisor。

记忆卡进入 `TeachingState.memory_card`，并以一条 SystemMessage 让专家可见；
service 流式侧过滤 system 消息，避免污染 SSE。
"""

from __future__ import annotations

import logging
from typing import NotRequired

from langchain_core.messages import SystemMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import MessagesState

from agents.supervisor import inner_supervisor
from core import settings
from memory.runtime import get_store
from memory.safe import safe_remember
from memory.window import trim_conversation
from memory.working import abuild_memory_card

logger = logging.getLogger(__name__)


class TeachingState(MessagesState, total=False):
    """工作记忆进 Graph State；每轮 invoke 由 load_memory 写入。"""

    memory_card: NotRequired[str]


async def load_memory(state: TeachingState, config=None) -> dict:
    """读 Store 生成记忆卡（超时/失败则空），写入 State。"""
    uid = None
    if config is not None:
        conf = dict(config.get("configurable") or {})
        uid = conf.get("user_id")
    store = get_store()
    card = ""
    if uid is not None:
        card = (
            await safe_remember(lambda: abuild_memory_card(store, uid), label="memory_card") or ""
        )
    updates: dict = {"memory_card": card}
    if card:
        updates["messages"] = [SystemMessage(content=card)]
    return updates


async def run_supervisor(state: TeachingState, config=None) -> dict:
    raw = state.get("messages") or []
    # 只裁剪「本轮送给模型的输入」；state/checkpointer 仍保留完整历史
    trimmed = trim_conversation(raw, max_messages=settings.MEMORY_HISTORY_MAX_MESSAGES)
    result = await inner_supervisor.ainvoke({"messages": trimmed}, config=config)
    if isinstance(result, dict):
        return {"messages": result.get("messages") or []}
    return {}


def build_teaching_graph():
    builder: StateGraph = StateGraph(TeachingState)
    builder.add_node("load_memory", load_memory)
    builder.add_node("supervisor", run_supervisor)
    builder.add_edge(START, "load_memory")
    builder.add_edge("load_memory", "supervisor")
    builder.add_edge("supervisor", END)
    return builder.compile()
