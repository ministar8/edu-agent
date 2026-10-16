# GOLD_REVIEW 38 条 draft 审核工作单（2026-10-15）

> **由来**：owner 裁定 A4「`gold_status` reviewed→frozen 升格前，须先补 38 条 draft 的审核口径」——
> 依据实测：demo 五集 66 条 `gold_status` = **reviewed 28（generate 13 + grade 15）/ draft 38
> （qa 15 + verify 15 + generate 2 + memory 6）**，清单原「66 条 reviewed→frozen」前提不成立
> （复现：`python -c` 统计 `evals/datasets/demo/*_cases.jsonl` 的 `gold_status` 分布）。
> **规程**：审核必须人工做、脚本不得代签（与 `GOLD_REVIEW`/`GRADE_KEY_VERIFY` 同一条纪律）；
> 审核结论回填数据集后复跑 `task_eval sanity` →（若影响判据）backfill 新归档 → ledger 重建，
> 再由 owner 裁决 A4 升格 frozen。
> **关联裁定**：A1 有条件采纳（§20.7.6⑤——出错层降级只针对「来源可靠性未证」的**键可靠性结论**，
> 已独立人工核验过的 gold 值不追溯降级）；B6（`gen_difficulty` 中文难度行暂行登记，见 ③）。

## 一、逐任务审核口径（38 条怎么审）

### 1. verify 15 条（draft）—— **最高优先，与 A1 错键处置直接联动**
- gold 字段：`expected_question_ids`（期望被引用到的历年真题题号列表）。
- **实测撞键（2026-10-15 19:30 更正）**：期望列表含 A1 已确认错键的是 **2 条**——`ver-002`（含 2009-Q11）、
  `ver-007`（含 2011-Q5）。⇒ 这 2 条的审核**必须与 A1 (c) 扩查合并做**：
  持原卷逐键核对「题号存在性 + 该题是否真的考了 query 问的知识点」，错键按 A1 (d) 走
  `correct_key` 订正（样本 JSON 已有 13 条正键的先例），**旧值不回写、订正登记新行**。
- ⚠️ **更正留痕（本单原第 17–18 行有误，owner 审核时独立发现）**：原记「5 条撞键」多列了
  `ver-008`/`ver-012`/`ver-013`（称均含 2021-Q3）——那是一次**无边界子串匹配误报**（「2021-Q3」
  命中了 `2021-Q31/Q32/Q38/Q40` 等长题号），机械复算确认三者期望列表均不含 2021-Q3
  （复现：`evals/claims/p1_expanded_audit_20261015.json` 的 `correction_20261015_1930` 字段）。
- **owner 审核结论（2026-10-15）**：ver-002/ver-007 的题号引用与知识点相关、**引用有效不删除**；
  答案键纠错单独按 A1 (d) 登记 `correct_key`，**不得因答案键错误而删除有效题号引用**。
- 其余 10 条：逐键核对题号在原卷存在且知识点匹配；引用层若整层被 A1 (b) 降级，
  该条期望列表按降级层口径复核（值不降级、指针修正）。
- 通过判据：15/15 有 verdict；撞键 2 条（ver-002/ver-007）按 owner 结论保留题号引用、答案键纠错单走 A1 (d)；`gold_source_ref` 补齐。

### 2. qa 15 条（draft）
- gold 字段：`expected_kp`（期望命中知识点）+ `reference`（参考答案文本）。
- 口径：`reference` 人工对照权威教材/真题解析逐条审定（允许「多解」但须写明可接受判据）；
  `expected_kp` 与题面知识点人工核对。无 registry 判据对象（QA 行恒「已测量未证明」，
  引用只能带披露）⇒ 审核只服务 gold 完整性与 Grade/检索旁证，不产生签署。

### 3. generate 2 条（draft；A2 遗留）
- `gen-005`（`incomplete_source`：选择题选项缺失，第 1 小题可算）：补齐选项后盲标复核
  （**盲态纪律**：不得回头看系统已生成答案）。
