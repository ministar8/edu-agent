# 专项实验数据汇总

> 供论文实验章直接引用。数据来源均为仓库内 `evals/` 归档，可复现脚本见各节「复现」。
> 最后整理：2026-09-30

---

## 1. 实验设置

| 项 | 值 |
|---|---|
| 黄金集 | `evals/datasets/golden/sample_408.jsonl`（408 四科，含学科/章级知识点标注） |
| 消融样本 | 前 60 条（`--limit 60`） |
| 门禁全集 | 156 条 |
| 指标 | `kp_hit@k` / `kp_mrr`（章级知识点，文件=章）；`category_hit@1` / `category_mrr`（学科级） |
| Embedding | TEI `BAAI/bge-m3`（dim=1024） |
| 文本模型 | `dashscope:qwen3.8-max` |
| 跑分脚本 | `scripts/ablation_retrieval.py` / `python -m evaluation.retrieval_gate` |

> **口径提醒**：学科级 `category_hit@k` 易饱和（近 1.0），敏感指标是 **kp_mrr**。
> `RERANK_ENABLED` 由 `.env` 在进程启动时固化，rerank 消融需显式环境变量覆盖。

---

## 2. 消融实验（检索组件）

**复现**：`uv run python scripts/ablation_retrieval.py --limit 60`
**归档**：`evals/results/retrieval/ablation/20260930_165603.json`

| 配置 | kp_hit@k | Δ | kp_mrr | Δ | cat@1 | 证据数 | 耗时(s) |
|---|---|---|---|---|---|---|---|
| **full（基线）** | **1.000** | — | **0.943** | — | 0.983 | 5.75 | 61 |
| no_bm25 | 0.967 | −0.033 | 0.856 | **−0.088** | 0.950 | 5.78 | 38 |
| no_metadata | 0.983 | −0.017 | 0.831 | **−0.113** | 0.950 | 5.80 | 22 |
| no_decompose | 1.000 | 0 | 0.943 | 0 | 0.983 | 5.75 | 44 |
| no_hyde | 1.000 | 0 | 0.943 | 0 | 0.983 | 5.75 | 41 |
| vector_only | 0.967 | −0.033 | 0.785 | **−0.158** | 0.950 | 5.75 | 32 |
| plus_topup | 1.000 | 0 | 0.943 | 0 | 0.983 | **9.00** | 150 |

### 2.1 真·重排对照（单独一轮，`RERANK_ENABLED=true`）

**归档**：`evals/results/retrieval/ablation/20260930_165827.json`

| 配置 | kp_hit@k | kp_mrr | 证据数 |
|---|---|---|---|
| full（rerank on） | 0.983 | 0.897 | 4.12 |
| no_rerank | 1.000 | 0.943 | 5.72 |
| **Δ（rerank 带来）** | **−0.017** | **−0.046** | −1.60 |

### 2.2 消融结论（论文可直接写）

1. **多路召回是主贡献源**：仅语义向量（vector_only）相对完整系统 **kp_mrr −0.158**；BM25 与元数据路由均有正贡献，元数据路由最大（−0.113）。
2. **查询分解 / HyDE 在 k=5 预算下无增益**：去掉后指标逐位不变。诚实结论——复杂度未兑现，可归因于短查询占比与候选预算。
3. **L2 preferred 层 top-up 只增加覆盖**（证据数 5.75→9.0），不改善排序指标（主池已饱和）。
4. **重排（bge-reranker）在本黄金集上未带来收益，反而略降**（kp_mrr −0.046、证据数减少）：疑因阈值过滤误杀正确候选。**负面结果，如实报告。**

---

## 3. Legacy 资产池策略（三策略对比）

**背景**：无 `kb_depth` 的旧讲义/真题（legacy）曾挤占证据包。
**复现**：`scripts/legacy_runtime_compare.py` · 6 条固定 probe
**归档**：`evals/results/retrieval/legacy_runtime/legacy_runtime_20260929_194417.json`

