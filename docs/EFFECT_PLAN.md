# EFFECT_PLAN — 效果完整度提升方案（草案 v3）

> 目标（**已重定义**）：不用「完整度 75%」这类**无数学意义**的项目管理数字当论文指标。
> 论文口径 = **「系统效果表」+「系统工程表」**。
> 边界：**工程化已够**，本方案**只补效果，不铺工程**。
> 版本锚点：`V-2026-10-02`（`e36c766`）。★ **动检索链 → 新版本 + 全量重跑 + 重录门禁 + 换论文数**。
> 闭环：**Phase 0 测量 → Phase 1 优化 → Final Gate 验收**。
> 状态：草案 v3，待审。

---

## 0. 目标重定义

### 0.1 系统效果表（**论文指标**）

| 能力 | diagnostic（诊断） | final（终评） | 核心指标 | 目标（占位，Phase 0 后校准） |
|---|---|---|---|---|
| **QA** | 15 | 30 | `final_quality ≥ 4` 占比 | ≥ 80% |
| **Generate** | 15 | 30 | **五项完整交付率** | ≥ 75% |
| **Grade** | 15 | 30–50 | **`score_tolerance@±10`** | ≥ 75% |
| **Verify** | 15 | 30 | `question_id_recall@k` + `final_quality` | ≥ 80% |
| **Memory** | 5–10 | 10–20 | **correct-use rate** | ≥ 80% |

> ★ **两套样本量，两个用途，论文里不冲突**：
> **15 = diagnostic baseline**（诊断，定位问题）；**30+ = final evaluation set**（终评，出论文数字）。
> 「为什么前面 15、后面 30？」→ 答案就是这个。

### 0.2 系统工程表

| 项 | 状态 |
|---|---|
| RAG 检索（8 阶段链） / Evidence Policy / Task-aware routing | ✅ |
| 多 Agent / Memory / Tool calling | ✅ |
| Evaluation / Provenance / CI·Gate | ✅ |
| **E2E Demo（全链路跑通）** | **⏳ 待验证** |

### 0.3 项目管理目标

「55% → 70–80%」**仅内部排期用**，不进论文。

---

## 1. 现状（效果基线，V-2026-10-02 归档）

### 1.1 检索（强）

kp_hit@k / kp_mrr（full）= **1.000 / 0.9625** · Task MACRO 0.944 · vs 基础 RAG +0.0875 · legacy 层精度 1.000

### 1.2 生成（弱，证据单薄）

faithfulness 0.759 · precision 0.684 · **recall 0.400** · relevancy 0.599
- `generate` context_recall **0.067**（reference 是题面、输出是新题 → **口径不成立**）
- `code` answer_relevancy 0.292（反推问题；且 4/5 是拒答）
- **样本 n=20（每类 5）→ 不足以作结论**

### 1.3 核心判断

1. **检索已强，别再调**（阈值/参数在「不做清单」有三次负收益先例）。
2. **RAGAS 是组件指标，不是任务指标** → 不可当成绩单。
3. 顺序：**先建"对任务的尺子" → 再用 RAGAS 做诊断桥**。

---

## 2. Phase 0 — 测量（**分 A/B 两段，不要混做**）

> ⚠️ 反模式：Smoke + Mini Evaluation 一起搞 → 工作量膨胀。
> **0A 只答"能不能跑"，不作效果结论；0B 才测效果。**

### 2.A — Smoke（每类 3–5 条，只验"跑得通"）

检查：Docker/TEI · FastAPI(`/health`) · Agent · Tool · Evidence Pack · Memory · 四种任务各走通一次 · SSE/前端 · **无 hard failure**。

**全链路**：`Docker → TEI → FastAPI → Agent → Retriever → Evidence Pack → LLM → 前端`

> ★ 只求"跑通"，不求效果；产出 = §0.2 工程表最后那个 ⏳ 转 ✅。
> ★ 现状：TEI / Docker **均宕** → 当前唯一硬阻塞。

### 2.B — 真实效果基线（**测量，不修**）

#### 2.B.1 Demo Set

★ **不新建 `evals/manual/`** —— 接到现有 `scripts/agent_behavior_gate.py`，把 case 外部化为 jsonl。

```
evals/datasets/demo/{qa,generate,grade,verify,memory}_cases.jsonl
```

**规模（diagnostic baseline）**：QA/Gen/Grade/Verify 各 15 · Memory 5–10 ≈ **60–70 条**。

> ⚠️ 现有 `sample_408.jsonl` / `ragas_paired20.jsonl` **首行 `#` 注释头**，新 jsonl 沿用。

#### 2.B.2 rubric v1 — **task-aware**（统一 0–5 总分，判据按任务）

**QA / Verify**

