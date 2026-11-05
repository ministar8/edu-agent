# 论文实验表（可直接粘贴）

> **全部表均为现行代际（2026-11-04/05）**。
> 检索：全量 156 或前 60 条黄金集 · 生产索引 2026 chunk / 10 集合 · 真 TEI bge-m3 ·
> `RERANK_ENABLED=false` · RAG LLM `dashscope:deepseek-v4.1-flash`。
> 效果：task_eval 生成 `deepseek:deepseek-flash` + judge `qwen3.8-max-0902`；
> RAGAS 生成 `qwen3.8-max-0902` + judge `deepseek:deepseek-flash`（strictness=1）。
> 检索消融完整数据与口径见 [`rag_ablation.md`](rag_ablation.md)。
> 样本：检索 = 全量 156（表 2/3）或前 60（表 1/4/5）· 任务集 66 条 · 门禁 156 条

---

## 表 1 基础 RAG 对比（2026-11-05）

> 口径：黄金集前 60 条 · 生产索引 2026 chunk · 真 TEI bge-m3 · `RERANK_ENABLED=false` ·
> RAG LLM `dashscope:deepseek-v4.1-flash`。归档 `basic_rag_compare_20261105_deepseek41.json`。

| 指标 | basic_rag | ours | Δ（ours−basic） |
|---|---|---|---|
| kp_hit@k | 1.000 | 1.000 | 0.000 |
| kp_mrr | 0.9417 | 0.9236 | **−0.018** |
| cat@1 | 0.933 | 0.933 | 0.000 |
| cat_mrr | 0.9625 | 0.9597 | −0.003 |
| 平均证据数 | 4.37 | 5.88 | +1.52 |

> **任务口径**：六模式 `layer_hit` 逐项相同，MACRO 0.944 / 0.944（Δ 0）。
> **结论**：`ours` 在 kp_mrr 上**不再优于**朴素向量，增益只在证据数量。
> 与表 2（元数据负贡献）、表 3（L1 单层最优）指同一现象：当前融合权重对 kp_mrr 有稀释。

---

## 表 2 检索组件消融（2026-11-04）

> 口径：全量 156 · 生产索引 2026 chunk · 真 TEI bge-m3 · `RERANK_ENABLED=false` ·
> RAG LLM `dashscope:deepseek-v4.1-flash`。归档 `component_ablation_20261104_full156_deepseek41.json`；
> 本轮 `real_fail=0 / llm_fail=0`。

| 配置 | kp_hit@k | kp_mrr | Δ kp_mrr | cat@1 | 证据数 |
|---|---|---|---|---|---|
| **full** | 0.923 | **0.8309** | — | 0.872 | 5.55 |
| no_bm25 | 0.808 | 0.7403 | **−0.091** | 0.789 | 4.31 |
| no_metadata | 0.968 | 0.8675 | **+0.037** | 0.897 | 5.80 |
| no_decompose | 0.936 | 0.8236 | −0.007 | 0.853 | 5.01 |
| no_hyde | 0.923 | 0.8347 | +0.004 | 0.872 | 5.56 |
| vector_only | 0.878 | 0.8010 | −0.030 | 0.821 | 5.01 |
| plus_topup | 0.949 | 0.8365 | +0.006 | 0.872 | 6.92 |

> **结论**：BM25 是唯一大幅正贡献（−0.091）；**元数据路由为负贡献**（+0.037）；
> 分解 / HyDE 接近中性（−0.007 / +0.004）；top-up 只增覆盖（5.55→6.92）。

---

## 表 3 L1/L2/L3 单层保留（2026-11-05）

> 口径：全量 156 · 生产索引 2026 chunk · 真 TEI bge-m3 · `RERANK_ENABLED=false` ·
> RAG LLM `dashscope:deepseek-v4.1-flash`。归档
> `layer_ablation_20261105_full156_deepseek41_withfull.json`；`real_fail=0 / llm_fail=0`。
> Δ 均相对**同轮** full。

| 配置 | kp_hit@k | kp_mrr | Δ kp_mrr | empty |
|---|---|---|---|---|
| **full** | 0.923 | **0.8174** | — | 0.000 |
| no_l1 | 0.712 | 0.6400 | **−0.177** | 0.000 |
| no_l2 | 0.936 | 0.8293 | +0.012 | 0.000 |
| no_l3 | 0.923 | 0.8225 | +0.005 | 0.000 |
| l1_only | 0.942 | **0.8678** | **+0.050** | 0.000 |
| l2_only | 0.712 | 0.6587 | −0.159 | 0.000 |
| l3_only | 0.000 | 0.0000 | −0.817 | **0.769** |
| no_legacy | 0.930 | 0.8423 | +0.025 | 0.000 |
| legacy_only | 0.026 | 0.0256 | −0.792 | **0.833** |

