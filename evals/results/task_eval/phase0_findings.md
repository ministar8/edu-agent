# Phase 0 基线 + 归因修正（2026-10-06 · 定稿 v5）

> 数据：`phase0_baseline_v5.jsonl`（66/66 条；judge 口径统一 · gold 已核验 · 检索指标已重算）
> 配置：agent=`dashscope:qwen3.8-max-0902` · judge=`dashscope:qwen3.8-27b` · RAG 链=`qwen3.7-flash`
> **gold_status 全为 `draft` ⇒ 数字不得进论文**

## 1. 基线表（最终）

| Task | n | 平均 final_quality | 失败率 | kp_hit |
|---|---|---|---|---|
| QA | 15 | **4.867** | 0.200 | **1.000** |
| Generate | 15 | **5.000** | 0.000 | **0.714** |
| Grade | 15 | **4.333** | 0.133 | n/a |
| **Verify** | 15 | **0.200** | **1.000** | n/a |
| Memory | 6 | **2.167** | 0.667 | n/a |

- **Grade**：`score_tolerance@±10 = 0.867` · `score_mae = 13.3`
- **Memory 四率**：recalled 0.333 · used 0.333 · correct 0.333 · **correct-use 0.500**
- **Verify**：`exam_hit@5 = 0.800`（检索命中真题）但**题号输出 0**

## 2. ★ 三处指标口径缺陷（**全是假阴性，不是能力问题**）

### (1) `kp_hit` 假阴性：chunk 缺 KP 元数据时记了 False

实测 Generate 15 条中 **8 条**检索到的 chunk `knowledge_points` 为空
（`basic/`、`advanced/` 集合缺该标签）⇒ 「覆盖与否」**不可判定**。
改记 **N/A** 后（`reprobe` 重算）：

| Task | 修正前 | **修正后** |
|---|---|---|
| QA | 0.733 | **1.000** |
| Generate | 0.333 | **0.714** |

⇒ **QA 知识点覆盖实际满分**；Generate 是 0.714。

### (2) Grade 的 `score_tolerance` 曾测的是 **gold 的准确率**

`answer_key` 来自扫描：**24% 缺失 + 15 条抽样中 5 条错误（33%）**。
修正后 0.800 → **0.867**、`score_mae` 20.0 → **13.3**。
**剩余 2 条经核验是真正的系统错误**（模式：选项字母 ↔ 内容映射混乱）。

### (3) Memory 的 `retrieval_miss` 归因错位

Memory 的 query 本就不是知识查询，检索返空属**预期**。已豁免检索判据，改报四率。

## 3. Phase 1 优先级（修正后）

| 优先级 | 任务 | 依据 |
|---|---|---|
| **1** | **Verify** | 唯一全线 0 分的真缺口；但修它需动检索链（§6 开新版本） |
| **2** | **Memory** | correct-use 0.500 |
| **3** | **Grade** | 86.7%，错误模式明确 |
| **4** | QA | 4.867，仅小瑕疵；kp 已满分 |
| **5** | **Generate** | **无需投入**（μ=5.0 有依据，kp 0.714） |

---

## 4. judge 敏感性：换 judge 让分数大幅漂移

同一批 reply（agent 未变），只换 judge（`qwen3.8-max` → `qwen3.8-27b`）：

| Task | judge=max | judge=27b | Δ |
|---|---|---|---|
| QA | 4.733 | 4.867 | +0.133 |
| Generate | 4.800 | 5.000 | +0.200 |
| Grade | 4.133 | 3.733 | **−0.400** |
| Verify | 0.333 | 0.200 | −0.133 |
| Memory | 3.500 | 2.167 | **−1.333** |

**⇒ judge 是测量误差的主要来源**（Memory 漂移 1.33 分 > 一个 rubric 等级）
⇒ **calibration 不是可选项**。
**⇒ 反向强证据**：**Verify 在两个 judge 下都 ≈0** ⇒ 「能力不存在」不依赖 judge 选择。

**⇒ judge 是测量误差的主要来源**（Memory 一项漂移 1.33 分，超过一个 rubric 等级）
⇒ **calibration 不是可选项**，是冻结前的必经步骤。

**⇒ 反向的强证据**：**Verify 在两个 judge 下都是 ≈0**
（0.333 → 0.200；分布 12×0 分 + 3×1 分）
⇒ 「Verify 能力不存在」的结论**不依赖 judge 选择**，是稳健发现。

## 3. ⚠️ 天花板效应：judge 给分过于集中

