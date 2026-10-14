# ragas/ —— RAGAS 配对样本

| 文件 | 条数 | 说明 |
|---|---|---|
| `ragas_paired20.jsonl` | 20 | RAGAS 组件指标（faithfulness / context_precision / context_recall / answer_relevancy）的配对样本 |

- 样本 query 与 `golden/sample_408.jsonl` 同源，**`reference` 与黄金集逐字一致**（2026-10-14 审计：
  交集 20 条零不一致）——两处必须同源改动，改一处勿忘另一处。
- 用法：`PYTHONPATH=src uv run python -m evaluation.ragas.cli --dataset evals/datasets/ragas/ragas_paired20.jsonl --sample-per-type 5 --no-rerank --tag <标签>`
- 整理产物：`scripts/ops/ragas_report.py` → `evals/results/generation/ragas/`。
- ★ RAGAS 读数属旧代语料体系（归档 metrics.json 时间戳 2026-10-01），引用前查
  `docs/EXPERIMENTS.md` §5 的代际脚注。
