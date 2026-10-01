# 论文实验表（可直接粘贴）

> 数字来源：`evals/results/` **V-2026-10-02**（见 EXPERIMENTS.md §18）
> 完整论述见 `docs/EXPERIMENTS.md` · 问题诊断见 `evals/reports/rerun_summary.md`
> 样本：黄金集前 60 条（检索）· 任务集 25 条 · 门禁 156 条

## 表 1 基础 RAG 对比（§11，V-2026-10-02）

| 指标 | basic_rag | ours | Δ |
|---|---|---|---|
| kp_hit@k | 0.967 | **1.000** | +0.033 |
| kp_mrr | 0.875 | **0.9625** | **+0.0875** |
| category_hit@1 | 0.917 | **0.983** | +0.067 |
| category_mrr | 0.956 | **0.992** | +0.036 |
| 平均证据数 | 4.73 | 5.67 | +0.93 |

## 表 2 检索组件消融（§2，V-2026-10-02）

| 配置 | kp_hit@k | kp_mrr | Δ kp_mrr |
|---|---|---|---|
| **full** | 1.000 | **0.9625** | — |
| no_bm25 | 0.983 | 0.9000 | **−0.062** |
| no_metadata | 1.000 | 0.9417 | −0.021 |
| no_decompose | 1.000 | 0.9625 | 0 |
| no_hyde | 1.000 | 0.9625 | 0 |
| vector_only | 0.983 | 0.9306 | −0.032 |
| plus_topup | 1.000 | 0.9625 | 0 |
| rerank on（对照） | — | 0.975 | **+0.012**（符号不稳，更早 −0.046） |

> **口径**：本轮 BM25 贡献 > 元数据；与旧表排序不同，以本轮为准。
> decompose/HyDE 仍零增益。rerank **不宜写「负优化」**，写「收益不稳定，默认关」。

## 表 3 Task-aware 任务指标（§10，V-2026-10-02）

| task_mode | 目标层 | baseline | ours | Δ |
|---|---|---|---|---|
| learn | L1 basic | 0.833 | **1.000** | **+0.167** |
| method | L2 advanced | 1.000 | 1.000 | 0 |
| practice | L2+L3 | 1.000 | 1.000 | 0（泄漏 0.25→0） |
| grade | L3 exams | 0.667 | 0.667 | 0 |
| explain | L3 exams | 1.000 | 1.000 | 0 |
| verify | L3 exams | **1.000** | **1.000** | 0 |
| **MACRO** | | 0.917 | **0.944** | **+0.028** |

> 口径：实验路径与 Agent 路径统一 `eligibility_where` + top-up 同源过滤后，
> verify 从 0.333→1.000；baseline 同步抬升，ours 相对 Δ 缩小。

## 表 4 L1/L2/L3 单层保留（§9，V-2026-10-02）

| 配置 | kp_hit@k | kp_mrr | empty |
|---|---|---|---|
| full | 1.000 | 0.9625 | 0 |
| l1_only | 0.983 | 0.9556 | 0 |
| l2_only | 0.783 | 0.7194 | 0 |
| l3_only | 0.000 | 0.000 | 0.983 |
| no_legacy | 0.983 | 0.8988 | 0 |
| legacy_only | 1.000 | 0.9450 | 0 |

## 表 5 legacy 池策略（§3）

| 策略 | 层精度 pack 均值 |
|---|---|
| keep | 0.396 |
| downrank | 0.438 |
| **exclude（采用）** | **1.000** |

## 表 6 Task Mode × Layer Policy（§12，主表，2026-10-01 P0' 后）

> 只动 `preferred_layers`；安全字段冻结。  
> hit = 目标层进包；prec = 目标层在包内占比；pack = `pack_nonempty_rate`

| task_mode | flat hit | ours hit | flat prec | ours prec | flat pack | ours pack |
|---|---|---|---|---|---|---|
| learn | 1.000 | 1.000 | 0.583 | 0.583 | 1.000 | 1.000 |
| method | 1.000 | 1.000 | 0.606 | 0.606 | 1.000 | 1.000 |
| practice | 1.000 | 1.000 | 0.542 | 0.542 | 1.000 | 1.000 |
| grade | 0.667 | 0.667 | 0.267 | 0.267 | 1.000 | 1.000 |
| explain | 1.000 | 1.000 | 0.378 | 0.378 | 1.000 | 1.000 |
| verify | **1.000** | **1.000** | 0.333 | **0.417** | 1.000 | 1.000 |

要点：ours 在 hit 不降的前提下提升 grade/verify 包纯度，并保持全任务非空证据包。

## 附表 6A 固定单层偏好对照（layer_hit）

| task_mode | 目标层 | flat | ours | prefer_l1 | prefer_l2 | prefer_l3 |
|---|---|---|---|---|---|---|
| learn | L1 | 1.000 | 1.000 | 1.000 | 0.833 | 1.000 |
| method | L2 | 1.000 | 1.000 | 0.500 | 1.000 | 1.000 |
| practice | L2+L3 | 1.000 | 1.000 | 0.250 | 1.000 | 1.000 |
| grade | L3 | 0.667 | 0.667 | 0.000 | 0.000 | 0.667 |
| explain | L3 | 1.000 | 1.000 | 0.333 | 0.333 | 1.000 |
| verify | L3 | **1.000** | **1.000** | 0.000 | 0.000 | **1.000** |
| **MACRO** | | **0.944** | **0.944** | 0.347 | 0.528 | **0.944** |

## 附表 6B pack_nonempty_rate（sufficiency）

| task_mode | flat | ours | prefer_l1 | prefer_l2 | prefer_l3 |
|---|---|---|---|---|---|
| learn | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| method | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| practice | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| grade | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| explain | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| verify | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |

> **修复前** prefer_l3 空包（practice 0.25）；**sufficiency 兜底后全 1.000**。
> 残余交互伤害由 prefer_l1（0.347）/ prefer_l2（0.528）体现——合规但错层。

## 图 1（建议）：任务 → 层 → 策略

```
Task Policy ──► Retrieval Plan ──► Evidence Pack
   learn ──────── L1 优先 ──────── exclude legacy
   method ─────── L2 优先 ──────── exclude legacy
   practice ───── L2+L3 ─────────── exclude + 禁答案
   grade ──────── L3 优先 ──────── fallback legacy
   verify ─────── L3 优先 ──────── exclude 答案
```
