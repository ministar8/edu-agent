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

**复现**：`uv run python scripts/lib/ablation_retrieval.py --limit 60 --configs full,no_bm25,no_metadata,no_decompose,no_hyde,vector_only,plus_topup`
**归档**：`evals/results/retrieval/ablation/component_ablation.json`

| 配置 | kp_hit@k | kp_mrr | Δ kp_mrr | cat@1 | 证据数 |
|---|---|---|---|---|---|
| **full（基线）** | **1.000** | **0.9625** | — | 0.983 | 5.65 （证据：`evals/results/retrieval/ablation/component_ablation.json`） |
| no_bm25 | 0.983 | 0.9000 | **−0.062** | 0.950 | 5.73 （证据：`evals/results/retrieval/ablation/component_ablation.json`） |
| no_metadata | 1.000 | 0.9417 | **−0.021** | 0.950 | 5.77 （证据：`evals/results/retrieval/ablation/component_ablation.json`） |
| no_decompose | 1.000 | 0.9625 | 0 | 0.983 | 5.65 （证据：`evals/results/retrieval/ablation/component_ablation.json`） |
| no_hyde | 1.000 | 0.9625 | 0 | 0.983 | 5.65 （证据：`evals/results/retrieval/ablation/component_ablation.json`） |
| vector_only | 0.983 | 0.9306 | **−0.032** | 0.933 | 5.67 （证据：`evals/results/retrieval/ablation/component_ablation.json`） |
| plus_topup | 1.000 | 0.9625 | 0 | 0.983 | **8.83** （证据：`evals/results/retrieval/ablation/component_ablation.json`） |

> **V-2026-10-02**（§18）。vector_only 较 V-2026-10-01 明显改善（kp_hit 0.967→**0.983**、 （证据：`git show 1cc69b39f:docs/EXPERIMENTS.md`）
> kp_mrr 0.914→**0.931**）——正是排序方向修复（§18.2 #3）的直接效果：向量路由此前返回**最不相似**的 k 条。 （证据：`git show e36c76675:docs/EXPERIMENTS.md`）
> ⚠️ vector_only 是唯一有非零 run-to-run 抖动的配置（§13：kp_hit ±0.010），故其数值以本节归档为准。 （证据：`git show e36c76675:docs/EXPERIMENTS.md`）

### 2.1 真·重排对照（`RERANK_ENABLED=true`）

**归档**：`evals/results/retrieval/ablation/rerank_compare.json`

| 配置 | kp_mrr | 证据数 |
|---|---|---|
| full（rerank on） | **0.975** | 4.03 （证据：`evals/results/retrieval/ablation/rerank_compare.json`） |
| no_rerank | 0.9625 | 5.62 （证据：`evals/results/retrieval/ablation/rerank_compare.json`） |
| **Δ（rerank 带来）** | **+0.012** | −1.59 （证据：`git show 3ff8519f7:docs/EXPERIMENTS.md`） |

### 2.2 消融结论（论文可直接写）

1. **多路召回正贡献**：vector_only 相对 full **kp_mrr −0.032**； （证据：`git show 1cc69b39f:docs/EXPERIMENTS.md`）
   BM25 **−0.062** > 元数据 **−0.021**。旧表「元数据贡献最大（−0.113）」**不成立**。 （证据：`git show 1cc69b39f:docs/EXPERIMENTS.md`）
2. **查询分解 / HyDE 仍无增益**：去掉后指标逐位不变。诚实结论——复杂度未兑现。
3. **L2 preferred top-up 只增加覆盖**（证据数 5.65→8.83），不改善排序指标。
4. **重排为弱正收益（+0.012）**，与更早的 −0.046 **符号相反**。 （证据：`git show 1cc69b39f:docs/EXPERIMENTS.md`）
   不宜写死「负优化」；准确表述：**在本黄金集上收益不稳定，默认关闭**。

---

## 3. Legacy 资产池策略（三策略对比）

**复现**：~~`uv run python scripts/legacy_runtime_compare.py`~~（一次性诊断脚本，`0cac1d4` 已删；git 历史可取回，归档 JSON 仍可读）
**归档**：`evals/results/retrieval/legacy_runtime/legacy_runtime.json`

| 策略 | 层精度 pack（6 probe 均值） | legacy 占坑 |
|---|---|---|
| keep | 0.396 | 29 （证据：`evals/results/retrieval/legacy_runtime/legacy_runtime.json`） |
| downrank | 0.438 | 27 （证据：`evals/results/retrieval/legacy_runtime/legacy_runtime.json`） |
| **drop / exclude（采用）** | **1.000** | 0 （证据：`evals/results/retrieval/legacy_runtime/legacy_runtime.json`） |

**结论**：调权重治不了数据治理问题；**真删 legacy 后层精度 → 1.000**。 （证据：`evals/results/retrieval/legacy_runtime/legacy_runtime.json`）
采用 `legacy_policy=exclude`（learn/method/practice/verify）+ `fallback`（grade/explain）。

---

## 4. 检索质量门禁基线（156 条全集）

**复现**：`PYTHONPATH=src uv run python -m evaluation.gates.retrieval_gate`
**归档**：`evals/baselines/retrieval_baseline.json`（fake-embedding 口径）

本轮运行：**门禁通过**。注意 `kp_mrr` 当前 0.6636 略低于基线 0.6698 仍判通过—— （证据：`git show 1cc69b39f:docs/EXPERIMENTS.md`）
若门禁本意是「不低于基线」，需确认容差口径（`rerun_summary.md` 问题 #8）。

| 指标 | 基线 |
|---|---|
| n_queries | 156 |
| category_hit@1 | 0.904 （证据：`evals/baselines/pre_task9_20261009/retrieval_baseline.json`） |
| kp_hit@k | 0.865 （证据：`evals/baselines/pre_task9_20261009/retrieval_baseline.json`） |
| kp_mrr | 0.670 （证据：`evals/baselines/pre_task9_20261009/retrieval_baseline.json`） |
| empty_result_rate | 0.0 |

> 该基线为**回归门禁**，非最优值声明。语义质量用真实 embedding 的消融（§2/§9）。
> ★ 代际：本表基线值（`category_hit@1 0.904` / `kp_hit@k 0.865` / `kp_mrr 0.670`）属 **10-10 换代前的
> 旧仪器**读数；同一路由（`fake+off`）当代基线为 `0.8846 / 0.9231 / 0.8041`，见 §20.7.3。 （证据：`git show 05a3767c3:docs/EXPERIMENTS.md`）
> 为什么不可互比：见 §18 抬头的代际脚注。

---

## 5. RAGAS 生成质量（V-2026-10-02 · 全量 20 条）

**口径**：`evals/datasets/ragas/ragas_paired20.jsonl`（20 条 = 4 类型 × 5）；
生成 `dashscope:qwen3.7-flash`；**judge `dashscope:qwen3.8-max-0902`（强制关 thinking）**；
k=5 · `--no-rerank`（与冻结检索版本同口径）；真实 bge-m3。

**复现**：`PYTHONPATH=src uv run python -m evaluation.ragas.cli --dataset evals/datasets/ragas/ragas_paired20.jsonl --sample-per-type 5 --no-rerank --include-details --tag final`
**整理**：`uv run python scripts/ops/ragas_report.py --tag final`
**归档**：`evals/results/generation/ragas/`（`raw.jsonl` / `metrics.json` / `summary.md`）
★ 代际：归档里的**数据**（`metrics.json` / `raw.jsonl`）时间戳为 **10-01**，只有 `summary.md` 是
10-11 —— 那是文档订正、不是重跑。所以本节数字同样属 10-10 换代前的旧体系（含当时的生产索引），
理由见 §18 抬头的代际脚注。

### 5.1 总体（四项均 n=20，无 judge 掉样）

| 指标 | **冻结版 V-2026-10-02** | 修复前三项检索缺陷时 | Δ |
|---|---|---|---|
| faithfulness | **0.7588** | 0.7595 | −0.001 （证据：`git show V-2026-10-02:docs/EXPERIMENTS.md`） |
| context_precision | **0.6840** | 0.7318 | −0.048 （证据：`git show V-2026-10-02:docs/EXPERIMENTS.md`） |
| context_recall | **0.4000** | 0.4625 | −0.063 （证据：`git show V-2026-10-02:docs/EXPERIMENTS.md`） |
| answer_relevancy | **0.5994** | 0.5324 | **+0.067** （证据：`git show V-2026-10-02:docs/EXPERIMENTS.md`） |

### 5.2 分查询类型（冻结版）

| query_type | faithfulness | context_precision | context_recall | answer_relevancy |
|---|---|---|---|---|
| **concept** | **1.000** | **0.817** | 0.633 | **0.792** （证据：`git show V-2026-10-02:docs/EXPERIMENTS.md`） |
| grade | 0.708 | 0.823 | 0.550 | 0.707 （证据：`git show V-2026-10-02:docs/EXPERIMENTS.md`） |
| code | 0.807 | 0.478 | 0.350 | 0.292 （证据：`git show V-2026-10-02:docs/EXPERIMENTS.md`） |
| **generate** | 0.521 | 0.619 | **0.067** | 0.606 （证据：`git show V-2026-10-02:docs/EXPERIMENTS.md`） |

### 5.3 结论

1. **concept 质量最高**（faith **1.000** / ansR 0.792）——与任务策略收益最大的类型一致。 （证据：`git show V-2026-10-02:docs/EXPERIMENTS.md`）
2. **answer_relevancy 提升 +0.067**（code 0.136→**0.292**）——排序方向修复后检索命中更精准， （证据：`git show V-2026-10-02:docs/EXPERIMENTS.md`）
   答案更切题。
3. **context_precision / context_recall 各降约 0.05–0.06**：排序修复让证据更「近邻」，
   但也更**集中**，对「参考答案覆盖率」略有不利。**样本每类 n=5，不作显著性判断**。
4. **generate 的 context_recall 0.067、code 的 answer_relevancy 偏低属口径失配**： （证据：`git show V-2026-10-02:docs/EXPERIMENTS.md`）
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

**复现**：`uv run python scripts/gates/agent_behavior_gate.py`
**归档**：`evals/results/system_validation/agent_behavior/agent_behavior_quality.json`

- 硬安全（泄漏/empty 硬教/无来源确认/编造页码）：**8 case 全 PASS**
- 软指标 `quality_score=0.1222`（evidence_usage 均值；该值受生成温度影响有 run-to-run 波动） （证据：`evals/results/system_validation/agent_behavior/agent_behavior_quality.json`）
- 三态 FULL/THIN/EMPTY 均 PASS

> State 闭环（`langgraph_state/state_gate.json`，4/4 PASS）**不依赖检索链**，
> 仍为 2026-09-30 录制，属可接受口径。

---

## 7. 一页结论（论文第 5 章可用）

| 主张 | 证据 | 数字（V-2026-10-02） |
|---|---|---|
| 多路召回优于纯向量 | §2 | vector_only **−0.035** （证据：`git show V-2026-10-02:docs/EXPERIMENTS.md`） |
| BM25 有正贡献 | §2 | no_bm25 **−0.062** （证据：`git show V-2026-10-02:docs/EXPERIMENTS.md`） |
| legacy 池策略必要 | §3 | 层精度 0.40→**1.000** （证据：`git show V-2026-10-02:docs/EXPERIMENTS.md`） |
| 系统稳定可回归 | §4/§6 | 门禁过 · agent 8/8 |
| 生成侧质量（concept 最优） | §5 | faith **0.759** · ansR **0.599** · concept faith **1.000**（n=20，V-2026-10-02） （证据：`git show V-2026-10-02:docs/EXPERIMENTS.md`） |
| 三层服务不同任务 | §9–§11 | learn→L1 / method→L2 / grade·verify→L3 |
| 任务×层策略交叉交互 | §12 | 错配偏好 prefer_l1 MACRO 0.347 vs ours 0.944 （证据：`git show V-2026-10-02:docs/EXPERIMENTS.md`） |
| pack sufficiency | §12.3/§15.7 | 兜底后全任务 nonempty=**1.000**（修复前 0.25） （证据：`git show V-2026-10-02:docs/EXPERIMENTS.md`） |
| 基础 RAG 对比 | §11 | kp_mrr **+0.088** （证据：`git show V-2026-10-02:docs/EXPERIMENTS.md`） |
| 消融可复现 | §13 | full/no_bm25/no_metadata kp_mrr **std=0** |
| 阈值稳健（full） | §14 | 五档指标不变；弱路由误杀可 0.9× 恢复（**不改默认**） |
| 负面/不稳（如实） | §2.1 | rerank **符号不稳**（+0.012 / 更早 −0.046） （证据：`git show V-2026-10-02:docs/EXPERIMENTS.md`） |
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

**复现**：`uv run python scripts/lib/ablation_retrieval.py --limit 60 --configs full,no_l1,no_l2,no_l3,l1_only,l2_only,l3_only,no_legacy,legacy_only`
**归档**：`evals/results/retrieval/layer_policy/layer_ablation.json`

### 9.1 逐层剔除 / 单层保留

| 配置 | kp_hit@k | kp_mrr | Δ kp_mrr | empty |
|---|---|---|---|---|
| **full** | 1.000 | **0.9625** | — | 0.0 （证据：`git show V-2026-10-02:docs/EXPERIMENTS.md`） |
| no_l1 | 1.000 | 0.9556 | −0.007 | 0.0 （证据：`git show V-2026-10-02:docs/EXPERIMENTS.md`） |
| no_l2 | 1.000 | 0.9514 | −0.011 | 0.0 （证据：`git show V-2026-10-02:docs/EXPERIMENTS.md`） |
| no_l3 | 1.000 | 0.9617 | −0.001 | 0.0 （证据：`git show V-2026-10-02:docs/EXPERIMENTS.md`） |
| l1_only | 0.983 | 0.9556 | −0.007 | 0.0 （证据：`git show V-2026-10-02:docs/EXPERIMENTS.md`） |
| l2_only | 0.783 | **0.7194** | −0.243 | 0.0 （证据：`git show V-2026-10-02:docs/EXPERIMENTS.md`） |
| l3_only | 0.000 | 0.000 | −0.963 | **0.983** （证据：`git show V-2026-10-02:docs/EXPERIMENTS.md`） |
| no_legacy | 0.983 | 0.8988 | −0.064 | 0.0 （证据：`git show V-2026-10-02:docs/EXPERIMENTS.md`） |
| legacy_only | 1.000 | 0.9450 | −0.018 | 0.0 （证据：`git show V-2026-10-02:docs/EXPERIMENTS.md`） |

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

1. **L1 提供主要语义覆盖**（l1_only 0.956）：probe 偏学习/概念题，不外推到全部任务。 （证据：`git show V-2026-10-02:docs/EXPERIMENTS.md`）
2. **L2 方法层覆盖不足**（l2_only 0.7194）：与 coverage analysis 互相印证。 （证据：`git show V-2026-10-02:docs/EXPERIMENTS.md`）
3. **L3 面向考试资源，不适合作通用知识解释库**（kp_mrr 0、empty 98%）：
   chunk 是题干/选项/答案/解析，缺定义原理推导；在 grade/verify 下不可替代。

**不要写**：~~「三层高度冗余」~~ · ~~「L3 不能当知识库」~~

**L3 待补任务专有指标**：exam_hit@k · question_id recall · answer availability

---

## 10. Task-aware Layer Ablation

**对照**：
- baseline = L1/L2/L3 平铺 + legacy=include
- ours = task_mode → preferred_layers → legacy_policy

**复现**：~~`uv run python scripts/task_layer_ablation.py`~~（两臂 {baseline, ours} 是
`scripts/exp/task_mode_layer_policy.py` 五臂 {flat≡baseline, ours, prefer_l1/l2/l3} 的子集，`8a51a87` 已合并去重；
本表数字与归档仍有效）
**归档**：`evals/results/retrieval/ablation/task_layer_ablation.json`

### 10.1 任务专有指标

| task_mode | 目标层 | baseline | ours | Δ | 泄漏 b/o |
|---|---|---|---|---|---|
| learn | L1 basic | 0.833 | **1.000** | **+0.167** | 0.00/0.00 （证据：`git show V-2026-10-02:docs/EXPERIMENTS.md`） |
| method | L2 advanced | 1.000 | 1.000 | 0 | 0.00/0.00 （证据：`git show V-2026-10-02:docs/EXPERIMENTS.md`） |
| practice | L2+L3 | 1.000 | 1.000 | 0 | **0.25/0.00** （证据：`git show V-2026-10-02:docs/EXPERIMENTS.md`） |
| grade | L3 exams | 0.667 | 0.667 | 0 | n/a （证据：`git show V-2026-10-02:docs/EXPERIMENTS.md`） |
| explain | L3 exams | 1.000 | 1.000 | 0 | n/a （证据：`git show V-2026-10-02:docs/EXPERIMENTS.md`） |
| verify | L3 exams | **1.000** | **1.000** | 0 | 0.00/0.00 （证据：`git show V-2026-10-02:docs/EXPERIMENTS.md`） |
| **MACRO** | | 0.917 | **0.944** | **+0.028** | （证据：`git show V-2026-10-02:docs/EXPERIMENTS.md`） |

> **2026-10-01 更新（P0' top-up eligibility）**：`task_layer` / `task_mode_layer_policy`
> 与 Agent 路径对齐，统一传入 `filter=policy.eligibility_where()`；
> `layer_recall.topup_preferred_layers` 合并同一 where，不再绕过 doc_role。
> **verify 0.333→1.000**（BST 类 query 不再被 top-up 塞入 `exam_answer` 后裁空）。 （证据：`git show V-2026-10-02:docs/EXPERIMENTS.md`）
> baseline 也因口径对齐而抬升，故 ours 相对 Δ 变小——增益主要在 legacy/access control。

### 10.2 结论

1. 任务感知层偏好有效：learn +0.333、method +0.167。 （证据：`git show V-2026-10-02:docs/EXPERIMENTS.md`）
2. access control 消除泄漏：practice 0.25→0。
3. L3 在 grade/explain 已可达；verify 命中仍低（0.333）= 待优化。 （证据：`git show V-2026-10-02:docs/EXPERIMENTS.md`）
4. **口径澄清**：相对 baseline 的增益**主要来自 legacy/access control**，
   不是 `preferred_layers` 排序单独贡献（见 §12）。

---

## 11. 基础 RAG 消融

**对照**：
- **basic_rag** = 语义向量 top-k（无 BM25/元数据/任务策略；层平铺、legacy 同池）
- **ours** = 完整系统

**复现**：`uv run python scripts/exp/basic_rag_ablation.py --limit 60`
**归档**：`evals/results/retrieval/ablation/basic_rag_compare.json`

### 11.1 检索口径

| arm | kp_hit@k | kp_mrr | cat@1 | cat_mrr | 证据数 |
|---|---|---|---|---|---|
| basic_rag | 0.967 | 0.875 | 0.917 | 0.956 | 4.73 （证据：`git show V-2026-10-02:docs/EXPERIMENTS.md`） |
| **ours** | **1.000** | **0.9625** | **0.983** | **0.992** | 5.67 （证据：`git show V-2026-10-02:docs/EXPERIMENTS.md`） |
| **Δ** | +0.033 | **+0.0875** | +0.067 | +0.036 | +0.93 （证据：`git show V-2026-10-02:docs/EXPERIMENTS.md`） |

### 11.2 任务口径（V-2026-10-02）

| task_mode | 目标层 | basic | ours | Δ |
|---|---|---|---|---|
| learn | L1 | 0.833 | **1.000** | **+0.167** （证据：`git show V-2026-10-02:docs/EXPERIMENTS.md`） |
| method | L2 | 1.000 | 1.000 | 0 （证据：`git show V-2026-10-02:docs/EXPERIMENTS.md`） |
| practice | L2+L3 | 1.000 | 1.000 | 0 （证据：`git show V-2026-10-02:docs/EXPERIMENTS.md`） |
| grade | L3 | 0.667 | 0.667 | 0 （证据：`git show V-2026-10-02:docs/EXPERIMENTS.md`） |
| explain | L3 | 1.000 | 1.000 | 0 （证据：`git show V-2026-10-02:docs/EXPERIMENTS.md`） |
| verify | L3 | 1.000 | 1.000 | 0 （证据：`git show V-2026-10-02:docs/EXPERIMENTS.md`） |
| **MACRO** | | 0.917 | **0.944** | **+0.028** （证据：`git show V-2026-10-02:docs/EXPERIMENTS.md`） |

### 11.3 结论

1. 相对朴素向量 RAG：kp_mrr **+0.0875**、kp_hit +0.033、cat@1 +0.067。 （证据：`git show V-2026-10-02:docs/EXPERIMENTS.md`）
2. 任务口径：learn +0.167（其余已同基线）。 （证据：`git show V-2026-10-02:docs/EXPERIMENTS.md`）
3. 平均证据 4.73→5.67。

> 论文「对比实验」主表：同黄金集、同指标、仅系统配置不同。

---

## 12. Task Mode × Layer Policy 交互实验

**对照**（安全字段冻结，只动 `preferred_layers`）：
flat（全层）/ ours（任务映射）/ prefer_l1 / prefer_l2 / prefer_l3

**复现**：`uv run python scripts/exp/task_mode_layer_policy.py`
**归档**：`evals/results/retrieval/layer_policy/task_mode_x_layer_policy.json`

### 12.1 主表（flat vs ours，论文表 6，V-2026-10-02）

| task_mode | flat hit | ours hit | flat prec | ours prec | flat pack | ours pack |
|---|---|---|---|---|---|---|
| learn | 1.000 | 1.000 | 0.583 | 0.583 | 1.000 | 1.000 （证据：`git show V-2026-10-02:docs/EXPERIMENTS.md`） |
| method | 1.000 | 1.000 | 0.606 | 0.606 | 1.000 | 1.000 （证据：`git show V-2026-10-02:docs/EXPERIMENTS.md`） |
| practice | 1.000 | 1.000 | 0.542 | 0.542 | 1.000 | 1.000 （证据：`git show V-2026-10-02:docs/EXPERIMENTS.md`） |
| grade | 0.667 | 0.667 | 0.267 | 0.267 | 1.000 | 1.000 （证据：`git show V-2026-10-02:docs/EXPERIMENTS.md`） |
| explain | 1.000 | 1.000 | 0.378 | 0.378 | 1.000 | 1.000 （证据：`git show V-2026-10-02:docs/EXPERIMENTS.md`） |
| verify | **1.000** | **1.000** | 0.333 | **0.417** | 1.000 | 1.000 （证据：`git show V-2026-10-02:docs/EXPERIMENTS.md`） |

### 12.2 附表：固定单层偏好（layer_hit_rate）

| task_mode | 目标层 | flat | ours | prefer_l1 | prefer_l2 | prefer_l3 |
|---|---|---|---|---|---|---|
| learn | L1 | 1.000 | 1.000 | 1.000 | 0.833 | 1.000 （证据：`git show V-2026-10-02:docs/EXPERIMENTS.md`） |
| method | L2 | 1.000 | 1.000 | 0.500 | 1.000 | 1.000 （证据：`git show V-2026-10-02:docs/EXPERIMENTS.md`） |
| practice | L2+L3 | 1.000 | 1.000 | 0.250 | 1.000 | 1.000 （证据：`git show V-2026-10-02:docs/EXPERIMENTS.md`） |
| grade | L3 | 0.667 | 0.667 | 0.000 | 0.000 | 0.667 （证据：`git show V-2026-10-02:docs/EXPERIMENTS.md`） |
| explain | L3 | 1.000 | 1.000 | 0.333 | 0.333 | 1.000 （证据：`git show V-2026-10-02:docs/EXPERIMENTS.md`） |
| verify | L3 | **1.000** | **1.000** | 0.000 | 0.000 | **1.000** （证据：`git show V-2026-10-02:docs/EXPERIMENTS.md`） |
| **MACRO** | | **0.944** | **0.944** | 0.347 | 0.528 | **0.944** （证据：`git show V-2026-10-02:docs/EXPERIMENTS.md`） |

> prefer_l3 经 sufficiency 兜底后与 flat 持平——**层偏好错配的「空包」伤害已消除**；
> 剩余交互伤害只由 prefer_l1 / prefer_l2（合规但错层）体现。

### 12.3 附表：pack_nonempty_rate（sufficiency）

| task_mode | flat | ours | prefer_l1 | prefer_l2 | prefer_l3 |
|---|---|---|---|---|---|
| learn | 1.000 | 1.000 | 1.000 | 1.000 | **1.000** （证据：`git show V-2026-10-02:docs/EXPERIMENTS.md`） |
| method | 1.000 | 1.000 | 1.000 | 1.000 | **1.000** （证据：`git show V-2026-10-02:docs/EXPERIMENTS.md`） |
| practice | 1.000 | 1.000 | 1.000 | 1.000 | **1.000** （证据：`git show V-2026-10-02:docs/EXPERIMENTS.md`） |
| grade | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 （证据：`git show V-2026-10-02:docs/EXPERIMENTS.md`） |
| explain | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 （证据：`git show V-2026-10-02:docs/EXPERIMENTS.md`） |
| verify | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 （证据：`git show V-2026-10-02:docs/EXPERIMENTS.md`） |

**修复前**：prefer_l3 的 top-up/排序把 exams 顶进候选，eligibility 裁掉 → **n_pack=0**
（practice 0.25 / method 0.333 / learn 0.667）。**修复后全任务 1.000**（见 §15.7）。 （证据：`git show V-2026-10-02:docs/EXPERIMENTS.md`）

### 12.4 结论

1. **pack sufficiency 已保底**：全任务 × 全策略 nonempty=1.000。 （证据：`git show V-2026-10-02:docs/EXPERIMENTS.md`）
2. **交互伤害仍在**（合规但错层）：prefer_l1 MACRO 0.347 · prefer_l2 0.528 vs ours 0.944。 （证据：`git show V-2026-10-02:docs/EXPERIMENTS.md`）
3. **ours**：hit 与 flat 持平 + verify 包纯度更高（0.333→0.417）。 （证据：`git show V-2026-10-02:docs/EXPERIMENTS.md`）
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

**复现**：`uv run python scripts/exp/component_variance.py`
**归档**：`evals/results/retrieval/ablation/component_variance/`（`run{1,2,3}.json` 明细 + `summary.json` 汇总入口）

### 13.1 mean ± std（n=3）

| config | kp_hit | kp_mrr | cat@1 | cat_mrr | evidence |
|---|---|---|---|---|---|
| full | 1.000±0.000 | 0.963±0.000 | 0.983±0.000 | 0.992±0.000 | 5.650±0.033 （证据：`git show V-2026-10-02:docs/EXPERIMENTS.md`） |
| no_bm25 | 0.983±0.000 | 0.900±0.000 | 0.950±0.000 | 0.975±0.000 | 5.733±0.000 （证据：`git show V-2026-10-02:docs/EXPERIMENTS.md`） |
| no_metadata | 1.000±0.000 | 0.942±0.000 | 0.950±0.000 | 0.975±0.000 | 5.772±0.010 （证据：`git show V-2026-10-02:docs/EXPERIMENTS.md`） |
| vector_only | 0.994±0.010 | 0.935±0.013 | 0.939±0.010 | 0.965±0.009 | 5.678±0.019 （证据：`git show V-2026-10-02:docs/EXPERIMENTS.md`） |

### 13.2 配对 Δ vs full

| Δ | kp_hit | kp_mrr | cat@1 | cat_mrr |
|---|---|---|---|---|
| Δ no_bm25 | −0.017±0.000 | **−0.062±0.000** | −0.033±0.000 | −0.017±0.000 （证据：`git show V-2026-10-02:docs/EXPERIMENTS.md`） |
| Δ no_metadata | +0.000±0.000 | **−0.021±0.000** | −0.033±0.000 | −0.017±0.000 （证据：`git show V-2026-10-02:docs/EXPERIMENTS.md`） |
| Δ vector_only | −0.006±0.010 | **−0.028±0.013** | −0.044±0.010 | −0.026±0.009 （证据：`git show V-2026-10-02:docs/EXPERIMENTS.md`） |

### 13.3 结论

1. **消融非常稳**：full/no_bm25/no_metadata 的 kp_mrr std=0；仅 vector_only 有非零 std（±0.013）。 （证据：`git show V-2026-10-02:docs/EXPERIMENTS.md`）
2. 论文表 2 可写 `mean±std`；**贡献排序：BM25 > vector_only > metadata**。
3. 方差实验**解释不了**旧表 −0.113→−0.021 的跨轮漂移（那是跨代码/跨索引差异，不是随机抖动）。 （证据：`git show V-2026-10-02:docs/EXPERIMENTS.md`）
4. **vector_only 是唯一有抖动的配置**（kp_hit ±0.010、kp_mrr ±0.013）—— （证据：`git show V-2026-10-02:docs/EXPERIMENTS.md`）
   其单轮数值不宜与其它配置等量齐观，跨批次比较时须看本节的 std。

> 脚注：n=3 独立进程；std 为运行间系统非确定性，不作为统计显著性检验。

---

## 14. E-next · RRF Threshold Sensitivity（2026-09-30）

**问题**：阈值是否在误杀已召回的正确证据？（由 q052 诊断引出）

**设计**：固定 60 golden / 索引 / embedding / top-k，**只改** `effective_threshold` 乘子
`{1.0, 0.95, 0.90, 0.85, 0}`。无 LLM。**不改默认 threshold**。

**复现**：`uv run python scripts/exp/threshold_sensitivity.py --arm full,vector_only`
**归档**：`evals/results/retrieval/ablation/threshold_sensitivity/threshold_sensitivity.json`

### 14.1 full（主配置，V-2026-10-02）

| scale | kp_hit | kp_mrr | cat@1 | n_ev | fallback | q052 |
|---|---|---|---|---|---|---|
| 100%–off | **1.000** | **0.9625** | 0.983 | 5.67→6.28 | 0% | ✅ 全程 （证据：`git show V-2026-10-02:docs/EXPERIMENTS.md`） |

**full 对阈值不敏感**：指标五档相同，只涨证据数。

### 14.2 vector_only（弱路由对照，V-2026-10-02）

| scale | kp_hit | kp_mrr | cat@1 | n_ev | fallback | q052 |
|---|---|---|---|---|---|---|
| 100% | **0.983** | 0.9222 | 0.933 | 5.70 | 1.67% | ❌ （证据：`git show V-2026-10-02:docs/EXPERIMENTS.md`） |
| 95% | 0.983 | 0.9222 | 0.933 | 5.77 | 0% | ❌ （证据：`git show V-2026-10-02:docs/EXPERIMENTS.md`） |
| **90%** | **1.000** | **0.9306** | 0.933 | 5.93 | 0% | **✅** （证据：`git show V-2026-10-02:docs/EXPERIMENTS.md`） |
| 85% | 1.000 | 0.9306 | 0.933 | 6.17 | 0% | ✅ （证据：`git show V-2026-10-02:docs/EXPERIMENTS.md`） |
| off | 1.000 | 0.9306 | 0.933 | 6.28 | 0% | ✅ （证据：`git show V-2026-10-02:docs/EXPERIMENTS.md`） |

**拐点在 90%**：q052 与 kp_hit 在 0.9× 恢复，再放松无收益；cat@1 不降。

> ⚠️ **边界抖动如实披露**：同一配置（100% 档）在不同批次出现过
> **kp_hit 0.9833 / 1.000**、**q052 ❌/✅** 两种结果 —— 与 §13 测得的 （证据：`git show V-2026-10-02:docs/EXPERIMENTS.md`）
> vector_only kp_hit ±0.010 一致。**该结论是边界性的**，不宜作强断言。 （证据：`git show V-2026-10-02:docs/EXPERIMENTS.md`）

### 14.3 结论

1. 阈值在 **full 下是有效质量控制**（稳健、不误杀），松紧只增证据数（5.67→6.28）。
2. 在 **vector_only/弱融合**下仍会误杀边界样本：q052 在 100% 档检出为失败，
   0.9× 后恢复 —— 但见上「边界抖动」，该差异处在测量噪声量级。
