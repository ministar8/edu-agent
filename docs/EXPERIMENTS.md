# 专项实验数据汇总

> 供论文实验章直接引用。数据来源均为仓库内 `evals/` 归档，可复现脚本见各节「复现」。
> **本轮全量重跑**：检索 2026-09-30 · RAGAS 2026-10-01；旧时间戳归档已删除，结果为规范文件名。
> 问题诊断见 `evals/reports/rerun_summary.md`。

---

## 1. 实验设置

| 项 | 值 |
|---|---|
| 黄金集 | `evals/datasets/golden/sample_408.jsonl`（408 四科，含学科/章级知识点标注） |
| 消融样本 | 前 60 条（`--limit 60`） |
| 任务集 | 25 条（learn6 / method6 / practice4 / grade3 / explain3 / verify3） |
| 门禁全集 | 156 条 |
| 指标 | `kp_hit@k` / `kp_mrr`（章级知识点）；`category_hit@1` / `category_mrr`（学科级）；任务口径 `layer_hit` / `pack_nonempty_rate` |
| Embedding | TEI `BAAI/bge-m3`（dim=1024） |
| 文本模型 | 检索链 decompose/HyDE + 答案生成：`dashscope:qwen3.7-flash`（`LLM_MODEL`）<br>RAGAS judge：`dashscope:qwen3.8-max-0902`（`RAGAS_JUDGE_MODEL`，强制关 thinking —— `answer_relevancy` 需 `n>1`）<br>agent 层：`dashscope:qwen3.8-max-0902`（`DEFAULT_MODEL`） |
| Rerank | 默认关（本轮对照单独开） |

> **口径提醒**：学科级 `category_hit@k` 易饱和，敏感指标是 **kp_mrr** 与任务口径。
> 组件消融 Δ 存在 run-to-run 波动（见 §2.2），引用时用**本轮数字**，勿混旧表。

---

## 2. 消融实验（检索组件）

**复现**：`uv run python scripts/ablation_retrieval.py --limit 60 --configs full,no_bm25,no_metadata,no_decompose,no_hyde,vector_only,plus_topup`
**归档**：`evals/results/retrieval/ablation/component_ablation.json`

| 配置 | kp_hit@k | kp_mrr | Δ kp_mrr | cat@1 | 证据数 |
|---|---|---|---|---|---|
| **full（基线）** | **1.000** | **0.9625** | — | 0.983 | 5.65 |
| no_bm25 | 0.983 | 0.9000 | **−0.062** | 0.950 | 5.73 |
| no_metadata | 1.000 | 0.9417 | **−0.021** | 0.950 | 5.77 |
| no_decompose | 1.000 | 0.9625 | 0 | 0.983 | 5.65 |
| no_hyde | 1.000 | 0.9625 | 0 | 0.983 | 5.65 |
| vector_only | 0.983 | 0.9306 | **−0.032** | 0.933 | 5.67 |
| plus_topup | 1.000 | 0.9625 | 0 | 0.983 | **8.83** |

> **V-2026-10-02**（§18）。vector_only 较 V-2026-10-01 明显改善（kp_hit 0.967→**0.983**、
> kp_mrr 0.914→**0.931**）——正是排序方向修复（§18.2 #3）的直接效果：向量路由此前返回**最不相似**的 k 条。
> ⚠️ vector_only 是唯一有非零 run-to-run 抖动的配置（§13：kp_hit ±0.010），故其数值以本节归档为准。

### 2.1 真·重排对照（`RERANK_ENABLED=true`）

**归档**：`evals/results/retrieval/ablation/rerank_compare.json`

| 配置 | kp_mrr | 证据数 |
|---|---|---|
| full（rerank on） | **0.975** | 4.03 |
| no_rerank | 0.9625 | 5.62 |
| **Δ（rerank 带来）** | **+0.012** | −1.59 |

### 2.2 消融结论（论文可直接写）

1. **多路召回正贡献**：vector_only 相对 full **kp_mrr −0.032**；
   BM25 **−0.062** > 元数据 **−0.021**。旧表「元数据贡献最大（−0.113）」**不成立**。
2. **查询分解 / HyDE 仍无增益**：去掉后指标逐位不变。诚实结论——复杂度未兑现。
3. **L2 preferred top-up 只增加覆盖**（证据数 5.65→8.83），不改善排序指标。
4. **重排为弱正收益（+0.012）**，与更早的 −0.046 **符号相反**。
   不宜写死「负优化」；准确表述：**在本黄金集上收益不稳定，默认关闭**。

---

## 3. Legacy 资产池策略（三策略对比）

**复现**：`uv run python scripts/legacy_runtime_compare.py`
**归档**：`evals/results/retrieval/legacy_runtime/legacy_runtime.json`

| 策略 | 层精度 pack（6 probe 均值） | legacy 占坑 |
|---|---|---|
| keep | 0.396 | 29 |
| downrank | 0.438 | 27 |
| **drop / exclude（采用）** | **1.000** | 0 |

**结论**：调权重治不了数据治理问题；**真删 legacy 后层精度 → 1.000**。
采用 `legacy_policy=exclude`（learn/method/practice/verify）+ `fallback`（grade/explain）。

---

## 4. 检索质量门禁基线（156 条全集）

**复现**：`PYTHONPATH=src uv run python -m evaluation.retrieval_gate`
**归档**：`evals/baselines/retrieval_baseline.json`（fake-embedding 口径）

本轮运行：**门禁通过**。注意 `kp_mrr` 当前 0.6636 略低于基线 0.6698 仍判通过——
若门禁本意是「不低于基线」，需确认容差口径（`rerun_summary.md` 问题 #8）。

| 指标 | 基线 |
|---|---|
| n_queries | 156 |
| category_hit@1 | 0.904 |
| kp_hit@k | 0.865 |
| kp_mrr | 0.670 |
| empty_result_rate | 0.0 |

> 该基线为**回归门禁**，非最优值声明。语义质量用真实 embedding 的消融（§2/§9）。

---

## 5. RAGAS 生成质量（V-2026-10-02 · 全量 20 条）

**口径**：`evals/datasets/ragas/ragas_paired20.jsonl`（20 条 = 4 类型 × 5）；
生成 `dashscope:qwen3.7-flash`；**judge `dashscope:qwen3.8-max-0902`（强制关 thinking）**；
k=5 · `--no-rerank`（与冻结检索版本同口径）；真实 bge-m3。

**复现**：`PYTHONPATH=src uv run python -m evaluation.cli --dataset evals/datasets/ragas/ragas_paired20.jsonl --sample-per-type 5 --no-rerank --include-details --tag final`
**整理**：`uv run python scripts/ragas_report.py --tag final`
**归档**：`evals/results/generation/ragas/`（`raw.jsonl` / `metrics.json` / `summary.md`）

### 5.1 总体（四项均 n=20，无 judge 掉样）

| 指标 | **冻结版 V-2026-10-02** | 修复前三项检索缺陷时 | Δ |
|---|---|---|---|
| faithfulness | **0.7588** | 0.7595 | −0.001 |
| context_precision | **0.6840** | 0.7318 | −0.048 |
| context_recall | **0.4000** | 0.4625 | −0.063 |
| answer_relevancy | **0.5994** | 0.5324 | **+0.067** |

### 5.2 分查询类型（冻结版）

| query_type | faithfulness | context_precision | context_recall | answer_relevancy |
|---|---|---|---|---|
| **concept** | **1.000** | **0.817** | 0.633 | **0.792** |
| grade | 0.708 | 0.823 | 0.550 | 0.707 |
| code | 0.807 | 0.478 | 0.350 | 0.292 |
| **generate** | 0.521 | 0.619 | **0.067** | 0.606 |

### 5.3 结论

1. **concept 质量最高**（faith **1.000** / ansR 0.792）——与任务策略收益最大的类型一致。
2. **answer_relevancy 提升 +0.067**（code 0.136→**0.292**）——排序方向修复后检索命中更精准，
   答案更切题。
3. **context_precision / context_recall 各降约 0.05–0.06**：排序修复让证据更「近邻」，
   但也更**集中**，对「参考答案覆盖率」略有不利。**样本每类 n=5，不作显著性判断**。
4. **generate 的 context_recall 0.067、code 的 answer_relevancy 偏低属口径失配**：
   - generate：reference 是题面、系统输出**新题** → `context_recall` 语义不成立
   - code：`answer_relevancy` 靠「答案反推问题」，源码无法反推 → 系统性偏低

### 5.4 引用纪律（重要）

- ❌ 不可写「context_recall 0.40 = 检索召回不足」（generate 整类为口径失配）
- ❌ 不可写「answer_relevancy 0.60 = 答案不切题」（code 整类为口径失配）
- ✅ 可写「concept 类 QA 最优；generate/code 的自动指标存在适用性限制」
- ⚠️ 每类仅 5 条，**不作显著性判断**；两版本差异同样不作显著性结论

> RAGAS 与检索指标不冲突、互为补充：前者答「证据有没有被用好」，后者答「证据找没找到」。

---

## 6. Agent 行为质量（软指标 · V-2026-10-02）

**复现**：`uv run python scripts/agent_behavior_gate.py`
**归档**：`evals/results/system_validation/agent_behavior/agent_behavior_quality.json`

- 硬安全（泄漏/empty 硬教/无来源确认/编造页码）：**8 case 全 PASS**
- 软指标 `quality_score=0.1222`（evidence_usage 均值；该值受生成温度影响有 run-to-run 波动）
- 三态 FULL/THIN/EMPTY 均 PASS

> State 闭环（`langgraph_state/state_gate.json`，4/4 PASS）**不依赖检索链**，
> 仍为 2026-09-30 录制，属可接受口径。

---

## 7. 一页结论（论文第 5 章可用）

| 主张 | 证据 | 数字（V-2026-10-02） |
|---|---|---|
| 多路召回优于纯向量 | §2 | vector_only **−0.035** |
| BM25 有正贡献 | §2 | no_bm25 **−0.062** |
| legacy 池策略必要 | §3 | 层精度 0.40→**1.000** |
| 系统稳定可回归 | §4/§6 | 门禁过 · agent 8/8 |
| 生成侧质量（concept 最优） | §5 | faith **0.759** · ansR **0.599** · concept faith **1.000**（n=20，V-2026-10-02） |
| 三层服务不同任务 | §9–§11 | learn→L1 / method→L2 / grade·verify→L3 |
| 任务×层策略交叉交互 | §12 | 错配偏好 prefer_l1 MACRO 0.347 vs ours 0.944 |
| pack sufficiency | §12.3/§15.7 | 兜底后全任务 nonempty=**1.000**（修复前 0.25） |
| 基础 RAG 对比 | §11 | kp_mrr **+0.088** |
| 消融可复现 | §13 | full/no_bm25/no_metadata kp_mrr **std=0** |
| 阈值稳健（full） | §14 | 五档指标不变；弱路由误杀可 0.9× 恢复（**不改默认**） |
| 负面/不稳（如实） | §2.1 | rerank **符号不稳**（+0.012 / 更早 −0.046） |
| 负面（如实） | §2 | decompose / HyDE 无增益 |
| 口径修正 | §18 | 排序方向 bug + 黄金集标注补全（§18.2） |

---

## 8. 归档索引（规范名）

| 路径 | 内容 |
|---|---|
| `evals/results/retrieval/ablation/component_ablation.json` | 组件消融 |
| `evals/results/retrieval/ablation/rerank_compare.json` | 重排对照 |
| `evals/results/retrieval/ablation/task_layer_ablation.json` | Task-aware |
| `evals/results/retrieval/ablation/basic_rag_compare.json` | 基础 RAG |
| `evals/results/retrieval/layer_policy/layer_ablation.json` | L1/L2/L3 |
| `evals/results/retrieval/layer_policy/task_mode_x_layer_policy.json` | 交互矩阵 |
| `evals/results/retrieval/legacy_runtime/legacy_runtime.json` | legacy 三策略 |
| `evals/results/retrieval/ablation/component_variance/` | 消融方差（summary.json） |
| `evals/results/retrieval/ablation/threshold_sensitivity/` | E-next 阈值敏感度 |
| `evals/baselines/` | 门禁基线 |
| `evals/results/generation/ragas/` | RAGAS（**2026-10-01 完成，n=20**） |
| `evals/reports/rerun_summary.md` | 本轮问题清单 |

---

## 9. L1/L2/L3 分层消融

**复现**：`uv run python scripts/ablation_retrieval.py --limit 60 --configs full,no_l1,no_l2,no_l3,l1_only,l2_only,l3_only,no_legacy,legacy_only`
**归档**：`evals/results/retrieval/layer_policy/layer_ablation.json`

### 9.1 逐层剔除 / 单层保留

| 配置 | kp_hit@k | kp_mrr | Δ kp_mrr | empty |
|---|---|---|---|---|
| **full** | 1.000 | **0.9625** | — | 0.0 |
| no_l1 | 1.000 | 0.9556 | −0.007 | 0.0 |
| no_l2 | 1.000 | 0.9514 | −0.011 | 0.0 |
| no_l3 | 1.000 | 0.9617 | −0.001 | 0.0 |
| l1_only | 0.983 | 0.9556 | −0.007 | 0.0 |
| l2_only | 0.783 | **0.7194** | −0.243 | 0.0 |
| l3_only | 0.000 | 0.000 | −0.963 | **0.983** |
| no_legacy | 0.983 | 0.8988 | −0.064 | 0.0 |
| legacy_only | 1.000 | 0.9450 | −0.018 | 0.0 |

### 9.2 结论（任务导向，非单一指标）

核心叙事：三层不是为了提升同一个检索指标，而是满足**不同任务下的证据组织与访问控制**。

| 任务 | 应偏向的层 | 设计对应 |
|---|---|---|
| learn | L1 | preferred_layers=[basic, advanced] |
| method | L2 | preferred_layers=[advanced, basic] |
| practice | L2+L3 | legacy_policy=exclude，出题走题库 |
| grade | L3 | exam_resources.answer=allowed |
| verify | L3 | exam_resources.question=allowed, answer=forbidden |

单指标（kp_mrr）只覆盖「知识点检索」切片：

1. **L1 提供主要语义覆盖**（l1_only 0.956）：probe 偏学习/概念题，不外推到全部任务。
2. **L2 方法层覆盖不足**（l2_only 0.7194）：与 coverage analysis 互相印证。
3. **L3 面向考试资源，不适合作通用知识解释库**（kp_mrr 0、empty 98%）：
   chunk 是题干/选项/答案/解析，缺定义原理推导；在 grade/verify 下不可替代。

**不要写**：~~「三层高度冗余」~~ · ~~「L3 不能当知识库」~~

**L3 待补任务专有指标**：exam_hit@k · question_id recall · answer availability

---

## 10. Task-aware Layer Ablation

**对照**：
- baseline = L1/L2/L3 平铺 + legacy=include
- ours = task_mode → preferred_layers → legacy_policy

**复现**：`uv run python scripts/task_layer_ablation.py`
**归档**：`evals/results/retrieval/ablation/task_layer_ablation.json`

### 10.1 任务专有指标

| task_mode | 目标层 | baseline | ours | Δ | 泄漏 b/o |
|---|---|---|---|---|---|
| learn | L1 basic | 0.833 | **1.000** | **+0.167** | 0.00/0.00 |
| method | L2 advanced | 1.000 | 1.000 | 0 | 0.00/0.00 |
| practice | L2+L3 | 1.000 | 1.000 | 0 | **0.25/0.00** |
| grade | L3 exams | 0.667 | 0.667 | 0 | n/a |
| explain | L3 exams | 1.000 | 1.000 | 0 | n/a |
| verify | L3 exams | **1.000** | **1.000** | 0 | 0.00/0.00 |
| **MACRO** | | 0.917 | **0.944** | **+0.028** | |

> **2026-10-01 更新（P0' top-up eligibility）**：`task_layer` / `task_mode_layer_policy`
> 与 Agent 路径对齐，统一传入 `filter=policy.eligibility_where()`；
> `layer_recall.topup_preferred_layers` 合并同一 where，不再绕过 doc_role。
> **verify 0.333→1.000**（BST 类 query 不再被 top-up 塞入 `exam_answer` 后裁空）。
> baseline 也因口径对齐而抬升，故 ours 相对 Δ 变小——增益主要在 legacy/access control。

### 10.2 结论

1. 任务感知层偏好有效：learn +0.333、method +0.167。
2. access control 消除泄漏：practice 0.25→0。
3. L3 在 grade/explain 已可达；verify 命中仍低（0.333）= 待优化。
4. **口径澄清**：相对 baseline 的增益**主要来自 legacy/access control**，
   不是 `preferred_layers` 排序单独贡献（见 §12）。

---

## 11. 基础 RAG 消融

**对照**：
- **basic_rag** = 语义向量 top-k（无 BM25/元数据/任务策略；层平铺、legacy 同池）
- **ours** = 完整系统

**复现**：`uv run python scripts/basic_rag_ablation.py --limit 60`
**归档**：`evals/results/retrieval/ablation/basic_rag_compare.json`

### 11.1 检索口径

| arm | kp_hit@k | kp_mrr | cat@1 | cat_mrr | 证据数 |
|---|---|---|---|---|---|
| basic_rag | 0.967 | 0.875 | 0.917 | 0.956 | 4.73 |
| **ours** | **1.000** | **0.9625** | **0.983** | **0.992** | 5.67 |
| **Δ** | +0.033 | **+0.0875** | +0.067 | +0.036 | +0.93 |

### 11.2 任务口径（V-2026-10-02）

| task_mode | 目标层 | basic | ours | Δ |
|---|---|---|---|---|
| learn | L1 | 0.833 | **1.000** | **+0.167** |
| method | L2 | 1.000 | 1.000 | 0 |
| practice | L2+L3 | 1.000 | 1.000 | 0 |
| grade | L3 | 0.667 | 0.667 | 0 |
| explain | L3 | 1.000 | 1.000 | 0 |
| verify | L3 | 1.000 | 1.000 | 0 |
| **MACRO** | | 0.917 | **0.944** | **+0.028** |

### 11.3 结论

1. 相对朴素向量 RAG：kp_mrr **+0.0875**、kp_hit +0.033、cat@1 +0.067。
2. 任务口径：learn +0.167（其余已同基线）。
3. 平均证据 4.73→5.67。

> 论文「对比实验」主表：同黄金集、同指标、仅系统配置不同。

---

## 12. Task Mode × Layer Policy 交互实验

**对照**（安全字段冻结，只动 `preferred_layers`）：
flat（全层）/ ours（任务映射）/ prefer_l1 / prefer_l2 / prefer_l3

**复现**：`uv run python scripts/task_mode_layer_policy.py`
**归档**：`evals/results/retrieval/layer_policy/task_mode_x_layer_policy.json`

### 12.1 主表（flat vs ours，论文表 6，V-2026-10-02）

| task_mode | flat hit | ours hit | flat prec | ours prec | flat pack | ours pack |
|---|---|---|---|---|---|---|
| learn | 1.000 | 1.000 | 0.583 | 0.583 | 1.000 | 1.000 |
| method | 1.000 | 1.000 | 0.606 | 0.606 | 1.000 | 1.000 |
| practice | 1.000 | 1.000 | 0.542 | 0.542 | 1.000 | 1.000 |
| grade | 0.667 | 0.667 | 0.267 | 0.267 | 1.000 | 1.000 |
| explain | 1.000 | 1.000 | 0.378 | 0.378 | 1.000 | 1.000 |
| verify | **1.000** | **1.000** | 0.333 | **0.417** | 1.000 | 1.000 |

### 12.2 附表：固定单层偏好（layer_hit_rate）

| task_mode | 目标层 | flat | ours | prefer_l1 | prefer_l2 | prefer_l3 |
|---|---|---|---|---|---|---|
| learn | L1 | 1.000 | 1.000 | 1.000 | 0.833 | 1.000 |
| method | L2 | 1.000 | 1.000 | 0.500 | 1.000 | 1.000 |
| practice | L2+L3 | 1.000 | 1.000 | 0.250 | 1.000 | 1.000 |
| grade | L3 | 0.667 | 0.667 | 0.000 | 0.000 | 0.667 |
| explain | L3 | 1.000 | 1.000 | 0.333 | 0.333 | 1.000 |
| verify | L3 | **1.000** | **1.000** | 0.000 | 0.000 | **1.000** |
| **MACRO** | | **0.944** | **0.944** | 0.347 | 0.528 | **0.944** |

> prefer_l3 经 sufficiency 兜底后与 flat 持平——**层偏好错配的「空包」伤害已消除**；
> 剩余交互伤害只由 prefer_l1 / prefer_l2（合规但错层）体现。

### 12.3 附表：pack_nonempty_rate（sufficiency）

| task_mode | flat | ours | prefer_l1 | prefer_l2 | prefer_l3 |
|---|---|---|---|---|---|
| learn | 1.000 | 1.000 | 1.000 | 1.000 | **1.000** |
| method | 1.000 | 1.000 | 1.000 | 1.000 | **1.000** |
| practice | 1.000 | 1.000 | 1.000 | 1.000 | **1.000** |
| grade | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| explain | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| verify | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |

**修复前**：prefer_l3 的 top-up/排序把 exams 顶进候选，eligibility 裁掉 → **n_pack=0**
（practice 0.25 / method 0.333 / learn 0.667）。**修复后全任务 1.000**（见 §15.7）。

### 12.4 结论

1. **pack sufficiency 已保底**：全任务 × 全策略 nonempty=1.000。
2. **交互伤害仍在**（合规但错层）：prefer_l1 MACRO 0.347 · prefer_l2 0.528 vs ours 0.944。
3. **ours**：hit 与 flat 持平 + verify 包纯度更高（0.333→0.417）。
4. 层偏好单独**不抬 hit**；价值在包构成、缺层 top-up、避免错配掏空。
5. §10 的增益主要来自 legacy/access control，非排序单独贡献。