- `gen-009`（`missing_key`：锚点⑤归档 `generation_ok=false`、无题干）：重生成题干后再盲标。
- 两条修复后复跑 sanity/backfill/ledger（§20.7.5 已登记流程）；`gold_status` 随盲标结论升 reviewed。

### 4. memory 6 条（draft）
- gold 字段：`expected_memory`（期望召回值 + `should_be_recalled`）、`expected_answer_property`
  （禁忌值，如「栈/队列」不得作为答案）、`setup_conditions`（前置条件：批改次数/分段）。
- 口径：逐条审定「期望召回值是否确为该生语境下的弱知识点/应忆项」「禁忌值是否覆盖主要混淆项」；
  `setup_conditions` 与 case 多轮脚本人工核对。memory 三维有 registry 判据（`memory_correct_use`），
  审核结论直接影响该行读数 ⇒ 审完必须复跑 sanity + ledger。

## 二、审核后动作（收口链）

1. 结论回填 `evals/datasets/demo/*_cases.jsonl`（`gold_answer_status` / `gold_source_ref` 四件套、
   `gold_status` draft→reviewed；行尾 LF 不变；`git diff` 只允许数据行变化）。
2. `task_eval sanity` ERROR 0（PENDING 集合级存量项照实披露）。
3. 若 gold 变化影响判据读数：`gold_blindlabel_apply` 同款注入 → `task_eval backfill` 新归档 →
   `build_claim_ledger.py` 重建 → `--check`（第 1 段 PASS、V0 ① 缺键 0、第 2 段无新增孤立行）。
4. 全部 reviewed 后由 **owner 裁决 A4**：66 条 `gold_status` 升 `frozen`（2026-10-06 曾裁
   reviewed，明示「出论文数字前需最终升为 frozen」）；gold sha256 记入新归档 provenance。

## 三、逐条可填工作表（38 条）

> 填法：读「query + 待审字段」→ 按 §一 口径人工审定 → 「结论」列把 ☐ 换成 `pass` / `needs_fix`（个别行可用 `correct_key:<X>`）。
> 表中 ⚠撞键=该行期望列表含 A1 已确认错键；「暂定不一致」=含扩查第三方页读数与仓库键不一致的题号（**待正式原卷复核，不是 fail**）；「空键」=仓库 items.md 该题 `answer_key: null`（出处缺陷既定）。
> 结论回填数据集由项目方机械执行（脚本不代签；本表结论必须人工签）。

