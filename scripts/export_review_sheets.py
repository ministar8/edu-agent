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


class SheetConflict(RuntimeError):
    """旧表里有一行**不在本次导出集合里** ⇒ 直接重跑会把它冲掉。调用方必须显式 `--force`。"""


def _read_sheet(path: Path) -> dict[str, dict[str, Any]]:
    """读已有审核表的行（跳过 `#` 注释行）；文件不存在返回空 dict。"""
    if not path.exists():
        return {}
    out: dict[str, dict[str, Any]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        obj = json.loads(line)
        cid = str(obj.get("case_id") or "")
        if cid:
            out[cid] = obj
    return out


def _get_dotted(row: dict[str, Any], dotted: str) -> Any:
    cur: Any = row
    for part in dotted.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def _set_dotted(row: dict[str, Any], dotted: str, value: Any) -> None:
    parts = dotted.split(".")
    cur = row
    for part in parts[:-1]:
        cur = cur.setdefault(part, {})
    cur[parts[-1]] = value


def merge_preserving_human(
    old_rows: dict[str, dict[str, Any]],
    new_rows: list[dict[str, Any]],
    human_paths: list[str],
    fill_if_missing: list[str] | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    """重跑导出时**保留人工填过的值**，并把会被丢掉的行报出来（#37）。

    ★ 为什么必须有这一步：`export_calibration` 原先无条件写 `"human_score": None`，
      而 `calibration_30.jsonl` 的 30 条 human_score 是**人工标注**（judge 校准的
      exact / within_1 / mae / spearman 四个数就是从它算的）。⇒ 按文档里那句默认命令
      重跑一次，就把已发表的标注连同论文依据一起清空，而且工具照旧打印成功。
    ★ 规则是「**表里的非空值一律优先于派生值**」，不是「只在派生值为空时才保留」——
      因为 `gold_review` 的 grade `human_score` 是**机械预填**的（有派生值），
      而审核人改的正是这个字段：若按后者判，「他把 100 改成 0」会在重跑时被预填值冲回去。
      派生值只是起始猜测，**表才是人写的那一份**。
    - 派生列（`system_output` / `llm_score`）不在 human_paths 里 ⇒ 照常刷新，
      不会把过期的系统输出留在表里。
    - `dropped` = 旧表里有、本次集合里没有的 case_id ⇒ 非空就必须中止（除非 `--force`），
      **且在打开文件之前判定** —— 先 `open(path, "w")` 再决定就已经把数据删了。
    """
    fill = fill_if_missing or []
    new_ids = {str(r.get("case_id")) for r in new_rows}
    merged: list[dict[str, Any]] = []
    for row in new_rows:
        old = old_rows.get(str(row.get("case_id")))
        if old:
            for path_key in human_paths:
                if _get_dotted(old, path_key) is not None:
                    _set_dotted(row, path_key, _get_dotted(old, path_key))
            # 派生列走另一条规则：**新值有就用新的（要能刷新），只在本次拿不到时沿用旧的**。
            # 不这么做的后果很具体：`--records` 的默认文件本机不存在 ⇒ 不加这条就会把
            # 已发表表里的 llm_score 整列清空，而 judge 校准是 llm_score × human_score 成对算的。
            for path_key in fill:
                if _get_dotted(row, path_key) is None and _get_dotted(old, path_key) is not None:
                    _set_dotted(row, path_key, _get_dotted(old, path_key))
        merged.append(row)
    dropped = sorted(cid for cid in old_rows if cid not in new_ids)
    return merged, dropped


def export_calibration(
    cases: list[TaskCase],
    records: dict[str, dict[str, Any]],
    out_dir: Path,
    force: bool = False,
) -> Path:
    """A 表：30 条，人工填 `human_score`（0–5）。llm_score 有 record 就预填。"""
    picked: list[TaskCase] = []
    for task, quota in CALIB_QUOTA.items():
        picked.extend([c for c in cases if c.task == task][:quota])

    path = out_dir / "calibration_30.jsonl"
    old_rows = _read_sheet(path)
    new_rows: list[dict[str, Any]] = []
    for c in picked:
        rec = records.get(c.case_id, {})
        new_rows.append(
            {
                "case_id": c.case_id,
                "task": c.task,
                "task_mode": c.task_mode,
                "query": c.query,
                "system_output": rec.get("reply", ""),
                "gold": _gold_brief(c),
                "rubric": rubric_for(c.task),
                "llm_score": rec.get("final_quality"),  # 无 record 时为 null，待补
                "human_score": None,  # ← 人工填 0–5（旧值由 merge 保留）
                "judge": rec.get("judge", ""),
                "notes": "" if rec.get("reply") else "系统输出缺失：需额度恢复后重跑该 case",
            }
        )
    rows, dropped = merge_preserving_human(
        old_rows, new_rows, ["human_score"], fill_if_missing=["llm_score"]
    )
    if dropped and not force:
        raise SheetConflict(
            f"{path.name} 里有 {len(dropped)} 行不在本次导出集合（{dropped}）⇒ 重跑会把它们冲掉。"
            "确认要冲掉就加 --force，否则请用 --out-dir 导到别处"
        )
    with open(path, "w", encoding="utf-8") as f:
        f.write("# Judge Calibration · 30 条（人工填 human_score 0–5；llm_score 由 judge 产出）\n")
        f.write("# 通过阈值：exact>=0.60  within_1>=0.90  mae<=0.50  spearman>=0.70\n")
        f.write("# 填完跑：python -m evaluation.task_eval calibrate --input <本文件>\n")
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return path


def export_gold_review(cases: list[TaskCase], out_dir: Path, force: bool = False) -> Path:
    """B 表：只含需人工确认的 gold 字段（Generate 难度/答案、Grade human_score 0–100）。

    ★ 2026-10-06 追加：Grade 需**校验 `answer_key`** —— 实测源数据
      **24% 缺失（`answer_key: null`）+ ≥20% 错误**（逐条人工核验 3 例，3/3 是源数据错）。
      不校验它，`score_tolerance` 测的是「gold 质量」而非「系统能力」。
    """
    path = out_dir / "gold_review.jsonl"
    human_paths = sorted(
        {f"review_fields.{name}" for fields in GOLD_REVIEW_FIELDS.values() for name in fields}
    )
    new_rows: list[dict[str, Any]] = []
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
        new_rows.append(payload)
    # ★ 判定在打开文件之前 —— 先 `open(path, "w")` 就已经把审核人写进去的东西删了
    rows, dropped = merge_preserving_human(_read_sheet(path), new_rows, human_paths)
    if dropped and not force:
        raise SheetConflict(
            f"{path.name} 里有 {len(dropped)} 行不在本次导出集合（{dropped}）⇒ 重跑会把它们冲掉。"
            "确认要冲掉就加 --force，否则请用 --out-dir 导到别处"
        )
    with open(path, "w", encoding="utf-8") as f:
        f.write("# Gold 审核（**不是** judge calibration）\n")
        f.write("# Grade 的 human_score 为 0–100（选择题已按 answer_key 机械预填，请抽查）\n")
        f.write(
            "# ★ Grade 的 answer_key 来自扫描数据，**必须人工校验**（实测缺失 24%、错误 ≥20%）\n"
        )
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"  gold_review: {len(rows)} 条（{path.name}）")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="导出 judge 校准表与 gold 审核表")
    parser.add_argument("--records", default=str(DEFAULT_RECORDS))
    parser.add_argument("--out-dir", default=str(DEMO_DIR))
    parser.add_argument(
        "--force",
        action="store_true",
        help="允许冲掉旧表里本次集合之外的行（默认**不允许** —— 见 #37）",
    )
    args = parser.parse_args(argv)

    out_dir = Path(args.out_dir)
    # ★ #37 的处置办法就是「导到别处去」，所以那条路必须真的走得通：目录不存在就建，
    #   否则安全的那个选项反而先 FileNotFoundError。
    out_dir.mkdir(parents=True, exist_ok=True)
    cases = load_demo()
    records = load_records(Path(args.records))
    print(f"demo case {len(cases)} 条 · 已有 record {len(records)} 条")
    try:
        cal = export_calibration(cases, records, out_dir, force=args.force)
        prefilled = sum(1 for c in cases if c.case_id in records)
        print(
            f"  calibration_30: {sum(CALIB_QUOTA.values())} 条（{cal.name}）"
            f"· 其中 {prefilled} 条有系统输出"
        )
        export_gold_review(cases, out_dir, force=args.force)
    except SheetConflict as e:
        # ★ 用退出码说话：这不是「跑成功了但少了点东西」
        print(f"❌ 中止（未写出任何文件）：{e}", file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
