"""Verify 探针 case：验证「能力不存在」的结论是否只是**模板问法**造成的。

背景
----
Phase 0B 的 15 条 Verify case **全是同一个模板**（`「X考过哪些真题？」`），
系统 100% 走到出题路径。但**不能排除「是这个问法触发了出题」**：
若换自然问法系统就能正确列出真题，那结论应是「模板问法特殊」而非「能力不存在」。

设计（隔离变量）
----------------
- **同一考点 × 5 种问法** ⇒ 隔离「问法」的影响（考点固定）。
- 选 2 个**不同学科**的考点（ds / net）⇒ 顺带看是否与学科相关。
- 其中第 1 种问法 = 现有模板，作为**组内对照**。

用法::

    PYTHONPATH=src uv run python scripts/build_verify_probe_cases.py
    PYTHONPATH=src uv run python -m evaluation.task_eval run \\
        --task verify --demo-dir evals/datasets/probes \\
        --out evals/results/task_eval/probe_verify_phrasing.jsonl
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from evaluation.task_eval.assets import load_kp_index, parse_exam_items  # noqa: E402

OUT_DIR = ROOT / "evals" / "datasets" / "probes"

# 问法模板：{kp} 为考点中文名。第 1 条是 Phase 0B 的原始模板（组内对照）。
PHRASINGS: list[str] = [
    "{kp}考过哪些真题？",  # ← 对照组：Phase 0B 用的就是这个
    "历年真题里，{kp}出现在哪些题里？",
    "帮我找一下考 {kp} 的真题。",
    "{kp} 这个考点在 408 真题里出现过吗？出现在哪几年？",
    "我想做 {kp} 的真题，有哪些年份考过？",
]

# 选两个不同学科的考点，且真题覆盖较多（多题 gold 才有判别力）
TARGET_KPS = ["ds.stack_queue.stack", "cn.datalink.flow_control"]


def main() -> int:
    kp_index = load_kp_index()
    items = parse_exam_items()
    by_kp: dict[str, list[str]] = defaultdict(list)
    for it in items:
        for kp in it["kp_ids"]:
            by_kp[kp].append(it["question_id"])

    cases: list[dict] = []
    n = 0
    for kp in TARGET_KPS:
        ids = sorted(set(by_kp.get(kp, [])))
        if not ids:
            print(f"⚠️ {kp} 无真题覆盖，跳过")
            continue
        name = kp_index.get(kp, {}).get("name", kp)
        subject = kp_index.get(kp, {}).get("subject", "")
        for pi, tpl in enumerate(PHRASINGS, 1):
            n += 1
            cases.append(
                {
                    "case_id": f"vprobe-{n:03d}",
                    "task": "verify",
                    "task_mode": "verify",
                    "query": tpl.format(kp=name),
                    "subject": subject,
                    "gold": {"expected_question_ids": ids},
                    "gold_status": "draft",
                    "needs_review": [],
                    "notes": (
                        f"探针：kp_id={kp}（{name}）· 问法 #{pi}"
                        f"{'（=Phase 0B 原始模板，组内对照）' if pi == 1 else ''}"
                        f" · gold {len(ids)} 题"
                    ),
                }
            )

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / "verify_cases.jsonl"
    with open(path, "w", encoding="utf-8") as f:
        for c in cases:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    print(f"写入 {len(cases)} 条探针 case → {path}")
    for c in cases:
        print(f"  {c['case_id']}  {c['query']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
