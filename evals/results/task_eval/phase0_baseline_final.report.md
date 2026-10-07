# Phase 0 报告（n=66）

> gold_status 分布：{'reviewed': 66} —— ✅ **已人工审核（reviewed）**；仍非 frozen，出论文数字前需最终冻结。

## 能力总表

| 能力 | Retrieval | Generation | Final Quality | 主要失败原因 |
|---|---|---|---|---|
| QA | kp=1.000 cat=0.933 exam@5=0.000 pack=0.9333 | gen_ok=1.000 | μ=4.333 pass=0.867 | generation_incomplete |
| Generate | kp=0.714 cat=1.000 exam@5=0.000 pack=1.0 | gen_ok=1.000 | μ=4.8 pass=0.933 | generation_wrong |
| Grade | kp=n/a(15) cat=0.600 exam@5=1.000 pack=1.0 | gen_ok=1.000 | μ=5.0 pass=1.000 | none |
| Verify | kp=n/a(15) cat=0.600 exam@5=0.800 pack=1.0 | gen_ok=1.000 | μ=1.133 pass=0.000 | retrieval_miss |
| Memory | n/a（非知识检索任务） | gen_ok=1.000 | μ=2.833 pass=0.500 | memory_miss |

## 基线表（§2.B.5）

| Task | n | judged | 平均 final_quality | 失败率 | 主失败原因（分布） |
|---|---|---|---|---|---|
| QA | 15 | 15 | 4.333 | 0.3333 | generation_incomplete×3, retrieval_miss×2 |
| Generate | 15 | 15 | 4.8 | 0.0667 | generation_wrong×1 |
| Grade | 15 | 15 | 5.0 | 0.0 | — |
| Verify | 15 | 15 | 1.133 | 1.0 | retrieval_miss×15 |
| Memory | 6 | 6 | 2.833 | 0.5 | memory_miss×3 |

## Grade 专有

- `score_tolerance@±10`：1.000（n=15, n/a=0）
- `score_mae`：0.0

## Generate 专有（交付五项，§3.1 v1.0）

> **口径**：交付完整率 = 适用项通过数 / 适用项数；**不适用项从分母剔除**。
> ❌ 不要求「5 项永远齐全」；❌ 难度匹配本批全 N/A（query 未指定难度，无可靠 gold）。

| 交付项 | 通过率 | n（适用） | n/a（剔除） |
|---|---|---|---|
| 结构完整率 | 1.000 | 15 | 0 |
| 答案可判定率 | 1.000 | 15 | 0 |
| 知识点覆盖率 | 0.714 | 7 | 8 |
| 内容正确率 | 0.933 | 15 | 0 |
| 难度匹配 | n/a(15) | 0 | 15 |

- **Generate 交付完整率（主指标）**：0.942（通过 49 / 适用 52；不适用 23 已从分母剔除）

## Memory 专有（四率，§2.B.4）

> Memory 的检索指标为 **N/A**（非知识检索任务）；判据是下列四率。

- `memory_recalled`（检索率）：0.500
- `memory_used`（使用率）：0.500
- `memory_correct`（正确率）：0.800
- **`correct-use rate`**（retrieved ∧ used ∧ correct，**主指标**）：0.600
