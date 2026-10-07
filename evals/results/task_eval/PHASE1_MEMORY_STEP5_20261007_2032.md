# Step 5 · Memory 跨会话召回 + paired control（Store ON/OFF）

**日期**：2026-10-07T20:36:01+08:00

## 一、配对总览（同一批 case，只差 Store 开关）

| 指标 | Store ON | Store OFF | 差值 | 期望 |
|---|---|---|---|---|
| case 数 | 3 | 3 | — | 相同 |
| 有效 case（valid≠False） | 1 | 0 | +1 | — |
| **有 memory card 的 case** | **0** | **0** | +0 | ON>OFF |
| **recalled_actual=True** | **0** | **0** | +0 | ON≥OFF（正样本 ON 应 True）|
| recalled_pass=True | 0 | 0 | +0 | — |
| used=True | 0 | 0 | +0 | — |
| correct_use=True | 0 | 0 | +0 | — |

## 二、逐条对照（Store ON）

| case | validity | A段得分 | 批改次数 | card数 | recalled_actual | pass | used | correct | failure |
|---|---|---|---|---|---|---|---|---|---|
| mem-001 | False | [0.0] | 1 | 0 | None | None | None | None | case_invalid |
| mem-002 | True | [0.0, 0.0] | 2 | 0 | False | False | False | False | - |
| mem-003 | False | [0.0, 100.0] | 2 | 0 | None | None | None | None | case_invalid |

## 三、逐条对照（Store OFF）

| case | validity | card数 | recalled_actual | pass | failure | validity_reason |
|---|---|---|---|---|---|---|
| mem-001 | False | 0 | None | None | case_invalid | A 段批改次数 1 < 期望下限 2 |
| mem-002 | False | 0 | None | None | case_invalid | A 段批改次数 1 < 期望下限 2 |
| mem-003 | False | 0 | None | None | case_invalid | 第 1 次批改得分未能解析（未获授权容忍缺分） |

## 四、判定

- Store OFF 组「有卡的 case」= 0、「recalled_actual=True」= 0 ⇒ ✅ 干净（无卡、无召回 —— 证明 ON 组的召回确实来自 Store）
- Store ON·正样本（should_be_recalled=True 且 valid）= 1 条，实际召回 = 0 条 ⇒ ⚠️ 有正样本未召回（见逐条表）
- case_invalid 合计 = 5 条（前置条件没凑成）——这些**不计入产品失败**，需在报告中单列

> ★ **provenance 声明**：本轮使用的代码含 `schema/grading.py` 的 canonical KP 示例修正（属**产品 prompt 行为变更**）。该结果**不得回写进 Phase 0B 冻结基线**；若 Memory 相关改动正式纳入 Phase 1，应形成新的 provenance/version。
