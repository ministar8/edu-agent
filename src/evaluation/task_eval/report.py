"""Phase 0 报告：把 record 聚合成两张表（§2.B.5 基线表 + 能力总表）。

★ 报告纪律：
- 分母只含 `True/False`；`None`（不适用）单独计为 `n/a`，**不得并入失败率**。
- `final_quality` 的均值只统计有分的 case；缺分单独报 `judged_n`。
- `draft` 状态的 gold **不得出论文数字** —— 报告头显式标注 gold_status 分布。
"""

from __future__ import annotations

import logging
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from evaluation.task_eval import metrics

logger = logging.getLogger(__name__)

TASK_LABELS = {
    "qa": "QA",
    "generate": "Generate",
    "grade": "Grade",
    "verify": "Verify",
    "memory": "Memory",
}


@dataclass
class TaskReport:
    task: str
    n: int = 0
    judged_n: int = 0
    mean_final_quality: float | None = None
    quality_pass: dict[str, Any] = field(default_factory=dict)
    generation_ok: dict[str, Any] = field(default_factory=dict)
    failure_rate: float | None = None
    # ★ `case_invalid` 的样本数 —— 必须显式露出，否则「失败率的分母到底扣了几条」不可查。
    invalid_n: int = 0
    primary_failures: list[tuple[str, int]] = field(default_factory=list)
    # 检索侧
    kp_hit: dict[str, Any] = field(default_factory=dict)
    category_hit: dict[str, Any] = field(default_factory=dict)
    exam_hit: dict[str, Any] = field(default_factory=dict)
    pack_nonempty_rate: float | None = None
    mean_evidence_count: float | None = None
    # 任务专有
    score_tolerance: dict[str, Any] = field(default_factory=dict)
    # ★ 二值 gold 上合法的 Grade 头号指标（见 metrics.verdict_agreement 的说明）
    verdict_agreement: dict[str, Any] = field(default_factory=dict)
    score_mae: float | None = None
    # Generate 交付五项（§3.1 v1.0 冻结口径；N/A 从分母剔除）
    # ★ `gen_case_pass` = 主指标（逐题「适用项全过」）；`gen_delivery` = 项级池化，仅诊断。
    gen_case_pass: dict[str, Any] = field(default_factory=dict)
    gen_delivery: dict[str, Any] = field(default_factory=dict)
    gen_items: dict[str, Any] = field(default_factory=dict)
    memory_correct_use: dict[str, Any] = field(default_factory=dict)
    memory_recalled: dict[str, Any] = field(default_factory=dict)
    memory_used_rate: dict[str, Any] = field(default_factory=dict)
    memory_correct_rate: dict[str, Any] = field(default_factory=dict)


def _fmean(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 3) if values else None


