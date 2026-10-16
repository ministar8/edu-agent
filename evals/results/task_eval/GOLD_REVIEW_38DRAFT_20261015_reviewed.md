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
- **原登记的 5 条撞键清单需更正**：对当前仓库 `evals/datasets/demo/verify_cases.jsonl` 逐项核对后，`ver-002` 确含 `2009-Q11`，`ver-007` 确含 `2011-Q5`；但 `ver-008`、`ver-012`、`ver-013` 的当前 `expected_question_ids` 均**不含 `2021-Q3`**。因此当前数据实际对应这两条题号交集，而不是 5 条。两题仍与各自 query 的考点相关；答案键错误应走 A1(d) 单独登记 `correct_key`（`2009-Q11 → C`、`2011-Q5 → C`），不应删除有效的题号引用。**2021-Q3 的键订正仍需在 A1 样本链处理，但不能记到这三条 verify case 上。**
- 本次对 15 条 `expected_question_ids` 做了仓库题库 ID 存在性与 `kp_ids` 逐条比对；全部 ID 均存在，且当前标签与所问主题相符（`ver-015` 例外：题目清单只覆盖 exact 标签，query 语义过宽，见逐条审阅）。不过 verify 数据尚未补 `gold_source_ref`，且本次不是逐题查看官方原卷扫描件，因此这些 `pass` 只表示**当前题库元数据下内容层通过**，不等于来源追溯与官方原卷复核已经完成。
- 其余 10 条：逐键核对题号在原卷存在且知识点匹配；引用层若整层被 A1 (b) 降级，
  该条期望列表按降级层口径复核（值不降级、指针修正）。
- 通过判据：15/15 有 verdict；撞键 5 条有 correct_key 或删除记录；`gold_source_ref` 补齐。

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

## 四、逐条可填工作表（38 条）

> 填法：读「query + 待审字段」→ 按 §一 口径人工审定 → 「结论」列填 `pass` / `correct_key:<X>` / `needs_fix`。
> 结论回填数据集由项目方机械执行（脚本不代签；本表结论必须人工签）。

