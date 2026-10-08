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
    # Generate 交付判据（§3.1 v1.0 冻结项 + 机械替身，定义只在 `predicates.registry`）：
    # ★ `gen_case_pass` = 主指标（registry 逐题复合，四态）；`gen_delivery` = 项级池化，仅诊断。
    gen_case_pass: dict[str, Any] = field(default_factory=dict)
    gen_delivery: dict[str, Any] = field(default_factory=dict)
    gen_items: dict[str, Any] = field(default_factory=dict)
    memory_correct_use: dict[str, Any] = field(default_factory=dict)
    # ★ D15：分母摊开（不算率）+ 证据链可追溯性
    memory_measure_scope: dict[str, Any] = field(default_factory=dict)
    memory_traceability: dict[str, Any] = field(default_factory=dict)
    # ★ Verify 行为层（D14）：仍出题率（**必须 0**）+ 两级引用率
    ver_fabrication: dict[str, Any] = field(default_factory=dict)
    ver_item_cited: dict[str, Any] = field(default_factory=dict)
    ver_year_only: dict[str, Any] = field(default_factory=dict)
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
        # ★ Task 4（registry 化）：判据定义只有 `predicates.registry` 一处，报告层只读——
        #   逐题复合走 `pc.composite`（fail 优先 → missing_premise 毒化 → not_applicable 有权缺席），
        #   「整题测不到」⇒ rate=None、missing_premise 显式计数，不再被剔出分母（§4.2 的教训）。
        #   裁决 1：本函数**不得改写**传入的 record —— 落盘（判据值 + item_reasons）只归 `cli._backfill`。
        from evaluation.task_eval.predicates import common as pc
        from evaluation.task_eval.predicates import registry

        preds = registry.for_task("generate")
        verdicts_per_case: list[dict[str, pc.Verdict]] = []
        for r in records:
            verdicts_per_case.append({p.name: p.fn(r) for p in preds})
        rep.gen_items = {p.name: pc.rate([v[p.name] for v in verdicts_per_case]) for p in preds}
        optional = frozenset(p.name for p in preds if p.optional)
        comp = [pc.composite(v, optional=optional) for v in verdicts_per_case]
        # ★ 主指标：逐题「required 项复合全过」（对齐 §3.1 的逐题 AND）。
        rep.gen_case_pass = pc.rate(comp)
        # 项级池化（**诊断，非主指标**）：required 项的判定倒进一个池子数通过率。
        rep.gen_delivery = pc.rate(
            [v for per in verdicts_per_case for k, v in per.items() if k not in optional]
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
        # ★ D15：Memory 的 §6 行不写百分数门槛 ⇒ 这里必须把**分母从哪来**摊开，
        #   否则读报告的人会把「1/1 = 100%」当成品能力率。三条都计数、不算率：
        #     positives_total     = 声明为正样本的 case 数
        #     positives_valid     = 其中前置条件成立的（= 有资格进分母的）
        #     positives_traceable = 其中结论有证据链可查的（断言 ②）
        pos = [
            r
            for r in records
            if ((r.get("gold") or {}).get("expected_memory") or {}).get("should_be_recalled")
            is True
        ]
        pos_valid = [r for r in pos if r.get("validity_valid") is True]
        rep.memory_measure_scope = {
            "positives_total": len(pos),
            "positives_valid": len(pos_valid),
            "positives_invalid": len(pos) - len(pos_valid),
            "positives_traceable": sum(1 for r in pos_valid if metrics.memory_traceable(r)),
        }
        rep.memory_traceability = metrics.rate(
            [
                metrics.memory_traceable(r) if r.get("validity_valid") is not False else None
                for r in records
            ]
        )

    if task == "verify":
        # ★ D14：Verify 这一行改由行为层把门（`question_id_recall@k` 不可计算 = #20；
        #   `final_quality≥4` 在 verify 上测的是**检索覆盖**，见 `metrics.verify_*` 的说明）。
        #   `rate()` 天然排除 None ⇒ 探针跑/无回复的 case 不会被算成「没出题」。
        #   ★ 读 JSON 时注意：`ver_fabrication` 是**坏事率**，里面的 `passed` 数的是
        #     「判为 True（= 仍出题）」的条数，不是「通过」。门槛要求它的 rate **= 0**。
        rep.ver_fabrication = metrics.rate([r.get("ver_fabricated") for r in records])
        rep.ver_item_cited = metrics.rate([r.get("ver_exam_item_cited") for r in records])
        rep.ver_year_only = metrics.rate([r.get("ver_exam_year_only") for r in records])

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
    """渲染率块。★ 兼容两代形状：`metrics.rate`（`n_a` 单键）与 `pc.rate`（四态双键）。"""
    rate = block.get("rate")
    if rate is None:
        if "n_a" in block:
            return f"n/a({block.get('n_a', 0)})"
        return (
            f"n/a(mp={block.get('n_a_missing_premise', 0)},"
            f" na={block.get('n_a_not_applicable', 0)})"
        )
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
        lines.append("## Generate 专有（registry 判据，§3.1 v1.0）")
        lines.append("")
        lines.append(
            "> **主指标口径**：registry 判据的**逐题复合**（`predicates.common.composite`）——"
            "任一 required 项 fail ⇒ 该题 fail；required 项测不到（missing_premise）⇒ "
            "该题复合为 missing_premise ⇒ **rate=None，不冒充通过率**（§4.2：旧布尔合取把"
            " None 剔出分母，0.733 被读成 1.000）。"
        )
        lines.append(
            "> ★ **不用项级池化当主指标**：池化会把「一道题崩掉 3 项」被另外十几道题的通过稀释，"
            "它测的是「项平均健康度」，不是「能否交付一道完整的题」⇒ 只列作诊断。"
        )
        lines.append("")
        lines.append("| 判据 | 通过率 | n（已测） | missing_premise | not_applicable |")
        lines.append("|---|---|---|---|---|")
        for label, st in gen["gen_items"].items():
            lines.append(
                f"| {label} | {_pct(st)} | {st.get('n')} "
                f"| {st.get('n_a_missing_premise')} | {st.get('n_a_not_applicable')} |"
            )
        cp = gen.get("gen_case_pass") or {}
        d = gen.get("gen_delivery") or {}
        lines.append("")
        lines.append(
            f"- **Generate 适用项全过率（主指标）**：{_pct(cp)}"
            f"（已测 n={cp.get('n')}; 测不到 missing_premise={cp.get('n_a_missing_premise')}、"
            f"不适用 not_applicable={cp.get('n_a_not_applicable')}，均已剔除出分母）"
        )
        lines.append(
            f"- 项级池化通过率（**诊断，非主指标**）：{_pct(d)}"
            f"（已测 n={d.get('n')} 项；missing_premise={d.get('n_a_missing_premise')}、"
            f"not_applicable={d.get('n_a_not_applicable')} 项已剔除）"
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
        sc = memory.get("memory_measure_scope") or {}
        if sc:
            lines.append(
                f"- **分母摊开（D15，§6 的 Memory 行不设百分数门槛就看这三行）**："
                f"正样本共 {sc.get('positives_total')} 条 ⇒ 前置条件成立 "
                f"{sc.get('positives_valid')} 条（不可测 {sc.get('positives_invalid')} 条）、"
                f"其中有证据链可查的 {sc.get('positives_traceable')} 条"
            )
            lines.append(
                f"- `memory_traceable`（逐轮日志 + 记忆卡通道 + `episodes` 字段 + `store_enabled` 齐备）："
                f"{_pct(memory['memory_traceability'])}"
            )
            lines.append(
                "> ★ 上面任何「率」都必须连同本行的分母一起引用："
                "**n=1 的 100% 不是能力率**（`EXPERIMENTS.md` §21 D15）。"
            )
        lines.append("")

    ver = (report.get("tasks") or {}).get("verify")
    if ver and (ver.get("ver_fabrication") or {}).get("n"):
        lines.append("## Verify 专有（行为层三判据 · D14）")
        lines.append("")
        lines.append(
            "> §3.1 冻结的头号指标 `question_id_recall@k` 在当前语料**不可计算**（#20，按 §11 走披露）；"
            "`final_quality≥4` 在 verify 上测的是**检索覆盖**（未达成 case 的诚实拒答是正确行为）"
            "⇒ 这两项都**不能**当 Verify 的通过判据，本表按行为层把门。"
        )
        lines.append("")
        lines.append(
            f"- **仍出题率（硬条件：必须 0）**：{_pct(ver['ver_fabrication'])}"
            f"（可测 {ver['ver_fabrication'].get('n')} 条；未测/无回复 "
            f"{ver['ver_fabrication'].get('n_a')} 条已剔除）"
        )
        lines.append(f"- L1 给出可核对真题条目：{_pct(ver['ver_item_cited'])}")
        lines.append(f"- L2 只报年份/来源与考点归属：{_pct(ver['ver_year_only'])}")
        lines.append(
            "- ★ `final_quality` 与 `exam_hit@k` 只作诊断保留；"
            "**不得**用 `exam_hit` 冒充 `question_id_recall` 回答 §4 的因果问题（#20/D7）。"
        )
        lines.append("")
    return "\n".join(lines)