3. **不改默认 threshold**；问题在 **RRF 量纲与可达上限**（见 `postprocess._rrf_scale_needed`），
   不是阈值高低。

### 14.4 q052 摘要（诊断，不再继续优化）

- vector_only：目标已入池（rank 2）→ `dropped_by=rrf_threshold`（0.0857<0.088）→ 保底 top-1 错学科 （证据：`git show V-2026-10-02:docs/EXPERIMENTS.md`）
- full：L1 目标全程 rank 1 存活；多路召回救回
- **归因**：召回到了但被阈值滤掉；非召回失败

---

## 15. 版本节点 V-2026-10-01 · top-up eligibility 对齐（冻结）

**冻结内容**：证据资格边界修复。**不含** exam 专用召回器。

### 15.1 改了什么

| 文件 | 变更 |
|---|---|
| `src/rag/retrieval/layer_recall.py` | `topup_preferred_layers(..., eligibility_where=)`；`merge_where_filters(kb_depth, eligibility_where)` |
| `src/rag/retrieval/retriever.py` | top-up 传入主检索同一 `filter`（= `policy.eligibility_where()`） |
| `scripts/task_layer_ablation.py` | 补传 `filter=policy.eligibility_where()`（口径对齐） |
| `scripts/exp/task_mode_layer_policy.py` | 同上 |
| `scripts/gates/topup_eligibility_gate.py` | **新增**：4+1 场景资格回归门禁 |

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
| verify layer_hit | 0.333 | **1.000** （证据：`git show V-2026-10-02:docs/EXPERIMENTS.md`） |
| Task-aware MACRO（ours） | 0.833 | **0.944** （证据：`git show V-2026-10-02:docs/EXPERIMENTS.md`） |
| TMLP MACRO（flat/ours） | 0.833 | **0.944** （证据：`git show V-2026-10-02:docs/EXPERIMENTS.md`） |

> baseline 同步抬升，因实验路径原先未传 eligibility——增益主要来自 legacy/access control。

### 15.5 决策树结论（本轮）

| 检查项 | 结果 | 结论 |
|---|---|---|
| prefer_l3 空包是否因 P0' 恢复？ | **未恢复**（practice nonempty 仍 0.25） | → 已实施 sufficiency 兜底（§15.7） |
| verify 是否需 exam 专用召回？ | **不需要**（items 在池内 rank 6–9，能进包） | 维持当前路由 |
| verify 实验口径是否与 Agent 一致？ | 已对齐（同传 `eligibility_where`） | — （证据：`git show V-2026-10-02:docs/EXPERIMENTS.md`） |

### 15.6 P0'.1 补充：preferred 层与资格冲突时的 top-up 回退

**问题**：`preferred_layers=['exams']` 而 exams 不合规时，top-up 只按 `kb_depth=exams`
找（被 where 挡空），且**不为合规层补**，主池可能只剩 legacy → 包被掏空。

**修法**：`aretrieve_evidence_with_retry(..., eligible_layers=)`（新增可选参数）。
preferred 层**全部不合规**时收敛到 `eligible_layers`；生产 policy 恒一致，不影响默认行为。 （证据：`git show V-2026-10-02:docs/EXPERIMENTS.md`）
资格真源：`TaskPolicy.eligible_semantic_layers()`（basic/advanced 恒允许；exams 需任一资源 allowed）。

### 15.7 P0'.1 补充：Evidence Pack sufficiency 兜底

**问题**：错误层偏好把 eligibility 禁止的资源顶进 pack，Evidence Policy 全裁 → **n_pack=0**。

**修法**（`evidence_policy.finalize_with_layer_ranking`）：
包内已无合规项时，从 `main_items` 按 score 回填**合规项**。

- 新增 `pack_blocked(policy, ev)`：与 Evidence Policy 的剔除条件同源（eligibility / 缺题干 / explanation 隐藏）
- 只回填 `main_items`（已按 `legacy_policy` 过滤）→ **不引入被排除资产，不放松安全**
- 记入 `layer_pack.sufficiency_refill` 与 release flags（不静默）

**验证**：`scripts/gates/sufficiency_gate.py`（错误偏好 n_pack≥1 且无被禁资源；ours 不回归）

**结果**：`pack_nonempty_rate` **全任务 × 全策略 = 1.000**； （证据：`git show V-2026-10-02:docs/EXPERIMENTS.md`）
prefer_l3 MACRO 0.681 → **0.944**（与 flat/ours 持平）。 （证据：`git show V-2026-10-02:docs/EXPERIMENTS.md`）
leakage / mode_layer / retrieval_gate / topup_eligibility_gate 全过。

> **叙事更新**：层偏好错配的「空包」伤害已由兜底消除；
> 残余交互伤害只由 prefer_l1 / prefer_l2（合规但错层）体现——**这才是排序偏好的真实代价**。

---

## 16. L2 覆盖归因（2026-10-01，只分析）

**问题**：`l2_only kp_mrr 0.7167`，L2 是分层短板。 （证据：`git show 1cc69b39f:docs/EXPERIMENTS.md`）

**复现**：~~`uv run python scripts/l2_coverage_analysis.py`~~（一次性分析脚本，`0cac1d4` 已删；git 历史可取回，归档 JSON 仍可读）
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
   污染伤的是**证据包纯度与 `l2_only`**（0.7194），full 仅 −0.011；任务侧 （证据：`evals/reports/l2_impact_analysis.md`）
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
| `sufficiency_gate` | PASS（nonempty 全 1.000） （证据：`git show V-2026-10-02:docs/EXPERIMENTS.md`） |

### 17.4 冻结基线指标（最终 TMLP，2026-10-01）

| 策略 | MACRO layer_hit | pack_nonempty | leakage |
|---|---|---|---|
| **flat** | **0.944** | 1.000 | 0 （证据：`evals/results/retrieval/layer_policy/task_mode_x_layer_policy.json`） |
| **ours** | **0.944** | 1.000 | 0 （证据：`evals/results/retrieval/layer_policy/task_mode_x_layer_policy.json`） |
| prefer_l1 | 0.319 | 1.000 | 0 （证据：`git show 1cc69b39f:docs/EXPERIMENTS.md`） |
| prefer_l2 | 0.500 | 1.000 | 0 （证据：`evals/results/retrieval/layer_policy/task_mode_x_layer_policy.json`） |
| prefer_l3 | 0.944 | 1.000 | 0 （证据：`evals/results/retrieval/layer_policy/task_mode_x_layer_policy.json`） |

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

★★ **代际脚注（2026-10-14 补，统一说明，不在各表重复）**：本节、§1–§17 以及 §20.2 的四路由表，
都是 **10-10「语料体系换代 + 门禁仪器对齐」之前**的读数。取证：本锚点落点 `e36c766` ＝ **10-01**；
而 `94a6997`（code 库独立）、`d3813fb`（L3 收口 questions→exams）、`d60d8f0`（删旧体系）、
`a2dce06`（入库构建下沉 `ingest_layers`）、`8e2add6`（门禁对准生产入库路径 + 重录 6 份基线）、
`74b9eb5`（探针表改指新语料）**全部落在 10-10 当天**；生产索引亦于当日重建（`chroma_db` 现为
2026 chunk / 10 集合，与门禁临时索引逐位相等）。
⇒ 被改的是**测量的输入**（语料结构 + 索引构建链），不只是代码；所以这些数字描述的是旧体系，
不能当作当前行为的读数。**换代后的门禁权威读数一律看 §20.7.3**（`code_version = 78e8461`）。
引用时把两者并列并注明口径（「旧体系 V-2026-10-02 实测」vs「换代后 §20.7.3 基线」），
**不要**把它们当作同一口径下互相印证或互相矛盾的两个版本 —— 它们不可比。

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
| 1 | `rag/common/rag_utils.py` | 新增 `_DOMAIN_WORDS` + `ensure_jieba_domain_words()`：注册 9 个链表/线性表领域词 | 查询侧分词 |
| 2 | `rag/common/synonyms.py` | ① 新增 7 条「逆置」同义词；② 扩展守卫由「**子串**出现」改为「**已是分词结果**」 | 查询扩展 |
| 3 | `rag/retrieval/routes.py` | `_raw_search` 向量分支排序 `-score` → **`score`**（Chroma score 是**余弦距离**，越小越好） | **排序 bug** |
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

**#3 排序方向（决定性）**：用 chunk 原文检索自身，score = **0.0000**， （证据：`git show V-2026-10-02:docs/EXPERIMENTS.md`）
且集合 `hnsw:space=cosine` → **score 是距离**。原 `-score` 降序 = **返回最不相似的 k 条**：

| | 前 5 条 score |
|---|---|
| Chroma 原始（最近邻） | 0.3318 **← 目标** · 0.3579 · 0.3733 … （证据：`git show V-2026-10-02:docs/EXPERIMENTS.md`） |
| `_raw_search` 修复前 | **0.4212 · 0.4208 · 0.4198 …（15 条里最差）** （证据：`git show V-2026-10-02:docs/EXPERIMENTS.md`） |
| `_raw_search` 修复后 | 0.3318 **← 目标** · 0.3579 … （证据：`git show V-2026-10-02:docs/EXPERIMENTS.md`） |

影响 semantic / focus / expanded **三条向量路由**（BM25 不受影响）。
#16 目标 chunk 修复后：semantic **rank 1** · expanded rank 1 · focus rank 4。

**#4 标注口径（诊断结论）**：修 #1–#3 后 kp_hit 由 1.000 降至 0.983，**唯一掉分 query**： （证据：`git show V-2026-10-02:docs/EXPERIMENTS.md`）

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
| kp_hit | 1.000 | **1.000** （证据：`git show V-2026-10-02:docs/EXPERIMENTS.md`） |
| kp_mrr | 0.9514 | **0.9625** ↑ （证据：`git show V-2026-10-02:docs/EXPERIMENTS.md`） |
| cat@1 | 0.9833 | 0.9833 （证据：`git show V-2026-10-02:docs/EXPERIMENTS.md`） |

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

**门禁全过**：`retrieval_gate`（kp_hit **0.8718** / kp_mrr **0.6729–0.6761**，均高于基线； （证据：`git show V-2026-10-02:docs/EXPERIMENTS.md`）
区间的抖动源于已知 Chroma ANN 边界效应）· `probe_gate` · `leakage_gate` · `mode_layer_gate` ·
`topic_relevance_gate` · `topup_eligibility_gate` · `sufficiency_gate` ·
`policy_layer_evidence_proof`（6/6 ok）· `agent_behavior_gate`（8/8 PASS，quality 0.1473） （证据：`git show V-2026-10-02:docs/EXPERIMENTS.md`）

> **跨版本不可混引**：§17（V-2026-10-01）的数字与本节不可混用同一张表。

### 18.6 ★ 冻结前检查发现的**结构性缺口**（待修）

**四层可追溯链检查**（`uv run python scripts/ops/freeze_precheck.py`）：

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
  "script":         "scripts/lib/ablation_retrieval.py",
  "argv":           ["--limit", "60", "--configs", "full,…"]
}
```

> **`code_version` 的 dirty 判定只看 `src/`、`scripts/`、`pyproject.toml`、`.env.example`**
> —— 不看结果归档。否则「刚跑完、归档未提交」会被误判成 `-dirty`，
> 把「代码有未提交改动」这个真正危险的信号淹没在噪声里。

**本版本归档的 `code_version`**：检索类 `d6eed4c` · RAGAS 派生类 `0479d6e`
（两者差异仅在 `scripts/ops/ragas_report.py`，不影响检索链）。

---

## 19. 最终系统决策表（V-2026-10-02）

> **性质**：本节是 **V-2026-10-02 冻结之后的纯文档补充**（标签 `V-2026-10-02` 指向
> `e36c766`，**不含本节**）。内容是对 §2–§18 中已发生问题与决策的汇总，不引入新实验。
> 每行都可在本文件对应小节或 `evals/results/` 归档中反查。

### 19.1 已修（本版本）

| 问题 | 诊断 | 最终处理 | 证据 / 位置 |
|---|---|---|---|
| **q052（inode）纯向量下丢目标** | 向量路由**排序方向反了**：Chroma score 是余弦距离（越小越好），代码按 `-score` 降序 = **返回最不相似的 k 条** | 改升序取前 k | `rag/retrieval/routes.py`；修后目标 semantic **rank 1**（§18.2 #3） |
| **verify 真题被「先注入后裁掉」** | top-up 只按 `kb_depth` 找，**未继承 `eligibility_where`** → 把 `exam_answer` 拉进池，再被 Evidence Policy 裁 → L3 空 | top-up 与主检索共用同一 where | `rag/retrieval/layer_recall.py` · `rag/retrieval/retriever.py`；`topup_eligibility_gate` 4+1 场景 PASS（§15） |
| **practice 出现空证据包** | ① preferred 层不合规时 top-up 空转 ② 包被 eligibility 裁空后无兜底 | 新增 `eligible_semantic_layers()` 回退 + `pack_blocked()` 空包回填（**只填合规项**） | `schema/task_policy.py` · `rag/retrieval/evidence_policy.py`；`pack_nonempty_rate` 全 **1.000**（§12.3/§15.7） （证据：`git show V-2026-10-02:docs/EXPERIMENTS.md`） |
| **「单链表就地逆置」召不回目标 chunk** | 三层叠加：① jieba 把「逆置」切成「表逆置 / 地逆置」 ② 同义词守卫按「**子串**」判定 → 标准词「逆置」永不追加 ③ 排序方向（同上） | 注册 9 个领域词 + 守卫改「**已是分词结果**」+ 排序修正 | `rag/common/rag_utils.py` `_DOMAIN_WORDS` · `rag/common/synonyms.py` · `rag/retrieval/routes.py`（§18.2 #1–#3） |
| **「滑动窗口协议」kp_hit 掉分** | **golden 单标签口径**：同文件同主题（L38 标传输层 / L163 标数据链路层），而 IP/MAC、ARP 早已双标签 | 补第二标签（纯数据修正，**未改 evaluation 逻辑**） | `evals/datasets/golden/sample_408.jsonl` L38 → `["数据链路层","传输层"]`（§18.2 #4） |
| **论文数字无法反查到代码版本** | 归档不自描述（无 `code_version` / golden hash / 脚本名） | 新增 provenance 注入 **13 个写入点**，全部归档按该版本重跑 | `src/evaluation/provenance.py`；`freeze_precheck` 矩阵 **11/11 全 Y**（§18.6） |
| **RAGAS judge 用不了强模型** | DashScope **thinking 模式拒绝 `n>1`**，而 `answer_relevancy` 必需 `n>1` | judge 独立槽位 `RAGAS_JUDGE_MODEL` + **只对 judge** 强制关 thinking | `core/settings.py` · `core/llm.py` · `evaluation/adapters.py`（§5） |
| **RAGAS 可能「白花钱」/ 静默失败** | judge 配额/鉴权失败时**生成已跑完**、费用作废；且全指标 `n=0` 仍退出码 0 | preflight **分别探活**生成/judge + 生成产物**先落盘** + 全无分升级为显式错误 | `evaluation/cli.py` · `evaluation/ragas_eval.py`（§5） |
| **实验路径与 Agent 路径口径不一致** | 实验脚本未传 `eligibility_where` → baseline 虚低、Δ 失真 | 补传 `filter` + `eligible_layers` | `scripts/task_layer_ablation.py` · `scripts/exp/task_mode_layer_policy.py`（§15.5） （证据：`git show V-2026-10-02:docs/EXPERIMENTS.md`） |

### 19.2 未修 / 已决策（如实记录）

| 问题 | 诊断 | 最终处理 | 数字 |
|---|---|---|---|
| **L2 跨学科污染** | `preferred_layers` 提升**所有** advanced；L2 池小（98），错学科靠通用词面挤进包 | **未修**（推迟）——方向是学科感知排序，**非补数据** | **40.0%**（10 条 L2 中 4 条错学科，§16） |
| **rerank 收益符号不稳** | 边界不稳定 | **默认关闭**（`.env` `RERANK_ENABLED=false`），论文如实披露 | +0.012 / 更早 −0.046（§2.1） （证据：`git show V-2026-10-02:docs/EXPERIMENTS.md`） |
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
| **Git 标签** | ① **`V-2026-10-07`**（附注标签对象 `abc115b` → **落点 `0f24891`**，2026-10-07 18:53 +0800）<br>② **`V-2026-10-07B`**（**D9 补的第二个锚点**；标签对象 `bf37b6b` → **落点 `c70ed03`**，2026-10-08 00:22 +0800）—— **Step 9 全部数字所属的代码状态**<br>③ **`V-2026-10-08`**（标签对象 `5471a9a` → **落点 `e65837a`**）—— #28~#31 + D12(B) 修完后的评测层/护栏态<br>④ **`V-2026-10-08B`**（标签对象 `beb833d` → **落点 `79ac38f`**）—— **§6 整轮跑在这个代码态上**<br>⑤ **`V-2026-10-08C`**（标签对象 `009b8d1` → **落点 `a1eea10`**）—— **#33 的修复态**：出题答案键与解析同结论；`PROMPT_SET_VERSION` 由此变成 `12abf293c62a` |
| **落点提交** | ① **`0f24891`**（`docs: §20 效果锚点…`）。其前两跳：`c5d5bca`（gold 数据集入库）→ `63b3b79`（效果层代码 + 11 条口径修复）；再上是 V-2026-10-02 之后的 `648d819`<br>② **`c70ed03`**（`docs(step9): §20.2 补 D9 收尾重跑…`）。它相对 ① 是 **19 个提交**、`src/`+`scripts/` **10 个文件 `+1153/−61`**；标签消息里直接写了落点时的验证状态（护栏 162 全绿 / sanity ERROR 0 / 检索门禁逐位复现）<br>③ **`e65837a`**（`docs(anchor): §20.2 记 V-2026-10-08 打锚点前的检索门禁复跑…`）；它相对 ② 是 **6 个提交**、`src`+`scripts` **10 个文件 +827/−70**，且**没有 gold 改动**（memory 指纹仍 `3c938365da7ce614`）<br>④ **`79ac38f`**（`docs(step6): §21 补「§6 整轮怎么跑」…`）；相对 ③ 是 **5 个提交**、`src`+`scripts` **6 个文件 +717/−1**，同样**无 gold 改动** ⇒ 四个锚点共用同一份效果集指纹<br>⑤ **`a1eea10`**（`fix(generate): #33 答案键与解析必须同结论…`）；相对 ④ 只动 **3 个文件**（`prompts/agents.py` +2 条规则、`schema/questions.py` 两个字段描述、护栏 `㉘a~㉘c`），**同样无 gold 改动** ⇒ 五个锚点仍共用同一份效果集指纹 （证据：`git show 0f24891:docs/EXPERIMENTS.md`） |
> ★ **与标签的代码层差异（2026-10-07 Step 9 之后复测）**：`git diff V-2026-10-07 HEAD -- src` **非空** —— 标签之后 `src/` 又改了 4 个文件（`+137/−17`：`metrics` / `report` / `runner` / `memory_scorer`，即 #21 主指标单一公式、#22 取证通道、⑯/⑰ 的落盘字段）。⇒ **Step 9 的 6 份归档全部跑在标签之后的提交上**，逐份 `code_version` 见 §20.8.5；`PROMPT_SET_VERSION` 仍是 `2f485d2d7ef7`（提示词未变）。⇒ 引用 Step 9 的数字时**不要**说「与 `V-2026-10-07` 同一代码状态」；★ **D9 已落地（2026-10-08 00:22）**：第二个锚点 **`V-2026-10-07B`** 指向 **`c70ed03`**，即「产出 Step 9 全部数字的代码状态」；从该锚点起，引用 Step 9 的数字可以说「与 `V-2026-10-07B` 同一代码状态」（比较仍应写成可重跑的命令：`git diff V-2026-10-07B HEAD -- src scripts` 应为空）。（★ 这一行此前写的是「空输出 ⇒ 逐字节相同」，那是当时的事实、现已被后续提交作废 —— 教训：这类断言只能写成**可重跑的比较**，不能写成结论句。） （证据：`git show 3a386b873:docs/EXPERIMENTS.md`）
> ★★ **锚点 ② 之后 `src/`+`scripts/` 又变了 ⇒ 已用锚点 ③ 收口（2026-10-08）**：② 之后那批改动是「对自己代码做对抗性 review」后的修复（#28~#31 + D12(B)：`runner.py` 写入证据判据的位置/归因/下游、`retrieval_probe.py` 的 KP 兜底、`agent_behavior_smoke.py` 的 `_UNSET` 与 `episodes_read_failed`、护栏 `㉓/㉔/㉕` 三组与护栏自身卫生），共 **6 个提交 / 10 个文件 +827/−70**、**无 gold 改动**。⇒ 现在的可重跑比较是两条，别混用：`git diff V-2026-10-07B HEAD -- src scripts` **非空**（引用 Step 9 的 d8b 数字仍用 ②），`git diff V-2026-10-08 HEAD -- src scripts` **应为空**（引用本批修复后的评测层/护栏状态用 ③）。护栏计数 162 → **184**（链条写进 §20.7）。 （证据：`git show 487c2f130:docs/EXPERIMENTS.md`）

> ★★ **锚点 ⑤（2026-10-08，§6 跑完之后打的）**：§22 唯一不达的门槛行是 Generate（0.733 < 0.75），成因登记为 **#33**（答案键与解析各写各的）⇒ 修在**产品侧**（`a1eea10`）。**动了 prompt** ⇒ 按纪律要新版本 + 全量重跑，而 §7.3 Freeze 本来就是「重跑全实验」，所以 ⑤ 的验证状态写的是「**护栏 204 全绿 + 篡改探测：逐项单独弄坏恰好对应那一项变红**」，★ **效果侧数字尚未在本 hash 下重测**（下一步：15 条 generate-only 探针 ≈100 次调用，再并进 Freeze 全量跑）。⇒ 引用 ④ 及以前的效果归档时：`git diff V-2026-10-08B HEAD -- src scripts` 现在**非空**（⑤ 在 ④ 之后），§6 那一跑仍归 **④**，别说成「与 ⑤ 同一代码态」。 （证据：`git show 6d5352360:docs/EXPERIMENTS.md`）

> ★ **自指限制（不是漏更）**：上面几行由标签**之后**的 docs 提交回填 —— 一个提交写不下自己的 SHA，所以 `git show V-2026-10-07:docs/EXPERIMENTS.md` / `... V-2026-10-07B:...` 里看到的都是回填前的文字。**锚点的权威解析不依赖本文字**：`git rev-parse "V-2026-10-07^{}"` → `0f24891599c194179755753d06e0d53f106d116e`；`git rev-parse "V-2026-10-07B^{}"` → `c70ed03a59f7f8d15ecb97a47673973664ef2434`；`git rev-parse "V-2026-10-08^{}"` → `e65837a5…`；`git rev-parse "V-2026-10-08B^{}"` → `79ac38f…`（★ ③④ 的回填都发生在各自标签**之后**的提交里 —— 自指限制对每个锚点都成立，别当成漏更）。`git rev-parse "V-2026-10-08C^{}"` → `a1eea106afd762c662ae8a6b1aabfceb2055d134`。（§18.0 的 `V-2026-10-02` 是同一做法：落点 `e36c766` 记在其后的 `e2ec6a6`。）
| **prompt 版本** | **现值 `PROMPT_SET_VERSION = 12abf293c62a`**（⑤ `a1eea10`，#33 修出题规则之后）。**当时值 `2f485d2d7ef7`**（E-3 注入词表 + **#8 过滤课程根节点**后；词表 **158 个** = 162 − 4，批改 system **1293 字符**）。★ E-5 的 `0.875` 是在**旧 hash `f09c75642029`**（词表 162 个）下测得 ⇒ 严格说 E-5 归「E-3 完成后、#8 前」的中间态，新 hash 下的复测（12 次调用）**建议并入 Step 9**。★ `PROMPT_SET_VERSION` 是**全部提示词**的 hash、改一个字都变 ⇒ 12abf293c62a 只反映**出题**那两条规则变了，**批改 system 逐字节未动（仍 1293 字符 / 词表 158 个）**：`git show a1eea10 -- src/prompts/agents.py` 的 diff 只落在 `_QUESTION_AGENT_RULES`。⇒ E-5 的 `0.875` 与 §20.8.6 的配对数字**仍属 `2f485d2d7ef7`**，不受 ⑤ 影响 （证据：`git show 0f24891:docs/EXPERIMENTS.md`） |
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

> ★ **指纹口径 = 工作副本字节的 sha256**（与 `scripts/ops/freeze_precheck.py:65` 一致），**不是 git blob 哈希**。因为 `.gitattributes` 声明 `*.jsonl text` ⇒ 入库时 CRLF 会归一成 LF，实测同一份黄金集：工作副本（CRLF）`be98912a4c91fb88…` / 归一后（LF）`979b7f96537cb147…`。⇒ **在纯 LF 环境（如 Linux/CI）checkout 后重算会得到另一个值**，那不是数据被改；复算要么在本机工作副本上跑，要么比较前先做行尾归一。 （证据：`git show 0f24891:docs/EXPERIMENTS.md`）
| **归档 `code_version` 现状** | 全部为 **`648d819-dirty`**（见 §20.5 第 3 条——这是本节存在的理由） |

### 20.1 为什么必须开新版本（三条触发，均已核到代码）

1. **动了检索链**：`rag/retrieval/llm_calls.py` 的重试 + 兜底被 **`query_classifier.py:311`** 与
   **`query_decomposer.py:175`** 共用 ⇒ 按 §18 / `EFFECT_PLAN` 的「动检索链 → 新版本」规则触发。
2. **批改 prompt 变更**：`GRADE_PROMPT` 注入 162 个 canonical 考点名，system 从 389 → **1317 字符**。
3. **Memory 写链三层改**：`GradingResult.knowledge_points` → `record_grade` → `compute_weak_topics`。

### 20.2 检索门禁在本锚点的实测（四路由 + 隔离实验）

> ★ 代际：本表是 **V-2026-10-07 / 08C 锚点（10-07 / 10-08）** 上的门禁实测，早于 10-10 的语料换代与
> 仪器对齐；同四路由的换代后读数见 §20.7.3（如 `real+on` 权威路由现 `kp_mrr 0.8223`，本表为 0.8048）。
> 两者不可互证、也不可当作退化，理由见 §18 抬头。

| 路由 | 判定 | 关键值（当前 / 基线） |
|---|---|---|
| `fake + off`（默认） | ✅ 通过 | `kp_mrr 0.6761 / 0.6698` · `kp_hit@k 0.8718 / 0.8654` （证据：`git show V-2026-10-08C:docs/EXPERIMENTS.md`） |
| `fake + disabled`（生产关闭态） | ✅ 通过 | `kp_mrr 0.6614 / 0.6277` （证据：`git show V-2026-10-08C:docs/EXPERIMENTS.md`） |
| **`real + on`（权威 · 唯一能答语义质量）** | ✅ 通过 | `kp_mrr 0.8048 / 0.8051` · `kp_hit@k 0.9103 / 0.9167`（均在容差内） （证据：`git show V-2026-10-08C:docs/EXPERIMENTS.md`） |
| `fake + on`（假重排） | ❌ 退化 | `kp_mrr 0.7566 / 0.7828`（−0.0262 > 容差 0.02） （证据：`git show V-2026-10-08C:docs/EXPERIMENTS.md`） |

**隔离实验**（决定「该红是否本轮造成」）：在 `HEAD` 的独立 worktree 上跑同一路由、完整 156 条 ⇒
**同样是 0.7566，逐位相同** ⇒ 该退化**由已提交的代码带入**，与 E-3 / E-4 / 类型收窄无关。 （证据：`git show V-2026-10-08C:docs/EXPERIMENTS.md`）
**基线不重录**（本轮无任何指标变化需要吸收），该红按 §20.5 披露。

★ **门禁的能力边界（必须写清，否则这句话会被误用）**：门禁把 LLM 钉成 fake
（`settings.USE_FAKE_MODEL=True`，模型恒返回测试串）⇒ 日志里每条 query 都有
`结构化输出类型不符 [classify]，重试 1 次后仍失败`，**重试确实在检索链内部被触发**，
但因 fake 永远失败、重试只多打一次 ⇒ **结果不变**。
⇒ 「检索未受影响」只在**确定性层面**成立；**重试对真实 LLM 路径的影响既未证实也未证伪**，
门禁在设计上测不到它（真实 LLM 下重试可能把分类失败变成功 ⇒ `query_type` 变 ⇒ 路由变）。

★ **D9 收尾时重跑过权威路由一次（`real + on`，156 条，`code_version` = 本轮 HEAD）**：
`category_hit@1 0.9423/0.9423` · `category_hit@k 0.9679/0.9615` · `kp_hit@k 0.9103/0.9167` · （证据：`git show V-2026-10-08C:docs/EXPERIMENTS.md`）
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
⇒ **与 §20.2 上表逐位相同**（D12(B) 只改评测读数 `retrieval_probe`，本来就不在这条链上，此处得到确认）。 （证据：`git show V-2026-10-08C:docs/EXPERIMENTS.md`）
★ 唯一有差的是 `mean_evidence_count`：**3.9295 → 3.9231**（基线仍 3.8846，两次跑的是同一份代码）；打锚点 ④ 前又跑了一次同一份代码 ⇒ **3.9295** —— 三次落在 **[3.9231, 3.9295]** 之间，确认这是**运行间抖动**而不是代码效应（其余指标三次都逐位相同）。 （证据：`git show V-2026-10-08C:docs/EXPERIMENTS.md`）
⇒ 这说明该指标有**运行间抖动**（其余全部逐位相同 ⇒ 不是抖动在扩散）。可疑来源是那条 （证据：`git show V-2026-10-08C:docs/EXPERIMENTS.md`）
「阈值过滤后为空 ⇒ 保底返回 top-1」的分支（fake LLM 分类失败时 `query_type`/路由会变 ⇒ 证据条数会变）。
判定不受影响（阈值判定是「不低于基线」，本次仍高于）。★ 但引用 `mean_evidence_count` 时**必须带上这个抖动**，
不要把它写成第三位小数稳定的量。

### 20.3 效果侧实测（本锚点新增，均可从归档反查）

**E-5 · 批改是否跟随词表**（`scripts/mem/memory_e5_probe.py`，配对 12 次批改调用，零 token 风险）
：两臂 system **除词表块外逐字节相同**，同模型同温度（`dashscope:qwen3.7-flash` / `T=0.0`）。

| 臂 | 词级跟随率 | `all_canonical` 题级 | 目标考点入桶 |
|---|---|---|---|
| A 注入 162 词表 | **0.875**（7/8） | 5/6 | **6/6** （证据：`git show 0f2489159:docs/EXPERIMENTS.md`） |
| B 8 示例（= 修复前口径） | 0.273（3/11） | 1/6 | 3/6 （证据：`git show 0f2489159:docs/EXPERIMENTS.md`） |

**缺陷 A 的批改失败率——口径修正**（按 A 段**预期**批改次数为分母；
失败 = 分数不可解析 **+** 完全没有落分记录）：

| 运行 | 预期 | 落分记录 | 不可解析 | 无记录 | 失败率 |
|---|---|---|---|---|---|
| Step 5 修复前 ON | 9 | 6 | 2 | 3 | **5/9 = 0.556** （证据：`git show 0f2489159:docs/EXPERIMENTS.md`） |
| Step 5 修复前 OFF | 9 | 7 | 2 | 2 | 4/9 = 0.444 （证据：`git show 0f2489159:docs/EXPERIMENTS.md`） |
| Step 5 修复后 ON | 9 | 9 | 0 | 0 | **0/9 = 0.000** （证据：`evals/results/task_eval/phase1_e5_step9_20261007.jsonl`） |

⇒ 此前文档写的 **62.5%（5/8）** 分子对、分母错（8 无法从归档构造）；
只数「`score=None`」得到的 30.8% 则**漏掉了「完全无落分记录」这种最硬形态**。
**论文改用 `5/9 → 0/9` 这一对**，两端都可从 `phase1_memory_step5_*` 重算。

**Grade · `verdict_agreement`（#7 换来的合法指标，零 token，从冻结归档重算）**