### 12.5 叙事要点（论文）

> 任务与层策略存在交叉交互：错误的全局层偏好会在对不齐的任务上压低目标层命中，
> 并在 access control 裁剪后掏空证据包（pack_nonempty_rate 可低至 0.25）；
> 任务映射保持全任务非空证据包，在不损失命中的前提下提升包纯度，
> 并与 legacy 池策略/access control 协同，形成任务条件下的证据组织。

---

## 13. 组件消融方差（P0.1，2026-09-30）

**问题**：单轮 Δ 是否可信？run-to-run 波动有多大？

**设计**：3 个**独立进程** × 4 配置 × 60 golden（无 seed、无同进程 loop）。
Δ 为**逐 run 配对差**（ablation_i − full_i）。环境冻结。

**复现**：`uv run python scripts/component_variance.py`
**归档**：`evals/results/retrieval/ablation/component_variance/`（`run{1,2,3}.json` 明细 + `summary.json` 汇总入口）

### 13.1 mean ± std（n=3）

| config | kp_hit | kp_mrr | cat@1 | cat_mrr | evidence |
|---|---|---|---|---|---|
| full | 1.000±0.000 | 0.963±0.000 | 0.983±0.000 | 0.992±0.000 | 5.650±0.033 |
| no_bm25 | 0.983±0.000 | 0.900±0.000 | 0.950±0.000 | 0.975±0.000 | 5.733±0.000 |
| no_metadata | 1.000±0.000 | 0.942±0.000 | 0.950±0.000 | 0.975±0.000 | 5.772±0.010 |
| vector_only | 0.994±0.010 | 0.935±0.013 | 0.939±0.010 | 0.965±0.009 | 5.678±0.019 |

### 13.2 配对 Δ vs full

| Δ | kp_hit | kp_mrr | cat@1 | cat_mrr |
|---|---|---|---|---|
| Δ no_bm25 | −0.017±0.000 | **−0.062±0.000** | −0.033±0.000 | −0.017±0.000 |
| Δ no_metadata | +0.000±0.000 | **−0.021±0.000** | −0.033±0.000 | −0.017±0.000 |
| Δ vector_only | −0.006±0.010 | **−0.028±0.013** | −0.044±0.010 | −0.026±0.009 |

### 13.3 结论

1. **消融非常稳**：full/no_bm25/no_metadata 的 kp_mrr std=0；仅 vector_only 有非零 std（±0.013）。
2. 论文表 2 可写 `mean±std`；**贡献排序：BM25 > vector_only > metadata**。
3. 方差实验**解释不了**旧表 −0.113→−0.021 的跨轮漂移（那是跨代码/跨索引差异，不是随机抖动）。
4. **vector_only 是唯一有抖动的配置**（kp_hit ±0.010、kp_mrr ±0.013）——
   其单轮数值不宜与其它配置等量齐观，跨批次比较时须看本节的 std。

> 脚注：n=3 独立进程；std 为运行间系统非确定性，不作为统计显著性检验。

---

## 14. E-next · RRF Threshold Sensitivity（2026-09-30）

**问题**：阈值是否在误杀已召回的正确证据？（由 q052 诊断引出）

**设计**：固定 60 golden / 索引 / embedding / top-k，**只改** `effective_threshold` 乘子
`{1.0, 0.95, 0.90, 0.85, 0}`。无 LLM。**不改默认 threshold**。

**复现**：`uv run python scripts/threshold_sensitivity.py --arm full,vector_only`
**归档**：`evals/results/retrieval/ablation/threshold_sensitivity/threshold_sensitivity.json`

### 14.1 full（主配置，V-2026-10-02）

| scale | kp_hit | kp_mrr | cat@1 | n_ev | fallback | q052 |
|---|---|---|---|---|---|---|
| 100%–off | **1.000** | **0.9625** | 0.983 | 5.67→6.28 | 0% | ✅ 全程 |

**full 对阈值不敏感**：指标五档相同，只涨证据数。

### 14.2 vector_only（弱路由对照，V-2026-10-02）

| scale | kp_hit | kp_mrr | cat@1 | n_ev | fallback | q052 |
|---|---|---|---|---|---|---|
| 100% | **0.983** | 0.9222 | 0.933 | 5.70 | 1.67% | ❌ |
| 95% | 0.983 | 0.9222 | 0.933 | 5.77 | 0% | ❌ |
| **90%** | **1.000** | **0.9306** | 0.933 | 5.93 | 0% | **✅** |
| 85% | 1.000 | 0.9306 | 0.933 | 6.17 | 0% | ✅ |
| off | 1.000 | 0.9306 | 0.933 | 6.28 | 0% | ✅ |

**拐点在 90%**：q052 与 kp_hit 在 0.9× 恢复，再放松无收益；cat@1 不降。

> ⚠️ **边界抖动如实披露**：同一配置（100% 档）在不同批次出现过
> **kp_hit 0.9833 / 1.000**、**q052 ❌/✅** 两种结果 —— 与 §13 测得的
> vector_only kp_hit ±0.010 一致。**该结论是边界性的**，不宜作强断言。

### 14.3 结论

1. 阈值在 **full 下是有效质量控制**（稳健、不误杀），松紧只增证据数（5.67→6.28）。
2. 在 **vector_only/弱融合**下仍会误杀边界样本：q052 在 100% 档检出为失败，
   0.9× 后恢复 —— 但见上「边界抖动」，该差异处在测量噪声量级。
3. **不改默认 threshold**；问题在 **RRF 量纲与可达上限**（见 `postprocess._rrf_scale_needed`），
   不是阈值高低。

### 14.4 q052 摘要（诊断，不再继续优化）

- vector_only：目标已入池（rank 2）→ `dropped_by=rrf_threshold`（0.0857<0.088）→ 保底 top-1 错学科
- full：L1 目标全程 rank 1 存活；多路召回救回
- **归因**：召回到了但被阈值滤掉；非召回失败

---

## 15. 版本节点 V-2026-10-01 · top-up eligibility 对齐（冻结）

**冻结内容**：证据资格边界修复。**不含** exam 专用召回器。

### 15.1 改了什么

| 文件 | 变更 |
|---|---|
| `src/rag/layer_recall.py` | `topup_preferred_layers(..., eligibility_where=)`；`merge_where_filters(kb_depth, eligibility_where)` |
| `src/rag/retriever.py` | top-up 传入主检索同一 `filter`（= `policy.eligibility_where()`） |
| `scripts/task_layer_ablation.py` | 补传 `filter=policy.eligibility_where()`（口径对齐） |
| `scripts/task_mode_layer_policy.py` | 同上 |
| `scripts/topup_eligibility_gate.py` | **新增**：4+1 场景资格回归门禁 |

**结构约定**：policy 决定「什么资源有资格进来」，layer_recall 只决定「从哪些层补」。

### 15.2 修复前问题

verify 的 `exam_resources.answer=forbidden` 被 top-up 绕过：top-up 只按 `kb_depth=exams`
把 `exams/*/answer.md` 拉进池，随后 Evidence Policy 裁掉 → **L3 空**（BST 真题 query）。

### 15.3 回归证据

| 验证 | 结果 |
|---|---|
| `topup_eligibility_gate.py` | 4+1 场景 **全 PASS**（answer 不进池/包、items 可进、grade 保持、learn/method/practice 不绕过） |
| BST「考过哪些真题」 | 修复前 L3=answer 被裁空 → **2× exam_item 进包** |
| `leakage_gate` / `mode_layer_gate` / `retrieval_gate` | 全过 |

### 15.4 指标变化（§10 已更新）

| 项 | 修复前 | 修复后 |
|---|---|---|
| verify layer_hit | 0.333 | **1.000** |
| Task-aware MACRO（ours） | 0.833 | **0.944** |
| TMLP MACRO（flat/ours） | 0.833 | **0.944** |

> baseline 同步抬升，因实验路径原先未传 eligibility——增益主要来自 legacy/access control。

### 15.5 决策树结论（本轮）

| 检查项 | 结果 | 结论 |
|---|---|---|
| prefer_l3 空包是否因 P0' 恢复？ | **未恢复**（practice nonempty 仍 0.25） | → 已实施 sufficiency 兜底（§15.7） |
| verify 是否需 exam 专用召回？ | **不需要**（items 在池内 rank 6–9，能进包） | 维持当前路由 |
| verify 实验口径是否与 Agent 一致？ | 已对齐（同传 `eligibility_where`） | — |

### 15.6 P0'.1 补充：preferred 层与资格冲突时的 top-up 回退

**问题**：`preferred_layers=['exams']` 而 exams 不合规时，top-up 只按 `kb_depth=exams`
找（被 where 挡空），且**不为合规层补**，主池可能只剩 legacy → 包被掏空。

**修法**：`aretrieve_evidence_with_retry(..., eligible_layers=)`（新增可选参数）。
preferred 层**全部不合规**时收敛到 `eligible_layers`；生产 policy 恒一致，不影响默认行为。
资格真源：`TaskPolicy.eligible_semantic_layers()`（basic/advanced 恒允许；exams 需任一资源 allowed）。

### 15.7 P0'.1 补充：Evidence Pack sufficiency 兜底

**问题**：错误层偏好把 eligibility 禁止的资源顶进 pack，Evidence Policy 全裁 → **n_pack=0**。

**修法**（`evidence_policy.finalize_with_layer_ranking`）：
包内已无合规项时，从 `main_items` 按 score 回填**合规项**。

- 新增 `pack_blocked(policy, ev)`：与 Evidence Policy 的剔除条件同源（eligibility / 缺题干 / explanation 隐藏）
- 只回填 `main_items`（已按 `legacy_policy` 过滤）→ **不引入被排除资产，不放松安全**
- 记入 `layer_pack.sufficiency_refill` 与 release flags（不静默）

**验证**：`scripts/sufficiency_gate.py`（错误偏好 n_pack≥1 且无被禁资源；ours 不回归）

**结果**：`pack_nonempty_rate` **全任务 × 全策略 = 1.000**；
prefer_l3 MACRO 0.681 → **0.944**（与 flat/ours 持平）。
leakage / mode_layer / retrieval_gate / topup_eligibility_gate 全过。

> **叙事更新**：层偏好错配的「空包」伤害已由兜底消除；
> 残余交互伤害只由 prefer_l1 / prefer_l2（合规但错层）体现——**这才是排序偏好的真实代价**。

---

## 16. L2 覆盖归因（2026-10-01，只分析）

**问题**：`l2_only kp_mrr 0.7167`，L2 是分层短板。

**复现**：`uv run python scripts/l2_coverage_analysis.py`
**归档**：`evals/results/retrieval/ablation/l2_coverage.json`（**V-2026-10-02 重跑**）

### 16.1 L2 数据规模

| 项 | 值 |
|---|---|
| L2 chunk 总数 | **98** |
| 按学科 | DS 38 · OS 21 · CO 20 · CN 19 |
| 章级分布 | 树与二叉树 8 · 文件管理 8 · 线性表 7 · 进程管理 7 · 查找 6 · 图 5 · 排序 5 · 存储系统 5 · 栈和队列 4 … |

**结论：数据存在，无整体性覆盖缺口。**

### 16.2 method query 逐条归因（V-2026-10-02）

| query | 期望学科 | L2 池内 rank | L2 进包 | 归类 |
|---|---|---|---|---|
| BST 删除双支结点 | DS | 3 | ✅ 1 | B1 OK |
| 银行家算法 | OS | 5 | ✅ 1 | B1 OK |
| LRU 实现 | OS | 7,10 | ✅ 2（**1 污染** CO cache） | B1 + 污染 |
| Dijkstra | DS | 4 | ✅ 1 | B1 OK |
| 平衡二叉树判定 | DS | 6,9 | ✅ 2（**1 污染** CN transport） | B1 + 污染 |
| TCP 拥塞控制 | CN | 8–10 | ✅ 3（**2 污染** OS/CO） | B1 + 污染 |

**6/6 全部召回到且进包** → **不是 retrieval miss**。
> 与修复前对比：进包 L2 **13→10 条**（排序修复后检索更准，进包的 L2 更少），
> 但**错学科条数 5→4**，污染**率**基本持平。

### 16.3 跨学科污染量化

| 指标 | V-2026-10-02 | 修复前 |
|---|---|---|
| pack 中 L2 chunk | **10** | 13 |
| 其中错学科 | **4** | 5 |
| 污染率 | **40.0%** | 38.5% |

### 16.4 结论

1. L2 短板**不是数据缺口**（98 chunk，17 章齐全），**不是召回失败**（6/6 进包）。
2. 真因是 **L2 跨学科污染（40.0%）**：`preferred_layers=[advanced,basic]` 提升**所有** advanced，
   而 L2 池小（98），错学科 advanced 靠通用词面分挤进 pack。
3. 这直接压低 `l2_only kp_mrr`：目标章与错学科章竞争 top-k。
4. **本版本未修**（§18.4）。若要动，方向是**学科感知的 L2 排序/过滤**（如 `preferred_layers`
   叠加学科约束），而非新增数据。
5. **影响面与「修不修」输入**见 `evals/reports/l2_impact_analysis.md`（V-2026-10-02）：
   污染伤的是**证据包纯度与 `l2_only`**（0.7194），full 仅 −0.011；任务侧
   `layer_hit` **对学科盲**，不能当 L2 质量证据。生成侧是否受影响**未测**。

---

## 17. 检索版本冻结 · V-2026-10-01（RETRIEVAL-FROZEN）

> **冻结含义**：以下配置与实现状态即论文实验所用版本。冻结后**不再改检索链**
> （阈值 / 层策略 / 路由 / 切分 / embedding / rerank / evidence policy）。
> 后续若有改动，必须作为**新版本节点**并重跑受影响的实验。

### 17.1 冻结配置

| 项 | 值 |
|---|---|
| 黄金集 | `evals/datasets/golden/sample_408.jsonl`（156 条，其中 60 条用于消融） |
| 任务集 | 25 条（learn6/method6/practice4/grade3/explain3/verify3） |
| 生成集 | `evals/datasets/ragas/ragas_paired20.jsonl`（20 条，4 类 × 5） |
| Embedding | TEI `BAAI/bge-m3`（dim=1024，真实） |
| Rerank | **默认关闭**（`RERANK_ENABLED=false`） |
| 文本模型 | `dashscope:qwen3.7-flash`（`LLM_MODEL`）｜`dashscope:qwen3.8-max-0902`（`DEFAULT_MODEL`） |
| 语义缓存 | **默认关闭** |
| top-k | 5（消融/任务口径） |
| RRF 阈值 | 默认（**未调整**，见 §14） |
| 层策略 | `task_mode → preferred_layers → legacy_policy`（§10） |
| 资格边界 | 召回 `eligibility_where` + top-up 同源 + pack sufficiency 兜底（§15） |

### 17.2 冻结时点的改动清单（相对上一版本）

1. **top-up eligibility 对齐**（§15.1–15.3）：`layer_recall` 合并 `eligibility_where`；
   实验路径与 Agent 路径统一传 `filter` + `eligible_layers`。
2. **pack sufficiency 兜底**（§15.6–15.7）：`eligible_semantic_layers()` +
   `pack_blocked()` + 空包回填合规项。
3. 新增门禁：`topup_eligibility_gate` · `sufficiency_gate`。

### 17.3 冻结时点的验收（全过）

| 门禁 | 结果 |
|---|---|
| `retrieval_gate`（156 条） | 通过（所有指标不低于基线） |
| `probe_gate` | 通过 |
| `leakage_gate` | PASS |
| `mode_layer_gate` | PASS |
| `topup_eligibility_gate` | 4+1 场景 PASS |
| `sufficiency_gate` | PASS（nonempty 全 1.000） |

### 17.4 冻结基线指标（最终 TMLP，2026-10-01）

| 策略 | MACRO layer_hit | pack_nonempty | leakage |
|---|---|---|---|
| **flat** | **0.944** | 1.000 | 0 |
| **ours** | **0.944** | 1.000 | 0 |
| prefer_l1 | 0.319 | 1.000 | 0 |
| prefer_l2 | 0.500 | 1.000 | 0 |
| prefer_l3 | 0.944 | 1.000 | 0 |

**归档**：`evals/results/retrieval/layer_policy/task_mode_x_layer_policy.json`

### 17.5 已知未修问题（冻结不阻断，如实记录）

| 问题 | 状态 |
|---|---|
| L2 跨学科污染 **40.0%**（§16，V-2026-10-02 重测） | **未修**（明确推迟） |
| rerank 收益符号不稳（§2.1） | 未修，默认关 |
| decompose / HyDE 零增益（§2） | 未修，保留 |
| vector_only 下阈值误杀边界样本（§14） | 未修，full 不受影响 |

### 17.6 最终 retrieval 结果索引

| 文件 | 内容 | 出处 |
|---|---|---|
| `retrieval/ablation/component_ablation.json` | 组件消融 | §2 |
| `retrieval/ablation/rerank_compare.json` | 重排对照 | §2.1 |
| `retrieval/ablation/task_layer_ablation.json` | Task-aware | §10 |
| `retrieval/ablation/basic_rag_compare.json` | 基础 RAG 对比 | §11 |
| `retrieval/ablation/component_variance/{run1..3,summary}.json` | 消融方差（3 独立进程） | §13 |
| `retrieval/ablation/threshold_sensitivity/threshold_sensitivity.json` | 阈值敏感度 | §14 |
| `retrieval/ablation/l2_coverage.json` | L2 覆盖归因 | §16 |
| `retrieval/layer_policy/layer_ablation.json` | L1/L2/L3 分层 | §9 |
| `retrieval/layer_policy/task_mode_x_layer_policy.json` | Task × Layer 交互（**最终**） | §12/§17.4 |
| `retrieval/legacy_runtime/legacy_runtime.json` | legacy 三策略 | §3 |
| `system_validation/agent_behavior/agent_behavior_quality.json` | Agent 行为 | §6 |
| `system_validation/langgraph_state/state_gate.json` | State 闭环 | §6 |
| `generation/ragas/` | RAGAS（本轮跑） | §5 |

---

## 18. 检索版本冻结 · **V-2026-10-02**（现行 · 替代 §17）

> 触发：RAGAS 拒答归因（§16 后续）途中发现**三项检索缺陷 + 一处黄金集标注缺失**。
> 本节点记录修复与证据；§17 的 V-2026-10-01 **已被本节点取代**，
> §2/§9/§10/§11/§12/§13/§14/§5 的数字均已按本版本重跑。

### 18.0 ★ 版本锚点（可追溯链起点）

| 项 | 值 |
|---|---|
| **Git 标签** | ① **`V-2026-10-07`**（附注标签对象 `abc115b` → **落点 `0f24891`**，2026-10-07 18:53 +0800）<br>② **`V-2026-10-07B`**（**D9 补的第二个锚点**；标签对象 `bf37b6b` → **落点 `c70ed03`**，2026-10-08 00:22 +0800）—— **Step 9 全部数字所属的代码状态**<br>③ **`V-2026-10-08`**（**评测层修复完成、Final Gate 之前**；标签对象 `5471a9a` → **落点 `e65837a`**，2026-10-08 12:41 +0800）—— #28~#31 + D12(B) 全在里面；**数据集与 ② 相同**<br>④ **`V-2026-10-08B`**（**§6 Final Gate 实跑所用的代码与门槛状态**；标签对象 `beb833d` → **落点 `79ac38f`**，2026-10-08 13:35 +0800）—— D14/D15/D16 + §21 门槛定稿；**数据集与 ②③ 相同** |
| **检索修复提交** | **`1cc69b3`**（三项检索修复 + golden 补标落点） |
| **归档 code_version** | 检索类 **`d6eed4c`** · RAGAS 派生类 **`0479d6e`**（以各归档 `provenance.code_version` 为准） |
| **黄金集 sha256** | **`be98912a4c91fb88151640c82515127465031c1e79382b99c40e32311d6d1a66`**（156 条） |
| 生成集 | `evals/datasets/ragas/ragas_paired20.jsonl`（20 条） |
| 冻结日期 | 2026-10-02（标签落点 `e36c766`） |

**解析方式**（无需翻文档即可定位）：

```bash
git rev-parse "V-2026-10-02^{}"           # 标签落点 e36c766
git show V-2026-10-02 --stat              # 本节点完整状态
git show V-2026-10-02:docs/EXPERIMENTS.md # 该状态下的实验文档（含本节，不含 §19）
git rev-parse 1cc69b3                     # 检索三项修复的落点提交
```

> **与实验的关系**：检索三项修复落在 `1cc69b3`；此后 `33cdb8d`–`e36c766` 只加
> provenance 基础设施并按该版本重跑归档，**不动检索链**。归档内
> `provenance.code_version`（检索类 `d6eed4c` / RAGAS 派生类 `0479d6e`）
> 即论文数字所对应的代码版本；两者与 `1cc69b3` 的差异均为脚本/类型注解级，
> **无检索运行时行为差异**。
>
> **可追溯性已闭环（原「待补」，见 §18.6）**：归档 JSON 现已记录
> `code_version` / `golden_sha256` / `script` / `argv`，`freeze_precheck`
> 四层检查 **11/11 全 Y**，反查不再依赖本表。

### 18.1 改了什么

| # | 位置 | 改动 | 性质 |
|---|---|---|---|
| 1 | `rag/rag_utils.py` | 新增 `_DOMAIN_WORDS` + `ensure_jieba_domain_words()`：注册 9 个链表/线性表领域词 | 查询侧分词 |
| 2 | `rag/synonyms.py` | ① 新增 7 条「逆置」同义词；② 扩展守卫由「**子串**出现」改为「**已是分词结果**」 | 查询扩展 |
| 3 | `rag/routes.py` | `_raw_search` 向量分支排序 `-score` → **`score`**（Chroma score 是**余弦距离**，越小越好） | **排序 bug** |
| 4 | `evals/datasets/golden/sample_408.jsonl` L38 | 「什么是滑动窗口协议？」标签 `["传输层"]` → `["数据链路层","传输层"]` | **标注补全** |

