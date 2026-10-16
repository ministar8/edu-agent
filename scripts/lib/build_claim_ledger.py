"""主张 ledger：三态状态词由代码算出（EVIDENCE_CHAIN.md §1.1；EFFECT_PLAN.md §6）。"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
# ★ 本包拆出的 `_ledger_common/_ledger_rows/_ledger_render` 与本文件同目录 ⇒ 放上路径
#   供裸名 import（`evidence_chain_gate` 以 `import lib.build_claim_ledger` 取用）。
sys.path.insert(0, str(ROOT / "scripts" / "lib"))

from _ledger_common import (  # noqa: E402
    _ORPHAN_RE,
    _ORPHAN_SCAN_DOCS,
    _SOURCED_RE,
    CALIBRATION_PATH,
    EFFECT_PLAN_PATH,
    ROOT,
    SIGNATURES_PATH,
    _load_jsonl,
)
from _ledger_render import (  # noqa: E402
    render_artifacts,
    render_falsify_table,
    render_main_table,
    render_predicate_table,
)

# ★ re-export：`evidence_chain_gate` 以 `bcl.X` 取用 tier 常量与行构建器注册表。
from _ledger_rows import (  # noqa: E402  # noqa: E402, F401
    _ROW_BUILDERS,
    DERIVED_TIER_DIMS,
    LITERAL_TIER_REASONS,
    compute_rows,
)

from evaluation import provenance as prov_mod  # noqa: E402
from evaluation.task_eval import claims as cl  # noqa: E402
from evaluation.task_eval import schema_gate  # noqa: E402
from evaluation.task_eval.predicates import common as pc  # noqa: E402
from evaluation.task_eval.predicates import registry  # noqa: E402

__all__ = ["DERIVED_TIER_DIMS", "LITERAL_TIER_REASONS", "_ROW_BUILDERS"]


def orphan_lines(md_path: Path) -> list[int]:
    """含可验证事实但 100 字符内找不到来源锚点的行。"""
    text = md_path.read_text(encoding="utf-8")
    bad = []
    for i, line in enumerate(text.splitlines(), start=1):
        if _ORPHAN_RE.search(line) and not _SOURCED_RE.search(line):
            bad.append(i)
    return bad


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


def falsify_evidence(
    pred_name: str, rows: dict[str, dict[str, Any]], *, archive_all_mp: bool
) -> tuple[bool, str]:
    """单判据的 `falsify_passed`（R1-A）+ 可读注记。遵守 Task 5 披露的三条口径：

    ① `all_flipped=False` 且基线全 pass ⇒ 读作 **partial**（存在形式覆盖、语义无操作的
      op，plan-mandated）——不得当 full，不得因此算 proven；
    ② `baselines_pass=False` 且该判据在归档上全 missing_premise ⇒ **预期**（缺前提 ⇒
      基线本就 pass 不了；缺前提的根因逐判据不同——gold 未填 / 来源不完整 / 机械判据
      不适用于该题型；P−1 已填 gold 的判据也可能因适用域结构性不可测）——不是失败，
      但同样不得算 proven；
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
                "（缺前提 ⇒ 基线本就 pass 不了；缺哪个前提见该判据 contract_inputs "
                "与 ledger 缺前提明细），——不是失败，但不得算 proven"
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


def _record_paths(records_spec: str) -> list[Path]:
    files = [Path(p.strip()) for p in records_spec.split(",") if p.strip()]
    for f in files:
        if not f.exists():
            raise SystemExit(f"归档不存在：{f}")
    return files


def load_records(records_spec: str) -> list[dict[str, Any]]:
    """`--records` 逗号分隔的全部归档记录（V0 段与 ledger 用同一份，避免两套现实）。"""
    return [r for f in _record_paths(records_spec) for r in _load_jsonl(f)]


def build_ctx(records_spec: str, falsify_report: str) -> dict[str, Any]:
    files = _record_paths(records_spec)
    falsify_path = Path(falsify_report)
    records: list[dict[str, Any]] = [r for f in files for r in _load_jsonl(f)]
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
        "proven；② 冻结名 `baselines_pass=False` 属**预期**（判据在归档上全 missing_premise "
        "⇒ 基线本就是 missing_premise；缺前提的根因逐判据不同，见逐行注记）——不是失败，"
        "也不得算 proven；③ `inputs` 多 op 重复项已去重。",
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


