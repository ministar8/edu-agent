"""主张 ledger 的行构建：tier 申报 + `_row_*` 构建器 + 复合（`compute_rows`）。"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from _ledger_common import (  # noqa: E402
    _PROV_KEYS,
    _sha12,
)

from evaluation.task_eval import claims as cl  # noqa: E402
from evaluation.task_eval import metrics  # noqa: E402
from evaluation.task_eval import report as report_mod  # noqa: E402
from evaluation.task_eval.predicates import common as pc  # noqa: E402
from evaluation.task_eval.predicates import registry  # noqa: E402

DERIVED_TIER_DIMS = frozenset({"Generate", "Verify", "Memory"})


LITERAL_TIER_REASONS: dict[str, tuple[int, tuple[str, ...]]] = {
    "QA": (2, ("§1.3-tier2",)),
    "Grade": (1, ("§1.3-tier1", "G1b-revoked", "§7-②")),
    "Retrieval": (0, ("§1.3-tier0",)),
    "hard failure": (0, ("§1.3-tier0",)),
    "tool error": (0, ("§1.3-tier0",)),
    "provenance": (0, ("§1.3-tier0", "§3")),
    "Docker / TEI": (0, ("§6-no-archive",)),
    "四任务链": (0, ("§6-no-archive",)),
}


def tier_decl(dim: str) -> dict[str, Any]:
    """字面量行的 tier 申报：数值只存在于 `LITERAL_TIER_REASONS`，构建器拿不到裸 int。"""
    tier, anchors = LITERAL_TIER_REASONS[dim]
    return {"tier": tier, "tier_reason": anchors}


def tier_decl_derived(dim: str, source: str, tier: int) -> dict[str, Any]:
    """派生行的 tier 申报：dim 必须在 `DERIVED_TIER_DIMS` 且不在字面量表里（两表互斥 ⇒ 不会漂移）。"""
    if dim not in DERIVED_TIER_DIMS:
        raise ValueError(f"{dim}: 未申报为 registry 派生行 ⇒ 不能给裸 max(tier)")
    if dim in LITERAL_TIER_REASONS:
        raise ValueError(f"{dim}: 同时出现在字面量表与派生集合 ⇒ tier 依据有歧义")
    return {"tier": tier, "tier_derived": source}


def tier_ok_for(tier: int, boundary: bool, jitter: dict[str, float]) -> tuple[bool, str]:
    """§1.3 的 tier_ok 取值规则：tier 0/1 恒 True；tier 2 须两个前置都**算出来**为真。"""
    if tier <= 1:
        return True, f"tier {tier}（机械事实/可观测物证，不经 judge）⇒ 前置恒成立"
    return (
        boundary and bool(jitter),
        f"tier {tier} 两前置：boundary_calibrated={boundary}"
        "（calibration_30 真实 human_score 分布算出；门槛 final_quality≥4 两侧各需 ≥3 样本）"
        f"；repeat_jitter 非空={bool(jitter)}"
        "（同 case 跨 --records 多份归档的 final_quality 极差；单份归档 ⇒ {} = 未量化）",
    )


def provenance_match_for(
    records: list[dict[str, Any]], cur_cv: str, cur_golden: str
) -> tuple[bool, str]:
    """归档嵌套 provenance 八键齐全 **且** code_version/golden_sha256 与当前一致。

    ★ 键缺失 ⇒ 保守判不符（check_1e 的教训：空 provenance ≠「配置已核对」）。
    ★ 注记文本**不写当前 code_version**：它随 HEAD/工作区状态变，写进 ledger 会让
      `--check` 的一致性比对在每次提交后都假红；当前值只参与布尔量计算。
    """
    if not records:
        return False, "无归档记录可核对 ⇒ 保守判不符"
    ok_n = 0
    for r in records:
        p = r.get("provenance")
        if (
            isinstance(p, dict)
            and all(k in p for k in _PROV_KEYS)
            and p.get("code_version") == cur_cv
            and p.get("golden_sha256") == cur_golden
        ):
            ok_n += 1
    legacy = sorted({str(r.get("code_version") or "—") for r in records})
    return (
        ok_n == len(records),
        f"嵌套 provenance 齐全且与当前 code_version/golden_sha256 一致：{ok_n}/{len(records)} 条；"
        f"归档顶层 code_version={','.join(legacy)}（当前值由 `provenance.code_version()` 运行时算出）",
    )


def signed_for(backing: tuple[str, ...], sigs: dict[str, Any]) -> tuple[bool, str]:
    if not backing:
        return False, "未签署（该行无 registry 支撑判据 ⇒ R1-B 无签署对象，恒 False）"
    n = sum(1 for b in backing if b in sigs)
    src = "签署文件在册" if sigs else "evals/claims/r1b_signatures.json 不存在 ⇒ 恒 False（待签）"
    return n == len(
        backing
    ), f"{'已签' if n == len(backing) else '未签署'}（{n}/{len(backing)} 判据；{src}）"


def _na_tail(block: dict[str, Any]) -> str:
    """§1.6 分母语义：**单项率必须并列 N/A 计数**——rate 有值时同样要摊开分母。

    否则 `0.966（已测 n=29）` 读不出池子是 60 条非 memory 记录、另有 31 条 None
    被静默剔出分母（`metrics.rate` 的口径是「N/A 从分母剔除」）。

    ★ 四态块（`predicates.common.rate`）按 §1.6「不得合并成一个 `n/a`」分列
      `missing_premise` 与 `not_applicable`；`metrics.rate` 块只有单个 `n_a`
      （None 计数，该函数不区分后两态）⇒ 只能并列一个。两种键名都是代码里的真实键。
    ★ 纯显示：不改任何计数/分母的计算。
    """
    if "n_a_missing_premise" in block:
        return (
            f", missing_premise={block.get('n_a_missing_premise')}, "
            f"not_applicable={block.get('n_a_not_applicable')}"
        )
    if "n_a" in block:
        return f", n/a={block.get('n_a')}"
    return ""


def fmt_rate(block: dict[str, Any] | None) -> str:
    if block is None:
        return "N/A（无可算的归档证据）"
    r = block.get("rate")
    if r is None:
        if "n_a_missing_premise" in block:
            return (
                f"N/A（rate=None；已测 n={block.get('n')}, "
                f"missing_premise={block.get('n_a_missing_premise')}, "
                f"not_applicable={block.get('n_a_not_applicable')}）"
            )
        return f"N/A（rate=None；已测 n={block.get('n', 0)}, n/a={block.get('n_a', 0)}）"
    return f"{r:.3f}（已测 n={block.get('n')}{_na_tail(block)}）"


def _count_block(k: int, n: int) -> dict[str, Any]:
    return {"rate": round(k / n, 4) if n else None, "n": n}


def _mark(flag: bool) -> str:
    return "✓" if flag else "✗"


def _pred_verdict_blocks(task: str, by_task: dict[str, list[dict[str, Any]]]):
    """task 的 registry 判据在归档上逐条重算 ⇒ (preds, {name: pc.rate 块})。"""
    preds = registry.for_task(task)
    recs = by_task.get(task) or []
    blocks: dict[str, dict[str, Any]] = {}
    for p in preds:
        blocks[p.name] = pc.rate([p.fn(r) for r in recs])
    return preds, blocks


def _row_qa(ctx: dict[str, Any]) -> dict[str, Any]:
    recs = ctx["by_task"].get("qa") or []
    rep = report_mod.summarize_task("qa", recs) if recs else None
    return {
        "metric": "final_quality≥4 的 case 占比（唯一公式 `metrics.quality_pass`；"
        "judge 观点 ⇒ tier 2，两个前置见「前置」列）",
        "block": (rep.quality_pass if rep else None),
        **tier_decl("QA"),
        "backing": (),
        "records": recs,
        "notes": [],
    }


def _row_generate(ctx: dict[str, Any]) -> dict[str, Any]:
    recs = ctx["by_task"].get("generate") or []
    preds, blocks = _pred_verdict_blocks("generate", ctx["by_task"])
    optional = frozenset(p.name for p in preds if p.optional)
    per_case = []
    for r in recs:
        per_case.append(pc.composite({p.name: p.fn(r) for p in preds}, optional=optional))
    cp = pc.rate(per_case) if recs else None
    notes: list[str] = []
    gold_deps = sorted(
        {p.name for p in preds if any(i.startswith("gold.") for i in p.contract_inputs)}
    )
    if gold_deps:
        notes.append(
            f"gold 依赖判据（{', '.join(gold_deps)}）的前提是盲标 gold（P−1，暂停中）；"
            "缺失时按契约记 missing_premise 并原样传播——诚实状态，不是失败，也不得折成 pass/fail"
        )
    for p in preds:
        st = blocks.get(p.name) or {}
        if st.get("n_a_missing_premise"):
            notes.append(
                f"缺前提明细：{p.name} missing_premise {st['n_a_missing_premise']}/{len(recs)}"
                f"（契约输入：{', '.join(p.contract_inputs)}）"
            )
    required = [p for p in preds if not p.optional]
    return {
        "metric": "五项完整交付率 `gen_case_pass`（registry 逐题复合，§3.1 冻结五项；"
        "机械替身 optional 项只作诊断、永不顶替冻结名进本行）",
        "block": cp,
        **tier_decl_derived(
            "Generate",
            "registry 必需（非 optional）判据 max(tier)",
            max((p.tier for p in required), default=1),
        ),
        "backing": tuple(p.name for p in preds),
        "records": recs,
        "notes": notes,
    }


def _row_grade(ctx: dict[str, Any]) -> dict[str, Any]:
    recs = ctx["by_task"].get("grade") or []
    rep = report_mod.summarize_task("grade", recs) if recs else None
    tol = (rep.score_tolerance if rep else None) or {}
    va = (rep.verdict_agreement if rep else None) or {}
    notes: list[str] = []
    if tol.get("degenerate_gold"):
        notes.append(
            f"退化 gold：human_score 仅 {tol.get('n_distinct_gold')} 个不同取值 ⇒ ±10 容差无判别力"
            f"（raw_rate={tol.get('raw_rate')} 仅诊断，不得当成绩；偏离登记 EVIDENCE_CHAIN §7 ②）"
        )
    if va.get("rate") is not None:
        notes.append(
            f"行级替身（**辅助位，非门槛值**）：verdict_agreement={va['rate']:.3f}"
            f"（已测 n={va.get('n')}, n/a={va.get('n_a')}）"
        )
    return {
        "metric": "`score_tolerance@±10`（EFFECT_PLAN §3.1 头号；两极 gold ⇒ 行级判据改读 "
        "verdict_agreement 且只作辅助披露）",
        "block": tol or None,
        **tier_decl("Grade"),
        "backing": (),
        "records": recs,
        "notes": notes,
    }


def _row_verify(ctx: dict[str, Any]) -> dict[str, Any]:
    recs = ctx["by_task"].get("verify") or []
    preds, blocks = _pred_verdict_blocks("verify", ctx["by_task"])
    hard = [p for p in preds if not p.optional]
    blk = blocks.get("ver_fabricated") if recs else None
    return {
        "metric": "仍出题率 `ver_fabricated`（硬条件必须 0；D14 行为层把门——§6 原文 "
        "final_quality≥4 在 verify 上测的是检索覆盖，只作诊断）。值为**坏事率**",
        "block": blk,
        **tier_decl_derived(
            "Verify",
            "registry 硬条件（非 optional）判据 max(tier)",
            max((p.tier for p in hard), default=1),
        ),
        "backing": tuple(p.name for p in hard),
        "records": recs,
        "notes": ["值口径：rate 越高越坏（1.000 = 每条仍在编造真题）；门槛要求见 §6 原文列"],
    }


def _row_memory(ctx: dict[str, Any]) -> dict[str, Any]:
    recs = ctx["by_task"].get("memory") or []
    preds, blocks = _pred_verdict_blocks("memory", ctx["by_task"])
    rep = report_mod.summarize_task("memory", recs) if recs else None
    notes: list[str] = []
    sc = (rep.memory_measure_scope if rep else None) or {}
    if sc:
        notes.append(
            f"分母摊开（D15）：正样本 {sc.get('positives_total')} 条 ⇒ 前置成立 "
            f"{sc.get('positives_valid')} 条（不可测 {sc.get('positives_invalid')} 条）、"
            f"证据链可查 {sc.get('positives_traceable')} 条——n=1 的率不是能力率"
        )
    return {
        "metric": "correct-use rate `memory_correct_use`（唯一公式 "
        "`metrics.memory_correct_use_from_record` 的 registry verdict 化）",
        "block": blocks.get("memory_correct_use") if recs else None,
        **tier_decl_derived(
            "Memory", "registry 该任务全部判据 max(tier)", max((p.tier for p in preds), default=1)
        ),
        "backing": tuple(p.name for p in preds),
        "records": recs,
        "notes": notes,
    }


def _row_retrieval(ctx: dict[str, Any]) -> dict[str, Any]:
    pool = [r for r in ctx["records"] if r.get("task") != "memory"]
    blk = metrics.rate([r.get("kp_hit") for r in pool]) if pool else None
    return {
        "metric": "kp_hit 率（tier 0 机械字段，全任务池化重算；Memory 除外——非知识检索任务）。"
        "§6「不低于 V-2026-10-02」需基线归档对比，未接入本 ledger ⇒ 不下该结论",
        "block": blk,
        **tier_decl("Retrieval"),
        "backing": (),
        "records": pool,
        "notes": [],
    }


def _row_hard_failure(ctx: dict[str, Any]) -> dict[str, Any]:
    recs = ctx["records"]
    k = sum(1 for r in recs if r.get("hard_fails"))
    return {
        "metric": "`hard_fails` 非空的记录占比（**坏事率**，越低越好）",
        "block": _count_block(k, len(recs)),
        **tier_decl("hard failure"),
        "backing": (),
        "records": recs,
        "notes": [],
    }


def _row_tool_error(ctx: dict[str, Any]) -> dict[str, Any]:
    recs = ctx["records"]
    k = sum(1 for r in recs if "tool_error" in (r.get("failure_reason") or []))
    return {
        "metric": "`failure_reason` 含 `tool_error` 的记录占比（**坏事率**；判定唯一来源 "
        "`runner.mechanical_failures`，检索返空 `empty` 属 retrieval 口径、不计入本行）",
        "block": _count_block(k, len(recs)),
        **tier_decl("tool error"),
        "backing": (),
        "records": recs,
        "notes": [],
    }


def _row_provenance(ctx: dict[str, Any]) -> dict[str, Any]:
    recs = ctx["records"]
    k = sum(
        1
        for r in recs
        if isinstance(r.get("provenance"), dict)
        and all(key in r["provenance"] for key in _PROV_KEYS)
    )
    return {
        "metric": "嵌套 `provenance` 八键齐全的记录占比（§3；与当前版本是否一致另见 "
        "provenance_match 布尔量）",
        "block": _count_block(k, len(recs)),
        **tier_decl("provenance"),
        "backing": (),
        "records": recs,
        "notes": [],
    }


def _row_no_archive(ctx: dict[str, Any], *, dim: str = "Docker / TEI") -> dict[str, Any]:
    return {
        "metric": "本 ledger 无该维度的归档证据源（需服务验收/演示记录接入后才可算）",
        "block": None,
        **tier_decl(dim),
        "backing": (),
        "records": [],
        "notes": [],
    }


_ROW_BUILDERS = {
    "QA": _row_qa,
    "Generate": _row_generate,
    "Grade": _row_grade,
    "Verify": _row_verify,
    "Memory": _row_memory,
    "Retrieval": _row_retrieval,
    "hard failure": _row_hard_failure,
    "tool error": _row_tool_error,
    "provenance": _row_provenance,
    "Docker / TEI": lambda ctx: _row_no_archive(ctx, dim="Docker / TEI"),
    "四任务链": lambda ctx: _row_no_archive(ctx, dim="四任务链"),
}


def _finish_row(dim: str, requirement: str, spec: dict[str, Any], ctx: dict[str, Any]) -> dict:
    backing = tuple(spec.get("backing") or ())
    recs = spec.get("records") or []
    fp_notes: list[str] = []
    if backing:
        fps = []
        for name in backing:
            ok, note = ctx["falsify_for"](name)
            fps.append(ok)
            fp_notes.append(f"{name}: {note}")
        fp = all(fps)
    else:
        fp = False
        fp_notes.append("（无 registry 支撑判据 ⇒ 无 mutation 取证，falsify_passed 恒 False）")
    tier_kind, tier_basis = cl.tier_justification(dim, spec)
    tok, tok_note = tier_ok_for(int(spec["tier"]), ctx["boundary"], ctx["jitter"])
    tok_note = f"[{tier_kind}] {tier_basis}；{tok_note}"
    pm, pm_note = provenance_match_for(recs, ctx["cur_cv"], ctx["cur_golden"])
    block = spec.get("block")
    disc = bool(block and block.get("rate") is not None)
    sg, sg_note = signed_for(backing, ctx["sigs"])
    status = cl.derive_status(
        {}, falsify_passed=fp, tier_ok=tok, discriminating=disc, provenance_match=pm, signed=sg
    )
    if recs:
        anchor_files = ", ".join(f"`{p.as_posix()}`@sha256:{_sha12(p)}" for p in ctx["files"])
        anchor = f"证据：{anchor_files}"
        if backing:
            fr = ctx["falsify_path"]
            fr_sha = _sha12(fr) if fr.exists() else "missing"
            anchor += f"；mutation 取证：`{fr.as_posix()}`@sha256:{fr_sha}"
    else:
        anchor = "证据：无归档证据源（该维度未被 task_eval 归档覆盖 ⇒ 未测量）"
    repro = (
        "复现：`PYTHONIOENCODING=utf-8 PYTHONPATH=src uv run python "
        f"scripts/lib/build_claim_ledger.py --records {ctx['records_spec']}`"
    )
    value = fmt_rate(block)
    return {
        "dim": dim,
        "requirement": requirement,
        "metric": spec["metric"],
        "value": value,
        "status": status,
        "booleans": (
            f"falsify{_mark(fp)} tier{_mark(tok)} disc{_mark(disc)} prov{_mark(pm)} sign{_mark(sg)}"
        ),
        "tier_note": tok_note,
        "anchor": anchor,
        "repro": repro,
        "signed_note": sg_note,
        "notes": list(spec.get("notes") or []) + fp_notes + [f"provenance_match：{pm_note}"],
    }


def compute_rows(ctx: dict[str, Any]) -> list[dict[str, Any]]:
    gate_rows = ctx["gate_rows"]
    rows = [
        _finish_row(dim, req, _ROW_BUILDERS[dim](ctx), ctx)
        for dim, req in gate_rows
        if dim in _ROW_BUILDERS
    ]
    unknown = [dim for dim, _ in gate_rows if dim not in _ROW_BUILDERS]
    if unknown:
        raise SystemExit(f"§6 出现 ledger 未登记的维度行：{unknown}（拒绝静默丢行）")
    missing = sorted(set(_ROW_BUILDERS) - {dim for dim, _ in gate_rows})
    if missing:
        raise SystemExit(
            f"ledger 构建器里有维度不在 EFFECT_PLAN §6 表中：{missing}（文档结构已变？）"
        )
    return rows
