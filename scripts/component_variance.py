"""组件消融方差实验（P0.1）：3 个独立进程 × 4 配置，query 级明细 + 配对 Δ。

只测「当前系统本身有多稳」，不为降 std 改检索逻辑。
旧结果 `component_ablation.json` 原封不动；本实验独立目录 `component_variance/`。

用法：
    uv run python scripts/component_variance.py              # 3 进程 + 汇总
    uv run python scripts/component_variance.py --run-id 2   # 只跑 run2
    uv run python scripts/component_variance.py --aggregate-only

输出：
    evals/results/retrieval/ablation/component_variance/run{1,2,3}.json
    evals/results/retrieval/ablation/component_variance/summary.json   ← 唯一汇总入口
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from evaluation.retrieval_gate import (  # noqa: E402
    DEFAULT_GOLDEN_PATH,
    GATE_K,
    QueryOutcome,
    compute_metrics,
    load_golden_queries,
)

OUT_DIR = ROOT / "evals" / "results" / "retrieval" / "ablation" / "component_variance"

# 与论文表 2 主结论相关的四配置（B 组零增益行暂不进方差）
CONFIG_NAMES = ("full", "no_bm25", "no_metadata", "vector_only")

# 明细/汇总列（不止 kp_mrr）
METRIC_KEYS = (
    "kp_hit_at_k",
    "kp_mrr",
    "category_hit_at_1",
    "category_mrr",
    "mean_evidence_count",
)


def _query_row(
    run_id: int,
    config: str,
    query_id: str,
    outcome: QueryOutcome,
    error: str,
) -> dict[str, Any]:
    """query 级贡献：便于定位「哪几条在抖」。"""
    kp_annotated = bool(outcome.expected_knowledge_points)
    kp_rank = outcome.first_correct_kp_rank
    cat_rank = outcome.first_correct_rank
    return {
        "run_id": run_id,
        "config": config,
        "query_id": query_id,
        "query": outcome.query[:80],
        # 逐 query 的指标贡献（与 compute_metrics 口径一致）
        "kp_annotated": kp_annotated,
        "kp_hit": (1 if kp_rank is not None else 0) if kp_annotated else None,
        "kp_mrr": ((1.0 / kp_rank) if kp_rank else 0.0) if kp_annotated else None,
        "cat_hit_at_1": 1 if cat_rank == 1 else 0,
        "cat_mrr": (1.0 / cat_rank) if cat_rank else 0.0,
        "evidence_count": len(outcome.hit_categories),
        "infra_error": error,
    }


async def run_one_run(run_id: int) -> dict[str, Any]:
    """单次独立进程内：4 配置 × 60 query，写 query 级明细。"""
    # 延迟 import：避免子进程启动路径差异
    from ablation_retrieval import CONFIGS, apply_config

    from rag.retriever import aretrieve_evidence_with_retry

    queries = load_golden_queries(DEFAULT_GOLDEN_PATH, limit=60)
    from evaluation.retrieval_gate import chapter_of_source

    t0 = time.perf_counter()
    detail: list[dict[str, Any]] = []
    config_metrics: dict[str, dict[str, Any]] = {}

    for name in CONFIG_NAMES:
        flags = CONFIGS[name]
        print(f"[run{run_id}] {name} ...", flush=True)
        outcomes: list[QueryOutcome] = []
        errors: list[str] = []
        k = int(flags.get("k") or GATE_K)
        preferred = ["basic", "advanced", "exams"] if flags.get("topup") else None
        layer_filter = flags.get("layer_filter")

        with apply_config(flags):
            for idx, (query, expected, expected_kps) in enumerate(queries):
                qid = f"q{idx:03d}"
                err = ""
                try:
                    fused, _ = await aretrieve_evidence_with_retry(
                        query=query,
                        k=k,
                        use_rerank=True,
                        max_retries=0,
                        use_llm_verify=False,
                        preferred_layers=preferred,
                        filter=layer_filter,
                    )
                except Exception as exc:  # noqa: BLE001
                    err = f"{type(exc).__name__}: {exc}"
                    errors.append(f"{qid}: {type(exc).__name__}")
                    outcomes.append(
                        QueryOutcome(
                            query=query,
                            expected_categories=expected,
                            expected_knowledge_points=expected_kps,
                        )
                    )
                    detail.append(_query_row(run_id, name, qid, outcomes[-1], err))
                    continue

                docs = fused.text_evidences or []
                hit_cats: list[str] = []
                hit_kps: list[str] = []
                for ev in docs:
                    meta = ev.metadata or {}
                    coll = str(meta.get("_collection") or ev.collection or "")
                    hit_cats.append(coll)
                    src = str(meta.get("source_file") or meta.get("source") or ev.source or "")
                    hit_kps.append(chapter_of_source(src))
                outcome = QueryOutcome(
                    query=query,
                    expected_categories=expected,
                    hit_categories=hit_cats,
                    expected_knowledge_points=expected_kps,
                    hit_knowledge_points=hit_kps,
                )
                outcomes.append(outcome)
                detail.append(_query_row(run_id, name, qid, outcome, err))

        metrics = compute_metrics(outcomes)
        config_metrics[name] = {
            **metrics.as_dict(),
            "n_errors": len(errors),
            "errors": errors[:5],
        }

    elapsed = round(time.perf_counter() - t0, 1)
    return {
        "run_id": run_id,
        "recorded_at": time.strftime("%Y%m%d_%H%M%S"),
        "golden": str(DEFAULT_GOLDEN_PATH),
        "limit": 60,
        "configs": list(CONFIG_NAMES),
        "elapsed_s": elapsed,
        "config_metrics": config_metrics,
        "detail": detail,
    }


def _mean_std(vals: list[float]) -> tuple[float, float]:
    if not vals:
        return 0.0, 0.0
    mean = statistics.fmean(vals)
    std = statistics.stdev(vals) if len(vals) >= 2 else 0.0
    return round(mean, 4), round(std, 4)


def aggregate(runs: list[dict[str, Any]]) -> dict[str, Any]:
    """run 级 mean±std + 逐 run 配对 Δ。"""
    # config 级：每个 metric 的三 run 序列
    per_config: dict[str, dict[str, Any]] = {}
    for name in CONFIG_NAMES:
        block: dict[str, Any] = {}
        for key in METRIC_KEYS:
            series = [float(r["config_metrics"][name][key]) for r in runs]
            mean, std = _mean_std(series)
            block[key] = {
                "runs": [round(v, 4) for v in series],
                "mean": mean,
                "std": std,
            }
        errs = [int(r["config_metrics"][name].get("n_errors", 0)) for r in runs]
        block["n_errors"] = {"runs": errs, "mean": round(statistics.fmean(errs), 2)}
        per_config[name] = block

    # 配对 Δ：同一 run 内 ablation − full
    paired_delta: dict[str, dict[str, Any]] = {}
    for name in CONFIG_NAMES:
        if name == "full":
            continue
        block = {}
        for key in METRIC_KEYS:
            deltas = []
            for r in runs:
                a = float(r["config_metrics"][name][key])
                b = float(r["config_metrics"]["full"][key])
                deltas.append(round(a - b, 4))
            mean, std = _mean_std(deltas)
            block[key] = {"paired_deltas": deltas, "mean": mean, "std": std}
        paired_delta[name] = block

    return {
        "design": "3 independent processes × 4 configs × 60 golden queries",
        "n_runs": len(runs),
        "metrics": list(METRIC_KEYS),
        "metric_map": {
            "kp_hit_at_k": "kp_hit",
            "kp_mrr": "kp_mrr",
            "category_hit_at_1": "cat@1",
            "category_mrr": "cat_mrr",
            "mean_evidence_count": "evidence_count",
        },
        "per_config": per_config,
        "paired_delta_vs_full": paired_delta,
        "footnote": (
            "n=3 独立进程；std 为运行间系统非确定性波动，不作为统计显著性检验。"
            "Δ 为逐 run 配对差（ablation_i − full_i）的 mean±std。"
        ),
        "run_ids": [r["run_id"] for r in runs],
        "recorded_at": [r["recorded_at"] for r in runs],
    }


def print_summary(summary: dict[str, Any]) -> None:
    print("\n==== Component Variance (mean ± std, n=3) ====")
    header = f"{'config':<12}" + "".join(f"{k:>18}" for k in METRIC_KEYS)
    print(header)
    print("-" * len(header))
    for name in CONFIG_NAMES:
        block = summary["per_config"][name]
        line = f"{name:<12}"
        for key in METRIC_KEYS:
            cell = block[key]
            line += f"{cell['mean']:.3f}±{cell['std']:.3f}".rjust(18)
        print(line)
    print("\n==== paired Δ vs full (mean ± std) ====")
    header = f"{'Δ':<12}" + "".join(f"{k:>18}" for k in METRIC_KEYS)
    print(header)
    print("-" * len(header))
    for name in CONFIG_NAMES:
        if name == "full":
            continue
        block = summary["paired_delta_vs_full"][name]
        line = f"{name:<12}"
        for key in METRIC_KEYS:
            cell = block[key]
            line += f"{cell['mean']:+.3f}±{cell['std']:.3f}".rjust(18)
        print(line)
    print(f"\n{summary['footnote']}")


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", type=int, default=0, help="1/2/3=单跑；0=三进程+汇总")
    ap.add_argument("--aggregate-only", action="store_true")
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    if args.aggregate_only:
        runs = []
        for i in (1, 2, 3):
            p = OUT_DIR / f"run{i}.json"
            if not p.exists():
                print(f"missing {p}")
                return 2
            runs.append(json.loads(p.read_text(encoding="utf-8")))
        summary = {
            "summary": aggregate(runs),
            "runs_meta": [
                {"run_id": r["run_id"], "config_metrics": r["config_metrics"]} for r in runs
            ],
        }
        path = OUT_DIR / "summary.json"
        path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print_summary(summary["summary"])
        print(f"summary → {path}")
        return 0

    if args.run_id in (1, 2, 3):
        result = await run_one_run(args.run_id)
        path = OUT_DIR / f"run{args.run_id}.json"
        path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"run{args.run_id} → {path}  elapsed={result['elapsed_s']}s")
        return 0

    # 三独立进程
    script = Path(__file__).resolve()
    for i in (1, 2, 3):
        print(f"==== spawn run {i}/3 ====", flush=True)
        proc = subprocess.run(
            [sys.executable, str(script), "--run-id", str(i)],
            cwd=str(ROOT),
        )
        if proc.returncode != 0:
            print(f"run{i} failed rc={proc.returncode}")
            return proc.returncode

    runs = [json.loads((OUT_DIR / f"run{i}.json").read_text(encoding="utf-8")) for i in (1, 2, 3)]
    summary = {
        "summary": aggregate(runs),
        "runs_meta": [{"run_id": r["run_id"], "config_metrics": r["config_metrics"]} for r in runs],
    }
    path = OUT_DIR / "summary.json"
    path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print_summary(summary["summary"])
    print(f"summary → {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
