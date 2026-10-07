"""Agent 输出行为冒烟（真 LLM，软断言）。

第 1 层 `agent_input_contract_gate` 验的是**进 Agent 的输入**；
本脚本验 **Agent 拿到 Evidence Pack 之后怎么说话**：

- empty 不硬答：检索为空时如实说「未检索到」，不开始硬教
- 不编造来源：`来源: X` 的 X 必须出现在 ToolMessage docs 里，且不得编造页码
- search 路径不泄答案：knowledge_search 的 ToolMessage / 回复不得含答案字段
- 多轮约束：practice → 提交作答 → 不崩、不自行给分

★ 这是**软断言冒烟**，不是硬门禁：LLM 有随机性（生产温度 0.3），
  默认宽松匹配以压低误报；`--strict` 把软失败升硬，供本地调提示词用。

用法：
    uv run python scripts/agent_behavior_smoke.py
    uv run python scripts/agent_behavior_smoke.py --strict
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from langchain_core.messages import (  # noqa: E402
    AIMessageChunk,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.runnables import RunnableConfig  # noqa: E402

from agents.agents import DEFAULT_AGENT, get_agent  # noqa: E402

# ★ 记忆卡消息 ID **必须从产品侧导入**，不得在此硬编码副本（2026-10-06 修）。
#   硬编码的失效模式是**静默**的：产品改 ID ⇒ 本脚本按旧 ID 匹配 ⇒ `memory_cards`
#   恒为空列表 ⇒ `recalled` 恒 False ⇒ 整条 Memory 指标凭空下降，
#   而现象与「产品记忆功能退化」完全一致，排查成本极高。导入则改名即报错。
from agents.teaching_graph import MEMORY_CARD_MESSAGE_ID  # noqa: E402
from memory.namespaces import student_episodes_ns, student_profile_ns  # noqa: E402

# —— 启发式模式（故意宽松，压低误报）——
_EMPTY_ACK_RE = re.compile(r"未检索到|未找到|没有找到|知识库.{0,6}(未|没有|无)|未覆盖|检索不到")
# 编造页码/教材章节（prompt 明令禁止）
_FAB_PAGE_RE = re.compile(r"第\s*\d+\s*页|P\s*\d{1,4}|《[^》]{1,20}》\s*第\s*\d+\s*章")
# 答案泄漏面（search 路径）
_ANS_FIELD_RE = re.compile(r"answer_key|reference_answer|correct_answer", re.I)
_ANS_BODY_RE = re.compile(r"答案[:：]|【答案】|正确答案|标准答案")
_QID_RE = re.compile(r"(?:19|20)\d{2}-Q\d+")
# 来源标注（prompt 要求末尾纯文本一次）
_SOURCE_RE = re.compile(r"来源[:：]\s*([^\n]+)")
# 自行给分（grading 应走工具，不许自由发挥分数）
_SELF_SCORE_RE = re.compile(r"(?:得分|评分|得分是|我给)\s*[:：]?\s*\d+\s*(?:/\s*\d+)?\s*分?")


@dataclass
class CaseResult:
    name: str
    reply: str = ""
    tool_payloads: list[dict[str, Any]] = field(default_factory=list)
    hard_fails: list[str] = field(default_factory=list)
    soft_fails: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    # ── 多段会话（Memory 评测用）──────────────────────────
    # 每段会话的最终回复（`reply` 仍 = 最后一段的回复，保持向后兼容）
    session_replies: list[str] = field(default_factory=list)
    # 每轮注入的**记忆卡**内容（`load_memory` 的 SystemMessage）。
    # 这是 `recalled` 的**客观证据**：不依赖 judge 猜测。
    memory_cards: list[str] = field(default_factory=list)
    # ── Memory 评测：本次 case 使用的隔离身份（Step 4 硬要求）────
    # ★ 每 case 独立 `user_id` ⇒ 不同 case 的 Store 数据互不污染；
    #   跨会话召回**只能**在同一 case 内发生（Session A 写 → Session B 读）。
    user_id: str = ""
    # ── ★ 批改得分（2026-10-06 补，Step 5 case-validity 用）────────
    # 每次 `grade_student_answer` 调用的得分与所在会话下标：
    #   `[{"session": 0, "score": 52.0}, {"session": 0, "score": 48.0}]`
    # 用途：case 的**前置条件**（如 mem-006「两次高分」、mem-004「低分」）
    #   必须由**实际运行结果**验收，而不是假定模型一定给出预期分数 ——
    #   否则 grading LLM 的随机性会污染 Memory 指标（用户 2026-10-06 裁决）。
    grade_scores: list[dict[str, Any]] = field(default_factory=list)
    # ── ★ Store 开关状态（2026-10-06 补，paired control 用）────────
    # `False` ⇒ 本 case 是 **Store OFF** 对照组（不装 store，B 段不应召回）。
    store_enabled: bool = True


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


# 批改工具的输出是**对话体文本**（见 `grading_core.format_grading_for_chat`）：
#   "评分：52/100\n结论：..."
# 故不能用 JSON 解析，必须正则提分。
_GRADE_SCORE_RE = re.compile(r"评分\s*[:：]\s*(\d+(?:\.\d+)?)\s*(?:/\s*(\d+))?")
_GRADE_FULL_SCORE = 100.0


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


# 批改工具名（与 `agents/tools.py` 的 `@tool("grade_student_answer")` 同源；
# 硬编码会随产品改名而**静默失效** —— 这里用常量集中一处，改名时只需改这里）。
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


async def run_sessions(
    agent,
    sessions: list[list[str]],
    *,
    user_id: str,
    cleanup_first: bool = True,
    store_enabled: bool = True,
) -> CaseResult:
    """跑**多段会话**（Memory 评测专用）：每段新 ``thread_id``、**同一** ``user_id``。

    为什么必须这样
    --------------
    要证明「用的是 **Store 长期记忆**」而不是「**checkpointer 会话内历史**」，必须让
    写入段与读取段**互不共享会话**，只经 Store 相连：

        Session A（thread-A）──写──► Store ──读──► Session B（thread-B）
                                      ▲
                          user_id 相同才连得上；thread 不同才隔离

    同时**捕获记忆卡**：``load_memory`` 每轮把 Store 读出的记忆以固定 ID
    （``MEMORY_CARD_MESSAGE_ID``）的 SystemMessage 注入 state。把它收下来，
    ``recalled`` 就能**从证据判定**，不必让 judge 猜。

    ★ 与 ``run_turns`` 的区别：``run_turns`` 是单 thread 跑完全部轮次（既有行为，
      未改动）；本函数**每段会话换 thread**，这是 Memory 跨会话验证的前提。

    ``cleanup_first``：跑前清理该 ``user_id`` 的 Store 数据（Step 4 硬要求）。
    依赖 ``agent.store`` 已装配（与 ``service.lifespan`` / ``task_eval.runner`` 一致）；
    store 不可用时跳过并记 note，不抛。

    ★ **跑后清理**（2026-10-06 补）：无论成功、失败还是中途抛错，都在 ``finally`` 里
      同时清掉 Store 与 **checkpointer** 的本次 thread。理由见 ``_cleanup_threads``。

    ★★ **paired control：``store_enabled=False``**（2026-10-06 Step 5 补）：
      这是证明「B 段的记忆**确实来自 Store**」的关键对照。仅靠「Store ON 时 B 召回」
      只能说明「召回了」，不能排除「B 段碰巧提到该 KP」或「checkpointer 泄漏」。
      加 Store OFF 组后，证据链变成：

          Store ON  → B 段有 memory card → recalled_actual = True
          Store OFF → B 段无 memory card → recalled_actual = False

      两组**只差 Store 开关**这一个变量 ⇒ 差异只能归因于 Store。

      实现方式：把 ``agent.store`` 临时置 `None`（不改产品代码、不动全局单例的其它字段），
      跑完在 ``finally`` 恢复。`load_memory` 读到 `store=None` 时不注入记忆卡
      ⇒ `memory_cards` 为空 ⇒ 机械判定自然给出 `recalled_actual=False`。
      **注意**：本组**不做** Store 清理（无 store 可清），避免 note 噪声。
    """
    case = CaseResult(name=" | ".join(t[:14] for t in (sessions[0] if sessions else [])))
    case.user_id = user_id
    case.store_enabled = store_enabled
    reply_parts: list[str] = []

    store = getattr(agent, "store", None)
    checkpointer = getattr(agent, "checkpointer", None)
    # 本次真实用到的 thread（跑后清理对象）；无论成败都要清
    used_threads: list[str] = []

    # ── paired control：Store OFF 组——临时摘掉 store ──────────────────
    #   ★ 只摘本函数作用域内的引用，跑完在 finally 恢复，不影响其它 case。
    if not store_enabled and store is not None:
        agent.store = None
        case.notes.append("paired control：Store OFF（临时摘除 agent.store，B 段不应召回）")
    eff_store = store if store_enabled else None

    # ── 跑前清理（Step 4 硬要求：起点必须干净）─────────────────────────
    if cleanup_first and store_enabled:
        if store is None:
            case.notes.append("cleanup 跳过：agent.store 未装配（基线可能不干净，需检查装配方式）")
        else:
            removed = await _cleanup_user_store(store, user_id)
            case.notes.append(f"跑前清理 user={user_id}：删除 {removed} 项 Store 数据")

    try:
        for si, turns in enumerate(sessions):
            # ★ 每段会话新 thread ⇒ checkpointer 里没有上一段的历史
            thread = f"eval-{user_id}-s{si}"
            used_threads.append(thread)
            config = RunnableConfig(configurable={"thread_id": thread, "user_id": user_id})
            for text in turns:
                reply_parts.clear()
                try:
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
                except Exception as e:  # noqa: BLE001
                    case.hard_fails.append(f"invoke 抛错(session {si}): {type(e).__name__}: {e}")
                    return case
            case.session_replies.append("".join(reply_parts).strip())

        case.reply = case.session_replies[-1] if case.session_replies else ""
        if not case.reply:
            case.hard_fails.append("最终回复为空")
        return case
    finally:
        # ── paired control：先恢复被临时摘掉的 store ──────────────────
        #   ★ 必须在清理**之前**恢复，且放在 finally 最前 —— 否则中途抛错会让
        #     后续 case 的 agent.store 一直是 None（静默污染整轮后续样本）。
        if not store_enabled and store is not None:
            agent.store = store
        # ── 跑后清理（Step 4 硬要求：跑完必须干净）──────────────────────
        # ★ 放 finally：中途抛错/提前 return 也要清 —— 失败重跑最需要干净起点。
        if eff_store is not None:
            removed = await _cleanup_user_store(eff_store, user_id)
            case.notes.append(f"跑后清理 Store user={user_id}：删除 {removed} 项")
        if checkpointer is not None:
            n = await _cleanup_threads(checkpointer, used_threads)
            case.notes.append(f"跑后清理 checkpointer：{len(used_threads)} 个 thread，删除 {n} 项")
        elif used_threads:
            case.notes.append("跑后清理 checkpointer 跳过：agent.checkpointer 未装配")


def _record_card(case: CaseResult, content: str) -> None:
    """记录记忆卡（去重：同 ID 消息每轮被替换而非追加，可能重复触发）。"""
    text = content.strip()
    if text and text not in case.memory_cards:
        case.memory_cards.append(text)


def _all_tool_sources(payloads: list[dict[str, Any]]) -> set[str]:
    names: set[str] = set()
    for p in payloads:
        for d in p.get("docs") or []:
            src = str(d.get("source") or "")
            if src:
                names.add(src)
                names.add(Path(src).name)
    return names


def check_empty_not_taught(case: CaseResult, query: str) -> None:
    """检索为空时必须如实说未检索到，不得硬着头皮开讲。

    两种诚实形态都算过：
    - 工具返回 empty 且回复转述「未检索到」
    - 专家直接判定超出知识库 / 不在 408 范围（可不调工具）
    """
    payloads = case.tool_payloads
    empties = [p for p in payloads if p.get("status") == "empty"]
    reply = case.reply
    acked = bool(_EMPTY_ACK_RE.search(reply)) or bool(
        re.search(r"无关|不在.{0,6}范围|无法回答|不确定|不展开|没有实际含义", reply)
    )
    if empties:
        if not acked:
            case.soft_fails.append("empty 未被回复如实转述（缺「未检索到」类措辞）")
        if len(reply) > 500 and re.search(r"\*\*核心要点\*\*|## ", reply):
            case.soft_fails.append("empty 却输出讲义式长文（疑似硬答）")
        return
    if not payloads and not acked:
        case.soft_fails.append("既未检索也未拒答（疑似幻觉作答）")
    else:
        case.notes.append("无 empty 载荷（已诚实拒答或检索有命中）")


def check_no_fabricated_sources(case: CaseResult) -> None:
    """来源标注必须对得上 ToolMessage docs；不得编造页码。"""
    reply = case.reply
    if _FAB_PAGE_RE.search(reply):
        case.soft_fails.append(f"回复含编造页码/教材章节: {_FAB_PAGE_RE.search(reply).group(0)!r}")

    sources = _all_tool_sources(case.tool_payloads)
    if not sources:
        return
    for m in _SOURCE_RE.finditer(reply):
        blob = m.group(1)
        # 来源行可能写「06_tree.md（[二叉排序树]）」——取文件名片段核对
        tokens = re.findall(r"[\w一-鿿]+\.md", blob)
        if not tokens:
            continue
        for tok in tokens:
            if not any(tok in s or s.endswith(tok) for s in sources):
                case.soft_fails.append(f"来源标注 {tok!r} 不在 docs 中（疑似编造）")


def check_search_no_answer_leak(case: CaseResult, mode_hint: str) -> None:
    """search 路径（knowledge/text_search）不得泄答案；generate_practice_questions 例外。"""
    has_search_tool = any(p.get("query") is not None for p in case.tool_payloads)
    has_gen = any(
        str(p.get("status")) in ("raw",) or "practice" in str(p)[:200].lower() and "query" not in p
        for p in case.tool_payloads
    )
    # 仅当本轮走的是检索类载荷（有 query 字段）才做泄漏断言
    search_payloads = [p for p in case.tool_payloads if "query" in p]
    if not search_payloads:
        return
    for p in search_payloads:
        msg = json.dumps(p, ensure_ascii=False)
        if _ANS_FIELD_RE.search(msg):
            case.soft_fails.append("search 载荷含答案字段")
        # practice/learn/search 的 context 不得有答案正文
        if mode_hint in ("practice", "learn", "method") and _ANS_BODY_RE.search(
            str(p.get("context") or "")
        ):
            case.soft_fails.append("search context 含答案正文")
    if has_gen:
        case.notes.append("含 generate_practice_questions（题目带标准答案属预期，跳过泄漏断言）")
    if not has_search_tool and not search_payloads:
        case.notes.append("本轮未见 search 载荷")


def check_no_self_score(case: CaseResult) -> None:
    """批改不得自行给分（应走 grade_student_answer 工具）。"""
    m = _SELF_SCORE_RE.search(case.reply)
    if m and case.tool_payloads:
        # 有工具分时，回复里再写一个不同的自由分数要警惕；只做软提示
        case.notes.append(f"回复含分数字样: {m.group(0)!r}（请人工确认是否工具返回）")


def check_tool_errors_honestly_reported(case: CaseResult) -> None:
    """工具失败必须如实转述（prompt 约定）。

    口径收紧：仅当**没有可用证据**（全错 / 空 context）时才要求回复说明失败；
    有成功载荷时，不必叙述每一个工具抖动。
    """
    if not case.tool_payloads:
        return
    ok_payloads = [
        p
        for p in case.tool_payloads
        if p.get("status") in ("ok", "raw") and str(p.get("context") or "").strip()
    ]
    err_payloads = [
        p
        for p in case.tool_payloads
        if p.get("status") == "error" or "失败" in str(p.get("context") or "")
    ]
    if not err_payloads or ok_payloads:
        return
    if not re.search(r"失败|不可用|未能|无法|错误", case.reply):
        case.soft_fails.append("工具全错但回复未如实转述")
    else:
        case.notes.append("工具全错且回复已如实转述（行为符合预期）")


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--strict", action="store_true", help="软失败升硬（调提示词用）")
    args = ap.parse_args()

    agent = get_agent(DEFAULT_AGENT)
    t0 = time.time()
    results: list[CaseResult] = []

    cases = [
        (
            "empty 不硬答",
            ["2026 年 408 真题第 1 题的官方答案是什么？"],
            lambda c, qs: (check_empty_not_taught(c, qs[0]), check_no_fabricated_sources(c)),
        ),
        (
            "概念题·来源对账",
            ["什么是二叉排序树？"],
            lambda c, qs: (check_no_fabricated_sources(c), check_search_no_answer_leak(c, "learn")),
        ),
        (
            "method·不编造页码",
            ["BST 删除时双支结点怎么处理？"],
            lambda c, qs: (
                check_no_fabricated_sources(c),
                check_search_no_answer_leak(c, "method"),
            ),
        ),
        (
            "多轮 practice→作答",
            ["给我一道 BST 删除的练习题", "我的答案是 C"],
            lambda c, qs: (check_no_self_score(c), check_no_fabricated_sources(c)),
        ),
        (
            "verify·真题列表",
            ["BST 删除考过哪些真题？"],
            lambda c, qs: (
                check_no_fabricated_sources(c),
                check_tool_errors_honestly_reported(c),
            ),
        ),
    ]

    for name, turns, checkers in cases:
        print(f"==== {name} ====")
        case = await run_turns(agent, turns)
        case.name = name
        checkers(case, turns)
        check_tool_errors_honestly_reported(case)
        results.append(case)
        print(f"  reply_len={len(case.reply)} tools={len(case.tool_payloads)}")
        print(f"  reply[:120]={case.reply[:120]!r}")
        for n in case.notes:
            print(f"  note: {n}")
        for f in case.hard_fails:
            print(f"  HARD FAIL: {f}")
        for f in case.soft_fails:
            print(f"  soft-fail: {f}")

    hard = [f"{r.name}: {x}" for r in results for x in r.hard_fails]
    soft = [f"{r.name}: {x}" for r in results for x in r.soft_fails]

    print(f"\n==== 汇总（{time.time() - t0:.0f}s）====")
    print(f"  hard_fail={len(hard)} soft_fail={len(soft)}")
    if hard:
        print("\nAGENT BEHAVIOR HARD FAIL")
        for x in hard:
            print(" -", x)
        return 1
    if soft:
        print("\nsoft failures:")
        for x in soft:
            print(" -", x)
        if args.strict:
            print("AGENT BEHAVIOR FAIL (--strict)")
            return 1
        print("\nAGENT BEHAVIOR PASS（含软失败，未 --strict）")
        return 0
    print("\nAGENT BEHAVIOR PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
