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
    uv run python scripts/lib/agent_behavior_smoke.py
    uv run python scripts/lib/agent_behavior_smoke.py --strict

★ 本文件是**门面**：实现拆在 `_smoke_model`（模型 + 启发式正则）、
  `_smoke_session`（建身份 / 清理 / 跑轮次与会话）、`_smoke_checks`（软断言）。
  此处 re-export 供外部（三个 Gate / `task_eval._runner_agent`）import，并编排 `main`。
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
# ★ 本包拆出的 `_smoke_model/_smoke_checks/_smoke_session` 与本文件同目录 ⇒ 把该目录
#   放上路径，三个子模块才能以裸名 import（对外仍经本门面取用）。
sys.path.insert(0, str(ROOT / "scripts" / "lib"))

from _smoke_checks import (  # noqa: E402
    check_empty_not_taught,
    check_no_fabricated_sources,
    check_no_self_score,
    check_search_no_answer_leak,
    check_tool_errors_honestly_reported,
)
from _smoke_model import (  # noqa: E402
    _ANS_BODY_RE,
    _EMPTY_ACK_RE,
    _FAB_PAGE_RE,
    _QID_RE,
    CaseResult,
)
from _smoke_session import (  # noqa: E402
    _cleanup_threads,
    _cleanup_user_store,
    _off_arm_disable,
    _off_arm_restore,
    make_user_id,
    run_sessions,
    run_turns,
)

from agents.agents import DEFAULT_AGENT, get_agent  # noqa: E402
from agents.teaching_graph import MEMORY_CARD_MESSAGE_ID  # noqa: E402

# re-export 面（外部 import 的入口；拆分后仍须可从本模块取到）
__all__ = [
    "CaseResult",
    "MEMORY_CARD_MESSAGE_ID",
    "_ANS_BODY_RE",
    "_EMPTY_ACK_RE",
    "_FAB_PAGE_RE",
    "_QID_RE",
    "_cleanup_threads",
    "_cleanup_user_store",
    "_off_arm_disable",
    "_off_arm_restore",
    "check_empty_not_taught",
    "check_no_fabricated_sources",
    "check_no_self_score",
    "check_search_no_answer_leak",
    "check_tool_errors_honestly_reported",
    "make_user_id",
    "run_sessions",
    "run_turns",
]

_CASES = [
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


async def _run_one_case(agent, name, turns, checkers) -> CaseResult:
    """跑一条冒烟 case 并打印结果（回复长度 / notes / hard / soft 失败）。"""
    print(f"==== {name} ====")
    case = await run_turns(agent, turns)
    case.name = name
    checkers(case, turns)
    check_tool_errors_honestly_reported(case)
    print(f"  reply_len={len(case.reply)} tools={len(case.tool_payloads)}")
    print(f"  reply[:120]={case.reply[:120]!r}")
    for note in case.notes:
        print(f"  note: {note}")
    for hf in case.hard_fails:
        print(f"  HARD FAIL: {hf}")
    for sf in case.soft_fails:
        print(f"  soft-fail: {sf}")
    return case


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--strict", action="store_true", help="软失败升硬（调提示词用）")
    args = ap.parse_args()

    agent = get_agent(DEFAULT_AGENT)
    t0 = time.time()
    results = [
        await _run_one_case(agent, name, turns, checkers) for name, turns, checkers in _CASES
    ]

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
