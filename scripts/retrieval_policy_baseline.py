"""Retrieval Policy 门禁基线：录制 / 对比。

用法：
    uv run python scripts/retrieval_policy_baseline.py           # 对比
    uv run python scripts/retrieval_policy_baseline.py --update  # 重录（需说明原因）
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

BASELINE_PATH = ROOT / "evals" / "retrieval_policy_baseline.json"

# 冻结期望（不随实验 layer_weight 改动）
EXPECTED_CLASSIFY = {
    "什么是死锁？": "learn",
    "BST 删除怎么做？": "method",
    "给我一道死锁练习题": "practice",
    "学生答案是 A，请批改": "grade",
    "2019 年第 11 题为什么选 B？": "explain",
    "BST 删除考过哪些真题？": "verify",
}
PRACTICE_LEAK_MUST_BE_ZERO = ["answer_key", "reference_answer", "question_id", "exam_answer"]
E2E_CASES = ["learn", "method", "practice", "grade", "explain", "verify"]


def _run_script(name: str) -> tuple[int, str]:
    p = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / name)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(ROOT),
        timeout=180,
    )
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def collect() -> dict:
    from rag.retrieval_policy import classify_task_mode
    from schema.retrieval_policy import RetrievalPolicy

    classify = {q: classify_task_mode(q) for q in EXPECTED_CLASSIFY}

    # eligibility where 快照（安全相关）
    from rag.retrieval_policy import resolve_retrieval_policy

    where_snapshot = {}
    for mode, q in [
        ("learn", "什么是二叉排序树？"),
        ("method", "BST 删除怎么做？"),
        ("practice", "给我一道 BST 练习题"),
        ("grade", "2019-Q11 我选 C 对吗？"),
        ("explain", "2019-Q11 为什么选 B？"),
        ("verify", "BST 删除考过哪些真题？"),
    ]:
        p: RetrievalPolicy = resolve_retrieval_policy(q)
        where_snapshot[mode] = {
            "task_mode": p.task_mode,
            "where": p.eligibility_where(),
            "answer_policy": p.answer_policy,
            "exam_resources": p.exam_resources.model_dump(),
            "allow_question_id_leak": p.allow_question_id_leak,
        }

    leak_rc, leak_out = _run_script("leakage_gate.py")
    e2e_rc, e2e_out = _run_script("e2e_ds_tree_modes.py")
    mode_rc, mode_out = _run_script("mode_layer_gate.py")

    e2e_modes = re.findall(r"\[(learn|method|practice|grade|explain|verify)\]", e2e_out)
    layer_hits = len(re.findall(r"layer_hit=True", e2e_out))

    return {
        "_meta": {
            "recorded_at": datetime.now(UTC).isoformat(),
            "policy_version": "1.0",
            "note": "Retrieval Policy 安全门基线；改策略/分类器/裁剪后须 --update 并说明原因",
            "commands": [
                "scripts/leakage_gate.py",
                "scripts/e2e_ds_tree_modes.py",
                "scripts/mode_layer_gate.py",
            ],
        },
        "classify": classify,
        "where_snapshot": where_snapshot,
        "gates": {
            "leakage_gate": "PASS" if leak_rc == 0 else "FAIL",
            "e2e_ds_tree": "PASS" if e2e_rc == 0 else "FAIL",
            "mode_layer_gate": "PASS" if mode_rc == 0 else "FAIL",
        },
        "e2e": {
            "modes_seen": sorted(set(e2e_modes)),
            "layer_hit_count": layer_hits,
            "expected_modes": E2E_CASES,
        },
        "practice_leak_must_be_zero": PRACTICE_LEAK_MUST_BE_ZERO,
    }


def compare(current: dict, baseline: dict) -> list[str]:
    fails: list[str] = []
    for q, want in EXPECTED_CLASSIFY.items():
        got = current["classify"].get(q)
        base = (baseline.get("classify") or {}).get(q)
        if got != want:
            fails.append(f"classify drift {q!r}: got={got} expected={want}")
        elif base is not None and got != base:
            fails.append(f"classify vs baseline {q!r}: {got} != {base}")

    for mode in E2E_CASES:
        cw = current["where_snapshot"].get(mode) or {}
        bw = (baseline.get("where_snapshot") or {}).get(mode) or {}
        if cw.get("answer_policy") != bw.get("answer_policy"):
            fails.append(
                f"where_snapshot {mode} answer_policy {cw.get('answer_policy')} != {bw.get('answer_policy')}"
            )
        if cw.get("allow_question_id_leak") != bw.get("allow_question_id_leak"):
            fails.append(f"where_snapshot {mode} allow_question_id_leak drift")

    for name, st in (baseline.get("gates") or {}).items():
        cur = (current.get("gates") or {}).get(name)
        if st == "PASS" and cur != "PASS":
            fails.append(f"gate {name}: baseline PASS but now {cur}")

    base_modes = set((baseline.get("e2e") or {}).get("expected_modes") or E2E_CASES)
    cur_modes = set((current.get("e2e") or {}).get("modes_seen") or [])
    if not base_modes.issubset(cur_modes):
        fails.append(f"e2e modes missing: {sorted(base_modes - cur_modes)}")

    base_hits = int((baseline.get("e2e") or {}).get("layer_hit_count") or 0)
    cur_hits = int((current.get("e2e") or {}).get("layer_hit_count") or 0)
    if cur_hits < min(base_hits, len(E2E_CASES)):
        fails.append(f"layer_hit_count {cur_hits} < baseline {base_hits}")
    return fails


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--update", action="store_true", help="重录基线")
    ap.add_argument("--baseline", default=str(BASELINE_PATH))
    args = ap.parse_args()

    current = collect()
    path = Path(args.baseline)

    if args.update:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(current, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"基线已更新: {path}")
        print(json.dumps(current["gates"], ensure_ascii=False))
        return 0

    if not path.exists():
        print("[提示] 基线不存在，只观测。确认后加 --update 录制。")
        print(json.dumps(current, ensure_ascii=False, indent=2)[:2000])
        return 0

    baseline = json.loads(path.read_text(encoding="utf-8"))
    fails = compare(current, baseline)
    print("==== retrieval_policy baseline ====")
    print("gates", current["gates"])
    print(
        "e2e modes", current["e2e"]["modes_seen"], "layer_hits", current["e2e"]["layer_hit_count"]
    )
    if fails:
        print("BASELINE FAIL", len(fails))
        for x in fails:
            print(" -", x)
        return 1
    print("BASELINE PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