### 18.2 各项的判定证据

**#1 jieba 误切**（实测）
```
「单链表就地逆置」 修复前 → ['单链', '表就', '地逆置']   ← 「逆置」不成词
                修复后 → ['单链表', '就地逆置']
```
只影响**查询侧**；入库切分不依赖 jieba，**无需重建索引**。

**#2 扩展守卫过粗**：标准词「逆置」只是「就地逆置」的**子串**，旧守卫据此永不追加 →
`expanded` 路由永远不带「逆置」。改判据后 `expanded` 含该词。

**#3 排序方向（决定性）**：用 chunk 原文检索自身，score = **0.0000**，
且集合 `hnsw:space=cosine` → **score 是距离**。原 `-score` 降序 = **返回最不相似的 k 条**：

| | 前 5 条 score |
|---|---|
| Chroma 原始（最近邻） | 0.3318 **← 目标** · 0.3579 · 0.3733 … |
| `_raw_search` 修复前 | **0.4212 · 0.4208 · 0.4198 …（15 条里最差）** |
| `_raw_search` 修复后 | 0.3318 **← 目标** · 0.3579 … |

影响 semantic / focus / expanded **三条向量路由**（BM25 不受影响）。
#16 目标 chunk 修复后：semantic **rank 1** · expanded rank 1 · focus rank 4。

**#4 标注口径（诊断结论）**：修 #1–#3 后 kp_hit 由 1.000 降至 0.983，**唯一掉分 query**：

| | pack 章节分布 | gold 标签命中 |
|---|---|---|
| 修复前 | 数据链路层×4 + **传输层(rank3)** | ✅ |
| 修复后 | **数据链路层×5**（含 `[停等与滑动窗口]`、SR、GBN、流量控制） | ❌ |

- gold 目标 `05_传输层.md`：召回池 rank **6** → `dropped_by=rerank_topn`（top_n=5）
- 另一合理章节 `03_数据链路层.md`：召回池 **rank 1** → survived
- **同文件内出现标签自相矛盾**：L163「滑动窗口协议（后退N帧）」标 **数据链路层**，
  而 L38 同一主题标 **传输层**；L32/L35（IP/MAC、ARP）本就使用**双标签**
  → 判定：**golden 集标注口径问题**，非检索退化。修正方式：补第二标签（不改 evaluation 代码）。

### 18.3 修复后指标（真 embedding · 60 条 · `full`）

| 口径 | V-2026-10-01 | **V-2026-10-02** |
|---|---|---|
| kp_hit | 1.000 | **1.000** |
| kp_mrr | 0.9514 | **0.9625** ↑ |
| cat@1 | 0.9833 | 0.9833 |

门禁（156 条）：`kp_hit 0.8718`（基线 0.8654）· `kp_mrr 0.6761`（基线 0.6698）——**均高于基线，无需重录**。

### 18.4 已知未修（本版本不阻断）

| 问题 | 状态 |
|---|---|
| RRF 阈值 > 可达上限（#16 最后一层拦阻，`dropped_by=rrf_threshold`） | 未修（同 §14，属「不做清单」） |
| L2 跨学科污染 **40.0%** | 未修（§16） |
| rerank 收益不稳 · decompose/HyDE 零增益 | 未修 |

### 18.5 本节点重跑完成（2026-10-02）

| 实验 | 状态 | 归档 |
|---|---|---|
| 组件消融（§2） | ✅ | `component_ablation.json` |
| rerank 对照（§2.1） | ✅ | `rerank_compare.json` |
| 分层消融（§9） | ✅ | `layer_ablation.json` |
| Task-aware（§10） | ✅ | `task_layer_ablation.json` |
| 基础 RAG（§11） | ✅ | `basic_rag_compare.json` |
| TMLP（§12） | ✅ | `task_mode_x_layer_policy.json` |
| legacy（§3） | ✅ | `legacy_runtime.json` |
| 消融方差（§13） | ✅ 3 独立进程 | `component_variance/` |
| 阈值敏感度（§14） | ✅ | `threshold_sensitivity.json` |
| **RAGAS（§5）** | ✅ 仅冻结版跑 | `generation/ragas/` |

**门禁全过**：`retrieval_gate`（kp_hit **0.8718** / kp_mrr **0.6729–0.6761**，均高于基线；
区间的抖动源于已知 Chroma ANN 边界效应）· `probe_gate` · `leakage_gate` · `mode_layer_gate` ·
`topic_relevance_gate` · `topup_eligibility_gate` · `sufficiency_gate` ·
`policy_layer_evidence_proof`（6/6 ok）· `agent_behavior_gate`（8/8 PASS，quality 0.1473）

> **跨版本不可混引**：§17（V-2026-10-01）的数字与本节不可混用同一张表。

### 18.6 ★ 冻结前检查发现的**结构性缺口**（待修）

**四层可追溯链检查**（`uv run python scripts/freeze_precheck.py`）：

| 层 | 修复前 | **修复后（本版本）** |
|---|---|---|
| ④ 文档数字 → JSON | ✅ 通过 | ✅ 通过 |
| ③ JSON → 脚本/参数 | ⚠️ 有 `config_snapshot`，无生成脚本名 | ✅ **新增 `provenance.script` + `argv`** |
| ② JSON → 黄金集 | ⚠️ 只有路径，无哈希 | ✅ **新增 `provenance.golden_sha256`** |
| ① 节点 → 代码版本 | ❌ 零个归档记录 | ✅ **新增 `provenance.code_version`** |

**修复内容（已落地）**：新增 `src/evaluation/provenance.py`，提供 `build_provenance()`；
接入全部写归档的脚本（`ablation_retrieval` / `task_layer_ablation` / `basic_rag_ablation` /
`task_mode_layer_policy` / `legacy_runtime_compare` / `component_variance` /
`threshold_sensitivity` / `l2_coverage_analysis` / `agent_behavior_gate` /
`langgraph_state_gate` / `ragas_eval` / `ragas_report` / `retrieval_gate` 基线）。

每个归档现在自带：

```json
"provenance": {
  "recorded_at":    "2026-10-01T…Z",
  "code_version":   "d6eed4c",          // 代码目录有未提交改动时为 "<sha>-dirty"
  "golden_sha256":  "be98912a…",
  "script":         "scripts/ablation_retrieval.py",
  "argv":           ["--limit", "60", "--configs", "full,…"]
}
```

> **`code_version` 的 dirty 判定只看 `src/`、`scripts/`、`pyproject.toml`、`.env.example`**
> —— 不看结果归档。否则「刚跑完、归档未提交」会被误判成 `-dirty`，
> 把「代码有未提交改动」这个真正危险的信号淹没在噪声里。

**本版本归档的 `code_version`**：检索类 `d6eed4c` · RAGAS 派生类 `0479d6e`
（两者差异仅在 `scripts/ragas_report.py`，不影响检索链）。

---

## 19. 最终系统决策表（V-2026-10-02）

> **性质**：本节是 **V-2026-10-02 冻结之后的纯文档补充**（标签 `V-2026-10-02` 指向
> `e36c766`，**不含本节**）。内容是对 §2–§18 中已发生问题与决策的汇总，不引入新实验。
> 每行都可在本文件对应小节或 `evals/results/` 归档中反查。

### 19.1 已修（本版本）

| 问题 | 诊断 | 最终处理 | 证据 / 位置 |
|---|---|---|---|
| **q052（inode）纯向量下丢目标** | 向量路由**排序方向反了**：Chroma score 是余弦距离（越小越好），代码按 `-score` 降序 = **返回最不相似的 k 条** | 改升序取前 k | `rag/routes.py`；修后目标 semantic **rank 1**（§18.2 #3） |
| **verify 真题被「先注入后裁掉」** | top-up 只按 `kb_depth` 找，**未继承 `eligibility_where`** → 把 `exam_answer` 拉进池，再被 Evidence Policy 裁 → L3 空 | top-up 与主检索共用同一 where | `rag/layer_recall.py` · `rag/retriever.py`；`topup_eligibility_gate` 4+1 场景 PASS（§15） |
| **practice 出现空证据包** | ① preferred 层不合规时 top-up 空转 ② 包被 eligibility 裁空后无兜底 | 新增 `eligible_semantic_layers()` 回退 + `pack_blocked()` 空包回填（**只填合规项**） | `schema/task_policy.py` · `rag/evidence_policy.py`；`pack_nonempty_rate` 全 **1.000**（§12.3/§15.7） |
| **「单链表就地逆置」召不回目标 chunk** | 三层叠加：① jieba 把「逆置」切成「表逆置 / 地逆置」 ② 同义词守卫按「**子串**」判定 → 标准词「逆置」永不追加 ③ 排序方向（同上） | 注册 9 个领域词 + 守卫改「**已是分词结果**」+ 排序修正 | `rag/rag_utils.py` `_DOMAIN_WORDS` · `rag/synonyms.py` · `rag/routes.py`（§18.2 #1–#3） |
| **「滑动窗口协议」kp_hit 掉分** | **golden 单标签口径**：同文件同主题（L38 标传输层 / L163 标数据链路层），而 IP/MAC、ARP 早已双标签 | 补第二标签（纯数据修正，**未改 evaluation 逻辑**） | `evals/datasets/golden/sample_408.jsonl` L38 → `["数据链路层","传输层"]`（§18.2 #4） |
| **论文数字无法反查到代码版本** | 归档不自描述（无 `code_version` / golden hash / 脚本名） | 新增 provenance 注入 **13 个写入点**，全部归档按该版本重跑 | `src/evaluation/provenance.py`；`freeze_precheck` 矩阵 **11/11 全 Y**（§18.6） |
| **RAGAS judge 用不了强模型** | DashScope **thinking 模式拒绝 `n>1`**，而 `answer_relevancy` 必需 `n>1` | judge 独立槽位 `RAGAS_JUDGE_MODEL` + **只对 judge** 强制关 thinking | `core/settings.py` · `core/llm.py` · `evaluation/adapters.py`（§5） |
| **RAGAS 可能「白花钱」/ 静默失败** | judge 配额/鉴权失败时**生成已跑完**、费用作废；且全指标 `n=0` 仍退出码 0 | preflight **分别探活**生成/judge + 生成产物**先落盘** + 全无分升级为显式错误 | `evaluation/cli.py` · `evaluation/ragas_eval.py`（§5） |
| **实验路径与 Agent 路径口径不一致** | 实验脚本未传 `eligibility_where` → baseline 虚低、Δ 失真 | 补传 `filter` + `eligible_layers` | `scripts/task_layer_ablation.py` · `scripts/task_mode_layer_policy.py`（§15.5） |

### 19.2 未修 / 已决策（如实记录）

| 问题 | 诊断 | 最终处理 | 数字 |
|---|---|---|---|
| **L2 跨学科污染** | `preferred_layers` 提升**所有** advanced；L2 池小（98），错学科靠通用词面挤进包 | **未修**（推迟）——方向是学科感知排序，**非补数据** | **40.0%**（10 条 L2 中 4 条错学科，§16） |
| **rerank 收益符号不稳** | 边界不稳定 | **默认关闭**（`.env` `RERANK_ENABLED=false`），论文如实披露 | +0.012 / 更早 −0.046（§2.1） |
| **RRF 阈值 > 可达上限** | 阈值按 k=20 标定、实际 k=36，量纲错配 | **不改默认阈值**（0.9× 可缓解但属边界）；记入「不做清单」 | §14；`postprocess._rrf_scale_needed` |
| **decompose / HyDE 零增益** | k=5 预算 + 短查询占比高，复杂度未兑现 | **保留启用**（关闭无变化；HyDE 属低频兜底），论文如实报零增益 | 消融 Δ = 0（§2） |
| **语义缓存** | 会把「缓存命中」混进「检索质量」 | **默认关闭** | `SEMANTIC_CACHE_ENABLED=false` |
| **L3 不适合作通用知识库** | chunk 是题干/选项/答案/解析，缺定义原理推导 | **设计定位，非缺陷**；grade/verify 下不可替代 | `l3_only` empty 98%（§9） |

### 19.3 一句话总结

已修 9 项集中在三类根因：**① 排序方向 bug**（影响面最大，连带修好 q052 与 #16）、
**② 资格边界未对齐**（top-up / 实验路径）、**③ 可追溯性缺口**（golden 标注 + 归档 provenance）。

未修 6 项均为**有意决策**，且全部在 §18.4 与论文表中如实标注，不作美化。

---

## 20. 效果版本锚点 · **V-2026-10-07**（现行 · **效果章**）

> **与 §18 的分工**：§17/§18 冻结的是**检索**版本（论文第 3–4 章数字来源）；
> 本节冻结的是**效果 / 任务级**版本（`evaluation.task_eval` 那条链，论文效果章来源）。
> **互不覆盖**：动检索链仍回到 §18 口径；动**批改 prompt / Memory 写链 / 评测器**落本节。

### 20.0 ★ 版本锚点

| 项 | 值 |
|---|---|
| **Git 标签** | ① **`V-2026-10-07`**（附注标签对象 `abc115b` → **落点 `0f24891`**，2026-10-07 18:53 +0800）<br>② **`V-2026-10-07B`**（**D9 补的第二个锚点**；标签对象 `bf37b6b` → **落点 `c70ed03`**，2026-10-08 00:22 +0800）—— **Step 9 全部数字所属的代码状态** |
| **落点提交** | ① **`0f24891`**（`docs: §20 效果锚点…`）。其前两跳：`c5d5bca`（gold 数据集入库）→ `63b3b79`（效果层代码 + 11 条口径修复）；再上是 V-2026-10-02 之后的 `648d819`<br>② **`c70ed03`**（`docs(step9): §20.2 补 D9 收尾重跑…`）。它相对 ① 是 **19 个提交**、`src/`+`scripts/` **10 个文件 `+1153/−61`**；标签消息里直接写了落点时的验证状态（护栏 162 全绿 / sanity ERROR 0 / 检索门禁逐位复现）<br>③ **`e65837a`**（`docs(anchor): §20.2 记 V-2026-10-08 打锚点前的检索门禁复跑…`）；它相对 ② 是 **6 个提交**、`src`+`scripts` **10 个文件 +827/−70**，且**没有 gold 改动**（memory 指纹仍 `3c938365da7ce614`）<br>④ **`79ac38f`**（`docs(step6): §21 补「§6 整轮怎么跑」…`）；相对 ③ 是 **5 个提交**、`src`+`scripts` **6 个文件 +717/−1**，同样**无 gold 改动** ⇒ 四个锚点共用同一份效果集指纹 |
> ★ **与标签的代码层差异（2026-10-07 Step 9 之后复测）**：`git diff V-2026-10-07 HEAD -- src` **非空** —— 标签之后 `src/` 又改了 4 个文件（`+137/−17`：`metrics` / `report` / `runner` / `memory_scorer`，即 #21 主指标单一公式、#22 取证通道、⑯/⑰ 的落盘字段）。⇒ **Step 9 的 6 份归档全部跑在标签之后的提交上**，逐份 `code_version` 见 §20.8.5；`PROMPT_SET_VERSION` 仍是 `2f485d2d7ef7`（提示词未变）。⇒ 引用 Step 9 的数字时**不要**说「与 `V-2026-10-07` 同一代码状态」；★ **D9 已落地（2026-10-08 00:22）**：第二个锚点 **`V-2026-10-07B`** 指向 **`c70ed03`**，即「产出 Step 9 全部数字的代码状态」；从该锚点起，引用 Step 9 的数字可以说「与 `V-2026-10-07B` 同一代码状态」（比较仍应写成可重跑的命令：`git diff V-2026-10-07B HEAD -- src scripts` 应为空）。（★ 这一行此前写的是「空输出 ⇒ 逐字节相同」，那是当时的事实、现已被后续提交作废 —— 教训：这类断言只能写成**可重跑的比较**，不能写成结论句。）
> ★★ **锚点 ② 之后 `src/`+`scripts/` 又变了 ⇒ 已用锚点 ③ 收口（2026-10-08）**：② 之后那批改动是「对自己代码做对抗性 review」后的修复（#28~#31 + D12(B)：`runner.py` 写入证据判据的位置/归因/下游、`retrieval_probe.py` 的 KP 兜底、`agent_behavior_smoke.py` 的 `_UNSET` 与 `episodes_read_failed`、护栏 `㉓/㉔/㉕` 三组与护栏自身卫生），共 **6 个提交 / 10 个文件 +827/−70**、**无 gold 改动**。⇒ 现在的可重跑比较是两条，别混用：`git diff V-2026-10-07B HEAD -- src scripts` **非空**（引用 Step 9 的 d8b 数字仍用 ②），`git diff V-2026-10-08 HEAD -- src scripts` **应为空**（引用本批修复后的评测层/护栏状态用 ③）。护栏计数 162 → **184**（链条写进 §20.7）。

> ★ **自指限制（不是漏更）**：上面几行由标签**之后**的 docs 提交回填 —— 一个提交写不下自己的 SHA，所以 `git show V-2026-10-07:docs/EXPERIMENTS.md` / `... V-2026-10-07B:...` 里看到的都是回填前的文字。**锚点的权威解析不依赖本文字**：`git rev-parse "V-2026-10-07^{}"` → `0f24891599c194179755753d06e0d53f106d116e`；`git rev-parse "V-2026-10-07B^{}"` → `c70ed03a59f7f8d15ecb97a47673973664ef2434`；`git rev-parse "V-2026-10-08^{}"` → `e65837a5…`；`git rev-parse "V-2026-10-08B^{}"` → `79ac38f…`（★ ③④ 的回填都发生在各自标签**之后**的提交里 —— 自指限制对每个锚点都成立，别当成漏更）。（§18.0 的 `V-2026-10-02` 是同一做法：落点 `e36c766` 记在其后的 `e2ec6a6`。）
| **批改 prompt 版本** | `PROMPT_SET_VERSION = 2f485d2d7ef7`（E-3 注入词表 + **#8 过滤课程根节点**后；词表 **158 个** = 162 − 4，批改 system **1293 字符**）。★ E-5 的 `0.875` 是在**旧 hash `f09c75642029`**（词表 162 个）下测得 ⇒ 严格说 E-5 归「E-3 完成后、#8 前」的中间态，新 hash 下的复测（12 次调用）**建议并入 Step 9** |
| **黄金集 sha256** | `be98912a4c91fb88151640c82515127465031c1e79382b99c40e32311d6d1a66`（156 条，**与 §18.0 逐字相同 ⇒ 黄金集自 V-2026-10-02 未变**） |
| **效果集指纹**（`evals/datasets/demo/`，sha256 前 16 位，现值） | `generate 02e12e13bdcef4f7` · `grade 4e47351d03ede7c9` · **`memory 3c938365da7ce614`** · `qa e4ceeafabcc488fc` · `verify 5daad346d24f7100` |

> ★ **`memory` 这条改过四次**（其余四集与黄金集**逐字未变**，都对得上 §18.0）：
> - `dbcfe0b809c084e3` → `b5619085d7979a36`：B4（修 #17）给 `mem-005` 的 gold 加了 `max_grade_calls: 0`，负样本对照的前置条件从「永真」变成真约束 —— **改了 gold 本体** ⇒ 指纹必然漂。
> - `b5619085d7979a36` → `6b91953493865c16`：**D8 第一次**（§20.8.6）把 `mem-002`/`mem-003` A 段**第一题**换成与第二题**同一考点**的题（修 #22 的样本设计缺陷：两道题落不同 KP ⇒ `MEMORY_WEAK_MIN_HITS=2` 永远凑不满 ⇒ 画像恒空）。
> - `6b91953493865c16` → `ffcf2b3233fc5595`：**D8 第二次**，补上第一次漏掉的 `mem-003` **第二题**。Step 9 归档实证：那题的学生作答「38, 49, 65, 97, 76」在一趟 Hoare 划分下**就是正确结果**（已用教材算法复算）⇒ 模型判 100 分是**判对了**，而 gold 的 `grade_score_bands=[[0,59],[0,59]]` 要求两次都低分 ⇒ **前置条件天然不可满足**，属 case 设计错、**不是**产品缺陷。已换成一道作答确实错、仍落在「快速排序」的辨析题。★ 连带**作废** §20.8.3 里「错题被判 100 分 = 缺陷 A 现存症状」的归因（该节已更正；同一归档里真正的误判是**反方向**的：`小根堆判定` 那题作答正确却被判 0 分）。
> - `ffcf2b3233fc5595` → `3c938365da7ce614`：**D8 第三次**，把 `mem-002`/`mem-003` 的 `expected_memory.values` 由**章名**（`图` / `排序`）收到**具体考点**（`图的存储` / `快速排序`）。原写法的判定是**子串包含** ⇒ 「任何含『图』字的卡都算召回」，正样本的「召回成功」测不出「召回的是不是设计的那个薄弱点」（登记为 **#26**）。D8 已让 A 段两题落在同一具体 KP ⇒ 现在**有资格**要求精确名（改前核对：两值均在 `canonical_names()` 里，`task_eval sanity` 复跑 **ERROR 0**）。
> - ★ **换进去的题面是「自拟辨析题」，不是真题原文**。核对方式：在 `knowledge/questions/*.md`（17 个年份）里检索「邻接矩阵…度」「快速排序…稳定」，命中的是**解析段落**而非同一题干 ⇒ 题干与 L3 语料的关系由「引用」降级为「自拟」，论文里必须这样标。这不构成造假：Memory 正样本要的是「两次低分批改落在同一考点」，**不依赖**真题；且**没有**造 `human_score`、**没有**动 L3 语料本体。（对照：`grade`/`verify` 那些任务**必须**用真题，因为它们的 gold 就是人工分。）
>
> 教训同前：**改 gold 与打标签是同一件事**，锚点必须在打标签之前重算。

