"""主张 ledger 的 Markdown 渲染（主表 / 判据表 / 证伪表 / 工件）。"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from _ledger_common import (  # noqa: E402
    CALIBRATION_PATH,
    ROOT,
)
from _ledger_rows import (  # noqa: E402
    _mark,
    fmt_rate,
    provenance_match_for,
    signed_for,
    tier_ok_for,
)

from evaluation.task_eval import claims as cl  # noqa: E402
from evaluation.task_eval.predicates import registry  # noqa: E402


def _table(header: list[str], rows: list[list[str]]) -> list[str]:
    out = ["| " + " | ".join(header) + " |", "|" + "|".join(["---"] * len(header)) + "|"]
    out += ["| " + " | ".join(c.replace("|", "∣") for c in row) + " |" for row in rows]
    return out


def render_main_table(rows: list[dict[str, Any]]) -> list[str]:
    out = _table(
        [
            "维度",
            "主指标（口径 = 重算）",
            "数值或 N/A",
            "状态词",
            "前置（tier_ok 依据）",
            "证据锚点",
            "复现命令",
            "R1-B 签署",
        ],
        [
            [
                r["dim"],
                f"{r['metric']}<br>§6 最低要求：{r['requirement']}",
                r["value"],
                f"**{r['status']}**<br>{r['booleans']}",
                r["tier_note"],
                r["anchor"],
                r["repro"],
                r["signed_note"],
            ]
            for r in rows
        ],
    )
    out.append("")
    out.append("逐行注记（missing_premise 缺哪个前提、falsify 读数口径，全部在此点名）：")
    out.append("")
    for r in rows:
        for note in r["notes"]:
            out.append(f"- **{r['dim']}**：{note}")
    return out


# 判据表的固定说明块（口径与债务登记，逐字保留；抽出以免撑爆函数长度）。
_PRED_TABLE_NOTES = [
    "> ★ `falsify=✓` 但「归档重算」n=0 有效测量（全 missing_premise，如 `gen_correctness`）时，"
    "状态词仍是「已测量未证明」——这来自**冻结公式**（brief Step 2 / `claims.derive_status`："
    "只有 `not discriminating and not falsify_passed` 才判「未测量」），本表逐字执行、不改判。",
    "> ★ 该格里 mutation 取证测的是**判据对契约输入的敏感性**（取证夹具自带 gold ⇒ 能翻转），"
    "**不是主张的数值**；数值一侧在真实归档上仍全 missing_premise（P−1 盲标暂停中）。"
    "§1.1 表把「gold 前提不存在」列为未测量，与 Step 2 公式在这一格上口径不一致"
    "（证据：`docs/EVIDENCE_CHAIN.md` §1.1 ↔ 本 brief Step 2 冻结公式）—— "
    "属计划级缺口，已登记，待 Task 10 文档收口。",
    "> ★ 债的可见性（Task 7 Step 4b）：`tier 依据` 列里的 `TIER-DEBT-task3` 是**债标记**、"
    "不是依据 —— 标着它的判据，其 tier 值与 §1.3 的证据种类**不符**（`fn` 是确定性字符串/字段"
    "比较，按定义应为 tier 0/1，却写着 2），已登记为 Task 3 遗留债、本轮只登记不改。"
    "护栏 `7g` 通过的语义是「债名单与登记一致」，**不是**「债务已清偿」；"
    "清偿（改 tier）时 `7g` 会红，必须同步删除这条登记。",
    "",
]

_PRED_TABLE_HEADER = [
    "判据",
    "task",
    "tier",
    "tier 依据（白名单锚点／债标记）",
    "归档重算",
    "falsify",
    "tier_ok",
    "disc",
    "prov",
    "sign",
    "状态词",
]


def _pred_table_rows(ctx: dict[str, Any]) -> tuple[list[list[str]], list[str]]:
    """逐 task × 判据构造判据表行与 falsify 读数 notes。"""
    rows: list[list[str]] = []
    notes: list[str] = []
    for task in ctx["pred_tasks"]:
        recs = ctx["by_task"].get(task) or []
        pm, _pm_note = provenance_match_for(recs, ctx["cur_cv"], ctx["cur_golden"])
        for p in registry.for_task(task):
            st = ctx["pred_stats"][p.name]["block"]
            fp, fp_note = ctx["falsify_for"](p.name)
            tok, _tok_note = tier_ok_for(p.tier, ctx["boundary"], ctx["jitter"])
            disc = st.get("rate") is not None
            sg, _sg_note = signed_for((p.name,), ctx["sigs"])
            status = cl.derive_status(
                {},
                falsify_passed=fp,
                tier_ok=tok,
                discriminating=disc,
                provenance_match=pm,
                signed=sg,
            )
            rows.append(
                [
                    p.name,
                    task,
                    str(p.tier),
                    "+".join(p.tier_reason) or "（未申报）",
                    fmt_rate(st),
                    _mark(fp),
                    _mark(tok),
                    _mark(disc),
                    _mark(pm),
                    _mark(sg),
                    status,
                ]
            )
            notes.append(f"- `{p.name}`：{fp_note}")
    return rows, notes


def render_predicate_table(ctx: dict[str, Any]) -> list[str]:
    rows, notes = _pred_table_rows(ctx)
    out = ["## 判据级三态（registry 全量重算 · 诊断附表）", ""]
    out += _PRED_TABLE_NOTES
    out += _table(_PRED_TABLE_HEADER, rows)
    out += ["", "falsify_passed 逐判据读数（三条口径见页首）：", ""]
    out += notes
    return out


def render_falsify_table(ctx: dict[str, Any]) -> list[str]:
    rows = []
    for name, row in sorted(ctx["falsify"].items()):
        fp, _note = ctx["falsify_for"](name)
        rows.append(
            [
                name,
                ", ".join(row.get("inputs") or []),
                _mark(bool(row.get("all_flipped"))),
                _mark(bool(row.get("no_collateral"))),
                _mark(bool(row.get("no_raise"))),
                _mark(bool(row.get("baselines_pass"))),
                _mark(fp),
            ]
        )
    out = ["## mutation 取证消费结果（falsify_latest.json，inputs 已按口径③去重）", ""]
    out += _table(
        [
            "判据",
            "inputs（去重）",
            "all_flipped",
            "no_collateral",
            "no_raise",
            "baselines_pass",
            "falsify_passed",
        ],
        rows,
    )
    return out


def render_artifacts(ctx: dict[str, Any]) -> list[str]:
    cal_rel = CALIBRATION_PATH.relative_to(ROOT).as_posix()
    paths = [p.as_posix() for p in ctx["files"]] + [ctx["falsify_path"].as_posix(), cal_rel]
    out = ["## 工件状态（claims.artifact_status）", ""]
    rows = []
    for p in paths:
        a = cl.artifact_status(p)
        rows.append([a["path"], a["status"], a["superseded_by"] or "—", a["reason"] or "—"])
    out += _table(["path", "status", "superseded_by", "reason"], rows)
    out.append("")
    out.append("> 本 ledger 当前只登记 active；历史归档的 superseded 标注由 Task 10 收尾。")
    return out
