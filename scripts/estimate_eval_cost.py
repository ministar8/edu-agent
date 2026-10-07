"""EFFECT_PLAN 全方案 token 成本估算（**可复算**，不是一次性口头数字）。

为什么落成脚本
--------------
「跑完这个方案要多少 token」会被反复问（改 case 数、换 judge、加迭代轮次都会变）。
口头估算无法复算、也无法随参数更新，故把成本模型固化在这里。

模型由三部分组成，**全部有出处**：
1. **单 case 调用构成**：实测 `0A smoke` 日志 —— 75 次 LLM 调用 / 15 条 case ≈ **5 次/case**。
2. **每次调用的字符量**：实测组件（agent system prompt 870 字符、证据包 867 字符、
   最终回复 576 字符、judge 输入约 1,126 字符），见 `_calls_for_case`。
3. **字符→token 换算**：中文混合文本 **1.4–1.7 字符/token**（区间，非点估计）。

★ RAGAS 单列：它的成本结构与任务评测**完全不同**（faithfulness 逐断言核验、
context_precision 逐上下文判定），且历史产物**不含 usage 字段**，只能建模。

用法::

    PYTHONPATH=src uv run python scripts/estimate_eval_cost.py
    PYTHONPATH=src uv run python scripts/estimate_eval_cost.py --iterations 3
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field

# ── 实测组件（字符）────────────────────────────────────────
SYS_SUP = 1200  # supervisor 分派 prompt
SYS_AGENT = 870  # 专业 agent system prompt（实测 576–906）
TOOLDOC = 600  # 4 个检索工具 docstring 合计
USER = 30  # 用户提问
PACK = 867  # 工具回填的证据包（0A 实测均值）
REPLY = 576  # 最终回复（0A 实测均值；generate 可达 1,150）
GOLD = 270  # judge 看到的 gold（实测）
JUDGE_OUT = 150  # judge 的 JSON 输出

# 字符 → token 换算区间（中文混合文本）
CHARS_PER_TOKEN = (1.4, 1.7)  # (高估token数, 低估token数)
MULTI_TURN_FACTOR = 1.8  # 两轮（memory）：历史进上下文，调用数与输入量同时放大

# ★ 实测校正（2026-10-05）：`phase0_full` 全量 66 条实际发出 **496 次** LLM 调用
#   （见 `evals/results/task_eval/phase0_full.log` 的 dashscope 计数）
#   = **7.5 次/case**，而非最初假设的 5 次。
#   初版 `_calls_for_case` 只建模了 5 次，导致总成本**低估约 40%**。
#   差异来源：grade / verify 的工具回环更多、memory 为多轮。
#   ⇒ 这里用实测值放大；改评测规模时**先按实测调用数校正**，不要沿用假设。
CALLS_PER_CASE_MEASURED = 7.5
_CALLS_MODELED = 5.0
_SCALE = CALLS_PER_CASE_MEASURED / _CALLS_MODELED


def _calls_for_case(single_turn: bool = True) -> tuple[int, int]:
    """返回 (输入字符, 输出字符) 合计。"""
    sys_judge = 250  # judge 的 rubric 指令
    calls = [
        (SYS_SUP + USER, 50),  # ① supervisor 路由
        (SYS_AGENT + TOOLDOC + USER, 60),  # ② agent 首轮（带工具）
        (SYS_AGENT + TOOLDOC + PACK + REPLY // 2, REPLY),  # ③ agent 次轮（含证据包）
        (SYS_AGENT + PACK // 2 + USER, 200),  # ④ agent 补轮 / 工具回环
        (sys_judge + GOLD + USER + REPLY, JUDGE_OUT),  # ⑤ judge 评分
    ]
    chars_in = sum(c[0] for c in calls)
    chars_out = sum(c[1] for c in calls)
    # 按实测调用密度放大（见 CALLS_PER_CASE_MEASURED 的说明）
    chars_in = int(chars_in * _SCALE)
    chars_out = int(chars_out * _SCALE)
    if not single_turn:
        chars_in = int(chars_in * MULTI_TURN_FACTOR)
        chars_out = int(chars_out * MULTI_TURN_FACTOR)
    return chars_in, chars_out


def tokens_for_cases(n_single: int, n_multi: int = 0) -> tuple[float, float]:
    """返回 (低估值, 高估值) tokens —— 输入+输出合计。"""
    si, so = _calls_for_case(True)
    mi, mo = _calls_for_case(False)
    total_chars = n_single * (si + so) + n_multi * (mi + mo)
    return total_chars / CHARS_PER_TOKEN[1], total_chars / CHARS_PER_TOKEN[0]


@dataclass
class Item:
    """一个 LLM 消耗项。"""

    name: str
    n_single: int
    n_multi: int = 0
    note: str = ""
    tokens: tuple[float, float] = field(init=False)

    def __post_init__(self) -> None:
        self.tokens = tokens_for_cases(self.n_single, self.n_multi)


@dataclass
class RagasItem:
    """RAGAS 项：按「每样本调用数 × 每次 token」建模。"""

    name: str
    n_samples: int
    calls_per_sample: int = 22  # faithfulness 逐断言 + context_precision 逐上下文 + …
    tokens_per_call: tuple[float, float] = (1200.0, 2000.0)

    @property
    def tokens(self) -> tuple[float, float]:
        lo = self.n_samples * self.calls_per_sample * self.tokens_per_call[0]
        hi = self.n_samples * self.calls_per_sample * self.tokens_per_call[1]
        return lo, hi


def build_plan(iterations: int, grade_n: int, memory_final: int) -> tuple[list, list]:
    """按 EFFECT_PLAN 的任务清单建表。"""
    items = [
        Item(
            "Phase 0A Smoke（12 单轮 + 3 两轮）",
            12,
            3,
            "每类 3 条 + memory；可加 --no-judge 省 15 次",
        ),
        Item(
            "Phase 0B 诊断基线（QA/Gen/Grd/Ver 各 15 + Mem 6）",
            60,
            6,
            "含 calibration 的 30 条（同批跑不额外计）",
        ),
        Item("Phase 1.5 L3 闸门（Verify 扩到 30）", 15, 0, "仅新增的 15 条"),
        Item(
            f"Final Gate 终评集（QA30 Gen30 Grd{grade_n} Ver30 Mem{memory_final}）",
            30 + 30 + grade_n + 30,
            memory_final,
            "论文数字来源",
        ),
    ]
    if iterations > 0:
        items.insert(
            2,
            Item(
                f"Phase 1 迭代 × {iterations} 轮（每轮全量 66 条）",
                (60 + 6) * iterations,
                0,
                "每轮改检索/生成后重跑；轮数不可预知，按需调整 --iterations",
            ),
        )
    ragas = [
        RagasItem("RAGAS 扩样（20 → 60，冻结集）", 60),
    ]
    return items, ragas


def _fmt(v: float) -> str:
    return f"{v / 10_000:.1f}万" if v < 1e8 else f"{v / 1e8:.2f}亿"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="EFFECT_PLAN 全方案 token 估算")
    p.add_argument(
        "--iterations", type=int, default=0, help="Phase 1 迭代轮数（默认 0 = 只算测量）"
    )
    p.add_argument("--grade-n", type=int, default=40, help="Final Gate 的 Grade 条数（30–50）")
    p.add_argument(
        "--memory-final", type=int, default=15, help="Final Gate 的 Memory 条数（10–20）"
    )
    args = p.parse_args(argv)

    items, ragas = build_plan(args.iterations, args.grade_n, args.memory_final)

    print("=" * 78)
    print("  EFFECT_PLAN 全方案 token 估算（输入+输出）")
    print("=" * 78)
    print(
        f"  单 case 实测：{CALLS_PER_CASE_MEASURED} 次调用"
        f"（建模 {_CALLS_MODELED:.0f} 次 × {_SCALE:.1f} 校正）· 输入 7,814 + 输出 1,036 字符"
    )
    print(f"  换算口径：{CHARS_PER_TOKEN[0]}–{CHARS_PER_TOKEN[1]} 字符/token（低估值 ~ 高估值）")
    print(f"  多轮(memory) 放大系数：{MULTI_TURN_FACTOR}×")
    print()

    print(f"{'项':52s} {'case':>6s} {'低估值':>9s} {'高估值':>9s}")
    print("-" * 78)
    sub_lo = sub_hi = 0.0
    for it in items:
        lo, hi = it.tokens
        sub_lo += lo
        sub_hi += hi
        print(f"{it.name:52s} {it.n_single + it.n_multi:>6d} {_fmt(lo):>9s} {_fmt(hi):>9s}")
    print("-" * 78)
    print(f"{'小计（任务评测，不含 RAGAS）':52s} {'':>6s} {_fmt(sub_lo):>9s} {_fmt(sub_hi):>9s}")
    print()

    rag_lo = rag_hi = 0.0
    for r in ragas:
        lo, hi = r.tokens
        rag_lo += lo
        rag_hi += hi
        print(
            f"{r.name:52s} {r.n_samples:>6d} {_fmt(lo):>9s} {_fmt(hi):>9s}"
            f"   ({r.calls_per_sample} 次调用/样本 × {r.tokens_per_call[0]:.0f}–{r.tokens_per_call[1]:.0f} tok)"
        )
    print("-" * 78)
    print(
        f"{'合计（任务评测 + RAGAS）':52s} {'':>6s} {_fmt(sub_lo + rag_lo):>9s} {_fmt(sub_hi + rag_hi):>9s}"
    )
    print()
    print("★ 已知额度事实：qwen3.8-max-0902 在第 10 条 case（≈6 万 token）就 403")
    print("  ⇒ 单模型免费额度约 6 万 token 量级，**远小于本方案需求**。")
    print()
    for it in items:
        if it.note:
            print(f"  · {it.name[:40]:42s} {it.note}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
