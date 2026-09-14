"""教学图：入口写入工作记忆（Graph State），再进 supervisor。

记忆卡进入 `TeachingState.memory_card`，并以一条 SystemMessage 让专家可见；
service 流式侧过滤 system 消息，避免污染 SSE。

记忆卡 SystemMessage 使用**固定消息 ID**（`MEMORY_CARD_MESSAGE_ID`）：
add_messages reducer 对同 ID 消息做 upsert，因此每轮只替换不累积，
不会随对话轮数把多张不同时刻的快照全部塞进模型上下文。
"""

from __future__ import annotations

import logging
from typing import NotRequired

from langchain_core.messages import RemoveMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import MessagesState

from agents.supervisor import inner_supervisor
from core import settings
from memory.runtime import get_store
from memory.safe import safe_remember
from memory.window import trim_conversation
from memory.working import abuild_memory_card

logger = logging.getLogger(__name__)

# 记忆卡固定消息 ID：同 ID 消息每轮被替换而非追加
MEMORY_CARD_MESSAGE_ID = "edu_memory_card"


class TeachingState(MessagesState, total=False):
    """工作记忆进 Graph State；每轮 invoke 由 load_memory 写入。"""

    memory_card: NotRequired[str]


async def load_memory(state: TeachingState, config=None) -> dict:
    """读 Store 生成记忆卡（超时/失败则空），写入 State。

    同时清理历史 checkpoint 里累积的旧 SystemMessage（旧版本无固定 ID，
    每轮追加一张卡），保证 state 里至多存在一张当前卡。
    """
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

    # 旧版累积的记忆卡没有固定 ID，逐条删除；当前卡由同 ID upsert 覆盖
    removes = [
        RemoveMessage(id=m.id)
        for m in (state.get("messages") or [])
        if isinstance(m, SystemMessage) and m.id and m.id != MEMORY_CARD_MESSAGE_ID
    ]

    updates: dict = {"memory_card": card}
    if card:
        updates["messages"] = [
            *removes,
            SystemMessage(content=card, id=MEMORY_CARD_MESSAGE_ID),
        ]
    elif removes:
        updates["messages"] = removes
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


# 对外唯一图：与 HTTP 注册表、LangGraph Studio 共用（含 load_memory）
edu_supervisor = build_teaching_graph()
