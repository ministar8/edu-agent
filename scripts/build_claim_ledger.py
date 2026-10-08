"""主张 ledger：三态状态词由代码算出（EVIDENCE_CHAIN.md §1.1；EFFECT_PLAN.md §6 门槛行）。

纪律（本脚本的硬约束）：
- 数值一律从归档 jsonl 经 registry predicates / metrics 重算，**代码里不出现手写百分数**——
  连 §6 的最低要求也不抄：运行时从冻结文档 `docs/EFFECT_PLAN.md` 解析。
- `missing_premise` 原样传播：值列显示 `N/A（rate=None; …）`并点名缺哪个前提，
  绝不折成 pass/fail。
- `falsify_passed=True` 表示「mutation 取证成功：判据对它声明的每个契约输入都敏感、
  无附带损伤、无抛异常」，**不是**「主张被证伪」（命名理由见 `claims.derive_status`）。
- 零 LLM 调用：全程本地纯计算。

用法：
    PYTHONIOENCODING=utf-8 PYTHONPATH=src uv run python scripts/build_claim_ledger.py \
        --records evals/results/task_eval/ec_r1_final_gate.jsonl --out evals/claims/ledger_draft.md
    PYTHONIOENCODING=utf-8 PYTHONPATH=src uv run python scripts/build_claim_ledger.py \
        --records <同上> --check
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from evaluation import provenance as prov_mod  # noqa: E402
from evaluation.task_eval import claims as cl  # noqa: E402
from evaluation.task_eval import metrics  # noqa: E402
from evaluation.task_eval import report as report_mod  # noqa: E402
from evaluation.task_eval.predicates import common as pc  # noqa: E402
from evaluation.task_eval.predicates import registry  # noqa: E402

CALIBRATION_PATH = ROOT / "evals" / "datasets" / "demo" / "calibration_30.jsonl"
SIGNATURES_PATH = ROOT / "evals" / "claims" / "r1b_signatures.json"
EFFECT_PLAN_PATH = ROOT / "docs" / "EFFECT_PLAN.md"

# R3 扫描对象（brief Step 5 点名四份）。本 Task 只报警不阻塞：历史文档的既有结论句
# 逐条补锚点是 Task 10 的收尾工作；本脚本不接入任何 CI。
_ORPHAN_SCAN_DOCS = ("docs/EXPERIMENTS.md", "docs/README.md", "README.md", "CLAUDE.md")

_ORPHAN_RE = re.compile(r"(应为空|逐位相同|全绿|一致|通过率|达线|不达线|\d+\.\d{3})")
_SOURCED_RE = re.compile(r"(证据：|复现：|`[a-z_]+ [\w\-./]+`|ledger\.md#)")

# §3 的嵌套 provenance 八键（缺一即视为「没记全」）。
_PROV_KEYS = (
    "code_version",
    "golden_sha256",
    "script",
    "argv",
    "model_refs",
    "sampling",
    "experiment_config_hash",
    "dependency_lock_hash",
)


def orphan_lines(md_path: Path) -> list[int]:
    """含可验证事实但 100 字符内找不到来源锚点的行。"""
    text = md_path.read_text(encoding="utf-8")
    bad = []
    for i, line in enumerate(text.splitlines(), start=1):
        if _ORPHAN_RE.search(line) and not _SOURCED_RE.search(line):
            bad.append(i)
    return bad


# ── 输入装载 ──────────────────────────────────────────────


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(ln) for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]


def _sha12(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:12]


def load_falsify(path: Path) -> dict[str, dict[str, Any]]:
    """读 falsify_latest.json；口径③：`inputs` 对多 op 输入有重复 ⇒ 消费前去重（保序）。"""
    if not path.exists():
        return {}
    rows = json.loads(path.read_text(encoding="utf-8"))
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        row = dict(row)
        row["inputs"] = list(dict.fromkeys(row.get("inputs") or []))
        out[str(row.get("predicate"))] = row
    return out


def load_signatures() -> dict[str, Any]:
    """R1-B 语义签署（§1.2：「已审待签 / 已签@版本」）。

    ★ 当前仓库不存在 `evals/claims/r1b_signatures.json` ⇒ 恒返回空 dict ⇒
      所有行的 `signed` 恒 False —— 这是诚实状态（待签），不是缺陷；
      人工对冻结契约逐判据签署后落该文件，本列自动变真。
      约定格式：{"<predicate_name>": {"signed_at_version": "<code_version>"}}
    """
    if not SIGNATURES_PATH.exists():
        return {}
    data = json.loads(SIGNATURES_PATH.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def calibration_human_scores(path: Path = CALIBRATION_PATH) -> list[float]:
    """真实校准集的人工分（跳过 # 注释行；human_score 为空的行不计）。"""
    out: list[float] = []
    for ln in path.read_text(encoding="utf-8").splitlines():
        if not ln.strip() or ln.startswith("#"):
            continue
        v = json.loads(ln).get("human_score")
        if v is not None:
            out.append(float(v))
    return out


