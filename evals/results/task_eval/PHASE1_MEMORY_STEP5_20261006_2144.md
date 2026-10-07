# Step 5 · Memory 跨会话召回 + paired control（Store ON/OFF）

**日期**：2026-10-06T21:50:03+08:00

## 一、配对总览（同一批 case，只差 Store 开关）

| 指标 | Store ON | Store OFF | 差值 | 期望 |
|---|---|---|---|---|
| case 数 | 6 | 6 | — | 相同 |
| 有效 case（valid≠False） | 6 | 2 | +4 | — |
| **有 memory card 的 case** | **1** | **0** | +1 | ON>OFF |
| **recalled_actual=True** | **1** | **0** | +1 | ON≥OFF（正样本 ON 应 True）|
| recalled_pass=True | 4 | 2 | +2 | — |
| used=True | 2 | 0 | +2 | — |
| correct_use=True | 2 | 0 | +2 | — |

## 二、逐条对照（Store ON）

| case | validity | A段得分 | 批改次数 | card数 | recalled_actual | pass | used | correct | failure |
|---|---|---|---|---|---|---|---|---|---|
| mem-001 | True | [0.0, 0.0] | 2 | 1 | True | True | True | True | - |
| mem-002 | True | [0.0, 0.0] | 2 | 0 | False | False | False | False | - |
| mem-003 | True | [0.0, 40.0] | 2 | 0 | False | False | False | False | - |
| mem-004 | True | [0.0] | 1 | 0 | False | True | False | False | - |
| mem-005 | True | [] | 0 | 0 | False | True | False | False | - |
| mem-006 | True | [100.0, 100.0] | 2 | 0 | False | True | True | True | - |

## 三、逐条对照（Store OFF）

| case | validity | card数 | recalled_actual | pass | failure | validity_reason |
|---|---|---|---|---|---|---|
| mem-001 | False | 0 | None | None | case_invalid | 第 2 次批改得分 100.0 不在期望区间 [0.0,59.0] |
| mem-002 | False | 0 | None | None | case_invalid | A 段批改次数 1 < 期望下限 2 |
| mem-003 | False | 0 | None | None | case_invalid | A 段批改次数 1 < 期望下限 2 |
| mem-004 | True | 0 | False | True | - | 前置条件满足 |
| mem-005 | True | 0 | False | True | - | 前置条件满足 |
| mem-006 | False | 0 | None | None | case_invalid | A 段批改次数 1 < 期望下限 2 |

## 四、判定

- Store OFF 组「有卡的 case」= 0、「recalled_actual=True」= 0 ⇒ ✅ 干净（无卡、无召回 —— 证明 ON 组的召回确实来自 Store）
- Store ON·正样本（should_be_recalled=True 且 valid）= 3 条，实际召回 = 1 条 ⇒ ⚠️ 有正样本未召回（见逐条表）
- case_invalid 合计 = 4 条（前置条件没凑成）——这些**不计入产品失败**，需在报告中单列

> ★ **provenance 声明**：本轮使用的代码含 `schema/grading.py` 的 canonical KP 示例修正（属**产品 prompt 行为变更**）。该结果**不得回写进 Phase 0B 冻结基线**；若 Memory 相关改动正式纳入 Phase 1，应形成新的 provenance/version。
