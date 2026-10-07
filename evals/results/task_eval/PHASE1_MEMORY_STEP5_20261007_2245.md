# Step 5 · Memory 跨会话召回 + paired control（Store ON/OFF）

**日期**：2026-10-07T22:48:00+08:00

## 一、配对总览（同一批 case，只差 Store 开关）

| 指标 | Store ON | Store OFF | 差值 | 期望 |
|---|---|---|---|---|
| case 数 | 3 | 3 | — | 相同 |
| 有效 case（valid≠False） | 2 | 1 | +1 | — |
| **有 memory card 的 case** | **2** | **1** | +1 | ON>OFF |
| **recalled_actual=True** | **2** | **1** | +1 | ON≥OFF（正样本 ON 应 True）|
| recalled_pass=True | 2 | 1 | +1 | — |
| used=True | 2 | 1 | +1 | — |
| correct_use=True | 2 | 1 | +1 | — |

## 二、逐条对照（Store ON）

| case | validity | A段得分 | 批改次数 | card数 | recalled_actual | pass | used | correct | failure |
|---|---|---|---|---|---|---|---|---|---|
| mem-001 | True | [0.0, 0.0] | 2 | 1 | True | True | True | True | - |
| mem-002 | True | [0.0, 0.0] | 2 | 1 | True | True | True | True | - |
| mem-003 | False | [0.0, 100.0] | 2 | 0 | None | None | None | None | case_invalid |

## 三、逐条对照（Store OFF）

| case | validity | card数 | recalled_actual | pass | failure | validity_reason |
|---|---|---|---|---|---|---|
| mem-001 | False | 0 | None | None | case_invalid | A 段批改次数 1 < 期望下限 2 |
| mem-002 | True | 1 | True | True | - | 前置条件满足 |
| mem-003 | False | 0 | None | None | case_invalid | 第 2 次批改得分 100.0 不在期望区间 [0.0,59.0] |

## 四、判定

- Store OFF 组「有卡的 case」= 1、「recalled_actual=True」= 1 ⇒ ❌ 不干净（OFF 组仍有卡/召回 ⇒ 存在旁路，需排查）
- Store ON·正样本（should_be_recalled=True 且 valid）= 2 条，实际召回 = 2 条 ⇒ ✅ 跨会话召回成立
- case_invalid 合计 = 3 条（前置条件没凑成）——这些**不计入产品失败**，需在报告中单列

> ★ **provenance 声明**：本轮使用的代码含 `schema/grading.py` 的 canonical KP 示例修正（属**产品 prompt 行为变更**）。该结果**不得回写进 Phase 0B 冻结基线**；若 Memory 相关改动正式纳入 Phase 1，应形成新的 provenance/version。
