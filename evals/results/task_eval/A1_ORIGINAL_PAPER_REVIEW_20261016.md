# A1 正式原卷复核工作单（2026-10-16）

**对象**：`p1_expanded_audit_20261015.json` 机械复算出的 **78 条暂定不一致 + 13 条无可比键**，共 91 题。

**背景**：题库键（`knowledge/exams/<年>/items.md` 的 `answer_key`）与第三方网页读数（`reading`，工作单自述来源）存在差异；第三方来源非权威，最终以**正式原卷**为准。

**核对方法**：逐题打开锚点 `knowledge/exams/<年>/items.md#<题号>`，对照正式原卷（真题试卷/官方答案）确定权威键，填表。

**处置规则**（回填由项目方机械执行）：

1. 原卷键 = 题库键 ⇒ 第三方读数错，题库不动，登记「一致」；
2. 原卷键 ≠ 题库键 ⇒ 题库键错，按 A1(d) 走 `correct_key` 订正（新字段追加、旧值不回写），登记「改键」并给出原卷键；
3. 13 条无源键 ⇒ 以原卷补齐权威键后按 1/2 处置；原卷不可得则登记「原卷不可得」并说明。

**工作量参考**：2011 年 15 题优先（其余年 4 批：13×4 + 10 + 2）；单选 2 分题为主，预计 2–3 人时。


---

## 第一部分：78 条暂定不一致（题库键 vs 第三方读数）（78 题）

差异模式提示：C→A 11 题、B→C 10 题、B→D 8 题——若整片同模式偏移，优先怀疑其中一侧系统性错位，先抽查 3 题定向可省大量时间。