| 归档 | verdict_agreement | 分数不可解析 | 旧 `tolerance@±10` |
|---|---|---|---|
| `phase0_baseline_final` | **15/15 = 1.000** | 0 | 不可判（两极 gold；`raw_rate=1.0`） （证据：`git show 0f2489159:docs/EXPERIMENTS.md`） |
| `phase1_baseline_v2` | **13/13 = 1.000** | **2**（grd-004 / grd-011） | 不可判（同上） （证据：`git show 0f2489159:docs/EXPERIMENTS.md`） |

⇒ 论文里 Grade 的写法应是：**「选择题对错判别 15/15 全对」**，而不是**「0–100 判分与人工一致率 100%」** （证据：`git show 0f2489159:docs/EXPERIMENTS.md`）
—— 后者在本项目**没有对应的数据前提**。★ 且**两个数必须同框**：只报 13/13 不报那 2 条批改失败，
就是拿"分母剔除"把失败藏起来（这正是 §20.5 #4/#6 那一类错误的第三次现身，故由 ③r' 强制披露）。

### 20.4 ★ 结果归属矩阵（引用前先看这张表）

| 归档 | 产出时间 | 对应代码状态 | 能否引到本锚点 |
|---|---|---|---|
| `phase0_baseline_final.jsonl`（66 条，0B 冻结） | 10-06 07:01Z | **前态**（不含 E-3/E-4） | 只可作**诊断基线**，非本锚点产物 |
| `phase1_baseline_v2.jsonl` · `phase1_verify_probe*` | 10-06 09:12Z | **前态** | 同上；其「检索侧逐位一致」成立于该次比较（早于 `llm_calls` 改动） （证据：`git show 0f2489159:docs/EXPERIMENTS.md`） |
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
| 2 | **Generate 主指标口径分叉**：`EFFECT_PLAN §3.1` 冻结为逐题 `five_of_five` AND，代码 `report.py:134-145`（`gen_items`）实为**跨题跨项池化** | 同一归档三数：**池化 0.9423 / 逐题适用项全过 0.80 / 严格 5/5 = 0.00**。★ 解剖后发现真正的问题不是公式，而是**五项里只有两项有区分力**（见 §20.5.1） | ✅ **已修（D1，2026-10-07 采纳）**：`metrics.every_item_passes()` 做**逐题 AND**（N/A 项不进该题分母），`report.py` 主指标改挂逐题数、**项级池化降级为诊断**（不删，留对照）；旧名「交付完整率（主指标）」从报告消失。★ 归档 15 条**复现三个数不变**：主指标 **0.80（12/15 题）** / 诊断池化 **0.9423（49/52 项）** / 严格 5/5 **0.00**。护栏 **⑭a~⑭f**（⑭c 锁「同一样本两口径必须分叉且池化偏高」= 证明换口径有信息量；⑭d 锁两个已发表数字不许漂；⑭f 锁「整题不可测的题不许假装进分母」） （证据：`git show 0f2489159:docs/EXPERIMENTS.md`） |
| 3 | 归档 `code_version` 全为 `648d819-dirty`，且 record **不含 `prompt_set_version`** | `provenance.code_version()` 对 `src/ scripts/` 的未提交改动只加 `-dirty` ⇒ 多次运行同值 | ✅ **已修（D4）**：`CaseRecord` 新增 `prompt_set_version` 字段，`_attach_provenance` 从 `prompts` 取**活值**写入 ⇒ 新归档自描述跑在哪个提示词上，不再依赖本节人工对账。★ **老归档没有该键 ⇒ 读侧一律按空串（未知）处理，绝不回填当前 hash**（回填等于伪造 provenance）。护栏 **⑮d/⑮d' + ⑮e**（⑮e 是反向：把 `PROMPT_SET_VERSION` 临时改成 SENTINEL，新 record 必须跟着变 —— 若当初写成硬编码字面量，⑮d 照样绿、这条必然红）。★ 另：三次提交之后 `provenance.code_version()` 实测返回**干净的 `0f24891`**（`CODE_PATHS = (src, scripts, pyproject.toml, .env.example)` ⇒ 文档改动与未跟踪的 `evals/results/task_eval/` 都**不**算脏）⇒ 本条对**新跑的归档**已消除；既有 5 份仍是 `648d819-dirty`，**不回写**（它们是历史证据），对那批仍靠本节人工对账 |
| 4 | Memory 的 `used` 用「回复含 gold 值**子串**」判定 ⇒ **双向错** | `phase1_memory_step5_store_on`：`mem-006` 卡为空、未召回却 `used=True`（假阳性）；而 `mem-004`/`mem-005` 规规矩矩没凭空用记忆，却因 `used=False` 被 AND 判 **失败**（假阴性）⇒ 净效果是「**负样本只有碰巧提到才算通过**」 | ✅ **已修（本轮）**：`used` 加事实前提 `recalled_actual`；`correct_use` 按极性分定义（正=召回∧used∧correct；负=未召回∧未误用）。**ON 组数字变化：`used` 2→1、`correct_use` 2→4（0.333→0.667）**。护栏新增 ③d~③h 锁住四个方向 （证据：`git show 0f2489159:docs/EXPERIMENTS.md`） |
| 5 | Step 5 配对 OFF 组 `valid=2` **且两条皆负样本** | 重算：正样本 mem-001 在 OFF 侧 `case_invalid` ⇒ 两臂样本集不相交。★ **本条的原始证据已被 #24 二次削弱**：那批 OFF 跑在「OFF 臂其实没关掉 Store」的代码上，所以它连「不相交」都说明不了对照本身有效 | ✅ **已闭合（D8 + #24，§20.8.6）**：用修好的 OFF 重跑后，两臂在正样本上有**交集** `mem-002`（ON 与 OFF 都 `valid=True`、都满足「两次低分批改且同考点」）⇒ 这是本文第一条**可信配对**：ON 1 卡 + `recalled/used/correct_use` 全 True，OFF 0 卡 + `recalled=False`。剩余限制照实写：可测正样本 **n=1**（ON 侧另两条因 A 段第 2 轮未调用批改工具而 `case_invalid`，与 Store 无关） |
| 6 | `case_invalid` 计入 `failure_rate` 的分子与分母 | `report.py:74-75`：分母为 `len(records)`，`case_invalid` 在枚举内 | ✅ **已修（本轮）**：分母改为「有效 n」，并新增 `invalid_n` 字段 + 报告表「有效 n」列。护栏 ③i 锁「1/2 而非 1/3」 |
| 7 | Grade 的 `gold.human_score` **只有 0 与 100 两值** | 重算分布 `{100:8, 0:7}` ⇒ `score_tolerance@±10` 退化为「模型是否也跟着给 0/100」 | ✅ **已修（换指标，非补标）**。★ **我先前写的处置「按 rubric 补部分分」是错的，已撤回**：L3 语料 **674/674 全是 2 分 `choice`**、case 的学生答案 **15/15 仅 1 个字母** ⇒ **没有部分分可标**，硬要补就只能造题（= 造假 + 动语料）。正确解法是**换成二值 gold 上本来就合法的问题**：新增 `metrics.verdict_agreement()`（阈值直接引用 `schema/grading.py` 的 `score<60 视为错误`）⇒ 实测 **0B 15/15 = 1.000**、**Phase 1 13/13 = 1.000（另 2 条分数不可解析，报告已强制披露）**。两极 gold 下 `tolerance` 置 N/A 但**保留 `raw_rate=1.0`**；护栏 **③o~③r'**（③o 锁住"数值差 30 但结论一致 ⇒ verdict 过 / tolerance 败"这条换指标理由；③r 锁"tolerance 不可判时 verdict 仍可判"，防止这次修复变成删指标） （证据：`git show 0f2489159:docs/EXPERIMENTS.md`） |
| 8 | 批改词表含 **4 个学科根节点**（数据结构/计算机组成原理/操作系统/计算机网络） | 与同一 prompt 的规则尾「不是学科名（如「数据结构」太粗）」自相矛盾；且根节点是 canonical ⇒ 模型选它能**轻易凑满 `MIN_HITS=2`**，聚成「整门课 = 一个薄弱点」的桶，**比自造词更难发现** | ✅ **已修（本轮，#8）**：新增 `kp_vocab.prompt_names_by_subject()`，按数据字段 **`node_kind == "subject"`** 过滤（★ 不写硬编码名单 —— 硬编码正是缺陷 E 的成因）；`canonical_names()` **仍保 162 全量**（归一化侧必须认得根节点，否则 `normalize_topic('数据结构')` 反被判非 canonical，是另一种错）；`domain` 章名（`图`/`排序`/`内存管理`…）**保留**，它们是合法薄弱点标签。词表 **162 → 158**、护栏 **⑫k 双向**（剔根节点 + 防过滤过头）。★ 连带后果：**`PROMPT_SET_VERSION` 变更**（`f09c75642029` → `2f485d2d7ef7`）⇒ E-5 的 0.875 严格归中间态，需在新 hash 下复测（并入 Step 9） （证据：`git show 0f2489159:docs/EXPERIMENTS.md`） |
| 9 | **0B 的 Memory 四率与现口径不可比** | 实测：0B 记录的 `gold` 键里**没有 `expected_memory`**（只有 `gold_points`/`human_score` 等），用当前 scorer 判 ⇒ 六项**全 N/A**；可归档里 `mem-002` 等却记着 `used=True`/`cu=True`，且 `judge_memory_used=None` | ⇒ 0B 那组 Memory 数字**不是这套机械 scorer 产出的**（与 §5.1「0B 只测到 checkpointer 会话内记忆」一致）。论文若要用 0B 的 Memory μ=2.833，**必须标注其口径与 Phase 1.5 之后不同** （证据：`git show 0f2489159:docs/EXPERIMENTS.md`） |
| 10 | `category_hit` 对学科码 **`cn` 恒判未命中** ⇒ **系统性压低 grade / verify 的学科命中指标** | `metrics.category_hit` 旧写法 `.get(subject, subject)` 拿学科码去比类目名：`cn` ≠ `computer_network` ⇒ 恒 False。实测归档分布：`grade` **4 条 `cn` 全 False**、`verify` **4 条 `cn` 全 False**；而 `qa` / `generate` 的 case 用的是 `network` ⇒ 全 True —— **同一函数在两个任务上表现不一致**，这是它长期没暴露的原因。另核实 `retrieval_gate` 自身用 `.get(subject)`（无默认回退），**不受此影响** | ✅ **已修（本轮）**：加 `_SUBJECT_ALIASES = {"cn": "network"}` 对齐，且**未登记学科记 None（N/A，不进分母）**而非 False。护栏新增 **③j**（对齐命中 + 未登记记 N/A），当时 Gate **87 项全绿**（现 116）。★ 归档里那 8 条 False **不可离线重算**（2026-10-07 复核确认：记录只有 `category_hit` 这个**结果布尔**，`tool_calls` 里**没存**每条命中文档的类目 ⇒ 无法反推，正确值需 **Step 9 一并重跑**；旧归档值不覆写 ⇒ ✅ **已补测（§20.8.4）**：同一批 top-k 上新旧公式对照 0.600 → 0.800、`cn` 0/4 → 3/4 ⇒ 确认这 8 条是系统性假阴性，剩余各 1 条为真实未命中）。★ 复核过程本身也纠正了一次误报：直接按 `task` 数 False 会得到 grade 13 / verify 33 条，**看着像**『比登记的 8 条多』—— 其实记录里**没有 `subject` 字段**，必须与 case 表按 `case_id` 关联；关联后 `cn` 恰为 grade 4 + verify 4（且 `cn` 是**唯一 16/16 全 False** 的学科，其余学科有 True 有 False，属真实未命中）⇒ 登记值成立。护栏补 **③j+**：扫遍 `evals/datasets/` 实际出现过的学科码，逐个要求「在映射表里查得到」且「用映射后的真实类目自测为 True」⇒ **防下一个 `cn`**（反向验证：抽掉 `cn` 别名，③j 与③j+ 同时变红） （证据：`git show 0f2489159:docs/EXPERIMENTS.md`） |
| 11 | Grade 分数解析取**首个数字** ⇒ 把「满分/总分 N」当成得分 | 旧正则在 `"总分 100 分，你得了 62 分"` 上返回 **100**、在 `"得分（满分 100）：62"` 上返回 **100** ⇒ 批改明明正常，指标却记成分数差 38 分；更糟的是它**方向不定**（说明性数字在前就偏高、在后才正常） | ✅ **已修（A1）**：先用 `_MASK_FULLMARK_RE` 把「满分/总分 X」**遮蔽**掉，再按「显式得分 → 你得了 N 分 → a/b 折算 → 兜底」四级正则解析；解析不到返回 **None（N/A）** 而不是 0 分。护栏 **③s**（5 条形态全对）+ **③t**（4 条无分数形态必须 None） |
| 12 | API 批改端点 `record_grade` **没透传 `knowledge_points`** | `service.py` 的调用缺该参数 ⇒ 本路径写入的 episode KP **恒空** ⇒ `compute_weak_topics` 退回**题干前 80 字**（legacy fallback），薄弱点变成「某道题的开头」 | ✅ **已修（A2）**：`knowledge_points=list(result.knowledge_points or [])`。护栏 **③u**（AST 级：调用参数表里必须有它，防止「删了但注释还在」式漂移） |
| 13 | 结构化输出的 **salvage 兜底**只在「确实拿到过原文」时生效 | `scripts/mem/memory_e2e_fallback_probe.py` 用注入式假 LLM 驱动**真实** `call_structured`：① 合法对象 OK；② `ValidationError` 带脏原文（多行 KV + 参数标记）⇒ **救回**（score 40，KP `['平衡二叉树','平衡因子']`）；③ 模型**不产 tool call**（返回 `None`）⇒ 无原文可救，结果 `None`（重试后仍失败） | ⚠ **已知盲区，如实披露**（不是修复）：③ 形态下整条批改失败。是否为它再加一层兜底，**由 Step 9 的实测频率决定** —— 现在加就是凭想象加防护。`--reverse`（关掉 salvage）必须变红，实测 exit 1 |
| 14 | `--rejudge` 把 runner 写的归因**洗掉** ⇒ 无效样本看起来像通过 | `mechanical_reasons_from_record` 照抄 `runner.mechanical_failures`，而 `case_invalid`（`runner.py:505`）/ `memory_miss`（`runner.py:382`）是 runner **另两处分头**写的。实测归档：`phase1_memory_step5_store_off` 有 **4 条** `failure_reason` 恰为 `["case_invalid"]` ⇒ 重判后变 `[]`、`primary_failure` 翻成 `none`。★ 注：失败率**分母不受影响**（`report._is_invalid` 还看着 `validity_valid`），坏的是**故障分布** —— 「无效」被画成「通过」 | ✅ **已修（B1）**：`_KEEP_ON_REJUDGE = {case_invalid, memory_miss}` 原样保留（二者都**不是** judge 意见），`case_invalid` 另按 `validity_valid` 兜底重建（上一轮已被误清时仍能恢复）。护栏 **⑬a~⑬d**（⑬d 是反向：judge-only 的 `generation_wrong` 仍必须被清掉，防保留面过宽） |
| 15 | `cli.py` 三处 jsonl 写出**不留尾换行**，与 `append_record` 的 `"a"` 追加相撞 | 两条记录**粘成一条坏行** ⇒ 上一条与这一条**同时**解析失败（实测 3 条只剩 `['a-1']` 可读）。连带 `load_done_ids` 读不到被粘住的 case_id ⇒ 续跑**重做**它，已烧的 token 无从追溯。★ 全盘扫现存 **12 份**归档：末字节**都是** `\n`（都由 `dump_records`/`append_record` 产生）⇒ **尚未真的烧到过数据，属潜伏** | ✅ **已修（B2）**：行格式收口成 `runner.write_jsonl()`（`dump_records` 也改为调用它 ⇒ 只剩一份实现），cli 三处改用它；`append_record` 追加前检测末字节并按需补分隔（自愈，覆盖外部手改/旧产物）。护栏 **⑬e~⑬g**（⑬g 专测「无尾换行的旧文件 + 连追两条仍 4 条不丢」） |
| 16 | `_resolve_config`：显式 config **整块替换**、不与运行时上下文做键级合并 | 半条 review 结论**被推翻**：回落读的是 **contextvar**，asyncio 每个 Task 持自己的 context 副本 ⇒ 并发不串号（实测 4 个任务注入 U0~U3、内部 `sleep` 交错，两次阅读仍各自取到自己）。半条成立但**无调用方**：仓内给 config 的地方都**同时**给两把键（`service.py` 的 `configurable`、gate ⑩a） | 🟡 **不改行为**（无流量的假设性加固不做），改为**把契约钉住**：docstring 写明「只传其一不会替你补」+ 护栏 **⑩e**（并发隔离）与 **⑩f**（部分显式 config ⇒ `user_id` 为 None）。将来若真要改成合并，必须让 ⑩f 变红后由人裁决 |
| 17 | `min_grade_calls: 0` 单独存在是**永真** ⇒ mem-005 负样本对照的前提从未被校验 | `len(calls) < 0` 不可能成立，而 `is_valid()` 只看「字段非 None」⇒ **gold_sanity 全绿、其实没校验**。mem-005 的 note 写的正是「全新用户无写入⇒卡必空」，即意图是「**恰好 0 次**」。★ 同时**推翻**另一条 review 结论：「`forbidden_values` 未校验是否 canonical」是**错的规则** —— 该字段喂给 `memory_scorer._hits(reply, ...)`，是**回复文本里的自由词**（`['栈','队列']`），不是 KP 名；gold_sanity 已在查「未标注」与「与期望值重叠（自相矛盾）」 | ✅ **已修（B4）**：`SetupConditions` 新增 `max_grade_calls`，mem-005 改为 `min:0 + max:0` ⇒ 对照真被验收；gold_sanity 加「空标」lint（`min=0` 且无 max/bands ⇒ ERROR 并给出改写建议）。护栏 **⑬h~⑬l**，其中 **⑬l** 锁「两份归档 12 条 validity **逐条不变**」⇒ `grade_scores` 实测本就是 `[]`，**不改动任何已发表数字** （证据：`git show 0f2489159:docs/EXPERIMENTS.md`） |
| 18 | **整个「效果层」都不在版本控制里**（比原登记的「gold 没入库」大得多，2026-10-07 实测扩大） | `git ls-files` 全为 **0** 且**均未被 ignore**：`src/evaluation/task_eval/`（**12 个 .py**：cases / metrics / memory_scorer / gold_sanity / judge / report / runner / cli / retrieval_probe / assets / `__init__` / `__main__`）、`src/core/kp_vocab.py`（缺陷 E 的**单一事实源**）、`scripts/` 下 **12 个**护栏与探针（含 `memory_step4fix_gate.py` 本身、E-5 探针、e2e 兜底探针）、`evals/datasets/demo / probes / probes_phase1 三个目录/` + `exam_answer_corrections.json`。✅ **已解决（2026-10-07 提交）**：`src/evaluation/task_eval/`（12 个 .py）+ `src/core/kp_vocab.py` + `scripts/` 的 12 个护栏/探针已入库；gold 数据集单独一次 `data(evals)` 提交。`evals/results/task_eval/`（3.7MB，其中 1.9MB 是单个 log）**数据类维持不入库**，可复现性由本节的文件指纹 + 已入库的生成/护栏脚本承担；★ **文档类已按 D11 入库**（`*.md` 16 份 ≈ 200KB：交接件 HANDOVER、各步报告、review 件与 findings；`*.jsonl` / `*.log` / `*.report.json` 仍不入库 —— 二进制归档进版本控制只会让仓库变大且无法 diff，而结论都在 .md 里）。另：`.claude/` 未跟踪（**该 ignore、不该入库**）；`.workbuddy-ai/` 未跟踪但**将被删除** ⇒ 不写忽略规则 | ✅ 见上一格 |
| 19 | **judge 校准表的 PASS 只有 2/30 的信息量** —— 门槛过了，但它测不出「judge 会不会打分」 | `evals/datasets/demo/calibration_30.jsonl` 的 `human_score` 分布 = `{5: 28, 0: 1, 2: 1}`（众数占 **93.3%**，不同取值仅 3 个）。基线复算：`exact 0.9333 / within_1 1.0 / mae 0.0667 / spearman 0.7321` ⇒ **PASS**（阈值 0.60/0.90/0.50/0.70，`spearman` 仅高出 0.032）。★ 三条**破坏性检验**（零 LLM，只改内存里的副本，未回写文件）：① 把第 8 行（human=0）**单独**改成 5 ⇒ `spearman 0.4902` ⇒ **FAIL**；② 把第 17 行（human=2）改成 5 ⇒ `spearman 0.5265` ⇒ **FAIL**；③ 反向：把这 2 行的 **`llm_score` 改成 0**（即 judge 在唯一可判别的地方完全打错）⇒ 仍然 **PASS**（`spearman 0.7315`）—— 因为秩相关只看排序，不看量级。⇒ 结论：**整个 PASS 压在 6.7% 的样本上，且对「量级完全错」不敏感**（与 #7 同类的分布退化，但成因不同：#7 是 gold 造不出中间档，这里 28 个 5 是**真实人工判断**，说明系统输出普遍好，**不能当成数据缺陷去改**） | 🔵 **只披露，不擅自改**：不改阈值（`CALIBRATION_THRESHOLDS` 是「预先约定标准」的落点）、不改人工分（改它=伪造标注）。论文里应把校准表述为「30 条中 28 条人机完全一致；其余 2 条 judge 排序正确」，**不要**引用 `spearman=0.7321` 当「judge 与人工秩相关良好」的证据。是否给报告加一行「非众数占比」露出 = **待裁决 D6** |
| 20 | **Phase 1.5 的 §4「L3 闸门」从未执行，且按当前语料无法执行**（此前**未登记**，两份台账里一条记录都没有） | §4 冻结的判定规则问的是「真题缺失是不是低质量回答的**主要因果原因**」，并指定测据：`question_id_recall@k` · `answer_availability` · `final_quality` + `primary_failure` 分布。实测：① gold 侧**有**标注 （`verify_cases` demo 15/15、probes 10/10、probes_phase1 10/10 都填了 `expected_question_ids`）；② **语料侧没有** `question_id` —— 扫 `questions` 集合的 metadata（50 个键）无任何 `question*`/`qid*` 字段；③ 归档里 `question_id_recall` 字段**出现 0 次**，只有代理指标 `exam_hit`（194 条记录：True 69 / False 125）。⇒ `question_id_recall@k` **不是「没跑」，是「算不出来」**：检索结果里没有可与 gold `expected_question_ids` 对齐的字段。★ 这也解释了 P3 为什么保留 `question_id_recall` / `question_id_hit` / `exam_rank` 三个零调用函数 —— 它们就是为 §4 预留的，**接口在、数据源不在** | 🔵 **只披露，不擅自动**：补齐要 ①ingest 时把 `question_id` 写进 metadata ②**全量重建索引** ③重建即改变检索侧指纹 ⇒ 触发新版本锚点 + 四路由门禁重跑（`EFFECT_PLAN §11` 的「时间紧」退路正是 「L2/L3 全走披露、不修」）。✅ **已裁决（D7，2026-10-07）：按 §11 走披露，不补 `question_id`、不重建索引。** 论文口径固定为：「§4 的判定**未做出**（既不是『是』也不是『否』），原因是判据所需的 `question_id_recall@k` 在当前语料下不可计算」，并附上述三条证据；**禁止**用代理指标 `exam_hit@k` 冒充 `question_id_recall` 去回答 §4 的因果问题 （`exam_hit` 只说『top-5 里有没有真题块』，不说『是不是当年那道题』） |
| 21 | **我自己 #4 的修复从未生效**：同一条主指标存在**两套实现**，落盘用的是旧的那套 | `memory_scorer.MemoryJudgement.correct_use` 在 #4 改成「按样本极性分定义」，但 `runner.CaseRecord` 上**另有一个同名 property** 仍是旧三元 AND（`retrieved ∧ used ∧ correct`），而 `to_dict()` 用的正是那个 property ⇒ 极性版从未写进归档、`report.py` 读的也是旧值。★ 实测：报告对 `phase1_memory_step5_store_on` 印 `correct_use = 2/6 = 0.333`，而 #4 之后应为 **4/6 = 0.667**；两份归档里 `mem-004`/`mem-005` 两条负样本全被旧公式记 False。而 ③d~③h 当时全绿 —— 因为它们测的是 scorer 的**函数**，没测「函数结果如何被写出」（正是「只测 helper、不测接线」那一类） | ✅ **已修（本轮）**：公式收敛到 `metrics.memory_correct_use()` 一处；`memory_correct_use_from_record()` 从**原始字段**推导 ⇒ 旧归档也能按现口径重渲而**不改写归档**；`CaseRecord.memory_correct_use` 由 property 改为字段、由 scorer 写入。护栏 **⑱a~⑱e**（⑱a 用报告路径复现 4/6、⑱b 逐条断言两套账一致、⑱c 反向「同一负样本旧 False / 新 True」、⑱d 走真实 `_apply_memory_judgement` 验接线、⑱e 正样本未召回必须 False，防「修复」退化成负样本一律放行）。★ **连带更正**：#4 里写的「ON 组 correct_use 2→4（0.333→0.667）」当时只有手工重算成立，**报告路径并未产出该数**；现在两者一致 （证据：`git show 9fa42ef4b:docs/EXPERIMENTS.md`） |
| 22 | **正样本可能天然测不到召回**：`MEMORY_WEAK_MIN_HITS=2` 按 **KP 精确名**计 hit，而 A 段两道题落在**不同考点** ⇒ 画像恒空 ⇒ 「0 张卡」不是召回失败而是**样本设计缺陷** | Step 9 实跑：Store ON 的 `mem-002` 两次批改都是 0 分（低分前置条件**满足**），却 `memory_cards=0`、B 段召不回。纯函数复现（零 LLM）：`compute_weak_topics` 喂「图的基本性质 + 图的存储」⇒ `[]`；喂「平衡二叉树 ×2」⇒ `['平衡二叉树']`；一道题给两个 KP ⇒ 各 1 hit ⇒ 仍 `[]`。★ 取证曾不可能：工具回文 `format_grading_for_chat` 只输出 评分/结论/错因，**不含 KP**，而 harness 跑完就把 Store 清了 | ✅ **已修（本轮，取证通道 + 判据）**：`run_sessions` 在**清理之前**读出 episodes 落进 `CaseRecord.episodes`（`topic/score/knowledge_points/type`）；护栏 **⑲a~⑲e**（⑲d 用最小假 store 驱动**真实** `run_sessions` 验接线，⑲e 把读到的 episodes 直接喂聚合复现同一条链）。⇒ 剩下的属**样本设计决策**（A 段改成同一考点 / 按章聚合 / 只披露）= **D8**。✅ **已闭合（D8 ①，§20.8.6）**：A 段两题对齐同一考点，`mem-002` 在 ON 侧「前置条件 + 有卡 + 召回 + used + correct_use」首次全绿 （证据：`git show 9fa42ef4b:docs/EXPERIMENTS.md`） |
| 23 | **检索链上有一层「实现了但从未开启」**：`verifier` 的 LLM 相关性校验层，全仓 **24 处调用一律 `use_llm_verify=False`** ⇒ 该层对最终指标**没有任何贡献证据** | `retriever.py:377/403` 在 `use_llm_verify=True` 时会 `await _arun_llm_relevance_check(...)`（⇒ §20.5.2 已纠正审计件把它称作的「死代码」：它是**接了线的开关**，不是死码）。但实测所有调用点（`agents/tools.py`、`evaluation/adapters.py`、`retrieval_gate`、`task_eval/retrieval_probe` 及 `scripts/` 下 20 个实验脚本）都传 `False`；全仓 `use_llm_verify=True` **出现 0 次** ⇒ 这一层今天实际不执行 | 🔵 **已裁决（D10，2026-10-07）：承认未验证并披露，不跑消融、也不删。** 论文里检索章描述该层时必须写「已实现，**默认关闭且未做消融**，本文所有检索数字均不含该层的贡献」；❌ 不得写成「相关性校验提升了检索质量」（无证据）。不删的理由：删要连 `use_llm_verify` 参数一起动，波及 20+ 脚本的签名，收益只是少一段不调用的代码 |
| 24 | **paired control 的 OFF 臂从未真正关掉 Store**：旧实现只置 `agent.store = None`，而 `teaching_graph.load_memory` 与 `remember._record_episode` 都在**调用时**取进程级 `get_store()`、根本不看 `agent.store` ⇒ 两组是同一条件，**Step 5 起的「ON 有卡 / OFF 无卡」对照一直是假的** | 直接证据就在归档里：`phase1_memory_step5_store_off_step9_d8.jsonl` 的 `mem-002`（`store_enabled=False`；user_id 每 case 带随机后缀 ⇒ **不可能**是别的 case 残留）：A 段两次批改 `scores=[0.0, 0.0]`，B 段**注入了记忆卡**「薄弱：图的存储」，回复「根据你的做题记录，薄弱点在「图的存储」」⇒ 写链与读链都没关。★ **两个缺陷互相掩盖**：Step 5 当时 OFF 显示「0 卡 0 召回」被当作对照生效的证据，那其实是 #22（画像恒空 ⇒ 谁都召不回）造成的假象 —— 修好 #22 之后 OFF 才露出「照样有卡」。该记录的 `episodes=[]` **不能**当反证：OFF 臂 `eff_store=None`，取证通道压根没读 | ✅ **已修（本轮）**：抽成 `_off_arm_disable/_off_arm_restore`，**两处一起摘**（`agent.store` + `set_store(None)`），并在 `finally` **最前**恢复 —— 进程级那条忘恢复 ⇒ 之后所有 case **静默**失去记忆且不报错，比不恢复 agent 严重得多。护栏 **㉒a~㉒e**（㉒a/㉒b 按构造断言 ON/OFF 轮内 `get_store()` 的**实际值**；㉒c 锁恢复；㉒d 锁 notes 自证控了什么变量；㉒e 锁护栏自身不污染进程）。★ 连带把 **⑦b/⑦c 从源码文本断言改成行为断言**：抽 helper 后它们立刻变红，正好演示了那类断言的脆弱（**代码搬家、行为没变、红灯却响**）；反向验证 = 把 `_off_arm_disable` 临时换成旧实现 ⇒ ⑦b 必然红（实测 `tamper_red=True restored_green=True`，脚本为一次性件、未入库）。⇒ **既有 OFF 组的对照证据作废**，已用修好的 OFF 重跑（`step9_d8b` ⇒ **§20.8.6：配对第一次成立**，可测正样本 n=1） |
| 25 | **批改会把「作答正确」的题判成低分**（方向与缺陷 A 相反：不是把错题判满分，而是**把对题判零分**） | 实测 `phase1_memory_step5_store_on_step9_kp.jsonl` 的 `mem-003` 第 1 题：「判断序列 5, 8, 12, 19, 28, 20, 15, 22 是否构成小根堆，我认为构成」⇒ 逐层校验（1-based：5≺8,12；8≺19,28；12≺20,15；19≺22）**无违例、确为小根堆**，学生答对；批改却输出 **0.0 分**、KP 归到 `['堆排序','二叉树']`。★ 判定用的是当场写的 12 行堆校验器（`违例=[]`），不是人工肉眼 | 🔵 **只披露，不擅自改产品**。三点边界：① **单次观察**（Step 9 三次重复里只有这一处方向错），不足以定「批改普遍过严」；② **不进任何已发表指标** —— 该题只存在于 `memory` case，`grade` 的 15 条另有 `verdict_agreement`（13/13）覆盖；③ 原 §20.8.3 把它**误记**成「错题被判 100 分」，该归因已作废（那 100 分是判对的，错在 gold 要求两次都低分 ⇒ 属 D8/#26 的 case 设计问题）。是否值得为它扩评测集 = 后续决定，本轮不动 |
| 26 | **`recalled` / `used` 用子串包含判定，而正样本的 gold `values` 写的是章名** ⇒ 「召回成功」这句话偏松：任何含该字的记忆卡都算命中 | 口径写在 `memory_scorer` 顶部（`recalled_actual = 任一 card 含 values 中任一值`）。旧 `mem-002` 的 values = `["图"]`，而实测卡面是「薄弱：**图**的存储」⇒ 靠子串通过；`mem-003` 的 `["排序"]` 会被「快速排序 / 希尔排序 / 堆排序」**任一**满足 ⇒ 「召回成功」**测不出「召回的是不是设计的那个薄弱点」** | ✅ **已收紧（D8 第三次）**：两条正样本的 `values` 改为具体考点（`图的存储` / `快速排序`；改前核对两值均在 `canonical_names()`，`task_eval sanity` 复跑 **ERROR 0**）⇒ 正样本现在断言精确薄弱点。★ **子串口径本身不改**：记忆卡是自由文本「薄弱：X」，改全等会把排版差异也算成未召回（另一种错）。★ **负样本刻意保留章名**（`mem-005`/`mem-006` 的 `["图"]`）：对 `should_be_recalled=False` 来说偏松匹配让它**更难通过**（方向保守），无假通过风险 ⇒ 不动。指纹 `ffcf2b3233fc5595` → `3c938365da7ce614`（§20.0） |
| 27 | **layer top-up 路径把 `knowledge_points` 写死成空列表**，而同一份 `metadata` 里就带着 JSON 字符串 ⇒ 凡走这条路径进 top-k 的证据，在 `kp_hit` / `kp_mrr` / `coverage` 眼里**等于没标考点**（系统性假阴性，与 #10 同属「指标侧读不到真值」那一类） | 三条**互相独立**的证据：① **按构造**：`rag/retrieval/layer_recall.py:43` 写 `knowledge_points=[]`，而主路径 `rag/retrieval/evidence.py:93` 用 `_parse_knowledge_points(meta.get("knowledge_points"))`。本轮用假 Document（metadata 带 `["cn.arch.performance","带宽与时延"]`）直接驱动 `_doc_to_evidence` ⇒ 解析器给 **2 项**、该函数给 **`[]`。② **索引侧不背锅**（对 6 个集合做**全量分页**扫描，不是抽样）：`data_structure 777/785=99.0%`、`computer_organization 462/464=99.6%`、`operating_system 405/405=100%`、`computer_network 357/357=100%`、`questions 1358/2050=66.2%`（空值集中在 `doc_role=exam_answer` 685 条 + `exam_item` 7 条）；分桶看 **`doc_role=method` 在四个学科集合都是 100%**，`textbook` 只有 `data_structure 36/44=81.8%` 与 `computer_organization 27/29=93.1%` 有空（os/cn 的 textbook 100%）—— 这正是 §20.5.1 说的「仅剩 10 条 basic 讲义 detail 块」。③ **归档侧对不上**：两份 Step 9 探针归档 `phase1_step9_probeonly_{grade,verify}.jsonl` 的 **123 条 `top_items` 有 60 条 `kp` 为空**，其中 **13 条 `*/method` + 2 条 `*/textbook`** —— 按 ② 这些桶应当全有标签；且同一 `source`（`knowledge/advanced/computer_network/04_comprehensive.md`）在同一份归档里**既有带 kp 的、也有空 kp 的** ⇒ 差异只能来自路径，不能来自索引 | ✅ **已按 (B) 修（D12 裁决 2026-10-08）**。影响：`kp_hit` / `kp_mrr`（⇒ Generate 的 `coverage` 项）被**系统性低估**。★ 同时给 §20.5.1 那 **8 条 `coverage` N/A** 提供了一个比「旧索引未打标」**更可能的解释**：某题 top-5 若全走 top-up ⇒ `_all_kp(top)=[]` ⇒ 判 N/A；但归档**没存 `evidence_id`**（⑯ 只存 source/category/doc_role/kp/score）⇒ 这条**仍不能定论**，不许写成结论。三条路：**(A) 改产品**（`_doc_to_evidence` 改用解析器，1 行）：指标与对外契约一起变真，但 `EvidenceDoc.knowledge_points` 是**契约字段**（`agents/tools.py:54` 会带给 agent）⇒ **动检索链 ⇒ 触发新版本 + qa/generate 的 agent 侧数字要重跑（要 token）**；**(B) 只改评测口径**（`retrieval_probe._to_item` 在 `ev.knowledge_points` 为空时从 `ev.metadata` 兜底解析）：零 token、不触发版本，`retrieval_gate` 与探针当场可重测；代价是「指标说的」与「模型实际看到的」不一致（模型看到的 top-up 项仍无考点标签）；**(C) 只披露**。我建议 **(B) + 把产品侧那半单独披露**：与 #10 完全同构（修指标侧、离线重算、归档不改写），而 (A) 的代价是在收尾锚点上换检索契约。**已落地**：`retrieval_probe._to_item` 在 `ev.knowledge_points` 为空时从 `ev.metadata` 兜底解析（复用 `rag.retrieval.evidence.parse_knowledge_points` —— 原先是私有名，已改公开，防两套解析分叉）；护栏 **㉕a~㉕e**（㉕a 驱动真实 `_to_item`；㉕b 反向：metadata 也没有 ⇒ 记空、**绝不虚构**；㉕c 锁「与解析器同结果」；**㉕d 锁产品契约仍不带宽 KP**（(B) 的边界，改回 (A) 必然红）；㉕e `_all_kp` 不再漏）。⇒ 影响实测见 §20.5.1 末：coverage N/A **12 → 1**、`kp_hit` **0.889(16/18) → 0.966(28/29)**（成对读数、零 LLM）。★ **历史归档一律不回写**：0B/Phase 1 的 `gen_coverage` / `kp_hit` 仍按当时读数引用，论文里两处并列披露 |
| 28 | **写入证据判据放错了位置、替原因下了结论、且没有下游读者**（2026-10-08 对自己代码的对抗性 review 抓到，四条同源问题一起修） | ① **位置**：`memory_write_missing` 的调用点原先在 `if case.task == "memory"` **之外**，而非 memory 任务走 `run_turns` —— 它照抓 `grade_scores`、却**从不**读 Store ⇒ `episodes` 恒空 ⇒ 任何一次 grade/verify/qa 实跑都会在**第一条**被判 `env_error`，而 `cli._run` 的 `break` 在 `append_record` **之前**（`cli.py:72-79`）⇒ 整轮中止**且那条记录连盘都不落**，中止日志取 `hard_fails[0]`/`retrieval_error`（两者皆空）⇒ 屏幕上是一行**没有原因的**「中止」。★ 这条直接卡住 `EFFECT_PLAN §6 Final Gate`。② **归因**：函数把「没落库」写成**环境类** —— 可缺陷 C（`record_grade` 拿不到 config 被静默跳过）的症状与 TEI 502 一模一样，而 `memory/safe.py:24-35` 把写失败压成一行 WARNING、既不计数也不落到 record ⇒ 单凭 `episodes==[]` **无法区分**，指认环境等于替缺陷 C 打掩护。③ **下游**：注释承诺「不进指标」，但 `report._is_invalid` 与 `memory_step5_paired.ArmSummary` **都不读 `env_error`**（全仓 grep 为零）⇒ 真正产出 Memory 数字的那条路径上，这种样本照样进分母。④ **读链**：清理前那次读取自己抛过错时只写进 `notes`（而 `notes` 从不进 record）⇒ 「没读到」会被下游当成「没写入」 | ✅ **已修（零 token）**：判据移入 memory 分支、**只报「证据缺失」不指认原因**（环境类仍由 `preflight_check()` 与 `is_env_error()` 判），命中时置 `validity_valid=False` ⇒ **复用既有排除链**，`report` 与配对脚本两侧同时生效；新增 record 字段 `memory_write_missing` / `episodes_read_failed`（读链坏了就**不做**写入推断）；`env_error` 兜一句可操作文案，中止日志不再可能为空。护栏 **㉓a~㉓i（10 项）**：㉓a 驱动**真实 `run_case`**（`_run_agent` 与检索探针打桩 ⇒ 零 LLM、零 TEI 依赖）证明 grade 任务不开火、㉓b/c 锁「命中 + 不指认原因」、㉓d/d' 三个反向（有 episode / 读链坏 / OFF 臂）都不报、㉓e+f **逐条验证两个下游读者**、㉓g/h 证明真实环境信号仍开火（没把闸拆没）、㉓i 锁字段落盘。★ **牙齿实测**：把调用点临时移回分支外 ⇒ `㉓a ❌ env_error=True primary=tool_error`、整套 gate 退出码 1；还原后 **175 项全绿 exit 0**（篡改是临时 Edit + 逆 Edit，未落进任何提交）。★ **行为变化要披露**：写链证据缺失**不再中止整轮**（改为逐条标不可测）⇒ 若 TEI 在跑到一半时挂掉，剩余 case 仍会烧 token；判断是不做「无流量的假设性加固」，且预检已在开跑前拦住（㉑a）。要不要加「连续 N 条写链缺失即中止」= **待裁决 D13**。 （证据：`git show 487c2f130:docs/EXPERIMENTS.md`） |
| 29 | **护栏自己不合格**：㉑c 把 `EMBEDDING_API_BASE` 留在死端口、㉑b 是弱预言、`scripts/` 从来不在 pyrefly 范围内（新写的 ㉒ 里就有一个真类型错） | ① `check_21` 的 `㉑c` 在原 `finally` **之后**改 settings 却只还原 `USE_FAKE_EMBEDDING` ⇒ 跑完 `EMBEDDING_API_BASE=http://127.0.0.1:1`（实测），同进程后续任何 embedding 调用都会 ConnectTimeout。今天没造成红灯**只是因为 ㉑ 后面恰好只剩 ㉒**（不碰 embedding）—— 而「护栏全绿但它描述的路径已不可达」正是本仓反复踩的那一类。② `㉑b` 写的是 `len(probs2) >= 1`，标题却声称「两条路径不互相掩盖」⇒ 删掉 health 那一支它照样绿。③ `pyproject.toml` 的 `project-includes = ["src"]` ⇒ `scripts/` 从未被检查；显式跑 `pyrefly check scripts/mem/memory_step4fix_gate.py` 得 14 errors，其中 **`㉒d` 访问 `res_off.notes` 而 `_run()` 的返回注解写成了 `tuple[_SpyAgent, bool]`**（实返 `CaseResult`）—— 即「不污染进程」这套信任基础的类型从没被静态看过 | ✅ **已修（零 token）**：`㉑c` 包进 `try/finally` 两个字段一起还原，并新增 **`㉑c'`「跑完 settings 已还原」**（还原被删 ⇒ 必红）；`㉑b` 改**双向**断言（`不可达` 与 `推理` 两句都必须在）；`HTTPServer` 补 `server_close()`；`_run()` 注解改成它实际返回的形状（`tuple[smoke.CaseResult, bool 或 None]`） ⇒ 该文件 pyrefly 由 14 → **13 errors**（余下 13 条是 scripts 里的历史噪音：langgraph `Checkpoint` TypedDict 键、`sys.path` 注入导致的 `missing-import` 等，**不在本轮范围**，但口径必须改写）。★ 文档纪律：以后写「pyrefly 0 errors」一律注明**范围 = `src/`**，不能说成全仓 （证据：`git show 487c2f130:docs/EXPERIMENTS.md`） |
| 30 | **护栏的「判据数量」本身不可复现**（I6，与 #29 同属「护栏自己不合格」）：文档与标签里那句「175 项全绿」，在**干净克隆**上其实是「167 项跑过 + 8 项压根没跑」，而 `main()` 照样打印「GATE 通过 · exit 0」 | `⑬l×2`、`⑭d~⑭f`、`⑱a~⑱b`、`⑳d` 这 **8 项**读 `evals/results/task_eval/*.jsonl` 与 `calibration_30.jsonl`；按 **D11** 那些归档刻意不入库 ⇒ 缺文件时旧写法只 `print` 一行 `⏭`、**不进任何计数**，于是总数悄悄变小而退出码不变。★ 这是「**绿灯的数量**不可信」：我们反复防的是「绿而路径不可达」，这次坏的是计数口径本身。实测（一次性篡改脚本，未入库）：把 `check_20` 换成空函数 ⇒ `判定项 171 ≠ 声明 175` 且 exit 1；把 `ROOT` 指向空目录、只跑那四组 ⇒ `⏭` 恰好 **8 项**（另执行 24 项） | ✅ **已修（零 token；选「让数量自己说话」而不是「把归档入库」—— 后者与 D11 冲突）**：新增 `skip()`（跳过必须计数，一个 `if` 挡掉多项时用 `count=`）与模块级 `_EXPECTED_ITEMS = 175`；收尾两条不变量 —— ① 执行数（含跳过）必须等于声明值，② 跳过数必须为 0 —— 任一不满足 ⇒ `_flag()` 置红 + **exit 1**，文案写明「本次不能称为全绿，只能说跑了的那几项绿」。⇒ 新克隆上看到的是一行带原因的红灯，而不是一行更小的绿。★ 维护契约：**加判据必须同步改 `_EXPECTED_ITEMS`**，忘了就红（不靠人记性）。本轮护栏计数不变（仍 **175**，本机 skip=0） （证据：`git show 6d758c175:docs/EXPERIMENTS.md`） |
| 31 | 对**自己代码**的 review 余下 **12 条 Minor** 的处置：8 修 / 1 删 / 2 留（另 1 条被新护栏取代）——全部零 token | M7 是实测的：同一个「`/health` 404 但 `/embeddings` 正常」的本地桩，旧写法 `problems=['embedding 服务异常 HTTP 404…']`（会把能用的 TEI 拦在门外、`cli` 直接 return 3），新写法 `problems=[]`。护栏 **㉔a~㉔c**（正向 + 反向 + 「负样本用章名不报」三条一起，证明 lint 不是一刀切）、**㉑h**（M7）、**㉔d**（#26 不动已发表数字）；其余 6 条是小改（见处置） | ✅ **修**：M2 `_off_arm_*` 恢复状态改用 `_UNSET` 哨兵（原先 `None` 把「无需恢复」与「恢复成 None」压成一种）；M3 `cli` 打印 `informative_share` 加 `or 0`；M4 `⑳b` 改引用 `CALIBRATION_THRESHOLDS["spearman_min"]` 而不是写死 0.70；M5 `_INFORMATIVE_SHARE_MIN` 改公开名（原先 `cli`/护栏跨模块取私有成员）；M6 `judge.py` 两处过期**行号**引用改成**符号**引用；M7 预检的 health 抱怨只在推理也失败时才计入；M9 护栏的 `HTTPServer` 补 `server_close()`；M10 正样本 `values` 粒度 lint。★ **删**：`㉒d`（它读的是 harness 自己写的 note 文本，突变「OFF 臂什么都不做」时照样绿、措辞一改就假红 ⇒ 是文档不是护栏；note 仍留在 harness 里供报告引用）。**留**：M8（预检沿用产品的 `get_embeddings()` 客户端 ⇒ 不另加短超时；探针必须走产品那条路，最坏 60s 可接受因为它在开跑前且失败即中止）、M12（非 memory 的 record 不存 `grade_scores`/`episodes`；C1 修好后该分支不再影响判定，没有消费者就不扩字段）。⇒ 护栏计数 175 → **179**（`−㉒d` 1、`+㉑h` 1、`+㉔a~d` 4） |
| 32 | Grade 的「工具未返回 docs」**跨批次落在同两条 case**（`PHASE1_VERIFY.md` TODO-1 的形态升级） | Phase 1 报「批改失败（工具未返回评分结果）」的是 `grd-004`/`grd-011`；本轮 §6 **同一对 case** 报「来源: 未检索到（工具未返回 docs）」，而**同一份归档里评测探针给这两条 query 各 5 条证据、`retrieval_status=ok`、`top_items` 非空** ⇒ 「检索链没结果」这个解释被归档自身否证。其余 13 条 grade 无此措辞 | ⏳ **未修、未确证**（本轮只登记）。归因边界：agent 运行时的工具调用与评测侧探针是**两条独立通道**，探针成功**不能**证明 agent 那次调用成功 —— 要确证仍然只有 TODO-1 写的前提：**per-case tool-call logging**（`tool_calls` 字段对 Grade 15/15 全空、不具诊断性，这条没变）。★ 不做的事：不凭推测改 prompt，也不为了 D16 变绿去放宽判据（D16 实测五任务全 0.000，本行**不影响门槛判定**，只把定性从「偶发」改成「case-specific 可复现」）。⇒ 顺带：`grd-004` 恰是本轮两条 verdict 不一致之一（给 100 而 gold 0）⇒ **无证据时给满分**比「报失败」更值得在答辩上解释 （证据：`evals/results/task_eval/GOLD_REVIEW_20261008.md`） |
| 33 | Generate 在同一张报告里给出**两个看着打架的数**：主指标 0.733（11/15）与失败率 0.600（9/15），差集是 6 条「4 分但带失败原因」 | 逐条交叉表（零 LLM、直读归档）：`pf=generation_wrong` 的 6 条里有 **3 条适用项全过**（`gen-006`/`gen-014`/`gen-015`，均 fq=4.0）、另 3 条不过；`pf=generation_incomplete` 的 2 条 fq=4.0 **全过**。⇒ 两个数都没错，只是定义不同：主指标 = 逐题机械项 AND（`correctness` 取 `fq≥4`），失败率 = judge 记的首要失败原因非 none | ✅ **口径只登记、不改判据**（改了就不是 §21 冻结的那条门槛 —— 门槛仍是 ≥75%）；**缺陷本身已按 #33 修在产品侧**（⑤ `a1eea10`：`schema/questions.py` 两个字段描述 + `[规则]` 两条，护栏 **㉘a~㉘c**，201 → **204**）⇒ **效果数字要等重测才更新**：§22 仍照实写 0.733 不达，不提前替它报喜。★ 答辩若问「73% 通过和 60% 失败怎么共存」，答案就是这 6 条。⇒ 本轮 4 条不达的缺陷是**可举证**的，不是 judge 心情：`gen-003` 标准答案第 (4) 问同时写「共 1001 个序号」与「1+600+1=602？」再改口 602；`gen-007` 标准答案说「能聚合为 192.168.8.0/22」、解析却说「严格意义上三者不能合并为单个 CIDR 块」；`gen-009` 标准答案里带「= 3.2？——若按理想流水则 S 趋近 k = 4」；`gen-010` 推导中途自我改写（「地址 8：4」后接「→ 实际为 8」）。⇒ 定性：**题干 + 自相矛盾的答案键**对教学型 agent 是真缺陷，judge 判低分可辩护；同字段 Phase 1 只有 1 条 False ⇒ 存在**批次间翻转**，引用 Generate 数字必须说明单批 n=15 （证据：`git show 3fd5810cd:docs/EXPERIMENTS.md`） |
| 34 | **护栏自己覆写了 tracked 归档**（2026-10-08 实发，我自己踩的）：`agent_behavior_gate.py` 的 `--quality-out` **默认值**指向 `agent_behavior_quality.json` ——那是 **V-2026-10-02 的归档**（tracked，落点 `e36c766`）⇒ 任何人为验证跑一次护栏，就把已发表的数字原地改掉 | 实测：本次为 #33 查连带影响跑该护栏 ⇒ `git status` 出现 `M evals/results/system_validation/agent_behavior/agent_behavior_quality.json`，diff **27 增 / 27 删**，`quality_score 0.1222 → 0.1716`、`reply_len 2097 → 994`（同一判据、不同运行）。⇒ 三件事同时坏：**归档被改** + **绿灯照旧（exit 0）** + **没有任何地方提示这是已发表数字**。改动已复制到临时目录留证，再用 `git restore --source=HEAD` 还原（★ 顺序不能反：先保住证据再还原；且这次还原的是**我自己刚生成的改动**，不是人的未提交工作） | ✅ **已修（零 token）**：默认输出改成**带日期**的新文件（`agent_behavior_quality_YYYYMMDD.json`，与 task_eval 归档同为「不入库」约定），要覆写同名文件必须**显式**传 `--quality-out`；docstring 里的「用法示例」原先示范的正是覆写归档，一并改成带日期。★ 根因不是手滑而是**默认值** —— 来跑护栏的人正是在做验证，不该预期它写归档；护栏的默认行为应当是安全那一侧（与 #29/#30 同属「护栏自身卫生」这一族） |
| 35 | **出题链会把「题目正文整个丢掉」，只回一句页脚**（⑤ 复测里 `gen-009`：回复 42 字符 = 「以上为指令流水线练习题，可继续…」+「来源: 408考研练习题」，`generation_ok=False`、`failure_reason=[format_violation, generation_incomplete]`） | 同一条 case 在 §6（④）里是 1303 字符、五项全过 ⇒ 不是 case 设计问题。★ 与 **#32 同源**：两处都是「**agent 运行时的工具返回值丢了，而我们看不到工具那一层**」（`tool_calls` 字段对 Grade 15/15 全空、不具诊断性，Generate 同样没有逐次工具记录）⇒ 评测侧只能看见最终回复变短，看不见是工具没返、还是模型没转述 | ⏳ **登记，不擅自扩范围**：要确证只缺一件事 —— **per-case tool-call logging**（`PHASE1_VERIFY.md` TODO-1 的处置前提本来就是它，#32 也等它）。★ 那是产品侧改动 ⇒ 又一个新版本 + 全量重跑；而 ⑤ 复测的 Generate 主指标已过线，所以本次**不夹带**，留作 §7 之后的独立小项。当前影响：这类失败会随机占用一个分母名额 ⇒ 引用 Generate 数字必须带「单批 n=15」 |
| 36 | **LLM judge 的 `correctness` 判据对「算错」不敏感**：手验 `gen-001` 抓到一道**被判 5.0 而答案客观错**的题（Cache 组号应为 210，它写 46） | 冻结判据是 `gen_correctness = final_quality ≥ 4`，而 `final_quality` 出自 `dashscope:qwen3.8-flash` 的单次判分。★ 生成与判定是**不同模型**（deepseek 生成 / qwen 判）⇒ 不是自评偏袒；但 judge 读的是「答案是否自洽、格式是否完整」，**不会把算术重算一遍**。§22.1 那 5 道手验里 2 道有客观错、1 道满分漏检 | ⏳ **登记为判据局限、不改判据**（`§3.1 v1.0` 已冻结）。⇒ 影响所有引用 `final_quality` 的地方：**它测的是「像不像一份能用的答案」，不是「算得对不对」** —— 与 #20/#7/#10 同族，但这次错在**判据侧**而不是读数侧。可做的低成本改进（留到 §7 之后）：计算型题目让 judge 先重算再判，或抽一批人工复核表（人的活、零 token）。本轮已做的：`gen-010` 的 2.0 我用独立推算证明**判对了**、`gen-001` 的 5.0 证明**判错了** ⇒ 「过线」两个字必须连着这句引用 |
| 37 | **审核表导出器会吃掉人工标注**（#34 同一族、后果更重）：`export_review_sheets.py` 的 `export_calibration` 无条件写 `"human_score": None`，而 `calibration_30.jsonl` 的 30 条 human_score 是**人工标注** ⇒ 照 docstring 里那句默认命令重跑一次，judge 校准的 exact / within_1 / mae / spearman 四个数就没有输入了 | 实测（本机、`--out-dir` 指向副本，**没碰真表**）：满标注的表重跑后 `human_score` 全空。另外 `--out-dir` **默认就是 tracked 数据集目录** ⇒ 「顺手跑一下」= 直接改已发表数据 | ✅ **已修（零 token）**：① 新增 `merge_preserving_human`，规则是「**表里的非空值一律优先于派生值**」—— 注意不是「派生值为空才保留」，因为 grade 的 `human_score` 本来就带机械预填，审核人改的正是这个字段，按后者判会把「人把 100 改成 0」冲回 100；② 本次集合之外的行 ⇒ 抛 `SheetConflict`、**在打开文件之前**判定并 exit 3（先 `open(path,'w')` 就已经删了），要冲得显式 `--force`；③ 护栏 **㉙a~㉙e + ㉚a~㉚g**（204 → **216**），㉙d 直接钉「已发表那份仍是满标注」。★ 顺带产出两件审 gold 要用的东西：**`scripts/lib/gold_review_apply.py`**（翻转 `gold_status` 的执行器，护栏 ㉚ 钉住它「除 `gold_status` 外逐字段不变 / 注释行逐字节不变 / CRLF 不变 / 幂等 / 跨文件不误报 refused」——最后一条是 dry-run 当场抓出来的 bug）与 **`evals/results/task_eval/GOLD_REVIEW_20261008.md`**（grade 15 + generate 15 的审核工作单）。★ 签名仍然是人的：工具只执行「你确认过的 id」，`--all-draft` 存在但等于一次签 66 份 |
| 38 | **Grade gold 的 answer_key 人工核验：5 条 AI 修正错 1 条** ⇒ `grd-009`（2010-Q40）gold 分翻转 100→0。另：冻结阻塞项「grade 15 条出处/状态不匹配（30 ERROR）」经本次核验**闭合**（sanity FAIL→PASS）。★ 该 30 ERROR 的诞生从未登记：`c051495`（10-08）给 grade 15 条加派生 `gold_source_ref` 时状态检查器尚未存在（潜伏），`2cceda3`（10-09）落地双向检查后合流成 ERROR，而 10-10 的 0B/Phase-1 产物是带着这片未登记的红产出的 | `GRADE_KEY_VERIFY_20261014.md`（15 条逐题人工判定，对照 2009/2010/2011 真题原卷）+ `grade_key_verdicts_20261014.json`。**5 条 AI 修正逐条结果：2009-Q11 D→C ✓追认、2011-Q23 C→B ✓追认、2011-Q33 D→A ✓追认、2010-Q20 A→D ✓追认、2010-Q40 A→B ✗撤销**（该题递归模型下用户主机与本地服务器各发一条，原键 A 正确）。P−1 frozen list 7 条回填（2009-Q11=**fail**、余 6=pass）；其余 52 条原子仍 pending | ✅ **已闭合（2026-10-14）**：① 撤销 2010-Q40 修正（原键恢复生效，撤销记录进 `_comment`）；② 15 条补 `gold_answer_status=present` + `gold_status→reviewed`，**唯一数值变化 = grd-009 100→0**（学生选 B、正键 A ⇒ 判错）；③ `task_eval sanity` PASS（ERROR 0 · PENDING 1=集合级两极，#7 已登记）。★ **归档 Grade 读数口径披露，不回写**：0B/Phase-1 的 `verdict_agreement`（15/15 与 13/13）是在 grd-009 记 100 的错键 gold 上算出的 ⇒ 新口径**已实测**（零 LLM 机械重算：归档 `reply` 经 `metrics.parse_grade_score` 解析模型分 × 新 gold 过 `metrics.verdict_agreement`/`rate`，未跑模型、未动归档；以旧 gold 复算得 15/15 与 13/13 与登记值逐位一致 ⇒ 方法自校验通过）：**0B `verdict_agreement` 1.000→0.9333（15/15→14/15）**、**Phase1 1.000→0.9231（13/13→12/13）**，grd-009 模型判 100 而新 gold=0 ⇒ 唯一不一致项。★ 双向解读：该条同时暴露**模型也跟随了错键**（给答错的学生判满分）——新口径的 0.9333 是「gold 错 + 模型错」叠加的诚实值，不是单纯的口径损失。论文引用 Grade 读数一律用新值并带「gold 键错已订正（§20.5 #38）」脚注；旧归档不回写。④ ``needs_review`` 的「机械预填请抽查」标记按 `gold_review_apply` 的既有护栏语义保留（翻 status 不改其他字段），核验已完成的事实以本工作单为准 |
> ★ **#32 与 #35 是同一件缺失观测的两张脸**：Grade 那两条报「工具未返回 docs」而探针给得出 5 条证据、Generate 这条报「题目正文没了」而上一批同一 case 是完整的 —— 都指向「工具调用层没留痕」。把 #32 的定性从「case-specific 但未确证」往前推一步的前提，和 #35 是同一个（per-case tool-call logging）。
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
| 修复前 | **12** 条 | 18 | 16/18 = **0.889** （证据：`git show 0355a0fb1:docs/EXPERIMENTS.md`） |
| 修复后 | **1** 条（只剩 `qa-009`） | 29 | 28/29 = **0.966** （证据：`git show 0355a0fb1:docs/EXPERIMENTS.md`） |