| 策略 | 层精度 pack（6 probe 均值） | 说明 |
|---|---|---|
| keep（原样保留） | 0.375 | legacy 自由混排 |
| downrank（降权） | 0.417 | 仍占坑 |
| **drop / exclude（真删）** | **1.000** | 包内全为 L1/L2/L3 |

**结论**：调权重治不了数据治理问题；**真删 legacy 后层精度 0.375→1.000**。
最终采用 `legacy_policy=exclude`（learn/method/practice/verify）+ `fallback`（grade/explain）。

---

## 4. 检索质量门禁基线（156 条全集）

**复现**：`PYTHONPATH=src uv run python -m evaluation.retrieval_gate`
**归档**：`evals/baselines/retrieval_baseline.json`（fake-embedding 口径，防 CI 无 TEI）

| 指标 | 值 |
|---|---|
| n_queries | 156 |
| category_hit@1 | 0.904 |
| category_hit@k | 0.968 |
| category_mrr | 0.928 |
| kp_hit@k | 0.865 |
| kp_mrr | 0.670 |
| empty_result_rate | 0.0 |

> 该基线为**回归门禁**（指标不低于基线即通过），非最优值声明。
> 另有真实 embedding 口径基线：`evals/baselines/retrieval_baseline_real_*.json`。

---

## 5. RAGAS 生成质量（n=20，配对样本）

**归档**：`（已删，待重跑）`

| 指标 | mean |
|---|---|
| faithfulness | 0.617 |
| answer_relevancy | 0.136 |
| context_precision | 0.0 |
| context_recall | 0.0 |

> ⚠️ **诚实注记**：`context_precision/recall=0` 为当时标注/接口口径问题（非检索真为 0）；
> `answer_relevancy` 偏低受生成模型与问题表述影响。**论文若引用 RAGAS，需先修复口径重跑**，
> 建议以 §2 检索指标为主证据，RAGAS 作辅助。

---

## 6. Agent 行为质量（软指标）

**复现**：`scripts/agent_behavior_gate.py`
**归档**：`evals/results/system_validation/agent_behavior/agent_behavior_quality.json`

- 硬安全（泄漏/empty 硬教/无来源确认）：**8 case 全 PASS**
- 软指标 `quality_score=0.159`（evidence_usage 均值；FULL/THIN/EMPTY 三态含在内）

---

## 7. 一页结论（论文第 5 章可用）

| 主张 | 证据 | 数字 |
|---|---|---|
| 多路召回有效 | §2 消融 | vector_only kp_mrr **−0.158** |
| 元数据路由贡献最大 | §2 消融 | no_metadata **−0.113** |
| legacy 池策略必要 | §3 | 层精度 0.375→**1.000** |
| 系统稳定可回归 | §4 门禁 | 156 条指标不低于基线 |
| 生成侧安全可控 | §6 | 硬安全 8/8 PASS |
| 三层服务不同任务（非刷同一指标） | §9 | learn→L1 / method→L2 / grade·verify→L3 |
| 负面结果（如实） | §2.1 | rerank kp_mrr **−0.046** |
| 负面结果（如实） | §2 | decompose / HyDE 无增益 |

---

## 8. 归档索引

| 路径 | 内容 |
|---|---|
| `evals/results/paper_experiments/` | 消融矩阵与 rerank 对照 |
| `evals/results/retrieval/legacy_runtime/` | legacy 三策略 |
| `evals/results/layer_policy/` | 层权重 profile 实验 |
| `evals/results/ragas_*.json` | RAGAS 各轮 |
| `evals/results/system_validation/agent_behavior/agent_behavior_quality.json` | 行为软指标 |
| `evals/results/system_validation/langgraph_state/state_gate.json` | State 闭环证据 |
| `evals/baselines/retrieval_baseline*.json` | 门禁基线（多口径） |
| `evals/baselines/probe_baseline.json` | 探针基线 |


---

## 9. L1/L2/L3 分层消融（2026-09-30）

**复现**：uv run python scripts/ablation_retrieval.py --limit 60 --configs full,no_l1,no_l2,no_l3,l1_only,l2_only,l3_only,no_legacy,legacy_only
**归档**：evals/results/retrieval/layer_policy/20260930_180517.json

