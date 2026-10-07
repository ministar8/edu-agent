# EFFECT_PLAN 进度 + Phase 0B 最终基线（2026-10-06）

> **定稿配置**：agent=`deepseek:deepseek-flash` · judge=`dashscope:qwen3.8-flash` · RAG 链=`dashscope:qwen3.7-flash`
> **基线文件**：`phase0_baseline_final.jsonl`（66 条，agent/judge 口径均 100% 统一）
> **gold_status 全为 `draft` ⇒ 数字不得进论文**

## 一、最终基线（Phase 0B）

| Task | n | 平均 final_quality | 失败率 | 检索侧 |
|---|---|---|---|---|
| QA | 15 | **4.333** | 0.333 | kp=1.000 cat=0.933 pack=0.933 |
| Generate | 15 | **4.800** | 0.067 | kp=0.714 cat=1.000 pack=1.0 |
| **Grade** | 15 | **5.000** | 0.000 | cat=0.600 exam@5=1.000 |
| **Verify** | 15 | **1.133** | **1.000** | cat=0.600 **exam@5=0.800** |
| Memory | 6 | **2.833** | 0.500 | n/a |

**专有指标**
- Grade：`score_tolerance@±10 = 1.000` · `score_mae = 0.0`
- Generate 交付完整率（主指标）：**0.942**（通过 49 / 适用 52）
  - 结构完整率 1.000 · 答案可判定率 1.000 · 知识点覆盖率 0.714 · 内容正确率 0.933 · 难度匹配 N/A
- Memory 四率：recalled 0.500 · used 0.500 · correct 0.800 · **correct-use 0.600**

**验收**：`agent_model` 66/66 = `deepseek:deepseek-flash` ✅ · `judge` 66/66 = `qwen3.8-flash` ✅ ·
Sanity **PASS**（ERROR 0 · PENDING 0）· 实际调用：DeepSeek 250 · DashScope 171 · embedding 2701

---

## 二、★ 换模型前后对照

| Task | 旧（agent=qwen3.8-max-0902, judge=27b） | 新（agent=deepseek-flash, judge=qwen3.8-flash） | Δ |
|---|---|---|---|
| QA | 4.867 | **4.333** | **−0.533** |
| Generate | 5.000 | 4.800 | −0.200 |
| Grade | 4.333 | **5.000** | **+0.667** |
| Verify | 0.200 | 1.133 | +0.933 |
| Memory | 2.167 | 2.833 | +0.667 |

**检索侧逐位一致** ✅（`kp_hit` 旧 11/11、5/7、0/0 = 新 11/11、5/7、0/0）
⇒ **交叉验证成功**：`LLM_MODEL` 未动 ⇒ 检索链确实未受影响。

### ⚠️ 两个必须记录的解读限制

1. **agent 与 judge 同时变** ⇒ 上表 Δ **无法区分**「模型能力差异」与「judge 打分口径差异」。
   这正是「judge 是测量误差主要来源」的体现（此前实测同一批 reply 换 judge，Memory 漂移 1.33 分）。
2. **Grade 出现天花板**：μ=5.000、pass=1.000、`score_mae=0.0` ⇒ **无区分度**。
   Phase 1 若要度量 Grade 的改进，需先解决天花板（judge 过宽 or 任务过易）。

---

## 三、EFFECT_PLAN 进度

| 阶段 | 状态 |
|---|---|
| **§2.A 0A Smoke** | ✅ 完成 |
| **§2.B 0B 诊断基线** | ✅ **完成**（本文件；待 calibration 后冻结） |
| §2.B.5 Exit Criteria | ⚠️ 差最后一步：**judge calibration** |
| §3 Phase 1 优化 | ❌ 未开始（优先级：Verify > Memory > Grade > QA > Generate） |
| §4 Phase 1.5 L3 闸门 | ❌ 未开始 |
| §5 Phase 2 检索短板 | ❌ 未开始 |
| §6 Final Gate 终评集（145 条） | ❌ 未开始 |
| §7 收尾 + Final Freeze | ❌ 未开始 |

---

## 四、下一步（冻结 Phase 0B）

| 顺序 | 动作 | 成本 | 谁做 |
|---|---|---|---|
| 1 | 填 `calibration_30.jsonl` 的 `human_score`（30 条，0–5） | 0 | **你** |
| 2 | 跑 `calibrate` → 判定 judge 是否可信 | **0**（纯计算） | 我 |
| 3 | PASS → **冻结 Phase 0B**；FAIL → 收紧 judge prompt 后重判 | ~7–9 万 | 我 |

> ⚠️ **注意**：`calibration_30.jsonl` 的 `llm_score` 是**旧 judge（qwen3.8-27b）**给的，
> 而当前 judge 是 `qwen3.8-flash` ⇒ **校准前需先用新 judge 重判这 30 条**
> （`rejudge` 命令，约 30 次调用）。

---

## 五、保留 vs 失效（换 LLM 影响，2026-10-06 审理）

**✅ 保留**：检索层全部基线 · V-2026-10-02 锚点 · **RAGAS n=20 锚点**（`LLM_MODEL` 未动）·
demo 集 66 条 · `task_eval` harness · 全部修复（Grade case / answer_key 修正 / `kp_hit` N/A 口径 /
五项判据 / `rejudge`·`reprobe`·`backfill` 命令 / 环境预检）· `exam_answer_corrections.json`

**❌ 已重做**：66 条 `reply`/`final_quality`/`failure_reason` · Generate 五项 · Grade `score_tolerance` ·
Memory 四率

**findings 结论中仍成立的**（与模型无关）：Verify 根因（query 分类判成 `exercise`，**检索层**）·
`kp_hit` 假阴性 · Grade `answer_key` 33% 错误（**数据层**）· 五项 N/A 剔除**口径** ·
judge 是主要误差源
