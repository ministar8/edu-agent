# 论文实验表（可直接粘贴）

> 数字来源：`evals/results/` 原始归档 · 完整论述见 `docs/EXPERIMENTS.md`
> 样本：黄金集 `evals/datasets/golden/sample_408.jsonl` 前 60 条（标注齐）

## 表 1 基础 RAG 对比（§11）

| 指标 | basic_rag | ours | Δ |
|---|---|---|---|
| kp_hit@k | 0.967 | **1.000** | +0.033 |
| kp_mrr | 0.863 | **0.951** | **+0.089** |
| category_hit@1 | 0.917 | **0.983** | +0.067 |
| category_mrr | 0.956 | **0.992** | +0.036 |
| 平均证据数 | 4.75 | 5.73 | +0.98 |

## 表 2 检索组件消融（§2）

| 配置 | kp_hit@k | kp_mrr | Δ kp_mrr |
|---|---|---|---|
| **full** | 1.000 | **0.943** | — |
| no_bm25 | 0.967 | 0.856 | −0.088 |
| no_metadata | 0.983 | 0.831 | **−0.113** |
| no_decompose | 1.000 | 0.943 | 0 |
| no_hyde | 1.000 | 0.943 | 0 |
| vector_only | 0.967 | 0.785 | **−0.158** |
| plus_topup | 1.000 | 0.943 | 0 |
| rerank on（对照） | 0.983 | 0.897 | −0.046 |

## 表 3 Task-aware 任务指标（§10）

| task_mode | 目标层 | baseline | ours | Δ |
|---|---|---|---|---|
| learn | L1 basic | 0.667 | **1.000** | **+0.333** |
| method | L2 advanced | 0.833 | **1.000** | **+0.167** |
| practice | L2+L3 | 1.000 | 1.000 | 0（泄漏 0.25→0） |
| grade | L3 exams | 0.667 | 0.667 | 0 |
| explain | L3 exams | 1.000 | 1.000 | 0 |
| verify | L3 exams | 0.333 | 0.333 | 0 |
| **MACRO** | | 0.750 | **0.833** | **+0.083** |

## 表 4 L1/L2/L3 单层保留（§9）

| 配置 | kp_hit@k | kp_mrr | empty |
|---|---|---|---|
| full | 1.000 | 0.951 | 0 |
| l1_only | 0.983 | 0.944 | 0 |
| l2_only | 0.783 | 0.704 | 0 |
| l3_only | 0.000 | 0.000 | 0.983 |
| no_legacy | 0.967 | 0.882 | 0 |
| legacy_only | 1.000 | 0.934 | 0 |

## 表 5 legacy 池策略（§3）

| 策略 | 层精度 pack 均值 |
|---|---|
| keep | 0.375 |
| downrank | 0.417 |
| **exclude（采用）** | **1.000** |

## 图 1（建议）：任务 → 层 → 策略

```
Task Policy ──► Retrieval Plan ──► Evidence Pack
   learn ──────── L1 优先 ──────── exclude legacy
   method ─────── L2 优先 ──────── exclude legacy
   practice ───── L2+L3 ─────────── exclude + 禁答案
   grade ──────── L3 优先 ──────── fallback legacy
   verify ─────── L3 优先 ──────── exclude 答案
```