> ★ **指纹口径 = 工作副本字节的 sha256**（与 `scripts/freeze_precheck.py:65` 一致），**不是 git blob 哈希**。因为 `.gitattributes` 声明 `*.jsonl text` ⇒ 入库时 CRLF 会归一成 LF，实测同一份黄金集：工作副本（CRLF）`be98912a4c91fb88…` / 归一后（LF）`979b7f96537cb147…`。⇒ **在纯 LF 环境（如 Linux/CI）checkout 后重算会得到另一个值**，那不是数据被改；复算要么在本机工作副本上跑，要么比较前先做行尾归一。
| **归档 `code_version` 现状** | 全部为 **`648d819-dirty`**（见 §20.5 第 3 条——这是本节存在的理由） |

### 20.1 为什么必须开新版本（三条触发，均已核到代码）

1. **动了检索链**：`rag/llm_calls.py` 的重试 + 兜底被 **`query_classifier.py:311`** 与
   **`query_decomposer.py:175`** 共用 ⇒ 按 §18 / `EFFECT_PLAN` 的「动检索链 → 新版本」规则触发。
2. **批改 prompt 变更**：`GRADE_PROMPT` 注入 162 个 canonical 考点名，system 从 389 → **1317 字符**。
3. **Memory 写链三层改**：`GradingResult.knowledge_points` → `record_grade` → `compute_weak_topics`。

### 20.2 检索门禁在本锚点的实测（四路由 + 隔离实验）

| 路由 | 判定 | 关键值（当前 / 基线） |
|---|---|---|
| `fake + off`（默认） | ✅ 通过 | `kp_mrr 0.6761 / 0.6698` · `kp_hit@k 0.8718 / 0.8654` |
| `fake + disabled`（生产关闭态） | ✅ 通过 | `kp_mrr 0.6614 / 0.6277` |
| **`real + on`（权威 · 唯一能答语义质量）** | ✅ 通过 | `kp_mrr 0.8048 / 0.8051` · `kp_hit@k 0.9103 / 0.9167`（均在容差内） |
| `fake + on`（假重排） | ❌ 退化 | `kp_mrr 0.7566 / 0.7828`（−0.0262 > 容差 0.02） |

**隔离实验**（决定「该红是否本轮造成」）：在 `HEAD` 的独立 worktree 上跑同一路由、完整 156 条 ⇒
**同样是 0.7566，逐位相同** ⇒ 该退化**由已提交的代码带入**，与 E-3 / E-4 / 类型收窄无关。
**基线不重录**（本轮无任何指标变化需要吸收），该红按 §20.5 披露。

★ **门禁的能力边界（必须写清，否则这句话会被误用）**：门禁把 LLM 钉成 fake
（`settings.USE_FAKE_MODEL=True`，模型恒返回测试串）⇒ 日志里每条 query 都有
`结构化输出类型不符 [classify]，重试 1 次后仍失败`，**重试确实在检索链内部被触发**，
但因 fake 永远失败、重试只多打一次 ⇒ **结果不变**。
⇒ 「检索未受影响」只在**确定性层面**成立；**重试对真实 LLM 路径的影响既未证实也未证伪**，
门禁在设计上测不到它（真实 LLM 下重试可能把分类失败变成功 ⇒ `query_type` 变 ⇒ 路由变）。

★ **D9 收尾时重跑过权威路由一次（`real + on`，156 条，`code_version` = 本轮 HEAD）**：
`category_hit@1 0.9423/0.9423` · `category_hit@k 0.9679/0.9615` · `kp_hit@k 0.9103/0.9167` ·
`kp_mrr 0.8048/0.8051` · `kp_annotated 156/156` ⇒ **与上表逐位相同**，检索侧自锚点后无漂移。
★ **第一次跑是红的，而且红得是我自己造成的**：那次我**并发**开了第二个进程去全量扫 Chroma 索引
（就是 #27 的那次扫描），门禁侧 297 次查询抛 `Error creating hnsw segment reader: Nothing found on disk`
⇒ 它**没有**把这些查询当成「空结果 = 指标低」，而是判定「指标不可信、**跳过基线比对**」并以退出码 2 拒绝出绿。
单进程重跑即绿。⇒ 两点都要记：① 这条 fail-loud 设计救了一次假绿（换许多门禁的写法会直接把
「索引读不到」上报成「检索退化」）；② **别在跑检索门禁的同时再开第二个 Chroma 客户端**，
这条后来发现 #27 的扫描本身就是那次并发的产物。

★ **打 `V-2026-10-08` 之前又跑了一次同一路由**（`real + on`，156 条，单进程，完整日志留存）：
`category_hit@1 0.9423/0.9423` · `category_hit@k 0.9679/0.9615` · `category_mrr 0.9551/0.9519` ·
`kp_hit@k 0.9103/0.9167` · `kp_mrr 0.8048/0.8051` · `kp_annotated 156/156` · `empty_result_rate 0.0`
⇒ **与 §20.2 上表逐位相同**（D12(B) 只改评测读数 `retrieval_probe`，本来就不在这条链上，此处得到确认）。
★ 唯一有差的是 `mean_evidence_count`：**3.9295 → 3.9231**（基线仍 3.8846，两次跑的是同一份代码）；打锚点 ④ 前又跑了一次同一份代码 ⇒ **3.9295** —— 三次落在 **[3.9231, 3.9295]** 之间，确认这是**运行间抖动**而不是代码效应（其余指标三次都逐位相同）。
⇒ 这说明该指标有**运行间抖动**（其余全部逐位相同 ⇒ 不是抖动在扩散）。可疑来源是那条
「阈值过滤后为空 ⇒ 保底返回 top-1」的分支（fake LLM 分类失败时 `query_type`/路由会变 ⇒ 证据条数会变）。
判定不受影响（阈值判定是「不低于基线」，本次仍高于）。★ 但引用 `mean_evidence_count` 时**必须带上这个抖动**，
不要把它写成第三位小数稳定的量。

### 20.3 效果侧实测（本锚点新增，均可从归档反查）

**E-5 · 批改是否跟随词表**（`scripts/memory_e5_probe.py`，配对 12 次批改调用，零 token 风险）
：两臂 system **除词表块外逐字节相同**，同模型同温度（`dashscope:qwen3.7-flash` / `T=0.0`）。

| 臂 | 词级跟随率 | `all_canonical` 题级 | 目标考点入桶 |
|---|---|---|---|
| A 注入 162 词表 | **0.875**（7/8） | 5/6 | **6/6** |
| B 8 示例（= 修复前口径） | 0.273（3/11） | 1/6 | 3/6 |

**缺陷 A 的批改失败率——口径修正**（按 A 段**预期**批改次数为分母；
失败 = 分数不可解析 **+** 完全没有落分记录）：

| 运行 | 预期 | 落分记录 | 不可解析 | 无记录 | 失败率 |
|---|---|---|---|---|---|
| Step 5 修复前 ON | 9 | 6 | 2 | 3 | **5/9 = 0.556** |
| Step 5 修复前 OFF | 9 | 7 | 2 | 2 | 4/9 = 0.444 |
| Step 5 修复后 ON | 9 | 9 | 0 | 0 | **0/9 = 0.000** |

⇒ 此前文档写的 **62.5%（5/8）** 分子对、分母错（8 无法从归档构造）；
只数「`score=None`」得到的 30.8% 则**漏掉了「完全无落分记录」这种最硬形态**。
**论文改用 `5/9 → 0/9` 这一对**，两端都可从 `phase1_memory_step5_*` 重算。

**Grade · `verdict_agreement`（#7 换来的合法指标，零 token，从冻结归档重算）**

| 归档 | verdict_agreement | 分数不可解析 | 旧 `tolerance@±10` |
|---|---|---|---|
| `phase0_baseline_final` | **15/15 = 1.000** | 0 | 不可判（两极 gold；`raw_rate=1.0`） |
| `phase1_baseline_v2` | **13/13 = 1.000** | **2**（grd-004 / grd-011） | 不可判（同上） |

⇒ 论文里 Grade 的写法应是：**「选择题对错判别 15/15 全对」**，而不是**「0–100 判分与人工一致率 100%」**
—— 后者在本项目**没有对应的数据前提**。★ 且**两个数必须同框**：只报 13/13 不报那 2 条批改失败，
就是拿"分母剔除"把失败藏起来（这正是 §20.5 #4/#6 那一类错误的第三次现身，故由 ③r' 强制披露）。

### 20.4 ★ 结果归属矩阵（引用前先看这张表）

| 归档 | 产出时间 | 对应代码状态 | 能否引到本锚点 |
|---|---|---|---|
| `phase0_baseline_final.jsonl`（66 条，0B 冻结） | 10-06 07:01Z | **前态**（不含 E-3/E-4） | 只可作**诊断基线**，非本锚点产物 |
| `phase1_baseline_v2.jsonl` · `phase1_verify_probe*` | 10-06 09:12Z | **前态** | 同上；其「检索侧逐位一致」成立于该次比较（早于 `llm_calls` 改动） |
| `phase1_memory_step5_store_{on,off}.jsonl` | 10-06 13:44Z | **前态**（缺陷 A–D 已修，**E-3 未做**） | 同上 |
| `phase1_e5_prompt_following.jsonl` | 10-07 | **本锚点**（它测的就是 E-3） | ✅ 可引 |
| §20.2 四路由 + §20.3 失败率重算 | 10-07 | **本锚点** | ✅ 可引 |
| Step 9 全部归档（`phase1_e5_step9_*` · `..._step9_{20261007,diag,kp,d8,d8b,smoke}` · `phase1_step9_probeonly_*`） | 10-07 晚~10-08 凌晨 | **锚点 ② `V-2026-10-07B`（`c70ed03`）**，逐份 `code_version` 见 §20.8.5 | ✅ 可引 —— 但 **OFF 侧只有 `..._step9_d8b` 那两份可用**（更早的 OFF 归档跑在 #24 之前，对照无效） |

★ **D9 要求的「并进 §20.4」按这张表落地**：§20.4 留**归属结论**（能不能引），§20.8.5 留**逐份实测 hash**（`code_version` + `prompt_set_version`）—— 两表分工不复制内容，因为前者会随引用口径变、后者只能由归档自己读出。

★ **0B 的可复现性说明（修正此前一处过重的判断）**：当前 `evals/datasets/demo/` 的文件
**不是**产出 0B 的那批输入（`gold_status` 现为 `draft`，归档记 `reviewed`；Memory 6 条 query 也不同），
**但 0B 归档 66/66 条都自带 `query` + `turns` + `gold` + `agent_model` + `judge`** ⇒
**输入可从归档重建**；丢的只是「拿现件原样重跑」这一条路径。
⇒ 要重跑必须先按归档重建 case 文件（或改用现件重跑并另立 `phase1_` 前缀，**不得回写冻结基线**）。

### 20.5 已知偏离（如实记录，不美化 · 冻结件 `EFFECT_PLAN.md` 不在此改写）