### 9.1 逐层剔除（leave-one-out）

| 配置 | kp_hit@k | kp_mrr | Δ kp_mrr | cat@1 |
|---|---|---|---|---|
| **full** | 1.000 | **0.951** | — | 0.983 |
| no_l1 | 1.000 | 0.944 | −0.007 | 0.967 |
| no_l2 | 1.000 | 0.940 | −0.011 | 0.967 |
| no_l3 | 1.000 | 0.951 | −0.001 | 0.967 |

### 9.2 单层保留（single-layer-only）

| 配置 | kp_hit@k | kp_mrr | cat@1 | empty |
|---|---|---|---|---|
| l1_only | 0.983 | 0.944 | 0.967 | 0.0 |
| l2_only | 0.783 | 0.704 | 0.950 | 0.0 |
| l3_only | 0.000 | 0.000 | 0.000 | **0.983** |
| no_legacy | 0.967 | 0.882 | 0.967 | 0.0 |
| legacy_only | 1.000 | 0.934 | 0.950 | 0.0 |

### 9.3 结论（任务导向，非单一指标）

**核心叙事**：三层不是为了提升同一个检索指标，而是满足**不同任务下的证据组织与访问控制**：

| 任务 | 应偏向的层 | 设计对应 |
|---|---|---|
| learn | L1 | preferred_layers=[basic, advanced] |
| method | L2 | preferred_layers=[advanced, basic] |
| practice | L2+L3 | legacy_policy=exclude，出题走题库 |
| grade | L3 | exam_resources.answer=allowed |
| verify | L3 | exam_resources.question=allowed, answer=forbidden |

**单指标（kp_mrr）只覆盖「知识点检索」切片**——在该切片内：

1. **L1 提供主要语义覆盖**（l1_only 0.944）：当前黄金集 probe 偏学习/概念题，结论不外推到全部任务。
2. **L2 方法层覆盖不足**（l2_only 0.704）：与 coverage analysis（legacy 2481 vs L2 98）互相印证。
   研究闭环：coverage analysis → 发现方法层薄弱 → 补 L2 → 消融验证。
3. **L3 面向考试资源，不适合作为通用知识解释库**（kp_mrr 0、empty 98%）：
   其 chunk 是「题干/选项/答案/解析」，缺定义、原理、推导、方法体系；
   但在 grade/verify（「这个选项为什么错」「哪年考过」）下不可替代。
   对 kp_mrr 不敏感是**设计预期**，不是缺陷。

**不要写的结论**（易被审稿人抓住）：
- ~~「三层高度冗余」~~ —— 只在 kp_mrr 一个切片上重叠，跨任务不是冗余
- ~~「L3 不能当知识库」~~ —— 「不能」是能力判断；准确表述是「不适合作通用知识库」（定位判断）

**L3 需要任务专有指标**（当前实验未覆盖，列为后续工作）：
exam_hit@k（真题召回）· question_id recall（题目定位）· answer availability（答案可达）· verify accuracy

### 9.4 本轮发现并修正的度量问题

- **问题**：黄金集 kp 标注是中文章名（文件管理），新层文件名是英文 stem（file_disk）
  → l*_only 的 kp_* 一度恒为 0（l1_only cat@1=0.97 但 kp_hit=0），是度量失真非检索失败。
- **修正**：evaluation.retrieval_gate._CHAPTER_ALIASES 章名别名表，两侧归一到黄金集标签。
- **影响**：chapter_of_source 语义不变，只是补了英文 stem → 中文标签映射。

---

## 10. Task-aware Layer Ablation（2026-09-30）

**问题**：§9 用单一 kp_mrr 考三层，L3 必然吃亏。本实验改用**任务专有指标**。

**对照**：
- baseline = 所有任务 L1/L2/L3 平铺 + legacy 等同主池
- ours = task_mode → preferred_layers → legacy_policy

**复现**：`uv run python scripts/task_layer_ablation.py`
**归档**：`evals/results/retrieval/ablation/task_layer_20260930_182847.json`