| 分 | 判据 |
|---|---|
| 5 | 正确 + 切题 + 引用证据 + 结构完整 |
| 4 | 基本正确，小瑕疵 |
| 3 | 关键点缺 **或** 部分错 |
| 2 | 半数错 **或** 严重遗漏 |
| 1 | 答非所问 / 事实错 |
| 0 | 空 / 拒答 / 幻觉 / `hard_fail` |

**Generate**

| 分 | 判据 |
|---|---|
| 5 | 题目正确、考点明确、答案可判定、解析完整、符合题型 |
| 4 | 基本完整，轻微瑕疵 |
| 3 | 能用，但明显缺项 |
| 2 | 题目/答案有较严重问题 |
| 1 | 题目本身不可用 |
| 0 | 拒答 / 幻觉 / 崩溃 |

**Grade**

| 分 | 判据 |
|---|---|
| 5 | 结论正确 + 得分合理(±10) + 扣分点正确 + 反馈有帮助 |
| 4 | 结论正确，细微偏差 |
| 3 | 结论对，但得分/扣分有明显偏差 |
| 2 | 结论错，方向对 |
| 1 | 结论判反 |
| 0 | 空 / 崩溃 |

> ★ 统一 0–5 总分**保留**，但**判据 task-aware** —— 「答案好不好」≠「题出得好不好」。

#### 2.B.3 record schema

```
{
  case_id, task_mode, turns[], query,

  # 原始自动量 —— 最终报告只用这些
  kp_hit, kp_mrr, category_hit,
  pack_nonempty, pack_len, evidence_count,
  tool_calls[], latency_ms,

  # 判分量
  generation_ok,      # 是否产出【合法结果】（机械规则）
  final_quality,      # task-aware rubric 0–5
  failure_reason[],   # 完整故障链
  primary_failure,    # 根因

  # memory（仅多轮 case）
  memory_retrieved, memory_used, memory_correct,

  # 派生（仅供调试，不进报告）
  retrieval_ok,

  # provenance
  code_version, date, judge
}
```

**① `retrieval_ok` 不进报告。** 只用原始指标。
> `kp_hit=1 ∧ pack_nonempty=1` **不代表"检索就是好的"** —— L2 污染 40% 时目标证据仍在。

**② `generation_ok` ≠ 质量**，只答「**产出合法结果了吗**」：

| task | 合法 = |
|---|---|
| QA / Verify | reply 非空 且 无 `hard_fail` |
| Generate | 三件套字段可解析 |
| Grade | `score` + `feedback` 字段可解析 |

→ **`generation_ok` 管"有没有产出"，`final_quality` 管"产出多好"。两维不混。**

**③ `failure_reason` 允许多个 + `primary_failure`**：

```json
"failure_reason": ["retrieval_miss", "generation_incomplete"],
"primary_failure": "retrieval_miss"
```
→ 可画因果链：`retrieval_miss → evidence_insufficient → generation_incomplete`。

枚举：`retrieval_miss` · `retrieval_dropped` · `evidence_pollution` · `generation_wrong`
· `generation_incomplete` · `format_violation` · `tool_error` · `memory_miss`
· `hallucination` · `refusal` · `none`

#### 2.B.4 Memory —— 拆三维，**报告四率**

| 字段 | 报告为 |
|---|---|
| `memory_retrieved` | retrieval rate |
| `memory_used` | usage rate |
| `memory_correct` | correctness |
| —— | **correct-use rate = `retrieved ∧ used ∧ correct`**（主指标） |

> 例：一轮「我考 408，目标 120」→ 二轮「安排今天学习」：
> `retrieved=true, used=false` 与 `true/true/true` **不是一个质量等级**。
> ★ 答辩被问「Memory 80% 哪来的？」→ **直接拆因果链**。

> ★ 口径提醒：live 路径 = **时间序 recent episodes + profile**；
> `memory/vector_search.asearch_episodes`（语义召回）是**死代码**。评测须声明测的是哪条。

#### 2.B.5 ★ Exit Criteria（**Phase 0 到此为止**）

**跑满**：0A Smoke 全通过 + 0B 每类达标（QA/Gen/Grade/Verify 各 15、Memory 5–10）。

**产出这张表 → Phase 0 立即结束**：

| Task | n | 平均 final_quality | 失败率 | 主失败原因 |
|---|---|---|---|---|
| QA / Generate / Grade / Verify | 15 | ? | ? | ? |
| Memory | 5–10 | ? | ? | ? |

> ★★ **不要在 Phase 0 修任何效果问题。** 唯一允许修：① 环境；② case runner 的 bug；③ 记录系统本身的 bug。
> 效果问题**只记录、不修**，留给 Phase 1。

---

## 3. Phase 1 — 优化（按 Phase 0 的最大失败类型定序）

> **重排依据**：RAGAS 是组件指标；真正效果证据 = **任务级指标 + RAGAS + 人工 rubric + 失败归因**，四者结合。