★ 被救回的 11 条里，generate 侧恰好是 `gen-002/003/005/006/008/009/012/014` —— **与两份归档里那 8 条 N/A 同号**；
qa 侧是 `qa-007/010/015`（归档 4 条 N/A 里的 3 条）。
⇒ 于是「最可能是旧索引、但不可证明」换成了**可证明的机制**：① 「索引没打标」不再是必要解释
（现索引 + 旧读数照样能造出 12 条 N/A）；② 「走 top-up 那条路进来的证据会丢标签」是**充分**解释，
且量级足以覆盖归档里那批 N/A。
★ **仍然不许写成结论的部分**：本实验**不能**断言「0B 当年那 8 条就是这个原因」—— 归档既没存
`evidence_id` 也没存 `top_items`（⑯ 之后才有），逐条溯源不可能；且本机 `settings.RERANK_ENABLED=false`
⇒ 这次是「同一次检索的两套读数」，**不是**与 0B 可比的重跑。
⇒ 论文口径：**coverage N/A 的成因已在机制层面定位并在评测侧修复**；历史归档那 8 条写作
「与已修复的读数通道一致，但无法逐条证明」。 （证据：`git show 0355a0fb1:docs/EXPERIMENTS.md`）
★ 处置 = **#27 的 (B)**：只改评测读数，产品契约 `EvidenceDoc.knowledge_points` **不动**
（它经 `agents/tools.py:54` 交给 agent ⇒ 动它 = 动检索链 = 换锚点 + qa/generate 重跑）。
「模型实际看到的 top-up 证据仍无考点标签」这条**产品侧偏差单独披露**，并由护栏 **㉕d** 钉成可检查的事实
（将来改成 (A) 时那条必然红，用来提醒同步披露）。

⇒ 现在学科集合的覆盖是 **99.0–100%**，残留无标签块只有 10 条；而一条 query 的 top-5 全部落在这 10 条上的概率极低。
所以更一致的解释仍是：**归档（2026-10-06）跑在标签尚未打完的旧索引上**，此后索引重建过。 （证据：`git show 0f24891:docs/EXPERIMENTS.md`）

★ **复核记录（2026-10-07 晚）**：我后来用 `if meta.get("knowledge_points")` 重扫一遍，得到
「四学科 100%、ds 785/785」，与上表冲突。**是那次重扫错了** —— 该字段在 Chroma 里存的是
**JSON 字符串**，未命中的块是 `"[]"`，而**非空字符串 `"[]"` 在 Python 里为真**。按
`_parse_knowledge_points()` 的同口径（解析后判列表长度）重算，上表的 **99.0% / 82.8% 成立**。
⇒ 消费端**没有**这个坑（`evidence.py:43` 会 `json.loads` 后过滤空串，实测 `"[]"` 返回 `[]`、
探针的 `kp_hit` 正确走 N/A 分支）；坑只在**自己写扫描脚本**时。以后复核请直接用
`rag.retrieval.evidence._parse_knowledge_points`，别手写真值判断。

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

### 20.7.1 Task 9 六条路由基线重录（2026-10-09，禁止静默重录 ⇒ 逐条登记）