| # | 偏离 | 证据 | 处置 |
|---|---|---|---|
| 1 | `fake+on` 路由 `kp_mrr` 低于基线 | §20.2 + 隔离实验 | 披露，不重录基线 |
| 2 | **Generate 主指标口径分叉**：`EFFECT_PLAN §3.1` 冻结为逐题 `five_of_five` AND，代码 `report.py:134-145`（`gen_items`）实为**跨题跨项池化** | 同一归档三数：**池化 0.9423 / 逐题适用项全过 0.80 / 严格 5/5 = 0.00**。★ 解剖后发现真正的问题不是公式，而是**五项里只有两项有区分力**（见 §20.5.1） | ✅ **已修（D1，2026-10-07 采纳）**：`metrics.every_item_passes()` 做**逐题 AND**（N/A 项不进该题分母），`report.py` 主指标改挂逐题数、**项级池化降级为诊断**（不删，留对照）；旧名「交付完整率（主指标）」从报告消失。★ 归档 15 条**复现三个数不变**：主指标 **0.80（12/15 题）** / 诊断池化 **0.9423（49/52 项）** / 严格 5/5 **0.00**。护栏 **⑭a~⑭f**（⑭c 锁「同一样本两口径必须分叉且池化偏高」= 证明换口径有信息量；⑭d 锁两个已发表数字不许漂；⑭f 锁「整题不可测的题不许假装进分母」） |
| 3 | 归档 `code_version` 全为 `648d819-dirty`，且 record **不含 `prompt_set_version`** | `provenance.code_version()` 对 `src/ scripts/` 的未提交改动只加 `-dirty` ⇒ 多次运行同值 | ✅ **已修（D4）**：`CaseRecord` 新增 `prompt_set_version` 字段，`_attach_provenance` 从 `prompts` 取**活值**写入 ⇒ 新归档自描述跑在哪个提示词上，不再依赖本节人工对账。★ **老归档没有该键 ⇒ 读侧一律按空串（未知）处理，绝不回填当前 hash**（回填等于伪造 provenance）。护栏 **⑮d/⑮d' + ⑮e**（⑮e 是反向：把 `PROMPT_SET_VERSION` 临时改成 SENTINEL，新 record 必须跟着变 —— 若当初写成硬编码字面量，⑮d 照样绿、这条必然红）。★ 另：三次提交之后 `provenance.code_version()` 实测返回**干净的 `0f24891`**（`CODE_PATHS = (src, scripts, pyproject.toml, .env.example)` ⇒ 文档改动与未跟踪的 `evals/results/task_eval/` 都**不**算脏）⇒ 本条对**新跑的归档**已消除；既有 5 份仍是 `648d819-dirty`，**不回写**（它们是历史证据），对那批仍靠本节人工对账 |
| 4 | Memory 的 `used` 用「回复含 gold 值**子串**」判定 ⇒ **双向错** | `phase1_memory_step5_store_on`：`mem-006` 卡为空、未召回却 `used=True`（假阳性）；而 `mem-004`/`mem-005` 规规矩矩没凭空用记忆，却因 `used=False` 被 AND 判 **失败**（假阴性）⇒ 净效果是「**负样本只有碰巧提到才算通过**」 | ✅ **已修（本轮）**：`used` 加事实前提 `recalled_actual`；`correct_use` 按极性分定义（正=召回∧used∧correct；负=未召回∧未误用）。**ON 组数字变化：`used` 2→1、`correct_use` 2→4（0.333→0.667）**。护栏新增 ③d~③h 锁住四个方向 |
| 5 | Step 5 配对 OFF 组 `valid=2` **且两条皆负样本** | 重算：正样本 mem-001 在 OFF 侧 `case_invalid` ⇒ 两臂样本集不相交。★ **本条的原始证据已被 #24 二次削弱**：那批 OFF 跑在「OFF 臂其实没关掉 Store」的代码上，所以它连「不相交」都说明不了对照本身有效 | ✅ **已闭合（D8 + #24，§20.8.6）**：用修好的 OFF 重跑后，两臂在正样本上有**交集** `mem-002`（ON 与 OFF 都 `valid=True`、都满足「两次低分批改且同考点」）⇒ 这是本文第一条**可信配对**：ON 1 卡 + `recalled/used/correct_use` 全 True，OFF 0 卡 + `recalled=False`。剩余限制照实写：可测正样本 **n=1**（ON 侧另两条因 A 段第 2 轮未调用批改工具而 `case_invalid`，与 Store 无关） |
| 6 | `case_invalid` 计入 `failure_rate` 的分子与分母 | `report.py:74-75`：分母为 `len(records)`，`case_invalid` 在枚举内 | ✅ **已修（本轮）**：分母改为「有效 n」，并新增 `invalid_n` 字段 + 报告表「有效 n」列。护栏 ③i 锁「1/2 而非 1/3」 |
| 7 | Grade 的 `gold.human_score` **只有 0 与 100 两值** | 重算分布 `{100:8, 0:7}` ⇒ `score_tolerance@±10` 退化为「模型是否也跟着给 0/100」 | ✅ **已修（换指标，非补标）**。★ **我先前写的处置「按 rubric 补部分分」是错的，已撤回**：L3 语料 **674/674 全是 2 分 `choice`**、case 的学生答案 **15/15 仅 1 个字母** ⇒ **没有部分分可标**，硬要补就只能造题（= 造假 + 动语料）。正确解法是**换成二值 gold 上本来就合法的问题**：新增 `metrics.verdict_agreement()`（阈值直接引用 `schema/grading.py` 的 `score<60 视为错误`）⇒ 实测 **0B 15/15 = 1.000**、**Phase 1 13/13 = 1.000（另 2 条分数不可解析，报告已强制披露）**。两极 gold 下 `tolerance` 置 N/A 但**保留 `raw_rate=1.0`**；护栏 **③o~③r'**（③o 锁住"数值差 30 但结论一致 ⇒ verdict 过 / tolerance 败"这条换指标理由；③r 锁"tolerance 不可判时 verdict 仍可判"，防止这次修复变成删指标） |
| 8 | 批改词表含 **4 个学科根节点**（数据结构/计算机组成原理/操作系统/计算机网络） | 与同一 prompt 的规则尾「不是学科名（如「数据结构」太粗）」自相矛盾；且根节点是 canonical ⇒ 模型选它能**轻易凑满 `MIN_HITS=2`**，聚成「整门课 = 一个薄弱点」的桶，**比自造词更难发现** | ✅ **已修（本轮，#8）**：新增 `kp_vocab.prompt_names_by_subject()`，按数据字段 **`node_kind == "subject"`** 过滤（★ 不写硬编码名单 —— 硬编码正是缺陷 E 的成因）；`canonical_names()` **仍保 162 全量**（归一化侧必须认得根节点，否则 `normalize_topic('数据结构')` 反被判非 canonical，是另一种错）；`domain` 章名（`图`/`排序`/`内存管理`…）**保留**，它们是合法薄弱点标签。词表 **162 → 158**、护栏 **⑫k 双向**（剔根节点 + 防过滤过头）。★ 连带后果：**`PROMPT_SET_VERSION` 变更**（`f09c75642029` → `2f485d2d7ef7`）⇒ E-5 的 0.875 严格归中间态，需在新 hash 下复测（并入 Step 9） |
| 9 | **0B 的 Memory 四率与现口径不可比** | 实测：0B 记录的 `gold` 键里**没有 `expected_memory`**（只有 `gold_points`/`human_score` 等），用当前 scorer 判 ⇒ 六项**全 N/A**；可归档里 `mem-002` 等却记着 `used=True`/`cu=True`，且 `judge_memory_used=None` | ⇒ 0B 那组 Memory 数字**不是这套机械 scorer 产出的**（与 §5.1「0B 只测到 checkpointer 会话内记忆」一致）。论文若要用 0B 的 Memory μ=2.833，**必须标注其口径与 Phase 1.5 之后不同** |
| 10 | `category_hit` 对学科码 **`cn` 恒判未命中** ⇒ **系统性压低 grade / verify 的学科命中指标** | `metrics.category_hit` 旧写法 `.get(subject, subject)` 拿学科码去比类目名：`cn` ≠ `computer_network` ⇒ 恒 False。实测归档分布：`grade` **4 条 `cn` 全 False**、`verify` **4 条 `cn` 全 False**；而 `qa` / `generate` 的 case 用的是 `network` ⇒ 全 True —— **同一函数在两个任务上表现不一致**，这是它长期没暴露的原因。另核实 `retrieval_gate` 自身用 `.get(subject)`（无默认回退），**不受此影响** | ✅ **已修（本轮）**：加 `_SUBJECT_ALIASES = {"cn": "network"}` 对齐，且**未登记学科记 None（N/A，不进分母）**而非 False。护栏新增 **③j**（对齐命中 + 未登记记 N/A），当时 Gate **87 项全绿**（现 116）。★ 归档里那 8 条 False **不可离线重算**（2026-10-07 复核确认：记录只有 `category_hit` 这个**结果布尔**，`tool_calls` 里**没存**每条命中文档的类目 ⇒ 无法反推，正确值需 **Step 9 一并重跑**；旧归档值不覆写 ⇒ ✅ **已补测（§20.8.4）**：同一批 top-k 上新旧公式对照 0.600 → 0.800、`cn` 0/4 → 3/4 ⇒ 确认这 8 条是系统性假阴性，剩余各 1 条为真实未命中）。★ 复核过程本身也纠正了一次误报：直接按 `task` 数 False 会得到 grade 13 / verify 33 条，**看着像**『比登记的 8 条多』—— 其实记录里**没有 `subject` 字段**，必须与 case 表按 `case_id` 关联；关联后 `cn` 恰为 grade 4 + verify 4（且 `cn` 是**唯一 16/16 全 False** 的学科，其余学科有 True 有 False，属真实未命中）⇒ 登记值成立。护栏补 **③j+**：扫遍 `evals/datasets/` 实际出现过的学科码，逐个要求「在映射表里查得到」且「用映射后的真实类目自测为 True」⇒ **防下一个 `cn`**（反向验证：抽掉 `cn` 别名，③j 与③j+ 同时变红） |
| 11 | Grade 分数解析取**首个数字** ⇒ 把「满分/总分 N」当成得分 | 旧正则在 `"总分 100 分，你得了 62 分"` 上返回 **100**、在 `"得分（满分 100）：62"` 上返回 **100** ⇒ 批改明明正常，指标却记成分数差 38 分；更糟的是它**方向不定**（说明性数字在前就偏高、在后才正常） | ✅ **已修（A1）**：先用 `_MASK_FULLMARK_RE` 把「满分/总分 X」**遮蔽**掉，再按「显式得分 → 你得了 N 分 → a/b 折算 → 兜底」四级正则解析；解析不到返回 **None（N/A）** 而不是 0 分。护栏 **③s**（5 条形态全对）+ **③t**（4 条无分数形态必须 None） |
| 12 | API 批改端点 `record_grade` **没透传 `knowledge_points`** | `service.py` 的调用缺该参数 ⇒ 本路径写入的 episode KP **恒空** ⇒ `compute_weak_topics` 退回**题干前 80 字**（legacy fallback），薄弱点变成「某道题的开头」 | ✅ **已修（A2）**：`knowledge_points=list(result.knowledge_points or [])`。护栏 **③u**（AST 级：调用参数表里必须有它，防止「删了但注释还在」式漂移） |
| 13 | 结构化输出的 **salvage 兜底**只在「确实拿到过原文」时生效 | `scripts/memory_e2e_fallback_probe.py` 用注入式假 LLM 驱动**真实** `call_structured`：① 合法对象 OK；② `ValidationError` 带脏原文（多行 KV + 参数标记）⇒ **救回**（score 40，KP `['平衡二叉树','平衡因子']`）；③ 模型**不产 tool call**（返回 `None`）⇒ 无原文可救，结果 `None`（重试后仍失败） | ⚠ **已知盲区，如实披露**（不是修复）：③ 形态下整条批改失败。是否为它再加一层兜底，**由 Step 9 的实测频率决定** —— 现在加就是凭想象加防护。`--reverse`（关掉 salvage）必须变红，实测 exit 1 |
| 14 | `--rejudge` 把 runner 写的归因**洗掉** ⇒ 无效样本看起来像通过 | `mechanical_reasons_from_record` 照抄 `runner.mechanical_failures`，而 `case_invalid`（`runner.py:505`）/ `memory_miss`（`runner.py:382`）是 runner **另两处分头**写的。实测归档：`phase1_memory_step5_store_off` 有 **4 条** `failure_reason` 恰为 `["case_invalid"]` ⇒ 重判后变 `[]`、`primary_failure` 翻成 `none`。★ 注：失败率**分母不受影响**（`report._is_invalid` 还看着 `validity_valid`），坏的是**故障分布** —— 「无效」被画成「通过」 | ✅ **已修（B1）**：`_KEEP_ON_REJUDGE = {case_invalid, memory_miss}` 原样保留（二者都**不是** judge 意见），`case_invalid` 另按 `validity_valid` 兜底重建（上一轮已被误清时仍能恢复）。护栏 **⑬a~⑬d**（⑬d 是反向：judge-only 的 `generation_wrong` 仍必须被清掉，防保留面过宽） |
| 15 | `cli.py` 三处 jsonl 写出**不留尾换行**，与 `append_record` 的 `"a"` 追加相撞 | 两条记录**粘成一条坏行** ⇒ 上一条与这一条**同时**解析失败（实测 3 条只剩 `['a-1']` 可读）。连带 `load_done_ids` 读不到被粘住的 case_id ⇒ 续跑**重做**它，已烧的 token 无从追溯。★ 全盘扫现存 **12 份**归档：末字节**都是** `\n`（都由 `dump_records`/`append_record` 产生）⇒ **尚未真的烧到过数据，属潜伏** | ✅ **已修（B2）**：行格式收口成 `runner.write_jsonl()`（`dump_records` 也改为调用它 ⇒ 只剩一份实现），cli 三处改用它；`append_record` 追加前检测末字节并按需补分隔（自愈，覆盖外部手改/旧产物）。护栏 **⑬e~⑬g**（⑬g 专测「无尾换行的旧文件 + 连追两条仍 4 条不丢」） |
| 16 | `_resolve_config`：显式 config **整块替换**、不与运行时上下文做键级合并 | 半条 review 结论**被推翻**：回落读的是 **contextvar**，asyncio 每个 Task 持自己的 context 副本 ⇒ 并发不串号（实测 4 个任务注入 U0~U3、内部 `sleep` 交错，两次阅读仍各自取到自己）。半条成立但**无调用方**：仓内给 config 的地方都**同时**给两把键（`service.py` 的 `configurable`、gate ⑩a） | 🟡 **不改行为**（无流量的假设性加固不做），改为**把契约钉住**：docstring 写明「只传其一不会替你补」+ 护栏 **⑩e**（并发隔离）与 **⑩f**（部分显式 config ⇒ `user_id` 为 None）。将来若真要改成合并，必须让 ⑩f 变红后由人裁决 |
| 17 | `min_grade_calls: 0` 单独存在是**永真** ⇒ mem-005 负样本对照的前提从未被校验 | `len(calls) < 0` 不可能成立，而 `is_valid()` 只看「字段非 None」⇒ **gold_sanity 全绿、其实没校验**。mem-005 的 note 写的正是「全新用户无写入⇒卡必空」，即意图是「**恰好 0 次**」。★ 同时**推翻**另一条 review 结论：「`forbidden_values` 未校验是否 canonical」是**错的规则** —— 该字段喂给 `memory_scorer._hits(reply, ...)`，是**回复文本里的自由词**（`['栈','队列']`），不是 KP 名；gold_sanity 已在查「未标注」与「与期望值重叠（自相矛盾）」 | ✅ **已修（B4）**：`SetupConditions` 新增 `max_grade_calls`，mem-005 改为 `min:0 + max:0` ⇒ 对照真被验收；gold_sanity 加「空标」lint（`min=0` 且无 max/bands ⇒ ERROR 并给出改写建议）。护栏 **⑬h~⑬l**，其中 **⑬l** 锁「两份归档 12 条 validity **逐条不变**」⇒ `grade_scores` 实测本就是 `[]`，**不改动任何已发表数字** |
| 18 | **整个「效果层」都不在版本控制里**（比原登记的「gold 没入库」大得多，2026-10-07 实测扩大） | `git ls-files` 全为 **0** 且**均未被 ignore**：`src/evaluation/task_eval/`（**12 个 .py**：cases / metrics / memory_scorer / gold_sanity / judge / report / runner / cli / retrieval_probe / assets / `__init__` / `__main__`）、`src/core/kp_vocab.py`（缺陷 E 的**单一事实源**）、`scripts/` 下 **12 个**护栏与探针（含 `memory_step4fix_gate.py` 本身、E-5 探针、e2e 兜底探针）、`evals/datasets/demo / probes / probes_phase1 三个目录/` + `exam_answer_corrections.json`。✅ **已解决（2026-10-07 提交）**：`src/evaluation/task_eval/`（12 个 .py）+ `src/core/kp_vocab.py` + `scripts/` 的 12 个护栏/探针已入库；gold 数据集单独一次 `data(evals)` 提交。`evals/results/task_eval/`（3.7MB，其中 1.9MB 是单个 log）**数据类维持不入库**，可复现性由本节的文件指纹 + 已入库的生成/护栏脚本承担；★ **文档类已按 D11 入库**（`*.md` 16 份 ≈ 200KB：交接件 HANDOVER、各步报告、review 件与 findings；`*.jsonl` / `*.log` / `*.report.json` 仍不入库 —— 二进制归档进版本控制只会让仓库变大且无法 diff，而结论都在 .md 里）。另：`.claude/` 未跟踪（**该 ignore、不该入库**）；`.workbuddy-ai/` 未跟踪但**将被删除** ⇒ 不写忽略规则 | ✅ 见上一格 |
| 19 | **judge 校准表的 PASS 只有 2/30 的信息量** —— 门槛过了，但它测不出「judge 会不会打分」 | `evals/datasets/demo/calibration_30.jsonl` 的 `human_score` 分布 = `{5: 28, 0: 1, 2: 1}`（众数占 **93.3%**，不同取值仅 3 个）。基线复算：`exact 0.9333 / within_1 1.0 / mae 0.0667 / spearman 0.7321` ⇒ **PASS**（阈值 0.60/0.90/0.50/0.70，`spearman` 仅高出 0.032）。★ 三条**破坏性检验**（零 LLM，只改内存里的副本，未回写文件）：① 把第 8 行（human=0）**单独**改成 5 ⇒ `spearman 0.4902` ⇒ **FAIL**；② 把第 17 行（human=2）改成 5 ⇒ `spearman 0.5265` ⇒ **FAIL**；③ 反向：把这 2 行的 **`llm_score` 改成 0**（即 judge 在唯一可判别的地方完全打错）⇒ 仍然 **PASS**（`spearman 0.7315`）—— 因为秩相关只看排序，不看量级。⇒ 结论：**整个 PASS 压在 6.7% 的样本上，且对「量级完全错」不敏感**（与 #7 同类的分布退化，但成因不同：#7 是 gold 造不出中间档，这里 28 个 5 是**真实人工判断**，说明系统输出普遍好，**不能当成数据缺陷去改**） | 🔵 **只披露，不擅自改**：不改阈值（`CALIBRATION_THRESHOLDS` 是「预先约定标准」的落点）、不改人工分（改它=伪造标注）。论文里应把校准表述为「30 条中 28 条人机完全一致；其余 2 条 judge 排序正确」，**不要**引用 `spearman=0.7321` 当「judge 与人工秩相关良好」的证据。是否给报告加一行「非众数占比」露出 = **待裁决 D6** |
| 20 | **Phase 1.5 的 §4「L3 闸门」从未执行，且按当前语料无法执行**（此前**未登记**，两份台账里一条记录都没有） | §4 冻结的判定规则问的是「真题缺失是不是低质量回答的**主要因果原因**」，并指定测据：`question_id_recall@k` · `answer_availability` · `final_quality` + `primary_failure` 分布。实测：① gold 侧**有**标注 （`verify_cases` demo 15/15、probes 10/10、probes_phase1 10/10 都填了 `expected_question_ids`）；② **语料侧没有** `question_id` —— 扫 `questions` 集合的 metadata（50 个键）无任何 `question*`/`qid*` 字段；③ 归档里 `question_id_recall` 字段**出现 0 次**，只有代理指标 `exam_hit`（194 条记录：True 69 / False 125）。⇒ `question_id_recall@k` **不是「没跑」，是「算不出来」**：检索结果里没有可与 gold `expected_question_ids` 对齐的字段。★ 这也解释了 P3 为什么保留 `question_id_recall` / `question_id_hit` / `exam_rank` 三个零调用函数 —— 它们就是为 §4 预留的，**接口在、数据源不在** | 🔵 **只披露，不擅自动**：补齐要 ①ingest 时把 `question_id` 写进 metadata ②**全量重建索引** ③重建即改变检索侧指纹 ⇒ 触发新版本锚点 + 四路由门禁重跑（`EFFECT_PLAN §11` 的「时间紧」退路正是 「L2/L3 全走披露、不修」）。✅ **已裁决（D7，2026-10-07）：按 §11 走披露，不补 `question_id`、不重建索引。** 论文口径固定为：「§4 的判定**未做出**（既不是『是』也不是『否』），原因是判据所需的 `question_id_recall@k` 在当前语料下不可计算」，并附上述三条证据；**禁止**用代理指标 `exam_hit@k` 冒充 `question_id_recall` 去回答 §4 的因果问题 （`exam_hit` 只说『top-5 里有没有真题块』，不说『是不是当年那道题』） |
| 21 | **我自己 #4 的修复从未生效**：同一条主指标存在**两套实现**，落盘用的是旧的那套 | `memory_scorer.MemoryJudgement.correct_use` 在 #4 改成「按样本极性分定义」，但 `runner.CaseRecord` 上**另有一个同名 property** 仍是旧三元 AND（`retrieved ∧ used ∧ correct`），而 `to_dict()` 用的正是那个 property ⇒ 极性版从未写进归档、`report.py` 读的也是旧值。★ 实测：报告对 `phase1_memory_step5_store_on` 印 `correct_use = 2/6 = 0.333`，而 #4 之后应为 **4/6 = 0.667**；两份归档里 `mem-004`/`mem-005` 两条负样本全被旧公式记 False。而 ③d~③h 当时全绿 —— 因为它们测的是 scorer 的**函数**，没测「函数结果如何被写出」（正是「只测 helper、不测接线」那一类） | ✅ **已修（本轮）**：公式收敛到 `metrics.memory_correct_use()` 一处；`memory_correct_use_from_record()` 从**原始字段**推导 ⇒ 旧归档也能按现口径重渲而**不改写归档**；`CaseRecord.memory_correct_use` 由 property 改为字段、由 scorer 写入。护栏 **⑱a~⑱e**（⑱a 用报告路径复现 4/6、⑱b 逐条断言两套账一致、⑱c 反向「同一负样本旧 False / 新 True」、⑱d 走真实 `_apply_memory_judgement` 验接线、⑱e 正样本未召回必须 False，防「修复」退化成负样本一律放行）。★ **连带更正**：#4 里写的「ON 组 correct_use 2→4（0.333→0.667）」当时只有手工重算成立，**报告路径并未产出该数**；现在两者一致 |
| 22 | **正样本可能天然测不到召回**：`MEMORY_WEAK_MIN_HITS=2` 按 **KP 精确名**计 hit，而 A 段两道题落在**不同考点** ⇒ 画像恒空 ⇒ 「0 张卡」不是召回失败而是**样本设计缺陷** | Step 9 实跑：Store ON 的 `mem-002` 两次批改都是 0 分（低分前置条件**满足**），却 `memory_cards=0`、B 段召不回。纯函数复现（零 LLM）：`compute_weak_topics` 喂「图的基本性质 + 图的存储」⇒ `[]`；喂「平衡二叉树 ×2」⇒ `['平衡二叉树']`；一道题给两个 KP ⇒ 各 1 hit ⇒ 仍 `[]`。★ 取证曾不可能：工具回文 `format_grading_for_chat` 只输出 评分/结论/错因，**不含 KP**，而 harness 跑完就把 Store 清了 | ✅ **已修（本轮，取证通道 + 判据）**：`run_sessions` 在**清理之前**读出 episodes 落进 `CaseRecord.episodes`（`topic/score/knowledge_points/type`）；护栏 **⑲a~⑲e**（⑲d 用最小假 store 驱动**真实** `run_sessions` 验接线，⑲e 把读到的 episodes 直接喂聚合复现同一条链）。⇒ 剩下的属**样本设计决策**（A 段改成同一考点 / 按章聚合 / 只披露）= **D8**。✅ **已闭合（D8 ①，§20.8.6）**：A 段两题对齐同一考点，`mem-002` 在 ON 侧「前置条件 + 有卡 + 召回 + used + correct_use」首次全绿 |
| 23 | **检索链上有一层「实现了但从未开启」**：`verifier` 的 LLM 相关性校验层，全仓 **24 处调用一律 `use_llm_verify=False`** ⇒ 该层对最终指标**没有任何贡献证据** | `retriever.py:377/403` 在 `use_llm_verify=True` 时会 `await _arun_llm_relevance_check(...)`（⇒ §20.5.2 已纠正审计件把它称作的「死代码」：它是**接了线的开关**，不是死码）。但实测所有调用点（`agents/tools.py`、`evaluation/adapters.py`、`retrieval_gate`、`task_eval/retrieval_probe` 及 `scripts/` 下 20 个实验脚本）都传 `False`；全仓 `use_llm_verify=True` **出现 0 次** ⇒ 这一层今天实际不执行 | 🔵 **已裁决（D10，2026-10-07）：承认未验证并披露，不跑消融、也不删。** 论文里检索章描述该层时必须写「已实现，**默认关闭且未做消融**，本文所有检索数字均不含该层的贡献」；❌ 不得写成「相关性校验提升了检索质量」（无证据）。不删的理由：删要连 `use_llm_verify` 参数一起动，波及 20+ 脚本的签名，收益只是少一段不调用的代码 |
| 24 | **paired control 的 OFF 臂从未真正关掉 Store**：旧实现只置 `agent.store = None`，而 `teaching_graph.load_memory` 与 `remember._record_episode` 都在**调用时**取进程级 `get_store()`、根本不看 `agent.store` ⇒ 两组是同一条件，**Step 5 起的「ON 有卡 / OFF 无卡」对照一直是假的** | 直接证据就在归档里：`phase1_memory_step5_store_off_step9_d8.jsonl` 的 `mem-002`（`store_enabled=False`；user_id 每 case 带随机后缀 ⇒ **不可能**是别的 case 残留）：A 段两次批改 `scores=[0.0, 0.0]`，B 段**注入了记忆卡**「薄弱：图的存储」，回复「根据你的做题记录，薄弱点在「图的存储」」⇒ 写链与读链都没关。★ **两个缺陷互相掩盖**：Step 5 当时 OFF 显示「0 卡 0 召回」被当作对照生效的证据，那其实是 #22（画像恒空 ⇒ 谁都召不回）造成的假象 —— 修好 #22 之后 OFF 才露出「照样有卡」。该记录的 `episodes=[]` **不能**当反证：OFF 臂 `eff_store=None`，取证通道压根没读 | ✅ **已修（本轮）**：抽成 `_off_arm_disable/_off_arm_restore`，**两处一起摘**（`agent.store` + `set_store(None)`），并在 `finally` **最前**恢复 —— 进程级那条忘恢复 ⇒ 之后所有 case **静默**失去记忆且不报错，比不恢复 agent 严重得多。护栏 **㉒a~㉒e**（㉒a/㉒b 按构造断言 ON/OFF 轮内 `get_store()` 的**实际值**；㉒c 锁恢复；㉒d 锁 notes 自证控了什么变量；㉒e 锁护栏自身不污染进程）。★ 连带把 **⑦b/⑦c 从源码文本断言改成行为断言**：抽 helper 后它们立刻变红，正好演示了那类断言的脆弱（**代码搬家、行为没变、红灯却响**）；反向验证 = 把 `_off_arm_disable` 临时换成旧实现 ⇒ ⑦b 必然红（实测 `tamper_red=True restored_green=True`，脚本为一次性件、未入库）。⇒ **既有 OFF 组的对照证据作废**，已用修好的 OFF 重跑（`step9_d8b` ⇒ **§20.8.6：配对第一次成立**，可测正样本 n=1） |
| 25 | **批改会把「作答正确」的题判成低分**（方向与缺陷 A 相反：不是把错题判满分，而是**把对题判零分**） | 实测 `phase1_memory_step5_store_on_step9_kp.jsonl` 的 `mem-003` 第 1 题：「判断序列 5, 8, 12, 19, 28, 20, 15, 22 是否构成小根堆，我认为构成」⇒ 逐层校验（1-based：5≺8,12；8≺19,28；12≺20,15；19≺22）**无违例、确为小根堆**，学生答对；批改却输出 **0.0 分**、KP 归到 `['堆排序','二叉树']`。★ 判定用的是当场写的 12 行堆校验器（`违例=[]`），不是人工肉眼 | 🔵 **只披露，不擅自改产品**。三点边界：① **单次观察**（Step 9 三次重复里只有这一处方向错），不足以定「批改普遍过严」；② **不进任何已发表指标** —— 该题只存在于 `memory` case，`grade` 的 15 条另有 `verdict_agreement`（13/13）覆盖；③ 原 §20.8.3 把它**误记**成「错题被判 100 分」，该归因已作废（那 100 分是判对的，错在 gold 要求两次都低分 ⇒ 属 D8/#26 的 case 设计问题）。是否值得为它扩评测集 = 后续决定，本轮不动 |
| 26 | **`recalled` / `used` 用子串包含判定，而正样本的 gold `values` 写的是章名** ⇒ 「召回成功」这句话偏松：任何含该字的记忆卡都算命中 | 口径写在 `memory_scorer` 顶部（`recalled_actual = 任一 card 含 values 中任一值`）。旧 `mem-002` 的 values = `["图"]`，而实测卡面是「薄弱：**图**的存储」⇒ 靠子串通过；`mem-003` 的 `["排序"]` 会被「快速排序 / 希尔排序 / 堆排序」**任一**满足 ⇒ 「召回成功」**测不出「召回的是不是设计的那个薄弱点」** | ✅ **已收紧（D8 第三次）**：两条正样本的 `values` 改为具体考点（`图的存储` / `快速排序`；改前核对两值均在 `canonical_names()`，`task_eval sanity` 复跑 **ERROR 0**）⇒ 正样本现在断言精确薄弱点。★ **子串口径本身不改**：记忆卡是自由文本「薄弱：X」，改全等会把排版差异也算成未召回（另一种错）。★ **负样本刻意保留章名**（`mem-005`/`mem-006` 的 `["图"]`）：对 `should_be_recalled=False` 来说偏松匹配让它**更难通过**（方向保守），无假通过风险 ⇒ 不动。指纹 `ffcf2b3233fc5595` → `3c938365da7ce614`（§20.0） |
| 27 | **layer top-up 路径把 `knowledge_points` 写死成空列表**，而同一份 `metadata` 里就带着 JSON 字符串 ⇒ 凡走这条路径进 top-k 的证据，在 `kp_hit` / `kp_mrr` / `coverage` 眼里**等于没标考点**（系统性假阴性，与 #10 同属「指标侧读不到真值」那一类） | 三条**互相独立**的证据：① **按构造**：`rag/layer_recall.py:43` 写 `knowledge_points=[]`，而主路径 `rag/evidence.py:93` 用 `_parse_knowledge_points(meta.get("knowledge_points"))`。本轮用假 Document（metadata 带 `["cn.arch.performance","带宽与时延"]`）直接驱动 `_doc_to_evidence` ⇒ 解析器给 **2 项**、该函数给 **`[]`。② **索引侧不背锅**（对 6 个集合做**全量分页**扫描，不是抽样）：`data_structure 777/785=99.0%`、`computer_organization 462/464=99.6%`、`operating_system 405/405=100%`、`computer_network 357/357=100%`、`questions 1358/2050=66.2%`（空值集中在 `doc_role=exam_answer` 685 条 + `exam_item` 7 条）；分桶看 **`doc_role=method` 在四个学科集合都是 100%**，`textbook` 只有 `data_structure 36/44=81.8%` 与 `computer_organization 27/29=93.1%` 有空（os/cn 的 textbook 100%）—— 这正是 §20.5.1 说的「仅剩 10 条 basic 讲义 detail 块」。③ **归档侧对不上**：两份 Step 9 探针归档 `phase1_step9_probeonly_{grade,verify}.jsonl` 的 **123 条 `top_items` 有 60 条 `kp` 为空**，其中 **13 条 `*/method` + 2 条 `*/textbook`** —— 按 ② 这些桶应当全有标签；且同一 `source`（`knowledge/advanced/computer_network/04_comprehensive.md`）在同一份归档里**既有带 kp 的、也有空 kp 的** ⇒ 差异只能来自路径，不能来自索引 | ✅ **已按 (B) 修（D12 裁决 2026-10-08）**。影响：`kp_hit` / `kp_mrr`（⇒ Generate 的 `coverage` 项）被**系统性低估**。★ 同时给 §20.5.1 那 **8 条 `coverage` N/A** 提供了一个比「旧索引未打标」**更可能的解释**：某题 top-5 若全走 top-up ⇒ `_all_kp(top)=[]` ⇒ 判 N/A；但归档**没存 `evidence_id`**（⑯ 只存 source/category/doc_role/kp/score）⇒ 这条**仍不能定论**，不许写成结论。三条路：**(A) 改产品**（`_doc_to_evidence` 改用解析器，1 行）：指标与对外契约一起变真，但 `EvidenceDoc.knowledge_points` 是**契约字段**（`agents/tools.py:54` 会带给 agent）⇒ **动检索链 ⇒ 触发新版本 + qa/generate 的 agent 侧数字要重跑（要 token）**；**(B) 只改评测口径**（`retrieval_probe._to_item` 在 `ev.knowledge_points` 为空时从 `ev.metadata` 兜底解析）：零 token、不触发版本，`retrieval_gate` 与探针当场可重测；代价是「指标说的」与「模型实际看到的」不一致（模型看到的 top-up 项仍无考点标签）；**(C) 只披露**。我建议 **(B) + 把产品侧那半单独披露**：与 #10 完全同构（修指标侧、离线重算、归档不改写），而 (A) 的代价是在收尾锚点上换检索契约。**已落地**：`retrieval_probe._to_item` 在 `ev.knowledge_points` 为空时从 `ev.metadata` 兜底解析（复用 `rag.evidence.parse_knowledge_points` —— 原先是私有名，已改公开，防两套解析分叉）；护栏 **㉕a~㉕e**（㉕a 驱动真实 `_to_item`；㉕b 反向：metadata 也没有 ⇒ 记空、**绝不虚构**；㉕c 锁「与解析器同结果」；**㉕d 锁产品契约仍不带宽 KP**（(B) 的边界，改回 (A) 必然红）；㉕e `_all_kp` 不再漏）。⇒ 影响实测见 §20.5.1 末：coverage N/A **12 → 1**、`kp_hit` **0.889(16/18) → 0.966(28/29)**（成对读数、零 LLM）。★ **历史归档一律不回写**：0B/Phase 1 的 `gen_coverage` / `kp_hit` 仍按当时读数引用，论文里两处并列披露 |
| 28 | **写入证据判据放错了位置、替原因下了结论、且没有下游读者**（2026-10-08 对自己代码的对抗性 review 抓到，四条同源问题一起修） | ① **位置**：`memory_write_missing` 的调用点原先在 `if case.task == "memory"` **之外**，而非 memory 任务走 `run_turns` —— 它照抓 `grade_scores`、却**从不**读 Store ⇒ `episodes` 恒空 ⇒ 任何一次 grade/verify/qa 实跑都会在**第一条**被判 `env_error`，而 `cli._run` 的 `break` 在 `append_record` **之前**（`cli.py:72-79`）⇒ 整轮中止**且那条记录连盘都不落**，中止日志取 `hard_fails[0]`/`retrieval_error`（两者皆空）⇒ 屏幕上是一行**没有原因的**「中止」。★ 这条直接卡住 `EFFECT_PLAN §6 Final Gate`。② **归因**：函数把「没落库」写成**环境类** —— 可缺陷 C（`record_grade` 拿不到 config 被静默跳过）的症状与 TEI 502 一模一样，而 `memory/safe.py:24-35` 把写失败压成一行 WARNING、既不计数也不落到 record ⇒ 单凭 `episodes==[]` **无法区分**，指认环境等于替缺陷 C 打掩护。③ **下游**：注释承诺「不进指标」，但 `report._is_invalid` 与 `memory_step5_paired.ArmSummary` **都不读 `env_error`**（全仓 grep 为零）⇒ 真正产出 Memory 数字的那条路径上，这种样本照样进分母。④ **读链**：清理前那次读取自己抛过错时只写进 `notes`（而 `notes` 从不进 record）⇒ 「没读到」会被下游当成「没写入」 | ✅ **已修（零 token）**：判据移入 memory 分支、**只报「证据缺失」不指认原因**（环境类仍由 `preflight_check()` 与 `is_env_error()` 判），命中时置 `validity_valid=False` ⇒ **复用既有排除链**，`report` 与配对脚本两侧同时生效；新增 record 字段 `memory_write_missing` / `episodes_read_failed`（读链坏了就**不做**写入推断）；`env_error` 兜一句可操作文案，中止日志不再可能为空。护栏 **㉓a~㉓i（10 项）**：㉓a 驱动**真实 `run_case`**（`_run_agent` 与检索探针打桩 ⇒ 零 LLM、零 TEI 依赖）证明 grade 任务不开火、㉓b/c 锁「命中 + 不指认原因」、㉓d/d' 三个反向（有 episode / 读链坏 / OFF 臂）都不报、㉓e+f **逐条验证两个下游读者**、㉓g/h 证明真实环境信号仍开火（没把闸拆没）、㉓i 锁字段落盘。★ **牙齿实测**：把调用点临时移回分支外 ⇒ `㉓a ❌ env_error=True primary=tool_error`、整套 gate 退出码 1；还原后 **175 项全绿 exit 0**（篡改是临时 Edit + 逆 Edit，未落进任何提交）。★ **行为变化要披露**：写链证据缺失**不再中止整轮**（改为逐条标不可测）⇒ 若 TEI 在跑到一半时挂掉，剩余 case 仍会烧 token；判断是不做「无流量的假设性加固」，且预检已在开跑前拦住（㉑a）。要不要加「连续 N 条写链缺失即中止」= **待裁决 D13**。 |
| 29 | **护栏自己不合格**：㉑c 把 `EMBEDDING_API_BASE` 留在死端口、㉑b 是弱预言、`scripts/` 从来不在 pyrefly 范围内（新写的 ㉒ 里就有一个真类型错） | ① `check_21` 的 `㉑c` 在原 `finally` **之后**改 settings 却只还原 `USE_FAKE_EMBEDDING` ⇒ 跑完 `EMBEDDING_API_BASE=http://127.0.0.1:1`（实测），同进程后续任何 embedding 调用都会 ConnectTimeout。今天没造成红灯**只是因为 ㉑ 后面恰好只剩 ㉒**（不碰 embedding）—— 而「护栏全绿但它描述的路径已不可达」正是本仓反复踩的那一类。② `㉑b` 写的是 `len(probs2) >= 1`，标题却声称「两条路径不互相掩盖」⇒ 删掉 health 那一支它照样绿。③ `pyproject.toml` 的 `project-includes = ["src"]` ⇒ `scripts/` 从未被检查；显式跑 `pyrefly check scripts/memory_step4fix_gate.py` 得 14 errors，其中 **`㉒d` 访问 `res_off.notes` 而 `_run()` 的返回注解写成了 `tuple[_SpyAgent, bool]`**（实返 `CaseResult`）—— 即「不污染进程」这套信任基础的类型从没被静态看过 | ✅ **已修（零 token）**：`㉑c` 包进 `try/finally` 两个字段一起还原，并新增 **`㉑c'`「跑完 settings 已还原」**（还原被删 ⇒ 必红）；`㉑b` 改**双向**断言（`不可达` 与 `推理` 两句都必须在）；`HTTPServer` 补 `server_close()`；`_run()` 注解改成它实际返回的形状（`tuple[smoke.CaseResult, bool 或 None]`） ⇒ 该文件 pyrefly 由 14 → **13 errors**（余下 13 条是 scripts 里的历史噪音：langgraph `Checkpoint` TypedDict 键、`sys.path` 注入导致的 `missing-import` 等，**不在本轮范围**，但口径必须改写）。★ 文档纪律：以后写「pyrefly 0 errors」一律注明**范围 = `src/`**，不能说成全仓 |
| 30 | **护栏的「判据数量」本身不可复现**（I6，与 #29 同属「护栏自己不合格」）：文档与标签里那句「175 项全绿」，在**干净克隆**上其实是「167 项跑过 + 8 项压根没跑」，而 `main()` 照样打印「GATE 通过 · exit 0」 | `⑬l×2`、`⑭d~⑭f`、`⑱a~⑱b`、`⑳d` 这 **8 项**读 `evals/results/task_eval/*.jsonl` 与 `calibration_30.jsonl`；按 **D11** 那些归档刻意不入库 ⇒ 缺文件时旧写法只 `print` 一行 `⏭`、**不进任何计数**，于是总数悄悄变小而退出码不变。★ 这是「**绿灯的数量**不可信」：我们反复防的是「绿而路径不可达」，这次坏的是计数口径本身。实测（一次性篡改脚本，未入库）：把 `check_20` 换成空函数 ⇒ `判定项 171 ≠ 声明 175` 且 exit 1；把 `ROOT` 指向空目录、只跑那四组 ⇒ `⏭` 恰好 **8 项**（另执行 24 项） | ✅ **已修（零 token；选「让数量自己说话」而不是「把归档入库」—— 后者与 D11 冲突）**：新增 `skip()`（跳过必须计数，一个 `if` 挡掉多项时用 `count=`）与模块级 `_EXPECTED_ITEMS = 175`；收尾两条不变量 —— ① 执行数（含跳过）必须等于声明值，② 跳过数必须为 0 —— 任一不满足 ⇒ `_flag()` 置红 + **exit 1**，文案写明「本次不能称为全绿，只能说跑了的那几项绿」。⇒ 新克隆上看到的是一行带原因的红灯，而不是一行更小的绿。★ 维护契约：**加判据必须同步改 `_EXPECTED_ITEMS`**，忘了就红（不靠人记性）。本轮护栏计数不变（仍 **175**，本机 skip=0） |
| 31 | 对**自己代码**的 review 余下 **12 条 Minor** 的处置：8 修 / 1 删 / 2 留（另 1 条被新护栏取代）——全部零 token | M7 是实测的：同一个「`/health` 404 但 `/embeddings` 正常」的本地桩，旧写法 `problems=['embedding 服务异常 HTTP 404…']`（会把能用的 TEI 拦在门外、`cli` 直接 return 3），新写法 `problems=[]`。护栏 **㉔a~㉔c**（正向 + 反向 + 「负样本用章名不报」三条一起，证明 lint 不是一刀切）、**㉑h**（M7）、**㉔d**（#26 不动已发表数字）；其余 6 条是小改（见处置） | ✅ **修**：M2 `_off_arm_*` 恢复状态改用 `_UNSET` 哨兵（原先 `None` 把「无需恢复」与「恢复成 None」压成一种）；M3 `cli` 打印 `informative_share` 加 `or 0`；M4 `⑳b` 改引用 `CALIBRATION_THRESHOLDS["spearman_min"]` 而不是写死 0.70；M5 `_INFORMATIVE_SHARE_MIN` 改公开名（原先 `cli`/护栏跨模块取私有成员）；M6 `judge.py` 两处过期**行号**引用改成**符号**引用；M7 预检的 health 抱怨只在推理也失败时才计入；M9 护栏的 `HTTPServer` 补 `server_close()`；M10 正样本 `values` 粒度 lint。★ **删**：`㉒d`（它读的是 harness 自己写的 note 文本，突变「OFF 臂什么都不做」时照样绿、措辞一改就假红 ⇒ 是文档不是护栏；note 仍留在 harness 里供报告引用）。**留**：M8（预检沿用产品的 `get_embeddings()` 客户端 ⇒ 不另加短超时；探针必须走产品那条路，最坏 60s 可接受因为它在开跑前且失败即中止）、M12（非 memory 的 record 不存 `grade_scores`/`episodes`；C1 修好后该分支不再影响判定，没有消费者就不扩字段）。⇒ 护栏计数 175 → **179**（`−㉒d` 1、`+㉑h` 1、`+㉔a~d` 4） |
> ★ **#31 的两个意外收获（比修复本身更值得记）**：**① 新 lint 与既有护栏撞车** —— `⑤c` 的 fixture 一直用 `图` 当「canonical **name**（不是 ID）」的正面例子，而新的粒度 lint 判 `图` 是 `domain`、正样本 ERROR ⇒ `⑤c` 当场变红。**发现它的是 #30 那条计数不变量**（`判定项 179 ≠ 178`、exit 1），不是人肉看出的。修的是 fixture 的取值（`图` → `图的存储`，意图不变），**不是**放宽 lint。★ 撞车的根因是两条护栏各自用同一个词表达**不同**的意思（⑤c 说「名字合法」，㉔ 说「粒度够细」）。**② ㉔d 的第一版绑了两个变量** —— 它比「归档值 vs 当前代码重算」，于是立刻红在 `mem-006`：归档 `(T,T,T)` → 当前 `(T,F,F)`，而那是 **#4 已发表**的口径修正（负样本的 `used` 需要召回事实前提），不是 #26 的回归。⇒ 改成「**同一份代码**下，归档 gold vs 当前 gold」，只让 gold 改动说话。教训：**一条判据只能绑一个变量**，否则红灯无法解释；而这条教训本身是被 ① 那套计数机制暴露的。