> **结论**：L1 是主干（no_l1 −0.177）；L1 单层高于 full（+0.050），L2/L3/legacy 在当前融合权重下
> 对知识点检索有轻微稀释；L2/L3 单独覆盖不足（l3_only 空结果 76.9%），不能脱离 L1 使用。

---

## 表 4 Task Mode × Layer Policy（2026-11-05）

> 口径：每任务模式 6 条 · 生产索引 2026 chunk · 真 TEI bge-m3 · `RERANK_ENABLED=false` ·
> RAG LLM `dashscope:deepseek-v4.1-flash`。归档
> `task_mode_x_layer_policy_20261105_deepseek41.json`。安全字段冻结，只动 `preferred_layers`。

| policy | macro_layer_hit | 说明 |
|---|---|---|
| flat | 0.944 | 全层平铺（baseline） |
| **ours** | **0.944** | 任务映射 |
| prefer_l1 | 0.778 | 固定偏 L1 |
| prefer_l2 | 0.778 | 固定偏 L2 |
| prefer_l3 | 0.944 | 固定偏 L3 |

> 逐模式：`grade` 0.667（flat/ours/prefer_l3）、0（prefer_l1/l2）；`explain` 0.667（prefer_l1/l2）；
> `pack_nonempty_rate` 全任务 × 全策略 **1.000**。
> **结论**：`ours` 与 `flat` 命中相同，层偏好单独不抬 hit；错误层偏好伤害仍在（0.778）。

---

## 表 5 检索补充实验（2026-11-05）

### 5.1 阈值敏感性（60 条）

> 归档 `threshold_sensitivity_full_20261105_deepseek41.json` 与
> `threshold_sensitivity_vector_only_20261105_deepseek41.json`。

| arm | scale 1.0 | 0.95 | 0.90 | 0.85 | 0.0 |
|---|---|---|---|---|---|
| **full** kp_mrr | 0.9236 | 0.9236 | 0.9236 | **0.9361** | **0.9361** |
| full fallback | 1 | 1 | 1 | 0 | 0 |
| vector_only kp_mrr | 0.9208 | 0.9208 | 0.9208 | 0.9208 | 0.9208 |

> **结论**：full 到 **0.85×** 才出现正收益（+0.012），vector_only 五档不变；默认阈值不改。

### 5.2 重排对照（156 条）

> 归档 `rerank_compare_20261105_deepseek41.json`；`RERANK_ENABLED=true` 对照 `no_rerank`。

| 配置 | kp_hit@k | kp_mrr | cat@1 | 证据数 |
|---|---|---|---|---|
| full（rerank on） | 0.917 | 0.8287 | 0.904 | 2.99 |
| no_rerank | 0.936 | 0.8322 | 0.872 | 5.64 |
| **Δ（rerank 带来）** | −0.019 | −0.004 | **+0.032** | **−2.65** |

> **结论**：重排提升类别命中（+0.032）、压缩证据数（−2.65），知识点级排序收益不稳定；
> 生产默认关闭。

### 5.3 L2 覆盖归因（6 条 method query）

> 归档 `l2_coverage_20261105_deepseek41.json`。

| 指标 | 读数 |
|---|---|
| L2 总 chunk | **98**（DS 38 / OS 21 / CO 20 / CN 19） |
| method query L2 进包 | **6/6** |
| pack 中 L2 chunk | **12** |
| 错学科 | **0**（污染率 0.0%） |

> **结论**：L2 的覆盖率与纯度不再是短板；`l2_only kp_mrr` 偏低（0.6587）需从池规模/排序另查。

### 5.4 legacy 池策略

> 归档 `legacy_runtime_20261105_deepseek41.json`。

| 策略 | recall@pack | prec@pack | legacy 进包 |
|---|---|---|---|
| keep | 1.000 | 1.000 | 0 |
| downrank | 1.000 | 1.000 | 0 |
| drop | 1.000 | 1.000 | 0 |

> **结论**：现行索引由 `ingest_layers` 六层重建，**已不含 legacy 资产**，三策略不可区分；
> 该对比不再适用于当前系统。系统仍采用 `legacy_policy=exclude` + `fallback`（grade/explain）。

### 5.5 组件方差（3 进程 × 60 条）

> 归档 `component_variance/summary.json`；**只测系统稳定性，不用于判断组件贡献**。

| config | kp_mrr mean±std | cat@1 mean±std |
|---|---|---|
| full | 0.9236±0.000 | 0.933±0.000 |
| no_bm25 | 0.922±0.001 | 0.900±0.000 |
| no_metadata | 0.919±0.000 | 0.950±0.000 |
| vector_only | 0.915±0.005 | 0.900±0.000 |