### 3.1 四张任务表

**★ QA**（`learn`/`method`/`explain`）：Correctness · Groundedness（复用 gate）· Completeness ·
Source Cited（✅）· Clarity —— 判据按 mode 微调。

**★ Generate**（`practice`）

| 指标 | pass 判据（**规则现在固定；阈值 Phase 0 前冻结**） |
|---|---|
| `completeness_pass` | 题干 + 选项/要求 + 标准答案 + 解析 **齐全** |
| `answerability_pass` | 给定资料**足以唯一/明确判定**答案 |
| `knowledge_coverage_pass` | 命中 `expected_kp` |
| `correctness_pass` | gold 判定**正确** |
| `difficulty_match_pass` | 与 `expected_difficulty` **在允许档位内**（档位容差须冻结） |

```
five_of_five = completeness_pass ∧ answerability_pass ∧ knowledge_coverage_pass
             ∧ correctness_pass ∧ difficulty_match_pass

五项完整交付率 = five_of_five 占比        ← 论文主指标
```

> ★★ **"怎么算 pass"现在固定，"阈值"Phase 0 前冻结** —— 否则 Phase 0 跑完又会纠结「这题算 4 还是 5」。
> ★ 主表报五项 + 此率，**不简单平均**。

**★ Grade**（`grade`）—— **与 Generate 同级**，final n ≥ 30（理想 50）

> ★ **项目实况**：Grade agent **本来就输出 0–100**（`schema/grading.py`：`score: int, ge=0, le=100`）
> → **无需归一化**。但「±1 分」源自满分 10 的假设，在 0–100 制下 = **1%，过严**。

| 指标 | 计算 | 自动？ |
|---|---|---|
| **`score_tolerance@±10`** | `\|model − human\| ≤ 10`（0–100 制） | ✅ ← **头号** |
| `score_mae` | `mean(\|model − human\|)` | ✅ |
| `score_exact_match` | 完全同分率（次要） | ✅ |
| `feedback_quality` | rubric | 判 |

→ **gold（人工分）同样标 0–100**；★★ **`score_tolerance = ±10 pp` 已拍板锁定（2026-10-04）**
—— **不等 Phase 0、不用 ±5**。做 Grade gold 前即按此执行。
→ 第二阶段 `Weighted Cohen's Kappa` **仅当 n≥50 且有分布**。

**★ Verify**（`verify`）—— **进核心**（区别于普通 RAG Chatbot 的关键）

> ★ **项目实况**：`knowledge/exams/YYYY/items.md` 每条带 `question_id`（如 `2020-Q1`）+
> `answer_key` + `score` + `kp_ids` → **Verify 指标可算，无需造数据**。

| 指标 | 定义 | 自动？ |
|---|---|---|
| **`question_id_recall@k`** | `\|预测 id 集 ∩ gold 集\| / \|gold 集\|`；<br>若系统只返回一题 → `hit = predicted ∈ expected` | ✅ |
| `answer_availability` | 命中题是否带 `answer_key` | ✅ |
| `exam_hit@k` | 真题 chunk 命中@k | ✅ |
| `evidence_grounded` | 解析来自 KB | 半自动 |
| `final_quality` | rubric | 判 |

★ **不看 `layer_hit`**（对学科盲，`optimization_checklist` B1）。★ **本项关掉 OPEN 项 B2**。

### 3.2 人工基准集（gold）

在 Phase 0 的 demo set 上**加量 + 加 gold**（**不建第二套**）：
`gold_points`（QA）· `expected_kp`/`expected_difficulty`/gold 答案（Generate）·
`human_score`（0–100）/`full_marks`（Grade）· `expected_question_ids`（Verify）。

★ **表格下必须有失败分解**：每指标配 `failure_reason` 分布 + 2–3 样例 —— **"深挖"与"报个率"的分水岭**。

### 3.3 分析生成侧问题（归因）

用 §3.1 体系在 §3.2 数据上跑 → 失败模式分布 → 驱动下一步。

### 3.4 RAGAS —— **辅助通用指标，必要时才跑**

★ **不放在前面。** 顺序：Phase 0 基线 → 定最大失败类型 → **判定需要时才** RAGAS 20→60。
它"某些 query type 指标口径有问题"已被证明（`generate` 0.067 / `code` 0.292），
**不能当整个项目的唯一效果真相**。

### 3.5 Code —— 边界能力（不并列）

code **不是核心任务轴**。实测 4/5 拒答，根因是**知识库代码素材不足** → 严格 grounded → **正确拒答**。
- 定位：「对 KB 不存在的代码实现，系统识别证据不足并**拒绝编造**；对已有内容正确召回作答」。
- 口径：`answer_relevancy` 结构不适用；`faithfulness` **也不能当证据**（`#19/#20` 的 1.0 是
  "拒答未与证据冲突"的**平凡高分**）。保留小检查：拒答正确性（`#17` 该拒 ✔ / `#16` 不该拒 ✘）。