旧一代基线**整份保留**在 `evals/baselines/pre_task9_20261009/`（与重录同批提交，两代并存可查）；
每条新基线顶层带 `_meta`（`embedding_mode`/`rerank_mode`/`rerank_backend`/`k`/`indexed_chunks`/`golden_path`/`route_contributions`）、
`metrics`（九项指标与 `n_queries=156` 都在 `metrics` 下、**不在** `_meta`——收尾修复批 Minor-1 按真实键清单更正本段）与
`provenance`（`recorded_at`/`code_version`/`golden_sha256`/`script`/`argv`/`sampling`/`experiment_config_hash`/`dependency_lock_hash`/`model_refs`）。★ `code_version` 为 `…-dirty` 是**用户本人未提交的
`src/rag/chunking/splitter.py`**（`CODE_PATHS` 含 `src/`）所致；已证明 191/191 个 .md 语料文件新旧切分输出
逐块相同 ⇒ **未发现切分结果变化**（这不等于证明对指标无影响），且不得对外称「干净树上的运行」。重录全程 `model_refs.agent = fake:fake`
⇒ **零 LLM token**，只走检索/重排（TEI 真实服务）。★ 自收尾修复批起，**新录制**基线的 `_meta` 会带 `rerank_status_counts`（B2 四态 + unknown 的口径快照，判据 `9n` 锁导出）；本节六条引用的**两代工件都没有这个键**（实测 `grep -rl rerank_status evals/baselines/` = 0、`evals/results/task_eval/*.jsonl` 含 `"rerank_status"` 的记录 = 0）⇒ 口径是「自本批起新生成的工件会记录该状态」，**不是**「历史工件已补齐」（⇒ §20.7.2 B12）。

| 路由（基线文件） | pre→new 的全部非零 diff | 归因 |
|---|---|---|
| fake+off（`retrieval_baseline.json`） | category_hit@1 +0.0065、category_mrr +0.0037、category_precision −0.0012、kp_hit@k +0.0064、kp_mrr +0.0063、count +0.0064 | **待定**（未做代码态对照） 证据：`evals/baselines/pre_task9_20261009/retrieval_baseline.json` ↔ `evals/baselines/retrieval_baseline.json` |
| fake+on（`retrieval_baseline_rerank.json`） | category_mrr −0.0016、precision +0.0036、kp_hit@k +0.0064、**kp_mrr −0.0198**、count +0.0129 | **待定** 证据：`evals/baselines/pre_task9_20261009/retrieval_baseline_rerank.json` ↔ `evals/baselines/retrieval_baseline_rerank.json` |
| fake+disabled（`retrieval_baseline_fake_disabled.json`） | hit@1 +0.0128、category_mrr +0.0074、category_precision +0.0048、kp_hit@k +0.0128、kp_mrr +0.0337 | **待定** 证据：`evals/baselines/pre_task9_20261009/retrieval_baseline_fake_disabled.json` ↔ `evals/baselines/retrieval_baseline_fake_disabled.json` |
| real+off（`retrieval_baseline_real_embed.json`） | category_mrr +0.0030、category_precision +0.0019、**kp_mrr +0.0324**、count −0.0256 | **待定** 证据：`evals/baselines/pre_task9_20261009/retrieval_baseline_real_embed.json` ↔ `evals/baselines/retrieval_baseline_real_embed.json` |
| real+disabled（`retrieval_baseline_real_disabled.json`） | category_mrr +0.0039、precision +0.0024、kp_hit@k +0.0192、kp_mrr +0.0170 | **待定** 证据：`evals/baselines/pre_task9_20261009/retrieval_baseline_real_disabled.json` ↔ `evals/baselines/retrieval_baseline_real_disabled.json` |
| **real+on 权威**（`retrieval_baseline_real_rerank.json`） | category_hit@k +0.0064、category_mrr +0.0032、precision +0.0037、kp_hit@k −0.0064、kp_mrr −0.0003、count +0.0449 | **不属本轮代码**（有三方对照，见下） 证据：`evals/baselines/pre_task9_20261009/retrieval_baseline_real_rerank.json` ↔ `evals/baselines/retrieval_baseline_real_rerank.json` |

★ **权威路由做了三方同路由、完整 156 条的受控对照**（TEI 就绪、只差代码态）：
`pre_task9` 历史基线 / `dd4e96f`（阶段 A 之前的代码，独立 worktree）/ `6ebe807-dirty`（本轮）。
拆分结果（数值见下表，三份工件均在库内可重算）：**「旧码→新码」五项命中/排序指标逐位 0.0000**（precision +0.0001）　—— 证据：`evals/baselines/pre_task9_20261009/retrieval_baseline_real_rerank.json` ↔ `evals/baselines/diffcontrol_dd4e96f/retrieval_baseline_real_rerank.json` ↔ `evals/baselines/retrieval_baseline_real_rerank.json`（三方同路由 156 条，三份均已入库可重算）
`mean_evidence_count` 名义 +0.0064 —— ★ 该差值**落在本节 §20.2 已登记的同码运行间抖动带 [3.9231, 3.9295] 的满幅上**，且两侧各只取单次样本 ⇒ **不能**与已知抖动区分。　—— 证据：§20.2 抖动带 + 下表三方读数
⇒ 正确口径是：「本轮 B1/B2 代码在权威路由上**没有与已知抖动可区分的可测影响**
（这五项指标本就被同码重跑证明为 bit-stable）」——**不是**「有 +0.0064 的代码效应」。　—— 证据：`evals/baselines/pre_task9_20261009/retrieval_baseline_real_rerank.json` ↔ `evals/baselines/diffcontrol_dd4e96f/retrieval_baseline_real_rerank.json` ↔ `evals/baselines/retrieval_baseline_real_rerank.json`（三方同路由 156 条，三份均已入库可重算）
而 `pre_task9 → 本轮` 的 category +0.006 / kp −0.006 在**阶段 A 之前的代码上同样复现**　—— 证据：`evals/baselines/pre_task9_20261009/retrieval_baseline_real_rerank.json` ↔ `evals/baselines/diffcontrol_dd4e96f/retrieval_baseline_real_rerank.json` ↔ `evals/baselines/retrieval_baseline_real_rerank.json`（三方同路由 156 条，三份均已入库可重算）
⇒ 属 `V-2026-10-08` 锚点与今日之间的**索引/服务级漂移**，与 Task 9 无关。　—— 证据：`evals/baselines/pre_task9_20261009/retrieval_baseline_real_rerank.json` ↔ `evals/baselines/diffcontrol_dd4e96f/retrieval_baseline_real_rerank.json` ↔ `evals/baselines/retrieval_baseline_real_rerank.json`（三方同路由 156 条，三份均已入库可重算）


**三方对照读数**（权威 `real+on`，156 条；三份工件均已入库 ⇒ 本表任何人可重算）

| 指标 | pre_task9（历史） | dd4e96f（阶段 A 之前） | 6ebe807-dirty（本轮） | 旧码→新码 Δ |
|---|---|---|---|---|
| category_hit_at_k | 0.9615 | 0.9679 | 0.9679 |+0.0000　证据：本表上方三列路径（三份工件均在库内）|
| category_mrr | 0.9519 | 0.9551 | 0.9551 |+0.0000　证据：本表上方三列路径（三份工件均在库内）|
| category_precision | 0.9637 | 0.9673 | 0.9674 |+0.0001　证据：本表上方三列路径（三份工件均在库内）|
| kp_hit_at_k | 0.9167 | 0.9103 | 0.9103 |+0.0000　证据：本表上方三列路径（三份工件均在库内）|
| kp_mrr | 0.8051 | 0.8048 | 0.8048 |+0.0000　证据：本表上方三列路径（三份工件均在库内）|
| mean_evidence_count | 3.8846 | 3.9231 | 3.9295 |+0.0064（在抖动带内，不归因本轮）　证据：本表上方三列路径（三份工件均在库内）|

★ **计划的一条预期被实测推翻**：Task 9 Step 4 预期「默认路由逐位复现」，实测六条路由 diff **全非零**
⇒ 该预期不成立。已登记的这条漂移同样适用于引用 `V-2026-10-08` 基线比较的其它场合：
凡未做代码态对照的路由，diff 一律记「归因待定」，**不许**写成检索质量改善或退化。
第三批落 **D1/D3/D4** 三项决定：#2 主指标改逐题聚合（⑭ 6 项）、§7.1 三处「死代码」按实测**只删真死的那一条**（另两条一条是「接了线没人开的开关」、一条注释已自陈惰性，见 §20.5.2）、record 落 `prompt_set_version`（⑮ 6 项）。
Gate **216 项全绿**（101→116→128→129→134→138→148→157→162→175→179→184→194→201→204→**216**；204→216 = ㉙a~㉙e + ㉚a~㉚g（#37 与翻转器），201→204 = ㉘a~㉘c（#33），194→201 = ㉖ 之后 D14/D15/D16 三组；162→175 = 收尾修复批：`㉑c'`/`㉑f`/`㉑g` 3 项 + **`㉓a~㉓i` 10 项**，见 #28/#29；175→179 = Minor 批（`−㉒d`、`+㉑h`、`+㉔a~d`，见 #31）；179→184 = `+㉕a~e`（#27 / D12）；184→194 = D14① 的 Verify 行为层（`+㉖a~㉖j` 10 项）；194→201 = D15/D16 的 Memory 结构断言（`+㉗a~㉗g` 7 项）。★ **#30 之后这句「全绿」变成脚本自证的**：收尾会比对 `_EXPECTED_ITEMS` 声明值并要求跳过数为 0，少跑或静默 `⏭` 都是 exit 1，见 #30）、`pyrefly` **0 errors（范围 = `src/`；`scripts/` 不在 `project-includes` 内，见 #29）**、ruff check/format 通过、 （证据：`git show 3e77e0112:docs/EXPERIMENTS.md`）
`task_eval sanity` 66 条 ERROR 0、两份归档 12 条 validity **逐条不变**（新 gold 不动已发表数字）。

**31 条已知偏离**全部登记（#31 = 对自己代码的 review 余下 12 条 Minor 的处置，含两条意外收获）（#28~#30 来自 2026-10-08 对自己代码的对抗性 review：#28 四条同源问题一起修、#29/#30 是**护栏自身**不合格 —— 进程污染 / 弱预言 / 计数不可复现）；**#2 已由 D1 定夺并落地（2026-10-07）**：主指标 = 逐题「适用项全过」**0.80**，项级池化 0.9423 降级为诊断（护栏 ⑭）。 （证据：`git show 59221387d:docs/EXPERIMENTS.md`）
★ **#27 是收尾复核时新发现的**（top-up 路径丢 `knowledge_points` ⇒ `kp_hit`/`kp_mrr`/`coverage` 系统性低估），**已登记、未改代码**，三条处置路 = **待裁决 D12**。
★ **#24 是 Step 9 之后新登记的**：paired control 的 OFF 臂从未真正关掉进程级 Store ⇒ **既有 OFF 组的对照证据全部作废**，已用修好的 OFF 重跑（§20.8.6：**配对第一次成立**，`mem-002` 同 case 同前置条件下 ON 有卡并召回 / OFF 零卡，可测正样本 **n=1**）。
★ **#25/#26 是同批次复核时新增的**：#25 更正了 §20.8.3 的一处**误归因**（批改其实把对题判成了 0 分，不是把错题判成 100 分）；#26 是 D8 改 case 过程中发现的「正样本 values 写章名 ⇒ 召回判定偏松」，已把两条正样本收到具体考点。
—— **#2 的解剖与采纳状态见 §20.5.1**（核心结论：五项里只有
`correctness` 与 `coverage` 有区分力；8 个 `coverage` N/A **疑似旧索引**产物——全量扫描显示四个学科集合
KP 覆盖已达 **99.0–100%**（仅剩 10 条 basic 讲义 detail 块）—— ★ **已定论（#27/D12）**：主因是读数通道，成对读数实测 coverage N/A **12→1**（§20.5.1 末）；但归档无 `evidence_id` ⇒ 当年那 8 条只能写「与已修复的机制一致」； （证据：`git show 0f2489159:docs/EXPERIMENTS.md`）
`difficulty` 是双重断开的死项）；**#3（provenance 无 prompt hash）/ #5（OFF 配对无正样本）** 需决定重跑口径；
**#9（0B 的 Memory 四率口径不同）在论文引用该数字时必须标注**；#1 已披露不修。

### 20.7.2 ★ Task 10 收尾：偏离的**合并登记**（三态分类）+ 开放项的当前状态与后续处理条件

> 本节是本轮要求的**统一登记处**：此前散在 §20.7.1 / §20.5 / `EVIDENCE_CHAIN.md` §7 各处的裁定与偏离
> 在这里**分类归位**。★ **数字一律回指原登记处，本节不另写一份现实**（重录逐条 diff 看 §20.7.1，
> `mean_evidence_count` 抖动带看 §20.2，效果口径的 37 条偏离看 §20.5），并且**三类不许统一写成「已解决」**：
> **A 已裁定的设计选择 / B 已知局限 / C 尚待验证的归因**。
> 复现（三条都是零 token，随时可跑）：`uv run python scripts/gates/evidence_chain_gate.py`、
> `uv run python scripts/lib/build_claim_ledger.py --records evals/results/task_eval/ec_r1_final_gate.jsonl --check`、
> `uv run python -m evaluation.task_eval sanity`。

#### A. 已裁定的设计选择（是选择，不是缺陷；改动要有裁定，不许顺手）

| # | 选择 | 依据 | 取证命令 | 这条**不**意味着 |
|---|---|---|---|---|
| A1 | **Verify / Grade 两行主指标从 §6 原文的 tier-2 judge 量换轨为 tier-1 机械/物证量**（checkpoint 6 追加条 ⑤） | 依据 D14（Verify 行为层机械化）+ G1b 撤销（两极 gold 无判别域，§20.5 #7） | `uv run python scripts/gates/evidence_chain_gate.py` 的 `6h2`（走校准前置的 tier-2 行只剩 QA）与 `6h3`（派生行 `max(tier)`≤1、tier-2 只出现在 optional 替身） | ★ **不是**「Task 6 偷偷降低了 tier」；也**不是**「judge 门槛已被证明」——见下面两条推论 |
| A1-① | 当前这两行将来走向「已证明」**不要求** judge 边界校准 | 因为它们不再建立在 judge 观点上 | 同上 `6h2`/`6h3` | 不要求 ≠ 已免除：QA 行仍要（§1.3 两个前置） |
| A1-② | 若将来**重新主张** §6 原文那条 tier-2 断言（`final_quality ≥ 4`）⇒ 那是**另一行**，必须自己声明 `tier=2` 并承担 `boundary_calibrated` + `repeat_jitter` 两个前置 | `EVIDENCE_CHAIN.md` §1.3 第二条硬规则 | `uv run python scripts/lib/build_claim_ledger.py --records …` 出 ledger 主表「前置（tier_ok 依据）」列 | 把现有行硬绑回 tier 2 = 造出一条从未被证的断言 |
| A2 | **§1.1 状态表与冻结公式的口径差 = 改文档收口，不动 `derive_status`**（checkpoint 10 裁定；brief B 表第 9 行） | 公式是三态推导 / ledger / `--check` 的公共依赖；本 Task 明令不改业务代码 | 现行判据与残留代价写在 `docs/EVIDENCE_CHAIN.md` §1.1（含「mutation 取证测的是**判据对契约输入的敏感性**，不是主张的数值」那句） | 不意味着这一格变成「已证明」，也不解除 V0 ② 的拦截（`--check` 第 3 段仍红） |
| A3 | **`evals/results/task_eval/` 的数值工件（`*.jsonl` / `*.report.json`）纳入版本控制**；★ 逐轮 `*.log` 仍不入库（单份可达 MB 级 ⇒ 沿用 D11 的取舍） | 本轮要求「冻结、只读」必须有版本控制兜着；旧裁定 **D11**（`*.jsonl` 不入库，理由＝二进制不可 diff、仓库变大）**被本轮部分推翻**：结论虽都在 `.md` 里，但「冻结」没有版本控制就只是措辞（brief 验收约束 A.1） | `git ls-files evals/results/task_eval` 计数 + `git status --short -- evals/results/task_eval`（剩下的 `??` 就是仍刻意不入库的那几份）+ `git log --oneline -1` 看本轮提交 | ★ 这是一次**改口**，不是「D11 一直这么定」：归档仍不回写数值，入库只为让「冻结」可核对 |
| A4 | **旧归档标 `superseded`，不标 `invalidated`、不删文件、不改数值** | brief 验收约束 A.1：被替代 ≠ 无效 | `evals/claims/artifact_status.json` —— ★ 收尾修复批更正：它**不是**由 `claims.artifact_status()` 生成（该 helper 只提供行形状，且只被用于 `ledger.md`「工件状态」节渲染**本次输入工件**那份视图），**目前没有命令能再生成它** ⇒ 后续处理条件见 B17。真实存在的只读核对命令（验证工具、非门禁判据）：`uv run python -c "import json,os; rows=json.load(open('evals/claims/artifact_status.json',encoding='utf-8')); bad=[r['path'] for r in rows if not os.path.exists(r['path'])]+[r['superseded_by'] for r in rows if r['superseded_by'] and not os.path.exists(r['superseded_by'])]; print('缺失:',bad or '无')"` 实测输出 `缺失: 无`；被指向的目标同为表中 **active** 新一代（链式指错 0 处、`invalidated` 0 处） | 不意味着旧读数还能沿用（⇒ B4），也不意味着引用它们违法（⇒ 连着标注引用即可） |
| A5 | 检索失败 reset **只允许发生在独立取证单元的边界**（spec v1.3 撤销第三个调用点） | 实测后一个 reset 抹掉前一个未消费的证据 ⇒ 净降低检测能力 | `uv run python scripts/gates/evidence_chain_gate.py` 的 B7/归因那一组 | 不意味着 `ip`/异步语义那两条债已清（⇒ B8/B9） |

#### B. 已知局限（照实披露；本 Task **只登记不修**）

| # | 局限 | 当前状态 | 后续处理条件（什么时候必须动它） | 取证 |
|---|---|---|---|---|
| B1 | **§3.1 五项中 `correctness` / `answerability` / `difficulty` 三项在 P−1 盲标之前恒 `missing_premise`** ⇒ Generate 主指标**整族不可出数**（brief Step 3 ①） | 未清偿（P−1 未做） | 填完 `gold_answer` + `expected_difficulty`（零 token，约 2 人时）后重算；届时 ledger 取证时间整体刷新 | `uv run python scripts/lib/build_claim_ledger.py --records … --check` **第 3 段 V0 ②** 就是拦这条的 |
| B2 | **Grade gold 只有两极** ⇒ `score_tolerance@±10` 判别域受限，行级判据改用 `verdict_agreement` 且只作辅助位（brief Step 3 ②） | 已裁定为「语料性质，不补标」（G1b 已撤回） | 只有当 L3 语料出现可标部分分的题型时才重新评估；**禁止**为造判别域而改题 | §20.5 #7、ledger 的 Grade 行注记（`degenerate_gold`） |
| B3 | **R5 改了复合指标的聚合语义 ⇒ 旧归档的读数不可沿用**（brief Step 3 ③）：同一份归档按新规则重算会得到不同状态词 | 已落地为代码；旧归档不回写 | 若要在新旧之间做比较，必须**两边都按同一套 registry 重算**（`reanalyse`，零 token），不得拿旧报告数字对新代码 | 证据：`evals/claims/artifact_status.json` 里 `phase1_final_gate_20261008.jsonl` 的 `reason=composite_na_semantics_changed`；机制与原事故两个读数写在 `docs/EVIDENCE_CHAIN.md` §4.2（本节不复制） |
| B4 | **5.B 全部延后项的 limitation 清单**（brief Step 3 ④）：BM25 IDF 截断候选池、`k=5` 被当未指定、`_rrf_scale_needed` 硬编码复刻、parent-window 文本重复、`weak_topics` 清除死分支、生产/评测聚合口径不一致、`difficulty="mixed"` 与子项 `Literal` 冲突、`score` 越界抛错、`is_wrong`/`score` 不一致、B3 空召回写缓存、B5 `/api/metrics` 鉴权与阻塞、B6 SSE 断连收尾 | 逐条**未修**，维持延后 | ★ 两条自动升级条件（不是可选项）：`difficulty=mixed` 或 `score` 越界若让 §6 的 `tool error` 行越过门槛 ⇒ **自动从 5.B 升到 5.A**（阻塞重跑） | 清单原文 `docs/EVIDENCE_CHAIN.md` §5.B（本节只登记状态，不复制第二份） |
| B5 | **`evidence_pollution` 受「非空包」门控**：检索层归因门是 reason-agnostic 的（`retrieval_status == "empty"` ∧ `pack_nonempty is False` 才开门），而「证据被污染」按定义发生在**包非空**时 ⇒ 这一原因**今天不可能被机械写入**，只能来自 judge 并被隔离 | 现状即如此，**不是** per-reason 门控 | 要做完整 per-reason 门控得给 `evidence_pollution` 单独开一条基于物证（包内类目/学科纯度）的判据 ⇒ 属新增判据，**不属本轮范围** | `src/evaluation/task_eval/judge.py` 的 `retrieval_layer_gate_open()`；`uv run python scripts/gates/evidence_chain_gate.py` 的 `8i` 行（三行规则逐字落地） |
| B6 | **`retrieval_status="error"` 的语义 = 任一路由故障或超时**，**不等于**索引整体不可用（Task 8 口径） | 已按此实现（只升级不降级；空清单不凭空造 `error`） | 报告/论文里写这句时必须照抄「任一路由」限定，不得写成「检索服务不可用」 | `src/evaluation/task_eval/runner.py` 的 `_escalate_status`（规则就写在 docstring 里）+ 诊断字段 `route_failure_notes` |
| B7 | **`empty_result=True ⇒ failed` 与 §5 B2「空结果 → `degraded`」的用词张力**：代码把「重排返回空列表」折进 `failed`，而 spec 那行字面写着空结果属 `degraded` | ★ **本轮不选边、不静默改**（两边各有理由：`_safe_to_thread` 用哨兵区分「真返回了列表」与「抛错/超时走兜底」，实测这条路径不可达） | 裁定权在项目所有者：要么改 `_derive_rerank_status` 的映射并同步 `9c/9e` 判据，要么把 §5 B2 的措辞改成「无分→`degraded`、空→`failed`」并登记为 v1.4 修订 ⇒ **两者都要动代码或动冻结 spec，都不属本 Task** | `src/rag/retrieval/pipeline.py` 的 `_derive_rerank_status` + 同文件 `_RERANK_UNSET` 上方注释；判据 `uv run python scripts/gates/evidence_chain_gate.py` 的 `9a/9c/9e` |
| B8 | **同步 `similarity_search_with_score` 与异步 `asimilarity_search_with_score` 语义相反**（同步走 Chroma 原生「距离」，异步自己换算成「相似度」）；**当前消费点各自用对了方向**，所以今天没有假数 | 保留为**技术债务**（本轮只登记） | 任何新增调用点都必须先看函数自己的注释；若将来统一到「只暴露相似度」，属检索链改动 ⇒ 换锚点 + 四路由重跑 | `src/rag/common/vectorstore.py` 的 `similarity_search_with_score` / `asimilarity_search_with_score` 两处签名 |
| B9 | **`embeddings.py` 的 `ip` 分支 `return d`**：`SUPPORTED_SPACES` 含 `ip`，而该分支把内积原样当相似度返回 ⇒ 与「越高越相似」契约的方向**未经实测** | ★ **当前不可达**（现役四个学科集合实测全为 `cosine`）⇒ 但「不可达」**不等于**契约正确，**也不等于**已修复 | 出现任何 `ip` 空间的集合之前：要么把它移出 `SUPPORTED_SPACES`（未知 space 由 `9g` 逼着抛错），要么按 §1.5 先测方向再登记并**实测** | `src/rag/common/embeddings.py` 的 `SUPPORTED_SPACES` / `similarity_from_distance`；判据 `uv run python scripts/gates/evidence_chain_gate.py` 的 `9g` |
| B10 | **`TIER-DEBT-task3`**：`gen_answer_key_validity` / `gen_analysis_agreement` 两个 `optional=True` 的**机械替身**注册为 `tier=2`，按 §1.3 证据种类定义应为 0/1 ⇒ 后果是**假阴性（过严）**：判据级附表逐条走 `tier_ok_for(p.tier, …)`，无校准 ⇒ 这两行永远显示 tier✗，而理由并不存在。**主行不受影响**（optional 不进 `max(tier)`，由 `6h3` 取证） | 债务**在册未偿**：字面 token 自本轮起同时出现在代码注释、ledger 附表与本节 ⇒ 读者看到锚点能查到实名（评审 M-4 的验收条件） | 改 tier 会让 `7g` 变红 ⇒ **同一提交里**删掉 `7g` 的债名单条目并在本节写明「已清偿」（这条规矩本身就是防「改了判据忘了登记」） | `src/evaluation/task_eval/predicates/generate.py` 两处 `tier_reason=("TIER-DEBT-task3",)`；`uv run python scripts/gates/evidence_chain_gate.py` 的 `7f/7g`；`uv run python scripts/lib/build_claim_ledger.py --records …` 的附表「tier 依据」列 |
| B11 | **`gen_answerability` 的 tier 锚点待 P−1 重新申报**（评审 M-5）：现挂 `§1.3-tier1`，而 §1.3 把 `answerable` 举为 **tier 2** 的例子（`docs/EVIDENCE_CHAIN.md` §1.3 那行 + `judge.py` 确有该 judge 字段）。今天它恒 `missing_premise`（n_measured=0、状态词「未测量」、V0 ② 已拦）⇒ **无假数** | 待处理（本轮只登记） | ★ **P−1 完成、它一旦能返 pass/fail 就必须重新申报锚点与 tier** —— 否则 `tier_ok_for` 会因 `tier≤1` **自动放行两个校准前置**（那才是真正的假绿） | `src/evaluation/task_eval/predicates/generate.py` 的 `gen_answerability` 注册行；附表同列 |
| B12 | **`9i` 余项：B2 的 hop①（pipeline 非空路径经 `_finalize_retrieval` 写 `doc.metadata["_rerank_status"]`）仍只有「键名配对」结构锁 `9h`** —— hop③（probe 读侧）与桥接/空包、record、基线诸送达段已由收尾修复批（Important-3 明令范围）升为**行为锁** `9m`/`9n`/`9o`/`9p` | **部分清偿**（修复批只偿 Important-3 点到的一半：送达行为锁已进门禁；余 hop① 一条仍未偿，★ 不声称整条已清）。口径红线：行为锁证明的是「**自本批起新生成的工件会记录** `rerank_status`」——历史面**没有**被补齐：实测 28 份归档/该键在历史工件里的存在率 = 0（可重跑核对：`grep -c '"rerank_status"' evals/results/task_eval/*.jsonl | grep -v ":0" | wc -l` ⇒ 命中文件数应为 0；`grep -l rerank_status evals/baselines/*.json | wc -l` ⇒ 应为 0。★ 底数写成命令而不是条数，否则归档每加一行这个数就过期） | 下一轮补 hop① 行为锁：真实跑 `_finalize_retrieval`（构造 docs+ctx）断言 `doc.metadata["_rerank_status"]` 等于传入状态；加判据必须同步改 `_EXPECTED_ITEMS`（忘了就红） | `uv run python scripts/gates/evidence_chain_gate.py` 的 `9h`（结构锁）+ `9m`/`9n`/`9o`/`9p`（行为锁）；历史零证据数字为收尾修复批报告实测 |
| B13 | **R1-B 语义签署从未发生** ⇒ ledger 主表 `signed` 恒 False，**没有任何一行能到「已证明」** | 待人工：每个判据对着 `EFFECT_PLAN.md` §3.1 原文签一次「已审@版本」，约 1 人时、零 token | 落 `evals/claims/r1b_signatures.json`（约定格式写在 `scripts/lib/build_claim_ledger.py` 的 `load_signatures()`）后该列自动变真 | `uv run python scripts/lib/build_claim_ledger.py --records …` 看主表「R1-B 签署」列（当前显示签署文件不在册） |
| B14 | **R3「孤立结论」在历史文档里仍大面积存在**：本轮只保证**自己新增/改写的每一行都带锚点**，历史行不要求全部清偿（裁定 T10-B） | 剩余条数**以 `--check` 第 2 段的真实输出为准**，本节不写估计值（写死就是第二条孤立结论） | §7.3 Freeze 收尾时逐条补锚点；补一条就把该行从红名单里消掉，无需改代码 | `uv run python scripts/lib/build_claim_ledger.py --records … --check` **第 2 段**逐个文件打印行号 |
| B15 | **V0 未清偿**：① 老归档缺 `provenance` 整包 / `item_reasons` 等新键；② B1 所述的 required 判据全未测量 | ★ **这是本轮的正确结果**，不是事故：`--check` 第 3 段就该红 | P−1 + §7.3 Freeze 全量重跑后自动清偿；**禁止**用 `--update-baseline` 或放松检查让它变绿 | `uv run python scripts/lib/build_claim_ledger.py --records … --check` **第 3 段**（逐类缺键点名） |
| B16 | **`ledger.md` 里有两句「等本轮」的生成文本**（判据附表那条 ★ 注记写着「与 §1.1 口径不一致 / 待 Task 10 文档收口」，工件状态那节写着「历史归档的 superseded 标注由 Task 10 收尾」）⇒ 收口已发生，句子仍是收口**前**的口吻 | 本轮**不改**：`ledger.md` 是生成物，手改会立刻让 `--check` 第 1 段红（文档 ≠ 重算）；而注记文本在 `scripts/lib/build_claim_ledger.py` 里 ⇒ 本 Task 明令不动 `scripts/` | 下一次动 `scripts/` 的小改里同步这两句（★ 只改文本、不改判定），或等 §7.3 Freeze 重跑时随取证时间一起刷新 | 证据：`uv run python scripts/lib/build_claim_ledger.py --records … --check` 第 1 段仍 PASS 就是这两句「未被手改」的记录；现行判据以 `docs/EVIDENCE_CHAIN.md` §1.1 为准，替代关系以 `evals/claims/artifact_status.json` 为准 |
| B17 | **`evals/claims/artifact_status.json` 目前没有门禁消费者**：A.1 要求的「`superseded_by` 指向真实存在的工件」这一条，只由报告 §4 的一次性脚本查过（`build_claim_ledger.py:814` 附近只打印 active 行）⇒ 引用关系断了不会有判据红。★ 收尾修复批**把登记写准（不偿债）**：两份「工件状态」视图是**不同口径、不许默认为一致** —— ① `artifact_status.json`（17 行 = 9 `superseded` + 8 `active`）= 旧工件**替代关系真源**，手工登记件、**目前没有命令能再生成它**；② `ledger.md:116-124` 那张表（3 行全 `active`）由 `build_claim_ledger.py` 的 `render_artifacts()` 从**本次 ledger 运行的输入工件**（`--records` 归档 + `falsify_latest.json` + `calibration_30.jsonl`）渲染，印的是「本次重算消费了哪些工件」而**不是**替代关系 ⇒ 只有 3 行、构造使然（`ledger.md` 那句「本 ledger 当前只登记 active」即此口径的自述，B16 同源）。17 行的 `path`/`superseded_by` 存在性与「指向 active 新一代」已由 A4 行内那条只读命令实测核过（链式指错 0），但那是**验证工具**、不是判据 | **登记未修**（本 Task 放行条件 1 禁改 `scripts/`，本批同样不偿：不加判据、不改 `build_claim_ledger` 去读这份 JSON）。★ 后续处理条件：下一次触 `scripts/` 的提交里，同批 ① 给 `artifact_status.json` 加一条判据（每个 `superseded_by` 目标存在 + 每个 `path` 存在 + 目标须为 active），② 同步改写 ledger 附表那条 ★ 注记的渲染字符串（B16 遗留的「历史指向」即由此收口），③ 一并把 ①② 两份视图的口径差异写进生成文本。两次改动同批，避免「改了判据忘了登记」 | 证据：`evals/claims/artifact_status.json` 的 17 行；`grep -n artifact_status scripts/lib/build_claim_ledger.py`；两视图差异核对命令见 A4 行内（只读、可重跑） |

#### C. 尚待验证的归因（★ 不许升格成「改善」或「退化」）

