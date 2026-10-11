"""Agent 行为冒烟的会话运行机器（建身份 / 清理 / 跑轮次与会话）。

★ 从 `agent_behavior_smoke.py` 拆出；对外仍经 `agent_behavior_smoke` re-export。
"""

from __future__ import annotations

import json
import re
import sys
import uuid
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from _smoke_model import _GRADE_FULL_SCORE, _GRADE_SCORE_RE, CaseResult  # noqa: E402
from langchain_core.messages import (  # noqa: E402
    AIMessageChunk,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.runnables import RunnableConfig  # noqa: E402

from agents.teaching_graph import MEMORY_CARD_MESSAGE_ID  # noqa: E402
from memory.episodes import arecent_episodes  # noqa: E402
from memory.namespaces import student_episodes_ns, student_profile_ns  # noqa: E402


def make_user_id(case_id: str) -> str:
    """为一条 case 生成**独立**的 user_id（Step 4 硬要求）。

    为什么要独立
    ------------
    Store 的长期记忆按 ``("student", user_id, ...)`` 命名空间隔离。若所有 case 共用
    一个 ``user_id``，上一 case 写入的 ``weak_topics`` 会**残留**到下一 case，使
    ``recalled`` 变成「串味」的结果 —— 明明本 case 没写，却能召回。

    为什么带随机后缀
    ----------------
    ``case_id`` 在同一 case 的**多次重跑**间保持不变，若只按 ``case_id`` 命名，
    上一次跑失败留下的脏数据会污染下一次重跑。加短随机后缀 ⇒ **每次调用都是全新身份**，
    重跑天然干净（与 ``_cleanup_user_store`` 双保险）。

    ★ 与 ``run_turns`` 的兼容：``run_turns`` 仍用固定 ``"behavior-smoke"``（既有行为，
      未改动）；本函数只服务 Memory 评测。
    """
    safe = re.sub(r"[^0-9A-Za-z_-]+", "-", case_id).strip("-") or "case"
    return f"eval-{safe}-{uuid.uuid4().hex[:8]}"


async def _cleanup_user_store(store, user_id: str) -> int:
    """跑前清理该 user 的 Store 数据，返回删除条数（Step 4 硬要求）。

    清理**两个**命名空间（缺一不可）：

    - ``student/{uid}/profile`` —— 画像（含 ``weak_topics``），记忆卡的直接来源；
    - ``student/{uid}/episodes`` —— 情节记忆，``compute_weak_topics`` 的输入。

    ★ 只清自己的 user ⇒ 不影响其他 case / 生产数据。
    ★ 任何异常只记 note 不抛 —— 清理失败应表现为「基线可能不干净」的可见警告，
      **不是**让整轮评测崩掉。
    """
    removed = 0
    for ns in (student_profile_ns(user_id), student_episodes_ns(user_id)):
        try:
            items = await store.asearch(ns, limit=500)
            for it in items:
                await store.adelete(ns, it.key)
                removed += 1
        except Exception as e:  # noqa: BLE001
            print(f"    （清理 {ns} 时忽略：{type(e).__name__}: {e}）")
    return removed


async def _cleanup_threads(checkpointer, thread_ids: list[str]) -> int:
    """删除这些 thread 的检查点，返回删除条数（Step 4 硬要求，2026-10-06 补）。

    为什么必须补
    ------------
    `thread_id` 由 `user_id` 派生，而 `user_id` 含**随机后缀** ⇒ 每次跑（含重跑）
    产生的 thread **永不复用**。这带来两个后果：

    - 好的一面：**不会串味**（新 case 绝不可能命中旧 thread）；
    - 坏的一面：旧检查点**不会被任何代码回收**，在 `checkpoints.db` 里持续累积。

    故「跑后清理」是**资源生命周期**的补齐，而非正确性修复。评测跑完必须干净。

    ★ 用 `finally` 调用（见 `run_sessions`）：case 中途抛异常也必须清理，
      否则失败的那条 case 会留下残留 —— 而失败重跑恰恰是最需要干净起点的场景。

    ★ 删除失败只记 note 不抛：清理属收尾，不该把一次成功的评测变成失败。
    """
    if checkpointer is None:
        return 0
    removed = 0
    for tid in thread_ids:
        if not tid:
            continue
        try:
            config = RunnableConfig(configurable={"thread_id": tid})
            # 优先用官方 adelete_thread（一次清掉主记录 + 各 checkpoint 写入）
            deleter = getattr(checkpointer, "adelete_thread", None)
            if callable(deleter):
                await deleter(tid)
                removed += 1
                continue
            # 回退：历遍该 thread 的全部检查点逐个删（兼容无 adelete_thread 的实现）
            alist = getattr(checkpointer, "alist", None)
            adelete = getattr(checkpointer, "adelete", None)
            if callable(alist) and callable(adelete):
                async for tup in alist(config):
                    cid = getattr(tup, "config", {}).get("configurable", {}).get("checkpoint_id")
                    if cid:
                        await adelete(
                            RunnableConfig(configurable={"thread_id": tid, "checkpoint_id": cid})
                        )
                        removed += 1
        except Exception as e:  # noqa: BLE001
            print(f"    （清理 thread {tid} 时忽略：{type(e).__name__}: {e}）")
    return removed


def _parse_tool_payload(msg: ToolMessage) -> dict[str, Any] | None:
    raw = msg.content if isinstance(msg.content, str) else json.dumps(msg.content)
    try:
        obj = json.loads(raw)
    except Exception:  # noqa: BLE001
        return None
    return obj if isinstance(obj, dict) else None


def _parse_grade_score(content: str) -> float | None:
    """从批改工具文本里抓**得分**（0–100）。抓不到 ⇒ None。

    ★ 为什么必须显式抓分（2026-10-06 Step 5 case-validity）：
      case 的前置条件（mem-004「低分」/ mem-006「高分」）不能**假定**模型给多少分 ——
      必须由**实际批改输出**验收。抓不到分 ⇒ 该 case 无法验收有效性，应显式标出，
      而不是默认「假设它满足」。
    """
    m = _GRADE_SCORE_RE.search(str(content or ""))
    if not m:
        return None
    score = float(m.group(1))
    full = float(m.group(2)) if m.group(2) else _GRADE_FULL_SCORE
    if full and full != _GRADE_FULL_SCORE:
        score = score / full * _GRADE_FULL_SCORE  # 归一化到 100 制
    return score


def _record_grade_score(case: CaseResult, session_idx: int, score: float | None) -> None:
    """登记一次批改得分（含其所在会话下标）；`None` 也登记（表示「调用但未抓到分」）。"""
    case.grade_scores.append({"session": session_idx, "score": score})


_GRADE_TOOL_NAME = "grade_student_answer"


def _capture_tool_result(case: CaseResult, msg: ToolMessage, *, session_idx: int) -> None:
    """统一登记一次工具调用结果：JSON 载荷进 `tool_payloads`，批改分进 `grade_scores`。

    ★ 批改结果**不是 JSON**（是对话体文本）⇒ 只能靠 `msg.name` 识别 + 正则提分。
      两类结果都从同一个入口登记，避免以后新增工具时漏记。
    """
    name = str(getattr(msg, "name", "") or "")
    if name == _GRADE_TOOL_NAME or name.endswith("grade_student_answer"):
        _record_grade_score(case, session_idx, _parse_grade_score(str(msg.content or "")))
    p = _parse_tool_payload(msg)
    if p is not None:
        case.tool_payloads.append(p)


async def run_turns(agent, turns: list[str]) -> CaseResult:
    """跑一轮或多轮对话，收集最终回复与 ToolMessage 载荷。"""
    thread = f"smoke-{uuid.uuid4().hex[:10]}"
    config = RunnableConfig(configurable={"thread_id": thread, "user_id": "behavior-smoke"})
    case = CaseResult(name=" | ".join(t[:18] for t in turns))
    reply_parts: list[str] = []

    for text in turns:
        reply_parts.clear()
        try:
            async for ev in agent.astream(
                {"messages": [HumanMessage(content=text)]},
                config=config,
                stream_mode=["messages"],
                subgraphs=True,
            ):
                ns, mode, payload = ev
                if mode != "messages":
                    continue
                msg = payload[0]
                if isinstance(msg, ToolMessage):
                    _capture_tool_result(case, msg, session_idx=0)
                elif isinstance(msg, AIMessageChunk):
                    reply_parts.append(str(msg.content or ""))
        except Exception as e:  # noqa: BLE001
            case.hard_fails.append(f"invoke 抛错: {type(e).__name__}: {e}")
            return case

    case.reply = "".join(reply_parts).strip()
    if not case.reply:
        case.hard_fails.append("最终回复为空")
    return case


_UNSET = object()


def _off_arm_disable(agent, store) -> Any | None:
    """OFF 臂：摘掉**两处** store，返回需恢复的进程级旧值（#24）。

    ★ 必须两处一起摘：`teaching_graph.load_memory` 与 `remember._record_episode` 都在
      **调用时**取进程级 `get_store()`，只看 `agent.store` 是关不掉记忆的 ——
      旧实现因此「OFF 组照样写、照样召回」，paired control 一直是假的。
    """
    from memory.runtime import get_store, set_store

    prev_global = get_store()
    if store is not None:
        agent.store = None
    set_store(None)
    return prev_global


def _off_arm_restore(agent, store, prev_global: Any | None) -> None:
    """恢复两处。★ 进程级那条若忘恢复，之后所有 case 会**静默**失去记忆
    （`_record_episode` 见 None 只打 debug 日志、不报错）—— 比不恢复 agent 严重得多。
    """
    from memory.runtime import set_store

    set_store(prev_global)
    if store is not None:
        agent.store = store


def _record_card(case: CaseResult, content: str) -> None:
    """记录记忆卡（去重：同 ID 消息每轮被替换而非追加，可能重复触发）。"""
    text = content.strip()
    if text and text not in case.memory_cards:
        case.memory_cards.append(text)


# ==========================================================================
# 跑**多段会话**（Memory 评测专用）：每段新 ``thread_id``、**同一** ``user_id``。
#
# 为什么必须这样
# --------------
# 要证明「用的是 **Store 长期记忆**」而不是「**checkpointer 会话内历史**」，必须让
# 写入段与读取段**互不共享会话**，只经 Store 相连：
#
#     Session A（thread-A）──写──► Store ──读──► Session B（thread-B）
#                                   ▲
#                       user_id 相同才连得上；thread 不同才隔离
#
# 同时**捕获记忆卡**：``load_memory`` 每轮把 Store 读出的记忆以固定 ID
# （``MEMORY_CARD_MESSAGE_ID``）的 SystemMessage 注入 state。把它收下来，
# ``recalled`` 就能**从证据判定**，不必让 judge 猜。
#
# ★ 与 ``run_turns`` 的区别：``run_turns`` 是单 thread 跑完全部轮次（既有行为，
#   未改动）；本函数**每段会话换 thread**，这是 Memory 跨会话验证的前提。
#
# ``cleanup_first``：跑前清理该 ``user_id`` 的 Store 数据（Step 4 硬要求）。
# 依赖 ``agent.store`` 已装配（与 ``service.lifespan`` / ``task_eval.runner`` 一致）；
# store 不可用时跳过并记 note，不抛。
#
# ★ **跑后清理**（2026-10-06 补）：无论成功、失败还是中途抛错，都在 ``finally`` 里
#   同时清掉 Store 与 **checkpointer** 的本次 thread。理由见 ``_cleanup_threads``。
#
# ★★ **paired control：``store_enabled=False``**（2026-10-06 Step 5 补）：
#   这是证明「B 段的记忆**确实来自 Store**」的关键对照。仅靠「Store ON 时 B 召回」
#   只能说明「召回了」，不能排除「B 段碰巧提到该 KP」或「checkpointer 泄漏」。
#   加 Store OFF 组后，证据链变成：
#
#       Store ON  → B 段有 memory card → recalled_actual = True
#       Store OFF → B 段无 memory card → recalled_actual = False
#
#   两组**只差 Store 开关**这一个变量 ⇒ 差异只能归因于 Store。
#
#   实现方式：把 ``agent.store`` 临时置 `None`（不改产品代码、不动全局单例的其它字段），
#   跑完在 ``finally`` 恢复。`load_memory` 读到 `store=None` 时不注入记忆卡
#   ⇒ `memory_cards` 为空 ⇒ 机械判定自然给出 `recalled_actual=False`。
#   **注意**：本组**不做** Store 清理（无 store 可清），避免 note 噪声。
# ==========================================================================


def _setup_store_arm(agent, store, store_enabled, case) -> tuple[Any, Any]:
    """配对对照的 OFF 臂：临时摘掉 store，返回 ``(prev_global_store, eff_store)``。"""
    prev_global_store = _UNSET
    if not store_enabled:
        prev_global_store = _off_arm_disable(agent, store)
        case.notes.append(
            "paired control：Store OFF（同时置空 agent.store 与进程级 get_store() —— "
            "缺后者则 load_memory/record_grade 仍在读写，对照无效）"
        )
    return prev_global_store, (store if store_enabled else None)


async def _cleanup_before_run(store, user_id, cleanup_first, store_enabled, case) -> None:
    """跑前清理（Step 4 硬要求：起点必须干净）。"""
    if not (cleanup_first and store_enabled):
        return
    if store is None:
        case.notes.append("cleanup 跳过：agent.store 未装配（基线可能不干净，需检查装配方式）")
        return
    removed = await _cleanup_user_store(store, user_id)
    case.notes.append(f"跑前清理 user={user_id}：删除 {removed} 项 Store 数据")


async def _stream_turn(agent, text, config, case, si) -> tuple[str, list[str]]:
    """跑一轮并捕获工具载荷/批改分与记忆卡；返回 ``(本轮回复, 本轮工具名列表)``。

    异常**不**在此吞 —— 由调用方记 hard_fail 并收尾（per-turn 起点快照由调用方算）。
    """
    reply_parts: list[str] = []
    turn_tools: list[str] = []
    async for ev in agent.astream(
        {"messages": [HumanMessage(content=text)]},
        config=config,
        stream_mode=["messages", "updates"],
        subgraphs=True,
    ):
        ns, mode, payload = ev
        if mode == "messages":
            msg = payload[0]
            if isinstance(msg, ToolMessage):
                turn_tools.append(str(getattr(msg, "name", "") or ""))
                _capture_tool_result(case, msg, session_idx=si)
            elif isinstance(msg, AIMessageChunk):
                reply_parts.append(str(msg.content or ""))
            elif (
                isinstance(msg, SystemMessage)
                and getattr(msg, "id", None) == MEMORY_CARD_MESSAGE_ID
            ):
                # 记忆卡也走 messages 流（部分版本）—— 兜底捕获
                _record_card(case, str(msg.content or ""))
        elif mode == "updates" and isinstance(payload, dict):
            # `load_memory` 节点返回 {"messages": [SystemMessage(记忆卡)]}
            for node_out in payload.values():
                for m in (node_out or {}).get("messages") or []:
                    if (
                        isinstance(m, SystemMessage)
                        and getattr(m, "id", None) == MEMORY_CARD_MESSAGE_ID
                    ):
                        _record_card(case, str(m.content or ""))
    return "".join(reply_parts).strip(), turn_tools


async def _read_written_episodes(eff_store, user_id, case) -> None:
    """读 Store 里本次真正写入的 episodes（**必须在跑后清理之前**）。"""
    if eff_store is None:
        return
    try:
        eps = await arecent_episodes(eff_store, user_id, limit=20)
        for e in eps:
            case.episodes.append(
                {
                    "topic": e.topic,
                    "score": e.score,
                    "knowledge_points": list(e.knowledge_points or []),
                    "type": str(e.type),
                }
            )
    except Exception as e:  # noqa: BLE001
        case.episodes_read_failed = True
        case.notes.append(f"读取 episodes 失败：{type(e).__name__}: {e}")


async def run_sessions(
    agent,
    sessions: list[list[str]],
    *,
    user_id: str,
    cleanup_first: bool = True,
    store_enabled: bool = True,
) -> CaseResult:
    """跑多段会话（Memory 评测）：每段新 ``thread_id``、**同一** ``user_id``（设计见上方注释）。"""
    case = CaseResult(name=" | ".join(t[:14] for t in (sessions[0] if sessions else [])))
    case.user_id = user_id
    case.store_enabled = store_enabled
    store = getattr(agent, "store", None)
    checkpointer = getattr(agent, "checkpointer", None)
    used_threads: list[str] = []
    prev_global_store, eff_store = _setup_store_arm(agent, store, store_enabled, case)
    await _cleanup_before_run(store, user_id, cleanup_first, store_enabled, case)
    try:
        for si, turns in enumerate(sessions):
            thread = f"eval-{user_id}-s{si}"  # 每段新 thread ⇒ 无上一段历史
            used_threads.append(thread)
            config = RunnableConfig(configurable={"thread_id": thread, "user_id": user_id})
            reply = ""
            for ti, text in enumerate(turns):
                # ★ 逐轮快照起点：本轮新增的批改条目 = grade_scores[gs_start:]
                gs_start = len(case.grade_scores)
                try:
                    reply, turn_tools = await _stream_turn(agent, text, config, case, si)
                except Exception as e:  # noqa: BLE001
                    case.hard_fails.append(f"invoke 抛错(session {si}): {type(e).__name__}: {e}")
                    return case
                case.turn_log.append(
                    {
                        "session": si,
                        "turn": ti,
                        "input": text,
                        "reply": reply,
                        "tools": turn_tools,
                        "grade_scores": [g.get("score") for g in case.grade_scores[gs_start:]],
                    }
                )
            case.session_replies.append(reply)
        await _read_written_episodes(eff_store, user_id, case)
        case.reply = case.session_replies[-1] if case.session_replies else ""
        if not case.reply:
            case.hard_fails.append("最终回复为空")
        return case
    finally:
        # 先恢复 OFF 臂摘掉的 store（须在清理前）；再清 Store 与 checkpointer 本次 thread。
        if prev_global_store is not _UNSET:
            _off_arm_restore(agent, store, prev_global_store)
        if eff_store is not None:
            removed = await _cleanup_user_store(eff_store, user_id)
            case.notes.append(f"跑后清理 Store user={user_id}：删除 {removed} 项")
        if checkpointer is not None:
            n = await _cleanup_threads(checkpointer, used_threads)
            case.notes.append(f"跑后清理 checkpointer：{len(used_threads)} 个 thread，删除 {n} 项")
        elif used_threads:
            case.notes.append("跑后清理 checkpointer 跳过：agent.checkpointer 未装配")