def _check_ledger_consistency(args: argparse.Namespace, text: str) -> bool:
    """第 1 段：ledger 文档与重算逐字一致。返回 True = 红灯。"""
    out = Path(args.out)
    if not out.exists():
        print(f"FAIL  ledger 不存在：{out}（先不带 --check 生成一次）")
        return True
    existing = out.read_text(encoding="utf-8")
    if existing == text:
        print(f"PASS  ledger 与重算一致：{out}")
        return False
    print(f"FAIL  ledger 与重算不一致：{out}")
    for i, (a, b) in enumerate(zip(existing.splitlines(), text.splitlines(), strict=False), 1):
        if a != b:
            print(f"      首个差异在第 {i} 行：")
            print(f"      文档：{a[:120]}")
            print(f"      重算：{b[:120]}")
            break
    return True


def _check_orphan_conclusions() -> bool:
    """第 2 段：R3 扫描对象里不得有「含可验证事实、无来源锚点」的结论行。返回 True = 红灯。"""
    red = False
    for doc in _ORPHAN_SCAN_DOCS:
        p = ROOT / doc
        if not p.exists():
            print(f"WARN  扫描对象不存在：{doc}")
            continue
        bad = orphan_lines(p)
        if bad:
            red = True
            print(f"FAIL  {doc} 孤立结论行（含可验证事实、无来源锚点）：{bad}")
        else:
            print(f"PASS  {doc} 无孤立结论行")
    return red


def _check_v0_schema(records: list[dict[str, Any]]) -> bool:
    """第 3 段前半：§8① schema 缺键（逐条可归因）+ 答案键已知错误（分开统计）。"""
    red = False
    stats = schema_gate.missing_key_report(records)
    gaps = schema_gate.contract_gaps(records)
    groups = schema_gate.gap_groups(gaps)
    n_key_errors = schema_gate.confirmed_answer_key_error_count(records)
    if groups:
        red = True
        print(
            f"FAIL  V0 ① schema 缺键：{len(groups)} 组（字段×判据） / {stats.n_pairs} 处"
            f"（涉及 {stats.n_records} 条记录"
            f"，全归档 {len(records)} 条中；处 = 记录×缺键对数 ⇒ 一条记录缺两个键算两处）"
            "—— 逐条可归因（§4.4.7 第 4 条：缺什么字段、影响哪个 gold 字段与判据、"
            "旧归档缺字段还是新记录违反 schema、能否靠补真实证据解决），**禁止**自动回填"
        )
        for g in groups:
            print(
                f"      ×{g.n_old_archive_missing + g.n_new_record_violation}  "
                f"缺 {g.missing_field} × 判据 {g.predicate}"
                f" × 受影响 gold 字段 {g.gold_field or '—（非 gold 地址）'}"
                f" × 旧归档缺字段 {g.n_old_archive_missing} / 新记录违反 schema"
                f" {g.n_new_record_violation}"
                f" × 可补真实证据={'是' if g.resolvable_by_evidence else '否'}"
                f"（{schema_gate._GAP_RESOLUTION.get(g.missing_field, schema_gate._GAP_RESOLUTION['_default'])}）"
            )
            print(f"          示例 case：{', '.join(str(e) for e in g.examples)}")
    else:
        print("PASS  V0 ① 判据声明的 contract_inputs 在归档里键真实存在")
    # ★ §4.4.7 第 2 条：缺字段红与「答案键已知错误」**分开统计**（9q 钉死分界）。
    if n_key_errors:
        red = True
        print(
            f"FAIL  V0 ①b 答案键已知错误（与缺字段分开统计）：{n_key_errors} 处 —— 见 §4.4.5 扩查规程"
        )
    else:
        print(
            "      答案键已知错误（与缺字段**分开统计**，§4.4.7-2）：0 处"
            " —— 上面的缺字段红只说明『状态没登记』，不说明『键已确认错误』；"
            "已确认错键的唯一合法来源是带 answer_key_error:* 原因码的人工登记（今天没有）"
        )
    # ★ 评审 I-4（= 偏差 D5）：跳过多少条、为什么跳过，**必须明说**。
    print(
        f"      跳过 {stats.n_skipped_not_applicable} 条不适用行（不计入上面的缺键）："
        "qa/grade 在 registry 里没有任何判据 ⇒ 无四态项，`item_reasons` 的唯一生产者"
        " `cli._backfill`（cli.py）只在 `for pred in registry.for_task(task)` 内写这个键"
        " ⇒ 这些行无论怎么 reanalyse 都不会绿，把它们当红灯 = 先天无法清偿的红灯"
        "（正是逼人关掉门禁的成因）。真缺口一条未丢：有判据的任务照旧逐条查。"
    )
    return red


