"""case 执行的 agent harness（从 runner.py 拆出，行为等价）。"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any

from evaluation.task_eval import memory_scorer
from evaluation.task_eval._runner_record import CaseRecord
from evaluation.task_eval.cases import TaskCase

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[3]


def _assemble_agent(saver, store):
    """装配 agent：挂 checkpointer + store（与 `service.lifespan` 逐字对齐）。"""
    from agents.agents import DEFAULT_AGENT, get_agent
    from memory.runtime import set_store

    set_store(store)
    agent = get_agent(DEFAULT_AGENT)
    agent.checkpointer = saver
    agent.store = store
    return agent


async def _run_with_agent(
    agent,
    turns: list[str],
    *,
    task: str,
    case_id: str,
    sessions: list[list[str]] | None,
    store_enabled: bool,
):
    """按 task 分派：``memory`` 走跨会话的 `run_sessions`，其余走会话内的 `run_turns`。"""
    from agent_behavior_smoke import (  # type: ignore[import-not-found]
        make_user_id,
        run_sessions,
        run_turns,
    )

    if task == "memory":
        # ★ 跨会话：每段会话独立 thread、共享 user_id、跑前跑后自动清理。
        #   分组以传入的 sessions 为准；未标注时退化为「每轮一段」。
        eff_sessions = sessions if sessions else ([[t] for t in turns] if turns else [])
        return await run_sessions(
            agent,
            eff_sessions,
            user_id=make_user_id(case_id or "memory"),
            cleanup_first=True,
            store_enabled=store_enabled,
        )
    return await run_turns(agent, turns)


async def _run_agent(
    turns: list[str],
    *,
    task: str = "",
    case_id: str = "",
    sessions: list[list[str]] | None = None,
    store_enabled: bool = True,
):
    """跑真实 agent。惰性导入 `scripts/` 下的 smoke 封装（与 gate 同一套调用链）。

    ★★ **必须自行装配 checkpointer / store**（2026-10-05 实测教训）：
    服务端是在 FastAPI lifespan 里挂的（`service.py` 的 lifespan 里 `agent.checkpointer = saver`），
    而 `run_turns` 只调 `get_agent()`、**从不挂**。不挂的后果是**多轮之间没有历史** ——
    实测第 2 轮追问「我叫什么」，系统答「我这边暂时没有你的个人信息记录」。

    这会让 Memory 任务的测量**完全失真**（测的是「无 checkpointer 的 agent」，
    不是产品）。故此处逐字对齐 `service.lifespan` 的装配方式。

    ★ **memory 任务走 `run_sessions`**（2026-10-06 修，Step 4 接线）：
      Memory 要测的是**跨会话**长期记忆（Store），而不是**会话内**多轮（checkpointer）。
      二者的差别不是措辞 —— 若 memory 也走 `run_turns`（单 thread 跑完全部轮次），
      则「第 2 轮记得第 1 轮的话」完全可由 checkpointer 解释，**证明不了 Store 起了作用**。

      `run_sessions` 把每段会话拆成**独立 thread**（各自新会话）、共享同一 `user_id`，
      并在跑前跑后清理 Store / checkpointer ⇒ 唯一能连通两段的只有 Store，
      同时产出 `memory_cards`（机械判定 `recalled` 的证据）。

      ★ **会话分组由 `case.all_sessions` 决定**（2026-10-06 补）：
        - 有 `sessions` 字段 ⇒ 按标注的段数拆 thread（真跨会话）；
        - 无 `sessions` ⇒ 退化为「每轮一段」（`[[t] for t in turns]`）。
        这里的 `sessions` 由 `run_case` 从 `case.all_sessions` 传入，**不在本函数里重算** ——
        避免「解析处」与「执行处」两套分组逻辑漂移。

      `user_id` **每条 case 独立**（`make_user_id(case_id)`，带随机后缀）⇒
      case 之间与重跑之间都天然隔离，不会互相污染。
    """
    scripts_dir = ROOT / "scripts"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    if str(ROOT / "src") not in sys.path:
        sys.path.insert(0, str(ROOT / "src"))

    from memory import initialize_database, initialize_store

    async with initialize_database() as saver, initialize_store() as store:
        if hasattr(saver, "setup"):
            await saver.setup()
        agent = _assemble_agent(saver, store)
        return await _run_with_agent(
            agent,
            turns,
            task=task,
            case_id=case_id,
            sessions=sessions,
            store_enabled=store_enabled,
        )


def _tool_call_summaries(payloads: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for p in payloads:
        out.append(
            {
                "kind": "search" if p.get("query") is not None else "other",
                "status": p.get("status", ""),
                "query": str(p.get("query") or "")[:80],
                "docs": len(p.get("docs") or []),
            }
        )
    return out


def aggregate_memory_read_status(statuses: list[str], memory_cards: list[str]) -> str:
    """把本 case 各轮 `load_memory` 报上来的状态聚成**一个**四态值（B4，四态无损）。

    为什么要把聚合放在评测侧而不是让 `load_memory` 只报一次：一条 memory case 会跑
    **多轮/多段**，每轮都读一次 Store ⇒ 事实是「一串状态」，而 record 的字段是「一个」。
    聚合规则一旦写错就会**折叠**（用户点名的失效模式），故规则按「证据强度」排：

    1. **有卡**（`memory_cards` 非空）⇒ `success`。
       记忆卡是 harness 从 SystemMessage 机械捕获的**正面物证**：它出现了，
       读链就一定成功过 —— 即使别轮报 `failed`，也不能把已经拿到的物证降格成 `None`。
    2. 没卡 + 任一 `failed` ⇒ `failed`（★ 不折成 `empty`：「读挂了」与「确实没画像」
       是两件事，折起来会把基础设施故障记成产品召回失败）。
    3. 没卡 + 任一 `not_attempted` ⇒ `not_attempted`（没有 `user_id`，压根没读）。
    4. 没卡 + 全部 `empty` ⇒ `empty`（读到了、确实没卡 ⇒ 这是**真缺陷**，进分母记 fail）。
    5. **一条都没捕获**（`run_agent=False`、或 agent 在 `load_memory` 之前就抛错）⇒ `""`
       = 未测量。★ 刻意**不**映射成 `failed` —— 那会把「没有记录」说成「读链故障」；
       也刻意**不**让它走机械判定（`judge_memory_mechanically` 对 `""` 同样返回全 None）。

    `success` 只会从第 1 条来：`load_memory` 报的 `success` 就是「这轮有卡」，
    与 `memory_cards` 非空是同一件事的两个视图，不会互相打脸。
    """
    if memory_cards:
        return "success"
    seen = set(statuses)
    if "failed" in seen:
        return "failed"
    if "not_attempted" in seen:
        return "not_attempted"
    if seen & {"empty", "success"}:
        return "empty"
    return ""


def _apply_memory_judgement(
    record: CaseRecord,
    case: TaskCase,
    memory_cards: list[str],
    reply: str,
) -> list[str]:
    """**机械判定** Memory 三维并写入 record；返回需追加的 failure_reason。

    ★ 只在 case validity **通过**时调用（前置条件不成立时三项应保持 N/A）。
    ★ 必须在 judge 之前算：judge 的 `apply_judge` 已加护栏**不再写**这三项，
      若这里不算，record 的 memory_* 将恒为 None ⇒ 主指标全 N/A。
    """
    _m = memory_scorer.judge_memory_mechanically(
        memory_cards=memory_cards,
        reply=reply,
        gold=case.gold,
        # ★ B4：读链状态是**判定的前置事实**，不是事后诊断字段 ——
        #   `failed` / `not_attempted` / `""` 时三维一律 None（测不到不进分母）。
        read_status=record.memory_read_status,
    )
    record.memory_retrieved = _m.recalled_pass  # ★ 进主指标的是「与期望对齐」的结果
    record.memory_recalled_actual = _m.recalled_actual
    record.memory_used = _m.used
    record.memory_correct = _m.correct
    record.memory_hit_values = list(_m.hit_values)
    record.memory_forbidden_hits = list(_m.forbidden_hits)
    # ★ 主指标由 scorer 的**唯一公式**写入字段（旧实现在此另算一遍，见字段注释）
    record.memory_correct_use = _m.correct_use
    record.memory_cards = memory_cards
    # ★ gold 未标注/非法 ⇒ 三项记 None（N/A，不进分母），并标 `memory_miss`
    #   提示人工补齐。**绝不**回退 judge 猜测（那正是本轮要消除的问题）。
    extra: list[str] = []
    if not case.gold.memory_mechanizable() and "memory_miss" not in record.failure_reason:
        extra.append("memory_miss")
    return extra
