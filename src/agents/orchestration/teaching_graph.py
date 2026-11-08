"""教学图：任务初始化 → 写入工作记忆 → supervisor → 收尾。

管线：``prepare_task → load_memory → supervisor → finalize``。
``prepare_task`` 负责 task_id / context_mode；``load_memory`` 只写记忆卡；
``supervisor`` 做边界 A 的白名单搬运并推断执行者；``finalize`` 判定业务结果。

记忆卡以一条 SystemMessage 让专家可见，service 流式侧过滤 system 消息，避免污染 SSE。

记忆卡 SystemMessage 使用**固定消息 ID**（`MEMORY_CARD_MESSAGE_ID`）：
add_messages reducer 对同 ID 消息做 upsert，因此每轮只替换不累积，
不会随对话轮数把多张不同时刻的快照全部塞进模型上下文。
"""

import logging
import uuid
from collections import deque
from typing import Any

from langchain_core.messages import AnyMessage, HumanMessage, RemoveMessage, SystemMessage
from langgraph.config import RunnableConfig
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.store.base import BaseStore

from agents.orchestration.state import (
    SpecialistRunError,
    SupervisorRunError,
    TeachingState,
    has_final_answer,
    infer_execution,
)
from agents.orchestration.supervisor import UnclosedSpecialistOutput, inner_supervisor
from agents.orchestration.task_context import set_context_mode
from core import settings
from memory.runtime import get_store
from memory.safe import safe_remember_status
from memory.window import trim_conversation
from memory.working import abuild_memory_card
from schema.task_policy import TaskMode as RetrievalMode

logger = logging.getLogger(__name__)

# 记忆卡固定消息 ID：同 ID 消息每轮被替换而非追加
MEMORY_CARD_MESSAGE_ID = "edu_memory_card"

# ── B4 的可观测出口：本轮读链的**状态**（`memory_read_status` 的原料）──────
#   ★ 为什么放在模块级、而不是塞进 graph state：这是**取证**通道（一个评测单元有多条
#     明细、由边界统一 reset），不是业务状态。写进 checkpoint 会随线程永久累积，
#     而 reset 只发生在取证单元边界（产品侧没人调）。
#     （历史上 `MessagesState` 只有 messages 一个 channel、节点返回的其它键会被静默丢弃；
#      现在 `TeachingState` 已有业务字段，但这条通道的用途没变：只服务四态归因。）
#   ★ 与 `vectorstore._query_failures` 同构：append-only + `reset` 由取证单元在开跑前调，
#     消费方（`task_eval.runner.run_case`）在跑完后聚合成四态之一。
#   ★ 产品侧不读它 —— 它只服务「把 0.5 是不是 Store 挂了变成有证据可答」。
#
#   ★★ 修复轮 F5 的两处收紧（都是「无界进程级列表」+「自由字符串」这两个静默失效面）：
#   ① **有界**：`deque(maxlen=...)` —— 取证单元的 reset 只有两个边界（`retrieval_gate`、
#      `task_eval.runner.run_case`），**产品侧**（service / CLI 真用户会话）没人调 reset
#      ⇒ 原来的 `list` 会在长跑进程里无界增长（每轮一条，永不回收）。
#      容量取 `_MEMORY_READ_STATUS_CAPACITY = 64`：一个取证单元通常约 **3** 条
#      （一条 memory case 为 2 段会话 / 3 轮 ⇒ `load_memory` 每轮各调一次），
#      64 = 该量级的 20 倍以上余量，够覆盖 supervisor 重入 / 重试的最坏情况，
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


def _last_human_text(messages: list[AnyMessage]) -> str:
    for message in reversed(messages):
        if isinstance(message, HumanMessage):
            return str(message.content or "")
    return ""


def _classify(query: str, previous: RetrievalMode | None) -> RetrievalMode | None:
    """从用户 query 识别检索策略模式；失败或无 query 时沿用上一轮。"""
    if not query:
        return previous
    try:
        from rag.retrieval.task_policy import classify_task_mode

        return classify_task_mode(query, context_mode=previous)
    except Exception:
        return previous


