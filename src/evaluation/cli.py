"""RAGAS 评估 CLI。

uv sync --group eval
python -m evaluation.cli --dataset evals/sample_408.jsonl --limit 5
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="edu-agent RAGAS evaluation")
    parser.add_argument("--dataset", default="evals/sample_408.jsonl")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--no-rerank", action="store_true")
    parser.add_argument(
        "--metrics",
        default="faithfulness,context_precision,context_recall,answer_relevancy",
        help="逗号分隔",
    )
    parser.add_argument("--output-dir", default="evals/results")
    parser.add_argument("--tag", default="")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    from evaluation.config import EvaluationConfig
    from evaluation.ragas_eval import run_rag_evaluation

    cfg = EvaluationConfig(
        dataset_path=args.dataset,
        dataset_limit=args.limit,
        retrieval_k=args.k,
        use_rerank=not args.no_rerank,
        ragas_metrics=[m.strip() for m in args.metrics.split(",") if m.strip()],
        output_dir=args.output_dir,
        output_tag=args.tag,
    )
    report = asyncio.run(run_rag_evaluation(cfg))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if not report.get("_meta", {}).get("error") else 1


if __name__ == "__main__":
    sys.exit(main())
