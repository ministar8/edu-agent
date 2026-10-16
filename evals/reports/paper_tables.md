# 论文实验表（可直接粘贴）

> 数字来源：表 1–表 6/F1/F2 为 `evals/results/` **V-2026-10-02**（见 EXPERIMENTS.md §18）
> **表 7/表 8 为冻结代（2026-10-16）**：任务级效果来自 `ec_r3_freeze_20261016.jsonl`（§20.7.8⑯），
> RAGAS 来自 `ragas_freeze20261016.json`（§20.7.8⑱）——两者与 V-2026-10-02 读数**口径不同**，
> 按 D1 纪律并列引用、不回写旧表。
> 完整论述见 `docs/EXPERIMENTS.md` · 问题诊断见 `evals/reports/rerun_summary.md`
> 样本：黄金集前 60 条（检索）· 任务集 25 条 · 门禁 156 条

> **旧表脚注（D1，2026-10-16）**：表 1–6 的检索读数在冻结期经 C2 六路由门禁复验
> 「所有指标不低于基线」（§20.7.8⑰①）——基线文件因黄金集哈希变更（`be98912a`→`783e78ff`）
> 已于 2026-10-14/15 做第三代重录（§20.7.4），重录后指标与旧读数同代际；
> 检索表数字仍归 V-2026-10-02，论文引用时带本脚注即可，**不得**与表 7 混排同一张效果表。

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

## 表 F1 失败案例归因（§14.4 / §16 / §18.2，V-2026-10-02）

> 选取标准：黄金集/任务集中**可复现、且根因已定位**的代表性失败。
> 「处置」列区分**已修进本版本**与**已决策不修**。

| 案例 | 失败模式 | 根因 | 处置 | 证据 |
|---|---|---|---|---|
| q052（inode）纯向量 | 目标入池后丢失 | 向量路由按 `-score` 降序；Chroma score 是**余弦距离**（越小越好）→ 取到最不相似的 k 条 | **已修**：改升序取前 k | `rag/routes.py`；修后 semantic **rank 1**（§18.2 #3） |
| 「单链表就地逆置」 | 目标 chunk 召不回 | 三层叠加：① jieba 切成「表逆置/地逆置」 ② 同义词守卫按**子串**判定，「逆置」永不追加 ③ 排序方向（同上） | **已修**：领域词 + 守卫改分词结果 + 排序 | `rag/rag_utils.py` · `rag/synonyms.py` · `rag/routes.py`（§18.2 #1–#3） |
| verify 真题 | 答案先注入后被裁空 | top-up 只按 `kb_depth` 找，未继承 `eligibility_where` | **已修**：top-up 与主检索共用 where | `rag/layer_recall.py` · `rag/retriever.py`（§15） |
| practice 任务 | 空证据包 | ① preferred 层不合规时 top-up 空转 ② 包被裁空无兜底 | **已修**：层回退 + `pack_blocked()` 回填 | `schema/task_policy.py` · `rag/evidence_policy.py`；pack_nonempty **1.000**（§12.3） |
| 「滑动窗口协议」 | kp_hit 掉分 | **golden 单标签口径**：同主题 L38 标传输层 / L163 标数据链路层 | **已修**：补第二标签（纯数据修正） | `sample_408.jsonl` L38 → `["数据链路层","传输层"]`（§18.2 #4） |
| LRU / 平衡二叉树 / TCP 拥塞控制 | 进包 L2 错学科 | `preferred_layers` 提升**所有** advanced；L2 池小（98），错学科靠通用词面挤进 pack | **未修**（§F2） | 污染 **4/10 = 40.0%**（§16.3） |
| q052 vector_only | 目标被阈值滤掉 | 召回到了（rank 2）但 `rrf_threshold` 0.0857 < 0.088 → `dropped_by=rrf_threshold` | **未修**（属不做清单） | §14.4；非召回失败 |

**读法**：7 例中 5 例已修，且集中于**排序方向 / 资格边界 / 标注口径**三类根因；
2 例未修均为**策略层取舍**（跨学科过滤、阈值标定），不是实现 bug。

## 表 F2 已知局限与处置（§18.4 / §19.2，V-2026-10-02）

| 局限 | 影响面 | 处置决策 | 论文披露口径 |
|---|---|---|---|
| L2 跨学科污染 **40.0%** | `l2_only` kp_mrr **0.7194**（分层短板） | **不修**（小诊断：叠加噪声非挤占，目标 6/6 在包）；方向若是学科感知过滤，**非补数据** | 报 40.0% + 「未观察到目标被挤出」；生成侧未测 |
| rerank 收益符号不稳 | Δ = **+0.012** / 更早 **−0.046** | **默认关闭**（`RERANK_ENABLED=false`） | 写「收益不稳定」，**不写**「负优化」 |
| RRF 阈值 > 可达上限 | 阈值按 k=20 标定、实际 k=36 | **不改默认阈值**；记入不做清单 | 属量纲错配，非检索能力问题 |
| decompose / HyDE 零增益 | 消融 Δ = 0 | **保留启用**（关闭无变化；HyDE 属低频兜底） | 如实报零增益，归因短查询占比 + k=5 预算 |
| 语义缓存 | 会把「缓存命中」混进「检索质量」 | **默认关闭**（`SEMANTIC_CACHE_ENABLED=false`） | 不参与主表 |
| L3 不作通用知识库 | `l3_only` empty **98.3%** | **设计定位，非缺陷** | 写「考试资源层」；grade/verify 下不可替代 |

