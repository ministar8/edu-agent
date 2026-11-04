# RAG 消融汇总（2026-11-04）

> 本文把**组件消融**与 **L1/L2/L3 分层消融**放在一处——两者同属论文检索章的证据。
> 原始数字以归档 JSON 为准；论文表见 `paper_tables.md` 表 2B 与表 4B。

## 口径

| 项 | 值 |
|---|---|
| 黄金集 | `evals/datasets/golden/sample_408.jsonl`（**全量 156 条**，sha256 `783e78ff…`） |
| 索引 | 生产索引 `chroma_db`（2026 chunk / 10 集合，2026-11-04 全量重建） |
| Embedding | 真 TEI bge-m3（`localhost:11435`） |
| Rerank | `RERANK_ENABLED=false`（部署开关关闭，本组实验不执行重排） |
| RAG LLM | `dashscope:deepseek-v4.1-flash` |
| 代码版本 | 组件 `df0965b`；分层 `3e01416`（仅新增本文档，检索行为无差异） |
| 查询 embedding | 进程内缓存（只影响耗时，不改结果） |

---

## 一、组件消融

**归档**：`evals/results/retrieval/ablation/component_ablation_20261104_full156_deepseek41.json`
**复现**：`PYTHONPATH=src python scripts/lib/ablation_retrieval.py --configs full,no_bm25,no_metadata,no_decompose,no_hyde,vector_only,plus_topup`

| 配置 | kp_hit@k | kp_mrr | Δ kp_mrr | cat@1 | empty | 证据数 |
|---|---|---|---|---|---|---|
| **full** | 0.9231 | **0.8309** | — | 0.8718 | 0.000 | 5.55 |
| no_bm25 | 0.8077 | 0.7403 | **−0.091** | 0.7885 | 0.045 | 4.31 |
| no_metadata | 0.9679 | 0.8675 | **+0.037** | 0.8974 | 0.000 | 5.80 |
| no_decompose | 0.9359 | 0.8236 | −0.007 | 0.8526 | 0.000 | 5.01 |
| no_hyde | 0.9231 | 0.8347 | +0.004 | 0.8718 | 0.000 | 5.56 |
| vector_only | 0.8782 | 0.8010 | −0.030 | 0.8205 | 0.019 | 5.01 |
| plus_topup | 0.9487 | 0.8365 | +0.006 | 0.8718 | 0.000 | 6.92 |

**结论**

1. **BM25 是唯一大幅正贡献的组件**：去掉后 kp_mrr −0.091、kp_hit −0.115、cat@1 −0.083。
2. **元数据路由为负贡献**：去掉后 kp_mrr **+0.037**、kp_hit +0.045。这是最反直觉的一条，
   需要按具体 meta 路由（`concept_meta` / `section_meta` / `exercise_meta` 等）细分复核。
3. **分解 / HyDE 接近中性**（−0.007 / +0.004），不再支持「轻微负增益」的旧子集结论。
4. **多路召回整体有效**：`vector_only` 相对 full −0.030。
5. **top-up 只增加覆盖**（5.55 → 6.92），不改排序指标。

> ★ 60 条子集过渡读数（2026-11-04，qwen3.8-flash）已删除并作废；它与全量在 BM25 / 元数据方向上
> **不一致**。可从 `git show ed9f385:evals/results/retrieval/ablation/component_ablation_20261104_qwen38flash.json` 取回。

---

## 二、分层消融（L1 / L2 / L3）

**归档**：`evals/results/retrieval/layer_policy/layer_ablation_20261105_full156_deepseek41_withfull.json`
**复现**：`PYTHONPATH=src python scripts/lib/ablation_retrieval.py --configs full,no_l1,no_l2,no_l3,l1_only,l2_only,l3_only,no_legacy,legacy_only`

> 本轮 `real_fail=0`、`llm_fail=0`，无重试兜底记录。下表 Δ 全部相对**同轮 full**。
> ★ 两次运行的 full 相差 0.013（组件 0.8309 / 分层 0.8174），属 HyDE/分解的 LLM 非确定性；
> **同一张表内只用同轮 full 比较**，不要跨表拿 full 互比。