### 20.5.1 ★ Generate 主指标解剖（#2 的取证，2026-10-07）

**真正的问题不是"选哪个公式"，而是"五项"里只有两项有区分力。**

| 项 | 可测题数（归档） | 可测题数（现索引） | True 数 | 判定 |
|---|---|---|---|---|
| `gen_structure` | 15/15 | — | **15** | ⚠️ **恒真**，零区分力（靠模板标签，实际只验"没崩"） |
| `gen_answerability` | 15/15 | — | **15** | ⚠️ 同上 |
| `gen_correctness` | 15/15 | — | 14 | ✅ 唯一稳定有区分力的轴 |
| `gen_coverage` | **7/15** | 裸查 **15/15**（指示性，非结论） | 归档 5 → 现算 **13** | ✅ **已定论（#27 / D12 选 (B)）**：主因是**读数通道**（top-up 丢 KP），不是索引缺标签 —— 见本节末「定论」段 |
| `gen_difficulty` | **0/15** | **0/15** | — | ❌ **结构性死项** |

平均每题**只有 3.47 项可测**（7 题 4 项 / 8 题 3 项）——所以"五项完整交付率"这个名字目前**名不副实**。

#### 那 8 个 `gen_coverage` 的 N/A：**已定论** —— 主因是读数通道（#27），不是索引缺标签（★ 本节结论降级过一次、这次升级回来，过程全留）

我**先前用「每集合抽 400 条」外推成"六个内容集合 100%、重跑即救"——那是错的**。
下面是**全量分页扫描**（只读，零 token）的真实数字：

| 集合 | 有 KP / 总数 | 覆盖率 |
|---|---|---|
| `data_structure` | 777 / 785 | **99.0%**（缺 8） |
| `computer_organization` | 462 / 464 | **99.6%**（缺 2） |
| `operating_system` | 405 / 405 | 100% |
| `computer_network` | 357 / 357 | 100% |
| `questions` | 1358 / 2050 | **66.2%**（缺 692） |
| `learning_paths` | 24 / 24 | 100% |
| **合计** | **3383 / 4085** | **82.8%** |

**缺标签块的身份已定位到具体 `document_id`**（不是"某一层普遍缺"）：

| 缺口 | 数量 | 是什么 | 与本判据的关系 |
|---|---|---|---|
| `doc_role=textbook` 的 `detail` 块 | **10 条**（ds 8 / co 2，如 `basic-ds-tree` / `basic-ds-intro` / `basic-co-bus`） | basic 讲义里少数没打上 KP 的正文块 | **相关** —— practice 模式可用层 = `["advanced","basic"]` |
| `exam-*-answer` 块 | **692 条**（`questions` 集合） | 真题**答案**文档的块 | **无关** —— `schema/task_policy.py` 强制 practice 的 `exam_resources` 全 forbidden，这些块**不进证据包** |

★ **定论（2026-10-08，零 token 的成对读数实验，`scripts/kp_paired_reading_probe.py`）**
在同**一次** `probe_retrieval` 里对每条证据同时记两套读数 —— `old = ev.knowledge_points`（修复前评测看到的）
与 `new = retrieval_probe._to_item(ev).knowledge_points`（#27 修好后从 `metadata` 兜底解析）——
query / 索引 / 融合 / 截断 / gold 全部相同 ⇒ 差异只能来自**读数本身**。结果（30 条有 `expected_kp` 的 case = generate 15 + qa 15）：

| 读数 | coverage N/A（整批无 KP 标签） | 可比对 | `kp_hit` |
|---|---|---|---|
| 修复前 | **12** 条 | 18 | 16/18 = **0.889** |
| 修复后 | **1** 条（只剩 `qa-009`） | 29 | 28/29 = **0.966** |

★ 被救回的 11 条里，generate 侧恰好是 `gen-002/003/005/006/008/009/012/014` —— **与两份归档里那 8 条 N/A 同号**；
qa 侧是 `qa-007/010/015`（归档 4 条 N/A 里的 3 条）。
⇒ 于是「最可能是旧索引、但不可证明」换成了**可证明的机制**：① 「索引没打标」不再是必要解释
（现索引 + 旧读数照样能造出 12 条 N/A）；② 「走 top-up 那条路进来的证据会丢标签」是**充分**解释，
且量级足以覆盖归档里那批 N/A。
★ **仍然不许写成结论的部分**：本实验**不能**断言「0B 当年那 8 条就是这个原因」—— 归档既没存
`evidence_id` 也没存 `top_items`（⑯ 之后才有），逐条溯源不可能；且本机 `settings.RERANK_ENABLED=false`
⇒ 这次是「同一次检索的两套读数」，**不是**与 0B 可比的重跑。
⇒ 论文口径：**coverage N/A 的成因已在机制层面定位并在评测侧修复**；历史归档那 8 条写作
「与已修复的读数通道一致，但无法逐条证明」。
★ 处置 = **#27 的 (B)**：只改评测读数，产品契约 `EvidenceDoc.knowledge_points` **不动**
（它经 `agents/tools.py:54` 交给 agent ⇒ 动它 = 动检索链 = 换锚点 + qa/generate 重跑）。
「模型实际看到的 top-up 证据仍无考点标签」这条**产品侧偏差单独披露**，并由护栏 **㉕d** 钉成可检查的事实
（将来改成 (A) 时那条必然红，用来提醒同步披露）。

⇒ 现在学科集合的覆盖是 **99.0–100%**，残留无标签块只有 10 条；而一条 query 的 top-5 全部落在这 10 条上的概率极低。
所以更一致的解释仍是：**归档（2026-10-06）跑在标签尚未打完的旧索引上**，此后索引重建过。

★ **复核记录（2026-10-07 晚）**：我后来用 `if meta.get("knowledge_points")` 重扫一遍，得到
「四学科 100%、ds 785/785」，与上表冲突。**是那次重扫错了** —— 该字段在 Chroma 里存的是
**JSON 字符串**，未命中的块是 `"[]"`，而**非空字符串 `"[]"` 在 Python 里为真**。按
`_parse_knowledge_points()` 的同口径（解析后判列表长度）重算，上表的 **99.0% / 82.8% 成立**。
⇒ 消费端**没有**这个坑（`evidence.py:43` 会 `json.loads` 后过滤空串，实测 `"[]"` 返回 `[]`、
探针的 `kp_hit` 正确走 N/A 分支）；坑只在**自己写扫描脚本**时。以后复核请直接用
`rag.evidence._parse_knowledge_points`，别手写真值判断。

**但仍不能定论**：`CaseRecord` **没有保存每块来源 / 是否带 KP**（`tool_calls` 只有 `{kind,status,query,docs}`），
所以「重跑后是否 15/15 可测」**无法从归档证明**。我做的裸向量重查（`15/15` 题 top-5 带 KP、按同判据重算
覆盖 **13/15**）只是**指示性上界**——它绕过了 policy 过滤 / 融合 / 重排 / 截断。
⇒ **由 Step 9 走完整管线实跑定论**；`runner.py` 的注释已同步更正为该事实。

#### `gen_difficulty` 是**双重断开**的死项，不是"暂时没数据"

```
① gold：`expected_difficulty` 15/15 为 None（键存在但没标定）
② query：文本里没有难度指定（`请出一道考查 Cache 映射与地址划分的题。`）
③ 代码：runner.py:475 `difficulty_match(case.gold.expected_difficulty, None)`
        —— 第二个入参**硬编码 None**，注释记为「用户 2026-10-06 裁决」
```

⇒ 无论重跑多少次都不可能可测。**"五项"实际最多四项。**

#### 建议口径（**D1 已于 2026-10-07 采纳，1/2 已落地**；`EFFECT_PLAN.md` 是冻结件，本节只登记建议与落地状态，不改它）