def summarize_task(task: str, records: list[dict[str, Any]]) -> TaskReport:
    """聚合单个 task 的 record。输入为 `CaseRecord.to_dict()` 的列表。"""
    rep = TaskReport(task=task, n=len(records))
    if not records:
        return rep

    scores = [float(r["final_quality"]) for r in records if r.get("final_quality") is not None]
    rep.judged_n = len(scores)
    rep.mean_final_quality = _fmean(scores)

    rep.quality_pass = metrics.rate([metrics.quality_pass(r.get("final_quality")) for r in records])
    rep.generation_ok = metrics.rate([bool(r.get("generation_ok")) for r in records])

    # ★ 分母必须先剔除「case 本身不成立」的样本（方案 §2.B：**case validity ≠ product failure**）。
    #   旧口径分母 = `len(records)`，把 `case_invalid` 同时算进分子与分母 ——
    #   实测 Step 5 Store OFF 组 6 条里 4 条是 `case_invalid`，失败率被报成 **0.667**，
    #   读起来像「产品 2/3 的时候失败」，而真实含义是「这批样本本身没凑成前置条件」。
    def _is_invalid(r: dict[str, Any]) -> bool:
        return r.get("primary_failure") == "case_invalid" or r.get("validity_valid") is False

    rep.invalid_n = sum(1 for r in records if _is_invalid(r))
    valid_records = [r for r in records if not _is_invalid(r)]

    failed = [r for r in valid_records if r.get("primary_failure") not in (None, "", "none")]
    rep.failure_rate = round(len(failed) / len(valid_records), 4) if valid_records else None
    rep.primary_failures = Counter(r["primary_failure"] for r in failed).most_common()

    # ★ Memory 的检索指标一律 N/A（2026-10-05 修）：
    #   Memory 的 query 本就不是知识查询，检索返空属**预期** ——
    #   若照报 kp/cat/exam/pack，会把「预期返空」显示成「检索失败」，误导 Phase 1。
    if task != "memory":
        rep.kp_hit = metrics.rate([r.get("kp_hit") for r in records])
        rep.category_hit = metrics.rate([r.get("category_hit") for r in records])
        rep.exam_hit = metrics.rate([bool(r.get("exam_hit")) for r in records])
        nonempty = [bool(r.get("pack_nonempty")) for r in records]
        rep.pack_nonempty_rate = round(sum(nonempty) / len(nonempty), 4)
        counts = [float(r.get("evidence_count") or 0) for r in records]
        rep.mean_evidence_count = _fmean(counts)

    if task == "grade":
        pairs: list[tuple[float | None, float | None]] = []
        flags: list[bool | None] = []
        vflags: list[bool | None] = []
        humans: list[float] = []
        for r in records:
            model = metrics.parse_grade_score(str(r.get("reply") or ""))
            human = _human_score(r)
            flags.append(metrics.score_tolerance(model, human))
            vflags.append(metrics.verdict_agreement(model, human, _full_marks(r)))
            pairs.append((model, human))
            if human is not None:
                humans.append(human)
        block = metrics.rate(flags)
        # ★ 修 #7：人工分只有两极（实测 0B = `{100:8, 0:7}`）时，`tolerance=1.000`
        #   只证明"模型跟着说了 0/100"，**不证明判分能力** —— 报成有效值会直接误导论文。
        #   故置为 N/A（不进分母），但**保留 raw_rate** 供诊断，并把判定依据一起落进报告。
        degenerate, n_distinct = metrics.degenerate_gold(humans)
        block["raw_rate"] = block["rate"]
        block["degenerate_gold"] = degenerate
        block["n_distinct_gold"] = n_distinct
        if degenerate:
            block["rate"] = None
            block["value"] = None
        rep.score_tolerance = block
        rep.verdict_agreement = metrics.rate(vflags)
        rep.score_mae = metrics.score_mae(pairs)

    if task == "generate":
        # 交付五项（§3.1 v1.0；2026-10-06 按用户裁决重构，2026-10-07 #2 定聚合口径）：
        #   不适用项（None）从分母剔除 —— 但**主指标是逐题「适用项全过」**，
        #   项级池化只作诊断（详见 `metrics.delivery_rate` 与护栏 ⑭）。
        #   ❌ 不要求「5 项永远齐全」；❌ 难度匹配本批全 N/A（query 未指定难度）。
        item_keys = (
            ("gen_structure", "结构完整率"),
            ("gen_answerability", "答案可判定率"),
            ("gen_coverage", "知识点覆盖率"),
            ("gen_correctness", "内容正确率"),
            ("gen_difficulty", "难度匹配"),
        )
        rep.gen_items = {}
        for key, label in item_keys:
            rep.gen_items[label] = metrics.rate([r.get(key) for r in records])
        flat = [r.get(k) for r in records for k, _ in item_keys]
        rep.gen_delivery = metrics.delivery_rate(flat)
        # ★ 主指标（2026-10-07 #2 定稿）：**逐题**「适用项全过」——每题只看它自己
        #   能测的项，全过才算这题过。上面的池化数降级为诊断（见 `delivery_rate` docstring）。
        rep.gen_case_pass = metrics.rate(
            [metrics.every_item_passes([r.get(k) for k, _ in item_keys]) for r in records]
        )

    if task == "memory":
        # 四率（§2.B.4）：retrieved / used / correct / correct-use
        rep.memory_recalled = metrics.rate([r.get("memory_retrieved") for r in records])
        rep.memory_used_rate = metrics.rate([r.get("memory_used") for r in records])
        rep.memory_correct_rate = metrics.rate([r.get("memory_correct") for r in records])
        # ★ `correct_use` 走 `metrics.memory_correct_use_from_record`（**唯一公式**，
        #   从原始字段推导）。不能直接读 `r["memory_correct_use"]` —— 2026-10-07 之前
        #   落盘的归档存的是旧三元 AND 的值（详见 `metrics` 里 #21 的说明），
        #   直接读会把已修掉的负样本假阴性继续印出来；推导**不改写归档**。
        rep.memory_correct_use = metrics.rate(
            [metrics.memory_correct_use_from_record(r) for r in records]
        )

    return rep


