"""A2 收尾：把人工盲标 gold 快照写进新一代归档的 generate 记录（2026-10-15）。

为什么新归档的 gen 记录取自 anchor5 而不是 ec_r1
------------------------------------------------
盲标的题干来自「出题修复后锚点⑤ 复测归档」`phase1_gen_anchor5_20261008.jsonl`
（code_version=6610ef1、prompt_set_version=12abf293c62a，#33 修复态）。
`ec_r1_final_gate.jsonl` 的 15 条 gen 记录是修复前 §6 整轮的产物
（code_version=eb8112f、prompt_set_version=2f485d2d7ef7）。
两者同 case_id 的**题干不同**（实测：gen-001 修复前问「直接映射 + 4 路组相联 +
冲突趋势」，修复后只问「4 路组相联 + 组索引 0x1A5C」；gen-009 修复前有完整题干，
修复后 generation_ok=false）⇒ 把盲标 gold 挂到修复前记录 = **假 gold**
（正是 P−1 明令禁止的「拿另一题的答案充当本题 gold」）。
⇒ 本脚本只做三件事：
  ① gen 记录整体换成 anchor5 的对应记录（回复/工具/失败原因等运行期字段原样）；
  ② gold 快照替换为**现行 dataset** 的 gold（走 `load_demo` + `asdict`，与 runner
     落盘同一条代码路径；schema 与 `task_eval sanity` 校验的是同一份）；
  ③ 其余 51 条（qa/grade/verify/memory）从 ec_r1 **逐字节继承**。
判据数值**不在此脚本写** —— 由 `task_eval backfill`（唯一合法写回入口）重算。

运行期 provenance（code_version / prompt_set_version / golden_sha256 /
顶层 gold_status / date / judge）一律**不动**：本归档是「重算式新一代」而非重跑
产物，指纹字段保留运行期值；与现行 gold 的最终对齐由 C1 全量重跑完成。

用法::

    PYTHONIOENCODING=utf-8 PYTHONPATH=src .venv/Scripts/python.exe scripts/lib/gold_blindlabel_apply_20261015.py
    # 产出 evals/results/task_eval/ec_r2_goldinjected_20261015.jsonl（gold 已注入、判据仍是旧值）
    # 然后由官方入口重算判据：
    PYTHONIOENCODING=utf-8 PYTHONPATH=src .venv/Scripts/python.exe -m evaluation.task_eval backfill \
        --records evals/results/task_eval/ec_r2_goldinjected_20261015.jsonl \
        --out evals/results/task_eval/ec_r2_final_gate_20261015.jsonl
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

EC_R1 = ROOT / "evals/results/task_eval/ec_r1_final_gate.jsonl"
ANCHOR5 = ROOT / "evals/results/task_eval/phase1_gen_anchor5_20261008.jsonl"
OUT = ROOT / "evals/results/task_eval/ec_r2_goldinjected_20261015.jsonl"


def _load(path: Path) -> list[dict]:
    return [
        json.loads(ln)
        for ln in path.read_text(encoding="utf-8").splitlines()
        if ln.strip() and not ln.lstrip().startswith("#")
    ]


def main() -> int:
    ec_r1 = _load(EC_R1)
    anchor5 = _load(ANCHOR5)

    # 现行 dataset gold（runner 同路径：load_demo → asdict(case.gold)）
    from dataclasses import asdict

    from evaluation.task_eval.cases import load_demo

    demo_gold = {c.case_id: asdict(c.gold) for c in load_demo("generate")}

    an_by_id = {str(r["case_id"]): r for r in anchor5}
    ec_gen_ids = [str(r["case_id"]) for r in ec_r1 if r.get("task") == "generate"]
    assert len(ec_gen_ids) == 15 and len(an_by_id) == 15, (len(ec_gen_ids), len(an_by_id))
    assert set(ec_gen_ids) == set(an_by_id), "case_id 集合不一致"
    assert all(str(r["task"]) == "generate" for r in anchor5), "anchor5 混入非 gen 记录"

    out: list[dict] = []
    n_gen = 0
    for rec in ec_r1:
        if str(rec.get("task") or "") != "generate":
            out.append(rec)  # 51 条原样继承
            continue
        cid = str(rec["case_id"])
        new_rec = dict(an_by_id[cid])  # anchor5 运行期字段（回复/工具/失败原因…）
        gold = demo_gold[cid]
        # gold 快照：现行 dataset（含 gold_source_ref / gold_answer_status 键）
        new_rec["gold"] = gold
        # 断言：V0 ① 依赖的键必须真实存在（has_path 只查键存在性，null 也算存在）
        assert "gold_source_ref" in gold and "gold_answer_status" in gold, cid
        assert set(gold["gold_source_ref"]) == set(gold["gold_answer_status"]), cid
        out.append(new_rec)
        n_gen += 1

    assert len(out) == 66, len(out)
    n_present = sum(
        1
        for r in out
        if r.get("task") == "generate"
        and (r["gold"].get("gold_answer_status") or {}).get("gold_answer") == "present"
    )
    print(f"组成：66 条（gen {n_gen} 条换自 anchor5 并注入 gold，其中 present {n_present} 条）")

    # ★ newline=""：禁 text 模式换行翻译（Windows 会把 \n 写成 \r\n，破坏归档行尾风格）
    OUT.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in out) + "\n",
        encoding="utf-8",
        newline="",
    )
    print(f"写出 → {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
