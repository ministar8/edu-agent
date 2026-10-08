"""Step 5 · Memory 跨会话召回验证 + **paired control**（Store ON vs OFF）。

目的（用户 2026-10-06 裁决）
----------------------------
核心问题**不是**「B 段回复看起来像用了记忆吗」，而是：

    B 段的记忆到底**是不是来自 Store**？

故对**同一批 6 条 case**跑两组，只差一个变量（Store 开关）：

    Store ON  → B 段应有 memory card → recalled_actual = True
    Store OFF → B 段不应有 memory card → recalled_actual = False

`recalled` 已由 harness **直接读 memory card** 机械判定（不问 judge）
⇒ ON/OFF 的差异可机械观察，证据链干净。

★ 与 case-validity 的配合
  A 段前置条件（低分/高分次数）由**实际批改得分**验收：
    - 前置条件不成立 ⇒ `case_invalid`，该 case 的 Memory 三项记 N/A（**不进分母**）；
    - 前置条件成立 ⇒ Memory 三项才进分母。
  这保证「grading LLM 的随机性」不会污染 Memory 指标。

用法::

    PYTHONPATH=src uv run python scripts/memory_step5_paired.py            # 真跑（消耗 token）
    PYTHONPATH=src uv run python scripts/memory_step5_paired.py --dry-run  # 只打印计划，不调用 LLM
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
for _p in (ROOT / "src", ROOT / "scripts"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from evaluation.task_eval.cases import load_demo  # noqa: E402
from evaluation.task_eval.runner import preflight_check, run_case  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("memory_step5")

OUT_DIR = ROOT / "evals" / "results" / "task_eval"


@dataclass
class ArmSummary:
    """一组（Store ON 或 OFF）的汇总。"""

    store_enabled: bool
    records: list[dict[str, Any]]

    @property
    def n(self) -> int:
        return len(self.records)

    @property
    def n_valid(self) -> int:
        """前置条件成立（valid != False）的条数 —— 只有这些进 Memory 分母。"""
        return sum(1 for x in self.records if x.get("validity_valid") is not False)

    @property
    def n_case_invalid(self) -> int:
        return sum(1 for x in self.records if x.get("validity_valid") is False)

    @property
    def n_recalled_actual(self) -> int:
        """实际召回（卡里有期望值）的条数 —— 机械事实。"""
        return sum(1 for x in self.records if x.get("memory_recalled_actual") is True)

    @property
    def n_memory_cards(self) -> int:
        return sum(1 for x in self.records if x.get("memory_cards"))

    @property
    def n_retrieved_pass(self) -> int:
        return sum(1 for x in self.records if x.get("memory_retrieved") is True)

    @property
    def n_used(self) -> int:
        return sum(1 for x in self.records if x.get("memory_used") is True)

    @property
    def n_correct_use(self) -> int:
        return sum(1 for x in self.records if x.get("memory_correct_use") is True)


async def _run_arm(store_enabled: bool, limit: int | None) -> ArmSummary:
    """跑一组（ON 或 OFF）。返回原始 record dict 列表。"""
    cases = load_demo("memory", limit=limit)
    label = "Store ON" if store_enabled else "Store OFF"
    logger.info("=== %s：%d 条 case ===", label, len(cases))
    records: list[dict[str, Any]] = []
    for i, case in enumerate(cases, 1):
        logger.info("[%s %d/%d] %s", label, i, len(cases), case.case_id)
        rec = await run_case(case, store_enabled=store_enabled)
        d = rec.to_dict()
        records.append(d)
        logger.info(
            "    validity=%s cards=%d recalled_actual=%s pass=%s scores=%s",
            d.get("validity_valid"),
            len(d.get("memory_cards") or []),
            d.get("memory_recalled_actual"),
            d.get("memory_retrieved"),
            [g.get("score") for g in (d.get("grade_scores") or [])],
        )
    return ArmSummary(store_enabled=store_enabled, records=records)


def _render(store_on: ArmSummary, store_off: ArmSummary) -> str:
    """生成 paired-control 对照报告（markdown）。"""
    lines: list[str] = []
    lines.append("# Step 5 · Memory 跨会话召回 + paired control（Store ON/OFF）")
    lines.append("")
    lines.append(f"**日期**：{datetime.now(UTC).astimezone().isoformat(timespec='seconds')}")
    lines.append("")

    lines.append("## 一、配对总览（同一批 case，只差 Store 开关）")
    lines.append("")
    lines.append("| 指标 | Store ON | Store OFF | 差值 | 期望 |")
    lines.append("|---|---|---|---|---|")
    lines.append(f"| case 数 | {store_on.n} | {store_off.n} | — | 相同 |")
    lines.append(
        f"| 有效 case（valid≠False） | {store_on.n_valid} | {store_off.n_valid} | "
        f"{store_on.n_valid - store_off.n_valid:+d} | — |"
    )
    lines.append(
        f"| **有 memory card 的 case** | **{store_on.n_memory_cards}** | "
        f"**{store_off.n_memory_cards}** | {store_on.n_memory_cards - store_off.n_memory_cards:+d} | "
        f"ON>OFF |"
    )
    lines.append(
        f"| **recalled_actual=True** | **{store_on.n_recalled_actual}** | "
        f"**{store_off.n_recalled_actual}** | "
        f"{store_on.n_recalled_actual - store_off.n_recalled_actual:+d} | ON≥OFF（正样本 ON 应 True）|"
    )
    lines.append(
        f"| recalled_pass=True | {store_on.n_retrieved_pass} | {store_off.n_retrieved_pass} | "
        f"{store_on.n_retrieved_pass - store_off.n_retrieved_pass:+d} | — |"
    )
    lines.append(
        f"| used=True | {store_on.n_used} | {store_off.n_used} | {store_on.n_used - store_off.n_used:+d} | — |"
    )
    lines.append(
        f"| correct_use=True | {store_on.n_correct_use} | {store_off.n_correct_use} | "
        f"{store_on.n_correct_use - store_off.n_correct_use:+d} | — |"
    )
    lines.append("")

    lines.append("## 二、逐条对照（Store ON）")
    lines.append("")
    lines.append(
        "| case | validity | A段得分 | 批改次数 | card数 | recalled_actual | pass | used | correct | failure |"
    )
    lines.append("|---|---|---|---|---|---|---|---|---|---|")
    for x in store_on.records:
        sc = [g.get("score") for g in (x.get("grade_scores") or [])]
        lines.append(
            f"| {x.get('case_id')} | {x.get('validity_valid')} | {sc} | "
            f"{len(x.get('grade_scores') or [])} | {len(x.get('memory_cards') or [])} | "
            f"{x.get('memory_recalled_actual')} | {x.get('memory_retrieved')} | "
            f"{x.get('memory_used')} | {x.get('memory_correct')} | "
            f"{','.join(x.get('failure_reason') or []) or '-'} |"
        )
    lines.append("")

    lines.append("## 三、逐条对照（Store OFF）")
    lines.append("")
    lines.append(
        "| case | validity | card数 | recalled_actual | pass | failure | validity_reason |"
    )
    lines.append("|---|---|---|---|---|---|---|")
    for x in store_off.records:
        lines.append(
            f"| {x.get('case_id')} | {x.get('validity_valid')} | "
            f"{len(x.get('memory_cards') or [])} | {x.get('memory_recalled_actual')} | "
            f"{x.get('memory_retrieved')} | {','.join(x.get('failure_reason') or []) or '-'} | "
            f"{x.get('validity_reason') or '-'} |"
        )
    lines.append("")

    # —— 结论判定 ——
    lines.append("## 四、判定")
    lines.append("")
    clean = store_off.n_memory_cards == 0 and store_off.n_recalled_actual == 0
    lines.append(
        f"- Store OFF 组「有卡的 case」= {store_off.n_memory_cards}、"
        f"「recalled_actual=True」= {store_off.n_recalled_actual} "
        f"⇒ {'✅ 干净（无卡、无召回 —— 证明 ON 组的召回确实来自 Store）' if clean else '❌ 不干净（OFF 组仍有卡/召回 ⇒ 存在旁路，需排查）'}"
    )
    # ★ D15 断言 ①（§6 的 Memory 行就看这一条）：**两臂都满足前置条件的正样本交集**上，
    #   ON 侧必须召回、OFF 侧必须不召回，且 OFF 侧出现任何记忆卡一律判失败 ——
    #   后者就是 #24 的探测器（旧 OFF 臂没空白进程级 store，照样有卡）。
    from evaluation.task_eval import metrics as _mt

    pv = _mt.paired_control_verdict(store_on.records, store_off.records)
    lines.append(
        f"- **配对断言（D15①，逐 case 而不是汇总数）**：交集 {pv['n_pairs']} 条 ⇒ "
        f"通过 {pv['n_ok']} 条；反例 {pv['failed'] or '无'}；OFF 侧有卡 {pv['off_has_card'] or '无'} "
        f"⇒ {'✅ 成立' if pv['passed'] else '❌ 不成立'}"
    )
    lines.append(
        f"- **可追溯断言（D15②）**：ON 组 `memory_traceable` = "
        f"{_mt.rate([_mt.memory_traceable(x) if x.get('validity_valid') is not False else None for x in store_on.records])}"
        "（逐轮日志 + 记忆卡通道 + `episodes` 字段 + `store_enabled` 齐备）"
    )
    on_pos = [
        x
        for x in store_on.records
        if (x.get("gold", {}).get("expected_memory") or {}).get("should_be_recalled") is True
        and x.get("validity_valid") is not False
    ]
    on_pos_hit = sum(1 for x in on_pos if x.get("memory_recalled_actual") is True)
    lines.append(
        f"- Store ON·正样本（should_be_recalled=True 且 valid）= {len(on_pos)} 条，"
        f"实际召回 = {on_pos_hit} 条 ⇒ "
        f"{'✅ 跨会话召回成立' if on_pos_hit == len(on_pos) and on_pos else '⚠️ 有正样本未召回（见逐条表）'}"
    )
    inv = store_on.n_case_invalid + store_off.n_case_invalid
    lines.append(
        f"- case_invalid 合计 = {inv} 条（前置条件没凑成）——"
        f"{'无非预期' if inv == 0 else '这些**不计入产品失败**，需在报告中单列'}"
    )
    lines.append("")
    lines.append(
        "> ★ **provenance 声明**：本轮使用的代码含 `schema/grading.py` 的 canonical KP 示例修正"
        "（属**产品 prompt 行为变更**）。该结果**不得回写进 Phase 0B 冻结基线**；"
        "若 Memory 相关改动正式纳入 Phase 1，应形成新的 provenance/version。"
    )
    lines.append("")
    return "\n".join(lines)


async def main_async(args: argparse.Namespace) -> int:
    cases = load_demo("memory", limit=args.limit)
    if not cases:
        logger.error("未加载到 memory case —— 先跑 build_demo_cases.py")
        return 2

    if args.dry_run:
        print("\n# Step 5 计划（dry-run，不调用任何 LLM）\n")
        print(
            f"case 数：{len(cases)}；将跑两组（Store ON / Store OFF）= {2 * len(cases)} 次 case\n"
        )
        print("| case | 段数 | 总轮次 | should_recall | 前置条件 |")
        print("|---|---|---|---|---|")
        for c in cases:
            sc = c.gold.setup_conditions
            cond = []
            if sc:
                if sc.min_grade_calls is not None:
                    cond.append(f"≥{sc.min_grade_calls}次批改")
                if sc.grade_score_bands:
                    cond.append(
                        "分数∈" + ",".join(f"[{lo},{hi}]" for lo, hi in sc.grade_score_bands)
                    )
            lines = c.gold.expected_memory.values if c.gold.expected_memory else []
            should = c.gold.expected_memory.should_be_recalled if c.gold.expected_memory else None
            print(
                f"| {c.case_id} | {len(c.all_sessions)} | {len(c.all_sessions_flat)} | "
                f"{should} ({lines}) | {'; '.join(cond) or '-'} |"
            )
        print("\n每组每次 case = 多段会话（A 段批改 + B 段追问），约 5–9 次 LLM 调用。")
        print(f"预计总调用 ≈ {2 * len(cases)} × 7 ≈ {2 * len(cases) * 7} 次。")
        return 0

    problems = preflight_check()
    if problems:
        for p in problems:
            logger.error("预检失败：%s", p)
        print("\n> ⛔ 预检失败，已中止（未消耗 LLM）。请先恢复依赖服务。\n")
        return 3

    stamp = datetime.now(UTC).astimezone().strftime("%Y%m%d_%H%M")

    # ★ `--out-tag`（2026-10-07 Step 9 加）：**默认不覆写既有归档**。
    #   原实现固定写 `phase1_memory_step5_store_{on,off}.jsonl` —— 那两份是 §5 与 #4/#6
    #   数字的证据件，重跑一次就把旧证据覆盖了。
    #   ★ 检查必须在**跑之前**做：放在写盘处会等于「先烧 ~84 次调用、再拒绝落盘」，
    #     既丢了证据又白花 token（第一版就是这么写的，已挪出来）。
    suffix = f"_{args.out_tag}" if args.out_tag else ""
    targets = [OUT_DIR / f"phase1_memory_step5_store_{t}{suffix}.jsonl" for t in ("on", "off")]
    existing = [str(p.relative_to(ROOT)) for p in targets if p.exists()]
    if existing and not args.force:
        logger.error(
            "以下归档已存在，拒绝覆写：%s（换 --out-tag，或确认要覆盖才用 --force）", existing
        )
        return 4

    on = await _run_arm(store_enabled=True, limit=args.limit)
    off = await _run_arm(store_enabled=False, limit=args.limit)

    # 落盘原始 record（两组分开，便于复算）
    for arm, p in ((on, targets[0]), (off, targets[1])):
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            for r in arm.records:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        logger.info("归档 → %s", p)

    md = _render(on, off)
    report_path = OUT_DIR / f"PHASE1_MEMORY_STEP5_{stamp}.md"
    report_path.write_text(md, encoding="utf-8")
    print("\n" + md)
    logger.info("报告 → %s", report_path)
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Step 5 Memory paired control")
    ap.add_argument("--limit", type=int, default=None, help="每 task 取前 N 条")
    ap.add_argument("--dry-run", action="store_true", help="只打印计划，不调用 LLM")
    ap.add_argument(
        "--out-tag",
        default="",
        help="归档文件名后缀（如 step9_20261007）；不填则沿用旧名，且旧名存在时会**中止**",
    )
    ap.add_argument("--force", action="store_true", help="允许覆写同名既有归档（默认拒绝）")
    args = ap.parse_args(argv)
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