校准集 30 条的 `llm_score` 分布：**`{5.0: 26, 4.0: 1, 0.0: 3}`**

- 26/30 都是满分 ⇒ **judge 在 2/3/4 档几乎没有使用**，区分度不足
- 后果：**Phase 1 的改进无法被度量**（没有上升空间）
- 校准集也因此**缺乏分数梯度**，会削弱 calibration 的判别力

**⇒ 这正是 calibration 要暴露的问题**：若人工给出有梯度的分数而 judge 全给 5，
`exact`/`within_1` 必然不达标 ⇒ 需**收紧 judge prompt**（如显式禁止默认给 5、给出各档锚例）。

---

## 5. ★★ Grade 重做（#C）与结论反转

### 做了什么

1. **修 `student_answer` 恒为 A**：初版 15/15 全是 A（无答对样本、无 B/C/D 样本）。
   改为**答对/答错交替 + 按位置均匀轮换**，新分布 `{A:4, B:4, C:3, D:4}`。
2. **`human_score` 改为客观可推**：选择题「对 = 100，错 = 0」⇒ 机械预填，
   **`score_tolerance@±10` 由此立即可算**（此前 15 条全 N/A）。

### 顺带挖出一个**数据层 bug**

`knowledge/exams/*/items.md` 里 **160/674（24%）** 的题是 **`answer_key: null`**（扫描缺失）。
我的解析器把它读成**字符串 `'null'`** —— 而 **`'null'` 是 truthy**：

- 通过了 `if it["answer_key"]` 筛选 ⇒ 无答案的题混进 Grade 集
- 生成器因 `'null' not in A/B/C/D` 回退到 `opts[0]`（**恒为 A**）⇒ **凭空编造正确答案**

**★ 这正是初版「student_answer 全是 A」的真正根因**（前两轮只治了症状）。
修三层：解析层归一化占位符 / 生成器只收 `answer_key ∈ {A,B,C,D}` / sanity 比对前截掉选项。

### ★ 结论反转：`score_tolerance` 曾测的是 **gold 的准确率**

修正 gold 后：`score_tolerance@±10 = 0.800`、`score_mae = 20.0`。

但**逐条人工核验 3 个失败案例后，3/3 都是我的 gold 错、系统全对**：

| case | 题面 | 正确答案 | 我的 gold | 系统判分 |
|---|---|---|---|---|
| grd-009 | 递归解析：用户主机/本地 DNS 各发几条 | **B**（一条、多条） | 说 A 对 ❌ | 判 B ✅ |
| grd-013 | TCP/IP 网络层提供的服务 | **A**（无连接不可靠数据报） | 说 D 对 ❌ | 判 A ✅ |
| grd-014 | 英文缩写均为总线标准的是 | **D**（ISA/EISA/PCI/PCIe） | 说 D 错 ❌ | 判 D ✅ |

**根因**：`answer_key` 来自**扫描**（`explanation_status: scan`、third_party），
实测 **24% 缺失 + 15 条抽样中 5 条错误（33%）**。

### 15 条 answer_key 全量核验结果（5/15 源数据错误）

| case | 题号 | 源 key | 正确 | 说明 |
|---|---|---|---|---|
| grd-002 | 2009-Q11 | D | **C** | CPU 靠**指令周期不同阶段**区分指令/数据 |
| grd-009 | 2010-Q40 | A | **B** | 递归：用户主机 1 条、本地 DNS **多条** |
| grd-012 | 2011-Q23 | C | **B** | 短任务优先且不饥饿 = **高响应比优先** |
| grd-013 | 2011-Q33 | D | **A** | TCP/IP 网络层 = 无连接不可靠数据报 |
| grd-014 | 2010-Q20 | A | **D** | ISA/EISA/PCI/PCIe **均为总线标准** |

（仅 3 条改变 `human_score` —— grd-002/012 因学生答案在两种 key 下都判错，结果恰好一致。）

### 修正机制：`evals/datasets/exam_answer_corrections.json`

评测侧覆盖，由 `assets.parse_exam_items()` 套用。
**为什么不改 `items.md`**：它是**检索语料**，改它会改变检索结果 ⇒ 等于动检索链（§6 需开新版本）。
**原则：修 gold 与修语料必须分离。**

### 修正后的最终 Grade 结果

| 指标 | gold 有错时 | **gold 修正后** |
|---|---|---|
| `score_tolerance@±10` | 0.800 | **0.867** |
| `score_mae` | 20.0 | **13.3** |
| μ final_quality | 3.733 | **4.333** |

