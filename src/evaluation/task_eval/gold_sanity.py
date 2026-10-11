"""Gold Sanity Check：进 0B **之前**验证 gold 本身合法（不是评价效果）。

为什么必须有
------------
0A 实测暴露：`kp_hit` 恒为 0 的根因是 **gold 与检索侧的命名空间错配**，不是检索失败。
即「evaluator 自己的 fail」会被读成「系统的 fail」。本检查把这类问题挡在 0B 之前。

两级判定（**必须分开**，否则会把「还没标」误报成「标错了」）
--------------------------------------------------------
- `ERROR`  ：gold **已填但非法**（如 `expected_kp` 不是合法考点 ID、
             `expected_question_ids` 指向不存在的题、`expected_difficulty=9`）。
             ⇒ **阻止进入 0B**（exit 1）。
- `PENDING`：draft 阶段**尚未标注**（如 `gold_answer` 为空、`human_score` 为空）。
             ⇒ 只提示，**不算失败**（Phase 0 允许 gold 处于 draft）。

用法::

    PYTHONPATH=src uv run python -m evaluation.task_eval sanity
    PYTHONPATH=src uv run python -m evaluation.task_eval sanity --task grade
"""

from __future__ import annotations

import logging
from pathlib import Path

from evaluation.task_eval._gold_sanity_checks import (
    ERROR,
    PENDING,
    SanityIssue,
    SanityReport,
    _check_field_ownership,
    _check_generate,
    _check_gold_source_ref,
    _check_grade,
    _check_grade_score_spread,
    _check_kp,
    _check_memory,
    _check_structure,
    _check_verify,
    _norm_stem,
)
from evaluation.task_eval.assets import (
    load_kp_index,
    parse_exam_items,
)
from evaluation.task_eval.cases import (
    TASKS,
    TaskCase,
)

logger = logging.getLogger(__name__)


# ── 主流程 ────────────────────────────────────────────────


def run_sanity(cases: list[TaskCase]) -> SanityReport:
    """对全部 case 跑检查。资产解析与生成器同源（`task_eval.assets`）。"""
    # 局部导入防成环 + 600 行上限（Task 7 裁定：宁可新建文件，不撑爆本文件）
    from evaluation.task_eval.gold_status_sanity import check_gold_answer_status

    report = SanityReport(n_cases=len(cases))
    kp_index = load_kp_index()
    items = parse_exam_items()
    question_ids = {it["question_id"] for it in items}
    stem_to_answer = {_norm_stem(it["stem"]): it["answer_key"] for it in items if it["stem"]}

    seen: dict[str, str] = {}
    for case in cases:
        if case.case_id in seen:
            report.issues.append(
                SanityIssue(case.case_id, case.task, ERROR, "case_id", "重复（case_id 必须唯一）")
            )
        seen[case.case_id] = case.task

        _check_structure(case, report.issues)
        _check_field_ownership(case, report.issues)
        _check_gold_source_ref(case, report.issues)
        check_gold_answer_status(case, report.issues)
        if case.task in ("qa", "generate"):
            _check_kp(case, kp_index, report.issues)
        if case.task == "generate":
            _check_generate(case, report.issues)
        if case.task == "grade":
            _check_grade(case, stem_to_answer, report.issues)
        if case.task == "verify":
            _check_verify(case, question_ids, report.issues)
        if case.task == "memory":
            _check_memory(case, kp_index, report.issues)

    # ★ 集合级检查（修 #7）：**单条**人工分是 0 或 100 完全合法，退化是**分布**性质 ——
    #   所以这里按整个 grade 集判，而不是逐条报（逐条会把 15 条全标黄，淹没真信号）。
    _check_grade_score_spread(cases, report.issues)
    return report


def render(report: SanityReport) -> str:
    lines = [f"# Gold Sanity Check（{report.n_cases} 条 case）", ""]
    status = "✅ PASS" if report.ok else "❌ FAIL（存在非法 gold，禁止进 0B）"
    lines.append(
        f"**结论：{status}** —— ERROR {len(report.errors)} · PENDING {len(report.pendings)}"
    )
    lines.append("")
    if report.errors:
        lines.append("## ERROR（gold 非法，会污染 0B）")
        lines.append("")
        lines.append("| case_id | task | field | 说明 |")
        lines.append("|---|---|---|---|")
        for i in report.errors[:40]:
            lines.append(f"| {i.case_id} | {i.task} | {i.field_name} | {i.message} |")
        lines.append("")
    pend_by_field: dict[str, int] = {}
    for i in report.pendings:
        pend_by_field[f"{i.task}.{i.field_name}"] = (
            pend_by_field.get(f"{i.task}.{i.field_name}", 0) + 1
        )
    if pend_by_field:
        lines.append("## PENDING（draft 未标注 —— 不算失败，0B 前需补齐）")
        lines.append("")
        for k, v in sorted(pend_by_field.items()):
            lines.append(f"- `{k}`：{v} 条")
        lines.append("")
    # ★ 集合级问题**必须把消息打出来** —— 它不像逐条 PENDING 那样是同类噪声，
    #   一条消息里就带着处置指引；只报"1 条"等于没提醒。
    dataset_issues = [i for i in report.pendings if i.case_id == "<dataset>"]
    if dataset_issues:
        lines.append("## 集合级 PENDING（分布性质，逐条看不出来 —— 必须处置或明确披露）")
        lines.append("")
        for i in dataset_issues:
            lines.append(f"- **{i.task}.{i.field_name}** —— {i.message}")
        lines.append("")
    return "\n".join(lines)


def sanity_for_demo(task: str | None = None, demo_dir: str | Path | None = None) -> SanityReport:
    from evaluation.task_eval.cases import load_demo

    return run_sanity(load_demo(task, demo_dir=demo_dir))


__all__ = [
    "ERROR",
    "PENDING",
    "SanityIssue",
    "SanityReport",
    "TASKS",
    "render",
    "run_sanity",
    "sanity_for_demo",
]