| # | 建议 | 成本 |
|---|---|---|
| 1 | ✅ **已落地**。主指标 = **逐题「适用项全过」**（N/A 项剔除）。它是唯一同时满足「§3.1 的 AND 精神（明令禁止简单平均）」与「§2.B.3 的 N/A 不进分母」的解。★ 用现索引重跑后该值 **仍 = 0.80**（失败 = gen-008 correctness、gen-010 / gen-012 coverage），但**分母变成齐的 4 项/题**，比现在混合 3.47 项的版本可辩护得多 | 零（口径选择） |
| 2 | 把名字改成 **「交付完整率（本批 4 项适用）」**，并把难度项**明摘为"按裁决搁置"**，而不是留一个恒 N/A 的第五项 | ✅ **已落地**：名字最终取 **「适用项全过率」**（比「本批 4 项」更不误导 —— 每题可测项数是 3 或 4，不恒为 4）；难度项在报告里明列 `n/a=15` 而非留作隐形第五项 |
| 3 | 🔵 **属论文措辞，代码不动**（报告已按项分列，15/15 恒真看得见）。`structure` / `answerability` 在论文里定位为 **格式前置门**（防崩），与质量轴**分开列**；否则它们会以 15/15 混进分母摊薄结果 | 零（叙述） |
| 4 | ❌ **不采纳**（超出毕设范围）。若坚持"五项"名副其实：需 ①query 补难度 ②15 条 gold 人工标 `expected_difficulty` ③**产品输出契约里得有"系统判定的难度"**（先查有没有该字段）⇒ 属改 schema + 重跑，**不建议在毕设范围内做** | 高 |

#### ★ 取证边界（必须连这张表一起引用）

本轮重算用的是**单集合裸向量查询 + top-5**，**不是完整管线**（未经 task policy 过滤、融合、重排、
截断）。⇒ 「重跑后 coverage 15/15 可测」是**指示性上界**，不是保证；真实数值要等 **Step 9** 走完整条链。

#### 本次调查里我犯的四处错（留此防重犯）

1. 把 `knowledge_points == "[]"` 当成"有 KP" ⇒ 一度虚报 top5 = 5/5；
2. 从**归档记录**读 `subject`（该字段未入档，全 None）⇒ 集合映射全落到默认 `data_structure`，第一轮重算作废；
3. 由 1+2 得出「`runner.py` 那句『`basic/`/`advanced/` 缺标签』**已不成立**」——**这本身说过头了**：
   全量扫描显示缺标签的确实是 **basic 讲义的 `detail` 块**（方向对），只是**范围被注释说大了**
   （只剩 10 条，且 `questions` 那 692 条与 practice 模式无关）。注释已按事实更正；
4. ★ **用「每集合抽 400 条」外推成"六个内容集合 100% 覆盖、重跑即救"** ⇒ 被**全量分页扫描推翻**
   （真实总体 **82.8%**，`questions` 仅 66.2%）。教训：**全称结论必须来自全量扫描**；
   抽样只能给指示，尤其当我自己已经看到 `semantic_cache` 是 0% 时，就该怀疑"100%"这个说法。

### 20.5.2 D3 落实前的**事实更正**（`EFFECT_PLAN §7.1` 的三条不都是死代码）

冻结件 §7.1 把三项并列成「dead code，每项删 or 接线」。逐条实测后：

| 项 | 实测状态 | 处置 |
|---|---|---|
| `memory/vector_search.asearch_episodes` | **真死**：全仓零调用，只在 `memory/__init__` 导出 | ✅ **已删**（模块文件 + 两行导出）。护栏 **⑮a/⑮b**：⑮b 用 **AST** 扫 import / 名字引用 —— 第一版用「文件文本里有没有这个词」，结果**扫到护栏自己**（注释里就写着这个函数名）⇒ 假红灯，已改；植入一个 `from memory.vector_search import asearch_episodes` 的探针文件后 ⑮b 确实变红（证明它会咬） |
| `rag/verifier._arun_llm_relevance_check` | **不是死代码**：`retriever.py:377/403` 在 `use_llm_verify=True` 时会 `await` 它；只是**全仓 24 处调用都传 `False`** ⇒ 「接了线但没人开的开关」 | 🟡 **保留。★ 已裁决（D10）：不做消融，改为披露** ⇒ 登记为偏离 **#23**（「实现了但从未开启，本文检索数字不含其贡献」）。不删的理由：删要连 `use_llm_verify` 参数一起动，波及 20+ 脚本的签名 |
| `service.py:89` handoff 过滤 | **by-design 惰性**，且源码注释已自陈「没有活路径…属有备无患，勿据此认为系统依赖它」 | ✅ **不动**（已如实披露；改掉反而丢信息） |

⇒ §7.1 的口径应读作「**1 删 / 1 做消融 / 1 已披露**」，而不是三处一刀切删除。

### 20.6 解析方式（**已可用**，2026-10-07 打标签后）

```bash
git rev-parse "V-2026-10-07^{}"            # → 0f24891599c194179755753d06e0d53f106d116e（落点提交）
git show V-2026-10-07 --stat               # 本节点完整状态
git show V-2026-10-07:docs/EXPERIMENTS.md  # 该状态下的实验文档（含本节）
```

### 20.7 一句话总结

本节把**效果章**的口径钉在「`PROMPT_SET_VERSION=2f485d2d7ef7` + 上列 5 个 demo 集指纹」上；
**权威检索路由未退化**、**E-5 证明词表注入有效**、**缺陷 A 的失败率修正为 `5/9 → 0/9`**。

本轮已修 **5 条口径错**（全部零 token 验证）：**#4**（`used` 要记忆卡事实前提 + `correct_use`
按极性；ON 组 `used` 2→1、`correct_use` 2→4）、**#6**（失败率分母改「有效 n」+ `invalid_n`）、
**#10**（`category_hit` 的学科码 `cn` 恒判未命中 ⇒ 加别名对齐，未登记记 N/A）、
**#8**（词表按 `node_kind` 剔 4 个课程根节点，162→158；归一化侧仍保 162 全量）、
**#7**（两极 gold 时 `score_tolerance` 判**不可判** + 保留 `raw_rate` + 报告 ⚠ 行 +
`gold_sanity` 集合级 PENDING；★ 处置是**换成 `verdict_agreement`**（实测 0B 15/15、Phase 1 13/13），
**不是**"补部分分"—— L3 全为 2 分选择题，**没有部分分可标**）。
分别由护栏 **③d~③j / ③i / ③j / ⑫k / ③l~③r'** 锁定。

第二批（同日 A/B 两组，全部零 token）又修 **6 条**：
**#11**（分数解析把「满分/总分」当得分 → 遮蔽后四级解析，③s/③t）、
**#12**（API 批改不透传 `knowledge_points` → 补参数，③u）、
**#14**（`--rejudge` 把 `case_invalid`/`memory_miss` 洗成「通过」 → 原样保留 + 按 `validity_valid` 重建，⑬a~⑬d）、
**#15**（cli 写 jsonl 不留尾换行 + 追加相撞 → 行格式收口 `write_jsonl`、追加前自愈补分隔，⑬e~⑬g）、
**#17**（`min_grade_calls: 0` 单独存在是永真 ⇒ mem-005 负样本对照从未被校验 → 新增 `max_grade_calls`，⑬h~⑬l）。
★ **两条 review 结论被实测推翻**，记在 #16/#17 里以免将来又被当成缺陷提出：
「并发下 config 回落会算到别人头上」不成立（contextvar 每 Task 副本，护栏 ⑩e 固化）；
「`forbidden_values` 应校验是否 canonical」是错的规则（它是回复文本里的自由词，不是 KP 名）。
**#13**（tool call 缺失 ⇒ 无原文可救）与 **#18**（gold 数据集本体未入版本控制）**只披露、不擅自修**。
第三批落 **D1/D3/D4** 三项决定：#2 主指标改逐题聚合（⑭ 6 项）、§7.1 三处「死代码」按实测**只删真死的那一条**（另两条一条是「接了线没人开的开关」、一条注释已自陈惰性，见 §20.5.2）、record 落 `prompt_set_version`（⑮ 6 项）。
Gate **201 项全绿**（101→116→128→129→134→138→148→157→162→175→179→184→194→**201**；162→175 = 收尾修复批：`㉑c'`/`㉑f`/`㉑g` 3 项 + **`㉓a~㉓i` 10 项**，见 #28/#29；175→179 = Minor 批（`−㉒d`、`+㉑h`、`+㉔a~d`，见 #31）；179→184 = `+㉕a~e`（#27 / D12）；184→194 = D14① 的 Verify 行为层（`+㉖a~㉖j` 10 项）；194→201 = D15/D16 的 Memory 结构断言（`+㉗a~㉗g` 7 项）。★ **#30 之后这句「全绿」变成脚本自证的**：收尾会比对 `_EXPECTED_ITEMS` 声明值并要求跳过数为 0，少跑或静默 `⏭` 都是 exit 1，见 #30）、`pyrefly` **0 errors（范围 = `src/`；`scripts/` 不在 `project-includes` 内，见 #29）**、ruff check/format 通过、
`task_eval sanity` 66 条 ERROR 0、两份归档 12 条 validity **逐条不变**（新 gold 不动已发表数字）。

**31 条已知偏离**全部登记（#31 = 对自己代码的 review 余下 12 条 Minor 的处置，含两条意外收获）（#28~#30 来自 2026-10-08 对自己代码的对抗性 review：#28 四条同源问题一起修、#29/#30 是**护栏自身**不合格 —— 进程污染 / 弱预言 / 计数不可复现）；**#2 已由 D1 定夺并落地（2026-10-07）**：主指标 = 逐题「适用项全过」**0.80**，项级池化 0.9423 降级为诊断（护栏 ⑭）。
★ **#27 是收尾复核时新发现的**（top-up 路径丢 `knowledge_points` ⇒ `kp_hit`/`kp_mrr`/`coverage` 系统性低估），**已登记、未改代码**，三条处置路 = **待裁决 D12**。
★ **#24 是 Step 9 之后新登记的**：paired control 的 OFF 臂从未真正关掉进程级 Store ⇒ **既有 OFF 组的对照证据全部作废**，已用修好的 OFF 重跑（§20.8.6：**配对第一次成立**，`mem-002` 同 case 同前置条件下 ON 有卡并召回 / OFF 零卡，可测正样本 **n=1**）。
★ **#25/#26 是同批次复核时新增的**：#25 更正了 §20.8.3 的一处**误归因**（批改其实把对题判成了 0 分，不是把错题判成 100 分）；#26 是 D8 改 case 过程中发现的「正样本 values 写章名 ⇒ 召回判定偏松」，已把两条正样本收到具体考点。
—— **#2 的解剖与采纳状态见 §20.5.1**（核心结论：五项里只有
`correctness` 与 `coverage` 有区分力；8 个 `coverage` N/A **疑似旧索引**产物——全量扫描显示四个学科集合
KP 覆盖已达 **99.0–100%**（仅剩 10 条 basic 讲义 detail 块）—— ★ **已定论（#27/D12）**：主因是读数通道，成对读数实测 coverage N/A **12→1**（§20.5.1 末）；但归档无 `evidence_id` ⇒ 当年那 8 条只能写「与已修复的机制一致」；
`difficulty` 是双重断开的死项）；**#3（provenance 无 prompt hash）/ #5（OFF 配对无正样本）** 需决定重跑口径；
**#9（0B 的 Memory 四率口径不同）在论文引用该数字时必须标注**；#1 已披露不修。

### 20.8 Step 9 实跑结果（2026-10-07 起，逐项追加）

> ★ 本节只放**跑出来的数**，每个数都标：归档文件名 + `code_version` + `prompt_set_version` + 调用次数。
> 既有归档一律**不覆写**（新结果写新文件名）；冻结的 0B 基线不动。

#### 20.8.1 E-5 复测：新 prompt hash `2f485d2d7ef7` 下，词表注入的效果**保持且更强**

| 项 | 值 |
|---|---|
| 归档 | `evals/results/task_eval/phase1_e5_step9_20261007.jsonl`（12 条 = 6 题 × 2 臂） |
| provenance | `prompt_set_version=2f485d2d7ef7` · `code_version=50b5017-dirty` · `model=dashscope:qwen3.7-flash` · `temperature=0.0` |
| 臂 A（注入词表） | system 1293 字符 · **实际注入 158 词**（#8 剔根节点后）· sha[:12] `adf234e3f7af` |
| 臂 B（8 条示例 = E-3 前口径） | system 389 字符 · sha[:12] **`0fe2deeddf69`** ⇒ ★ 与首跑那份**逐字节相同**，对照臂未被本轮改动污染 |

| 臂 | `all_canonical`（题级） | 词级跟随率 | 期望入桶 | 空产出 | 残留自造词 |
|---|---|---|---|---|---|
| **A** | **6/6** | **8/8 = 1.000** | **6/6** | 0 | **0 个** |
| **B** | 1/6 | 3/11 = 0.273 | 3/6 | 0 | 7 个（`图的存储结构`/`堆`/`小根堆`/`平衡因子`/`握手定理`/`无向图的度`/`邻接矩阵`） |

**Δ 词级跟随率 = +0.727**（首跑在 `f09c75642029` 下是 +0.602）。

★ **怎么读这个数**（三条边界，缺一条就是过度声称）：

1. 这**不是**同一配置的复跑：A 臂词表从 162 词变成 158 词（#8 剔 4 个课程根节点）⇒
   正确表述是「**#8 之后口径下的重测**」，不是「E-5 再跑一遍」。
2. 变好的那 1 个词正是首跑的残留自造词 `无向图`（本轮 A 臂 0 个自造词）。
   但**单条差异不外推**（纪律 #5，模型有随机性）⇒ 能出口的只有聚合值 8/8 与 6/6。
3. 「为什么剔根节点反而跟随率上升」给的是**机制推断**而非本轮实测因果：根节点本身
   canonical，模型选它也算「跟随词表」，但产出会聚成「整门课 = 一个薄弱点」的粗桶；
   候选变细后本轮全部落在细粒度考点上。要证实需另看 A 臂产出的 `node_kind` 分布。

⇒ **关闭 #8 的待办**（原记「E-5 的 0.875 属中间态，需在新 hash 下复测」）：
新 hash 下 A 臂 **1.000 / 入桶 6/6 / 零自造词**，方案 A 的结论保持且更强。

★ **本轮顺手修掉探针自己的两个问题**（都属于「自述与实际不符」）：
① 归档头部硬写「臂 A 词表 162」，而实际注入 158 ⇒ 改为运行时由
   `_system_vocab_size()` 计算并写入（解析逻辑收成一处，禁止两处各写一遍）；
② `E5_OUT` 传相对路径会在收尾 `OUT.relative_to(ROOT)` 抛 `ValueError`
   —— 实测 12 次调用**已跑完并已落盘**、只是退出码为 1，故数据没丢，但这类
   「崩在写盘之后」的失败极易被误读成「整跑作废」而重复烧 token ⇒ 已把相对路径
   先 resolve 到仓库根。臂名 `A_vocab162` **刻意不改**（旧归档按臂名存取）。

#### 20.8.2 离线复核（**零调用**）：#7/#11 的数字能复现，且 2 条「不可解析」的真实身份查明了

只用既有归档的 `reply` 原文 + 修好的解析器重算，不产生任何 LLM 调用：

| 归档 | grade n | `verdict_agreement`（重算） | `score_tolerance`（重算） | 解析不到分数的条 |
|---|---|---|---|---|
| `phase0_baseline_final.jsonl` | 15 | **15/15 = 1.000** | 15/15（但按 #7 判**不可判**，见下） | **0** |
| `phase1_baseline_v2.jsonl` | 15 | **13/13 = 1.000** | 13/13 | **2**：`grd-004`、`grd-011` |

⇒ §20.3 登记的 `verdict_agreement` 两个数**在 #11 修完解析器之后仍然成立**（不是靠旧解析器凑出来的）。
⇒ `score_tolerance` 那两行的 1.000 **仍按 #7 处置为不可判**：人工分是 `{100:8, 0:7}` 的两极分布，
   ±10 没有中间地带可判别 —— 报告里必须显示 N/A 并保留 `raw_rate`，不许当「判分能力完美」引用。

★ **那 2 条不可解析的到底是什么**（此前挂着「待 Step 9 观察」，现在零成本查清）：
两条 `reply` 的全文都是 28 个字符 ——

> `批改失败：批改失败（工具未返回评分结果，无法给出分数）。`

⇒ 归属**正确**：两条的 `primary_failure` 都是 `tool_error`、`failure_reason = ['tool_error']`、
   `final_quality = 0.0` ⇒ 「工具没出分」被记成了工具故障，**不是**被洗成通过。
   （我一度假设「`hard_fails` 为空 + `generation_ok=True` ⇒ 故障在分布里不可见」，
   实测**该假设不成立**，已撤回。）
⇒ 所以这 2 条的正确读法是：**分母里的 13 条是「工具出了分」的样本**，
   另有 2 条属产品侧批改链失败（缺陷 A 的残留症状），两者不可混为一谈。
   报告已强制披露「⚠ N 条未产出可解析分数」，本轮复核确认该披露与实际一致。

#### 20.8.3 Memory 配对重跑（3 次重复，实测 252 次 LLM 调用）：**本轮观察不到跨会话召回**，且原因已归因到三轮的逐轮证据

| 归档（`evals/results/task_eval/`） | 调用 | 用途 | 关键产出 |
|---|---|---|---|
| `..._step9_20261007.jsonl` | **126** | 6 条全量重跑（新 hash `2f485d2d7ef7`） | 正样本 ON 组 **0/3 有效** |
| `..._step9_diag.jsonl` | **65** | 逐轮日志上线后的诊断重复（3 条正样本 × 2 臂） | 证明「第 2 轮没调批改工具」 |
| `..._step9_kp.jsonl` | **61** | episodes 捕获上线后的归因重复 | 证明「KP 不重复 ⇒ 画像恒空」 |

★ 调用数是**按端点分别数 HTTP POST** 得到的（不是 dry-run 的估算 —— 它把全量那跑估成 ≈84，
    实际 126）：`api.deepseek.com` = agent 侧（`DEFAULT_MODEL=deepseek:deepseek-flash`），
    `dashscope.aliyuncs.com` = 批改结构化调用（`LLM_MODEL=qwen3.7-flash`）；
    本地 TEI/Chroma 请求（同三跑分别 1735 / 660 / 630 次）**不花 token**，故不计入。

★ 三次都是**独立重复**，不是「跑到绿为止」：第 2、3 次的目的写在名字里（`diag`/`kp`），
且每一次都完整报告自己的 `valid` 计数（见下），不挑好的用。

**汇总（三条正样本 mem-001/002/003 × Store ON）**

| 重复 | 前置条件满足 | 有记忆卡 | 召回成功 | 失败形态 |
|---|---|---|---|---|
| Step 5（旧，2026-10-06） | 1/3 | 1/3 | **1/3（`mem-001`）** | —— 这是论文里目前唯一的召回正例 |
| Step 9 全量 | **0/3** | 0/3 | 0/3 | A 段只捕获 1 次批改 |
| Step 9 diag | 1/3 | 0/3 | 0/3 | 同上 + 错题被判 100 |
| Step 9 kp | 1/3 | **0/3** | 0/3 | KP 不重复 ⇒ 画像空 |

**三重归因（每条都有逐轮/逐 episode 证据，不再是推测）**

1. **A 段第 2 轮有时不调用批改工具** —— `turn_log` 直接显示：
   `mem-001` 三次重复里 `tools=[['grade_student_answer'], [], []]`，第 2 轮空。
   ⇒ 「≥2 次批改」的前置条件不成立 ⇒ `case_invalid`（与产品召回能力无关）。
2. **错题被判 100 分**（缺陷 A 的现存症状）—— `mem-003` 第 2 次批改 `[100.0]`，
   gold 要求落在 `[0,59]` ⇒ `case_invalid`。另见 OFF 臂 `mem-003` 第 1 次抓到 `None`
   （调了工具但没抓到分）—— 与 §20.8.2 那 2 条 Grade 不可解析同源。
3. **正样本设计缺陷 #22** —— 即使前两条都不发生（`mem-002` 两次都 0 分、前置条件满足），
   `episodes` 显示两次批改的 KP 是 `['图的存储','数组与特殊矩阵']` 与 `['图']`：
   **没有任何考点重复** ⇒ `compute_weak_topics(...)` 现算 = `[]` ⇒ 0 张卡 ⇒ 召不回。
   同一函数喂「同一 KP 两次」立即得到 `['平衡二叉树']`（护栏 ⑲a/⑲b），
   ⇒ 不是聚合坏了，是**样本假设「同章不同考点会累计」与 `MIN_HITS=2` 按精确名计 hit 不符**。

**★ 归因 #2 的更正（2026-10-07 D8 二次修正时复核，原判**不成立**）**
原判「错题被判 100 分（缺陷 A 的现存症状）」搞反了方向。逐题复核：`mem-003` 第二题「对
49, 38, 65, 97, 76 以 49 为枢轴做一趟划分，我写成 38, 49, 65, 97, 76」—— 用教材 Hoare 双指针
复算的结果**正是** `38, 49, 65, 97, 76` ⇒ **学生答对了，模型判 100 分是判对的**；错的是 gold
要求「两次都 <60」⇒ **前置条件天然不可满足**（case 设计错，见 §20.0 指纹第三次漂移）。
同一批归档里**真正的**误判是反方向的、且只有一处：`mem-003` 第一题「序列 5,8,12,19,28,20,15,22
是否构成小根堆，我认为构成」—— 逐层校验该序列**确实是小根堆**（无违例），却被判 **0 分**。
⇒ 症状应记为「**批改把正确作答判成低分**（过严）」，而不是「把错题判满分」。
这条与 #13（tool call 缺失 ⇒ 无原文可救）无关，也不在缺陷 A 的既有形态里 ⇒ **新增登记为 #25**。

**Store OFF 臂**：三条正样本的 `episodes` 全为 **0 条**，`memory_cards=0`、`recalled_actual=False`
⇒ 当时读作「对照侧干净」。
**★ 该结论已被 #24 作废**：① `episodes=0` 是**取证通道没读**（OFF 臂 `eff_store=None`），不是
「没写入」的证据；② 修好 OFF 臂后重跑（`..._step9_d8.jsonl`，OFF 侧 `mem-002`）**照样注入记忆卡**
⇒ 那三次重复里 OFF 与 ON 是**同一条件**，「对照侧干净」不成立。
另需说明：即便当时的 0 卡为真，它在正样本上也是**平凡真**（#22 让画像恒空 ⇒ 谁都召不回），
证明不了「召回不可能来自 Store 之外」⇒ **OFF 对照必须用修好的接线重做**（§20.8.6）。