**剩余 2 条失败经核验是真正的系统错误**（错误模式统一为「选项字母 ↔ 内容映射混乱」）：

| case | 学生选 | gold | 系统判 | 系统错在哪 |
|---|---|---|---|---|
| grd-004 | C（z=FFFF0076H ❌） | 0 | **100** ❌ | 称「y 的补码为 0xFFF9」——**算错**（-9 应为 0xFFF7），且与选项内容自相矛盾 |
| grd-009 | B（一条、多条 ✅） | 100 | **0** ❌ | 称「正确答案是『一条、多条』，即选项 **A**」——**字母说反**（A 是一条、一条） |

**⇒ Grade 真实能力：判分准确率 86.7%（13/15）。**

---

## 6. ★ Verify 问法探针（#1 复核）：结论**修正**

**目的**：Phase 0B 的 15 条 Verify 全是同一模板（`「X考过哪些真题？」`），
需排除「是这个问法特殊」的可能。设计：**2 考点 × 5 种自然问法 = 10 条**
（`evals/datasets/probes/verify_cases.jsonl`）。

### 结果

| 问法 | 栈（ds） | 流量控制（cn） |
|---|---|---|
| ①「X考过哪些真题？」（原模板） | 出题 ❌ | 出题 ❌ |
| ②「历年真题里，X出现在哪些题里？」 | **列出真题 ✅** | 诚实说明 |
| ③「帮我找一下考 X 的真题。」 | 出题 ❌ | 出题 ❌ |
| ④「X 这个考点在 408 真题里出现过吗？出现在哪几年？」 | 诚实说明 | 诚实说明 |
| ⑤「我想做 X 的真题，有哪些年份考过？」 | 出题 ❌ | 出题 ❌ |

**汇总**：新出练习题 **6/10** · 诚实说明无法定位 **3/10** · **正确列出真题 1/10**

### 机制（从检索日志读出，非推测）

```
「栈考过哪些真题？」        → coarse_k=20 rerank=False [exercise+short] ← 不做查询扩展
「历年真题里，栈出现在哪些题里？」→ coarse_k=50 rerank=True  [exercise+long]  ← 扩展为
                                「栈 历年真题考点 出栈序列 顺序存储 链栈」
```

⇒ **根因是 query 分类器把「考过哪些真题」判成了 `exercise`（出题意图）**，
它同时导致两件事：
1. **路由到 `question_agent`**（所以生成练习题）
2. **`exercise+short` 不做查询扩展** ⇒ 检索质量差甚至为空

⇒ **不是「supervisor 路由单独的问题」，而是「query 分类」这一层的问题。**

### ⚠️ 对 Phase 1 的重大含义

分类器位于 `src/rag/pipeline.py` 与 `src/rag/task_policy.py` —— **属检索链**。
按 `EFFECT_PLAN` §6：

> **动检索链 → 新版本 + 全量重跑 + 重录门禁 + 换论文数**

⇒ **修 Verify 不是「补个 agent 指令」的小改动，而是要开新检索版本、全量重跑。**
这条必须在上 Phase 1 之前让用户拍板。

### 我自己犯的两个判据错误（已修）

1. **题号正则只认 `YYYY-Qn`** ⇒ 漏判了 vprobe-002。
   系统用**自然语言**「2010 年第 1 题」报真题 —— 已补 `_QID_NATURAL_RE`。
2. 曾假设「模板空格影响检索」⇒ 实测**去掉空格同样为空**，假设**排除**。

---

## 6. ★ 三类归因修正（**不要照抄上表的主失败原因**）

### (1) Verify 全线 0 分 = **能力端到端不存在**（产品级缺口，Phase 1 头号目标）

| 证据 | 内容 |
|---|---|
| supervisor | `SUPERVISOR_PROMPT` **仅 291 字符、只有 3 条路由**（knowledge / question / grading），**无 verify**，从不提「真题 / 考过」 |
| 实测回复 | 15 条**全是新出的练习题**：`以下是「X」相关练习题…**题目1** 类型：选择` |
| 题号 | 回复中 `YYYY-Qn` 出现 **0 个**（gold 有 11–28 个） |
| **反证** | **`exam_hit@5 = 0.800`** ⇒ 检索**找到了真题**，是生成侧没用上 |

⇒ 「查历年真题」必然落到 `question_agent` → 变成出题。
**Phase 1 要做的不是改检索，是补能力**（supervisor 路由 + agent 指令 + 题号输出）。

### (2) Memory 首轮 0 分是 **harness 假象**（已修，非产品缺陷）