> **结论**：三跑 std ≤ 0.005；60 条子集的 Δ 与全量 156 量级/方向不同，
> 组件贡献一律以表 2（全量）为准，本节只说明“系统是稳的”。

---

## 表 F1 失败案例归因（2026-11-05 复核）

> 选取标准：黄金集/任务集中**可复现、且根因已定位**的代表性失败。
> 「处置」列区分**已修进本版本**与**已决策不修**。

| 案例 | 失败模式 | 根因 | 处置 | 证据 |
|---|---|---|---|---|
| q052（inode）纯向量 | 目标入池后丢失 | 向量路由按 `-score` 降序；Chroma score 是**余弦距离**（越小越好）→ 取到最不相似的 k 条 | **已修**：改升序取前 k | `rag/routes.py`；修后 semantic **rank 1** |
| 「单链表就地逆置」 | 目标 chunk 召不回 | 三层叠加：① jieba 切成「表逆置/地逆置」 ② 同义词守卫按**子串**判定，「逆置」永不追加 ③ 排序方向（同上） | **已修**：领域词 + 守卫改分词结果 + 排序 | `rag/rag_utils.py` · `rag/synonyms.py` · `rag/routes.py` |
| verify 真题 | 答案先注入后被裁空 | top-up 只按 `kb_depth` 找，未继承 `eligibility_where` | **已修**：top-up 与主检索共用 where | `rag/layer_recall.py` · `rag/retriever.py` |
| practice 任务 | 空证据包 | ① preferred 层不合规时 top-up 空转 ② 包被裁空无兜底 | **已修**：层回退 + `pack_blocked()` 回填 | `schema/task_policy.py` · `rag/evidence_policy.py`；pack_nonempty **1.000** |
| 「滑动窗口协议」 | kp_hit 掉分 | **golden 单标签口径**：同主题 L38 标传输层 / L163 标数据链路层 | **已修**：补第二标签（纯数据修正） | `sample_408.jsonl` L38 → `["数据链路层","传输层"]` |
| LRU / 平衡二叉树 / TCP 拥塞控制 | 进包 L2 错学科 | `preferred_layers` 提升**所有** advanced；L2 池小（98），错学科靠通用词面挤进 pack | **本代际未复现**：12 条 L2 进包、0 错学科；6/6 method query 进包 | 表 5.3 |
| q052 vector_only | 目标被阈值滤掉 | 召回到了（rank 2）但 `rrf_threshold` 0.0857 < 0.088 | **未修**（属不做清单） | 表 5.1；非召回失败 |

**读法**：7 例中 5 例已修，集中于**排序方向 / 资格边界 / 标注口径**三类根因；
1 例（L2 跨学科污染）在现行代际**未复现**；1 例（阈值标定）未修，属策略层取舍。

---

## 表 F2 已知局限与处置（2026-11-05 复核）

| 局限 | 影响面 | 处置决策 | 论文披露口径 |
|---|---|---|---|
| L2 跨学科污染 | 现行代际 **0/12**（旧体系 40%） | **已不复现** | 不再作为短板；`l2_only` 偏低另查池规模/排序 |
| rerank 收益符号不稳 | 现行 Δ = **−0.004**（kp_mrr）/ **+0.032**（cat@1） | **默认关闭**（`RERANK_ENABLED=false`） | 写「收益不稳定」，**不写**「负优化」 |
| 元数据路由负贡献 | 去掉后 kp_mrr **+0.037** | **待归因**：按具体 meta 路由细分 | 如实报负贡献，列为后续工作 |
| RRF 阈值 > 可达上限 | 阈值按 k=20 标定、实际 k=36 | **不改默认阈值**；记入不做清单 | 属量纲错配，非检索能力问题 |
| decompose / HyDE 接近中性 | 现行 Δ = −0.007 / +0.004 | **保留启用** | 如实报中性 |
| 语义缓存 | 会把「缓存命中」混进「检索质量」 | **默认关闭**（`SEMANTIC_CACHE_ENABLED=false`） | 不参与主表 |
| L3 不作通用知识库 | `l3_only` empty **76.9%** | **设计定位，非缺陷** | 写「考试资源层」；grade/verify 下不可替代 |

---

## 图 1（建议）：任务 → 层 → 策略

```
Task Policy ──► Retrieval Plan ──► Evidence Pack
   learn ──────── L1 优先 ──────── exclude legacy
   method ─────── L2 优先 ──────── exclude legacy
   practice ───── L2+L3 ─────────── exclude + 禁答案
   grade ──────── L3 优先 ──────── fallback legacy
   verify ─────── L3 优先 ──────── exclude 答案
```

---