## 图 1（建议）：任务 → 层 → 策略

```
Task Policy ──► Retrieval Plan ──► Evidence Pack
   learn ──────── L1 优先 ──────── exclude legacy
   method ─────── L2 优先 ──────── exclude legacy
   practice ───── L2+L3 ─────────── exclude + 禁答案
   grade ──────── L3 优先 ──────── fallback legacy
   verify ─────── L3 优先 ──────── exclude 答案
```

## 表 7 冻结代任务级效果表（2026-10-16，ec_r3_freeze_20261016；口径 = ledger §6 重算）

> 来源：`evals/results/task_eval/ec_r3_freeze_20261016.jsonl`（66 条：qa/verify/generate/grade 各 15 + memory 6；
> gold_status **reviewed 66/66**）。数字与 `evals/claims/ledger.md` §6 门槛行逐字同源（重算产物）。
> **每个数字必须带分母**；n=1/2 的率不是能力率（D15）。

| 维度 | 主指标（§6 口径） | 冻结代读数 | §6 门槛 | 达成判定 |
|---|---|---|---|---|
| QA | `final_quality≥4` case 占比 | **1.000**（已测 n=15） | ≥ 80% | 达成（judge 观点，tier 2 两前置未标定 ⇒「已测量未证明」） |
| Generate | 五项完整交付率 `gen_case_pass`（registry 逐题复合） | **N/A**（已测 n=0，missing_premise 15/15） | ≥ 75% | **未测量**——gold 依赖判据结构性缺前提，按 option B 作 limitation 披露，**不得折成 0 或 1** |
| Grade | `score_tolerance@±10` 头号；两极 gold ⇒ 行级改读 `verdict_agreement`（辅助位） | 头号 N/A（两极 gold 无判别力）；**verdict_agreement=0.933**（n=15） | ≥ 75% | 头号未测量；辅助位 0.933 只作披露 |
| Verify | 仍出题率 `ver_fabricated`（硬条件必须 0；D14 行为层） | **仍出题率 0.000**（pass 15/15 = 1.000） | 必须 0 | **达成**（硬条件）；L1 真题条目 0.133 / L2 年份归属 0.333 作诊断 |
| Memory | correct-use rate（正样本口径） | **1.000**（已测 n=2，missing_premise 4） | ≥ 80% | 数字达成但**分母极小**：正样本 3 条全不可测，可测 2 条均为负样本 ⇒ 按 D15 只作结构断言披露 |
| Retrieval | `kp_hit` 率（全任务池化） | 0.967（已测 n=30, n/a=30） | 不低于 V-2026-10-02 | 池化诊断位；与基线对比由 C2 门禁承担（六路由全过） |
| hard failure | `hard_fails` 非空占比（坏事率） | **0.000**（n=66） | < 5% | 达成 |
| tool error | `failure_reason` 含 tool_error 占比（坏事率） | **0.000**（n=66） | < 5% | 达成 |
| provenance | 八键齐全率 | **1.000**（n=66，从 0.000 转正） | 100% | 达成 |

**读法红线**：① Generate 行写「主指标未测量（结构性缺前提）」，**禁止**写 0.733/0.750 之类的门槛比较；
② Verify 的 `final_quality≥4`（μ=1.067）在 verify 上测的是检索覆盖，只作诊断，不得当通过判据（D14）；
③ Memory 的 1.000 必须连同「n=2、正样本不可测」引用；④ 各任务失败分布（照实）：Generate
generation_incomplete×8/generation_wrong×3/hallucination×1；Grade hallucination×1/generation_wrong×1；
Verify generation_incomplete×9/refusal×2/generation_wrong×1；Memory memory_miss×2（+4 条 case 无效）。

## 表 8 RAGAS 冻结版（2026-10-16，`ragas_freeze20261016.json`，全量黄金集 156 条）

| 指标 | 冻结版读数（n/156） | V-2026-10-02 锚点（n=20） | 可比性 |
|---|---|---|---|
| faithfulness | 0.8109（n=112） | 0.7588（n=20） | **不可比**（见下） |
| context_precision | 0.7454（n=113） | 0.684（n=20） | **不可比** |
| context_recall | 0.5963（n=108） | 0.400（n=20） | **不可比** |
| answer_relevancy | 0.7217（n=111） | 0.5994（n=20） | **不可比** |

> 运行口径：156 条全量（code 32 / concept 60 / generate 32 / grade 32）、真实 `BAAI/bge-m3`
> embedding（`embedding_fake=false`）、rerank 生效、judge=`dashscope:qwen3.8-flash`。
> **五处口径与锚点全不同**：judge 模型（`qwen3.8-max-0902`→`qwen3.8-flash`）、样本（n=20 分层→156 全量）、
> rerank（未生效→生效）、golden 哈希（`be98912a`→`783e78ff`）、代码代（`0479d6e`→`7220229`）。
> ⇒ 论文中两代读数**只能并列披露**，不得表述为「RAGAS 指标改善/退化」；各指标 n<156（judge 不可判样本
> 已剔除：faithfulness 缺 44、context_precision 缺 43、context_recall 缺 48、answer_relevancy 缺 45）。