| # | 题号 | 科目 | 题库键 | 第三方读数 | 原卷锚点 | 原卷键 | 判定 | 处置 |
|---|---|---|---|---|---|---|---|---|
| 1 | 2011-Q1 | 数据结构 | C | A | `knowledge/exams/2011/items.md#2011-Q1` | ☐ A ☐ B ☐ C ☐ D | ☐ 一致 ☐ 改键 | ☐ 无（一致时） ☐ correct_key 订正 |
| 2 | 2011-Q2 | 数据结构 | A | B | `knowledge/exams/2011/items.md#2011-Q2` | ☐ A ☐ B ☐ C ☐ D | ☐ 一致 ☐ 改键 | ☐ 无（一致时） ☐ correct_key 订正 |
| 3 | 2011-Q3 | 数据结构 | A | B | `knowledge/exams/2011/items.md#2011-Q3` | ☐ A ☐ B ☐ C ☐ D | ☐ 一致 ☐ 改键 | ☐ 无（一致时） ☐ correct_key 订正 |
| 4 | 2011-Q6 | 数据结构 | A | D | `knowledge/exams/2011/items.md#2011-Q6` | ☐ A ☐ B ☐ C ☐ D | ☐ 一致 ☐ 改键 | ☐ 无（一致时） ☐ correct_key 订正 |
| 5 | 2011-Q8 | 数据结构 | B | C | `knowledge/exams/2011/items.md#2011-Q8` | ☐ A ☐ B ☐ C ☐ D | ☐ 一致 ☐ 改键 | ☐ 无（一致时） ☐ correct_key 订正 |
| 6 | 2011-Q9 | 数据结构 | B | D | `knowledge/exams/2011/items.md#2011-Q9` | ☐ A ☐ B ☐ C ☐ D | ☐ 一致 ☐ 改键 | ☐ 无（一致时） ☐ correct_key 订正 |
| 7 | 2011-Q10 | 数据结构 | C | A | `knowledge/exams/2011/items.md#2011-Q10` | ☐ A ☐ B ☐ C ☐ D | ☐ 一致 ☐ 改键 | ☐ 无（一致时） ☐ correct_key 订正 |
| 8 | 2011-Q11 | 数据结构 | D | B | `knowledge/exams/2011/items.md#2011-Q11` | ☐ A ☐ B ☐ C ☐ D | ☐ 一致 ☐ 改键 | ☐ 无（一致时） ☐ correct_key 订正 |
| 9 | 2011-Q12 | 计算机组成原理 | B | D | `knowledge/exams/2011/items.md#2011-Q12` | ☐ A ☐ B ☐ C ☐ D | ☐ 一致 ☐ 改键 | ☐ 无（一致时） ☐ correct_key 订正 |
| 10 | 2011-Q13 | 计算机组成原理 | C | A | `knowledge/exams/2011/items.md#2011-Q13` | ☐ A ☐ B ☐ C ☐ D | ☐ 一致 ☐ 改键 | ☐ 无（一致时） ☐ correct_key 订正 |
| 11 | 2011-Q14 | 计算机组成原理 | C | B | `knowledge/exams/2011/items.md#2011-Q14` | ☐ A ☐ B ☐ C ☐ D | ☐ 一致 ☐ 改键 | ☐ 无（一致时） ☐ correct_key 订正 |
| 12 | 2011-Q15 | 计算机组成原理 | C | D | `knowledge/exams/2011/items.md#2011-Q15` | ☐ A ☐ B ☐ C ☐ D | ☐ 一致 ☐ 改键 | ☐ 无（一致时） ☐ correct_key 订正 |
| 13 | 2011-Q16 | 计算机组成原理 | C | A | `knowledge/exams/2011/items.md#2011-Q16` | ☐ A ☐ B ☐ C ☐ D | ☐ 一致 ☐ 改键 | ☐ 无（一致时） ☐ correct_key 订正 |
| 14 | 2011-Q17 | 计算机组成原理 | A | C | `knowledge/exams/2011/items.md#2011-Q17` | ☐ A ☐ B ☐ C ☐ D | ☐ 一致 ☐ 改键 | ☐ 无（一致时） ☐ correct_key 订正 |
| 15 | 2011-Q19 | 计算机组成原理 | A | C | `knowledge/exams/2011/items.md#2011-Q19` | ☐ A ☐ B ☐ C ☐ D | ☐ 一致 ☐ 改键 | ☐ 无（一致时） ☐ correct_key 订正 |
| 16 | 2015-Q3 | 数据结构 | C | D | `knowledge/exams/2015/items.md#2015-Q3` | ☐ A ☐ B ☐ C ☐ D | ☐ 一致 ☐ 改键 | ☐ 无（一致时） ☐ correct_key 订正 |
| 17 | 2015-Q4 | 数据结构 | C | D | `knowledge/exams/2015/items.md#2015-Q4` | ☐ A ☐ B ☐ C ☐ D | ☐ 一致 ☐ 改键 | ☐ 无（一致时） ☐ correct_key 订正 |
| 18 | 2015-Q5 | 数据结构 | C | D | `knowledge/exams/2015/items.md#2015-Q5` | ☐ A ☐ B ☐ C ☐ D | ☐ 一致 ☐ 改键 | ☐ 无（一致时） ☐ correct_key 订正 |
| 19 | 2015-Q8 | 数据结构 | B | C | `knowledge/exams/2015/items.md#2015-Q8` | ☐ A ☐ B ☐ C ☐ D | ☐ 一致 ☐ 改键 | ☐ 无（一致时） ☐ correct_key 订正 |
| 20 | 2015-Q10 | 数据结构 | A | C | `knowledge/exams/2015/items.md#2015-Q10` | ☐ A ☐ B ☐ C ☐ D | ☐ 一致 ☐ 改键 | ☐ 无（一致时） ☐ correct_key 订正 |
| 21 | 2015-Q11 | 数据结构 | C | A | `knowledge/exams/2015/items.md#2015-Q11` | ☐ A ☐ B ☐ C ☐ D | ☐ 一致 ☐ 改键 | ☐ 无（一致时） ☐ correct_key 订正 |
| 22 | 2015-Q12 | 操作系统 | D | A | `knowledge/exams/2015/items.md#2015-Q12` | ☐ A ☐ B ☐ C ☐ D | ☐ 一致 ☐ 改键 | ☐ 无（一致时） ☐ correct_key 订正 |
| 23 | 2015-Q13 | 计算机组成原理 | D | B | `knowledge/exams/2015/items.md#2015-Q13` | ☐ A ☐ B ☐ C ☐ D | ☐ 一致 ☐ 改键 | ☐ 无（一致时） ☐ correct_key 订正 |
| 24 | 2015-Q14 | 计算机组成原理 | C | D | `knowledge/exams/2015/items.md#2015-Q14` | ☐ A ☐ B ☐ C ☐ D | ☐ 一致 ☐ 改键 | ☐ 无（一致时） ☐ correct_key 订正 |
| 25 | 2015-Q16 | 计算机组成原理 | D | B | `knowledge/exams/2015/items.md#2015-Q16` | ☐ A ☐ B ☐ C ☐ D | ☐ 一致 ☐ 改键 | ☐ 无（一致时） ☐ correct_key 订正 |
| 26 | 2015-Q18 | 数据结构 | B | D | `knowledge/exams/2015/items.md#2015-Q18` | ☐ A ☐ B ☐ C ☐ D | ☐ 一致 ☐ 改键 | ☐ 无（一致时） ☐ correct_key 订正 |
| 27 | 2015-Q19 | 计算机组成原理 | B | C | `knowledge/exams/2015/items.md#2015-Q19` | ☐ A ☐ B ☐ C ☐ D | ☐ 一致 ☐ 改键 | ☐ 无（一致时） ☐ correct_key 订正 |
| 28 | 2015-Q20 | 操作系统 | A | B | `knowledge/exams/2015/items.md#2015-Q20` | ☐ A ☐ B ☐ C ☐ D | ☐ 一致 ☐ 改键 | ☐ 无（一致时） ☐ correct_key 订正 |
| 29 | 2019-Q3 | 数据结构 | B | C | `knowledge/exams/2019/items.md#2019-Q3` | ☐ A ☐ B ☐ C ☐ D | ☐ 一致 ☐ 改键 | ☐ 无（一致时） ☐ correct_key 订正 |
| 30 | 2019-Q4 | 数据结构 | C | A | `knowledge/exams/2019/items.md#2019-Q4` | ☐ A ☐ B ☐ C ☐ D | ☐ 一致 ☐ 改键 | ☐ 无（一致时） ☐ correct_key 订正 |
| 31 | 2019-Q5 | 数据结构 | A | C | `knowledge/exams/2019/items.md#2019-Q5` | ☐ A ☐ B ☐ C ☐ D | ☐ 一致 ☐ 改键 | ☐ 无（一致时） ☐ correct_key 订正 |
| 32 | 2019-Q6 | 数据结构 | C | A | `knowledge/exams/2019/items.md#2019-Q6` | ☐ A ☐ B ☐ C ☐ D | ☐ 一致 ☐ 改键 | ☐ 无（一致时） ☐ correct_key 订正 |
| 33 | 2019-Q7 | 数据结构 | A | D | `knowledge/exams/2019/items.md#2019-Q7` | ☐ A ☐ B ☐ C ☐ D | ☐ 一致 ☐ 改键 | ☐ 无（一致时） ☐ correct_key 订正 |
| 34 | 2019-Q8 | 数据结构 | D | C | `knowledge/exams/2019/items.md#2019-Q8` | ☐ A ☐ B ☐ C ☐ D | ☐ 一致 ☐ 改键 | ☐ 无（一致时） ☐ correct_key 订正 |
| 35 | 2019-Q10 | 数据结构 | B | D | `knowledge/exams/2019/items.md#2019-Q10` | ☐ A ☐ B ☐ C ☐ D | ☐ 一致 ☐ 改键 | ☐ 无（一致时） ☐ correct_key 订正 |
| 36 | 2019-Q11 | 数据结构 | D | B | `knowledge/exams/2019/items.md#2019-Q11` | ☐ A ☐ B ☐ C ☐ D | ☐ 一致 ☐ 改键 | ☐ 无（一致时） ☐ correct_key 订正 |
| 37 | 2019-Q12 | 计算机组成原理 | B | C | `knowledge/exams/2019/items.md#2019-Q12` | ☐ A ☐ B ☐ C ☐ D | ☐ 一致 ☐ 改键 | ☐ 无（一致时） ☐ correct_key 订正 |
| 38 | 2019-Q13 | 计算机组成原理 | C | A | `knowledge/exams/2019/items.md#2019-Q13` | ☐ A ☐ B ☐ C ☐ D | ☐ 一致 ☐ 改键 | ☐ 无（一致时） ☐ correct_key 订正 |
| 39 | 2019-Q14 | 操作系统 | A | D | `knowledge/exams/2019/items.md#2019-Q14` | ☐ A ☐ B ☐ C ☐ D | ☐ 一致 ☐ 改键 | ☐ 无（一致时） ☐ correct_key 订正 |
| 40 | 2019-Q17 | 计算机组成原理 | D | B | `knowledge/exams/2019/items.md#2019-Q17` | ☐ A ☐ B ☐ C ☐ D | ☐ 一致 ☐ 改键 | ☐ 无（一致时） ☐ correct_key 订正 |
| 41 | 2019-Q18 | 计算机组成原理 | B | C | `knowledge/exams/2019/items.md#2019-Q18` | ☐ A ☐ B ☐ C ☐ D | ☐ 一致 ☐ 改键 | ☐ 无（一致时） ☐ correct_key 订正 |
| 42 | 2021-Q4 | 数据结构 | B | C | `knowledge/exams/2021/items.md#2021-Q4` | ☐ A ☐ B ☐ C ☐ D | ☐ 一致 ☐ 改键 | ☐ 无（一致时） ☐ correct_key 订正 |
| 43 | 2021-Q5 | 数据结构 | C | B | `knowledge/exams/2021/items.md#2021-Q5` | ☐ A ☐ B ☐ C ☐ D | ☐ 一致 ☐ 改键 | ☐ 无（一致时） ☐ correct_key 订正 |
| 44 | 2021-Q6 | 数据结构 | B | D | `knowledge/exams/2021/items.md#2021-Q6` | ☐ A ☐ B ☐ C ☐ D | ☐ 一致 ☐ 改键 | ☐ 无（一致时） ☐ correct_key 订正 |
| 45 | 2021-Q7 | 数据结构 | D | A | `knowledge/exams/2021/items.md#2021-Q7` | ☐ A ☐ B ☐ C ☐ D | ☐ 一致 ☐ 改键 | ☐ 无（一致时） ☐ correct_key 订正 |
| 46 | 2021-Q8 | 数据结构 | A | C | `knowledge/exams/2021/items.md#2021-Q8` | ☐ A ☐ B ☐ C ☐ D | ☐ 一致 ☐ 改键 | ☐ 无（一致时） ☐ correct_key 订正 |
| 47 | 2021-Q9 | 数据结构 | C | A | `knowledge/exams/2021/items.md#2021-Q9` | ☐ A ☐ B ☐ C ☐ D | ☐ 一致 ☐ 改键 | ☐ 无（一致时） ☐ correct_key 订正 |
| 48 | 2021-Q10 | 数据结构 | A | C | `knowledge/exams/2021/items.md#2021-Q10` | ☐ A ☐ B ☐ C ☐ D | ☐ 一致 ☐ 改键 | ☐ 无（一致时） ☐ correct_key 订正 |
| 49 | 2021-Q11 | 数据结构 | C | B | `knowledge/exams/2021/items.md#2021-Q11` | ☐ A ☐ B ☐ C ☐ D | ☐ 一致 ☐ 改键 | ☐ 无（一致时） ☐ correct_key 订正 |
| 50 | 2021-Q14 | 计算机组成原理 | D | A | `knowledge/exams/2021/items.md#2021-Q14` | ☐ A ☐ B ☐ C ☐ D | ☐ 一致 ☐ 改键 | ☐ 无（一致时） ☐ correct_key 订正 |
| 51 | 2021-Q15 | 计算机组成原理 | A | C | `knowledge/exams/2021/items.md#2021-Q15` | ☐ A ☐ B ☐ C ☐ D | ☐ 一致 ☐ 改键 | ☐ 无（一致时） ☐ correct_key 订正 |
| 52 | 2021-Q16 | 计算机组成原理 | C | A | `knowledge/exams/2021/items.md#2021-Q16` | ☐ A ☐ B ☐ C ☐ D | ☐ 一致 ☐ 改键 | ☐ 无（一致时） ☐ correct_key 订正 |
| 53 | 2021-Q17 | 计算机组成原理 | A | D | `knowledge/exams/2021/items.md#2021-Q17` | ☐ A ☐ B ☐ C ☐ D | ☐ 一致 ☐ 改键 | ☐ 无（一致时） ☐ correct_key 订正 |
| 54 | 2021-Q18 | 计算机组成原理 | D | C | `knowledge/exams/2021/items.md#2021-Q18` | ☐ A ☐ B ☐ C ☐ D | ☐ 一致 ☐ 改键 | ☐ 无（一致时） ☐ correct_key 订正 |
| 55 | 2024-Q2 | 数据结构 | D | A | `knowledge/exams/2024/items.md#2024-Q2` | ☐ A ☐ B ☐ C ☐ D | ☐ 一致 ☐ 改键 | ☐ 无（一致时） ☐ correct_key 订正 |
| 56 | 2024-Q4 | 数据结构 | A | B | `knowledge/exams/2024/items.md#2024-Q4` | ☐ A ☐ B ☐ C ☐ D | ☐ 一致 ☐ 改键 | ☐ 无（一致时） ☐ correct_key 订正 |
| 57 | 2024-Q5 | 数据结构 | B | D | `knowledge/exams/2024/items.md#2024-Q5` | ☐ A ☐ B ☐ C ☐ D | ☐ 一致 ☐ 改键 | ☐ 无（一致时） ☐ correct_key 订正 |
| 58 | 2024-Q6 | 数据结构 | D | A | `knowledge/exams/2024/items.md#2024-Q6` | ☐ A ☐ B ☐ C ☐ D | ☐ 一致 ☐ 改键 | ☐ 无（一致时） ☐ correct_key 订正 |
| 59 | 2024-Q7 | 数据结构 | A | D | `knowledge/exams/2024/items.md#2024-Q7` | ☐ A ☐ B ☐ C ☐ D | ☐ 一致 ☐ 改键 | ☐ 无（一致时） ☐ correct_key 订正 |
| 60 | 2024-Q8 | 数据结构 | D | A | `knowledge/exams/2024/items.md#2024-Q8` | ☐ A ☐ B ☐ C ☐ D | ☐ 一致 ☐ 改键 | ☐ 无（一致时） ☐ correct_key 订正 |
| 61 | 2024-Q9 | 数据结构 | A | B | `knowledge/exams/2024/items.md#2024-Q9` | ☐ A ☐ B ☐ C ☐ D | ☐ 一致 ☐ 改键 | ☐ 无（一致时） ☐ correct_key 订正 |
| 62 | 2024-Q11 | 数据结构 | C | D | `knowledge/exams/2024/items.md#2024-Q11` | ☐ A ☐ B ☐ C ☐ D | ☐ 一致 ☐ 改键 | ☐ 无（一致时） ☐ correct_key 订正 |
| 63 | 2024-Q14 | 计算机组成原理 | B | C | `knowledge/exams/2024/items.md#2024-Q14` | ☐ A ☐ B ☐ C ☐ D | ☐ 一致 ☐ 改键 | ☐ 无（一致时） ☐ correct_key 订正 |
| 64 | 2024-Q15 | 计算机组成原理 | C | D | `knowledge/exams/2024/items.md#2024-Q15` | ☐ A ☐ B ☐ C ☐ D | ☐ 一致 ☐ 改键 | ☐ 无（一致时） ☐ correct_key 订正 |
| 65 | 2024-Q17 | 计算机组成原理 | D | C | `knowledge/exams/2024/items.md#2024-Q17` | ☐ A ☐ B ☐ C ☐ D | ☐ 一致 ☐ 改键 | ☐ 无（一致时） ☐ correct_key 订正 |
| 66 | 2024-Q18 | 计算机组成原理 | C | B | `knowledge/exams/2024/items.md#2024-Q18` | ☐ A ☐ B ☐ C ☐ D | ☐ 一致 ☐ 改键 | ☐ 无（一致时） ☐ correct_key 订正 |
| 67 | 2024-Q19 | 计算机组成原理 | B | C | `knowledge/exams/2024/items.md#2024-Q19` | ☐ A ☐ B ☐ C ☐ D | ☐ 一致 ☐ 改键 | ☐ 无（一致时） ☐ correct_key 订正 |
| 68 | 2025-Q2 | 数据结构 | B | D | `knowledge/exams/2025/items.md#2025-Q2` | ☐ A ☐ B ☐ C ☐ D | ☐ 一致 ☐ 改键 | ☐ 无（一致时） ☐ correct_key 订正 |
| 69 | 2025-Q4 | 数据结构 | D | B | `knowledge/exams/2025/items.md#2025-Q4` | ☐ A ☐ B ☐ C ☐ D | ☐ 一致 ☐ 改键 | ☐ 无（一致时） ☐ correct_key 订正 |
| 70 | 2025-Q5 | 数据结构 | B | D | `knowledge/exams/2025/items.md#2025-Q5` | ☐ A ☐ B ☐ C ☐ D | ☐ 一致 ☐ 改键 | ☐ 无（一致时） ☐ correct_key 订正 |
| 71 | 2025-Q6 | 数据结构 | D | C | `knowledge/exams/2025/items.md#2025-Q6` | ☐ A ☐ B ☐ C ☐ D | ☐ 一致 ☐ 改键 | ☐ 无（一致时） ☐ correct_key 订正 |
| 72 | 2025-Q9 | 数据结构 | C | A | `knowledge/exams/2025/items.md#2025-Q9` | ☐ A ☐ B ☐ C ☐ D | ☐ 一致 ☐ 改键 | ☐ 无（一致时） ☐ correct_key 订正 |
| 73 | 2025-Q11 | 数据结构 | D | A | `knowledge/exams/2025/items.md#2025-Q11` | ☐ A ☐ B ☐ C ☐ D | ☐ 一致 ☐ 改键 | ☐ 无（一致时） ☐ correct_key 订正 |
| 74 | 2025-Q12 | 操作系统 | A | D | `knowledge/exams/2025/items.md#2025-Q12` | ☐ A ☐ B ☐ C ☐ D | ☐ 一致 ☐ 改键 | ☐ 无（一致时） ☐ correct_key 订正 |
| 75 | 2025-Q16 | 计算机组成原理 | C | B | `knowledge/exams/2025/items.md#2025-Q16` | ☐ A ☐ B ☐ C ☐ D | ☐ 一致 ☐ 改键 | ☐ 无（一致时） ☐ correct_key 订正 |
| 76 | 2025-Q17 | 计算机组成原理 | B | C | `knowledge/exams/2025/items.md#2025-Q17` | ☐ A ☐ B ☐ C ☐ D | ☐ 一致 ☐ 改键 | ☐ 无（一致时） ☐ correct_key 订正 |
| 77 | 2025-Q18 | 计算机组成原理 | C | B | `knowledge/exams/2025/items.md#2025-Q18` | ☐ A ☐ B ☐ C ☐ D | ☐ 一致 ☐ 改键 | ☐ 无（一致时） ☐ correct_key 订正 |
| 78 | 2025-Q19 | 计算机组成原理 | B | A | `knowledge/exams/2025/items.md#2025-Q19` | ☐ A ☐ B ☐ C ☐ D | ☐ 一致 ☐ 改键 | ☐ 无（一致时） ☐ correct_key 订正 |