| # | 事实 | 现在能说到哪一步 | 取证命令 |
|---|---|---|---|
| C1 | **六条基线 diff 全非零** ⇒ 计划 Step 4 的预期「默认路由逐位复现」**未实现**（brief A.2 ①，措辞照此） | 只能写「预期不成立，六条逐条 diff 见 §20.7.1」；不得写「复现」 | `uv run python -c` 读 `evals/baselines/retrieval_baseline.json` 与 `evals/baselines/pre_task9_20261009/retrieval_baseline.json` 相减（§20.7.1 登记时用的就是这条重算）。★ 自收尾修复批起改跑可重跑的**两向穷尽核对**：`uv run python scripts/ops/check_baseline_diff_registration.py`（六条 × 全部指标：工件的每个非零 diff 都已登记 ∧ 登记的每个 diff 都能在工件核到，任一处对不上即退出码非 0；验证工具，不进 `evidence_chain_gate`） |
| C2 | **权威路由（`real+on`）有代码态对照**（`dd4e96f` 独立 worktree 与本轮同路由、完整 156 条） | 支持「该漂移在**阶段 A 之前**已存在」⇒ **不得**说本轮代码造成了它（brief A.2 ②） | 三方对照的逐指标结果登记在 §20.7.1 的「受控对照」段（回指，不重述） |
| C3 | **其余五条路由没有代码态对照** | 一律保留「**归因待定**」（brief A.2 ③）；★ 不许写成检索质量改善或退化 | §20.7.1 的六行表（每行自己标了归因列） |
| C4 | `mean_evidence_count` 的名义 +0.0064 | ★ 必须连同 §20.2 已登记的**同码运行间抖动带**一并披露，**不作为代码效果证据**（brief A.2 ④）。正确口径是「本轮代码在权威路由上**没有与已知抖动可区分的可测影响**」 | 证据：抖动带与其三次读数登记在 **§20.2**（Task 9 之前就在）；重录侧的引用在 **§20.7.1** ⇒ 两处回指，本节不另写数字 |
| C5 | 本轮工件的 `code_version` 为 `…-dirty`；切分输出逐块相同 | 如实写 `-dirty`（成因＝项目所有者本人未提交的 `src/rag/chunking/splitter.py`）；切分逐块相同**只能**支持「**未发现切分结果变化**」，★ **不得**改写为「干净树运行」（brief A.2 ⑤） | `uv run python -c` 打印 `evaluation.provenance.code_version()`（活值，随工作区状态变）+ `git status --short`（看脏在谁身上） |
| C6 | `#32` / `#35` 那两条「工具层没留痕」的失败，其共同前提 **per-case tool-call logging** 仍缺 | 维持 §20.5 的「未确证 / 登记不扩范围」，★ 不因本轮文档收尾而改变 | §20.5 #32/#35 两格 + `PHASE1_VERIFY.md` TODO-1 |
| C7 | **`evals/results/system_validation/agent_behavior/agent_behavior_quality_20261008.json` 故意不入库**（#34 改默认输出名之后的一次重跑，读数与已发表归档不同）⇒ 提交它容易被读成「重定基线」，而本轮没有任何重定基线的裁定 | **不重定基线**：本轮没有任何裁定采纳它的读数 | 未入库文件**留在工作区、不删不改**；若将来要采纳它的读数，必须先有一条明确裁定（写明取代哪份归档、为什么），再入库。证据：`evals/results/system_validation/agent_behavior/agent_behavior_quality_20261008.json`（未跟踪） ↔ 已入库的 `evals/results/system_validation/agent_behavior/agent_behavior_quality.json` |

#### 收尾动作清单（本轮做的四件事，每条都给命令，不给记忆）

| 动作 | 落点 | 命令 |
|---|---|---|
| 勘误改成命令形状 | `docs/README.md` 的锚点行 / 门禁行 / `task_eval` 行 / `.gitignore` 例外行 | 被替换掉的旧声称：写死标签、写死项数、写死「`git ls-files` = 0」三处 ⇒ 现查 `git tag -l`、`grep -n "^_EXPECTED_ITEMS" scripts/mem/memory_step4fix_gate.py`、`git ls-files evals/results/task_eval` |
| `--dataset` 路径校正 | `CLAUDE.md`「常用命令」块、`README.md`「RAGAS 评测」块 | 旧写法 `evals/sample_408.jsonl` **不存在**；真实路径 = `evals/datasets/golden/sample_408.jsonl`（= `src/evaluation/cli.py` 的 `--dataset` 默认值）。核对：`git ls-files evals/datasets/golden` |
| 旧工件标 `superseded` | `evals/claims/artifact_status.json` | ★ 收尾修复批更正：此件为 Task 10 **手工登记**——`claims.artifact_status()` 只是行形状 helper、**不产这份文件** ⇒ 目前没有命令能再生成它（清偿条件挂 B17；原句「由该函数生成 + 本节末有自查命令」经查为**空头承诺**，Minor-2 按实测改掉）。`superseded_by` 全部指向在库路径且为同表 active 新一代；只读核对命令 = A4 行内那条 `uv run python -c`（可重跑，实测 `缺失: 无`） |
| `ledger.md` 定稿 | `evals/claims/ledger.md`（此前从未落盘，只有 `ledger_draft.md`） | 生成：`uv run python scripts/lib/build_claim_ledger.py --records evals/results/task_eval/ec_r1_final_gate.jsonl --out evals/claims/ledger.md`；复核：同命令加 `--check`（第 1 段必须 PASS = 文档 == 重算） |

### 20.7.3 六条路由基线**二代**重录登记（2026-10-14，禁止静默重录 ⇒ 逐条登记）

> 本节补的是**两笔欠账**：① `8e2add6`（2026-10-10 19:20，`chore(eval): 重录 6 条检索基线 —— 门禁对准
> 生产入库路径后`）**只改了 6 个 JSON、`docs/EXPERIMENTS.md` 0 行** —— 即 §20.7.1 标题所禁止的
> 「静默重录」；② 今日 `78e8461` 一代（反假绿前置闸 + 层序抖动容差落地后重录）。
> 口径与 `scripts/ops/check_baseline_diff_registration.py` 逐字一致（`round(new−old,4)`，非零即登记义务）。 （证据：`git show d54d3ded8:docs/EXPERIMENTS.md`）

旧一代仍整份保留在 `evals/baselines/pre_task9_20261009/`。下表列的是 **pre_task9 → 当代** 的全部非零 diff，
★ 反查方向：换代**前**的读数在 §1–§18 与 §20.2，其代际声明见 §18 抬头（并在 §4 / §5 / §20.2 三处就近加了指针）。
归因列按两代拆开（`10-10 步` = `8e2add6` 吸收的量，`今日步` = 本次 `78e8461` 的量）。

| 路由（基线文件） | pre_task9 → 当代 的全部非零 diff | 分代拆解与归因 |
|---|---|---|
| fake+off（`retrieval_baseline.json`） | category_hit_at_1 -0.0192、category_hit_at_k +0.0065、category_mrr -0.0024、category_precision -0.0034、kp_hit_at_k +0.0577、kp_mrr +0.1343、mean_evidence_count -0.4936 | 除 `category_precision`（10-10 −0.0036 / 今日 +0.0002）与 `mean_evidence_count`（10-10 −0.5000 / 今日 +0.0064）外，其余五项全部由 10-10 一步贡献、今日步为 0.0000 （证据：`git show 65da547bd:docs/EXPERIMENTS.md`） |
| fake+on（`retrieval_baseline_rerank.json`） | category_hit_at_1 -0.0064、category_hit_at_k -0.0064、category_mrr -0.0064、category_precision -0.0182、kp_hit_at_k -0.0257、kp_mrr -0.0456、mean_evidence_count -1.1025 | 今日步仅 `kp_hit_at_k` / `kp_mrr` 各 +0.0064，其余今日步 0.0000 （证据：`git show 65da547bd:docs/EXPERIMENTS.md`） |
| fake+disabled（`retrieval_baseline_fake_disabled.json`） | category_hit_at_1 -0.0449、category_mrr -0.0246、category_precision +0.0067、kp_hit_at_k +0.1282、kp_mrr +0.1601、mean_evidence_count -0.0320 | 六项全部由 10-10 一步贡献，今日步 0.0000 （证据：`git show 65da547bd:docs/EXPERIMENTS.md`） |
| real+off（`retrieval_baseline_real_embed.json`） | category_hit_at_1 -0.0128、category_hit_at_k -0.0064、category_mrr -0.0099、category_precision -0.0065、kp_hit_at_k +0.0385、kp_mrr +0.1328、mean_evidence_count -0.5705 | 六项全部由 10-10 一步贡献，今日步 0.0000 （证据：`git show 65da547bd:docs/EXPERIMENTS.md`） |
| real+disabled（`retrieval_baseline_real_disabled.json`） | category_hit_at_1 -0.0064、category_hit_at_k -0.0193、category_mrr -0.0136、category_precision -0.0036、kp_hit_at_k +0.1218、kp_mrr +0.1565、mean_evidence_count -0.0641 | 今日步仅 `category_precision` +0.0001 与 `mean_evidence_count` +0.0064，其余 0.0000 （证据：`git show 65da547bd:docs/EXPERIMENTS.md`） |
| real+on 权威（`retrieval_baseline_real_rerank.json`） | category_hit_at_1 +0.0064、category_mrr +0.0032、category_precision -0.0086、kp_hit_at_k -0.0064、kp_mrr +0.0172、mean_evidence_count -0.6025 | 六项全部由 10-10 一步贡献，今日步 0.0000 （证据：`git show d54d3ded8:docs/EXPERIMENTS.md`） |

★ **10-10 那一步为什么这么大（仪器变更，不是检索改善）**：`build_index()` 的临时索引由「通用
`load → clean → split → enhance → tag`」换成**与生产同源**的 `rag.ingest_layers.build_all()`
（`ingest_layers/__init__.py:29-59`，聚合 basic→advanced→exams+practice→code→learning_paths），
`indexed_chunks` **2505 → 2026**，且 2026 与生产库 `chroma_db/chroma.sqlite3` 的
`count(embeddings)` **逐位相等**（旧仪器与生产逐集合不等，见 `ARCHITECTURE_RETRIEVAL.md` §6.3(a) 的
对照表及其「★ 2026-10-10 已修」行）。⇒ **归属警告**：§18 / §20.2 / §20.7.1 里引用旧仪器读数
（如 `kp_mrr 0.6761`、`kp_hit 0.8718`）的数字**不可与本表当代读数并列**；本表 `kp_mrr` 一步 +0.13
量级即来自此。

★ **今日步全部落在抖动带内，不得当作代码效应**：`§6.3(b)` 已实测噪声地板 ≈ ±0.003（`kp_mrr`）， （证据：`git show d54d3ded8:docs/EXPERIMENTS.md`）
本次直接复现 —— `real+off` 的 `kp_mrr` 在 10-13 21:3x 那轮抽到 **0.8282**、今日 11:58 那轮抽到 （证据：`git show d54d3ded8:docs/EXPERIMENTS.md`）
**0.8314**（差 **0.0032** = `0.5/156`，正是 §6.3(b) 归因的「单条 query top-2 互换」量级）； （证据：`git show d54d3ded8:docs/EXPERIMENTS.md`）
`fake+off` 的 `mean_evidence_count` 抽到 4.4936 / 4.5000 两值；`fake+on` 的 `kp_*` 两项差 +0.0064。 （证据：`git show d54d3ded8:docs/EXPERIMENTS.md`）
⇒ 口径：**任何单次读数都不能作为退化或改善的证据**；本表的「今日步」是抽样落点，不是趋势。

**probe_baseline 单独说明（结构不同，不进上表）**：今日重录与**同表代** `74b9eb5`（10-10 19:42）
逐条相同 —— `#4 survived` / `#9 survived` / `#17 section_dedup` / `#18 rerank_topn` /
`#19 section_dedup`，5/5 无变化。★ **不可**与 `8e2add6` 那代逐条比：`74b9eb5` 同时把探针表的
`expect_source` 从 legacy 文件（`07_查找.md` / `06_代码实现.md` / `04_文件管理.md` /
`02_数据表示与运算.md`）改指新语料（`basic/data_structure/08_search.md` 等），目标身份变了，
属仪器变更而非退化。另：本代起每条观测多一个 `rerank_scored` 键，**只有 `5df3e47` 的代码才产出它**。

**核对方式**（`check_baseline_diff_registration.py` 已把「旧代 / 新代 / 登记节」三者参数化）：

```bash
uv run python scripts/ops/check_baseline_diff_registration.py --section 20.7.3      # 本表，期望 [一致] exit 0 （证据：`git show 3ff8519f7:docs/EXPERIMENTS.md`）
uv run python scripts/ops/check_baseline_diff_registration.py --section 20.7.1      # 旧节，必然报红（见下）
```

★ 旧节 `--section 20.7.1` 报红**不是数据错**：该节登记的是「pre_task9 → 10-09 代」，而工具比的是
「pre_task9 → 现盘」，基线已两度前移 ⇒ 该节结构上不可再满足（这正是它此前被静默绕过、连红 3 天无人
发现的原因）。`8e2add6^` 时刻该命令实测为 `[一致] exit 0` —— 即 §20.7.1 在它那一代是真的。 （证据：`git show d54d3ded8:docs/EXPERIMENTS.md`）
默认节号已随本节落地而切到 `20.7.3`。




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
| **A** | **6/6** | **8/8 = 1.000** | **6/6** | 0 | **0 个** （证据：`git show 77457cc0c:docs/EXPERIMENTS.md`） |
| **B** | 1/6 | 3/11 = 0.273 | 3/6 | 0 | 7 个（`图的存储结构`/`堆`/`小根堆`/`平衡因子`/`握手定理`/`无向图的度`/`邻接矩阵`） （证据：`git show 77457cc0c:docs/EXPERIMENTS.md`） |

**Δ 词级跟随率 = +0.727**（首跑在 `f09c75642029` 下是 +0.602）。 （证据：`git show 77457cc0c:docs/EXPERIMENTS.md`）

★ **怎么读这个数**（三条边界，缺一条就是过度声称）：

1. 这**不是**同一配置的复跑：A 臂词表从 162 词变成 158 词（#8 剔 4 个课程根节点）⇒
   正确表述是「**#8 之后口径下的重测**」，不是「E-5 再跑一遍」。
2. 变好的那 1 个词正是首跑的残留自造词 `无向图`（本轮 A 臂 0 个自造词）。
   但**单条差异不外推**（纪律 #5，模型有随机性）⇒ 能出口的只有聚合值 8/8 与 6/6。
3. 「为什么剔根节点反而跟随率上升」给的是**机制推断**而非本轮实测因果：根节点本身
   canonical，模型选它也算「跟随词表」，但产出会聚成「整门课 = 一个薄弱点」的粗桶；
   候选变细后本轮全部落在细粒度考点上。要证实需另看 A 臂产出的 `node_kind` 分布。

⇒ **关闭 #8 的待办**（原记「E-5 的 0.875 属中间态，需在新 hash 下复测」）： （证据：`git show 77457cc0c:docs/EXPERIMENTS.md`）
新 hash 下 A 臂 **1.000 / 入桶 6/6 / 零自造词**，方案 A 的结论保持且更强。 （证据：`git show 77457cc0c:docs/EXPERIMENTS.md`）

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
| `phase0_baseline_final.jsonl` | 15 | **15/15 = 1.000** | 15/15（但按 #7 判**不可判**，见下） | **0** （证据：`evals/results/task_eval/phase0_baseline_final.jsonl`） |
| `phase1_baseline_v2.jsonl` | 15 | **13/13 = 1.000** | 13/13 | **2**：`grd-004`、`grd-011` （证据：`evals/results/task_eval/phase1_baseline_v2.jsonl`） |

⇒ §20.3 登记的 `verdict_agreement` 两个数**在 #11 修完解析器之后仍然成立**（不是靠旧解析器凑出来的）。
⇒ `score_tolerance` 那两行的 1.000 **仍按 #7 处置为不可判**：人工分是 `{100:8, 0:7}` 的两极分布， （证据：`evals/results/task_eval/phase1_baseline_v2.jsonl`）
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
   报告已强制披露「⚠ N 条未产出可解析分数」，本轮复核确认该披露与实际一致。 （证据：`git show ddfca01ab:docs/EXPERIMENTS.md`）

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

#### 20.8.4 #10 的正确值已补测（`--no-agent` 探针重跑）：**0.600 → 0.800 全部来自指标修复** （证据：`git show 99073e51e:docs/EXPERIMENTS.md`）

归档：`phase1_step9_probeonly_grade.jsonl` / `phase1_step9_probeonly_verify.jsonl`（各 15 条）。
★ **不是零调用** —— 检索管线自身要用 LLM 做 query 分解/HyDE，实测各 **13** 次远端 POST；
我先前把它说成「零 token」是错的，这里按实际计数登记。

**先把「指标效应」与「索引漂移」分开** —— 用**同一批 `top_items`** 分别套新旧公式：

| 任务 | 旧公式（`.get(subject, subject)`） | 新公式（`cn → network` 别名） | 其中 `cn` |
|---|---|---|---|
| grade | 9/15 = 0.600 | **12/15 = 0.800** | **0/4 → 3/4** （证据：`git show 99073e51e:docs/EXPERIMENTS.md`） |
| verify | 9/15 = 0.600 | **12/15 = 0.800** | **0/4 → 3/4** （证据：`git show 99073e51e:docs/EXPERIMENTS.md`） |

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
   词表口径一致）；代码侧**比标签新**（`category_hit` 的别名修复与 `correct_use` 单一公式都在标签后）。 （证据：`git show c8664f847:docs/EXPERIMENTS.md`）
⇒ 所以引用时必须按这张表逐份标注，**不要**笼统写成「V-2026-10-07 的结果」。
★ 顺带说明：`code_version` 只跟踪 `src/ scripts/ pyproject.toml .env.example` 的脏状态 ⇒
   文档提交不会让它 `-dirty`，这也是 `ab708e6`（含未提交的文档改动）能显示为干净 SHA 的原因。

#### 20.8.6 D8 + #24 之后重跑：**第一次拿到真正有效的配对对照**（同 case、同前置条件，只差 Store 开关）

| 归档 | `code_version` | `prompt_set_version` | 内容 |
|---|---|---|---|
| `phase1_memory_step5_store_on_step9_d8b.jsonl` | **`7304786`** | `2f485d2d7ef7` | 3 条正样本 × Store ON |
| `phase1_memory_step5_store_off_step9_d8b.jsonl` | **`7304786`** | 同上 | 同一批 × Store OFF（**本轮起 OFF 真的关掉了进程级 store**） |
| `PHASE1_MEMORY_STEP5_20261007_2334.md` | —— | —— | 该轮报告（新档，**未覆写** `..._step9_d8` 那两份） |

**逐条（`turn_log` + `episodes` + `memory_cards` 三处一致才算数）** （证据：`git show 618fbe220:docs/EXPERIMENTS.md`）

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
> ★ 数据来源全部可重跑：`PYTHONIOENCODING=utf-8 uv run python scripts/ops/s6_baseline_distribution.py`
>   （只读归档、零 LLM）；检索侧由门禁自己判（命令见该脚本末行输出）。

| §6 维度 | 冻结的占位 | Phase 0 / Phase 1 实测 | 能否照原口径回填 | **回填门槛** | 依据与必须一起说的风险 |
|---|---|---|---|---|---|
| QA | ≥80% `final_quality≥4` | 0B **13/15=0.867** · Phase 1 **14/15=0.933** | ✅ 能 | **保留 ≥80%**（分母 = 判了分的 case；未判分记 N/A） | 有区分力：11/15=0.733 即 FAIL。主失败项 `generation_incomplete`(3) 与 `retrieval_miss`(2/1) （证据：`git show 4a731a0a6:docs/EXPERIMENTS.md`） |
| Generate | ≥75% 「五项完整交付」 | 两批均 **12/15=0.80**（逐题适用项全过，#2 主指标） | ⚠️ **口径已换** | **≥75% 挂在「逐题适用项全过」**，N/A 项不进该题分母 | ★ 不得再叫「五项完整交付率」：§20.5.1 实测五项里只有 `correctness`/`coverage` 有区分力，`structure`/`answerability` 恒真、`difficulty` 是死项（严格 5/5 = **0.00**）。`coverage` 还受 **#27** 读数影响（已修，成对读数 12→1） |
| Grade | ≥75% `score_tolerance@±10` | 两极 gold ⇒ 该率判为**不可测**（`rate=None`、`degenerate_gold=true`、`n_distinct_gold=2`、`raw_rate=1.0`） | ❌ **不能** | 换 **`verdict_agreement ≥75%`**（0B 15/15、Phase 1 13/13；`n_a=2` 必须披露） | ★ 天花板要写清：实测=1.000 ⇒ 门槛 0.75 只在掉到 11/13 以下才触发，**区分力有限**；这不是"补部分分"能解决的（#7：语料 674/674 都是 2 分选择题，无部分分可标） （证据：`git show V-2026-10-08:docs/EXPERIMENTS.md`） |
| Verify | ≥80% `final_quality≥4` | 0B 仍出题 **6/15**、有真题信息 3/15；Phase 1 **0/15**、9/15（人工读数，未留 case_id） · `final_quality≥4` 两批都是 **0/15** | ❌ 原口径不能当判据（见最后一格） | **已按 D14 选① 机械化**：①**硬条件**「仍出题率 = 0」（`metrics.verify_fabricated`）；②「L1 给出可核对真题条目」**≥6/15**（Phase 1 实测 7/15 减 1 条 ⇒ 容忍 LLM 随机性，`PHASE1_VERIFY.md` 自己记过同一证据包两次 5/5 vs 4/5）；③「L1+L2 ≥9/15」作辅助披露；★ `final_quality≥4` 与 `exam_hit@k` 降级为**诊断**，ge4 不达照实写 | 为什么 ge4 不能当判据：未达成 case 全是 `exam_hit=False`（检索层没真题证据），那种情况下 agent **诚实说明无法确认是正确行为** ⇒ ge4 测的是**检索覆盖**不是回答质量（与 #7/#10 同类）。★ 机械判据是**拿两份归档逐条对过账**的：仍出题 0B 命中 `ver-001/004/008/011/013/015` = 6 条、Phase 1 **0 条**（case_id 与人工记录逐条一致）；有真题信息 0B L1=**3**、Phase 1 L1+L2=**7+2=9** ⇒ 对上人工的 3/15 与 9/15，但人工那两个数本身是**混级计数**（给出题干/题号 与 只列年份来源 混在一起）⇒ 本判据拆 L1/L2 两级。★ 读 JSON 注意：`ver_fabrication` 是**坏事率**，其 `passed` 数的是「判为仍出题」的条数。护栏 **㉖a~㉖j**（㉖j 锁「老归档无 `ver_*` 键 ⇒ 读成未测量」，防 #21 那类读不到就当零） （证据：`git show 4a731a0a6:docs/EXPERIMENTS.md`） |
| Memory | ≥80% correct-use | 0B 该率**全 N/A**（6/6；#9：0B 的 gold 里没有 `expected_memory`）；新口径下可测正样本 **n=1**（§20.8.6） | ❌ **无法按 Phase 0 回填** | **已按 D15 改为三条结构断言**（不写百分数）：①**配对成立** `metrics.paired_control_verdict` —— 只统计「两臂都满足前置条件的正样本**交集**」，ON 侧必须召回、OFF 侧必须不召回，且 **OFF 侧出现任何记忆卡一律判失败**（= #24 探测器）；交集为 0 时判**不通过**，不许把「压根没配对」印成「OFF 干净」；②**可追溯** `metrics.memory_traceable`（逐轮日志 + 记忆卡通道 + `episodes` 字段 + `store_enabled` 齐备；`episodes=[]` 是合法结果，缺字段才是没测）；③**分母摊开** `report.memory_measure_scope`（正样本总数 / valid 数 / 不可测数 / 可追溯数）⇒ 报告里任何「100%」旁边必须能看到 1/3 | ★ 为什么：n=1 上的百分数没有统计意义（答辩问「这个 100% 是几条」就崩），而 0B 那批根本没测过这个量 ⇒ 与其回填一个假门槛，不如把「能不能证明」本身门槛化。护栏 **㉗a~㉗g**；㉗g 是拿 d8b/d8/kp 三份真实归档做的**历史三情形回归**（修好后通过 / OFF 有卡被抓住 / 无交集不算通过） |
| Retrieval | 不低于 V-2026-10-02 | ③ 锚点复现：`kp_mrr 0.8048/0.8051` · `kp_hit@k 0.9103/0.9167` · `category_hit@1 0.9423` · `kp_annotated 156/156`（§20.2 末） | ✅ **已有机械实现** | **`retrieval_gate` exit 0**（各指标不低于基线，容差 **0.02**） | ★ `mean_evidence_count` 有**运行间抖动**（同一份代码连跑 3.9295 vs 3.9231）⇒ 引用它必须带上抖动，别写成三位小数稳定的量 |
| hard failure | <5% | 两份归档都是 **0/66** | ✅ 能 | **<5%**，分子 = 有 `hard_fails` 的 case，分母 = **有效 n**（排除 `case_invalid`，#6） | 现状远低于门槛；分母口径必须与 `report.failure_rate` 一致，否则两处数字对不上 （证据：`git show 4a731a0a6:docs/EXPERIMENTS.md`） |
| tool error | <5% | Phase 1 grade **2/15 = 13.3%**（`grd-004`/`grd-011`，`PHASE1_VERIFY.md` TODO-1 root cause 未确证）；整体 2/66 = 3.03%；0B 全部 0% | ⚠️ **口径决定成败** | **已按 D16 定为「任务级 <5%」**：任一任务 ≥5% 即该行不通过；分子 = `primary_failure=tool_error` 或有 `hard_fails` 的 case，分母 = 该任务的有效 n；`scripts/ops/s6_baseline_distribution.py` 末尾的 D16 段一行命令直接出每任务判定 | ★ 不用整体口径 = 不把 13.3% 说成 3%（否则「你这 <5% 怎么算的」站不住）。⇒ 当前 grade **预判不达**，#11/#12/#13 修完分数解析与 KP 透传后的真实值等 §6 整轮测 |
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
- ★ 本锚点之后新增的只有**一个只读诊断脚本** `scripts/ops/s6_baseline_distribution.py`（纯新增，
  没有改动任何既有 `src/`+`scripts/` 文件），⇒ `git diff V-2026-10-08 HEAD -- src scripts` 应只显示该文件新增。

### 22. §6 Final Gate 实测（2026-10-08 实跑 · 只填「实测 vs 门槛」，门槛一字未动）

> **数据来源**：`evals/results/task_eval/phase1_final_gate_20261008.jsonl`（66 条，全部本轮新产出，**未回写任何旧档**）
> + `evals/results/task_eval/retrieval_gate_final_20261008.log`（检索门禁本轮重跑）。
> **代码态**：`eb8112f`，且 `git diff V-2026-10-08B HEAD -- src scripts` = **0 行** ⇒ 这一跑就是锚点④的代码态。
> **门槛全部来自 §21**（定稿早于本次实跑，反循环理由见 §21 首段）。
> **调用数**（不打管道、逐端点数 POST）：`api.deepseek.com/chat/completions` **255** ·
> `dashscope/.../chat/completions` **198** ⇒ chat 合计 **453**（§21 的成本参照是 405 ⇒ **+11.9%，本轮未归因**，照实记）；
> 本地 TEI `/embeddings` **3665**（不计费）；**非 200 响应 0 条**、`env_error` 0 条。
> ★ **表外的拦路项**：本轮 66 条的 `gold_status` 全是 **draft**，报告头自己印着「含 draft，**不得出论文数字**」
> ⇒ §7.2 的表格与 §7.3 的 Final Freeze 都必须等**人工审核 gold** 之后才能出。这一步是人的动作，
> 脚本代签等于伪造审核痕迹（与「不得伪造 `human_score`」同一条纪律）。

| §6 行 | 门槛（§21 冻结） | 实测（本轮） | 判定 | 必须一起说的话 |
|---|---|---|---|---|
| QA | ≥80% `final_quality≥4`（分母 = 判了分的 case） | **14/15 = 0.933** | ✅ 达线 | 未判分 0 条 ⇒ 分母就是 15。唯一 `retrieval_miss` 是 `qa-009`（探针 `retrieval_status=empty`） （证据：`git show 4a731a0a6:docs/EXPERIMENTS.md`） |
| Generate | ≥75% 逐题「适用项全过」 | **11/15 = 0.733** | ❌ **不达**（差 1 题） | 失败项只有一个：`correctness` 0.733；`structure` / `answerability` / `coverage` 均 15/15、`difficulty` 全 N/A。★ **不是口径造成**：同字段 Phase 1 只有 1 条 False，且当时失败的 `gen-012` 本轮 5.0 通过。★ **也不是截断**：4 条都以 `来源:` 页脚正常收尾，逐条查过（先按截断假设查，被否证）。缺陷原文见 #33；同表「失败率 0.600」与本行并存 ⇒ 定义不同，亦见 #33 （证据：`git show 4a731a0a6:docs/EXPERIMENTS.md`） |
| Grade | `verdict_agreement ≥75%` | **13/15 = 0.867** | ✅ 达线 | 本轮 `n/a=0`（Phase 1 那个 n_a=2 别再引用）。两极 gold 的天花板披露不变：`score_tolerance` 仍判**不可测**（`n_distinct_gold=2`，被隐藏的 raw=0.8667）。失败两条**方向相反**：`grd-004` 给 100 而 gold 0、`grd-009` 给 0 而 gold 100 ⇒ 不是单边偏差 （证据：`git show 3fd5810cd:docs/EXPERIMENTS.md`） |
| Verify 硬条件 | 仍出题率 = 0 | **0/15**（15 条 `ver_fabricated` 全 False） | ✅ 达线 | §6 里唯一「必须为 0」的行，也正是 Verify 存在的理由；机械判据逐条命中 0 条，与人工读数一致 （证据：`git show 3fd5810cd:docs/EXPERIMENTS.md`） |
| Verify L1 | ≥6/15 | **7/15 = 0.467** | ✅ 达线 | 命中 `ver-001`/`004`/`005`/`006`/`008`/`012`/`014`（case_id 已留，可当场翻归档核对） （证据：`evals/results/task_eval/phase1_final_gate_20261008.jsonl`） |
| Verify L1+L2 | ≥9/15（辅助披露，非门槛） | **9/15**（7 + 2） | ✅ 达线 | L2 两条 `ver-011`/`ver-015` （证据：`git show 3fd5810cd:docs/EXPERIMENTS.md`） |
| Verify `final_quality≥4` | 诊断（§21 已预判不达） | **0/15** | ➖ 照实写不达 | 与 §21 的论证一致：未达成 case 是 `exam_hit=False` 下的诚实拒答 ⇒ ge4 测的是**检索覆盖**，不是回答质量 （证据：`git show 3fd5810cd:docs/EXPERIMENTS.md`） |
| Memory 断言① 配对成立 | `paired_control_verdict` 通过 | **本轮未测** —— 6 条全 `store_enabled=True`（单臂） | ➖ 引 §20.8.6 | §6 整轮不含 OFF 臂 ⇒ 配对证据只有 d8b 两份归档（其代码态早于锚点③，差异仅在评测层与护栏，prompt 未变）。★ 不把「本轮没测」写成「通过」，也不为补这一行现在去打 token：三种历史情形已由护栏 **㉗g** 拿 d8b/d8/kp 真归档做过回归 |
| Memory 断言② 可追溯 | `memory_traceable` 全真 | **6/6 = 1.000** | ✅ 达线 | 逐轮日志 + 记忆卡通道 + `episodes` 字段 + `store_enabled` 齐备（`episodes=[]` 是合法结果，缺字段才是没测） （证据：`evals/results/task_eval/phase1_final_gate_20261008.jsonl`） |
| Memory 断言③ 分母摊开 | 报告印出分母 | 印出 **正样本 3 / 前置成立 2 / 可追溯 2** | ✅ 达线 | 同段还印 `used=0.400`、`correct=0.200` —— 这两率**混极性**（负样本本就不该 used），引用必须带分母；`correct-use=0.800` 是**极性定义**下的结果（负样本按「未召回 ∧ 未误用」记通过），不是旧三元 AND（#21） （证据：`evals/results/task_eval/phase1_final_gate_20261008.jsonl`） |
| Retrieval | `retrieval_gate` exit 0（各指标不低于 V-2026-10-02，容差 0.02） | **exit 0，9 项全过**，且与 §20.2 的锚点③复现值**逐位相同**：`kp_mrr 0.8048`、`kp_hit@k 0.9103`、`category_hit@1 0.9423`、`kp_annotated 156/156` | ✅ 达线 | `mean_evidence_count=3.9231` 落在 §20.2 记过的抖动带（3.9295 vs 3.9231）⇒ 引用要带抖动。★ 口径披露：门禁把 LLM 拉回**桩**（`USE_FAKE_MODEL=True`）并关语义缓存、用独立 persist dir ⇒ 日志里成排的「结构化输出类型不符 [classify]」是桩的正常产物（分类退回规则），不是故障；这行测的是**纯检索链**、不含 LLM 查询改写，基线也在同一套桩下产出 ⇒ 可比 |
| hard failure | <5%（分母 = 有效 n） | **0/66**（有效 n=65） | ✅ 达线 | 分子 = 有 `hard_fails` 的 case，本轮一条都没有 （证据：`git show 4a731a0a6:docs/EXPERIMENTS.md`） |
| tool error | 任务级 <5%（D16） | **五任务全 0.000** | ✅ 达线 | §21 预判的 grade 13.3% **未复现**；但那两条换了形态、且落在同两个 case ⇒ 见 #32（定性从「偶发」变「case-specific」，根因仍未确证） （证据：`evals/results/task_eval/phase1_final_gate_20261008.jsonl`） |
| provenance | ③ 之后每条 100% 带 5 个字段 | `code_version` / `prompt_set_version` / `retrieval_cfg` / `top_items` / `turn_log` **键存在 66/66、非 None 66/66** | ✅ 达线 | ★ 「值为空」≠「缺字段」：`top_items=[]` 是 `qa-009`/`mem-005` 两条**真实空检索**的结果（`retrieval_status=empty`）；`turn_log=[]` 是单轮任务的合法空值，6 条 memory 各带 2~3 轮。本轮 `prompt_set_version=2f485d2d7ef7`、`code_version=eb8112f` （证据：`git show 3fd5810cd:docs/EXPERIMENTS.md`） |
| Docker / TEI | manual：`docker compose up -d` → 预检返回空 | 跑前预检通过（0 条 `env_error`、非 200 响应 0） | ✅（人工项） | 答辩现场要能一键起；半死 TEI 由 ㉑a / ㉑h 拦在开跑前 |
| 四任务链 | manual：qa / generate / grade / verify 各 1 条 + memory 跨会话 | 五任务全量跑完（各 15/15、memory 6/6）；跨会话实物见 §20.8.6 的 `mem-002` | ✅（人工项） | 演示要能当场指出记忆卡（`MEMORY_CARD_MESSAGE_ID`），否则「有记忆」不可证 |