## 表 6 任务级效果表（2026-11-05，现行 · 干净锚点 `fa76f48`）

> 来源 `evals/results/task_eval/ec_r5_20261105.jsonl`（66 条：qa/verify/generate/grade 各 15 + memory 6；
> gold **frozen 66/66**）；`provenance.code_version = fa76f48`（工作区干净、无 `-dirty`）。
> 生成 agent `deepseek:deepseek-flash`；judge `dashscope:qwen3.8-max-0902`；检索 rerank off。
> ★ 与 2026-10-16 旧版**不可直接比较**（judge 与生成口径均变）。
> **每个数字必须带分母**；n=1/2 的率不是能力率（D15）。

| 维度 | 主指标 | 读数 | 备注 |
|---|---|---|---|
| QA | `final_quality≥4` | **1.000**（15/15） | μ4.933；失败率 0.000 |
| Generate | `quality_pass` | **0.800**（12/15） | μ4.333；失败率 0.200（generation_wrong×3） |
| Grade | `verdict_agreement` | **0.929**（13/14） | μ3.400；1 条判 N/A（回复解析不出分数）；`quality_pass` 0.467 仅反映 judge 严格度 |
| Verify | 仍出题率（硬条件） | **0.000**（15/15） | μ1.200；`quality_pass` 0.000（generation_incomplete×8、refusal×2、generation_wrong×2、hallucination×1） |
| Memory | correct-use rate | **0.800**（4/5，n_a=1） | 3 条 `case_invalid`（mem-004/005/006）；正样本 3/3 有效 |
| hard failure | `hard_fails` 非空 | **0.000**（66） | |
| tool error | `failure_reason` 含 tool_error | 0.061（4/66） | grd-011 / mem-004 / mem-005 / mem-006，均为副标签，`hard_fails` 为空 |

### 6.1 同配置复跑（重复性证据）

> 复跑归档 `evals/results/task_eval/ec_r4_20261105.jsonl`（`code_version=2ce9c71-dirty`）。
> 两次运行的代码差异仅 `fa76f48` 一个提交（移除 `/api/questions/*` 专用 HTTP API 与前端入口）；
> 该提交对 `src/agents`、`src/prompts`、`src/memory` 的改动**全是 docstring / 注释**，
> 删掉的端点在 service 层 ⇒ 效果链**行为等价**。
> 差异全部来自生成侧采样随机性：66 条中 65 条回复文本不同，`hard_fails` 差异 **0**，
> `memory_*` 判定差异 **0**。

| 维度 | ec_r4（复跑） | ec_r5（主） | 复跑区间 |
|---|---|---|---|
| QA `quality_pass` | 1.000（15/15） | 1.000（15/15） | 1.000 |
| Generate `quality_pass` | 0.667（10/15） | 0.800（12/15） | **0.667–0.800** |
| Grade `verdict_agreement` | 1.000（15/15） | 0.929（13/14） | **0.929–1.000** |
| Verify 仍出题率 | 0.000（15/15） | 0.000（15/15） | 0.000 |
| Memory correct-use | 0.800（4/5） | 0.800（4/5） | 0.800 |
| tool error | 0.045（3/66） | 0.061（4/66） | 0.045–0.061 |

> **读法**：n=15 时**一条 case = 6.7 个百分点**。翻转都发生在单条上——
> `gen-006/008/015`（2→5，judge 分）、`grd-009`（模型分 15→100，人类 0）、`grd-012`（回复解析不出分数）；
> 不是系统能力变化，是采样抖动。论文正文引用主读数 + 本区间，**不要**单点断言「Grade 完美」。

**读法红线**：① Grade 看 `verdict_agreement`，`quality_pass` 会随 judge 变严而下降，不能当系统退化；
② Memory 的 0.800 必须连同「n=5、3 条 case_invalid」引用；③ 与旧冻结版不可混排；
④ 表 6 的数字引用**必须**同时标注锚点 `fa76f48`（复跑读数标 `2ce9c71-dirty`）。

---

## 表 7 RAGAS（2026-11-05，现行）

> 生成 `dashscope:qwen3.8-max-0902`；judge `deepseek:deepseek-flash`；rerank off；
> `answer_relevancy.strictness=1`（DeepSeek 仅支持 n=1）。全量 156 条，四指标 n=156，无 dropped metrics。
> 归档 `ragas_freeze20261105.json` + `_samples.jsonl`。

| 指标 | 读数（n/156） |
|---|---|
| faithfulness | **0.7238** |
| context_precision | **0.7405** |
| context_recall | **0.4764** |
| answer_relevancy | **0.6598** |

> ★ 与 2026-10-16 旧版不可直接比较：生成模型、judge、rerank、strictness 四处口径全变。