**结论（论文该怎么写）**

- 核心断言「**新 thread + 同 user_id 能跨会话召回**」的**直接证据只有 1 例**
  （2026-10-06 `mem-001`，ON 组 1 卡 1 召回）。Step 9 的三次重复**没有增加正例**，
  反而暴露上述三个前置/设计问题 ⇒ **不能**改口说「多次验证通过」。
- 可以说的是：指标侧的因果链已经**可归因**（`turn_log` + `episodes` + 极性口径），
  「测不到」不再会被误记成「产品差」。
- 要真正补上正例，需要 **D8** 的决定（下面登记）。

#### 20.8.4 #10 的正确值已补测（`--no-agent` 探针重跑）：**0.600 → 0.800 全部来自指标修复**

归档：`phase1_step9_probeonly_grade.jsonl` / `phase1_step9_probeonly_verify.jsonl`（各 15 条）。
★ **不是零调用** —— 检索管线自身要用 LLM 做 query 分解/HyDE，实测各 **13** 次远端 POST；
我先前把它说成「零 token」是错的，这里按实际计数登记。

**先把「指标效应」与「索引漂移」分开** —— 用**同一批 `top_items`** 分别套新旧公式：

| 任务 | 旧公式（`.get(subject, subject)`） | 新公式（`cn → network` 别名） | 其中 `cn` |
|---|---|---|---|
| grade | 9/15 = 0.600 | **12/15 = 0.800** | **0/4 → 3/4** |
| verify | 9/15 = 0.600 | **12/15 = 0.800** | **0/4 → 3/4** |

⇒ 输入完全相同 ⇒ 差异只可能来自公式 ⇒ #10 的定性成立：那 8 条确为**系统性假阴性**。
⇒ 剩下的未命中是**真实未命中**（`grd-009` 的 top-5 全是 `questions` 块；`co`/`os` 各 1 条），
   不是指标问题。
★ 这正是 **`top_items` 落盘的价值**：旧归档只能标「待重跑」，新归档能把
   「指标效应」与「检索到的内容」拆开重算（护栏 ⑯c 的用途在此兑现）。

#### 20.8.5 Step 9 各跑动的**版本归属**（引用前先看这张表）

| 归档（`evals/results/task_eval/`） | 实测 `code_version` | `prompt_set_version` | 与标签 `0f24891` 的关系 |
|---|---|---|---|
| `phase1_e5_step9_20261007.jsonl` | `50b5017-dirty` | `2f485d2d7ef7` | **在标签之后**（探针修正尚未提交 ⇒ `-dirty`） |
| `..._store_{on,off}_step9_20261007.jsonl` | `ab708e6` | 同上 | 在标签之后 |
| `..._step9_diag.jsonl` | `179187a` | 同上 | 在标签之后（含 `turn_log`） |
| `..._step9_kp.jsonl` | `6b53f4f` | 同上 | 在标签之后（含 `episodes` 与 #21 单一公式） |
| `phase1_step9_probeonly_{grade,verify}.jsonl` | `9fa42ef` | 同上 | 在标签之后 |
| `..._step9_d8.jsonl` / `..._step9_d8b.jsonl` | **`7304786`** | 同上 | 在锚点 ② 之内（`d8` 那两份的 **OFF 侧因 #24 作废**；`d8b` 是修好对照后的重跑 ⇒ §20.8.6） |

⇒ **含义分两层**：提示词侧**同源**（`PROMPT_SET_VERSION` 未变 ⇒ E-5 / Memory / 探针与 §20.0 登记的
   词表口径一致）；代码侧**比标签新**（`category_hit` 的别名修复与 `correct_use` 单一公式都在标签后）。
⇒ 所以引用时必须按这张表逐份标注，**不要**笼统写成「V-2026-10-07 的结果」。
★ 顺带说明：`code_version` 只跟踪 `src/ scripts/ pyproject.toml .env.example` 的脏状态 ⇒
   文档提交不会让它 `-dirty`，这也是 `ab708e6`（含未提交的文档改动）能显示为干净 SHA 的原因。

#### 20.8.6 D8 + #24 之后重跑：**第一次拿到真正有效的配对对照**（同 case、同前置条件，只差 Store 开关）

| 归档 | `code_version` | `prompt_set_version` | 内容 |
|---|---|---|---|
| `phase1_memory_step5_store_on_step9_d8b.jsonl` | **`7304786`** | `2f485d2d7ef7` | 3 条正样本 × Store ON |
| `phase1_memory_step5_store_off_step9_d8b.jsonl` | **`7304786`** | 同上 | 同一批 × Store OFF（**本轮起 OFF 真的关掉了进程级 store**） |
| `PHASE1_MEMORY_STEP5_20261007_2334.md` | —— | —— | 该轮报告（新档，**未覆写** `..._step9_d8` 那两份） |

**逐条（`turn_log` + `episodes` + `memory_cards` 三处一致才算数）**

| case | 臂 | A 段批改次数 | 分数 | 卡 | `recalled_actual` | `used` | `correct_use` | validity |
|---|---|---|---|---|---|---|---|---|
| mem-001 | ON | **1**（第 2 轮 `tools=[]`） | `[0.0]` | 0 | None | None | None | False（前置条件） |
| **mem-002** | **ON** | **2** | `[0.0, 0.0]` | **1**「薄弱：图的存储」 | **True** | **True** | **True** | True |
| mem-003 | ON | **1**（第 2 轮 `tools=[]`） | `[0.0]` | 0 | None | None | None | False（前置条件） |
| mem-001 | OFF | 1 | `[0.0]` | 0 | None | None | None | False（前置条件） |
| **mem-002** | **OFF** | **2** | `[0.0, 0.0]` | **0** | **False** | False | False | True |
| mem-003 | OFF | 2 | `[0.0, 0.0]` | 0 | False | False | False | True |

**四条结论**

1. **配对成立（本轮唯一的、也是第一次的硬证据）**：`mem-002` 两臂**都**满足前置条件
   （各 2 次低分批改、两次都落在同一考点「图的存储」⇒ `episodes` 可查），
   ON 侧 1 张卡 + `recalled/used/correct_use` 全 True，OFF 侧 0 卡 + `recalled=False`。
   两组**只差 Store 这一个变量** ⇒ 召回来源确证为 Store，而不是「碰巧提到」或 checkpointer 泄漏。
   ★ 这句话在 **#24 修好之前没有资格说** —— 旧 OFF 臂与 ON 是同一条件（`..._step9_d8` 里 OFF 侧
   `mem-002` 照样有卡就是证据），当时的「0 卡」只是 #22 造成的假象。
2. **D8 的 case 修正生效**：ON 侧第一次出现「前置条件 + 有卡 + 召回」三项同时成立的正样本。
   Step 5 那例 `mem-001` 只有召回、**没有**可信对照 ⇒ 现在论文里的正例升级为**带对照的 1 例**。
3. **★ #26 的收紧生效**：ON 侧 `recalled` 断言的是精确考点「图的存储」，不再是旧 gold 的章名「图」
   ⇒ 「召回成功」这句话现在测的是「召回的是不是设计的那个薄弱点」。
4. **仍受限，不粉饰**：可测的配对正样本 **n=1**。ON 侧 `mem-001`/`mem-003` 都因为
   **A 段第 2 轮没调用批改工具**（`tools=[]`）而 `case_invalid`；OFF 侧 `mem-001` 同样复现
   ⇒ 与 Store 无关，是 agent 行为的**概率性**问题（同一 case 在两臂表现不同：`mem-003`
   OFF 侧两轮都调了、ON 侧没调）。这是 §20.8.3 归因 ① 的**再次复现**，不是本轮引入的。

**论文口径（可以写 / 不可以写）**

- ✅ 可写：「在严格配对的 Store ON/OFF 对照下观察到跨会话召回：ON 侧满足前置条件的正样本
  召回 1/1，OFF 侧 0/2；该对照自 `7304786`（#24）起才真正控制住了 Store 变量。」
- ❌ 不可写：「多次重复验证通过」（可测 n=1）；也不得引用 #24 之前任何 OFF 侧的「0 卡」
  作为对照证据（那批归档的 OFF 与 ON 是同一条件）。

**★ 本轮调用数未能核对（我的操作失误，如实登记）**：stdout 被 `tail -60` 截断
⇒ 端点级 POST 计数通道丢失，**无法**像 §20.8.3 那样按 `api.deepseek.com` / `dashscope` 分别报数。
只能给 `turn_log` 可查的**下界**：agent 轮次 **18**（两臂各 9），其中批改工具被调用 **9** 次
（ON 4 / OFF 5）；每轮内部至少 1 次 chat completion ⇒ **≥18 次**，真实值更高且**不可考**。
教训（写进纪律）：**跑带 token 的实跑不要把 stdout 管进 `tail`** —— 计费凭证只存在于日志里。

### 21. `EFFECT_PLAN §6 Final Gate` 门槛回填（定稿于 2026-10-08，**早于 §6 那次实跑**）

> ★ **为什么必须现在定稿**：冻结件 §6 写的是「门槛数字推迟到 Phase 0 回填 —— 先测量，再据真实分布设定」，
> 而规则（怎么算）v1.0 已冻结。⇒ 门槛若等跑完再定，就是**看着结果画线**，等于没有门槛。
> ★ **本节是 §6 的执行细则，不改 `docs/EFFECT_PLAN.md`**（冻结件只读，drift 记在活文档 —— 纪律 #20）。
> ★ 数据来源全部可重跑：`PYTHONIOENCODING=utf-8 uv run python scripts/s6_baseline_distribution.py`
>   （只读归档、零 LLM）；检索侧由门禁自己判（命令见该脚本末行输出）。

| §6 维度 | 冻结的占位 | Phase 0 / Phase 1 实测 | 能否照原口径回填 | **回填门槛** | 依据与必须一起说的风险 |
|---|---|---|---|---|---|
| QA | ≥80% `final_quality≥4` | 0B **13/15=0.867** · Phase 1 **14/15=0.933** | ✅ 能 | **保留 ≥80%**（分母 = 判了分的 case；未判分记 N/A） | 有区分力：11/15=0.733 即 FAIL。主失败项 `generation_incomplete`(3) 与 `retrieval_miss`(2/1) |
| Generate | ≥75% 「五项完整交付」 | 两批均 **12/15=0.80**（逐题适用项全过，#2 主指标） | ⚠️ **口径已换** | **≥75% 挂在「逐题适用项全过」**，N/A 项不进该题分母 | ★ 不得再叫「五项完整交付率」：§20.5.1 实测五项里只有 `correctness`/`coverage` 有区分力，`structure`/`answerability` 恒真、`difficulty` 是死项（严格 5/5 = **0.00**）。`coverage` 还受 **#27** 读数影响（已修，成对读数 12→1） |
| Grade | ≥75% `score_tolerance@±10` | 两极 gold ⇒ 该率判为**不可测**（`rate=None`、`degenerate_gold=true`、`n_distinct_gold=2`、`raw_rate=1.0`） | ❌ **不能** | 换 **`verdict_agreement ≥75%`**（0B 15/15、Phase 1 13/13；`n_a=2` 必须披露） | ★ 天花板要写清：实测=1.000 ⇒ 门槛 0.75 只在掉到 11/13 以下才触发，**区分力有限**；这不是"补部分分"能解决的（#7：语料 674/674 都是 2 分选择题，无部分分可标） |
| Verify | ≥80% `final_quality≥4` | 0B 仍出题 **6/15**、有真题信息 3/15；Phase 1 **0/15**、9/15（人工读数，未留 case_id） · `final_quality≥4` 两批都是 **0/15** | ❌ 原口径不能当判据（见最后一格） | **已按 D14 选① 机械化**：①**硬条件**「仍出题率 = 0」（`metrics.verify_fabricated`）；②「L1 给出可核对真题条目」**≥6/15**（Phase 1 实测 7/15 减 1 条 ⇒ 容忍 LLM 随机性，`PHASE1_VERIFY.md` 自己记过同一证据包两次 5/5 vs 4/5）；③「L1+L2 ≥9/15」作辅助披露；★ `final_quality≥4` 与 `exam_hit@k` 降级为**诊断**，ge4 不达照实写 | 为什么 ge4 不能当判据：未达成 case 全是 `exam_hit=False`（检索层没真题证据），那种情况下 agent **诚实说明无法确认是正确行为** ⇒ ge4 测的是**检索覆盖**不是回答质量（与 #7/#10 同类）。★ 机械判据是**拿两份归档逐条对过账**的：仍出题 0B 命中 `ver-001/004/008/011/013/015` = 6 条、Phase 1 **0 条**（case_id 与人工记录逐条一致）；有真题信息 0B L1=**3**、Phase 1 L1+L2=**7+2=9** ⇒ 对上人工的 3/15 与 9/15，但人工那两个数本身是**混级计数**（给出题干/题号 与 只列年份来源 混在一起）⇒ 本判据拆 L1/L2 两级。★ 读 JSON 注意：`ver_fabrication` 是**坏事率**，其 `passed` 数的是「判为仍出题」的条数。护栏 **㉖a~㉖j**（㉖j 锁「老归档无 `ver_*` 键 ⇒ 读成未测量」，防 #21 那类读不到就当零）|
| Memory | ≥80% correct-use | 0B 该率**全 N/A**（6/6；#9：0B 的 gold 里没有 `expected_memory`）；新口径下可测正样本 **n=1**（§20.8.6） | ❌ **无法按 Phase 0 回填** | **已按 D15 改为三条结构断言**（不写百分数）：①**配对成立** `metrics.paired_control_verdict` —— 只统计「两臂都满足前置条件的正样本**交集**」，ON 侧必须召回、OFF 侧必须不召回，且 **OFF 侧出现任何记忆卡一律判失败**（= #24 探测器）；交集为 0 时判**不通过**，不许把「压根没配对」印成「OFF 干净」；②**可追溯** `metrics.memory_traceable`（逐轮日志 + 记忆卡通道 + `episodes` 字段 + `store_enabled` 齐备；`episodes=[]` 是合法结果，缺字段才是没测）；③**分母摊开** `report.memory_measure_scope`（正样本总数 / valid 数 / 不可测数 / 可追溯数）⇒ 报告里任何「100%」旁边必须能看到 1/3 | ★ 为什么：n=1 上的百分数没有统计意义（答辩问「这个 100% 是几条」就崩），而 0B 那批根本没测过这个量 ⇒ 与其回填一个假门槛，不如把「能不能证明」本身门槛化。护栏 **㉗a~㉗g**；㉗g 是拿 d8b/d8/kp 三份真实归档做的**历史三情形回归**（修好后通过 / OFF 有卡被抓住 / 无交集不算通过） |
| Retrieval | 不低于 V-2026-10-02 | ③ 锚点复现：`kp_mrr 0.8048/0.8051` · `kp_hit@k 0.9103/0.9167` · `category_hit@1 0.9423` · `kp_annotated 156/156`（§20.2 末） | ✅ **已有机械实现** | **`retrieval_gate` exit 0**（各指标不低于基线，容差 **0.02**） | ★ `mean_evidence_count` 有**运行间抖动**（同一份代码连跑 3.9295 vs 3.9231）⇒ 引用它必须带上抖动，别写成三位小数稳定的量 |
| hard failure | <5% | 两份归档都是 **0/66** | ✅ 能 | **<5%**，分子 = 有 `hard_fails` 的 case，分母 = **有效 n**（排除 `case_invalid`，#6） | 现状远低于门槛；分母口径必须与 `report.failure_rate` 一致，否则两处数字对不上 |
| tool error | <5% | Phase 1 grade **2/15 = 13.3%**（`grd-004`/`grd-011`，`PHASE1_VERIFY.md` TODO-1 root cause 未确证）；整体 2/66 = 3.03%；0B 全部 0% | ⚠️ **口径决定成败** | **已按 D16 定为「任务级 <5%」**：任一任务 ≥5% 即该行不通过；分子 = `primary_failure=tool_error` 或有 `hard_fails` 的 case，分母 = 该任务的有效 n；`scripts/s6_baseline_distribution.py` 末尾的 D16 段一行命令直接出每任务判定 | ★ 不用整体口径 = 不把 13.3% 说成 3%（否则「你这 <5% 怎么算的」站不住）。⇒ 当前 grade **预判不达**，#11/#12/#13 修完分数解析与 KP 透传后的真实值等 §6 整轮测 |
| provenance | 100% | 0B/Phase 1 归档 **0/66 带 `code_version`、0/66 带 `prompt_set_version`**（#3） | ❌ 对历史不可能 | **定义成「③ 之后新产出的每条 record 100% 带 `code_version` + `prompt_set_version` + `retrieval_cfg` + `top_items` + `turn_log`」** | 由护栏 ⑮d/⑮e/⑯/⑰/㉓i 保证；历史归档按 #3 披露「缺字段读作未知、**绝不回填当前 hash**」 |
| Docker / TEI | 一键启动成功 | 非数字项 | ✅ | **manual**：`docker compose up -d` → `preflight_check()` 返回空（㉑a 探真实推理端点、㉑h 不因缺 `/health` 假红） | 半死 TEI（health 200 / embeddings 502）是**实发事故**，预检必须拦在开跑前 |
| 四任务链 | 全部可演示 | 非数字项 | ✅ | **manual**：qa / generate / grade / verify 各跑 1 条 + memory 跑 1 条 A→B 跨会话（§20.8.6 那条 `mem-002`） | Memory 演示要能当场指出记忆卡（`MEMORY_CARD_MESSAGE_ID`），否则"有记忆"不可证 |

#### 三个洞（回填时暴露出来的，比门槛本身更重要）

1. ~~Verify 没有可机械判定的头号指标~~ —— **已闭合（D14 选①，2026-10-08）**：`question_id_recall@k` 依然不可计算（#20/D7 的披露不变），但 Verify 这一行不再悬空：改为两条机械断言（仍出题率 = 0 为硬条件 + L1 引用率 ≥6/15），判据落在 `metrics.verify_fabricated` / `verify_exam_item_cited` / `verify_exam_year_only`；record 侧三个 `ver_*` 字段**只在 verify 分支写**、无回复或探针跑一律 `None`（N/A，不进分母）；报告新增「Verify 专有（行为层三判据）」一节，并把 ge4 / `exam_hit` 明确标成诊断。★ 机械化不是「随便换一个能算的数」：它是拿 0B 与 Phase 1 两份归档**逐条对过账**的（仍出题的 6 个 case_id 与人工记录完全相同；有真题信息拆成 L1/L2 后 3 与 7+2 也对上人工的 3/15、9/15）。

2. ~~Memory 无法按 Phase 0 回填~~ —— **已按 D15 闭合**：改为三条结构断言（配对成立 / 可追溯 / 分母摊开），不再写百分数门槛；实现见 `metrics.paired_control_verdict` + `metrics.memory_traceable` + `report.memory_measure_scope`，配对脚本「四、判定」段落已改成**逐 case** 输出而不是汇总数。

3. ~~tool error 的口径决定成败~~ —— **已按 D16 定为任务级**（任一任务 ≥5% 即该行不通过）。当前 grade 任务级 13.3% ⇒ **预判不达**，真实值等 §6 实测。

★ 三个洞的**收尾状态：全部关闭**（D14 机械化 / D15 结构断言 / D16 任务级口径）⇒ §6 这张表每一行都有确定的算法与分母，不再有「等实跑再想」的空格。

#### 与 §6 实跑的关系

**怎么跑（写在这里，免得跑完争论口径）**

```bash
PYTHONIOENCODING=utf-8 PYTHONPATH=src uv run python -m evaluation.task_eval run   --judge --out evals/results/task_eval/phase1_final_gate_20261008.jsonl
```

- 成本参照：同规模历史整轮 `phase1_baseline_v2.log` 实测 **405 次** `chat/completions`
  （agent 与 RAG 链各端点分别数 POST，不用 dry-run 估算 —— 它的估算曾把 126 报成 84）。
- **检索配置必须是生产态**：本机 `.env` 是 `RERANK_ENABLED=false` + `use_rerank=True`
  ⇒ 实际 `rerank_effective=False`（`ARCHITECTURE.md:351-356` 解释了这对组合，§19 也把 Rerank 记为默认关闭）。
  新归档会把这个事实写进每条 record 的 `retrieval_cfg`（⑯），所以**可比性是可证的而不是假设的**。
- 模型：`DEFAULT_MODEL=deepseek:deepseek-flash`（agent）· `LLM_MODEL=dashscope:qwen3.7-flash`（RAG 链）
  · `RAGAS_JUDGE_MODEL=dashscope:qwen3.8-flash`（judge）⇒ 与 0B / Phase 1 两张表同源。
- 产出**一律新档**（`phase1_final_gate_*`），**不回写** 0B 与 Phase 1 的任何归档。
- 跑完按本节表格逐行填「实测值 vs 门槛」，**不达就照实写不达**（预期不达的两行：Verify 的 `final_quality≥4`、
  Grade 的任务级 tool error 13.3%）。

- 上面这张表就是 §6 的**验收定义**；实跑产出 `phase1_final_gate_*.jsonl` 后逐行填「实测值 vs 门槛」，
  **不达标就照实写不达标**（Verify 的 ge4 与 grade 的 tool error 当前**预判不达**）。
- ★ 本锚点之后新增的只有**一个只读诊断脚本** `scripts/s6_baseline_distribution.py`（纯新增，
  没有改动任何既有 `src/`+`scripts/` 文件），⇒ `git diff V-2026-10-08 HEAD -- src scripts` 应只显示该文件新增。
