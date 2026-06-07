"""评估体系 CLI 入口

用法:
    python -m app.evaluation.run --quick                         # 快速模式（10条，faithfulness+context_recall, ~5min）
    python -m app.evaluation.run --layer all                     # 全量评估
    python -m app.evaluation.run --layer ragas                   # 仅 RAGAS
    python -m app.evaluation.run --layer diagnosis               # 仅诊断
    python -m app.evaluation.run --category data_structure       # 指定学科
    python -m app.evaluation.run --dataset path/to/data.jsonl    # 指定数据集
    python -m app.evaluation.run --limit 10                      # 限制样本数
    python -m app.evaluation.run --output ./results              # 输出目录
    python -m app.evaluation.run --tag v1                        # 报告标签
"""

from __future__ import annotations

import argparse
import logging
import sys


def main():
    parser = argparse.ArgumentParser(
        description="智能教学系统 - RAG 评估体系",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    # 评估范围
    parser.add_argument(
        "--layer", "-l",
        choices=["all", "ragas", "diagnosis"],
        default="all",
        help="评估层级（默认 all）",
    )
    parser.add_argument(
        "--category", "-c",
        default=None,
        help="限定学科（默认全部）",
    )

    # 数据集
    parser.add_argument(
        "--dataset", "-d",
        default="",
        help="数据集文件路径（默认自动加载 data/evaluation/datasets/ 下所有 .jsonl）",
    )
    parser.add_argument(
        "--limit", "-n",
        type=int,
        default=None,
        help="限制样本数（调试用）",
    )

    # 检索参数
    parser.add_argument(
        "--k",
        type=int,
        default=6,
        help="检索 Top-K（默认 6）",
    )
    parser.add_argument(
        "--no-rerank",
        action="store_true",
        default=False,
        help="禁用 Reranker",
    )

    # RAGAS 指标与模型
    parser.add_argument(
        "--metrics",
        default="",
        help="RAGAS 指标（逗号分隔，默认全部），如 faithfulness,context_recall",
    )
    parser.add_argument(
        "--judge-model",
        default="",
        help="Judge LLM 模型名（空=跟随 EVAL_JUDGE_MODEL → LLM_MODEL）",
    )
    parser.add_argument(
        "--judge-api-base",
        default="",
        help="Judge LLM API base URL（空=跟随 EVAL_JUDGE_API_BASE → LLM_API_BASE）",
    )
    parser.add_argument(
        "--judge-api-key",
        default="",
        help="Judge LLM API key（空=跟随 EVAL_JUDGE_API_KEY → LLM_API_KEY）",
    )
    parser.add_argument(
        "--answer-model",
        default="",
        help="答案生成 LLM 模型名（空=跟随 EVAL_ANSWER_MODEL → LLM_MODEL）",
    )
    parser.add_argument(
        "--answer-api-base",
        default="",
        help="答案生成 LLM API base URL（空=跟随 EVAL_ANSWER_API_BASE → LLM_API_BASE）",
    )
    parser.add_argument(
        "--answer-api-key",
        default="",
        help="答案生成 LLM API key（空=跟随 EVAL_ANSWER_API_KEY → LLM_API_KEY）",
    )

    # 输出
    parser.add_argument(
        "--output", "-o",
        default="data/evaluation/results",
        help="输出目录（默认 data/evaluation/results）",
    )
    parser.add_argument(
        "--tag", "-t",
        default="",
        help="报告文件名标签",
    )

    # 快速模式
    parser.add_argument(
        "--quick", "-q",
        action="store_true",
        default=False,
        help="快速评估模式：仅 10 条样本，仅 faithfulness + context_recall，跳过诊断层",
    )

    # 日志
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        default=False,
        help="详细日志输出",
    )

    args = parser.parse_args()

    # ── 快速模式：覆盖参数 ──
    if args.quick:
        if args.limit is None:
            args.limit = 10
        if not args.dataset:
            args.dataset = "data/evaluation/datasets/baseline.jsonl"
        if not args.metrics:
            args.metrics = "faithfulness,context_recall"
        args.layer = "ragas"
        if not args.tag:
            args.tag = "quick"

    # 日志级别
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stderr,
    )

    from app.evaluation.config import EvaluationConfig
    from app.evaluation.runner import run_evaluation, save_report

    # 解析指标
    metrics = None
    if args.metrics:
        metrics = [m.strip() for m in args.metrics.split(",") if m.strip()]

    cfg = EvaluationConfig(
        layer=args.layer,
        category=args.category,
        dataset_path=args.dataset,
        dataset_limit=args.limit,
        ragas_metrics=metrics or ["faithfulness", "context_precision", "context_recall", "answer_relevancy"],
        judge_model=args.judge_model,
        judge_api_base=args.judge_api_base,
        judge_api_key=args.judge_api_key,
        answer_model=args.answer_model,
        answer_api_base=args.answer_api_base,
        answer_api_key=args.answer_api_key,
        retrieval_k=args.k,
        use_rerank=not args.no_rerank,
        output_dir=args.output,
        output_tag=args.tag,
        quick=args.quick,
    )

    mode_label = " [QUICK]" if args.quick else ""
    print(f"\n{'='*60}")
    print(f"  智能教学系统 - 评估运行{mode_label}")
    print(f"  Layer: {cfg.layer}")
    print(f"  学科: {cfg.category or '全部'}")
    print(f"  数据集: {args.dataset or '自动加载'}")
    print(f"  样本限制: {cfg.dataset_limit or '无'}")
    print(f"  指标: {', '.join(cfg.ragas_metrics)}")
    print(f"{'='*60}\n")

    report = run_evaluation(cfg)

    # 保存报告
    paths = save_report(report, cfg.output_dir, tag=cfg.output_tag)

    print(f"\n{'='*60}")
    print("  评估完成")
    print(f"  报告: {paths.get('json', 'N/A')}")
    print(f"        {paths.get('markdown', 'N/A')}")

    # 打印关键指标摘要
    layer1 = report.get("layer1", {})
    if layer1:
        print("\n  Layer 1 摘要:")
        for metric, scores in sorted(layer1.items()):
            if metric.startswith("_"):
                continue
            if isinstance(scores, dict) and "mean" in scores:
                print(f"    {metric}: mean={scores.get('mean', 'N/A')}, "
                      f"p50={scores.get('p50', 'N/A')}, p90={scores.get('p90', 'N/A')}")

    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