| 配置 | kp_hit@k | kp_mrr | Δ kp_mrr | cat@1 | empty | 证据数 |
|---|---|---|---|---|---|---|
| **full（基线）** | 0.9231 | **0.8174** | — | 0.8397 | 0.000 | 5.50 |
| no_l1 | 0.7115 | 0.6400 | **−0.177** | 0.8718 | 0.000 | 5.35 |
| no_l2 | 0.9359 | 0.8293 | +0.012 | 0.8590 | 0.000 | 5.21 |
| no_l3 | 0.9231 | 0.8225 | +0.005 | 0.8462 | 0.000 | 5.44 |
| l1_only | 0.9423 | **0.8678** | **+0.050** | 0.8974 | 0.000 | 5.09 |
| l2_only | 0.7115 | 0.6587 | −0.159 | 0.9038 | 0.000 | 5.27 |
| l3_only | 0.0000 | 0.0000 | −0.817 | 0.2051 | **0.769** | 0.94 |
| no_legacy | 0.9295 | 0.8423 | +0.025 | 0.8974 | 0.000 | 5.46 |
| legacy_only | 0.0256 | 0.0256 | −0.792 | 0.0000 | **0.833** | 0.49 |

**结论**

1. **L1 是检索主干**：去掉 L1 后 kp_mrr −0.177，是分层实验中最大的单点损失。
2. **L1 单层高于 full**（+0.050）；`no_l2` +0.012、`no_l3` +0.005、`no_legacy` +0.025 也为正：
   在当前的 RRF 权重与阈值下，L2/L3/legacy 的加入对**知识点检索切片**有轻微稀释。
   这不等于「L2/L3 无用」——它们承担方法/真题/安全场景，单指标 kp_mrr 覆盖不到
   （见 `docs/EXPERIMENTS.md` §9.2 的任务导向结论）。
3. **L2/L3 单独不可用**：`l2_only` kp_mrr 0.6587；`l3_only` 空结果率 **76.9%**，
   `legacy_only` 空结果率 **83.3%** —— 覆盖率不足，必须与 L1 组合。
4. **legacy 对排序略有稀释**（no_legacy +0.025），但它的价值在 `grade/explain` 场景的
   旧题库对照，不能只凭 kp_mrr 判定。

---

## 二·补、重排对照（2026-11-05，全量 156）

**归档**：`evals/results/retrieval/ablation/rerank_compare_20261105_deepseek41.json`

| 配置 | kp_hit@k | kp_mrr | cat@1 | 证据数 |
|---|---|---|---|---|
| full（rerank on） | 0.917 | 0.8287 | 0.904 | 2.99 |
| no_rerank | 0.936 | 0.8322 | 0.872 | 5.64 |
| **Δ（rerank 带来）** | −0.019 | −0.004 | **+0.032** | **−2.65** |

**结论**：重排在知识点级排序上略负（kp_mrr −0.004 / kp_hit −0.019），但**类别命中 +0.032**，
并把证据数从 5.64 压到 2.99。生产默认 `RERANK_ENABLED=false` 不变；论文表述应为
「提升类别命中、压缩证据数，知识点级收益不稳定」。

## 三、共同结论（论文可直接引用）

| 主题 | 结论 | 证据 |
|---|---|---|
| 多路召回 | BM25 贡献最大（−0.091）；整体多路优于纯向量（−0.030） | 组件消融 |
| 元数据路由 | 当前配置下为负贡献（+0.037），需细分复核 | 组件消融 |
| 查询分解 / HyDE | 中性（−0.007 / +0.004） | 组件消融 |
| 层 top-up | 只增覆盖（+1.37 条），不改排序 | 组件消融 |
| 知识分层 | L1 为主干；单层检索以 L1 最优 | 分层消融 |
| 重排 | 类别命中 +0.032；kp_mrr −0.004；证据数 −2.65 | 重排对照 |

---

## 四、已知局限与待办

1. **组件与分层是两次独立进程**：两次 full 相差 0.013（0.8309 / 0.8174），属 HyDE/分解的
   LLM 非确定性。各表内部用同轮 full 比较，**不要跨表拿 full 互比**。
2. **元数据负贡献未归因**：下一步按 `concept_meta` / `section_meta` / `exercise_meta` /
   `code_meta` 等逐条关掉，定位是哪一路引入噪声。
3. **单轮读数**：HyDE / 查询分解调用 LLM，存在轻微 run-to-run 抖动；关键结论的幅度均大于
   `docs/ARCHITECTURE_RETRIEVAL.md` §6.3(b) 的噪声地板（约 ±0.003）。
4. **指标切片有限**：kp_* 只覆盖知识点检索，不覆盖任务级效果（出题/批改/记忆），
   后者见 `paper_tables.md` 表 7 / 表 8。

---

## 五、与旧代际的关系

- `paper_tables.md` 表 2 / 表 4 与 `docs/EXPERIMENTS.md` §2 / §9 的旧数字（V-2026-10-02）
  是 **2026-10-10 语料换代之前**的读数，**不可与本文行对行比较**。
- 本文数据为现行代际（2026 chunk / 10 集合）；旧表保留为代际锚点，不覆盖。