---

## 4. Phase 1.5 — L3 覆盖诊断（**gated**）

先测（用 §3.1 Verify 的 30 cases）：

| 判据 | 结论 |
|---|---|
| L3 recall ≈70% **且** `final_quality` ≈4.4/5 | **不修** |
| L3 recall ≈45% **且** 70% 低质量回答因真题缺失 | **才开 `V-2026-10-03`** |

---

## 5. Phase 2 — 检索短板（**仅必要时**）

| 项 | 代价 | 倾向 |
|---|---|---|
| **L2 跨学科污染 40%** | 修（学科感知过滤，全量重跑）/ 披露 | **披露**（收益集中 `l2_only` 消融） |
| **L3 真题召回** | 由 §4 判定 | 由 §4 决定 |

---

## 6. Final Gate — 验收（**毕业版 Exit Criteria**）

**闭环：Phase 0 测量 → Phase 1 优化 → 本 Gate 验收。**

| 维度 | 最低要求（**占位**，Phase 0 后按真实分布校准） |
|---|---|
| QA | ≥ 80% case `final_quality ≥ 4` |
| Generate | ≥ 75% 五项完整交付 |
| Grade | ≥ 75% `score_tolerance@±10` |
| Verify | ≥ 80% `final_quality ≥ 4` |
| Memory | ≥ 80% correct-use rate |
| Retrieval | **不低于 V-2026-10-02** |
| hard failure | < 5% |
| tool error | < 5% |
| provenance | 100% |
| Docker / TEI | 一键启动成功 |
| 四任务链 | 全部可演示 |

> ★★ **这些数字现在不要随便拍** —— 先跑 Phase 0，再据真实分布设定最终门槛。

---

## 7. 收尾 + Final Freeze

| 项 | 内容 |
|---|---|
| 7.1 dead code | `verifier.py` LLM 层 / `asearch_episodes` / `service.py:89` —— 每项「删 or 接线」 |
| 7.2 一致性 | 文档数字 ↔ 最新实验结果 |
| **7.3 Freeze** | 冻结 → 重跑全实验 → 写论文 |

---

## 8. 依赖与次序

```
Phase 0A Smoke ──► Phase 0B 诊断基线 ──► Phase 1 优化 ──► Phase 1.5（L3 闸门）
                                              │                    │
                                              │                    ▼
                                              │            Phase 2（仅必要时）
                                              ▼                    │
                                        Final Gate ◄───────────────┘
```

- **0A 卡所有**（无 TEI 全停）；0A 不过不进 0B
- **Phase 0 只测量，不修**
- Phase 1.5 是 Phase 2 的**闸门**

---

## 9. 不做清单

- ❌ 调检索阈值/参数（三次负收益先例）
- ❌ 换 LLM / embedding（除非体检发现崩）
- ❌ 铺广度（多模态、voice、多厂商）
- ❌ 重开 `merged_qa_meta` 路由（两轮净负）
- ❌ 把 `code` 的 `answer_relevancy` 当核心目标
- ❌ 硬上统计指标（Kappa）——数据不够就是不够
- ❌ **Phase 0 修效果问题**（只记录）
- ❌ **Smoke 与 Mini Evaluation 混做**

---

## 10. 风险与约束

| 风险 | 应对 |
|---|---|
| **E2E 跑不通**（论文说能力全，答辩跑不起来） | **0A Smoke 提前验证** |
| 环境依赖（TEI/Docker 宕） | Phase 0 先修 |
| 判分主观 | rubric 固定 + 阈值 Phase 0 前冻结 + 记 `judge` |
| 成本 | RAGAS 只跑冻结集、必要时才跑 |
| 检索改动连带 | 能披露就不修 |

---

## 11. 最小可交付（时间紧时）

**0A Smoke 跑通 + 0B 诊断基线（QA/Generate/Grade 三张表）** —— 把"生成质量"这一章从"站不住"变"站得住"。
L2/L3 全走披露、不修。

---

## 附：与现有文档的关系

| 文档 | 关系 |
|---|---|
| `RETRIEVAL_PLAN.md` / `RETRIEVAL_ROADMAP.md` | 检索执行 + 不做清单 |
| `EXPERIMENTS.md` | 实验总册（§3.4 数字落点） |
| `evals/reports/paper_tables.md` | 论文表（§3.1 新表并入） |
| `evals/reports/l2_impact_analysis.md` / `optimization_checklist.md` | L2 决策 + 问题清零（§3.1 Verify **关掉 B2**） |
| `scripts/agent_behavior_gate.py` | Phase 0 复用基建（case 外部化） |