async def prepare_task(state: TeachingState, config: RunnableConfig | None = None) -> dict:
    """每次 invoke 开一个新任务：生成 task_id，重置任务字段；messages 不动。

    ``context_mode`` 是线程级字段：从恢复的 state 读上一轮值，分类后写回，不随任务重置。
    这里**不** set_context_mode —— 实测 ContextVar 不跨节点传播，真正生效的位置在
    ``run_supervisor`` 里、``ainvoke`` 之前。
    """
    conf = dict((config or {}).get("configurable") or {})
    thread_id = str(conf.get("thread_id") or "")
    request_id = str(conf.get("request_id") or "") or str(uuid.uuid4())

    ctx_mode = _classify(
        _last_human_text(state.get("messages") or []),
        state.get("context_mode"),
    )

    return {
        "task_id": f"{thread_id}:{request_id}",
        "task_mode": "unknown",
        "task_context": {},
        "context_mode": ctx_mode,
        "active_agent": None,
        "task_status": "pending",
        "task_result": None,
        "error": None,
    }


async def load_memory(state: TeachingState, config: RunnableConfig | None = None) -> dict:
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

    return updates


# 边界 A 的入参白名单：外层 TeachingState → 内层 SupervisorState。
# 不进 payload 的字段，内层就是拿不到（刻意用白名单，新增字段时才会被迫显式决定）。
_INBOUND_KEYS = ("task_context", "context_mode")


async def run_supervisor(state: TeachingState, config: RunnableConfig | None = None) -> dict:
    raw = state.get("messages") or []
    # 只裁剪「本轮送给模型的输入」；state/checkpointer 仍保留完整历史
    trimmed = trim_conversation(raw, max_messages=settings.MEMORY_HISTORY_MAX_MESSAGES)
    payload: dict[str, Any] = {"messages": trimmed}
    payload.update({k: state[k] for k in _INBOUND_KEYS if k in state})

    # ContextVar 未必能跨嵌套图传播：这里再设一次，兜住检索链里的同步读取。
    set_context_mode(state.get("context_mode"))

    # 异常分段（§4.5）：本节点是唯一同时看到内外两层的地方，包装后再上抛，
    # 服务层 `_mark_failed` 用 `stage_of(exc)` 写 TaskError.stage，不按消息猜。
    # 专家合约破坏 → specialist；其余内层失败 → supervisor（含未包装的工具冒泡）。
    try:
        result = await inner_supervisor.ainvoke(payload, config=config)
    except (SupervisorRunError, SpecialistRunError):
        raise  # 已打标，避免二次包装丢 stage
    except UnclosedSpecialistOutput as e:
        raise SpecialistRunError(str(e)) from e
    except Exception as e:
        raise SupervisorRunError(str(e)) from e
    if not isinstance(result, dict):
        return {}

    # active_agent / task_mode 独立推断；异常路径不会走到这里（异常直接上抛）。
    inferred = infer_execution(result.get("messages") or [], run_ok=True)
    return {
        "messages": result.get("messages") or [],
        **inferred,
    }


async def finalize(state: TeachingState, config: RunnableConfig | None = None) -> dict:
    """正常路径收尾：有终答才算 completed，否则记 EMPTY_RESULT。"""
    if has_final_answer(state.get("messages") or []):
        return {"task_status": "completed"}
    return {
        "task_status": "failed",
        "error": {
            "code": "EMPTY_RESULT",
            "message": "本轮没有产出可返回的结果",
            "stage": "finalize",
            "recoverable": True,
        },
    }


def build_teaching_graph() -> CompiledStateGraph:
    builder: StateGraph = StateGraph(TeachingState)
    builder.add_node("prepare_task", prepare_task)
    builder.add_node("load_memory", load_memory)
    builder.add_node("supervisor", run_supervisor)
    builder.add_node("finalize", finalize)
    builder.add_edge(START, "prepare_task")
    builder.add_edge("prepare_task", "load_memory")
    builder.add_edge("load_memory", "supervisor")
    builder.add_edge("supervisor", "finalize")
    builder.add_edge("finalize", END)
    return builder.compile()


# 对外唯一图：与 HTTP 注册表、LangGraph Studio 共用（含 load_memory）
edu_supervisor = build_teaching_graph()