def _check_v0_unmeasurable(records: list[dict[str, Any]]) -> bool:
    """第 3 段后半：§8② required 判据在该归档上全未测量的任务。返回 True = 红灯。"""
    unmeasurable = schema_gate.unmeasurable_tasks(records)
    if not unmeasurable:
        print("PASS  V0 ② 无「required 判据全未测量」的任务 ⇒ 门槛行未被未测量项污染")
        return False
    print(
        "FAIL  V0 ② required 判据在该归档上一次都没测出值（全 missing_premise）"
        "⇒ 相关 claim = 未测量，**禁止**进入正式效果章的门槛行（§8②、§4.2 事故的拦网）"
    )
    for task, names in sorted(unmeasurable.items()):
        n_task = sum(1 for r in records if str(r.get("task") or "") == task)
        for name in names:
            print(
                f"      {task}/{name}: missing_premise（该任务 {n_task} 条归档全部缺前提 ⇒ n_measured=0）"
            )
    return True


def run_check(args: argparse.Namespace, text: str, records: list[dict[str, Any]]) -> int:
    """三段各自判定：① ledger 一致性 ② R3 孤立结论 ③ V0 拦截（§8①/§8②）。

    ★ 退出码仍是「任一段红 ⇒ 1」，但**每段单独打印自己的 PASS/FAIL**：
      混在一起会把「V0 尚未清偿」（判据全 missing_premise + 归档缺 provenance/item_reasons）
      误读成「ledger 算错了」—— 前者是计划里等待办的事实，后者会让人怀疑整条证据链。
      ★ generate 的 gold 已由 P−1 盲标填写（2026-10-15，13 present + gen-005
        incomplete_source + gen-009 missing_key）；剩余 V0 ② 红的根因是判据结构性不可测
        （人工可判定性结论通道 / 纯选择题适用域 / 难度行中文映射缺失），不是 gold 未填。
    """
    print("── 第 1 段【ledger 一致性】文档 == 重算 ──")
    seg1_red = _check_ledger_consistency(args, text)
    print("── 第 2 段【R3 孤立结论】文档结论句必须带来源锚点 ──")
    seg2_red = _check_orphan_conclusions()
    print("── 第 3 段【V0 拦截】schema 完整性 + 未测量判据禁进门槛（§8①/§8②）──")
    seg3a = _check_v0_schema(records)
    seg3b = _check_v0_unmeasurable(records)
    seg3_red = seg3a or seg3b

    for title, red in (
        ("第 1 段【ledger 一致性】", seg1_red),
        ("第 2 段【R3 孤立结论】", seg2_red),
        ("第 3 段【V0 拦截】", seg3_red),
    ):
        print(f"{'FAIL' if red else 'PASS'}  {title}")
    print(
        "说明：① 第 2 段在本 Task 只报警不阻塞（未接入任何 CI）——历史文档的既有结论句"
        "逐条补锚点是 Task 10 的收尾工作。"
    )
    print(
        "      ② 第 3 段红 = **V0 尚未清偿**（判据全 missing_premise + 归档缺 provenance/"
        "item_reasons；generate 的 gold 已由 P−1 盲标填写，剩余未测根因是判据结构性不可测，"
        "逐条见上面的 V0 ② 输出），不是 ledger 算错了；这两件事分属不同段，别混读。"
        "本轮的正确结果就是这一段红 —— 它正是本计划的目的（§8：未证明的东西不得当成绩）。"
    )
    return 1 if (seg1_red or seg2_red or seg3_red) else 0


def main() -> int:
    ap = argparse.ArgumentParser(description="主张 ledger 生成/校验（零 LLM，纯本地重算）")
    ap.add_argument("--records", required=True, help="效果归档 jsonl（可逗号分隔多份）")
    ap.add_argument("--falsify-report", default="evals/claims/falsify_latest.json")
    ap.add_argument("--out", default="evals/claims/ledger.md")
    ap.add_argument("--check", action="store_true", help="只校验：文档引用与重算是否一致")
    args = ap.parse_args()
    text = build_ledger(args.records, args.falsify_report)
    if args.check:
        # V0 先于「文档 == 重算」？不：三段一起判定、各段各自表态（见 run_check 的 docstring），
        # 这样读者既能看到 ledger 是否漂移，也能看到 V0 是否清偿。
        return run_check(args, text, load_records(args.records))
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    print(f"ledger 已写入 {out}")
    for r in compute_rows(build_ctx(args.records, args.falsify_report)):
        print(f"  {r['dim']:<14} {r['status']}（{r['booleans']}）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
