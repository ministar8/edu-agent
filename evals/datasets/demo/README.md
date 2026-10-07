# Phase 0 demo 集（evals/datasets/demo/）

> 本目录是 **Phase 0 效果测量的唯一 case 来源**（`docs/EFFECT_PLAN.md` §2.B.1）。
> 由 `scripts/build_demo_cases.py` **确定性生成** —— 不要手工编辑生成结果；
> 要改内容，改生成器或改其引用的上游资产（黄金集 / 真题 / 考点表）。

## 文件

| 文件 | task | 条数 | 用途 |
|---|---|---|---|
| `qa_cases.jsonl` | qa | 15 | 知识问答（learn / method / explain） |
| `generate_cases.jsonl` | generate | 15 | 出题（practice） |
| `grade_cases.jsonl` | grade | 15 | 批改（grade，0–100 制） |
| `verify_cases.jsonl` | verify | 15 | 真题核查（verify） |
| `memory_cases.jsonl` | memory | 6 | 两轮对话记忆 |

**0A Smoke 子集** = 每个文件**前 3 条** + `memory_cases.jsonl` 前 1 条（共 13 条）。
`--limit 3` 即取此子集（memory 亦取 3，如需严格 1 条请单独跑 `--task memory --limit 1`）。

## 一行 = 一条 case（JSON）

```jsonc
{
  "case_id": "qa-001",          // 必填，全局唯一
  "task": "qa",                 // 必填，qa|generate|grade|verify|memory
  "task_mode": "learn",         // 选填，交给 Task Policy；空则由 query 信号分类
  "query": "Cache 的作用是什么？", // 必填（多轮时 = 首轮）
  "turns": [],                  // 选填，多轮输入；非空时以它为准
  "subject": "co",              // 选填，ds|co|os|network，用于 category_hit
  "gold": { ... },              // 见下
  "gold_status": "draft",       // draft | reviewed | frozen
  "needs_review": ["gold.gold_points"],  // 待人工确认的字段
  "notes": "..."                // 选填，说明 gold 来源
}
```

文件首部允许 `#` 注释行（沿用 `sample_408.jsonl` 约定，`load_cases` 会跳过）。

## gold 字段（按 task 取用；缺失 = **不适用**，不是失败）

| task | 字段 | 来源 |
|---|---|---|
| qa | `gold_points[]` · `expected_kp[]` · `reference` | `expected_kp`/`reference` 自动预填；`gold_points` 待人工 |
| generate | `expected_kp[]` · `expected_difficulty` · `gold_answer` | 仅 `expected_kp` 自动预填 |
| grade | `question_stem` · `student_answer` · `human_score`(0–100) · `full_marks` | 题干自动预填；`student_answer`/`human_score` 待人工 |
| verify | `expected_question_ids[]` | **自动预填**（由真题 `kp_ids` 反查，多题 gold） |
| memory | —— | 三维由 judge/人工判 |

### 四条冻结口径（改动需回 `docs/EFFECT_PLAN.md`）

1. **`kp_hit` = 祖先覆盖（方向性，2026-10-05 拍板冻结）**

   ```
   expected_kp 中每一个知识点，都能被 retrieved_kp 中的「自身 或 后代」覆盖
   ```

   ```
   expected = co.storage          retrieved = co.storage.cache   → ✅ 覆盖
   expected = co.storage.cache    retrieved = co.storage          → ❌ 不覆盖（反向不算）
   ```

   **理由**：这里测的是「知识点**是否被证据覆盖**」，不是「chunk metadata 与 gold 字符串是否全等」。
   反向必须不成立——否则父节点会反向吞掉子节点，指标虚高。
   实现见 `metrics._kp_covered`（`expected` 为前缀、`retrieved` 为 `expected + "."` 开头）。
   ⚠️ 配套：gold 的 `expected_kp` 必须已是**考点 ID**（生成器用 `name→id` 映射统一，实测覆盖 67/67）。

2. `knowledge_coverage_pass = expected_kp ≠ ∅ AND expected_kp ⊆ retrieved_kp`；
   `expected_kp = []` → **N/A**，不并入失败率。

3. Grade 的 `full_marks` **恒为 100** —— 批改 agent 输出 0–100（`schema/grading.py`），
   与真题卷面 2 分制**不是一个量纲**；`score_tolerance@±10` 按 0–100 计。

4. Verify 的 `question_id_recall@5` 属 **Phase 1**；Phase 0 用 `exam_hit@5` 作代理
   （系统当前未被要求输出题号，见 EFFECT_PLAN §7 讨论）。

## gold_status 三态（报告必须声明）

- `draft`：脚本预填，**未经人工** —— 只可用于 0A smoke，**不得出论文数字**。
- `reviewed`：人工审核过。
- `frozen`：冻结，可用于论文归档。

## 进 0B 前的两道关（都跑在 demo 集上）

```bash
# ① Gold Sanity Check —— 保证 0B 的 fail 是系统 fail，不是 evaluator 自己的 fail
PYTHONPATH=src uv run python -m evaluation.task_eval sanity     # ERROR>0 则 exit 1

# ② 导出两张**互不混用**的复核表（生成脚本）
PYTHONPATH=src uv run python scripts/export_review_sheets.py
```

| 表 | 内容 | 谁填 | 用途 |
|---|---|---|---|
| `calibration_30.jsonl` | 30 条，`human_score` 0–5（`llm_score` 由 judge 出） | 人工 | Judge 校准（exact≥0.60 / ±1≥0.90 / MAE≤0.50 / Spearman≥0.70） |
| `gold_review.jsonl` | Generate `expected_difficulty`+`gold_answer`；Grade `human_score` 0–100 | 人工 | **Gold 审核**，与 judge 校准**不是一件事** |

> ★ Memory **不进** 0–5 校准：它的主指标是 `retrieved ∧ used ∧ correct` 三维，不是 `final_quality`。
> 填完 calibration 跑：`python -m evaluation.task_eval calibrate --input evals/datasets/demo/calibration_30.jsonl`

## 重新生成

```bash
PYTHONPATH=src uv run python scripts/build_demo_cases.py
```
