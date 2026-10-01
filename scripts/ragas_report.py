"""RAGAS 结果整理：把 `ragas_<tag>.json` 转成 results/ 约定的三层产物。

为什么需要它：`evaluation.cli` 只写一份完整报告（含 details）；
而 `evals/results/generation/ragas/` 的约定是三层 ——
`raw.jsonl`（逐样本）/ `metrics.json`（汇总）/ `summary.md`（人工结论）。
本脚本负责把前两层从报告里派生出来，保证与报告**同源、可重算**。

用法：
    uv run python scripts/ragas_report.py                      # 默认 tag=final
    uv run python scripts/ragas_report.py --tag smoke
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAGAS_DIR = ROOT / "evals" / "results" / "generation" / "ragas"
METRICS = ("faithfulness", "context_precision", "context_recall", "answer_relevancy")

sys.path.insert(0, str(ROOT / "src"))
from evaluation.provenance import build_provenance  # noqa: E402


def _current_judge_model() -> str | None:
    """报告缺 judge_model 时的回退（老报告兼容）。"""
    try:
        import sys

        sys.path.insert(0, str(ROOT / "src"))
        from core.settings import settings

        return settings.ragas_judge_model
    except Exception:
        return None


def _current_generation_model() -> str | None:
    try:
        import sys

        sys.path.insert(0, str(ROOT / "src"))
        from core.settings import settings

        return settings.LLM_MODEL
    except Exception:
        return None


def _by_type(details: list[dict]) -> dict[str, dict[str, dict]]:
    """按 query_type 聚合：均值 + 有效样本数（None 不计入分母）。"""
    buckets: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    counts: dict[str, int] = defaultdict(int)
    for row in details:
        t = str(row.get("query_type") or "concept")
        counts[t] += 1
        for m in METRICS:
            v = row.get(m)
            if v is not None:
                buckets[t][m].append(float(v))
    out: dict[str, dict] = {}
    for t, per_metric in buckets.items():
        out[t] = {
            "n": counts[t],
            **{
                m: {
                    "mean": round(statistics.fmean(vals), 4) if vals else None,
                    "n": len(vals),
                }
                for m, vals in per_metric.items()
            },
        }
    return dict(sorted(out.items()))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default="final")
    args = ap.parse_args()

    report_path = RAGAS_DIR / f"ragas_{args.tag}.json"
    if not report_path.exists():
        print(f"报告不存在: {report_path}（先跑 evaluation.cli）")
        return 2
    report = json.loads(report_path.read_text(encoding="utf-8"))
    meta = report.get("_meta", {})
    details = report.get("details") or []
    rc = meta.get("run_config", {})

    # 1) raw.jsonl —— 逐样本（question / answer / contexts / scores）
    raw_path = RAGAS_DIR / "raw.jsonl"
    with raw_path.open("w", encoding="utf-8") as f:
        for row in details:
            f.write(
                json.dumps(
                    {
                        "id": f"ragas_{row['index']:03d}",
                        "query": row.get("query"),
                        "query_type": row.get("query_type"),
                        "subject": row.get("subject"),
                        "reference": row.get("reference"),
                        "answer": row.get("answer"),
                        "contexts": row.get("contexts"),
                        "sources": [(c or {}).get("source") for c in (row.get("retrieval") or [])],
                        "scores": {m: row.get(m) for m in METRICS},
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )

    # 2) metrics.json —— 汇总（总体 + 分类型）
    metrics_out = {
        "status": "ok" if not meta.get("error") else "error",
        "error": meta.get("error"),
        "tag": args.tag,
        "n_loaded": rc.get("n_loaded"),
        "n_filled": rc.get("n_filled"),
        "query_type_distribution": rc.get("query_type_distribution"),
        "judge_model": rc.get("judge_model") or _current_judge_model(),
        "generation_model": rc.get("generation_model") or _current_generation_model(),
        "retrieval_k": rc.get("retrieval_k"),
        "effective_rerank_enabled": rc.get("effective_rerank_enabled"),
        "embedding_fake": rc.get("embedding_fake"),
        "note": "逐样本明细见 raw.jsonl 与 ragas_<tag>.json；分类型均值为本文件派生",
        # 本文件由本脚本派生，故 provenance 记本脚本；上游 RAGAS 运行的口径见上方 model 字段
        "source_report": f"ragas_{args.tag}.json",
        **build_provenance("scripts/ragas_report.py"),
    }
    for m in METRICS:
        metrics_out[m] = report.get(m)
    metrics_out["by_query_type"] = _by_type(details)

    (RAGAS_DIR / "metrics.json").write_text(
        json.dumps(metrics_out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    print(f"wrote {raw_path.name} ({len(details)} rows)")
    print("wrote metrics.json")
    for m in METRICS:
        cell = report.get(m) or {}
        print(f"  {m}: mean={cell.get('mean')} n={cell.get('n')}")
    print("按 query_type:")
    for t, block in metrics_out["by_query_type"].items():
        cells = " ".join(f"{m[:9]}={block[m]['mean']}" for m in METRICS if m in block)
        print(f"  {t:<10} n={block['n']} {cells}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