def _human_score(record: dict[str, Any]) -> float | None:
    gold = record.get("gold") or {}
    value = gold.get("human_score") if isinstance(gold, dict) else None
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _full_marks(record: dict[str, Any]) -> float:
    """满分。缺失时回退 100.0 —— 与 `cases.py` 里 `full_marks` 的默认值保持一致。"""
    gold = record.get("gold") or {}
    value = gold.get("full_marks") if isinstance(gold, dict) else None
    try:
        return float(value) if value is not None else 100.0
    except (TypeError, ValueError):
        return 100.0


def build_report(records: list[dict[str, Any]]) -> dict[str, Any]:
    """按 task 分组产出完整报告结构（含 gold_status 分布）。"""
    by_task: dict[str, list[dict[str, Any]]] = {}
    for r in records:
        by_task.setdefault(str(r.get("task") or "unknown"), []).append(r)
    tasks = [t for t in TASK_LABELS if t in by_task]
    gold_status = Counter(str(r.get("gold_status") or "draft") for r in records)
    return {
        "n_total": len(records),
        "gold_status": dict(gold_status),
        "agent_models": sorted(
            {str(r.get("agent_model") or "") for r in records if r.get("agent_model")}
        ),
        "judges": sorted({str(r.get("judge") or "") for r in records if r.get("judge")}),
        "tasks": {t: summarize_task(t, by_task[t]).__dict__ for t in tasks},
    }


def _pct(block: dict[str, Any]) -> str:
    rate = block.get("rate")
    if rate is None:
        return f"n/a({block.get('n_a', 0)})"
    return f"{rate:.3f}"