def runs_and_case_ids(files: list[Path]) -> tuple[list[dict[str, float]], list[str]]:
    """每个归档文件视为一次运行：[{case_id: final_quality}]，供 `repeat_jitter` 用。"""
    by_run: list[dict[str, float]] = []
    ids: dict[str, None] = {}
    for f in files:
        run: dict[str, float] = {}
        for r in _load_jsonl(f):
            cid = str(r.get("case_id") or "")
            if not cid:
                continue
            ids.setdefault(cid, None)
            if r.get("final_quality") is not None:
                run[cid] = float(r["final_quality"])
        by_run.append(run)
    return by_run, sorted(ids)


def parse_gate_rows(path: Path = EFFECT_PLAN_PATH) -> list[tuple[str, str]]:
    """从冻结文档解析 §6 门槛行（维度, 最低要求原文）。门槛数字不进本脚本源码。"""
    text = path.read_text(encoding="utf-8")
    m = re.search(r"^## 6\.(.*?)^## 7\.", text, re.S | re.M)
    if not m:
        raise SystemExit(f"EFFECT_PLAN.md §6 表解析失败：{path}")
    rows: list[tuple[str, str]] = []
    for ln in m.group(1).splitlines():
        ln = ln.strip()
        if not ln.startswith("|"):
            continue
        cells = [c.strip() for c in ln.strip("|").split("|")]
        if len(cells) != 2 or cells[0] == "维度" or set(cells[0]) <= {"-", " "}:
            continue
        rows.append((cells[0], cells[1]))
    if not rows:
        raise SystemExit(f"EFFECT_PLAN.md §6 表为空：{path}")
    return rows


# ── 五个布尔量的计算 ──────────────────────────────────────


def falsify_evidence(
    pred_name: str, rows: dict[str, dict[str, Any]], *, archive_all_mp: bool
) -> tuple[bool, str]:
    """单判据的 `falsify_passed`（R1-A）+ 可读注记。遵守 Task 5 披露的三条口径：

    ① `all_flipped=False` 且基线全 pass ⇒ 读作 **partial**（存在形式覆盖、语义无操作的
      op，plan-mandated）——不得当 full，不得因此算 proven；
    ② `baselines_pass=False` 且该判据在归档上全 missing_premise ⇒ **预期**（gold 前提
      不存在，基线本就 pass 不了；P−1 盲标暂停中）——不是失败，但同样不得算 proven；
      不满足「全 missing_premise」却 baselines_pass=False ⇒ 意外，注记要求排查；
    ③ `inputs` 已在 `load_falsify` 去重。
    ★ `baselines_pass` 始终留在 falsify_passed 的合取里：不允许为「变绿」悄悄去掉。
    """
    row = rows.get(pred_name)
    if row is None:
        return False, "无 mutation 取证行（取证矩阵未覆盖该判据）⇒ falsify_passed=False"
    pred = registry.get(pred_name)
    inputs = set(row.get("inputs") or [])
    gaps = tuple(i for i in pred.contract_inputs if i not in inputs)
    ok = (
        bool(row.get("all_flipped"))
        and bool(row.get("no_collateral"))
        and bool(row.get("no_raise"))
        and bool(row.get("baselines_pass"))
        and not gaps
    )
    notes: list[str] = []
    if gaps:
        notes.append(f"R1-A 覆盖缺口（contract_inputs 未被 mutation 覆盖）：{gaps}")
    if not row.get("all_flipped"):
        if row.get("baselines_pass"):
            notes.append(
                "all_flipped=False ⇒ 读作 partial：部分声明 op 未翻转判据"
                "（形式覆盖、语义无操作，plan-mandated）——不得当 full，不得算 proven"
            )
        else:
            notes.append("all_flipped=False（基线本就 pass 不了，见 baselines_pass 注）")
    if not row.get("baselines_pass"):
        if archive_all_mp:
            notes.append(
                "baselines_pass=False 属**预期**：该判据在归档上全 missing_premise"
                "（gold 前提不存在，P−1 盲标暂停中），基线本就 pass 不了——"
                "不是失败，但不得算 proven"
            )
        else:
            notes.append("baselines_pass=False（意外：归档上存在已测值，需排查取证夹具）")
    if not row.get("no_collateral"):
        notes.append("no_collateral=False：存在附带损伤")
    if not row.get("no_raise"):
        notes.append("no_raise=False：判据在 mutation 下抛过异常")
    if ok:
        notes.append("all_flipped ∧ no_collateral ∧ no_raise ∧ baselines_pass ∧ 覆盖完整")
    return ok, "；".join(notes)


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


