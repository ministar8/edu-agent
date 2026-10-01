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
| vector_only | 1.000 | 0.9278 | **−0.035** | 0.933 | 5.67 |
| plus_topup | 1.000 | 0.9625 | 0 | 0.983 | **8.83** |

> **V-2026-10-02**（§18）。vector_only 较 V-2026-10-01 明显改善（kp_hit 0.967→**1.000**、
> kp_mrr 0.914→0.928）——正是排序方向修复（§18.2 #3）的直接效果：向量路由此前返回**最不相似**的 k 条。

### 2.1 真·重排对照（`RERANK_ENABLED=true`）

**归档**：`evals/results/retrieval/ablation/rerank_compare.json`

| 配置 | kp_mrr | 证据数 |
|---|---|---|
| full（rerank on） | **0.975** | 4.03 |
| no_rerank | 0.9625 | 5.62 |
| **Δ（rerank 带来）** | **+0.012** | −1.59 |

### 2.2 消融结论（论文可直接写）

1. **多路召回正贡献**：vector_only 相对 full **kp_mrr −0.035**；
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
- 软指标 `quality_score=0.1473`（evidence_usage 均值）
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
| l1_only | 0.983 | 0.9444 | −0.018 | 0.0 |
| l2_only | 0.783 | **0.7167** | −0.246 | 0.0 |
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

1. **L1 提供主要语义覆盖**（l1_only 0.944）：probe 偏学习/概念题，不外推到全部任务。
2. **L2 方法层覆盖不足**（l2_only 0.7167）：与 coverage analysis 互相印证。
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
| **ours** | **1.000** | **0.9625** | **0.983** | **0.992** | 5.60 |
| **Δ** | +0.033 | **+0.0875** | +0.067 | +0.036 | +0.87 |

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
3. 平均证据 4.73→5.60。

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
| grade | 0.667 | 0.667 | 0.200 | **0.267** | 1.000 | 1.000 |
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
| vector_only | 0.989±0.010 | 0.928±0.005 | 0.933±0.000 | 0.961±0.005 | 5.672±0.010 |

### 13.2 配对 Δ vs full

| Δ | kp_hit | kp_mrr | cat@1 | cat_mrr |
|---|---|---|---|---|
| Δ no_bm25 | −0.017±0.000 | **−0.062±0.000** | −0.033±0.000 | −0.017±0.000 |
| Δ no_metadata | +0.000±0.000 | **−0.021±0.000** | −0.033±0.000 | −0.017±0.000 |
| Δ vector_only | −0.011±0.010 | **−0.035±0.005** | −0.050±0.000 | −0.031±0.005 |

### 13.3 结论

1. **消融非常稳**：full/no_bm25/no_metadata 的 kp_mrr std=0；仅 vector_only ±0.005。
2. 论文表 2 可写 `mean±std`；**贡献排序：BM25 > vector_only > metadata**。
3. 方差实验**解释不了**旧表 −0.113→−0.021 的跨轮漂移（那是跨代码/跨索引差异，不是随机抖动）。
4. vector_only 是唯一有非零 std 的配置（近阈值边界样本）。

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
| 100%–off | **1.000** | **0.963** | 0.983 | 5.67→6.33 | 0% | ✅ 全程 |

**full 对阈值不敏感**：指标五档相同，只涨证据数。

### 14.2 vector_only（弱路由对照，V-2026-10-02）

| scale | kp_hit | kp_mrr | cat@1 | n_ev | fallback | q052 |
|---|---|---|---|---|---|---|
| 100% | **1.000** | 0.9306 | 0.933 | 5.65 | 1.67% | ✅ |
| 95% | 1.000 | 0.9306 | 0.933 | 5.72 | 0% | ✅ |
| 90% | 1.000 | 0.9306 | 0.933 | 5.88 | 0% | ✅ |
| 85% | 1.000 | 0.9306 | 0.933 | 6.17 | 0% | ✅ |
| off | 1.000 | 0.9306 | 0.933 | 6.28 | 0% | ✅ |

**关键变化**：**q052 在 100% 档即恢复**（V-2026-10-01 时需 0.9×）。
阈值松紧只改变证据数（5.65→6.28），**不再改变 kp 指标**。

> ⚠️ **边界抖动如实披露**：同一配置两次运行中，100% 档出现 kp_hit **0.9833 / 1.000** 两种结果、
> q052 ❌/✅ 两种结果 —— 与 §13 测得的 vector_only kp_hit ±0.010 一致。
> 故「0.9× 是安全拐点」这一结论在本版本**不再成立**（阈值已基本不咬合）。

### 14.3 结论

1. 阈值在 **full 下是有效质量控制**（稳健、不误杀），松紧只增证据数。
2. 排序方向修复（§18.2 #3）后，**vector_only 的阈值误杀基本消失**——
   此前 q052 需 0.9× 才恢复，现 100% 档即可。
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
| **代码版本** | **`1cc69b39f5c1287e2941ae282f9a03a5e80464c6`**（短 `1cc69b3`） |
| **黄金集 sha256** | **`be98912a4c91fb88151640c82515127465031c1e79382b99c40e32311d6d1a66`**（156 条） |
| 生成集 | `evals/datasets/ragas/ragas_paired20.jsonl`（20 条） |
| 冻结日期 | 2026-10-01 |

> **与实验的关系**：本节点所有归档均由 `1cc69b3` 的**前一工作区状态**产生；
> 提交时的唯一额外改动是 `Sequence[str]` **纯类型注解**（`rag/retriever.py`、
> `rag/layer_recall.py`，两文件均 `from __future__ import annotations`）——
> **无运行时行为差异，实验结果对 `1cc69b3` 有效**。
>
> **待补（结构性缺口，见 §18.6）**：归档 JSON 目前**不记录** `code_version` 与
> `golden_sha256`，反查需依赖本表；已在 §18.6 列为待修项。

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

| 层 | 状态 |
|---|---|
| ④ 文档数字 → JSON | ✅ 通过（全量审计 + 抽样反查） |
| ③ JSON → 脚本/参数 | ⚠️ 有 `config_snapshot`，但**无生成脚本名**；3 个归档无 cfg |
| ② JSON → 黄金集 | ⚠️ 部分记录了 golden 路径，**无哈希** |
| ① 节点 → 代码版本 | ❌ **全无**：**零个归档**记录 `code_version` |

**断点示例**：
```
paper_tables 表 2  full kp_mrr = 0.9625
  → component_ablation.json rows[full].kp_mrr = 0.9625        ✅
  → config_snapshot.full = {"note": "完整系统（当前默认）"}      ⚠️ 太薄
  → golden 路径 + limit=60 已记录                              ✅
  → 具体代码版本：无（需依赖 §18.0 的本表）                     ❌
```

**待修（列入下一步，冻结后不宜再改）**：给全部实验脚本统一注入 `provenance`
（`recorded_at` / `code_version` / `golden_sha256` / `script` / `argv`），
使每个归档自描述，不再依赖人工维护本表。
