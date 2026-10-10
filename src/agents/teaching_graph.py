"""教学图：入口写入工作记忆（以 SystemMessage 形态进 messages），再进 supervisor。

记忆卡以一条 SystemMessage 让专家可见，service 流式侧过滤 system 消息，避免污染 SSE。

记忆卡 SystemMessage 使用**固定消息 ID**（`MEMORY_CARD_MESSAGE_ID`）：
add_messages reducer 对同 ID 消息做 upsert，因此每轮只替换不累积，
不会随对话轮数把多张不同时刻的快照全部塞进模型上下文。
"""

from __future__ import annotations

import logging
from collections import deque

from langchain_core.messages import RemoveMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import MessagesState
from langgraph.store.base import BaseStore

from agents.supervisor import inner_supervisor
from agents.task_context import load_thread_context, remember_query_mode
from core import settings
from memory.runtime import get_store
from memory.safe import safe_remember_status
from memory.window import trim_conversation
from memory.working import abuild_memory_card

logger = logging.getLogger(__name__)

# 记忆卡固定消息 ID：同 ID 消息每轮被替换而非追加
MEMORY_CARD_MESSAGE_ID = "edu_memory_card"

# ── B4 的可观测出口：本轮读链的**状态**（`memory_read_status` 的原料）──────
#   ★ 为什么放在模块级、而不是塞进 graph state：`MessagesState` 只有 `messages` 一个
#     channel，节点返回的其它键会被 LangGraph **静默丢弃**（实测：`{"messages": [], "x": 1}`
#     ⇒ updates 流与最终 state 里都没有 `x`）。走 state 等于把状态写进黑洞。
#   ★ 与 `vectorstore._query_failures` 同构：append-only + `reset` 由取证单元在开跑前调，
#     消费方（`task_eval.runner.run_case`）在跑完后聚合成四态之一。
#   ★ 产品侧不读它 —— 它只服务「把 0.5 是不是 Store 挂了变成有证据可答」。
#
#   ★★ 修复轮 F5 的两处收紧（都是「无界进程级列表」+「自由字符串」这两个静默失效面）：
#   ① **有界**：`deque(maxlen=...)` —— 取证单元的 reset 只有两个边界（`retrieval_gate`、
#      `task_eval.runner.run_case`），**产品侧**（service / CLI 真用户会话）没人调 reset
#      ⇒ 原来的 `list` 会在长跑进程里无界增长（每轮一条，永不回收）。
#      容量取 `_MEMORY_READ_STATUS_CAPACITY = 64`：实测一个取证单元最多 **3** 条
#      （`evals/datasets/demo` 全部 66 条 case 的 `len(all_turns)` 上限 = 3，
#      一条 memory case = 2 段会话 / 3 轮 ⇒ `load_memory` 每轮各调一次），
#      64 = 该上限的 20 倍以上余量，够覆盖 supervisor 重入 / 重试的最坏情况，
#      又把「一个进程最多攒多少条」钉成常数（≈64 个短字符串，可忽略的驻留）。
#      ★ 满容量时 `deque` 丢**最旧**一条 ⇒ 写入口在满时先打 ERROR（丢证据必须是**可见**事件）。
#   ② **取值有界**：只有四态字符串能进这条通道（`""` 只是**读取侧**的「未记录」默认值，
#      不是可写入的第五态）。非法值 ⇒ 拒绝入列并报警（宁可少一条明细，也不稀释四态口径）。
_MEMORY_READ_STATUS_CAPACITY = 64
MEMORY_READ_STATUS_VALUES: frozenset[str] = frozenset(
    {"not_attempted", "success", "empty", "failed"}
)
_MEMORY_READ_STATUSES: deque[str] = deque(maxlen=_MEMORY_READ_STATUS_CAPACITY)


def record_memory_read_status(status: str) -> None:
    """★ 读链状态的**唯一写入口**（四态之外的值进不来）。

    返回值本身不携带信息 ⇒ 用 `memory_read_statuses()` 读回明细。
    非法值（含 `""`、None、拼错的态名）**不落列**：`aggregate_memory_read_status` 的
    四态口径是契约（§5 B4），让第五种值进来 = 把「测不到 / 没卡 / 有卡 / 没尝试」
    这四件事实重新压回一个自由字符串 —— 正是 B4 要消除的折叠。
    ★ 丢弃是**可见**事件（ERROR 日志带原值），不静默。
    """
    if status not in MEMORY_READ_STATUS_VALUES:
        logger.error(
            "忽略非法的 memory 读链状态 %r（允许值=%s）—— 明细不落列，四态口径不被稀释",
            status,
            sorted(MEMORY_READ_STATUS_VALUES),
        )
        return
    if len(_MEMORY_READ_STATUSES) == _MEMORY_READ_STATUS_CAPACITY:
        logger.error(
            "memory 读链明细已达容量 %d：本次将丢弃**最旧**一条 —— "
            "说明取证单元没在边界调 reset（或单单元轮数远超实测上限 3），聚合可能看不到早期故障",
            _MEMORY_READ_STATUS_CAPACITY,
        )
    _MEMORY_READ_STATUSES.append(status)