# ── 数值格式化（全部来自重算块，无字面量） ─────────────────


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
    return f"{r:.3f}（已测 n={block.get('n')}）"


def _count_block(k: int, n: int) -> dict[str, Any]:
    return {"rate": round(k / n, 4) if n else None, "n": n}


def _mark(flag: bool) -> str:
    return "✓" if flag else "✗"


# ── §6 门槛行的逐行重算 ───────────────────────────────────


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
        "tier": 2,
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
        "tier": max((p.tier for p in required), default=1),
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
        "tier": 1,
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
        "tier": max((p.tier for p in hard), default=1),
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
        "tier": max((p.tier for p in preds), default=1),
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
        "tier": 0,
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
        "tier": 0,
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
        "tier": 0,
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
        "tier": 0,
        "backing": (),
        "records": recs,
        "notes": [],
    }


def _row_no_archive(ctx: dict[str, Any]) -> dict[str, Any]:
    return {
        "metric": "本 ledger 无该维度的归档证据源（需服务验收/演示记录接入后才可算）",
        "block": None,
        "tier": 0,
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
    "Docker / TEI": _row_no_archive,
    "四任务链": _row_no_archive,
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
    tok, tok_note = tier_ok_for(int(spec["tier"]), ctx["boundary"], ctx["jitter"])
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
        f"scripts/build_claim_ledger.py --records {ctx['records_spec']}`"
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


# ── 渲染 ──────────────────────────────────────────────────


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


def render_predicate_table(ctx: dict[str, Any]) -> list[str]:
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
    out = ["## 判据级三态（registry 全量重算 · 诊断附表）", ""]
    out += _table(
        [
            "判据",
            "task",
            "tier",
            "归档重算",
            "falsify",
            "tier_ok",
            "disc",
            "prov",
            "sign",
            "状态词",
        ],
        rows,
    )
    out.append("")
    out.append("falsify_passed 逐判据读数（三条口径见页首）：")
    out.append("")
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


def build_ctx(records_spec: str, falsify_report: str) -> dict[str, Any]:
    files = [Path(p.strip()) for p in records_spec.split(",") if p.strip()]
    for f in files:
        if not f.exists():
            raise SystemExit(f"归档不存在：{f}")
    falsify_path = Path(falsify_report)
    records: list[dict[str, Any]] = []
    for f in files:
        records += _load_jsonl(f)
    if not records:
        raise SystemExit(f"归档为空：{records_spec}")
    by_task: dict[str, list[dict[str, Any]]] = {}
    for r in records:
        by_task.setdefault(str(r.get("task") or "unknown"), []).append(r)

    falsify_rows = load_falsify(falsify_path)
    sigs = load_signatures()
    boundary = cl.boundary_calibrated(calibration_human_scores())
    by_run, case_ids = runs_and_case_ids(files)
    jitter = cl.repeat_jitter(by_run, case_ids=case_ids)

    pred_tasks = sorted(t for t in by_task if registry.for_task(t))
    pred_stats: dict[str, dict[str, Any]] = {}
    for task in pred_tasks:
        recs = by_task[task]
        for p in registry.for_task(task):
            blk = pc.rate([p.fn(r) for r in recs])
            pred_stats[p.name] = {
                "block": blk,
                "all_mp": blk["n"] == 0 and blk["n_a_missing_premise"] > 0,
            }

    return {
        "records": records,
        "files": files,
        "by_task": by_task,
        "falsify": falsify_rows,
        "falsify_path": falsify_path,
        "sigs": sigs,
        "boundary": boundary,
        "jitter": jitter,
        "cur_cv": prov_mod.code_version(),
        "cur_golden": prov_mod.golden_sha256(),
        "gate_rows": parse_gate_rows(),
        "records_spec": records_spec,
        "pred_tasks": pred_tasks,
        "pred_stats": pred_stats,
        "falsify_for": lambda name: falsify_evidence(
            name,
            falsify_rows,
            archive_all_mp=bool(pred_stats.get(name, {}).get("all_mp")),
        ),
    }


def build_ledger(records_spec: str, falsify_report: str) -> str:
    ctx = build_ctx(records_spec, falsify_report)
    rows = compute_rows(ctx)
    counts = Counter(r["status"] for r in rows)
    n_prov = sum(1 for r in rows if _mark_prov(r))
    n_sign = sum(1 for r in rows if "sign✓" in r["booleans"])

    lines = [
        "# 主张 ledger（三态状态词 = 代码算出，EVIDENCE_CHAIN.md §1.1）",
        "",
        "> **状态词不是人写的**：`claims.derive_status` 由五个布尔量推导"
        "（falsify_passed / tier_ok / discriminating / provenance_match / signed），"
        "五个布尔量全部从归档、falsify 取证件、真实校准集与 registry 重算而来。",
        "> 本文档不含手写百分数：§6 最低要求运行时解析自冻结文档 `docs/EFFECT_PLAN.md`，"
        "数值一律从归档经 registry predicates / metrics 重算。",
        "> ★ `falsify_passed=True` = mutation 取证成功（判据对它声明的每个契约输入都敏感、"
        "无附带损伤、无抛异常），**不是**「主张被证伪」。",
        "> ★ falsify_latest.json 消费三口径（Task 5 披露）：① `all_flipped=False` 且基线全 "
        "pass ⇒ 读作 **partial**（形式覆盖、语义无操作，plan-mandated），不得当 full、不得算 "
        "proven；② 冻结名 `baselines_pass=False` 属**预期**（gold 未盲标、P−1 暂停，基线本就是 "
        "missing_premise）——不是失败，也不得算 proven；③ `inputs` 多 op 重复项已去重。",
        "> ★ missing_premise 全链原样传播（predicates → composite/rate → 本表）："
        "缺前提的行显示 `N/A（rate=None; …）`并在注记点名缺哪个前提，绝不折成 pass/fail。",
        f"> 本表汇总：{cl.CLAIM_PROVEN} {counts.get(cl.CLAIM_PROVEN, 0)} 行 / "
        f"{cl.CLAIM_MEASURED} {counts.get(cl.CLAIM_MEASURED, 0)} 行 / "
        f"{cl.CLAIM_UNMEASURED} {counts.get(cl.CLAIM_UNMEASURED, 0)} 行；"
        f"provenance_match=True {n_prov} 行；signed=True {n_sign} 行。",
        "",
        "## §6 门槛行（EFFECT_PLAN.md §6 逐条）",
        "",
    ]
    lines += render_main_table(rows)
    lines += ["", ""]
    lines += render_predicate_table(ctx)
    lines += ["", ""]
    lines += render_falsify_table(ctx)
    lines += ["", ""]
    lines += render_artifacts(ctx)
    lines.append("")
    return "\n".join(lines)


def _mark_prov(row: dict[str, Any]) -> bool:
    return "prov✓" in row["booleans"]


# ── --check：ledger 与重算一致性 + R3 孤立结论 ─────────────


def run_check(args: argparse.Namespace, text: str) -> int:
    red = False
    out = Path(args.out)
    if not out.exists():
        print(f"RED   ledger 不存在：{out}（先不带 --check 生成一次）")
        red = True
    else:
        existing = out.read_text(encoding="utf-8")
        if existing == text:
            print(f"PASS  ledger 与重算一致：{out}")
        else:
            red = True
            print(f"RED   ledger 与重算不一致：{out}")
            for i, (a, b) in enumerate(
                zip(existing.splitlines(), text.splitlines(), strict=False), 1
            ):
                if a != b:
                    print(f"      首个差异在第 {i} 行：")
                    print(f"      文档：{a[:120]}")
                    print(f"      重算：{b[:120]}")
                    break
    for doc in _ORPHAN_SCAN_DOCS:
        p = ROOT / doc
        if not p.exists():
            print(f"WARN  扫描对象不存在：{doc}")
            continue
        bad = orphan_lines(p)
        if bad:
            red = True
            print(f"RED   {doc} 孤立结论行（含可验证事实、无来源锚点）：{bad}")
        else:
            print(f"PASS  {doc} 无孤立结论行")
    print(
        "说明：R3 孤立结论在本 Task 只报警不阻塞（未接入任何 CI）——历史文档的既有结论句"
        "逐条补锚点是 Task 10 的收尾工作。"
    )
    return 1 if red else 0


def main() -> int:
    ap = argparse.ArgumentParser(description="主张 ledger 生成/校验（零 LLM，纯本地重算）")
    ap.add_argument("--records", required=True, help="效果归档 jsonl（可逗号分隔多份）")
    ap.add_argument("--falsify-report", default="evals/claims/falsify_latest.json")
    ap.add_argument("--out", default="evals/claims/ledger.md")
    ap.add_argument("--check", action="store_true", help="只校验：文档引用与重算是否一致")
    args = ap.parse_args()
    text = build_ledger(args.records, args.falsify_report)
    if args.check:
        return run_check(args, text)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    print(f"ledger 已写入 {out}")
    for r in compute_rows(build_ctx(args.records, args.falsify_report)):
        print(f"  {r['dim']:<14} {r['status']}（{r['booleans']}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
