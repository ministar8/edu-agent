"""导出两张**互不混用**的复核表（决策 #4/#5，用户 2026-10-05 明确要求分开）。

    A. calibration_30.jsonl  —— Judge 校准：人工填 `human_score`（0–5）
    B. gold_review.jsonl     —— Gold 审核：Generate 难度/答案、Grade human_score（0–100）

★ 为什么必须分开：`final_quality`(0–5) 测的是「LLM judge 能否替代人工质量评分」；
  而 `human_score`(0–100) 是**批改任务的 gold**，属另一件事。
  混在一张表里，会把「judge 不准」与「gold 没标」两类问题搅成一条。

用法::

    PYTHONPATH=src uv run python scripts/export_review_sheets.py
    PYTHONPATH=src uv run python scripts/export_review_sheets.py --records evals/results/task_eval/0a_smoke_valid.jsonl
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from evaluation.task_eval.cases import TaskCase, load_demo  # noqa: E402
from evaluation.task_eval.judge import rubric_for  # noqa: E402

DEMO_DIR = ROOT / "evals" / "datasets" / "demo"
DEFAULT_RECORDS = ROOT / "evals" / "results" / "task_eval" / "0a_smoke_valid.jsonl"

# 校准集配额（共 30，**三类各 1/3**）——
# ★ 2026-10-05 用户拍板：**Verify 与 Memory 都不进 0–5 校准**。
#   - Verify：其低分反映「能力不存在」而非 judge 判断力，纳入会污染校准结论；
#     它继续留在 0B baseline 作为 Phase 1 的头号证据（exam_hit@5=0.8 而题号输出=0）。
#   - Memory：判据是 `retrieved ∧ used ∧ correct` 三维，不是 QA rubric。
#   并且**不是简单删掉**（8/8/7/7 → 23 条），而是重排为 10/10/10，
#   避免 calibration 结果受类别比例影响。
CALIB_QUOTA: dict[str, int] = {"qa": 10, "generate": 10, "grade": 10}
GOLD_REVIEW_FIELDS: dict[str, tuple[str, ...]] = {
    "generate": ("expected_difficulty", "gold_answer"),
    "grade": ("human_score",),
}


def load_records(path: Path) -> dict[str, dict[str, Any]]:
    """读已有 record（用于预填 reply / llm_score）。文件不存在则返回空。"""
    if not path.exists():
        print(f"（未找到已有 record：{path} —— reply/llm_score 将留空，待额度恢复后补）")
        return {}
    out: dict[str, dict[str, Any]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        obj = json.loads(line)
        out[str(obj.get("case_id"))] = obj
    return out


def _gold_brief(case: TaskCase) -> dict[str, Any]:
    """给标注者看的 gold 摘要（只放与判分相关的字段）。"""
    g = case.gold
    brief: dict[str, Any] = {}
    for name in ("expected_kp", "expected_difficulty", "expected_question_ids", "reference"):
        value = getattr(g, name, None)
        if value not in (None, "", []):
            brief[name] = value
    return brief


def export_calibration(
    cases: list[TaskCase], records: dict[str, dict[str, Any]], out_dir: Path
) -> Path:
    """A 表：30 条，人工填 `human_score`（0–5）。llm_score 有 record 就预填。"""
    picked: list[TaskCase] = []
    for task, quota in CALIB_QUOTA.items():
        picked.extend([c for c in cases if c.task == task][:quota])

    path = out_dir / "calibration_30.jsonl"
    with open(path, "w", encoding="utf-8") as f:
        f.write("# Judge Calibration · 30 条（人工填 human_score 0–5；llm_score 由 judge 产出）\n")
        f.write("# 通过阈值：exact>=0.60  within_1>=0.90  mae<=0.50  spearman>=0.70\n")
        f.write("# 填完跑：python -m evaluation.task_eval calibrate --input <本文件>\n")
        for c in picked:
            rec = records.get(c.case_id, {})
            f.write(
                json.dumps(
                    {
                        "case_id": c.case_id,
                        "task": c.task,
                        "task_mode": c.task_mode,
                        "query": c.query,
                        "system_output": rec.get("reply", ""),
                        "gold": _gold_brief(c),
                        "rubric": rubric_for(c.task),
                        "llm_score": rec.get("final_quality"),  # 无 record 时为 null，待补
                        "human_score": None,  # ← 人工填 0–5
                        "judge": rec.get("judge", ""),
                        "notes": ""
                        if rec.get("reply")
                        else "系统输出缺失：需额度恢复后重跑该 case",
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
    return path


def export_gold_review(cases: list[TaskCase], out_dir: Path) -> Path:
    """B 表：只含需人工确认的 gold 字段（Generate 难度/答案、Grade human_score 0–100）。

    ★ 2026-10-06 追加：Grade 需**校验 `answer_key`** —— 实测源数据
      **24% 缺失（`answer_key: null`）+ ≥20% 错误**（逐条人工核验 3 例，3/3 是源数据错）。
      不校验它，`score_tolerance` 测的是「gold 质量」而非「系统能力」。
    """
    path = out_dir / "gold_review.jsonl"
    rows = 0
    with open(path, "w", encoding="utf-8") as f:
        f.write("# Gold 审核（**不是** judge calibration）\n")
        f.write("# Grade 的 human_score 为 0–100（选择题已按 answer_key 机械预填，请抽查）\n")
        f.write(
            "# ★ Grade 的 answer_key 来自扫描数据，**必须人工校验**（实测缺失 24%、错误 ≥20%）\n"
        )
        for c in cases:
            fields = GOLD_REVIEW_FIELDS.get(c.task)
            if not fields:
                continue
            payload: dict[str, Any] = {
                "case_id": c.case_id,
                "task": c.task,
                "query": c.query,
                "review_fields": {name: getattr(c.gold, name, None) for name in fields},
                "notes": c.notes,
            }
            if c.task == "grade":
                payload["_ref"] = {
                    "question_stem": c.gold.question_stem,
                    "student_answer": c.gold.student_answer,
                    "full_marks": c.gold.full_marks,
                    "source_question_id": c.notes.split("（")[0] if c.notes else "",
                    "source_answer_key（扫描数据，待校验）": (
                        c.notes.split("answer_key=")[1].split("；")[0]
                        if "answer_key=" in (c.notes or "")
                        else ""
                    ),
                }
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
            rows += 1
    print(f"  gold_review: {rows} 条（{path.name}）")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="导出 judge 校准表与 gold 审核表")
    parser.add_argument("--records", default=str(DEFAULT_RECORDS))
    parser.add_argument("--out-dir", default=str(DEMO_DIR))
    args = parser.parse_args(argv)

    out_dir = Path(args.out_dir)
    cases = load_demo()
    records = load_records(Path(args.records))
    print(f"demo case {len(cases)} 条 · 已有 record {len(records)} 条")

    cal = export_calibration(cases, records, out_dir)
    prefilled = sum(1 for c in cases if c.case_id in records)
    print(
        f"  calibration_30: {sum(CALIB_QUOTA.values())} 条（{cal.name}）· 其中 {prefilled} 条有系统输出"
    )
    export_gold_review(cases, out_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