---

## 第二部分：13 条无可比键（题库无 answer_key）（13 题）

先以原卷补齐权威键，再按处置规则 1/2 走。

| # | 题号 | 科目 | 题库键 | 第三方读数 | 原卷锚点 | 原卷键 | 判定 | 处置 |
|---|---|---|---|---|---|---|---|---|
| 1 | 2009-Q3 | 数据结构 | null | D | `knowledge/exams/2009/items.md#2009-Q3` | ☐ A ☐ B ☐ C ☐ D | ☐ 一致 ☐ 改键 | ☐ 无（一致时） ☐ correct_key 订正 |
| 2 | 2009-Q6 | 数据结构 | null | B | `knowledge/exams/2009/items.md#2009-Q6` | ☐ A ☐ B ☐ C ☐ D | ☐ 一致 ☐ 改键 | ☐ 无（一致时） ☐ correct_key 订正 |
| 3 | 2009-Q8 | 数据结构 | null | D | `knowledge/exams/2009/items.md#2009-Q8` | ☐ A ☐ B ☐ C ☐ D | ☐ 一致 ☐ 改键 | ☐ 无（一致时） ☐ correct_key 订正 |
| 4 | 2009-Q10 | 数据结构 | null | B | `knowledge/exams/2009/items.md#2009-Q10` | ☐ A ☐ B ☐ C ☐ D | ☐ 一致 ☐ 改键 | ☐ 无（一致时） ☐ correct_key 订正 |
| 5 | 2009-Q13 | 计算机组成原理 | null | D | `knowledge/exams/2009/items.md#2009-Q13` | ☐ A ☐ B ☐ C ☐ D | ☐ 一致 ☐ 改键 | ☐ 无（一致时） ☐ correct_key 订正 |
| 6 | 2009-Q14 | 计算机组成原理 | null | C | `knowledge/exams/2009/items.md#2009-Q14` | ☐ A ☐ B ☐ C ☐ D | ☐ 一致 ☐ 改键 | ☐ 无（一致时） ☐ correct_key 订正 |
| 7 | 2009-Q15 | 计算机组成原理 | null | D | `knowledge/exams/2009/items.md#2009-Q15` | ☐ A ☐ B ☐ C ☐ D | ☐ 一致 ☐ 改键 | ☐ 无（一致时） ☐ correct_key 订正 |
| 8 | 2009-Q16 | 计算机组成原理 | null | C | `knowledge/exams/2009/items.md#2009-Q16` | ☐ A ☐ B ☐ C ☐ D | ☐ 一致 ☐ 改键 | ☐ 无（一致时） ☐ correct_key 订正 |
| 9 | 2009-Q18 | 计算机组成原理 | null | A | `knowledge/exams/2009/items.md#2009-Q18` | ☐ A ☐ B ☐ C ☐ D | ☐ 一致 ☐ 改键 | ☐ 无（一致时） ☐ correct_key 订正 |
| 10 | 2009-Q19 | 操作系统 | null | D | `knowledge/exams/2009/items.md#2009-Q19` | ☐ A ☐ B ☐ C ☐ D | ☐ 一致 ☐ 改键 | ☐ 无（一致时） ☐ correct_key 订正 |
| 11 | 2016-Q1 | 数据结构 | null | D | `knowledge/exams/2016/items.md#2016-Q1` | ☐ A ☐ B ☐ C ☐ D | ☐ 一致 ☐ 改键 | ☐ 无（一致时） ☐ correct_key 订正 |
| 12 | 2021-Q12 | 计算机组成原理 | null | D | `knowledge/exams/2021/items.md#2021-Q12` | ☐ A ☐ B ☐ C ☐ D | ☐ 一致 ☐ 改键 | ☐ 无（一致时） ☐ correct_key 订正 |
| 13 | 2024-Q10 | 数据结构 | null | C | `knowledge/exams/2024/items.md#2024-Q10` | ☐ A ☐ B ☐ C ☐ D | ☐ 一致 ☐ 改键 | ☐ 无（一致时） ☐ correct_key 订正 |