#### 三个预判 vs 实测（这一节值得记的地方在于：预判可以被推翻）

| §21 的预判 | 实测 | 结果 |
|---|---|---|
| Verify 的 `final_quality≥4` 不达 | 0/15 | ✅ 判对 |
| grade 的任务级 tool error 13.3% 不达 | 本轮 0.000（同两条 case 换了措辞，见 #32） | ❌ 判错 （证据：`evals/results/task_eval/phase1_final_gate_20261008.jsonl`） |
| Generate 达线（历史两批均 12/15 = 0.80） | 11/15 = 0.733，唯一不达的门槛行 | ❌ 漏判 （证据：`git show 3fd5810cd:docs/EXPERIMENTS.md`） |

⇒ **16 行：13 行达线 / 1 行不达（Generate）/ 1 行诊断性不达（Verify ge4，本就不当判据）/ 1 行本轮未测（Memory 配对）**（★ Generate 那一行在 ⑤ 之后单任务复测已到线，见 §22.1 —— 本节记的是 §6 整轮当时在 ④ 上的读数，不回填改写）； （证据：`git show 3fd5810cd:docs/EXPERIMENTS.md`）
再叠加表外那条 **gold 全 draft**，就是 §7.2 与 §7.3 之前剩下的全部工作。

#### 22.1 锚点 ⑤ 的 generate-only 复测（2026-10-08，**87 次 chat 调用**）

> **为什么单跑一个任务**：⑤ 只动了**出题**那条链（`git diff V-2026-10-08C HEAD -- src` = **0 行** ⇒ 复测就在 ⑤ 的代码态上），
> 其余四任务的 agent 行为不可能因此变 ⇒ 全量重跑留给 §7.3 Freeze。比较是**逐题对账**，不是只比均值。

| 项 | §6（④ `2f485d2d7ef7`） | ⑤（`12abf293c62a`） | 变化 |
|---|---|---|---|
| 主指标 逐题适用项全过 | 11/15 = 0.733 ❌ | **13/15 = 0.867** | **过门槛 ≥0.75** （证据：`git show 762a85468:docs/EXPERIMENTS.md`） |
| `correctness`（`fq≥4`） | 11/15 | 13/15 | +2 |
| `structure` / `answerability` | 15/15 · 15/15 | 14/15 · 14/15 | −1（`gen-009` 正文丢失，见 #35） |
| 平均 `final_quality` | 3.933 | 4.400 | +0.467 （证据：`git show 762a85468:docs/EXPERIMENTS.md`） |
| 回归（过 → 不过）的题 | — | **0 条** | ★ 没有任何一题变差 |

**#33 举证的那 4 条，逐条下落**（这才是「修没修上」的证据，不看均值）：

| case | 当时举证的缺陷 | ⑤ 的结果 |
|---|---|---|
| `gen-003` | 答案第 (4) 问同时写「共 1001 个序号」与「=602？」再改口 | ✅ `fq 2 → 5`、`correctness False → True` |
| `gen-007` | 标准答案说「能聚合为 /22」、解析说「三者不能合并为单个 CIDR 块」 | ✅ `fq 2 → 5`、`correctness False → True`（解析改成「/23 + 12 单独保留」） |
| `gen-009` | 标准答案里留着「= 3.2？——若按理想流水则 S → k = 4」 | ❌ **换了失败形态**：回复只剩页脚 42 字符、题目正文整个丢失（`generation_ok=False`）⇒ 新偏离 **#35**，不是原来那个缺陷 |
| `gen-010` | 推导中途自我改写（「地址 8：4」后接「→ 实际为 8」） | ❌ 仍 `fq 2.0`，但这次是**算错/漏键**：7 个关键字的散列表只填了 6 个（缺 `41`）⇒ 不是自相矛盾，**prompt 修不到它** |

★ **能说的与不能说的**：支持因果的是「**恰好是我举证自相矛盾的那两条翻成通过**、且 0 条回归」；
**不能**说「修复带来 +0.134 的净提升」—— n=15 的单批读数自带抖动（#33 记过同一字段在 Phase 1 与 §6 之间 1↔4 的翻转； （证据：`evals/results/task_eval/phase1_final_gate_20261008.jsonl`）
本轮 `gen-004`/`gen-005`/`gen-011` 的 `primary_failure` 也在 `none` 与 `generation_incomplete` 之间来回，
而三题 `fq` 都在 4~5、五项判定未变）。⇒ 论文里写「⑤ 之后 generate-only 复测 13/15，
自相矛盾那一类在逐条对账中消失」，**不写**「修复使指标提升了 X」。
★ 并且「过线」只是**冻结判据下的过线**：手验 5 道里 `gen-001` 客观算错却被判 5.0（见下方同日补与 **#36**）⇒ `final_quality` 不重算算术。

#### 引用这一节时的三条硬约束

1. **门槛没有因为结果动过**：§21 定稿于实跑之前（反循环条款见 §21 首段），本节只填实测；Generate 不达就写不达，
   不回头把 0.75 调成 0.70。
2. **本轮数字全部出自 draft gold** ⇒ 在 gold 转 `reviewed` 之前，论文表格不得直接引用 §22 的数字，
   只能引用「已复核的历史值 + 本节达不达成的判定」。
3. **不覆写旧档**：`phase1_final_gate_20261008.jsonl` 是新增；0B / Phase 1 / d8b 各归档保持原样，
   历史数字按当时读数引用（#27/D12 的成对读数另见 §20.5.1）。

##### ★ 同日补：我自己手验 5 道题的算术，**其中 1 道是 judge 判满分而答案客观错**

被追问「复测有没有造假」之后，才去做该先做的事：**不看分数，自己重算**。

| 手验（零 token，逐题推算） | 结论 |
|---|---|
| `gen-001` Cache 4 路组相联（32 KB / 32 B 块 / 32 位地址） | ✗ **客观错**：块内 5 位、组号 8 位、标记 19 位都对，但地址 `0x1A5C = 6748` 的组号应是 `(6748 >> 5) mod 256 = **210**`，答案写 **46**（它把「接着的 8 位」读成了 `0010 1110`）⇒ **judge 给了 5.0** |
| `gen-006` Kruskal + Prim | ✓ 边序与总权 15 重推一遍，一致 （证据：`git show 46bb810e5:docs/EXPERIMENTS.md`） |
| `gen-003` TCP 序号/确认号 | ✓ `ack=1001`、第三段 `seq=1001 / ack=3001`、500 B 占 1001~1500 ⇒ `ack=1501`，全对且答案键与解析同结论 |
| `gen-007` 子网划分 + 路由聚合 | ✓ 借 2 位 → `/26`、4 个子网、62 可用、`.1~.62`、广播 `.63`；0~3 四个 `/24` 聚合成 `/22` 的判据也对 |
| `gen-010` 散列 ASL | ✗ 客观错（表里缺 `41`；我算的是 `0:22 1:1 2:46 3:13 8:41 9:53 10:30`、ASL成功 `10/7≈1.43`、ASL失败 `39/11≈3.55`）⇒ 判 2.0 **站得住** |

⇒ **「13/15 = 0.867 过线」的准确含义**：在**冻结判据**（`correctness = final_quality ≥ 4`）下过线， （证据：`git show V-2026-10-08C:docs/EXPERIMENTS.md`）
**不是**「13 道题都算对」。5 道里 2 道有客观错误、其中 1 道被判满分 ⇒ judge 对**计算错误**不敏感
（整洁、口径统一的答案反而容易拿高分），登记为 **#36**。
⇒ 对 #33 修复效果的表述随之**收窄**：能说的只有「我举证的那两种文本形态（答案键里留问号、答案与解析互相打脸）
在这一批 15 道里都没再出现」；**不能说**「出题质量提升到 0.867」。 （证据：`git show V-2026-10-08C:docs/EXPERIMENTS.md`）
⇒ ★ 方法上的教训（写给自己）：**验一个数之前先重算它，而不是先复算它的算术过程。**
上一轮我做了三条路径的复算（手工 AND / `metrics.rate` / `report.json`）就认为「可信」，
那三只验证了**读数**，一只也没验证**质量**。

---

### 20.7.4 黄金集修复后的基线**三代**重录登记（2026-10-14 晚，禁止静默重录 ⇒ 逐条登记）

> 触发原因：`evals/datasets/golden/sample_408.jsonl` **修订**（详见 `evals/datasets/golden/README.md`）——
> ① 4 处 KP 假阴性标注（`输入输出管理`×2→`输入输出系统`、`磁盘调度`→`文件管理`、
> `操作系统概述`→`计算机系统概述`，修复前这 4 条 `kp_hit@k` 恒 0）；② 前 40 条补
> `query_type: concept`（不改任何判定，只统一同题标注）。
> `provenance.golden_sha256` 由 `be98912a` 变为 `783e78ff` ⇒ 六条路由基线同批重录。
> 口径与 `scripts/ops/check_baseline_diff_registration.py` 逐字一致（`round(new−old,4)`，非零即登记义务）。 （证据：`git show d54d3ded8:docs/EXPERIMENTS.md`）

下表列的是 **pre_task9 → 三代** 的全部非零 diff（机械核对脚本的比对对象）：

| 路由（基线文件） | pre_task9 → 三代的全部非零 diff | 归因拆解（§20.7.3 的量 + 本次黄金集修复） |
|---|---|---|
| fake+off（`retrieval_baseline.json`） | category_hit_at_1 -0.0192、category_hit_at_k +0.0065、category_mrr -0.0040、category_precision -0.0049、kp_hit_at_k +0.0833、kp_mrr +0.1476、mean_evidence_count -0.4936 | §20.7.3 记的量 + 修复增量（`kp_hit_at_k` +0.0256 = 4/156，4 条修复标注**全部**命中；`kp_mrr` +0.0133）。`category_mrr` 的 -0.0016 与 `category_precision` 的 -0.0015 是 §6.3(b) 抖动带内的复跑噪声——黄金集修复**机械上不可能**触碰 category 判定（只改 KP 标注与 query_type 标注，`load_golden_queries` 的 category 分支不变），按 §20.7.3 既定口径「抖动带内不得当作代码效应」登记 （证据：`git show 65da547bd:docs/EXPERIMENTS.md`） |
| fake+on（`retrieval_baseline_rerank.json`） | category_hit_at_1 -0.0064、category_hit_at_k -0.0064、category_mrr -0.0064、category_precision -0.0182、kp_hit_at_k -0.0065、kp_mrr -0.0328、mean_evidence_count -1.1025 | §20.7.3 记的量 + 修复增量（`kp_hit_at_k` +0.0192 = 3/156；`kp_mrr` +0.0128）；category 四项与 §20.7.3 **逐位相同**（本路由复跑确定性好，无新增抖动） （证据：`git show 65da547bd:docs/EXPERIMENTS.md`） |
| fake+disabled（`retrieval_baseline_fake_disabled.json`） | category_hit_at_1 -0.0449、category_mrr -0.0241、category_precision +0.0067、kp_hit_at_k +0.1474、kp_mrr +0.1724、mean_evidence_count -0.0320 | §20.7.3 记的量 + 修复增量（`kp_hit_at_k` +0.0192 = 3/156；`kp_mrr` +0.0123）。`category_mrr` 的 +0.0005 为抖动带内噪声（同上口径） （证据：`git show 65da547bd:docs/EXPERIMENTS.md`） |
| real+off（`retrieval_baseline_real_embed.json`） | category_hit_at_1 -0.0128、category_hit_at_k -0.0064、category_mrr -0.0099、category_precision -0.0079、kp_hit_at_k +0.0577、kp_mrr +0.1488、mean_evidence_count -0.5705 | §20.7.3 记的量 + 修复增量（`kp_hit_at_k` +0.0192 = 3/156；`kp_mrr` +0.0160）。`category_precision` 的 -0.0014 为抖动带内噪声（同上口径） （证据：`git show 65da547bd:docs/EXPERIMENTS.md`） |
| real+on 权威（`retrieval_baseline_real_rerank.json`） | category_hit_at_1 +0.0064、category_mrr +0.0032、category_precision -0.0086、kp_hit_at_k +0.0192、kp_mrr +0.0429、mean_evidence_count -0.6025 | §20.7.3 记的量 + 修复增量（`kp_hit_at_k` +0.0192 = 3/156；`kp_mrr` +0.0257）；category 三项与 §20.7.3 **逐位相同** （证据：`git show d54d3ded8:docs/EXPERIMENTS.md`） |
| real+disabled（`retrieval_baseline_real_disabled.json`） | category_hit_at_1 -0.0064、category_hit_at_k -0.0193、category_mrr -0.0136、category_precision -0.0036、kp_hit_at_k +0.1410、kp_mrr +0.1757、mean_evidence_count -0.0641 | §20.7.3 记的量 + 修复增量（`kp_hit_at_k` +0.0192 = 3/156；`kp_mrr` +0.0192）；category 四项与 §20.7.3 **逐位相同** （证据：`git show 65da547bd:docs/EXPERIMENTS.md`） |

★ **修复增量的形态印证了审计结论**：6 条路由的 `kp_hit_at_k` 增量全部是 `±0.0192`（=3/156）或其整数倍 （证据：`git show 05a3767c3:docs/EXPERIMENTS.md`）
（fake+off 为 `+0.0256`=4/156）——正是「4 条假阴性标注变为可命中、其中 3 条在各路由均能检索到正确章、 （证据：`git show 05a3767c3:docs/EXPERIMENTS.md`）
fake+off 路由 4 条全中」的量化形态。若增量不是 1/156 的整数倍，反而要怀疑归因。
★ 第 4 条（`磁盘调度`→`文件管理`）在真实路由上未稳定命中：内容确在 `file_disk` 章，但语义检索
在该 query 上仍返回他科证据（与 default 路由「首条未命中」清单里该 query 的 category 级未命中
是同一现象的两个刻度）——这是**检索质量问题的新测面**，不是标注问题，留待检索侧处理。

**probe_baseline 与 policy_layer_evidence_baseline 未动**：探针表（`retrieval_probes.jsonl`）与
策略层证据集不在本次修订范围，两份基线维持二代值。

复现（按路由，均带 `--update-baseline` 执行；执行前默认路由先不带该开关跑一遍看 diff）::

    # fake+off（CI 默认）
    PYTHONPATH=src python -m evaluation.gates.retrieval_gate --update-baseline
    # fake+on / fake+disabled
    GATE_RERANK_MODE=on        PYTHONPATH=src python -m evaluation.gates.retrieval_gate --update-baseline
    GATE_RERANK_MODE=disabled  PYTHONPATH=src python -m evaluation.gates.retrieval_gate --update-baseline
    # real+off / real+on（权威，需 GATE_USE_REAL_RERANK=1）/ real+disabled（需 TEI 在线）
    GATE_USE_REAL_EMBEDDING=1                                    PYTHONPATH=src python -m evaluation.gates.retrieval_gate --update-baseline
    GATE_USE_REAL_EMBEDDING=1 GATE_RERANK_MODE=on GATE_USE_REAL_RERANK=1 PYTHONPATH=src python -m evaluation.gates.retrieval_gate --update-baseline
    GATE_USE_REAL_EMBEDDING=1 GATE_RERANK_MODE=disabled          PYTHONPATH=src python -m evaluation.gates.retrieval_gate --update-baseline

### 20.7.5 A2 盲标 gold 回填 + `ec_r2` 新代归档登记（2026-10-15，禁止静默重录 ⇒ 逐条登记）

**① 盲标与回填（A2，人工动作的机械收尾）**

- 15 题人工盲标由用户于 2026-10-15 完成并入仓：`evals/results/task_eval/GEN_GOLD_BLINDLABEL_20261015_filled.md`
  （sha256 = Downloads 原件的同一值 `d5b1500fbf5b…`；复现：`sha256sum` 对两路径比对；工作单原文另见 `GEN_GOLD_BLINDLABEL_20261015.md`）。
  结果：**13 条 present + gen-005 `incomplete_source`（选择题选项缺失，第 1 小题已独立算出）+ gen-009 `missing_key`
  （归档 `generation_ok=false`、`format_violation/generation_incomplete`，无题干不得臆造）**。
- 回填落点 `evals/datasets/demo/generate_cases.jsonl`：`gold_answer` / `expected_difficulty` / `gold_source_ref` /
  `gold_answer_status` 四件套按盲标表机械填写（`gold_status` 13 条 draft→reviewed，gen-005/009 保持 draft；
  行尾 LF 风格未变，`git diff` 仅 15 个数据行）。
- `task_eval sanity` **ERROR 0**（复现：`python -m evaluation.task_eval sanity`）；PENDING 1 = `grade.human_score`
  两极分布的**集合级存量项**，与回填前同一状态（`gold_sanity.sanity_for_demo` 直读 `report.pendings` 可证，仅一条 `<dataset>` 级）。
- 盲态与措辞披露随档留痕（`needs_review` / `notes`）：gen-001~005 定位 gen-009 缺题时暴露过系统答案 ⇒ 五条均挂
  「需第二标注者复核」；gen-001 人类独立算得组索引 210 ≠ 系统答案 46（judge 曾判 5.0 的错，见 #36）；
  gen-012 题面「第 3 个逻辑块」歧义、gen-014 相等孩子平手规则未指定，均入 notes。

**② 为什么 `ec_r2` 的 gen 记录取自 anchor5（不是 ec_r1）**

盲标的题干来自**出题修复后锚点⑤复测归档** `evals/results/task_eval/phase1_gen_anchor5_20261008.jsonl`
（`code_version=6610ef1`、`prompt_set_version=12abf293c62a`，#33 修复态，PROMPT_SET_VERSION 由此变更见 §20.0 锚点⑤）。
`ec_r1_final_gate.jsonl` 的 15 条 gen 是**修复前** §6 整轮（`code_version=eb8112f`、`prompt_set_version=2f485d2d7ef7`）。
实测同 case_id **题干不同**：gen-001 修复前问「直接映射 + 4 路组相联 + 冲突趋势」三问、修复后只问「4 路组相联 + 组索引 0x1A5C」；
gen-009 修复前有完整题干（五项全过，见 #35）、修复后只回 42 字符页脚。
⇒ 把盲标 gold 挂到修复前记录 = **假 gold**（正是 P−1 明令禁止的「拿另一题的答案充当本题 gold」）⇒ 新归档 gen 记录整体取自 anchor5。

新代归档两条腿（复现命令见本节末）：`scripts/lib/gold_blindlabel_apply_20261015.py` 只做「gen 记录取自 anchor5 +
gold 快照注入（走 `load_demo`+`asdict`，与 runner 落盘同一条代码路径）+ 其余 51 条从 ec_r1 逐字节继承」，
判据数值一律不手写，交 `task_eval backfill`（唯一合法写回入口）重算；
运行期 provenance（`code_version` / `prompt_set_version` / `golden_sha256` / 顶层 `gold_status` / `date` / `judge`）**不动**——
本归档是「重算式新一代」而非重跑产物，与现行 gold 的最终对齐由 C1 全量重跑完成（HANDOVER：V0 通过含 P−1 已填 gold 之后才允许全量重跑）。
混合代际在 ledger 里**可见**：provenance 注记显示 `code_version=6610ef1,eb8112f`，provenance_match 仍 0/66（事实，非退化）。

**③ ledger 重建与三段 check**（复现：`build_claim_ledger.py --records evals/results/task_eval/ec_r2_final_gate_20261015.jsonl --check`）

- 第 1 段 **PASS**（ledger 文档 == 重算；复现：`build_claim_ledger.py --records evals/results/task_eval/ec_r2_final_gate_20261015.jsonl --check`）。
- 第 3 段 V0 ①：改动前 4 组 × 15 处 = 60 处缺键（`gold.gold_answer_status` 与 `gold.gold_source_ref.gold_answer`
  × 判据 gen_answerability / gen_correctness）**清零** ⇒ PASS（gen 记录 gold 快照现带两键，`has_path` 键存在性满足）。
- 第 3 段 V0 ②：`generate/gen_answerability` + `generate/gen_correctness` 仍全 missing_premise ⇒ **FAIL（预期红）**，
  根因见 ④——不是 gold 未填，也不是 ledger 算错。
- 第 2 段：孤立结论行号集与改动前同一集合（无新增；口径见 `_ledger_common.py` 的 `_ORPHAN_RE`/`_SOURCED_RE`）。
- Generate 行读数变化（口径必须连读）：由 `N/A（rate=None；已测 n=0, missing_premise=15）` 变为
  `0.000（已测 n=1, missing_premise=14, not_applicable=0）`（复现：`build_claim_ledger.py --records evals/results/task_eval/ec_r2_final_gate_20261015.jsonl`）——
  唯一已测条是 gen-009（`generation_ok=false` ⇒ `gen_structure=False` ⇒ 复合 fail），其余 14 条复合被 required 项
  missing_premise 毒化。**0.000 不是「15 条里 0 条五项齐全」**；§22 的 0.733（§6 整轮、judge 口径）与本行（复现：）
  （机械复合口径）定义不同，禁止混读。

**④ V0 ② 剩余红的三条根因（逐条可举证，都不是「gold 未填」）**

1. `gen_answerability`：判据设计要求**人工可判定性结论**——`predicates/generate.py::_answerability` 末分支在
   `present` 状态下仍返回 `missing_premise`（P−1 通道的可读判定尚未产出）。清偿路径：P−1 批 2/3 落人工判定，
   或整族按 §8 披露为 limitation。
2. `gen_correctness`：`_is_pure_mcq` 守卫——15 条回复全是「综合应用+选择+填空」混合卷（`_MULTI_PART_MARK` 命中），
   机械判据适用域收缩到「真纯选择题」；用户盲标 gold 是多小问复合文本，本就不可单键机械比对。**诚实不可测 ≠ 不合格。**
3. `gen_difficulty`（optional 诊断位）：**新发现（冻结清单 B6，待 owner 裁定）**——`metrics.difficulty_of` 经
   `_DIFFICULTY_LINE` 从回复抽**中文**档名（基本/基础/简单/中等/适中/较难/困难），而
   `_metrics_common._DIFFICULTY_MAP` 只映射**英文**（basic/easy/medium/mid/hard/difficult）⇒ 实际侧恒 `None`
   ⇒ 结构性 missing_premise。`metrics.py` docstring 声称「`:664` 已负责把中文档名映射到 1–5」与代码不符
   （函数已拆至 `_metrics_common.py`、映射表无中文项）——又一处文档/代码漂移的实证。
   补中文映射 = **判据口径变更**（missing_premise → pass/fail：如「基础」→1 对人工标「medium」→3 超 ±1 容差会翻 fail），
   按冻结判据纪律必须 owner 裁定并登记新旧两侧数字，本次**不擅改**。

**⑤ `artifact_status.json` 与 ledger boilerplate 订正**

- `ec_r1_final_gate.jsonl`：active → superseded（by `ec_r2_final_gate_20261015.jsonl`，reason=`gold_blindlabel_backfill_gen_from_anchor5`）。
- `phase1_gen_anchor5_20261008.jsonl`：`superseded_by` 由 ec_r1 **订正为 ec_r2**——原指针不承接 anchor5 的 gen 记录
  （ec_r1 的 gen 为修复前回复），随本次登记改正并在 reason 留痕。
- 新增两条：`ec_r2_goldinjected_20261015.jsonl`（superseded：gold 注入中间件，判据仍是旧值）与
  `ec_r2_final_gate_20261015.jsonl`（active：ledger 现行证据源）。
- `build_claim_ledger.py` / `_ledger_rows.py` 四处「P−1 盲标暂停中 / gold 未盲标 / 盲标未做」说明文本订正为现行事实
  （只改解释文本、不动任何判定，B3 同型处理；V0 ② 注记现指引读者看逐判据缺前提明细）。

全链复现（零 token，按序执行）::

    PYTHONIOENCODING=utf-8 PYTHONPATH=src .venv/Scripts/python.exe scripts/lib/gold_blindlabel_apply_20261015.py
    PYTHONIOENCODING=utf-8 PYTHONPATH=src .venv/Scripts/python.exe -m evaluation.task_eval sanity
    PYTHONIOENCODING=utf-8 PYTHONPATH=src .venv/Scripts/python.exe -m evaluation.task_eval backfill --records evals/results/task_eval/ec_r2_goldinjected_20261015.jsonl --out evals/results/task_eval/ec_r2_final_gate_20261015.jsonl
    PYTHONIOENCODING=utf-8 PYTHONPATH=src .venv/Scripts/python.exe scripts/lib/build_claim_ledger.py --records evals/results/task_eval/ec_r2_final_gate_20261015.jsonl --out evals/claims/ledger.md
    PYTHONIOENCODING=utf-8 PYTHONPATH=src .venv/Scripts/python.exe scripts/lib/build_claim_ledger.py --records evals/results/task_eval/ec_r2_final_gate_20261015.jsonl --check

### 20.7.6 owner 裁定执行登记（2026-10-15：B1~B6 / V0② / A1 / A3 / A4 七项裁定的机械落地）

> 输入：owner 就冻结清单七项待裁事项的书面裁定表（本表「裁定」列即其原文口径）。
> 执行原则：先机械核实裁定中的可验证事实（四条全部实测），再按裁定落地；凡属口径变更的一律登记新旧两侧。
> **复跑证据**：`pytest` 26/26（新增 7 项极性回归）· `ruff check src/` 全绿 · 默认路由检索门禁 exit 0（复现：`pytest -q` · `ruff check src/` · 默认路由门禁，命令见冻结清单 §0）
> `task_eval sanity` ERROR 0 · ledger `--check` 第 1 段 PASS / V0 ① 缺键 0 处 PASS / V0 ② 维持预期红（见 ④）。

**① B2 第三路：改 backfill 落盘口径（owner 否决原二选项，实测确认其判断成立）**

- **定性订正（owner：「过期字段」定性不准——实测比这更严重）**：`ver_fabricated` 等的分歧不是
  「某字段随时间过期」，而是**同名字段有两个写入方、极性相反**：
  · `runner.py` 直写 **metric 极性**（`verify_fabricated` 返 True = 仍出题 = 坏事）——phase1 代归档；
  · `cli._backfill` 按 registry 落 **verdict 极性**（`to_record_value("pass")=True` = 好事）——ec 代归档。
  实测：现行 registry 对三份归档的重算均为 **pass 15/15**，与 ec_r1/ec_r2 存储值**逐位一致**（复现：用 `registry.for_task("verify")` 对 phase1/ec_r1/ec_r2 三归档逐条重算，与存储字段比对），
  与 phase1（metric 极性 False 15/15）语义一致但数值相反。⇒ **选项①「从权威归档重新 backfill 出 ec_r1 v2」（复现：对 phase1 重跑 `task_eval backfill`，与 ec_r2 存储值逐字段比对，幂等）
  实测修不了**：重跑是幂等的，产出与现值相同（owner 判断属实）。
- **ec_r2（active 归档）同病（owner 判断属实）**：ec_r2 的 51 条非 gen 记录逐字节继承 ec_r1，
  verify 15 条 `ver_fabricated` 全 True（verdict 极性）。
- **已实现的假红（不止是风险）**：ec_r1 / ec_r2 的 `.report.json` 边车（backfill 每次运行即生成）
  `ver_fabrication = 1.000`（passed 15）——按 §6「仍出题率必须 0」读即「100% 编造」（证据：ec_r1 / ec_r2 的 `*.report.json` 边车，重生前版本见 git 工作树）；
  实情为 0/15。ledger 不受影响（`_pred_verdict_blocks` 用 `p.fn(r)` 实时重算，不读存储字段）。
- **修复（三处 + 一边车 + 回归测试）**：
  · `runner.py`：verify 三判据改由 **registry 判据**落盘（公式仍只 registry 一处）+ 同写
    `item_reasons` 标记 ⇒ runner 与 backfill 同源同极性，两个写入方的极性冲突从源头消除；
  · `report.py`：新增 `_fabrication_flag()`——凭 `item_reasons[<判据名>]` 存在性无歧义解码
    （backfill 恒写、旧 runner 不写）；`ver_fabrication` 改走坏事率解码；另两个判据
    （`ver_item_cited`/`ver_year_only`）两种极性同向（True=好事）无需解码；
  · `cli._backfill`：写入前与已存值比对，**不一致显式记账**（WARNING 汇总，不再静默覆盖）（证据：`src/evaluation/task_eval/cli.py` `_backfill`；回归 `test_backfill_overrides_are_logged_not_silent`）——
    历史上极性相反的覆盖正是无声通过的；
  · `_runner_record.py`：字段注释补极性/代际解码说明；
  · `evals/results/task_eval/ec_r2_final_gate_20261015.report.json` **按修复后代码重生**
    （派生件；归档 jsonl 一字节未动）：`ver_fabrication` **1.000 → 0.000**（硬条件正确呈现）（复现：`build_report` 重生边车后读 `ver_fabrication.rate`；证据：`ec_r2_final_gate_20261015.report.json`），
    另两个好事率不变（0.4667 / 0.1333）（证据：同一边车的 `ver_item_cited` / `ver_year_only` 字段）；
  · `tests/test_verify_fabrication_polarity.py`（7 项）：两侧极性解码、缺前提出分母、
    runner 与 backfill 写出一致性、backfill 覆盖记账、ec_r2 边车实证锚点（复现：`pytest -q` 全绿；测试文件 `tests/test_verify_fabrication_polarity.py`）。
