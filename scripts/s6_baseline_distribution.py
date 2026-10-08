"""§6 Final Gate 门槛回填的**数据来源**：把两份 Phase 0/1 归档里的真实分布算出来（零成本）。

为什么要有这个脚本
------------------
`EFFECT_PLAN §6` 冻结的是**规则**、明确把**门槛数字**推迟到 Phase 0 回填
（「先测量，再据真实分布设定」）。门槛必须在 §6 那次整轮实跑**之前**定稿并落档 ——
否则就是看着结果画线，等于没有门槛。

本脚本只读 `evals/results/task_eval/*.jsonl`，用**现口径**（`report.summarize_task` +
`metrics.every_item_passes`）重算，不调用任何 LLM、不写任何文件。
⇒ 门槛表里每个数字都能用一行命令重跑核对：

    PYTHONIOENCODING=utf-8 uv run python scripts/s6_baseline_distribution.py

输出对应的门槛行见 `docs/EXPERIMENTS.md` §21。
"""

from __future__ import annotations

import json
import pathlib
import sys
from collections import Counter

sys.path.insert(0, "src")

from evaluation.task_eval import metrics  # noqa: E402
from evaluation.task_eval.report import summarize_task  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1] / "evals" / "results" / "task_eval"
ARCHIVES = ("phase0_baseline_final.jsonl", "phase1_baseline_v2.jsonl")
TASKS = ("qa", "generate", "grade", "verify", "memory")


def load(path: pathlib.Path) -> list[dict]:
    return [
        json.loads(ln)
        for ln in path.read_text(encoding="utf-8").splitlines()
        if ln.strip() and not ln.strip().startswith("#")
    ]


def report_one(name: str) -> None:
    path = ROOT / name
    if not path.exists():
        print(f"!! 缺 {name}（不入库的历史归档，需在本机）")
        return
    rows = load(path)
    print(f"\n############ {name}  n={len(rows)} ############")
    for task in TASKS:
        sub = [r for r in rows if r.get("task") == task]
        if not sub:
            continue
        d = summarize_task(task, sub).__dict__
        judged = [float(r["final_quality"]) for r in sub if r.get("final_quality") is not None]
        ge4 = sum(1 for v in judged if v >= 4)
        hard = sum(1 for r in sub if r.get("hard_fails"))
        tool = sum(1 for r in sub if r.get("primary_failure") == "tool_error")
        fails = Counter(str(r.get("primary_failure")) for r in sub if r.get("primary_failure"))
        print(
            f"  {task:9s} n={len(sub):2d} 判分={len(judged):2d} μ={d.get('mean_final_quality')} "
            f"ge4={ge4}/{len(judged)}" + (f"={ge4 / len(judged):.3f}" if judged else "")
        )
        print(
            f"            invalid_n={d.get('invalid_n')} failure_rate={d.get('failure_rate')} "
            f"hard_fails={hard} tool_error={tool}({tool / len(sub):.1%} 任务级)"
        )
        print(f"            primary_failure={dict(fails)}")
        if task == "generate":
            flags = [
                metrics.every_item_passes(
                    [
                        r.get("gen_structure"),
                        r.get("gen_answerability"),
                        r.get("gen_coverage"),
                        r.get("gen_correctness"),
                        r.get("gen_difficulty"),
                    ]
                )
                for r in sub
            ]
            print(f"            逐题适用项全过（#2 主指标）= {metrics.rate(flags)}")
        if task == "grade":
            print(
                f"            verdict_agreement={d.get('verdict_agreement')}\n"
                f"            score_tolerance={d.get('score_tolerance')}"
            )
        if task == "memory":
            print(f"            memory_correct_use={d.get('memory_correct_use')}")
    print(
        "  provenance: 带 code_version="
        f"{sum(1 for r in rows if (r.get('provenance') or {}).get('code_version'))}/{len(rows)}"
        f" | 带 prompt_set_version={sum(1 for r in rows if r.get('prompt_set_version'))}/{len(rows)}"
        "（★ 旧格式没有这两个字段 ⇒ §6 的 provenance 条对历史归档不可能满足，只能定义成新产出的口径）"
    )


def main() -> int:
    print("§6 门槛回填的数据来源（真实分布，非门槛）。门槛表与口径讨论见 docs/EXPERIMENTS.md §21。")
    for name in ARCHIVES:
        report_one(name)
    print(
        "\n############ 检索侧（不进本脚本：由门禁自己判）############\n"
        "  `PYTHONPATH=src GATE_USE_REAL_EMBEDDING=1 GATE_RERANK_MODE=on GATE_USE_REAL_RERANK=1 "
        "uv run python -m evaluation.retrieval_gate`\n"
        "  判据 = 「各指标不低于 V-2026-10-02 基线，容差 0.02」；③ 锚点复现值见 §20.2。"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