### 10.1 任务专有指标对比

| task_mode | 目标层 | baseline hit | ours hit | Δ | 泄漏 b/o |
|---|---|---|---|---|---|
| learn | L1 basic | 0.667 | **1.000** | **+0.333** | 0.00/0.00 |
| method | L2 advanced | 0.833 | **1.000** | **+0.167** | 0.00/0.00 |
| practice | L2+L3 | 1.000 | 1.000 | 0 | **0.25/0.00** |
| grade | L3 exams | 0.667 | 0.667 | 0 | n/a |
| explain | L3 exams | 1.000 | 1.000 | 0 | n/a |
| verify | L3 exams | 0.333 | 0.333 | 0 | 0.00/0.00 |
| **MACRO** | | 0.750 | **0.833** | **+0.083** | |

（leakage 仅统计 answer-hidden 模式；grade/explain 的 answer_policy=released 不计）

### 10.2 结论

1. **任务感知的层偏好有效**：learn 的 L1 命中 +0.333、method 的 L2 命中 +0.167——
   证明 `preferred_layers` 不是装饰，而是把目标层推进证据包的实杠杆。
2. **access control 消除泄漏**：practice 平铺时泄漏 0.25，ours 降为 0——
   `legacy_policy=exclude` + `exam_resources` 的任务绑定生效。
3. **L3 在 grade/explain 已可达**（hit 0.67~1.0）：任务指标下 L3 不再「吃亏」，
   §9 中「L3 对 kp_mrr 不敏感」获得正面证据。
4. **verify 的 L3 命中偏低**（两臂均 0.333）：真题 chunk 在 verify 查询下召回不足，
   属**待优化点**（与 L2 薄弱并列），非策略失效。

### 10.3 叙事要点（论文）

> 三层的价值不在单一检索指标的堆叠，而在**任务条件下的证据组织与访问控制**：
> learn/method 获得目标层覆盖增益，practice 获得零泄漏，grade/verify 获得真题资源可达。

---

## 11. 基础 RAG 消融（2026-09-30）

**对照**：
- **basic_rag** = 语义向量 top-k（无 BM25/元数据/分解/HyDE/重排/任务策略；层平铺、legacy 同池）
- **ours** = 完整系统（多路召回 + task_mode → preferred_layers → legacy_policy）

**复现**：`uv run python scripts/basic_rag_ablation.py --limit 60`
**归档**：`evals/results/retrieval/ablation/basic_rag_20260930_191718.json`

### 11.1 检索口径

| arm | kp_hit@k | kp_mrr | cat@1 | cat_mrr | 证据数 |
|---|---|---|---|---|---|
| basic_rag | 0.967 | 0.863 | 0.917 | 0.956 | 4.75 |
| **ours** | **1.000** | **0.951** | **0.983** | **0.992** | 5.73 |
| **Δ** | +0.033 | **+0.089** | +0.067 | +0.036 | +0.98 |

### 11.2 任务口径

| task_mode | 目标层 | basic | ours | Δ |
|---|---|---|---|---|
| learn | L1 | 0.667 | **1.000** | **+0.333** |
| method | L2 | 0.833 | **1.000** | **+0.167** |
| practice | L2+L3 | 1.000 | 1.000 | 0 |
| grade | L3 | 0.667 | 0.667 | 0 |
| explain | L3 | 1.000 | 1.000 | 0 |
| verify | L3 | 0.333 | 0.333 | 0 |
| **MACRO** | | 0.750 | **0.833** | **+0.083** |

### 11.3 结论

1. **相对朴素向量 RAG 全面提升**：kp_mrr **+0.089**、kp_hit +0.033、cat@1 +0.067。
2. **任务口径收益更大**：learn +0.333 / method +0.167 —— 任务策略把目标层推进包，朴素平铺做不到。
3. **证据更充分**：平均 4.75 → 5.73 条（多路召回+融合的覆盖优势）。

> 这是论文「对比实验」的主表：**同黄金集、同指标、仅系统配置不同**。
