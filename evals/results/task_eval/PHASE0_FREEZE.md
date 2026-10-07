# Phase 0B 冻结快照（2026-10-06）

> **状态**：`gold_status = reviewed`（**非 frozen**，用户 2026-10-06 裁决）
> 出论文数字前需最终升为 `frozen`。

---

## ★ Phase 版本一览（**Phase 0B 冻结基线未被修改**）

| 版本 | 文件 | 说明 |
|---|---|---|
| **Phase 0B（frozen 参照系）** | `phase0_baseline_final.jsonl` | **本文件所描述。只读，Phase 1 未改动它一个字节。** |
| **Phase 1（新实验版本）** | `phase1_baseline_v2.jsonl` | Verify 修复后重跑（2 处 prompt 改动） |

**Phase 1 是独立实验版本**，不改写 Phase 0B。两者配置**相同**
（agent=`deepseek:deepseek-flash` · judge=`qwen3.8-flash` · RAG=`qwen3.7-flash`），
**差异只在 agent 的 prompt**。

### Phase 1 结果摘要（详见 `PHASE1_VERIFY.md`）

| Task | Phase 0B | Phase 1 | Δ |
|---|---|---|---|
| QA | 4.333 | **4.667** | +0.333 |
| Generate | 4.800 | 4.733 | −0.067 |
| Grade | 5.000 | 4.133 | −0.867（**非回归**，见下） |
| Verify | 1.133 | **1.267** | +0.133 |
| Memory | 2.833 | 2.833 | 0.000 |

**Verify 行为**：仍出题 **6/15 → 0/15** ✅ · 有真题信息 **3/15 → 9/15** ✅
**检索侧**：`kp_hit` / `exam_hit` **逐位一致** ✅ ⇒ 检索链未动
**Grade**：`score_tolerance` 仍 **1.000** ⇒ 判分能力未退化；−0.867 为**既有偶发失败**

---

## 0. 冻结一致性检查（4 项，2026-10-06）

### ✅ 检查 1：代码版本三者对应

| 项 | 值 |
|---|---|
| `code_version` | **`648d819-dirty`** |
| `golden_sha256` | **`be98912a4c91fb88151640c82515127465031c1e79382b99c40e32311d6d1a66`** |
| git HEAD | `648d819 docs: EFFECT_PLAN 转定稿 v1.0` |
| 未提交改动 | 13 个文件 |

**⚠️ 修复了一个真 bug**：`build_provenance()` 把 `code_version` 放在**嵌套的 `provenance`** 里，
而 `runner.py` 从**顶层**取 ⇒ **归档里的 `code_version` 一直是空字符串（66/66）**，
导致「冻结快照 ↔ 代码版本」**无法对应**（本检查第一项原本直接失败）。

- **已修**：`runner.py` 改读 `prov["provenance"]["code_version"]`，并新增 `golden_sha256` 字段。
- **已补录**：66 条记录填上上述值，并标 **`provenance_reconstructed: true`**
  （诚实标注：**事后补录**，非运行时记录）。

**⇒ 检查 1 通过（含修复）。**

### ✅ 检查 2：Phase 1 不修改 Phase 0 baseline

**规则（Phase 1 期间生效）**：
- `phase0_baseline_final.{jsonl,report.*}` **只读** —— 任何 Phase 1 实验**不得原地修改**。
- 后续实验一律**新建版本 / 新结果目录**，命名带 `phase1_` 前缀。
- 需要重算派生指标时，用 `reprobe` / `backfill` 输出到**新文件**，不覆盖基线。

**⇒ 已确立。baseline 是「已冻结的参照系」。**

### ✅ 检查 3：Grade 天花板**不作为**优化目标

**当前**：μ=5.000 · `pass=1.000` · `score_tolerance=1.000` · `score_mae=0.0`

**⚠️ 这不是「Grade 已经完美」的充分证据**，而是 **15 条 case 区分度不足**：
- 15 条里 8 对 7 错，系统全判对 ⇒ 所有样本落在同一侧，**没有梯度**
- 天花板意味着**无法度量改进**（没有上升空间）

**⇒ Phase 1 不把 Grade 作为优化目标。** 若要度量 Grade，先解决区分度（增加难样本 / 更细的评分粒度），
那是**测量问题**，不是效果问题。

### ✅ 检查 4：Phase 1 第一目标 = **Verify**

依据（Phase 0B 冻结基线）：

| 任务 | μ | 失败率 | 结论 |
|---|---|---|---|
| **Verify** | **1.133** | **1.000** | **唯一全线失败的能力** ⇒ 第一目标 |
| Memory | 2.833 | 0.500 | 次目标（correct-use 0.600） |
| QA | 4.333 | 0.333 | 低优先 |
| Generate | 4.800 | 0.067 | 无需投入 |
| Grade | 5.000 | 0.000 | **不做**（见检查 3） |

**Verify 的根因（Phase 0B 已定位）**：**query 分类器把「考过哪些真题」判成 `exercise`（出题意图）**，
同时导致 ① 路由到 `question_agent`；② `exercise+short` 不做查询扩展 ⇒ 检索弱。

**⚠️ 但修它属「动检索链」** ⇒ 按 `EFFECT_PLAN` §6 需**新版本 + 全量重跑 + 重录门禁 + 换论文数**。
**⇒ Phase 1 开工前必须就此决策**（这是 Phase 1 的第一个待决事项，不是技术问题而是范围问题）。

---

