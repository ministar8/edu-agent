# RAGAS 生成质量评估（V-2026-10-02 · 全量 20 条）

## 口径

| 项 | 值 |
|---|---|
| 数据集 | `evals/datasets/ragas/ragas_paired20.jsonl`（20 条 = 4 类型 × 5） |
| 覆盖 | concept 5 · generate 5 · grade 5 · code 5；学科 os7 / ds5 / co4 / net4 |
| 生成模型 | `dashscope:qwen3.7-flash` |
| **judge 模型** | **`dashscope:qwen3.8-max-0902`（强制关 thinking，因 `answer_relevancy` 需 `n>1`）** |
| 检索 | k=5 · `--no-rerank`（与冻结检索版本 V-2026-10-02 同口径） |
| Embedding | TEI `BAAI/bge-m3`（真实，非哈希桩） |
| 有效样本 | n_filled = 20 / n_loaded = 20（四项指标均 **n=20**） |

命令：
```bash
PYTHONPATH=src uv run python -m evaluation.cli \
  --dataset evals/datasets/ragas/ragas_paired20.jsonl \
  --sample-per-type 5 --no-rerank --include-details --tag final
uv run python scripts/ragas_report.py --tag final
```

## 总体结果

| 指标 | **V-2026-10-02** | 修复前三项检索缺陷 | Δ |
|---|---|---|---|
| faithfulness | **0.7588** | 0.7595 | −0.001 |
| context_precision | **0.6840** | 0.7318 | −0.048 |
| context_recall | **0.4000** | 0.4625 | −0.063 |
| answer_relevancy | **0.5994** | 0.5324 | **+0.067** |

## 分查询类型

| query_type | faithfulness | context_precision | context_recall | answer_relevancy |
|---|---|---|---|---|
| **concept** | **1.000** | **0.817** | 0.633 | **0.792** |
| grade | 0.708 | 0.823 | 0.550 | 0.707 |
| code | 0.807 | 0.478 | 0.350 | 0.292 |
| **generate** | 0.521 | 0.619 | **0.067** | 0.606 |

## 结论

1. **概念问答（concept）质量最高**：faithfulness **1.000**、answer_relevancy 0.792
   —— 证据被完全忠实使用，答案切题。与任务策略收益最大的类型一致（§10/§11）。
2. **answer_relevancy 提升 +0.067**（code 0.136→**0.292**）：
   排序方向修复（§18.2 #3）让向量路由返回**真正的最近邻**，检索命中更准 → 答案更切题。
3. **context_precision / context_recall 各降约 0.05–0.06**：
   更「近邻」的证据同时更**集中**，对「参考答案覆盖率」略有不利。
   ⚠️ **每类仅 5 条（n=5），两版本差异不作显著性结论**。
4. **两个低值仍是口径失配，不是质量崩塌**：
   - `generate` **context_recall 0.067**：reference 是**题面**，系统输出**新题** → 指标语义不成立
   - `code` **answer_relevancy 0.292**：该指标靠「答案反推问题」，源码推不出问题 → 系统性偏低；
     该类型 faithfulness 0.807 正常，说明证据使用是好的

## 诚实披露

- ❌ 不可写「context_recall 0.40 = 检索召回不足」——generate 一整类（n=5）是口径失配
- ❌ 不可写「answer_relevancy 0.60 = 答案不切题」——code 一整类（n=5）是口径失配
- ✅ 可写「concept 类 QA 表现最优；generate/code 的自动指标存在适用性限制」
- ⚠️ 样本量小（每类 5 条），**不作显著性判断**

## 产物

| 文件 | 内容 |
|---|---|
| `raw.jsonl` | 20 条逐样本：query / reference / answer / contexts / sources / scores |
| `metrics.json` | 总体 + 分类型汇总（含 judge / 生成模型 provenance） |
| `ragas_final.json` | CLI 原始完整报告（含 retrieval 明细） |
| `ragas_final_samples.jsonl` | 生成产物快照（judge 失败可复用，无需重新生成） |
| `summary.md` | 本文件 |