def render_markdown(report: dict[str, Any]) -> str:
    """渲染两张表：能力总表（§0.1 口径）+ 基线表（§2.B.5）。"""
    lines: list[str] = []
    gs = report.get("gold_status") or {}
    lines.append(f"# Phase 0 报告（n={report['n_total']}）")
    lines.append("")
    # 警告按**实际状态**给，不要写死 —— 否则 gold 升级到 reviewed/frozen 后文案会失真。
    if gs.get("draft"):
        lines.append(f"> gold_status 分布：{gs} —— ⚠️ **含 draft，不得出论文数字**。")
    elif gs.get("reviewed") and not gs.get("frozen"):
        lines.append(
            f"> gold_status 分布：{gs} —— ✅ **已人工审核（reviewed）**；"
            "仍非 frozen，出论文数字前需最终冻结。"
        )
    else:
        lines.append(f"> gold_status 分布：{gs} —— ✅ **已冻结（frozen）**，可用于论文数字。")
    lines.append("")

    lines.append("## 能力总表")
    lines.append("")
    lines.append("| 能力 | Retrieval | Generation | Final Quality | 主要失败原因 |")
    lines.append("|---|---|---|---|---|")
    for task, rep in (report.get("tasks") or {}).items():
        if task == "memory":
            retrieval = "n/a（非知识检索任务）"
        else:
            retrieval = (
                f"kp={_pct(rep['kp_hit'])} cat={_pct(rep['category_hit'])} "
                f"exam@5={_pct(rep['exam_hit'])} pack={rep['pack_nonempty_rate']}"
            )
        generation = f"gen_ok={_pct(rep['generation_ok'])}"
        quality = f"μ={rep['mean_final_quality']} pass={_pct(rep['quality_pass'])}"
        top = rep["primary_failures"][0][0] if rep["primary_failures"] else "none"
        lines.append(
            f"| {TASK_LABELS.get(task, task)} | {retrieval} | {generation} | {quality} | {top} |"
        )
    lines.append("")

    lines.append("## 基线表（§2.B.5）")
    lines.append("")
    # ★ `失败率` 的分母是 **有效 n**（= n − case_invalid），不是 n —— 见 `summarize_task`。
    lines.append(
        "| Task | n | 有效 n | judged | 平均 final_quality | 失败率 | 主失败原因（分布） |"
    )
    lines.append("|---|---|---|---|---|---|---|")
    for task, rep in (report.get("tasks") or {}).items():
        dist = ", ".join(f"{k}×{v}" for k, v in rep["primary_failures"][:3]) or "—"
        lines.append(
            f"| {TASK_LABELS.get(task, task)} | {rep['n']} | {rep['n'] - rep['invalid_n']} | "
            f"{rep['judged_n']} | "
            f"{rep['mean_final_quality']} | {rep['failure_rate']} | {dist} |"
        )
    lines.append("")

    grade = (report.get("tasks") or {}).get("grade")
    if grade:
        lines.append("## Grade 专有")
        lines.append("")
        tol = grade["score_tolerance"]
        ver = grade.get("verdict_agreement") or {}
        lines.append(
            f"- **`verdict_agreement`（头号 · 结论一致率）**：{_pct(ver)}"
            f"（可判 n={ver.get('n')}, 不可判 n/a={ver.get('n_a')}）"
        )
        if ver.get("n_a"):
            # ★ 不可解析的批改输出必须**露出来** —— Phase 1 实测 2/15 条属此类，
            #   旧口径下它们在 tolerance 与 verdict 的分母里**双双隐身**，
            #   于是"100% 一致"掩盖了真实存在的批改失败。
            lines.append(
                f"- ⚠️ **{ver['n_a']} 条未产出可解析分数**（缺陷 A 的残留形态）—— "
                f"已从分母剔除，但这是 Grade 轴**真实的问题**，不可当作不存在。"
            )
        lines.append(
            f"- `score_tolerance@±10`：{_pct(tol)}（n={tol.get('n')}, n/a={tol.get('n_a')}）"
        )
        if tol.get("degenerate_gold"):
            # ★ 不写成一句轻描淡写的 n/a —— 必须让读者知道**为什么**不可判、
            #   以及那个被隐藏的原始值是多少（否则会被误读成"还没跑")。
            lines.append(
                f"- ⚠️ **`score_tolerance` 不可判**：人工分只有 "
                f"**{tol.get('n_distinct_gold')} 个不同取值**（两极 gold）⇒ ±10 容差退化成"
                f"「模型有没有跟着说这两个值」，**不构成判分能力证据**。"
                f"被隐藏的原始值 `raw_rate={tol.get('raw_rate')}` 仅供诊断。"
                f"★ 且**补不了部分分**：L3 语料 674/674 全是 2 分选择题、"
                f"case 的学生作答仅 1 个字母 ⇒ 无中间地带可标 ⇒ 头号指标改用上方 "
                f"`verdict_agreement`。"
            )
        lines.append(f"- `score_mae`：{grade['score_mae']}")
        lines.append("")

    gen = (report.get("tasks") or {}).get("generate")
    if gen and gen.get("gen_items"):
        lines.append("## Generate 专有（交付五项，§3.1 v1.0）")
        lines.append("")
        lines.append(
            "> **主指标口径**：逐题「**适用项全过**」率 —— 每题只看它自己**可测**的项"
            "（`None` 项不进该题分母），可测项全过才算这题过（对齐 §3.1 的逐题 AND）。"
        )
        lines.append(
            "> ★ **不用项级池化当主指标**：池化会把「一道题崩掉 3 项」被另外十几道题的通过稀释，"
            "它测的是「项平均健康度」，不是「能否交付一道完整的题」⇒ 只列作诊断。"
        )
        lines.append(
            "> ❌ 不要求「5 项永远齐全」；❌ 难度匹配本批全 N/A（query 未指定难度，无可靠 gold）。"
        )
        lines.append("")
        lines.append("| 交付项 | 通过率 | n（适用） | n/a（剔除） |")
        lines.append("|---|---|---|---|")
        for label, st in gen["gen_items"].items():
            lines.append(f"| {label} | {_pct(st)} | {st.get('n')} | {st.get('n_a')} |")
        cp = gen.get("gen_case_pass") or {}
        d = gen.get("gen_delivery") or {}
        lines.append("")
        lines.append(
            f"- **Generate 适用项全过率（主指标）**：{_pct(cp)}"
            f"（通过 {cp.get('passed')} / 适用 {cp.get('n')} 题；"
            f"整题无可测项的 {cp.get('n_a')} 题已从分母剔除）"
        )
        lines.append(
            f"- 项级池化通过率（**诊断，非主指标**）：{_pct(d)}"
            f"（通过 {d.get('passed')} / 适用 {d.get('n')} 项；不适用 {d.get('n_a')} 项已剔除）"
        )
        lines.append("")

    memory = (report.get("tasks") or {}).get("memory")
    if memory:
        lines.append("## Memory 专有（四率，§2.B.4）")
        lines.append("")
        lines.append("> Memory 的检索指标为 **N/A**（非知识检索任务）；判据是下列四率。")
        lines.append("")
        lines.append(f"- `memory_recalled`（检索率）：{_pct(memory['memory_recalled'])}")
        lines.append(f"- `memory_used`（使用率）：{_pct(memory['memory_used_rate'])}")
        lines.append(f"- `memory_correct`（正确率）：{_pct(memory['memory_correct_rate'])}")
        lines.append(
            f"- **`correct-use rate`**（retrieved ∧ used ∧ correct，**主指标**）："
            f"{_pct(memory['memory_correct_use'])}"
        )
        lines.append("")
    return "\n".join(lines)
