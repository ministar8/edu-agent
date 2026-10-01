# 全量重跑总结（RAGAS 除外）· 2026-09-30

> 口径：黄金集前 60 条 / 任务集 25 条 / 门禁 156 条；配置冻结。
> 新结果均为**规范文件名**，旧时间戳文件待删。

## 1. 新结果落点

| 实验 | 文件 | 状态 |
|---|---|---|
| 组件消融 | `retrieval/ablation/component_ablation.json` | OK |
| rerank 对照 | `retrieval/ablation/rerank_compare.json` | OK |
| Task-aware | `retrieval/ablation/task_layer_ablation.json` | OK |
| 基础 RAG | `retrieval/ablation/basic_rag_compare.json` | OK |
| L1/L2/L3 | `retrieval/layer_policy/layer_ablation.json` | OK |
| Task Mode × Layer Policy | `retrieval/layer_policy/task_mode_x_layer_policy.json` | OK |
| Legacy 三策略 | `retrieval/legacy_runtime/legacy_runtime.json` | OK |
| 门禁基线 | `baselines/retrieval_baseline.json` | 通过（未覆写） |
| Agent 行为 | `system_validation/agent_behavior/agent_behavior_quality.json` | 8/8 PASS |
| State 闭环 | `system_validation/langgraph_state/state_gate.json` | 4/4 PASS |
| RAGAS | `generation/ragas/` | **未动（PENDING）** |

## 2. 与旧数据对照（核心）

### 2.1 组件消融（kp_mrr）

| 配置 | 旧 Δ | 新 Δ | 判定 |
|---|---|---|---|
| full | 0.943 | **0.951** | 基线略升 |
| no_bm25 | −0.088 | **−0.062** | 贡献缩小 |
| no_metadata | −0.113 | **−0.026** | ⚠️ **大幅缩小** |
| vector_only | −0.158 | **−0.037** | ⚠️ **大幅缩小** |
| no_decompose / no_hyde | 0 | 0 | 一致（零增益） |
| plus_topup | 0 | 0 | 一致 |

### 2.2 rerank（符号翻转）

| | 旧 | 新 |
|---|---|---|
| full(rerank) − no_rerank | **−0.046** | **+0.015** |

### 2.3 稳定复现（与旧一致）

- Task-aware：learn +0.333 / method +0.167 / practice 泄漏 0.25→0 / MACRO +0.083
- L1/L2/L3：l1_only 0.944 · l2_only **0.704** · l3_only **0 / empty 98%** · no_legacy 0.882
- Legacy：drop 层精度 **1.000**（keep/downrank 仍 <0.5）
- 基础 RAG：kp_mrr **+0.078**（旧 +0.089）
- TMLP：ours=flat hit 包络；prefer_l3 空包复现（practice nonempty **0.25**）

### 2.4 系统验证

- retrieval_gate：全过（见问题 #6）
- leakage / mode_layer / topic / proof / state：全过
- agent_behavior：8/8 PASS，quality_score **0.148**（旧 0.159）

## 3. 问题清单（按严重度）

| # | 严重度 | 问题 | 证据 | 建议 |
|---|---|---|---|---|
| 1 | **高** | **组件消融贡献漂移**：metadata/vector_only 的 Δ 相对旧表大幅缩水 | no_metadata −0.113→−0.026；vector_only −0.158→−0.037 | 论文表 2 **必须用新数**；查是否旧表混了不同索引/轮次；固定 seed 后做 run-to-run 方差 |
| 2 | **高** | **rerank 结论不稳**：本轮 +0.015，旧 −0.046 | `rerank_compare.json` | 不要写死「rerank 负优化」；改为「在本黄金集上收益不稳定（−0.05～+0.02），默认关闭」 |
| 3 | 中 | **verify / grade 的 L3 命中偏低** | verify 两臂均 0.333；grade 0.667 | 与 L2 薄弱并列为检索覆盖缺口；考虑 verify 专用真题召回路由 |
| 4 | 中 | **L2 覆盖薄** | l2_only kp_mrr 0.704 | 与 coverage analysis 互印；补 L2 是后续工作 |
| 5 | 中 | **L3 不适合通用解释** | l3_only empty 98.3% | 保持「考试资源定位」叙事 |
| 6 | 中 | **prefer_l3 空包**（sufficiency） | practice nonempty 0.25；method 0.50；learn 0.667 | 主表已用 pack_nonempty_rate；错误偏好会经 eligibility 掏空包 |
| 7 | 低 | **基础设施抖动** | prefer_l1 臂 Chroma/embedding 异步失败；l3_only HyDE 10s 超时致 415s | 不改管线；记录为环境噪声；关键实验可重跑核对 |
| 8 | 低 | **retrieval_gate 判定口径** | kp_mrr 0.6636 < 基线 0.6698 仍显示「通过」 | 确认是否有容差；若无则是门禁 bug |
| 9 | 低 | decompose / HyDE 零增益 | 与旧一致 | 诚实报告；可归因短查询占比与 k=5 预算 |
| 10 | 低 | basic_rag 任务口径 method 臂漂移 | basic method 0.833→0.667 | 样本 n=6 噪声；主表用检索口径 |

## 4. 论文叙事可写 / 不可写

**可写**

1. 多路召回仍优于纯向量（vector_only 仍负，但幅度以**新数**为准）
2. Task-aware 层策略：learn/method 命中增益 + practice 零泄漏（稳定复现）
3. 三层服务不同任务；L3 面向考试资源（l3_only 不适合通用库）
4. Legacy 必须 exclude（层精度 → 1.000）
5. 错误层偏好导致空包（pack_nonempty_rate）
6. 基础 RAG 对比：kp_mrr +0.078

**必须改口径**

- ~~「metadata 贡献最大（−0.113）」~~ → 新数 −0.026，且 vector_only −0.037；**贡献排序可能重排**
- ~~「rerank 负优化 −0.046」~~ → **符号不稳**，改为不稳定/默认关

**不外推**

- L1 优势仅在「当前知识点检索任务」
- component Δ 的 run-to-run 方差尚未量化

## 5. 完成状态（2026-09-30）

- [x] 删除历史时间戳与 `results/archive/`
- [x] 用新数覆写 `docs/EXPERIMENTS.md` + `evals/reports/paper_tables.md`
- [x] P0.1 消融方差（3 独立进程）→ `component_variance/`；full 等 std≈0
- [x] E-next 阈值敏感度 → `threshold_sensitivity/`；**不改默认 threshold**
- [x] q052 归因：召回到但被阈值滤掉（弱路由）；不再继续优化
- [ ] 转向真实短板：L2 覆盖 · verify L3 召回 · pack sufficiency 兜底
- [ ] RAGAS 仍 PENDING，单独处理