def reset_memory_read_statuses() -> None:
    """取证单元开跑前清空（否则上一条 case 的故障会一路跟着下一条）。"""
    _MEMORY_READ_STATUSES.clear()


def memory_read_statuses() -> list[str]:
    """本次捕获到的读链状态，按发生顺序（每轮 `load_memory` 追加一条），容量有界。"""
    return list(_MEMORY_READ_STATUSES)


async def abuild_card_with_status(
    store: BaseStore | None, uid: int | str | None
) -> tuple[str, str]:
    """读 Store 生成记忆卡，并返回**四态里的那一态**（B4）。

    值域：`not_attempted`（没有 `uid`，压根没读）/ `failed`（超时或抛错）/
    `empty`（读成功但没卡）/ `success`（读成功且有卡）。

    ★ 旧实现在调用点写 `await safe_remember(...) or ""` —— 于是
      「Store 挂了」与「画像确实是空的」压成同一个空串（§4.3 Memory 三维那一行）。
      空串只能说明**没有卡**，不能说明**为什么没有卡**；分开返回才谈得上归因。
    """
    if uid is None:
        return "", "not_attempted"  # ★ 今天这条路被压成 ""
    card, status = await safe_remember_status(
        lambda: abuild_memory_card(store, uid),
        label="memory_card",  # type: ignore[arg-type]
    )
    if status != "success":
        return "", status
    return (card or ""), ("success" if card else "empty")


async def load_memory(state: MessagesState, config=None) -> dict:
    """读 Store 生成记忆卡（超时/失败则空），以固定 ID SystemMessage 注入 messages。
    同时清理历史 checkpoint 里累积的旧 SystemMessage（旧版本无固定 ID，
    每轮追加一张卡），保证 state 里至多存在一张当前卡。
    """
    uid = None
    if config is not None:
        uid = (config.get("configurable") or {}).get("user_id")
    store = get_store()
    card, read_status = await abuild_card_with_status(store, uid)
    # ★ 落状态，不落布尔：`load_memory` 每轮都被调用一次，捕获到的顺序就是读链发生的顺序。
    #   记在这里而不是 state（见 `_MEMORY_READ_STATUSES` 的说明），且**只经唯一写入口**
    #   （四态之外的值进不来、容量有界 —— 见 `record_memory_read_status`）。
    record_memory_read_status(read_status)

    # 旧版累积的记忆卡没有固定 ID，逐条删除；当前卡由同 ID upsert 覆盖
    removes = [
        RemoveMessage(id=m.id)
        for m in (state.get("messages") or [])
        if isinstance(m, SystemMessage) and m.id and m.id != MEMORY_CARD_MESSAGE_ID
    ]

    updates: dict = {}
    if card:
        updates["messages"] = [
            *removes,
            SystemMessage(content=card, id=MEMORY_CARD_MESSAGE_ID),
        ]
    elif removes:
        updates["messages"] = removes

    # 多轮 task_mode：载入线程上下文，并记住本轮用户 query 的 mode
    try:
        conf = (config or {}).get("configurable") or {}
        tid = str(conf.get("thread_id") or "")
        load_thread_context(tid, config)
        last_user = ""
        for m in reversed(state.get("messages") or []):
            if getattr(m, "type", "") == "human" or m.__class__.__name__ == "HumanMessage":
                last_user = str(getattr(m, "content", "") or "")
                break
        if last_user:
            remember_query_mode(last_user, thread_id=tid, config=config)
    except Exception:
        logger.debug("task_context track failed", exc_info=True)

    return updates


async def run_supervisor(state: MessagesState, config=None) -> dict:
    raw = state.get("messages") or []
    # 只裁剪「本轮送给模型的输入」；state/checkpointer 仍保留完整历史
    trimmed = trim_conversation(raw, max_messages=settings.MEMORY_HISTORY_MAX_MESSAGES)
    result = await inner_supervisor.ainvoke({"messages": trimmed}, config=config)
    if isinstance(result, dict):
        return {"messages": result.get("messages") or []}
    return {}


def build_teaching_graph():
    builder: StateGraph = StateGraph(MessagesState)
    builder.add_node("load_memory", load_memory)
    builder.add_node("supervisor", run_supervisor)
    builder.add_edge(START, "load_memory")
    builder.add_edge("load_memory", "supervisor")
    builder.add_edge("supervisor", END)
    return builder.compile()


# 对外唯一图：与 HTTP 注册表、LangGraph Studio 共用（含 load_memory）
edu_supervisor = build_teaching_graph()
