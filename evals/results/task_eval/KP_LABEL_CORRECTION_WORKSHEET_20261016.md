# KB KP 标签订正工作单（2026-10-16，ver-002/007 裁定附带发现）

> 来源：`VER_002_007_RULING_20261016.md` 裁定结论 4。性质：**KB 数据质量发现**（`knowledge/exams/*/items.md` 的 `kp_ids` 标签与 KP 权威定义不符），不是 demo gold 错误（gold 已 frozen 且对标签机械忠实，不动）。
> 约束：KB **不回写**（A1(d) 纪律：新字段追加、旧值不回写）；本工作单只登记订正建议，**落地口径需 owner 裁定**——(A) 仿 `evals/datasets/exam_answer_corrections.json` 建评测侧覆盖表（检索/展示时改签，KB 原文不动）；(B) 走正式 KB 修订流程（改 items.md，需 KB 侧审核链）。
> 附带影响（两种口径都一样）：若标签最终改签，`ver-007` 的 gold `expected_question_ids` 须按新标签重生成——gold 已 frozen，届时须走新审核链 + owner 新裁决；本工作单**不触碰** gold。

| 题号 | 现标签 | 内容层实际考点 | 建议改签 | 依据（裁定文档行） |
|---|---|---|---|---|
| 2009-Q3 | ds.tree.forest_convert | 由遍历序列反推遍历方式 | `ds.tree.traversal` | VER_002_007_RULING §3 |
| 2011-Q4 | ds.tree.forest_convert | 完全二叉树 768 结点叶结点计数 | `ds.tree.complete`（或 `ds.tree.binary_tree`） | 同上 |
| 2011-Q5 | ds.tree.forest_convert | 前序+后序推中序 | `ds.tree.traversal` | 同上 |
| 2025-Q3 | ds.tree.forest_convert | 顺序存储数组表示二叉树的合法性 | `ds.tree.binary_tree` | 同上 |
| 2016-Q5 | ds.tree.forest_convert | 森林构成计数（边-结点推树棵数），边界 | 待 owner 定：维持 / 改 `ds.tree` | 同上 |

## 处理记录（owner 填写）

- 口径裁定（A/B/其它）：______________
- 落地时间 / 落地工件 / 审核人：______________
- 若触发 ver-007 gold 重生成：新审核链单号 ______________

---
*附注：本工作单只覆盖 ver-002/007 裁定中发现的 5 条。KP 标签与内容的一致性未做全库普查——是否普查由 owner 另裁（普查范围≈全exam items.md 的 kp_ids 逐条内容核对，属独立人工任务）。*