## 一、冻结配置（模型）

| 角色 | 模型 | 管哪些调用 |
|---|---|---|
| **agent** | `deepseek:deepseek-flash`（DeepSeek-V4.1-Flash） | supervisor + 3 个专家 agent（≈87% 调用量） |
| **judge** | `dashscope:qwen3.8-flash` | task_eval 打分 + RAGAS 判分 |
| **RAG 检索链** | `dashscope:qwen3.7-flash` | classify/decompose/HyDE/verify + RAGAS 生成侧 |

- `STRUCTURED_OUTPUT_METHOD=function_calling`
- **agent ≠ judge**（不同家族）⇒ 无自评偏差
- 检索链基础设施：本地 TEI（embedding `:11435` / rerank `:11436`），`RERANK_ENABLED=false`

## 二、冻结产物

| 文件 | 内容 |
|---|---|
| `phase0_baseline_final.jsonl` | **66 条基线记录**（agent/judge 口径 100% 统一） |
| `phase0_baseline_final.report.{json,md}` | 基线报告 |
| `evals/datasets/demo/*_cases.jsonl` | 66 条 case（`gold_status=reviewed`） |
| `evals/datasets/demo/calibration_30.jsonl` | judge 校准表（30 条，已填 human_score） |
| `evals/datasets/exam_answer_corrections.json` | 人工核验的真题答案修正（5 条） |
| `evals/baselines/*.json` | 检索层基线（V-2026-10-02，**未受换模型影响**） |
| `evals/results/generation/ragas/metrics.json` | RAGAS n=20 锚点（`LLM_MODEL` 未动 ⇒ 仍可比） |

## 三、基线数字（§2.B.5）

| Task | n | 平均 final_quality | 失败率 | 主失败原因 |
|---|---|---|---|---|
| QA | 15 | **4.333** | 0.333 | generation_incomplete×3, retrieval_miss×2 |
| Generate | 15 | **4.800** | 0.067 | generation_wrong×1 |
| **Grade** | 15 | **5.000** | 0.000 | — |
| **Verify** | 15 | **1.133** | **1.000** | retrieval_miss×15 |
| Memory | 6 | **2.833** | 0.500 | memory_miss×3 |

**专有指标**
- **Grade**：`score_tolerance@±10 = 1.000` · `score_mae = 0.0`
- **Generate 交付完整率 = 0.942**（通过 49 / 适用 52）
  - 结构完整率 1.000 · 答案可判定率 1.000 · 知识点覆盖率 0.714 · 内容正确率 0.933 · 难度匹配 N/A
- **Memory 四率**：recalled 0.500 · used 0.500 · correct 0.800 · **correct-use 0.600**
- **检索侧**：QA kp=1.000 · Generate kp=0.714 · Verify exam@5=0.800

## 四、Judge Calibration（§6 判据）

| 判据 | 值 | 阈值 | 判定 |
|---|---|---|---|
| `exact` | **0.9333** | ≥0.60 | ✅ |
| `within_1` | **1.000** | ≥0.90 | ✅ |
| `mae` | **0.0667** | ≤0.50 | ✅ |
| `spearman` | **0.7321** | ≥0.70 | ✅ |

**⇒ PASS —— judge 可进批量。**

`boundary_bias`：0 档 0.0 · 5 档 −0.071（无明显边界偏差）

## 五、验收记录

| 检查 | 结果 |
|---|---|
| `agent_model` 统一 | 66/66 = `deepseek:deepseek-flash` ✅ |
| `judge` 统一 | 66/66 = `qwen3.8-flash` ✅ |
| Gold Sanity | ✅ PASS（ERROR 0 · PENDING 0） |
| 实际调用量 | DeepSeek 250 · DashScope 171 · embedding 2701 |

## 六、⚠️ 必须随基线一起引用的已知局限

1. **Grade 天花板**：μ=5.000 / pass=1.000 / `score_mae=0.0` ⇒ **无区分度**。
   Phase 1 若要度量 Grade 改进，需先解决天花板（judge 过宽 or 任务过易）。
2. **校准集分布集中**：30 条中 25 条是 (5,5) ⇒ **Spearman 在大量并列时脆弱**
   （实测：仅 grd-004 一条人工分错误就能把 Spearman 从 0.732 拉到 0.565）。
   **⇒ 该 PASS 应理解为「judge 在可判定范围内一致」，而非「秩相关稳健」。**
3. **Verify 的 `exam_hit@5=0.800`** 与 **生成侧 `retrieval_miss×15`** 并存
   ⇒ 检索命中真题但生成侧不用；根因是 **query 分类器把「考过哪些真题」判成 `exercise`**
   （**属检索链**，修它按 §6 需新版本 + 全量重跑 + 重录门禁）。
4. **QA 的 `gold_points` 未标注** ⇒ QA 分数依赖 judge 主观判断（无 gold 支撑）。
5. **`expected_difficulty` / `gold_answer` 按冻结口径 N/A**（不编造、不用示例题答案冒充）。

## 七、Phase 0B 之后的进度

| 阶段 | 状态 |
|---|---|
| §2.A 0A Smoke | ✅ 完成 |
| §2.B 0B 基线 | ✅ **完成并冻结（reviewed）** |
| §2.B.5 Exit Criteria | ✅ 满足 |
| §3 Phase 1 优化 | ❌ 未开始（优先级：**Verify > Memory > Grade > QA > Generate**） |
| §4–§7 | ❌ 未开始 |