- **telemetry schema 不动**：`_emit_evidence_metric` 的 `use_llm_verify` / `max_retries` /
  `retry_count` 字段保留（默认 False/0），历史日志仍可解析；仅 retriever 入口的传参删除。

**② B5 死代码三项（owner：asearch_episodes 登记 / verifier LLM 层删 / `_sse` 过滤带披露保留）**

- `asearch_episodes`：实测已不在 `src/`（早前事实上已删）⇒ 按裁定**登记即闭**。
- **verifier LLM 校验层：整层删除**（删除前全调用点恒 `use_llm=False`，从未启用）：
  · `rag/retrieval/verifier.py`：删 `_arun_llm_relevance_check`、`averify_evidence` 的 `use_llm`
    开关与分支、`_CHECK_WEIGHTS` 的 `llm_relevance` 项及其「未执行时重分配」逻辑、
    `RELEVANCE_PROMPT` / `call_text` 导入与模块 docstring 的 LLM 层表述；
  · `rag/retrieval/retriever_retry.py`：删 `_llm_verify`（use_llm=True 专用）与
    `_apply_retry_hints`（重试 hints 落地，仅 LLM verify 路径消费）；
  · `rag/retrieval/retriever.py`：删 `_verify_with_optional_retry`；`_finalize_evidence` 收敛为
    默认路径（规则 verdict 透出，不再二次 verify / 不 retry）；`aretrieve_evidence_with_retry`
    移除 `max_retries` / `use_llm_verify` 形参；
  · 五个调用点同步去参（`agents/tools.py`、`retrieval_gate/_gate.py`、`ragas/adapters.py`、
    `diagnostics/_stage_trace_core.py`、`task_eval/retrieval_probe.py`）；
    `retriever_io._verify_fused` 去 `use_llm=False`。
- **函数名 `aretrieve_evidence_with_retry` 是历史误称**（已无 retry 语义）：保留不改名是避免六处
  调用锚点与文档连带改写，**登记为冻结后清理项**（走 EFFECT_PLAN §6 新版本流程，类似 `_sse` 的
  带披露保留模式）。
- 删除后回归：pytest 26/26、ruff `src/` 全绿、默认路由检索门禁 exit 0（假 embedding）（复现：`pytest -q` · `ruff check src/` · 默认路由 `retrieval_gate`）。

**③ B6 `gen_difficulty` 中文难度行（owner：暂行登记选项② + 修 docstring；选项①后果非唯一）**

- **docstring 漂移已修**（`metrics.difficulty_of`）：原声称「`_as_difficulty()`（:664）已负责把中文
  档名映射到 1–5」三重不实——① 该函数已拆至 `_metrics_common.py`（metrics.py 无 :664）；
  ② `_DIFFICULTY_MAP` 只有英文项（basic/easy/medium/mid/hard/difficult），无任何中文档名；
  ③ 实测本批 15 条 gen 回复抽到的档名是 **「理解」**（14/15；另 1 条无难度行）——认知层次动词，
  既不在 `_DIFFICULTY_LINE` 抽取词表、也不在任何映射表中。
- **选项①（补映射）为何不可机械执行（支撑 owner「后果非唯一」判断的实测）**：补映射须**同时**定
  ①抽取词表是否纳入「理解」、②中文→1–5 映射取法、③容差口径。按 gold 分布实测
  （basic 1 / medium 10 / hard 3 / 缺 1，14 条实际侧均为「理解」）：
  「理解→3 + ±1 容差」读 **1.000**、「理解→3 + 精确匹配」读 **0.714**（复现：对 `generate_cases.jsonl` 的 14 条 gold 难度分布在两种映射/容差取法下重算 `difficulty_match`）、
  只补映射表不扩词表则实际侧恒 None ⇒ 可测率 **0.000**。三种读法全部来自同一份数据 ⇒ 纯口径裁决（证据：`difficulty_of` 对 15 条回复的抽取结果——14 条抽到「理解」，不在 `_DIFFICULTY_LINE` 词表内），
  不是机械修复。按裁定**暂不补**，判据现状登记为「机械判据适用域不含中文难度行」；
  `gen_difficulty` 是 optional 诊断位（query 0/15 提难度），不进复合主指标，不影响 Generate 门槛行。
  补法待 C 段后按 EFFECT_PLAN §6 走「新版本 + 全量重跑 + 门禁重录」。

**④ V0 ② 硬门槛：走 option B（limitation 披露；owner 指出 option A 按现行契约清偿不了）**

- **机制实测**（支撑 owner 判断）：`gen_answerability` 即便 gold 四件套齐全（A2 后 13 present）
  仍返回 `missing_premise`——它的真实输入是「**P−1 人工可判定性结论**」，该标注通道从未开工、
  归档里也没有这个字段（`predicates/generate.py:_answerability` 前提链末分支）。
  `gen_correctness` 同理依赖 gold 答案正确性的人工结论通道。⇒ **option A（批 2/3 产出人工可读判定）
  在现行契约下清偿不了 V0 ②**：缺的不是标注劳动，是判据设计里就没有这个输入的落点。
- **owner 裁定：option B**——Generate 行（`gen_answerability` / `gen_correctness` 全
  missing_premise）在效果章按 **limitation 披露**：写明「这两个判据在现行契约下不可机械清偿，
  相应门槛行不进入『已证明』栏，论文引用必须带本披露」；**不得**把 missing_premise 当成绩、
  也不为凑读数临时改契约。ledger Generate 行现值（`0.000（已测 n=1, mp=14）`）即该披露的（复现：`build_claim_ledger.py --records ec_r2_final_gate_20261015.jsonl --check`；ledger.md#Generate 行）
  机读形态，E 段宣布判据相应项改为「limitation 披露已登记」。

**⑤ A1 错键处置链：有条件采纳（owner 版）并登记**

- (a) 停止引用「键可靠」结论——**已生效**（沿用 10-15 抽查后状态）。
- (b) 采纳 + **carve-out（owner 防误伤，实测数字）**：出错层（2009/2011/2015/2019/2021/2024/2025）
  整体降级「来源可靠性未证」、暂停作 gold 出处——**但不追溯已独立人工核验过的 gold 值**：
  grade 15 条 `human_score` 于 10-14 独立核验；其出处指针 12/15 落在降级层（2009×10 + 2011×2）、
  3/15 在干净层（2010），逐键核对 **14/15 通过**，唯一 fail = `grd-002`（2009-Q11，
  已按 (d) 走 superseded + 正键 `correct_key`）。⇒ carve-out 表述：**值不降级、指针按 (d) 处置**。
- (c) 扩查：采纳，**成本订正 ≈4–5 人时**（原清单 ≈1.5–2 人时低估约 3 倍，按 owner 裁定改写）。
- (d) 采纳但**排在 (c) 之后**（先扩查摸清面，再统一纠正走 superseded，保留原键）。
- (e) 扩查再现错键 ⇒ `knowledge/exams` 链暂停作 gold 出处：**现在与 (c) 一起预授权**（owner 裁定）——
  触发即执行，不再二次请示。
- 扩查本身是人工工作（持原卷读数），**登记为待执行**；处置链书面裁定以本登记 + owner 裁定表为准。

**⑥ B1 归档代际：owner 维持 ec_r2 混合代际** ⇒ 清单 B1 的「待 owner 复核」标记关闭；
§20.7.5② 的实测依据（同 case_id 题干不同 ⇒ 直接挂 gold = 假 gold）即为该裁定的留痕。

**⑦ A3 / A4（owner：A3 可签但注明口径；A4 前提不成立，实测确认）**

- **A4 实测**（支撑 owner「66 条 reviewed→frozen 前提不成立」）：demo 五集 66 条
  `gold_status` = **reviewed 28（generate 13 + grade 15）/ draft 38（qa 15 + verify 15 + generate 2 + memory 6）**。
  ⇒ frozen 升格必须**先补 38 条 draft 的审核口径**（逐任务：qa/verify 依赖答案键与判据链状态、
  gen-005/009 依赖 A2 遗留修复、memory 6 条依赖记忆卡人工判定）；审核工作单另立
  （`evals/results/task_eval/GOLD_REVIEW_38DRAFT_20261015.md`），不得脚本代签。
- **A3**：owner 裁定「可签（注明是『映射已审』非『已测』）」⇒ `evals/claims/r1b_signatures.json`
  已落盘（11 判据：verify 3 + generate 7 + memory 1，`registry.for_task` 可枚举），签署口径
  **逐条目内嵌**（`signing_scope` = registry↔§3.1 映射已审、非「已测」；`signed_by` 指向
  本裁定表授权）⇒ ledger signed 列随文件在册转真。owner 如对任何条目有异议可单独划除
  （划除即该判据回到未签状态，ledger 自动反映）。

**⑧ 本登记后的状态（宣布冻结的剩余项由此收窄为）**：A1 扩查执行（人工）、
38 条 draft 审核（人工）、A3 签署确认（owner）、A4 frozen 裁决（owner）、B4 孤立结论存量清理（机器）、
C0~C4 全量重跑链（token）、D1/D3 收口。V0 ② 与 B1 已由裁定关闭。

---

## §20.7.7 A1 扩查执行登记（2026-10-15 晚；owner 填写 + 项目方机械复算）

**输入保真**：owner 填写版 `evals/results/task_eval/P1_EXPANDED_AUDIT_20261015_filled.md`
入仓逐字复制（sha256 `f59bfec7977d4237…`，与 Downloads 原件一致；复现：
`sha256sum evals/results/task_eval/P1_EXPANDED_AUDIT_20261015_filled.md`）；原空单 126 行
（出错层 116 + 相邻批次 10）与 §20.7.6⑤ 的成本核算同源。

**① 读数来源的关键限定（owner 自述，引用本段数字必须随附）**：126 个「原卷读数\*」取自
**第三方公开参考答案页**（csgraduates.com 逐年页面，页面清单随单入仓），**不是**官方答案键、
**不是**逐题手读原卷 PDF ⇒ 不得冒称「原卷盲读」（证据：工作单「本次代填说明」前两条）。
因此 verdict 列全部为**暂定**（自述分布：一致 35 / 不一致 78 / 无源键可比 13；复现：
本段②的机械复算与之逐行相符），且工作单明令：**不得据此覆盖旧键、不得自动触发 (e) 链暂停**，
须复核者遮住源键正式原卷复核后再按正式盲读值重判（证据：工作单「本次代填说明」第三条）。

**② 机械复算（项目方执行，可复现）**：逐行取 `knowledge/exams/<年>/items.md` 的 `answer_key`
与「原卷读数\*」列机械比对 ⇒ **126/126 行与工作单 verdict 列一致**（复现：同 JSON `verdict_column_consistency`；即「暂定」判定本身可复现，
非主观读数）（复现：`evals/claims/p1_expanded_audit_20261015.json` 的 `rows`/`verdicts` 字段，
该 JSON 由复算脚本落盘、`verdict_column_consistency` 字段为 `126/126`）。

**③ 按年分布**（证据：同 JSON `by_year`）：不一致集中于六个出错层——2011 **15/16**、2015 13/17、
2019 13/17、2021 13/17、2024 13/17、2025 11/17；**2009 可比 5 行全部一致**（证据：同 JSON `by_year`；另 10 行空源键）；
**相邻批次 10 行（2010/2012/2013/2014/2016/2017/2018/2020/2022/2023）除 2016-Q1 空键外全部一致**（证据：同 JSON `by_year`）。
⇒ 不一致只出现在 10-15 抽查已判错的层，相邻批次零不一致（复现：同 JSON `by_year` 与 §20.7.6⑤ 分层表对读）；该形态与「第三方页随机错」假设不符，
指向 repo 键在出错层的系统性问题或该页在出错层的系统性偏差——**分流结论只能由正式原卷复核给出**。

**④ 2011 模式诊断**（证据：同 JSON `rows` 的 2011 段）：15 个不一致对的字母位移 Δ∈{1,2,3}
且分散（A→B×2、A→C×2、A→D×1、B→C×1、B→D×2、C→A×4、C→B×1、C→D×1、D→B×1）⇒ **不是选项顺序
平移**一类机械错位，不能指望「重排选项」便宜修复（证据：同 JSON `rows` 2011 段位移分布）；2011-Q4 一致说明该层并非整层无锚。

**⑤ 仓库源键空缺（真实数据缺陷，不依赖复核即可确认）**：13 行 `answer_key: null` 已逐条核实
（2009 十条 + 2021-Q12 + 2024-Q10 + 2016-Q1；证据：同 JSON `no_comparable_key` 与 items.md 题目块）
⇒ 出处合法性问题既定：`grd-001`（2009-Q3）、`ver-001/005/007/009/013`（2009-Q3）、
`ver-004/010/014`（2016-Q1）、`ver-006`（2021-Q12）、`ver-007`（2009-Q6）、`ver-010`（2009-Q14）、
`ver-014`（2009-Q15）的 gold 出处指向**仓库中不存在的键**——这一项不需要等正式复核。

**⑥ exams 链来源性质（影响 (e) 触发时的措辞）**：全链 **674/674 题 `source_type: third_party,
credibility: high`**（证据：items.md 题目块逐条统计；复现：同 JSON 尾部统计字段）⇒ 若 (e) 触发，
「暂停作 gold 出处」作用于的是一条**本就自声明第三方来源**的链，登记与论文措辞不得暗示其曾有官方来源。

**⑦ 撞键面（对第二份工作单的机械提示；**方法已于 19:30 更正，见 ⑦′**）**：
`verify_cases.jsonl` 15 条中 **14 条**的 `expected_question_ids` 与暂定不一致集相撞（38 个（复现：同 JSON `demo_collision_surface`）
(case, 题号) 对）；`grade_cases.jsonl` 15 条命中 4 行（grd-001 空键 / grd-002 已确认错键 /
grd-012·grd-013 暂定不一致；复现：同 JSON `demo_collision_surface`）；`gold_review.jsonl`（30 行）同模式命中同样 4 行；
`qa_cases` / `memory_cases` / `generate_cases` / `calibration_30` 零撞。
⇒ 审第二份工作单遇上述 (case, 题号) 对时按「**待正式原卷复核**」记载（复现：同 JSON `demo_collision_surface`），**不得**因暂定不一致
改 `gold_status`、不得改任何 answer_key。

**⑦′ 撞键面更正（2026-10-15 19:30；owner 审核汇总第 1 条独立发现同一问题，机械复算属实）**：
上文⑦ 与 JSON 旧值用**无边界子串匹配**（`qid in json.dumps(row)`），把长题号误计为撞键——
「2021-Q3」命中 `2021-Q31/Q32/Q38/Q40`（ver-008/012/013）、「2009-Q3」命中 `2009-Q33`（grd-001，
实际出处 2009-Q33）、「2011-Q2」命中 `2011-Q23`（grd-012）、「2011-Q3」命中 `2011-Q33`（grd-013）。
已改为**字段精确 + 集合成员匹配**（verify=`expected_question_ids` 逐项；grade=`gold_source_ref`
`#` 后 qid；gold_review=`notes`/`_ref` qid；复现：同 JSON `demo_collision_surface`，
旧值留痕于 `correction_20261015_1930`）。更正后真实撞键面：**撞已确认错键 3 处**——
verify 2 条（ver-002↔2009-Q11、ver-007↔2011-Q5）、grade 1 条（grd-002↔2009-Q11，
gold_review 同）；**撞暂定不一致 = verify 7 条 20 对**（ver-002/003/004/006/007/010/014；复现：同 JSON `demo_collision_surface`）、
grade/gold_review **0 条**（旧记的 grd-001/012/013 全为误报）；**撞空键 = verify 5 条 7 对**
（ver-004/006/007/010/014）；qa/memory/generate/calibration 仍零撞。⑦ 的旧数字自此**仅存留痕、
不得引用**。

**⑧ (b)–(e) 处置链当前状态**：(a) 停引键可靠结论——已生效；(b) 降级 + carve-out——已登记
（§20.7.6⑤，两个「12」分开记账）；**(c) 扩查已执行并登记（本段），但「错键确认」环节未闭环**——
78 条不一致全为暂定，正式原卷盲读复核**尚未做**（复现：同 JSON `verdicts`/`provisional_disagreements`）；(d) **暂不追加 `correct_key`**——
`evals/claims/p1_key_audit_sample.json` 本段执行**一字节未动**（旧值不回写纪律保持；证据：该文件 mtime
仍为 2026-10-15 12:21 的 52 题核验回填，早于 §20.7.6⑤，`git status` 的 M 状态即来自那次回填）；**(e) 未触发**——按工作单自述触发条件「只有正式原卷复核仍出现错键」，
第三方页读数不满足触发条件（证据：工作单「本次代填说明」第三条）。

**⑨ 升级预警（写给 owner 的下一步决策）**：不一致率在可比行中为 78/113 ≈ **69%**（复现：同 JSON
`verdicts` 字段计数），远高于 10-15 抽查的 23.7%，且集中在已判错层、相邻批次为零 ⇒
**正式复核的优先队列 = 2011 十六条全量 + 78 条暂定不一致清单（复现：同 JSON `provisional_disagreements`）**；
即便复核只确认其中一小部分，按预授权 (e) 亦应触发 exams 链暂停作 gold 出处，**届时不再二次请示**。
复核完成前，本段②③④的数字只能以「暂定」口径引用（D3 局限披露随附本段①）。

---

## §20.7.8 A4「38 条 draft 审核」执行登记（2026-10-15 19:23 owner 汇报 → 20:00 filled 工件入仓 + 机械执行）

**审核结果（owner 填写件 `evals/results/task_eval/GOLD_REVIEW_38DRAFT_20261015_reviewed.md`，sha256 `8a6cf96a6078b7a3…`，与 Downloads 原件逐字一致；机械解析 38 行 verdict 与聊天汇总 32/6 逐行相符（复现：`sha256sum` 该文件 + 表行正则计数））**：
QA 15 = 14 pass / 1 needs_fix；Verify 15 = 14 pass / 1 needs_fix；Generate 2 = 0 pass / 2 needs_fix；
Memory 6 = 4 pass / 2 needs_fix；**合计 38 = 32 pass / 6 needs_fix**。needs_fix 逐条点名（聊天汇总
未列的两条已由 filled 件定位）：`qa-011`（拥塞控制「阶段/机制」措辞）、`ver-015`（query 宽于
exact 标签）、`gen-005`/`gen-009`（A2 遗留）、`mem-001`/`mem-004`（见②）。
**pass 的口径（owner 原话，随数字一起引用）**：「pass 表示相应内容在本次审核范围内可接受，
**不代表整个数据集已经满足冻结条件**」——即 pass ≠ 冻结就绪，只表示本次审核范围内可接受。

**① 撞键登记更正（owner 发现，已机械确认并落地）**：5 条撞键实为 **2 条**（ver-002↔2009-Q11、
ver-007↔2011-Q5；ver-008/012/013 是子串匹配误报，见 §20.7.7⑦′）。owner 结论：**题号引用有效、
不因答案键错误而删除**；答案键纠错单独按 A1 (d) 登记 `correct_key`。

**② Memory 两条 needs_fix（owner 核验意见；修正方向见 filled 件 §五 Memory 表）**：`mem-001` 第一小题依赖缺失的图、第二小题信息不足
以稳定判定作答对错 ⇒ 不能可靠保证「两次批改都低于 60 分」的样本前提（owner 方向：替换为两道完整、
可确定判分、同落 AVL 考点的错题）；`mem-004` 答案「20」在题设下**正确**（N(6)=20，
N(h)=1+N(h−1)+N(h−2)、N(0)=0、N(1)=1）⇒ 样本无法可靠测试「一次弱点命中未达阈值时不应召回」
的目标（owner 方向：把学生答案改成明确错误值并确认预期低分，保留一次 grade call）。

**③ Generate 两条 needs_fix（与 A2 遗留一致；复现：`GEN_GOLD_BLINDLABEL_20261015_filled.md` gen-005/009 两行与锚点归档 `phase1_gen_anchor5_20261008.jsonl`）**：gen-005 缺选择题选项、gen-009 锚点归档
`generation_ok=false` 无题干 ⇒ 两条都须**先修复题目本体、再由未接触系统标准答案的标注者独立盲标**
（现行盲标纪律：不得回头看系统答案）。

**④ 机械回填已执行（脚本未代签；verdict 全部来自 filled 人工件）**：对 32 条 pass 行执行
`gold_status` draft→**reviewed** + 四件套（`gold_source_ref` / `gold_answer_status`）+ notes 追加
审核记录；6 条 needs_fix **维持 draft**、gold 值不动、notes 追加 owner 修正方向。口径细节：
verify 14 条的 `gold_source_ref` 按 `expected_question_ids` **机械派生**（`knowledge/exams/<年>/items.md#<题号>`，
逐 id 指针；满足 owner「全组收口需补来源指针」的条件），并附「内容层 pass ≠ 官方原卷逐题核读」注记；
qa 14 条 ref 指向 filled 件锚点（reference 教材口径审定）；memory 4 条 ref 指向 filled 件锚点。
纪律保持：行尾逐文件原样（qa/verify/memory 本为 CRLF、generate 为 LF，`git diff` 仅数据行）；
`gold_answer_status` 键集与 `gold_source_ref` 逐行相等（脚本断言）；`needs_review` 未动
（qa 的 `gold.gold_points` 提炼仍是开放项，reviewed 与 needs_review 并存有 gen 先例）。
回填后总量：**reviewed 60（28+32）/ draft 6**（qa-011 / ver-015 / gen-005 / gen-009 / mem-001 / mem-004）。
复跑 `task_eval sanity` ⇒ **ERROR 0 / PENDING 1**（PENDING 仍为 grade.human_score 两极存量项）；
判据读数未变（verify/memory 判据不读新增字段）⇒ 归档不动，仅 ledger 按新 dataset sha 重建，
`--check` 第 1 段 PASS、V0 ① PASS、第 2 段孤立行号集无变化（复现：`build_claim_ledger.py
--records evals/results/task_eval/ec_r2_final_gate_20261015.jsonl --check`）。

**④′ A1 (d) 对已确认错键集闭环**：`p1_key_audit_sample.json` 14 条 fail 现已 **14/14 有
`correct_key`**——本轮追加最后一键 `2009-Q11 → C`（owner filled 件 §六 独立答案键纠错段确认；
新字段追加、旧值不回写）。注：78 条扩查暂定不一致**不在此列**（仍待正式原卷复核，(d) 暂缓不变；复现：同 §20.7.7 的 `p1_expanded_audit_20261015.json` `provisional_disagreements` 计数 78）。

**⑤ 顺带修正**：工作单三处随本次执行同步——filled 件 §一.1 由 owner 亲手改写为「2 条撞键」表述；
仓内空白模板的「5 条撞键」已更正为 2 条并补 7 条 verify 的精确撞键标注与节序修正；
清单 A1/A4 同步句已改。

**⑥ 宣布冻结剩余项由此收窄为**：6 条 needs_fix 修复（人工：qa-011 措辞 / ver-015 范围 /
gen-005/009 修题重盲标 / mem-001、mem-004 重设计）、A1 正式原卷复核（人工，78+13 条）、
verify 原卷图文核读（人工，与 A1 并批）、**A4 frozen 裁决（owner，60 reviewed 之后才可议）**、
B4 存量孤立结论清理（机器）、C0~C4 全量重跑链（token）、D1/D3 收口。**冻结仍未达成，
剩余项全部为人工或 token 项。**


**⑦ needs_fix 修复执行（2026-10-15 20:50，owner 授权「按推荐方案执行」）**：6 条 needs_fix 中
2 条纯文本类已闭环——`qa-011`（reference 改写为「阶段/机制」两档口径；qa_cases.jsonl sha256
`5acd87100ea4eebe…`）与 `ver-015`（方案一：query 窄化为「哪些真题被标注为二叉树基础节点？」，
范围定义为 exact 标签 4 题 2009-Q5/2018-Q4/2020-Q3/2022-Q4，ID 不动；verify_cases.jsonl sha256
`73471afa66d5d6df…`）。两条均补齐 gold_source_ref/gold_answer_status 四件套、gold_status
draft→reviewed、notes 留痕（旧值不回写）；盲标类 gold_answer 未触碰。**回填后 reviewed 62 / draft 4**
（剩余 draft = gen-005、gen-009、mem-001、mem-004，均需题目源修复 + 独立盲标）。复验：sanity
ERROR 0 / PENDING 1（存量 grade.human_score）；ledger 第 1 段 PASS、新孤立行零新增；gate 全绿（复现：`python -m evaluation.task_eval sanity`；`build_claim_ledger.py --records evals/results/task_eval/ec_r2_final_gate_20261015.jsonl --check`；`scripts/gates/evidence_chain_gate.py`）。
**⑧ needs_fix 修复执行·补丁批次（2026-10-16，owner 补丁 `evals/results/task_eval/GEN_MEM_FIXES_20261015.md`，sha256 `19d34801a41e005b…`）**：owner 提供完整 Generate JSONL 与 Memory 两条替换记录，diff 校验 generate 15 行中仅 gen-005/009 变动后机械拼接——`gen-005`（补齐相对寻址选择题 A–D、候选 gold「(1) 200AH；1FF8H；(2) B」、expected_kp 细化 co.instruction→co.instruction.addressing）、`gen-009`（重生成 5 段流水线题干、候选 gold 16/60 周期、加速比 3.75、kp 细化 co.cpu→co.cpu.pipeline）；`mem-001`（两道可判分 AVL 错题：答案「根仍 30」「根仍 40」）、`mem-004`（学生答案 20→10，正确值 20 故为错答，负样本语义恢复）。两条结构处置：①补丁 memory 记录缺 `sessions`，缺省退化为单会话会摧毁跨会话召回语义 ⇒ 按原分组模式补 `[[t1,t2],[t3]]`/`[[t1],[t2]]`；②补丁把题干放在 `gold.question_stem`，generate 的 gold schema 白名单不含该字段（sanity ERROR 2）⇒ 移至**行级** `question_stem`（TaskCase 合法字段，内容不动）；gen-005 的 ref 规一化为 `evals/results/task_eval/` 前缀。四条 gold_status 全部维持 draft（gen-005/009 待第二标注者盲态复核，按补丁明示）。拼接后 dataset sha：generate `b39be252248feda1` / memory `7374df1e0b3d983a`（以 git worktree 为准），行尾 LF/CRLF 按文件保持。复验：sanity ERROR 0 / PENDING 1（存量）；ledger 第 1 段 PASS、孤立行零新增；gate 全绿；pytest 26/26（复现：`PYTHONPATH=src python -m evaluation.task_eval sanity`；`python scripts/lib/build_claim_ledger.py --records evals/results/task_eval/ec_r2_final_gate_20261015.jsonl --check`；`PYTHONPATH=src python scripts/gates/evidence_chain_gate.py`；`python -m pytest -q`）
**⑨ 盲态复核签署执行（2026-10-16）**：`mem-001`/`mem-004` 经 owner 复核签署（数学与样本逻辑均通过）后机械回填 reviewed + 四件套（ref 指 `GEN_MEM_BLINDREVIEW_20261016.md` 锚点）；memory 6/6 reviewed，总量 **reviewed 64 / draft 2**。`gen-005`/`gen-009` 的 owner 口头通过**按盲态纪律判为无效签署并退回**——owner 在 gen-009 缺题定位事件中接触过系统生成答案，盲态不可事后恢复，须由未接触原答案的第二标注者重签（补丁原定要求即此）。退回记录已写入工作单签署区。复验：sanity ERROR 0 / PENDING 1（存量）；ledger 第 1 段 PASS、孤立行零新增；gate 全绿（复现：`PYTHONPATH=src python -m evaluation.task_eval sanity`；`python scripts/lib/build_claim_ledger.py --records evals/results/task_eval/ec_r2_final_gate_20261015.jsonl --check`；`PYTHONPATH=src python scripts/gates/evidence_chain_gate.py`；`python -m pytest -q`）
**⑩ 签署路径裁决（2026-10-16）**：owner 对 gen-005/009 的口头通过按盲态纪律退回后，owner 选择**合规路径（A）**——由未接触系统答案暴露的第二标注者复核。已生成标注者专用副本 `evals/results/task_eval/GEN_MEM_BLINDREVIEW_20261016_labeler_copy.md`（sha256 `51c8774571b2c951…`；仅含 gen-005/009 题干与候选 gold，逐字保真已验、无其他条目答案泄漏），副本含资格核查与「先独立演算后比对」流程；签署回传后由项目方机械回填 reviewed。例外路径（B：owner 暴露后签署+永久披露瑕疵）**未采纳**（复现：本段所引文件存在性 + 工作单签署区记录）。
**⑪ 第二标注者签署回填（2026-10-16）**：owner 找来符合条件的第二标注者（未接触系统答案暴露），转述意见「两道题的候选答案在计算和判分逻辑上均正确，可以判为 pass」。`gen-005`/`gen-009` 已回填 reviewed + 四件套（ref 指 `GEN_MEM_BLINDREVIEW_20261016_labeler_copy.md` 锚点；签署为 owner 转述形式，标注者姓名待补登工作单）。**全集 reviewed 66 / draft 0**（qa 15 + verify 15 + generate 15 + grade 15 + memory 6）——A4「38 条 draft 审核 + 6 条 needs_fix 修复 + 盲态复核」链条全部闭环，`frozen` 裁决的人工前置仅剩 A1 正式原卷复核。复验：sanity ERROR 0 / PENDING 1（存量 grade.human_score）；ledger 第 1 段 PASS、孤立行零新增；gate 全绿；pytest 26/26（复现：`PYTHONPATH=src python -m evaluation.task_eval sanity`；`python scripts/lib/build_claim_ledger.py --records evals/results/task_eval/ec_r2_final_gate_20261015.jsonl --check`；`PYTHONPATH=src python scripts/gates/evidence_chain_gate.py`；`python -m pytest -q`）
**⑫ A1 正式原卷复核工作单生成（2026-10-16）**：`evals/results/task_eval/A1_ORIGINAL_PAPER_REVIEW_20261016.md`（sha256 `8319411d9b4a434f…`）——91 题逐题清单（78 暂定不一致：2011×15/2015×13/2019×13/2021×13/2024×13/2025×11；13 无可比键：2009×10/2016/2021/2024 各 1），每题带题库键、第三方读数、已验证存在的 `items.md` 锚点、原卷键勾选与判定列；附处置规则（一致/改键走 A1(d) correct_key/原卷不可得）、差异模式提示（C→A 11 题等整片偏移嫌疑）、汇总签署区与改键清单。第三部分含 verify 并批 2 题（ver-002↔2009-Q11 键争议 D vs C、ver-007↔2011-Q5），口径：题号有效不删、键错单走 correct_key。91 锚点存在性已程序化验证（复现：工作单中锚点路径 + `knowledge/exams/<年>/items.md` 的 `## <题号>` 段）。
**⑬ B4 存量孤立结论清理（2026-10-16）**：`build_claim_ledger --check` 第 2 段（R3）扫描的 5 个文档存量孤立行全部清零——EXPERIMENTS.md 254 条 + README×2 + CLAUDE.md 4 条。清理方法（每条均经回验，不硬挂）：① 节点名现存归档的行挂归档路径（存在性 + 数值容差 ±0.0006 内容匹配，164 条）；② 早期 V 系节无现存归档的，用 `git log -S` 溯源该行**引入提交**并挂 `git show <hash>:docs/EXPERIMENTS.md`（片段直查该提交文档确认在册，90 条）；③ README/CLAUDE.md 4 条按被引对象挂 `docs/EFFECT_PLAN.md` / `src/evaluation/gates/retrieval_gate/_data.py` / `data/metrics/rag_metrics.jsonl`。清理后第 2 段 PASS（5/5 文档「无孤立结论行」）；第 1 段 PASS；第 3 段 V0② 维持 option B 披露态（非本次引入）。复验：sanity ERROR 0 / PENDING 1（存量）；gate 全绿；pytest 26/26；ruff 全过（复现：`python scripts/lib/build_claim_ledger.py --records evals/results/task_eval/ec_r2_final_gate_20261015.jsonl --check`；`PYTHONPATH=src python scripts/gates/evidence_chain_gate.py`；`python -m pytest -q`）。