---

## 汇总签署区

| 批次 | 题数 | 一致 | 改键 | 原卷不可得 | 签署人/日期 |
|---|---|---|---|---|---|
| 2011（15） | 15 | | | | |
| 2015（13） | 13 | | | | |
| 2019（13） | 13 | | | | |
| 2021（13+1） | 14 | | | | |
| 2024（13+1） | 14 | | | | |
| 2025（11） | 11 | | | | |
| 2009（10） | 10 | | | | |
| 2016（1） | 1 | | | | |

**改键清单**（判定为「改键」的题目在此汇总，供 A1(d) correct_key 订正使用）：

| 题号 | 仓库旧键 | 原卷权威键 | 依据（试卷名/页码） |
|---|---|---|---|
| | | | |

**备注**（整片偏移模式、原卷版本差异等）：

---

## 第三部分：verify 原卷核读并批（2 题，与 A1 合并办理）

这 2 题是 verify case 的「撞已确认错键」题号引用。owner 口径：**题号引用有效不删**；题号是否真的考了 query 问的知识点，须以原卷核读确认；答案键争议单走 A1(d) `correct_key`，两者不互相牵连。

| case | query（知识点） | 引用题号 | 原卷锚点 | kp_ids | 题库键 | 复核要点 | 题号有效性 | 键争议裁定 |
|---|---|---|---|---|---|---|---|---|
| ver-002 | 冯·诺依曼结构考过哪些真题？ | 2009-Q11 | `knowledge/exams/2009/items.md#2009-Q11` | co.overview.von_neumann | D | 该题是否确考冯·诺依曼结构；题干是否自含可判 | ☐ 有效 ☐ 无效 | 题库 D vs 已登记 correct_key C ⇒ 原卷裁定：☐ C ☐ D ☐ 其他 |
| ver-007 | 树与森林转换考过哪些真题？ | 2011-Q5 | `knowledge/exams/2011/items.md#2011-Q5` | ds.tree.forest_convert | B | 该题是否确考树与森林转换；题干是否自含可判 | ☐ 有效 ☐ 无效 | 若原卷键 ≠ 仓库键 ⇒ 记入改键清单，correct_key 订正：______ |

**规则回放**：题号有效 + 键错 ⇒ 保留题号、A1(d) 订正键（`p1_key_audit_sample.json` 已 14/14 有 correct_key，含 2009-Q11→C）；题号无效（不考该知识点）⇒ 从对应 verify case 的 `expected_question_ids` 移除并在 notes 留痕。

**签署**：☐ ver-002 已核（签署人/日期：______） ☐ ver-007 已核（签署人/日期：______）