根因：服务端在 FastAPI lifespan 才挂 checkpointer（`service.py:129`），
`run_turns` **从不挂** ⇒ 多轮无历史。
实测：第 2 轮问「我叫什么」→ 系统答「我这边暂时没有你的个人信息记录」。
修法：`runner._run_agent` 逐字对齐 `service.lifespan`。修后同测 → 正确答出「林小满 / 计算机技术专硕」。

### (3) ★ Grade 基线曾被 **case 自身缺陷**压低（已修）

- **初版 15/15 条 Grade case 都缺选项**：`_STEM_RE` 在首个选项行截断，
  query 却是「请批改我的作答：<题干> 我选 A。」⇒ 系统只能回
  「请补充该题的选项内容，否则无法判定」。
- ⇒ 原 μ=3.467 测的是「无法批改缺选项的题」，**是假象**。
- 修法：query 改为「题干 + 选项 + 我选 X」。**修复后 μ 3.467 → 4.133，pass 0.733 → 0.800**。

### (4) Memory 归因口径（judge 误用 QA rubric）

- 根因：judge 对 Memory 用的是 `_RUBRIC_QA_VERIFY` ⇒ 6/6 被标 `retrieval_miss`，
  但 memory 的 query 本就不是知识查询，检索返空属**预期**。
- 修法三处：① `mechanical_failures` memory 豁免检索判据；
  ② `apply_judge` 过滤 memory 的检索层 reasons；③ 新增 `_RUBRIC_MEMORY`
  （按「长期记忆是否被正确使用」0–5 + 强制逐项填三维）；
  ④ 报告把 memory 检索列改为 **N/A**，改报四率。
- 效果：主因 `retrieval_miss` → **`memory_miss`**；correct-use 0.200 → **0.600**
  （★ 该提升来自**口径修正**，不是产品改进）。

---

## 3. `generation_ok` 复核结论：**evaluator 没问题**

用户假设「输出完整正确、只是缺正则字样」。实测 `grd-001` 回复全文：

> 请补充该题的选项内容（A/B/C/D 分别是什么），否则无法判定「A」对应的层次是否正确。

= **澄清请求，不是评分结果** ⇒ `generation_ok=False` **判定正确**。
错的是 **judge 给了 5.0**（把澄清请求当满分）—— 这正是 judge calibration 要解决的问题。

---

## 4. 校准集（已按用户裁决重建）

`evals/datasets/demo/calibration_30.jsonl` = **QA 10 + Generate 10 + Grade 10**（各占 1/3），
30/30 已预填 `llm_score` 与系统输出，**Verify 与 Memory 均不参与**。

- **Verify 15 条保留在 0B baseline**（未删除）—— 它是 Phase 1 的头号证据。
- **Memory 排除**：其判据是四率，不是 QA rubric。

`gold_review.jsonl` 30 条待人工（Generate 难度/答案、Grade `human_score` 0–100）。

---

## 5. 额度现状与 1M 预算方案

账号欠费已充值，实测恢复。**总预算 1M tokens**，按优先级分配：

| 用途 | 估算 | 说明 |
|---|---|---|
| **Judge calibration（30 条）** | **0** | ★ `llm_score` 已在 record 里，`calibrate` 是**纯计算**、零 LLM 调用 |
| Phase 1 ① Verify 能力修复后重跑 15 条 | ~10万 | 第一优先级 |
| Phase 1 每轮**定向**重跑（只跑受影响子集） | 10–15万/轮 | 例：只重跑 Verify 15 或 Grade 15 |
| 全量 66 条重跑 | 37–45万 | 尽量少做 |
| Final Gate 终评集 145 条 | 82–99万 | ❌ 需再充值 |
| RAGAS 扩样 60 条 | **158–264万** | ❌ **超出 1M 预算** |

**建议**：1M 全部投在 **Phase 1 定向迭代**上（10–15万/轮 → 可做 6–8 轮）。
**不要做全量重跑**；**RAGAS 60 条本次放弃**（或维持 n=20 的冻结集，成本约 53–88万，仍偏高）。

> 省钱铁律：**改了哪一层，就只重跑受影响的 case 子集** —— 不要每轮全量 66。

## 6. 下一步

| 项 | 状态 |
|---|---|
| Phase 0B 基线 | ✅ **66/66 全部有效** |
| Gold Sanity | ✅ PASS |
| Judge calibration | ⏸ 只差**人工填 `human_score` 0–5**（30 行）；填完跑 `calibrate`，**0 token** |
| Phase 1 优先级 | **① Verify 能力 → ② Generate/Grade 的真实低分 case** |