| case_id | 任务 | query（定位用） | 待审 gold 字段 | 审核结论 |
|---|---|---|---|---|
| qa-001 | qa | Cache 的作用是什么？ | reference=Cache 位于 CPU 与主存之间，存放近期使用的程序与数据，缓解 CPU 与…；expected_kp=['co.storage'] | pass |
| qa-002 | qa | 什么是二叉搜索树？ | reference=二叉搜索树是每个节点左子树键值均小于该节点、右子树键值均大于该节点的二叉树，支持…；expected_kp=['ds.tree'] | pass |
| qa-003 | qa | TCP 三次握手的作用是什么？ | reference=三次握手用于同步双方初始序号、确认收发能力并协商 MSS 等参数，避免历史连接造…；expected_kp=['cn.transport'] | pass |
| qa-004 | qa | 什么是进程死锁？死锁的四个必要条件是什么？ | reference=死锁是多个进程互相等待对方持有的资源而都无法继续执行的状态。四个必要条件：互斥、…；expected_kp=['os.process'] | pass |
| qa-005 | qa | 什么是存储器层次结构？ | reference=典型层次为寄存器-Cache-主存-辅存；Cache-主存解决速度问题，主存-辅…；expected_kp=['co.storage'] | pass |
| qa-006 | qa | 栈和队列的主要区别是什么？ | reference=栈是后进先出（LIFO），队列是先进先出（FIFO）；栈只能在栈顶操作，队列在队…；expected_kp=['ds.stack_queue'] | pass |
| qa-007 | qa | TCP 和 UDP 的主要区别是什么？ | reference=TCP 面向连接、可靠、有序、有流量与拥塞控制；UDP 无连接、不保证可靠，开销…；expected_kp=['cn.transport'] | pass |
| qa-008 | qa | 虚拟内存的作用是什么？ | reference=虚拟内存让进程逻辑地址空间可以大于物理内存，通过分页/置换在磁盘与内存间换入换出…；expected_kp=['os.memory'] | pass |
| qa-009 | qa | MAR 和 MDR 分别是什么？ | reference=MAR 是主存地址寄存器，保存访问地址；MDR 是主存数据寄存器，保存读出或待写…；expected_kp=['co.overview', 'co.storage'] | pass |
| qa-010 | qa | 什么是哈希冲突？如何解决？ | reference=哈希冲突指不同关键字映射到同一地址。解决方法包括开放定址法、链地址法（拉链法）、…；expected_kp=['ds.search'] | pass |
| qa-011 | qa | 什么是拥塞控制？TCP 拥塞控制有哪些阶段？ | reference=拥塞控制防止过多数据注入网络导致性能下降；TCP 常见阶段为慢开始、拥塞避免、快…；expected_kp=['cn.transport'] | needs_fix |
| qa-012 | qa | 页面置换算法中的 Belady 异常说明了什么？ | reference=Belady 异常指某些算法（如 FIFO）在物理块增加时缺页次数反而上升，说明…；expected_kp=['os.memory'] | pass |
| qa-013 | qa | 什么是流水线？流水线冒险有哪些？ | reference=流水线将指令重叠执行提高吞吐；冒险包括结构冒险、数据冒险、控制冒险，可通过转发、…；expected_kp=['co.cpu'] | pass |
| qa-014 | qa | 快速排序的基本思想是什么？ | reference=选基准将序列划分为小于和大于基准的两部分，递归排序子序列；平均时间复杂度 O(n…；expected_kp=['ds.sort'] | pass |
| qa-015 | qa | IP 地址与 MAC 地址有什么区别？ | reference=IP 地址是网络层逻辑地址，用于路由；MAC 地址是数据链路层物理地址，用于同一…；expected_kp=['cn.network', 'cn.datalink'] | pass |
| ver-001 | verify | 网络体系结构考过哪些真题？ | expected_question_ids=11 个：逐键核原卷 | pass |
| ver-002 | verify | 冯·诺依曼结构考过哪些真题？ | expected_question_ids=3 个 ⚠撞键['2009-Q11']：逐键核原卷 | pass |
| ver-003 | verify | 栈考过哪些真题？ | expected_question_ids=23 个：逐键核原卷 | pass |
| ver-004 | verify | 进程状态与转换考过哪些真题？ | expected_question_ids=28 个：逐键核原卷 | pass |
| ver-005 | verify | 流量控制考过哪些真题？ | expected_question_ids=9 个：逐键核原卷 | pass |
| ver-006 | verify | 浮点数 IEEE754考过哪些真题？ | expected_question_ids=16 个：逐键核原卷 | pass |
| ver-007 | verify | 树与森林转换考过哪些真题？ | expected_question_ids=12 个 ⚠撞键['2011-Q5']：逐键核原卷 | pass |
| ver-008 | verify | 处理机调度考过哪些真题？ | expected_question_ids=15 个：逐键核原卷 | pass |
| ver-009 | verify | 传输介质考过哪些真题？ | expected_question_ids=2 个：逐键核原卷 | pass |
| ver-010 | verify | Cache考过哪些真题？ | expected_question_ids=18 个：逐键核原卷 | pass |
| ver-011 | verify | 完全二叉树考过哪些真题？ | expected_question_ids=3 个：逐键核原卷 | pass |
| ver-012 | verify | 死锁考过哪些真题？ | expected_question_ids=10 个：逐键核原卷 | pass |
| ver-013 | verify | TCP考过哪些真题？ | expected_question_ids=23 个：逐键核原卷 | pass |
| ver-014 | verify | 主存储器考过哪些真题？ | expected_question_ids=14 个：逐键核原卷 | pass |
| ver-015 | verify | 二叉树考过哪些真题？ | expected_question_ids=4 个：逐键核原卷 | needs_fix |
| gen-005 | generate | 请出一道考查相对寻址的题。 | A2 遗留：gen-005 补选项后盲标 / gen-009 重生成题干后盲标（不得回头看系统答案） | needs_fix |
| gen-009 | generate | 请出一道考查指令流水线的题。 | A2 遗留：gen-005 补选项后盲标 / gen-009 重生成题干后盲标（不得回头看系统答案） | needs_fix |
| mem-001 | memory | 帮我批改这道题：在右图所示的平衡二叉树中，插入关键字 48 后得到一棵新平衡二叉树。在新平衡… | expected_memory(type=weak_topics, values=['平衡二叉树'], should_be_recalled=True)；禁忌值={'forbidden_values': ['栈', '队列']} | needs_fix |
| mem-002 | memory | 帮我看看这道题对不对：用邻接矩阵存储无向图时，第 i 行非零元素的个数就是顶点 i 的度。我… | expected_memory(type=weak_topics, values=['图的存储'], should_be_recalled=True)；禁忌值={'forbidden_values': ['排序', '栈']} | pass |
| mem-003 | memory | 批改一下：关于快速排序，我认为它是稳定排序，并且最坏情况时间复杂度是 O(n log n)。… | expected_memory(type=weak_topics, values=['快速排序'], should_be_recalled=True)；禁忌值={'forbidden_values': ['图', '栈']} | pass |
| mem-004 | memory | 帮我批改：若平衡二叉树的高度为 6，且所有非叶结点的平衡因子均为 1，则该平衡二叉树的结点总… | expected_memory(type=weak_topics, values=['平衡二叉树'], should_be_recalled=False)；禁忌值={'forbidden_values': []} | needs_fix |
| mem-005 | memory | 你好，我想了解一下考研 408 的备考节奏。 | expected_memory(type=weak_topics, values=['图'], should_be_recalled=False)；禁忌值={'forbidden_values': []} | pass |
| mem-006 | memory | 帮我批改这道题，我很有把握：下列关于图的叙述中，正确的是。I. 回路是简单路径 II. 存储… | expected_memory(type=weak_topics, values=['图'], should_be_recalled=False)；禁忌值={'forbidden_values': []} | pass |

## 三、状态

- [ ] verify 15（含撞键 5 条与 A1 扩查联动）
- [ ] qa 15
- [ ] generate 2（gen-005 补选项 / gen-009 重生成，均需盲标）
- [ ] memory 6
- [ ] 收口链复跑 + A4 frozen 裁决

> 人工成本参照：A1 扩查 (c) 已由 owner 订正为 ≈4–5 人时；本工作单 38 条按 ①~④ 分工估计
> 与 A1 (c) 有重叠（verify 15 条可并批），总估 ≈3–4 人时（不含并批收益的保守值）。


## 五、逐条审核结论与理由（本次审核记录）

> 判定范围：对当前默认分支的 `evals/datasets/demo/{qa,verify,generate,memory}_cases.jsonl`、题库 `knowledge/exams/<year>/items.md` 的题号存在性与 `kp_ids`，以及 `_kp_ds.py`、`_kp_cn.py`、`_kp_co.py`、`_kp_os.py` 的考点层级作了核验。`pass` 表示当前字段在这个范围内可接受；并不自动豁免工作单要求的 source_ref、原卷核读、sanity/backfill 或 owner 冻结裁决。

### QA（15 条）

| case_id | 结论 | 审核说明 / 建议 |
|---|---|---|
| qa-001 | pass | Cache 位于 CPU 与主存之间，利用局部性缓存近期/常用指令与数据，缓和速度差距；`co.storage` 与问题主题相符。可选精化为 `co.storage.cache`。 |
| qa-002 | pass | BST 的左子树键值小于根、右子树键值大于根的定义与有序操作描述基本正确；`ds.tree` 相关。若要提升判据区分度，建议 `expected_kp` 精化为 `ds.tree.bst`。 |
| qa-003 | pass | 三次握手同步初始序号、确认双向通信能力并交换 MSS 等选项，答案成立；`cn.transport` 相关。可精化为 `cn.transport.tcp_handshake`。 |
| qa-004 | pass | 死锁定义及互斥、占有并等待、不可抢占、循环等待四条件正确；`os.process` 覆盖该题。 |
| qa-005 | pass | 寄存器—Cache—主存—辅存的典型层次及速度/容量折衷描述正确；`co.storage` 相关。可精化为 `co.storage.hierarchy`。 |
| qa-006 | pass | LIFO/FIFO 和栈顶/队头队尾操作对照正确；`ds.stack_queue` 精度合适。 |
| qa-007 | pass | TCP/UDP 的连接、可靠性、顺序与控制机制比较总体正确；`cn.transport` 覆盖两者。可将目标 KP 精化为 TCP 与 UDP 两个节点。 |
| qa-008 | pass | 虚拟内存、分页/换入换出、逻辑空间和隔离描述总体正确；`os.memory` 相关。建议区分虚拟内存与页面置换细节。 |
| qa-009 | pass | MAR 保存主存访问地址，MDR 保存读出/待写数据，定义正确；两个宽口径 KP 均可解释，但映射粒度偏宽，建议后续结合 registry 统一 MAR/MDR 的归属。 |
| qa-010 | pass | 哈希冲突定义及开放定址、链地址、再哈希等常见处理方法正确；`ds.search` 相关。可精化为 `ds.search.hash`。 |
| qa-011 | needs_fix | 事实列表基本正确，但把慢开始、拥塞避免、快重传、快恢复统称“阶段”不够严谨；常见表述是前两者为拥塞窗口控制阶段，快重传/快恢复是丢包检测与恢复机制（教材可能统称拥塞控制算法）。建议改写 reference，保留可接受教材口径。 |
| qa-012 | pass | Belady 异常说明增加物理块仍可能增加缺页，FIFO 可出现、LRU/OPT 等栈算法不会；说明与“堆栈性质”一致。 |
| qa-013 | pass | 流水线提升吞吐，结构/数据/控制冒险分类及转发、暂停、分支预测等缓解方式正确；`co.cpu` 相关。可精化到流水线/冒险节点。 |
| qa-014 | pass | 快排选基准并划分、递归处理左右子序列；平均 `O(n log n)`、最坏 `O(n²)` 正确；`ds.sort` 相关。可精化为 `ds.sort.quick_sort`。 |
| qa-015 | pass | IP 的网络层逻辑编址/路由与 MAC 的链路内交付职责区分正确；`cn.network` 与 `cn.datalink` 合理。 |

### Verify（15 条）

| case_id | 结论 | 审核说明 / 后续动作 |
|---|---|---|
| ver-001 | pass | 11 个题号均存在于对应年度 `items.md`，当前 `kp_ids` 均为 `cn.arch.model`；需补逐题 `gold_source_ref`。 |
| ver-002 | pass | 3 个题号均存在且 `kp_ids=co.overview.von_neumann`。`2009-Q11` 题号与主题相关，答案键另走 `correct_key:C`，不要从期望题号表删除。需补 source refs。 |
| ver-003 | pass | 23 个题号均存在且对应栈节点；需补逐题 source refs。 |
| ver-004 | pass | 28 个题号均存在且标记为进程状态/转换；需补逐题 source refs。 |
| ver-005 | pass | 9 个题号均存在且标记为链路层流量控制；需补逐题 source refs。 |
| ver-006 | pass | 16 个题号均存在，均含 IEEE 754 标签（其中 1 条同时涉及补码）；需补逐题 source refs。 |
| ver-007 | pass | 12 个题号均存在且涉及树/森林转换；`2011-Q5` 的题号相关，答案键另走 `correct_key:C`。需补 source refs。 |
| ver-008 | pass | 15 个题号均存在且当前标签为处理机调度；实际清单不含 `2021-Q3`，工作单上方原“撞键”说明过期。需补 source refs。 |
| ver-009 | pass | 2 个题号均存在且标记为传输介质；需补 source refs。 |
| ver-010 | pass | 18 个题号均存在且有 Cache 标签（其中 1 条同时涉及 TLB）；需补 source refs。 |
| ver-011 | pass | 3 个题号均存在且标记为完全二叉树/二叉树；需补 source refs。 |
| ver-012 | pass | 10 个题号均存在且标记为死锁；实际清单不含 `2021-Q3`。需补 source refs。 |
| ver-013 | pass | 23 个题号均存在且标记为 TCP；实际清单不含 `2021-Q3`。需补 source refs。 |
| ver-014 | pass | 14 个题号均存在且标记为主存储器；需补逐题 source refs。 |
| ver-015 | needs_fix | 当前 4 个 ID 都存在且带 `ds.tree.binary_tree`/`ds.tree.complete` 标签，但 query“二叉树考过哪些真题？”比 exact 标签宽，容易漏掉遍历、BST、AVL 等相关真题。建议二选一：将 query 改为“哪些真题被标注为二叉树基础节点”，或按预期覆盖范围扩展 ID 列表并定义范围。需补 source refs。 |

**Verify 全组收口条件：** 当前内容层为 14 pass / 1 needs_fix；但 15 条都没有 `gold_source_ref`，不能据此直接把 `gold_status` 升为 `reviewed`/`frozen`。建议按每个 ID 记录 `knowledge/exams/<year>/items.md#<question_id>` 的指针，并按项目原定流程另做原卷图文核读。公开/仓库第三方题库元数据核验不等价于官方原卷签署。

### Generate（2 条）

| case_id | 结论 | 审核说明 / 后续动作 |
|---|---|---|
| gen-005 | needs_fix | 选择题缺 A–D 选项，无法给出可复核的选项字母；当前不能正式盲标。先修复题面/选项，再由未看系统标准答案的标注者独立填写 `gold_answer` 与难度。 |
| gen-009 | needs_fix | anchor⑤ 归档显示 `generation_ok=false`，回复没有实际题干；无题可答。重生成完整流水线题后另起盲标，不能根据“指令流水线”主题编造 gold。 |

### Memory（6 条）

| case_id | 结论 | 审核说明 / 后续动作 |
|---|---|---|
| mem-001 | needs_fix | A 段第一题引用“右图”但 turns 中没有随题图，难以核实作答是否应低分；第二题只给“删除后再插入同一结点、原树高 5”，缺少原树结构/删除结点，`我答 4` 不足以稳定判错。两次 `[0,59]` 前置条件没有可靠保证；替换为两道完整、可确定判分、同落 AVL 考点的错题。 |
| mem-002 | pass | 两次回答都可判错：无向图邻接矩阵对称，行/列计数相同，第一题“应看列所以原句错”不成立；简单无向图 6 顶点 10 边的邻接矩阵有 20 个非零对称项，答 10 错。两次都落图存储，适合作为弱点应召回正样本。 |
| mem-003 | pass | 两次回答都与快速排序知识相反：快速排序通常不稳定、最坏 `O(n²)`；一趟划分后枢轴到达该趟最终位置，不再进入左右子序列。弱点值精确指向“快速排序”，禁忌值用于排查无关话题污染，符合设计目的。 |
| mem-004 | needs_fix | 题面条件下，高度 6 且每个非叶结点平衡因子同为 1 时，按 `N(h)=1+N(h−1)+N(h−2)`、`N(0)=0,N(1)=1` 得 `N(6)=20`；当前学生答案“20”是正确答案，不应期待 `[0,59]` 低分。若要测试“一次弱点命中未达 MIN_HITS”，请把学生答案改成明确错误值并确认预期低分，保留一次 grade call。 |
| mem-005 | pass | 0 次批改、0 次记忆写入，`should_be_recalled=false` 的负样本逻辑正确。非阻断提醒：query 是跨四科备考咨询，但 `subject=ds` 是偏置元数据，需确认 memory 实验是否故意将其固定为 ds。 |
| mem-006 | pass | 两个作答均为正确的高分样本：图论陈述中只有 III 成立；无向连通图最少边数为 `n−1`。同主题高分不应计入 weak topics，因此不应召回“图”，符合负样本目的。 |

## 六、总判定与冻结阻断项

| 类别 | 内容层 pass | needs_fix | 备注 |
|---|---:|---:|---|
| QA | 14 | 1 | `qa-011` 修正拥塞控制阶段/机制措辞后复核 |
| Verify | 14 | 1 | `ver-015` 明确范围；全部 15 条补齐 `gold_source_ref` 后才能完成来源收口 |
| Generate | 0 | 2 | `gen-005` 补选项、`gen-009` 重生成完整题干并重新盲标 |
| Memory | 4 | 2 | `mem-001` 换成可判分问题；`mem-004` 改成真正低分的一次命中案例 |
| **合计** | **32** | **6** | 内容审核已逐条给结论；**尚不支持直接 38/38 升 reviewed 或 66 条 frozen** |

**独立答案键纠错（不要混入 Verify 的 question ID gold）：** `2009-Q11 → C`、`2011-Q5 → C` 应按 A1(d) 另行追加 `correct_key` 记录，旧值不回写；`2021-Q3` 的键订正仍走 A1，但当前 `ver-008`/`ver-012`/`ver-013` 清单均不含该题号。

**当前未完成的冻结前动作：** 修复 6 条 `needs_fix`；为 Verify 15 条补来源指针；对要作为正式证据的真题引用完成原卷核读；回填数据集后执行 `task_eval sanity`，必要时 backfill 新归档、重建 ledger 并 `--check`，最终由 owner 裁决 A4。此工作单不是自动签名，也没有声称已运行项目的测试命令。