| case_id | 任务 | query（定位用） | 待审 gold 字段 | 结论 ☐ |
|---|---|---|---|---|
| qa-001 | qa | Cache 的作用是什么？ | reference=Cache 位于 CPU 与主存之间，存放近期使用的程序与数据，缓解 CPU 与…；expected_kp=['co.storage'] | ☐ |
| qa-002 | qa | 什么是二叉搜索树？ | reference=二叉搜索树是每个节点左子树键值均小于该节点、右子树键值均大于该节点的二叉树，支持…；expected_kp=['ds.tree'] | ☐ |
| qa-003 | qa | TCP 三次握手的作用是什么？ | reference=三次握手用于同步双方初始序号、确认收发能力并协商 MSS 等参数，避免历史连接造…；expected_kp=['cn.transport'] | ☐ |
| qa-004 | qa | 什么是进程死锁？死锁的四个必要条件是什么？ | reference=死锁是多个进程互相等待对方持有的资源而都无法继续执行的状态。四个必要条件：互斥、…；expected_kp=['os.process'] | ☐ |
| qa-005 | qa | 什么是存储器层次结构？ | reference=典型层次为寄存器-Cache-主存-辅存；Cache-主存解决速度问题，主存-辅…；expected_kp=['co.storage'] | ☐ |
| qa-006 | qa | 栈和队列的主要区别是什么？ | reference=栈是后进先出（LIFO），队列是先进先出（FIFO）；栈只能在栈顶操作，队列在队…；expected_kp=['ds.stack_queue'] | ☐ |
| qa-007 | qa | TCP 和 UDP 的主要区别是什么？ | reference=TCP 面向连接、可靠、有序、有流量与拥塞控制；UDP 无连接、不保证可靠，开销…；expected_kp=['cn.transport'] | ☐ |
| qa-008 | qa | 虚拟内存的作用是什么？ | reference=虚拟内存让进程逻辑地址空间可以大于物理内存，通过分页/置换在磁盘与内存间换入换出…；expected_kp=['os.memory'] | ☐ |
| qa-009 | qa | MAR 和 MDR 分别是什么？ | reference=MAR 是主存地址寄存器，保存访问地址；MDR 是主存数据寄存器，保存读出或待写…；expected_kp=['co.overview', 'co.storage'] | ☐ |
| qa-010 | qa | 什么是哈希冲突？如何解决？ | reference=哈希冲突指不同关键字映射到同一地址。解决方法包括开放定址法、链地址法（拉链法）、…；expected_kp=['ds.search'] | ☐ |
| qa-011 | qa | 什么是拥塞控制？TCP 拥塞控制有哪些阶段？ | reference=拥塞控制防止过多数据注入网络导致性能下降；TCP 常见阶段为慢开始、拥塞避免、快…；expected_kp=['cn.transport'] | ☐ |
| qa-012 | qa | 页面置换算法中的 Belady 异常说明了什么？ | reference=Belady 异常指某些算法（如 FIFO）在物理块增加时缺页次数反而上升，说明…；expected_kp=['os.memory'] | ☐ |
| qa-013 | qa | 什么是流水线？流水线冒险有哪些？ | reference=流水线将指令重叠执行提高吞吐；冒险包括结构冒险、数据冒险、控制冒险，可通过转发、…；expected_kp=['co.cpu'] | ☐ |
| qa-014 | qa | 快速排序的基本思想是什么？ | reference=选基准将序列划分为小于和大于基准的两部分，递归排序子序列；平均时间复杂度 O(n…；expected_kp=['ds.sort'] | ☐ |
| qa-015 | qa | IP 地址与 MAC 地址有什么区别？ | reference=IP 地址是网络层逻辑地址，用于路由；MAC 地址是数据链路层物理地址，用于同一…；expected_kp=['cn.network', 'cn.datalink'] | ☐ |
| ver-001 | verify | 网络体系结构考过哪些真题？ | expected_question_ids=11 个：逐键核原卷 | ☐ |
| ver-002 | verify | 冯·诺依曼结构考过哪些真题？ | expected_question_ids=3 个 ⚠撞键['2009-Q11']：逐键核原卷；另 2019-Q12 暂定不一致 | ☐ |
| ver-003 | verify | 栈考过哪些真题？ | expected_question_ids=23 个：逐键核原卷；2011-Q2/2024-Q2/2025-Q2 暂定不一致 | ☐ |
| ver-004 | verify | 进程状态与转换考过哪些真题？ | expected_question_ids=28 个：逐键核原卷；2015-Q12/2025-Q12 暂定不一致 + 2009-Q19 空键 | ☐ |
| ver-005 | verify | 流量控制考过哪些真题？ | expected_question_ids=9 个：逐键核原卷 | ☐ |
| ver-006 | verify | 浮点数 IEEE754考过哪些真题？ | expected_question_ids=16 个：逐键核原卷；2011-Q13/2015-Q14/2021-Q14/2024-Q14 暂定不一致 + 2009-Q13/2021-Q12 空键 | ☐ |
| ver-007 | verify | 树与森林转换考过哪些真题？ | expected_question_ids=12 个 ⚠撞键['2011-Q5']：逐键核原卷；另 2011-Q6/2021-Q4/2025-Q4 暂定不一致 + 2009-Q3/2009-Q6 空键 | ☐ |
| ver-008 | verify | 处理机调度考过哪些真题？ | expected_question_ids=15 个：逐键核原卷 | ☐ |
| ver-009 | verify | 传输介质考过哪些真题？ | expected_question_ids=2 个：逐键核原卷 | ☐ |
| ver-010 | verify | Cache考过哪些真题？ | expected_question_ids=18 个：逐键核原卷；2015-Q16/2019-Q17/2021-Q16/2024-Q17/2024-Q18 暂定不一致 + 2009-Q14 空键 | ☐ |
| ver-011 | verify | 完全二叉树考过哪些真题？ | expected_question_ids=3 个：逐键核原卷 | ☐ |
| ver-012 | verify | 死锁考过哪些真题？ | expected_question_ids=10 个：逐键核原卷 | ☐ |
| ver-013 | verify | TCP考过哪些真题？ | expected_question_ids=23 个：逐键核原卷 | ☐ |
| ver-014 | verify | 主存储器考过哪些真题？ | expected_question_ids=14 个：逐键核原卷；2011-Q14/2011-Q15 暂定不一致 + 2009-Q15 空键 | ☐ |
| ver-015 | verify | 二叉树考过哪些真题？ | expected_question_ids=4 个：逐键核原卷 | ☐ |
| gen-005 | generate | 请出一道考查相对寻址的题。 | A2 遗留：gen-005 补选项后盲标 / gen-009 重生成题干后盲标（不得回头看系统答案） | ☐ |
| gen-009 | generate | 请出一道考查指令流水线的题。 | A2 遗留：gen-005 补选项后盲标 / gen-009 重生成题干后盲标（不得回头看系统答案） | ☐ |
| mem-001 | memory | 帮我批改这道题：在右图所示的平衡二叉树中，插入关键字 48 后得到一棵新平衡二叉树。在新平衡… | expected_memory(type=weak_topics, values=['平衡二叉树'], should_be_recalled=True)；禁忌值={'forbidden_values': ['栈', '队列']} | ☐ |
| mem-002 | memory | 帮我看看这道题对不对：用邻接矩阵存储无向图时，第 i 行非零元素的个数就是顶点 i 的度。我… | expected_memory(type=weak_topics, values=['图的存储'], should_be_recalled=True)；禁忌值={'forbidden_values': ['排序', '栈']} | ☐ |
| mem-003 | memory | 批改一下：关于快速排序，我认为它是稳定排序，并且最坏情况时间复杂度是 O(n log n)。… | expected_memory(type=weak_topics, values=['快速排序'], should_be_recalled=True)；禁忌值={'forbidden_values': ['图', '栈']} | ☐ |
| mem-004 | memory | 帮我批改：若平衡二叉树的高度为 6，且所有非叶结点的平衡因子均为 1，则该平衡二叉树的结点总… | expected_memory(type=weak_topics, values=['平衡二叉树'], should_be_recalled=False)；禁忌值={'forbidden_values': []} | ☐ |
| mem-005 | memory | 你好，我想了解一下考研 408 的备考节奏。 | expected_memory(type=weak_topics, values=['图'], should_be_recalled=False)；禁忌值={'forbidden_values': []} | ☐ |
| mem-006 | memory | 帮我批改这道题，我很有把握：下列关于图的叙述中，正确的是。I. 回路是简单路径 II. 存储… | expected_memory(type=weak_topics, values=['图'], should_be_recalled=False)；禁忌值={'forbidden_values': []} | ☐ |

## 四、状态

- [ ] verify 15（含撞键 2 条 ver-002/ver-007 与 A1 扩查联动）
- [ ] qa 15
- [ ] generate 2（gen-005 补选项 / gen-009 重生成，均需盲标）
- [ ] memory 6
- [ ] 收口链复跑 + A4 frozen 裁决

> 人工成本参照：A1 扩查 (c) 已由 owner 订正为 ≈4–5 人时；本工作单 38 条按 ①~④ 分工估计
> 与 A1 (c) 有重叠（verify 15 条可并批），总估 ≈3–4 人时（不含并批收益的保守值）。
