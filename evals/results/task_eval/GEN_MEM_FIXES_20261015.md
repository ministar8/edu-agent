# Generate / Memory 修复补丁（2026-10-15）

## 本次修改

- `gen-005`：在 `gold.question_stem` 补齐相对寻址选择题 A–D；候选盲标为 `(1) 200AH；1FF8H；(2) B`，难度 `medium`。
- `gen-009`：重生成完整五段流水线题；候选盲标为流水线 16 周期、非流水 60 周期、加速比 3.75，难度 `medium`。
- `mem-001`：两道 AVL 树题都给出完整树结构及错误学生答案；正确答案分别是“整棵树根仍为 30”和“整棵树根仍为 40”，两次都落在平衡二叉树考点。
- `mem-004`：把学生答案由 `20` 改为 `10`；按题设高度按层计数的约定，正确值为 20，因此该答案错误，但单次低分不应形成弱点记忆。

## 盲态与状态说明

`gen-005` 的原系统答案先前已在对话中暴露，严格盲态无法事后恢复。本次 gold 按题干独立演算，但 `gold_status` 暂保留 `draft`，需由未接触原答案的第二标注者确认后再升级。`gen-009` 是新生成题目，答案独立推导；按项目规程，仍保留 `draft` 等待人工复核签署。本补丁不代替项目方运行 sanity、backfill 或 ledger 重建。

## 应用方法

1. 用 `generate_cases_patched.jsonl` 替换 `evals/datasets/demo/generate_cases.jsonl`。
2. 在现有 `memory_cases.jsonl` 中，按 `case_id` 用 `memory_cases_patch.jsonl` 的 `mem-001` 与 `mem-004` 两条记录替换原记录，其余记录保持不变。
