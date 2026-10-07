# 交接文档 · edu-agent 评测改造（Phase 0B / Phase 1 / Phase 1.5）

> **用途**：换 agent 时的完整交接。**本文件自包含**，新 agent 读完即可接手。
> **时间**：2026-10-07（**E-3/E-4/E-5 完成** + **对抗性 review 的 A/B 两组已修完** —— 偏离表已扩到 #18）
> **提交状态**：2026-10-07 收盘已提交 `63b3b79` / `c5d5bca` / `0f24891` + 锚点回填提交；工作区只剩两项未跟踪 —— `.workbuddy-ai/`（待你删）与 `evals/results/task_eval/`（**刻意不入库**）
>
> ---
>
> ## ★★ 当前状态：环境已恢复，护栏全绿；**缺陷 E 已闭合** + **review 发现的 A/B 两组口径错已修（11 条）**
>
> **embedding / rerank**：`/health` 均 **200**（`tei-embedding` 11435 / `tei-rerank` 11436 均 Up）。
>
> **★ E-5 配对实测（2026-10-07，12 次批改调用，`scripts/memory_e5_probe.py`）**：
>
> | 臂 | 词级跟随率 | `all_canonical` 题级 | 期望入桶 |
> |---|---|---|---|
> | **A** 注入 162 词表 | **0.875**（7/8） | 5/6 | **6/6** |
> | **B** 8 示例（= E-3 前口径） | 0.273（3/11） | 1/6 | 3/6 |
>
> **Δ +0.602**，两臂 system **除词表块外逐字节相同** ⇒ 归因干净。**方案 A 足够**，
> 残留仅 1 个自造词（`无向图`，同题另有 canonical `图的存储` ⇒ 只是噪声桶，不阻断聚合）。
> 详见 §5.6「E-5 结果」。
>
> **护栏结果（2026-10-07 最新，全绿）**：
>
> | Gate | 判据数 | 结果 | 成本 | 与 E-3 的时序 |
> |---|---|---|---|---|
> | `memory_step4fix_gate.py` | **128**（98 → +③s~③u 3 → +⑩e/⑩f 2 → +⑬a~⑬l 13 → **+⑭ 6（D1）+ ⑮ 6（D3/D4）**） | ✅ 全绿 exit 0 | 零 LLM | ★ 每次改动后**都重跑过**，当前可信 |
> | `memory_step4_gate.py` | 14 | ✅ 全绿 | 零 LLM | 指标修复后复跑仍全绿（不触 `GRADE_PROMPT`） |
> | `memory_step2_gate.py` | 11 | ✅ **已在 Step 9 复跑（2 次批改调用）** —— 绿灯，「数字取自 E-3 前」这个缺口已关闭 | 2 次批改 LLM | Step 9 复跑；**E-3 后的真实批改路径已由 E-5 探针（12 次调用）覆盖**，step2 复测留给 Step 9 |
>
> ★ **本机运行这三个脚本必须带 `PYTHONIOENCODING=utf-8`** —— 否则 Windows GBK 控制台
> 在打印 ✅ 时抛 `UnicodeEncodeError`，**崩在 `print` 而非判据失败**，且退出码同为 1，极易误读成红灯。
>
> ## ★★ 2026-10-07 下午新增的两件事（本节只给结论，明细在锚点账本）
>
> **① 对已完成改造做了对抗性 review**（3 路并行审计 + 我逐条自己复核，未复核的都标了出处）。
> 结论登记为 **`docs/EXPERIMENTS.md` §20.5 的 18 条偏离**，其中 **11 条已修（#4/#6/#10/#8/#7 + #11/#12/#14/#15/#17 + #16 钉契约）**、
> **2 条只披露不擅自修（#13/#18）**、**2 条被实测推翻（写在 #16/#17 的证据列里）**：
>
> | 已修 | 内容 | 数字变化 |
> |---|---|---|
> | **#4** | `used` 只看「回复含期望值子串」⇒ **双向错**：负样本碰巧提到就算「用了记忆」（假阳性，`mem-006` 卡为空却 `used=True`）；而规矩地没凭空用记忆的负样本被 AND 判失败（假阴性，`mem-004/005`）。现：`used` 要求 `recalled_actual`，`correct_use` 按极性分定义 | ON 组 `used` **2→1**、`correct_use` **2→4**（0.333→0.667） |
> | **#6** | `case_invalid` 同时进 `failure_rate` 的分子与分母，违反 §2.B「validity ≠ product failure」 | 分母改用「有效 n」，新增 `invalid_n` 字段 + 报告新增「有效 n」列 |
> | **#10** | `category_hit` 旧写法 `.get(subject, subject)` 把学科码拿去比类目名 ⇒ **`cn` 恒 False**，`grade` / `verify` 各有 **4 条被系统性判未命中**；而 `qa`/`generate` 的 case 用 `network` 所以全 True —— **同一函数在两个任务上表现不一致**，这是它长期没暴露的原因 | 加 `_SUBJECT_ALIASES = {"cn": "network"}` 对齐 + **未登记学科记 `None`（N/A）而非 `False`**。护栏 ③j 锁两侧。★ 归档那 8 条**不可离线重算**（记录未保存证据的类目列表）⇒ 正确值等 **Step 9 重跑** |
> | **#8** | `GRADE_PROMPT` 的规则尾写着「不是学科名（如「数据结构」太粗）」，可词表把 **4 个课程根节点**（`node_kind=subject`）也列进了**可选取值**；且它们是 canonical ⇒ 模型选上就能**轻易凑满 `MIN_HITS=2`**，聚成「整门课 = 一个薄弱点」的桶 —— 比自造词**更难发现** | 新增 `kp_vocab.prompt_names_by_subject()`，按**数据字段** `node_kind` 过滤（★ 不写硬编码名单）。`canonical_names()` **仍保 162 全量**（归一化侧必须认得根节点，否则是另一种错）；`domain` 章名（`图`/`排序`/`内存管理`…）**保留**（合法薄弱点，E-5 可接受集就用到了 `图`）。词表 **162→158**、system **1317→1293**。护栏 **⑫k 双向**（剔根节点 + 防过滤过头）。★ **连带后果**：`PROMPT_SET_VERSION` **`f09c75642029` → `2f485d2d7ef7`** ⇒ **E-5 的 0.875 归「#8 之前的中间态」**，新 hash 下需复测（12 次调用，建议并入 Step 9） |
> | **#7** | Grade 的 `human_score` 只有 **0 / 100 两值**（`{100:8, 0:7}`）⇒ `score_tolerance@±10` 没有中间地带可判别，却报出 **1.000** 这种"完美判分能力" | ★ 我**不代填人工分**（那等于伪造论文数据），改做**让退化无处藏**：`metrics.degenerate_gold()`（样本 ≥5 且不同取值 ≤2）⇒ `report` 把 tolerance 置 **N/A** 但**保留 `raw_rate`** 并渲染 ⚠ 说明行；`gold_sanity` 加**集合级 PENDING**（单条 0/100 合法，退化是**分布**性质 ⇒ 不逐条报；且把处置指引打进消息，不只报"1 条"）。★ **真正的解法是换指标而不是补标**——我先前写的"需人工补部分分"**是错的、已撤回**：L3 语料 **674/674 全是 2 分 `choice`**、case 学生答案 **15/15 仅 1 个字母** ⇒ 没有部分分可标。新增 `metrics.verdict_agreement()`（阈值引用 `schema` 自己的 `score<60 视为错误`）⇒ 实测 **0B 15/15、Phase 1 13/13（另 2 条分数不可解析，报告强制披露）**；护栏 **③l~③n + ③o~③r'**。归档的 1.000 不回写 |
>
> **第二批（同日 A/B 两组，全部零 token 验证）** —— 明细在 §20.5 的 #11~#18：
>
> | 已修 | 内容 | 取证 / 护栏 |
> |---|---|---|
> | **#11** | 分数解析取**首个数字** ⇒ `"总分 100 分，你得了 62 分"` 被读成 **100** | 遮蔽「满分/总分 X」后四级解析；解析不到给 **None（N/A）**不是 0 分。③s（5 形态全对）/ ③t（4 条必须 None） |
> | **#12** | API 批改 `record_grade` **不透传 `knowledge_points`** ⇒ 该路径 episode KP 恒空 ⇒ 薄弱点退回「题干前 80 字」 | 补参数；③u 用 AST 锁住「调用参数表里必须有它」 |
> | **#14** | `--rejudge` 照抄 `mechanical_failures`，把 runner 另两处分头写的 `case_invalid`/`memory_miss` **洗掉** ⇒ 归档里 **4 条**无效样本会被画成 `primary_failure=none`（**看起来像通过**） | 保留这两项（都不是 judge 意见）+ 按 `validity_valid` 兜底重建；⑬d 是**反向**（judge-only 的 `generation_wrong` 仍必须清掉，防保留面过宽） |
> | **#15** | `cli.py` 三处 `write_text("\n".join(...))` **不留尾换行**，与 `append_record` 的 `"a"` 相撞 ⇒ 两条粘成一条坏行（实测 3 条只剩 1 条可读） | 行格式收口 `runner.write_jsonl()`（`dump_records` 也走它）+ 追加前**自愈补分隔**。★ **现存 12 份归档末字节都是 `\n`** ⇒ 尚未真的烧到过数据，属**潜伏**；⑬e~⑬g |
> | **#17** | `min_grade_calls: 0` 单独存在是**永真** ⇒ mem-005「全新用户无写入」这条**负样本对照的前提从未被校验**（gold_sanity 却全绿） | 新增 `max_grade_calls`，mem-005 改 `min:0 + max:0`；gold_sanity 加「空标」lint。★ **⑬l 锁「两份归档 12 条 validity 逐条不变」**（`grade_scores` 实测本就是 `[]`）⇒ **不动任何已发表数字** |
> | **#16** | 显式 config **整块替换**、不合并 ambient —— 成立但**仓内无调用方**（`service.py` 两把键一起给） | 🟡 **不改行为**（无流量的假设性加固不做），docstring 写契约 + ⑩f 钉住；★ 同组另一条「并发下回落会算到别人头上」**被实测推翻** ⇒ ⑩e 固化「contextvar 每 Task 副本，4 任务交错各取自己 uid」 |
>
> **只披露、不擅自修的 2 条**：**#13**（模型不产 tool call ⇒ 无原文可救，`memory_e2e_fallback_probe.py` 第 ③ 项确认盲区；
> 是否加兜底**由 Step 9 实测频率决定**）；**#18**（**task_eval 的 gold 数据集本体不在版本控制里** ——
> `git ls-files evals/datasets/demo` = 0，且 `probes/`、`probes_phase1/`、`exam_answer_corrections.json` 同样未跟踪、
> **未被 ignore**（只是没 `git add`）⇒ 建议随 `V-2026-10-07` 把 gold 数据集入库，**待你裁决**）。
> ★ 顺带更正一处我先前写错的话：「`evals/results/` 未入库」**只对了一半** —— 那里跟踪了 21 个文件，
> 没跟踪的只有 `evals/results/task_eval/`。
>
> ★ **归档文件与旧文档仍是旧数字**（未回写任何归档，这是刻意的）⇒ `PHASE1_MEMORY_STEP5_FINDINGS.md`
> 里的 `used=2` 与新口径**不可混用**；两侧数字 §20.5 都记了，Step 9 重跑后按 §20 对照。
>
> **② 效果版本锚点 `V-2026-10-07` 已建**（`docs/EXPERIMENTS.md` §20）：登记触发原因、四路由门禁、
> 结果归属矩阵、9 条偏离。**标签与提交 SHA 已回填**：`63b3b79`（代码）→ `c5d5bca`（gold）→ `0f24891`（文档 = **标签落点**）；解析命令 `git rev-parse "V-2026-10-07^{}"`。
>
> ★ **新披露（§20.5 #9）**：**0B 的 Memory 四率与现口径不可比** —— 0B 归档 memory 记录的 `gold`
> 里**没有 `expected_memory`**（当前 scorer 判 ⇒ 六项全 N/A），可归档却记着 `used/cu=True`
> ⇒ 那组数字不是这套机械 scorer 产的。论文引用 0B 的 Memory μ=2.833 **必须标注口径差异**。
>
> **Step 9 已实跑**（2026-10-07 晚，§20.8.1~§20.8.6）：E-5 在新 hash 下复测通过（Δ +0.727）；
> Memory 三次重复**没有增加跨会话召回的正例**，当时归因到三条 —— 现在逐条交代，**不粉饰也不夸大**：
> ① **A 段第 2 轮有时不调批改工具**（`turn_log` 实证）⇒ **仍然存在**，§20.8.6 的 ON 侧 `mem-001`/`mem-003` 又被它打掉两次（OFF 侧同样复现 ⇒ 与 Store 无关，是 agent 行为的概率性问题）；
> ② ~~错题被判 100 分（缺陷 A 现存症状）~~ → **本条归因作废**：复算证明那题的学生作答**是对的**（一趟 Hoare 划分即 `38,49,65,97,76`），模型判 100 分判对了，错在 gold 要求两次都低分 ⇒ 属 case 设计缺陷（D8 已修）。真正的误判在**反方向**：小根堆那题答对却被判 0 分 ⇒ 新增登记 **#25**（只披露，单次观察、不进任何已发表指标）；
> ③ **#22 正样本设计**（A 段两问不同考点 ⇒ 画像恒空）⇒ ✅ **已由 D8 修掉**（A 段两题对齐同一考点）。
> ★ **且本轮推翻了「OFF 对照干净」这句话**（#24）：旧 OFF 臂只置 `agent.store=None`，而 `load_memory`/`_record_episode` 取的是**进程级** `get_store()` ⇒ OFF 与 ON 是同一条件，既有 OFF 组的对照证据**全部作废**。
> ⇒ 论文口径改为（§20.8.6）：「跨会话召回有 **1 例严格配对**证据 —— `mem-002` 同 case、同前置条件下 ON 有卡且 `recalled/used/correct_use` 全 True、OFF 零卡未召回；可测正样本 **n=1**，另有 2 例因 A 段未调用批改工具而不可测。」

---

# 一、项目背景

408 考研辅导多 Agent 系统（supervisor → knowledge / question / grading 三个专家）。
正在按 `docs/EFFECT_PLAN.md` 做**效果完整度提升**，分阶段推进。

**核心度量工具**：`evaluation.task_eval`（66 条 demo case，5 个任务：qa / generate / grade / verify / memory）

---

# 二、总进度（EFFECT_PLAN 9 个阶段）

| 阶段 | 状态 |
|---|---|
| §2.A 0A Smoke | ✅ 完成 |
| **§2.B 0B 诊断基线** | ✅ **完成并冻结**（`gold_status=reviewed`） |
| §2.B.5 Exit Criteria | ✅ 满足 |
| **§3 Phase 1 — Verify 修复** | ✅ **完成并收尾** |
| **§4 Phase 1.5 — Memory** | 🟡 **Step 1–9 全部完成**；**缺陷 E 已闭合（E-1~E-5）**，方案 A 实测有效（Δ 跟随率 +0.602、入桶 3/6→6/6；新 hash 下复测 Δ **+0.727**，§20.8.1）；**跨会话召回的证据等级已在 §20.8.6 升级**：`mem-002` 在严格配对下 ON 有卡并召回、OFF 零卡（★ 这是 **#24 修好 OFF 臂之后**才成立的第一条配对，可测正样本 **n=1**） |
| §5 Phase 2 检索短板 | ❌ 未开始 |
| §6 Final Gate 终评集 | ❌ 未开始 |
| §7 收尾 + Final Freeze | 🟡 **部分启动**：两个效果锚点（`V-2026-10-07` 落点 `0f24891`；**`V-2026-10-07B`** = 本轮 D9，落点由标签后的回填提交记录，见 §20.0 的自指限制）；对抗性 review 的 A/B 两组 + D1~D11 **全部处置完毕**，偏离表 **26 条**（§20.5）；`evals/results/task_eval/*.md` 已入库（D11），`*.jsonl/log/report.json` 维持不入库；Final Freeze **未开始** |


> **最后更新**：2026-10-07（深夜，Step 9 收尾）—— **E-1~E-5 完成** + **对抗性 review 的 A/B 两组修完** + **D1~D11 全部裁决并落地**（偏离表 **26 条**：**#25/#26 是本轮复核时新增**；**#24 是 Step 9 之后新增** —— 它判定「paired control 的 OFF 臂从未真正关掉进程级 store」⇒ **既有 OFF 组对照证据全部作废**，已重跑）。本轮验证：护栏 **162 项全绿**（157→162，新增 ㉒a~㉒e；⑦b/⑦c 由源码文本断言改成**行为断言**，并做过「换回旧实现必须变红」的篡改验证）、`pyrefly` 0 errors、ruff check/format 通过、`task_eval sanity` 66 条 **ERROR 0**、step2/step4 gate 均 exit 0。**§20.8.6 = 论文里 Memory 那条主线的最终证据**：`mem-002` 同 case、同前置条件（两次低分批改、同一考点）下 ON 侧 1 卡 + `recalled/used/correct_use` 全 True，OFF 侧 0 卡 + `recalled=False` ⇒ 召回来源确证为 Store；可测正样本 **n=1**，不写成「多次验证通过」。★ D8 改 case 过程中**撤回了自己的一处归因**：§20.8.3 原写「错题被判 100 分（缺陷 A 症状）」是反的 —— 那题学生**答对了**、模型判 100 是判对的，错在 gold 要求两次都低分；真正的误判是小根堆那题**答对却被判 0 分**（→ #25）。memory 数据集指纹 `b5619085d7979a36` → **`3c938365da7ce614`**（四次漂移逐条见 §20.0）。提交链：`6e71fed`（D6/⑳/㉑）→ **`7304786`**（#24 + D8）→ 本轮文档提交。

---

# 三、Phase 0B（已冻结，**只读，不得修改**）

| 文件 | 内容 |
|---|---|
| `evals/results/task_eval/phase0_baseline_final.jsonl` | **66 条冻结基线** |
| `evals/results/task_eval/PHASE0_FREEZE.md` | **冻结快照** |

**配置**：agent=`deepseek:deepseek-flash` · judge=`dashscope:qwen3.8-flash` · RAG 链=`dashscope:qwen3.7-flash`

| Task | μ final_quality |
|---|---|
| QA | 4.333 |
| Generate | 4.800 |
| Grade | 5.000 |
| Verify | **1.133**（失败率 1.000） |
| Memory | 2.833 |

**Judge calibration**：PASS（exact 0.933 / within_1 1.000 / mae 0.067 / spearman 0.732）

---

# 四、Phase 1 — Verify 修复（**已收尾**）

## 失败的原始链条

```
用户问「考过哪些真题」 → supervisor 无「查真题」路由 → 归到 question_agent
                      → 生成一套**新题** → Verify = 0
```

## 改动（2 处 prompt，`rag/` 检索链**一行未改**）

| 文件 | 改动 |
|---|---|
| `src/prompts/supervisor.py` | ① 新增「历史真题检索 → knowledge_agent」路由；② **歧义处理**（「我想做 X 的真题」可能是「找真题」或「出真题风格的题」）；③ 路由条件是**语义**而非出现「真题」二字；④ **分派时不得输出文字说明**（防英文泄漏） |
| `src/prompts/agents.py` | ① knowledge_agent 加「历史真题查询」5 条硬性行为（用已有证据 / 列年份题号 / **不生成新练习题** / 只引用检索证据 / 证据不足则明确说明）；② `_TOOL_CONVENTION` 加「**不得输出叙述性前言**」 |

## 结果（全量 66 条，`phase1_baseline_v2.jsonl`）

| 指标 | Phase 0B | **Phase 1** |
|---|---|---|
| **Verify 仍出题（错误行为）** | **6/15** | **0/15** ✅ |
| **Verify 有真题信息** | 3/15 | **9/15** ✅ |
| Verify μ | 1.133 | 1.267 |
| QA μ | 4.333 | 4.667（+0.333） |
| Generate μ | 4.800 | 4.733（持平） |
| Grade μ | 5.000 | 4.133（**非回归**，见下） |
| Memory μ | 2.833 | 2.833 |
| **检索侧** | — | **逐位一致** ✅（检索链未动） |

**Grade −0.867 已查明**：`_TOOL_CONVENTION` **只在 knowledge/question agent**，**grading_agent 没有**；
`score_tolerance` 仍 **1.000** ⇒ 判分能力未退化；下降来自 2 条偶发「批改失败（工具未返回评分结果）」+ 1 条推理矛盾。

**⇒ 报告**：`PHASE1_VERIFY.md`

---

# 五、Phase 1.5 — Memory（🟡 Step 1–8 完成；**缺陷 E：E-1~E-5 已闭合，方案 A 实测有效**）

> **📁 文档整理说明（2026-10-06）**：本节原引用的 **7 份过程文档**已移入**系统回收站** ——
> `PHASE1_MEMORY_DIAGNOSIS.md` · `PHASE1_MEMORY_DESIGN.md` · `PHASE1_MEMORY_STEP2_DESIGN.md` ·
> `PHASE1_MEMORY_CASES_REWRITE.md` · `PHASE1_MEMORY_STEP4_REVIEW.md` · `PHASE1_MEMORY_STEP4FIX.md` ·
> `PHASE1_MEMORY_STEP5_20261006_2014_pre_fix.md`。
> **理由**：这些是「**已落地的方案**」与「**方案期间的中间产物**」，而**关键信息已全部提炼进本节**
> （下方各小节即为其结论）⇒ 保留它们只会与本节内容重复。
> **保留的最终成果**：`PHASE1_MEMORY_STEP5_FINDINGS.md`（★ 主文档）+
> `PHASE1_MEMORY_STEP5_20261006_2144.md`（配对报告）。
> **如需追溯原文**：在系统回收站按上述文件名恢复即可。

## 5.1 诊断结论（Phase 1.5 起点）

> ⚠️ **本节是对「旧 6 条 case」（初版，已作废）的历史诊断。**
> 其核心结论「**Store 恒空 ⇒ 完全没测到跨会话**」正是后续**三层改造 + case 重写**的动因。
> **当前生效的 case 设计见 5.2 表**；本节保留以说明「为什么要改」。

**6 条 case 的四率**：`correct-use = 3/5 = 0.600`（★ 分母是 5，mem-004 的 `correct=None` 算 N/A）

### ★ 核心结论

> **6 条里 0 条是「产品真实的 memory 失败」—— 全部是 case 问题。**

| 类别 | case | 数量 |
|---|---|---|
| 成功 | mem-002/003/006 | 3 |
| case 问题（请求超范围） | mem-001/005（问「复习计划」，系统明确拒绝） | 2 |
| case 问题（缺跨会话场景） | mem-004（说「上次聊到 AVL」，但 case 没有「上次」） | 1 |
| **产品真实失败** | — | **0** |

### ★ 更根本的问题（代码取证）

| 发现 | 证据 |
|---|---|
| **记忆卡只含 `weak_topics`** | `abuild_memory_card`：`if not weak and not preferred_style: return ""` |
| **`preferred_style` 是死字段** | grep 零写入路径 |
| **无「从对话抽取画像」逻辑** | `src/memory/` grep 零命中 |
| **Store 里没有 `behavior-smoke` 数据** | 实测 `profile: 0`、`episodes: 0` |
| **`user_id` 固定 `"behavior-smoke"`** | `agent_behavior_smoke.py:76` |
| **`weak_topics` 由 grade episodes 派生** | `weak_topics.py:3` |

**⇒ 6 条 case 测的全是「checkpointer 的会话内跨轮记忆」** —— Store 恒空 ⇒ **完全没测到跨会话**。

## 5.2 设计方案 v3（**已落地**）

### 三层必须同改（**冻结为硬要求**）

```
GradingResult.knowledge_points      ← ① schema 层
        ↓
record_grade(knowledge_points=…)    ← ② 写入层
        ↓
Episode.knowledge_points            ← （字段已有）
        ↓
compute_weak_topics(...)            ← ③ 聚合层 ★ 关键
        ↓
weak_topics
```

**原来 `compute_weak_topics` 只用单值 `e.topic`（写入时是 `stem[:80]` 题干截断）**
⇒ **Memory 记的是「某道题的开头」，不是「用户在哪个知识点上薄弱」**。

### 6 条 case 设计（统一生命周期）

> ★ **本节已按 case 重写方案更新**（2026-10-06）。
> 下方「旧设计草案表」已作废 —— 实际落地的是**两段独立会话 + 单变量对照**。

```
Session A（thread-A，user=eval-<case>-<随机后缀>）
  Turn 0：题 1 + 批改   → record_grade → episode
  Turn 1：题 2 + 批改   → 累计 2 hits → weak_topics → Store
Session B（**新 thread**、**同 user_id**）
  Turn 0：需要用到薄弱点的问题       → load_memory → memory card → agent
```

| case | KP | Session A | should_be_recalled | 用途 |
|---|---|---|---|---|
| **mem-001** | 平衡二叉树 | 2 次**低分**批改 | **True** | 正样本：`weak=2 ≥ MIN_HITS` |
| **mem-002** | 图 | 2 次**低分**批改 | **True** | 正样本：换 KP，验证非个例 |
| **mem-003** | 排序 | 2 次**低分**批改 | **True** | 正样本：换 KP |
| **mem-004** | 平衡二叉树 | **1** 次低分批改 | **False** | 负样本：`weak=1 < MIN_HITS(2)` |
| **mem-005** | 图 | 零批改（纯聊天） | **False** | 负样本：无 episode ⇒ 卡必空 |
| **mem-006** | 图 | 2 次**高分**批改 | **False** | 负样本：`score ≥ GOOD_SCORE` ⇒ 记 good 不记 weak |

**★★ 单变量对照（这两组是 case 设计的精髓）**：

- **mem-004 vs mem-001** —— 同 KP、同题型，**唯一差别是批改次数 1 vs 2**
  ⇒ 专测 `MEMORY_WEAK_MIN_HITS`；若阈值失效，两者会同向（都召回或都不召回）。
- **mem-006 vs mem-002** —— 同 KP、同为 2 次，**唯一差别是分数档**（低分 vs 高分）
  ⇒ 专测 `MEMORY_WEAK_SCORE`。

**★「2-hit」必须落在同一标准 KP**（不得因「同属数据结构」就合并）。

**当前阈值**（`core.settings`）：`WEAK_SCORE=60` · `GOOD_SCORE=85` · `MIN_HITS=2` ·
`CLEAR_MIN_GOOD_HITS=2` · `WINDOW_DAYS=30`

### gold 结构（**实际落地形态**，见 `memory_cases.jsonl`）

> ★ 下方已按**实际 schema** 更新。旧设计里的 `must_recall` / `usage_property` /
> `correct_property` **未落地** —— 实际用「`should_be_recalled` + `forbidden_values` + `setup_conditions`」。

```json
"gold": {
  "expected_memory": {
    "type": "weak_topics",
    "values": ["平衡二叉树"],          // ★ 必须是 kp_index canonical name
    "should_be_recalled": true          // 负样本为 false（对齐判定）
  },
  "expected_answer_property": {
    "forbidden_values": ["栈", "队列"]   // 回复不得出现（防「用错记忆」）
  },
  "setup_conditions": {                  // ★ case validity：前置条件不成立 ⇒ case_invalid
    "min_grade_calls": 2,
    "grade_score_bands": [[0, 59], [0, 59]]
  }
}
```

| 字段 | 回答什么 |
|---|---|
| `expected_memory.values` | **Store 里理论上应该存在什么**（canonical name） |
| `expected_memory.should_be_recalled` | **新 thread 是否**必须**召回**（负样本对齐） |
| `expected_answer_property.forbidden_values` | 回复**不得**出现的内容（防「用了但用错」） |
| `setup_conditions` | A 段前置条件（批改次数 / 分数档）⇒ **决定该 case 是否进分母** |

### 指标（**全部机械判定，judge 不参与**）

| 指标 | 定义 |
|---|---|
| `recalled_pass` | `recalled_actual == should_be_recalled`（**与期望对齐**，进主指标） |
| `recalled_actual` | 记忆卡里**是否真有**期望值（机械事实） |
| `used` | 回复含 `expected_memory.values` 中**任一** |
| `correct` | `used` **且** 回复不含 `forbidden_values` 中任一 |
| `memory_correct_use` | `recalled_pass ∧ used ∧ correct`（三者有 `None` ⇒ `None`） |

**★ `used ≠ correct`**（用了但用错 ⇒ `used=True`, `correct=False`）

**★ `case_invalid` 不进分母**：`validity_valid=False` ⇒ Memory 三项记 **N/A**，
另标 `case_invalid`（**不是** `memory_miss` —— 后者会被读成「产品没召回」）。

### ★★ alias 纪律（防评测污染）

> **alias 只能收录「已确认的同义表达」，不能为了让 case 通过而临时加。**

| | ✅ 合法 | ❌ 非法 |
|---|---|---|
| 时机 | **跑 case 之前**已加入 | 因 case 失败**事后**加 |
| 依据 | **教材/考纲的规范用语** | 「LLM 这么输出了」 |
| 验证 | 加完**重跑全部** case | 只让失败那条通过 |

## 5.3 Step 1 — 产品三层改动（**已实施**）

| # | 文件 | 改动 |
|---|---|---|
| 1 | `src/schema/grading.py` | `GradingResult` 新增 `knowledge_points: list[str]` |
| 2 | `src/prompts/service.py` | `GRADE_PROMPT` 加输出要求 + 标准考点名示例 |
| 3 | `src/agents/tools.py` | `record_grade(knowledge_points=...)`；**`topic` 保持 `stem[:80]` 不派生**（仅 legacy） |
| 4 | `src/memory/weak_topics.py` | `compute_weak_topics` **遍历 `knowledge_points`** + `allow_legacy_fallback: bool = True` |

**单元测试 5/5 通过**（零成本）：
① 一题两 KP → 各 1 次 ② 两题同 KP → weak ③ **两题不同 KP → 不合并** ④ 一题两 KP×2 → 两个都 weak ⑤ **fallback 开关生效**

### ★ Step 5 真跑追加修复的 4 个真实缺陷（A–D）

> 这 4 个缺陷**只有真跑 agent 才暴露**，静态 gate 全部漏检。详见 `PHASE1_MEMORY_STEP5_FINDINGS.md` §三。

| 缺陷 | 性质 | 症状 | 修复位置 |
|---|---|---|---|
| **A** | 真实产品缺陷 | `feedback` 超长 ⇒ `ValidationError` ⇒ **批改硬失败**（★ 原记「62.5%=5/8」**分母构造不出**；按 A 段**预期**批改次数重算 = **5/9 = 55.6%**，修复后 **0/9**，详见 `docs/EXPERIMENTS.md` §20.3） | ① `schema/grading.py` 改**截断**（`_FEEDBACK_SOFT_LIMIT=800`）；② `prompts/service.py` 加长度约束；③ `rag/llm_calls.py` 加同 prompt 重试 + 工具标记清洗兜底 |
| **B** | 真实产品缺陷 | `GRADE_PROMPT` 的 KP **示例名非 canonical** ⇒ 诱导模型输出漂移值 | `prompts/service.py` 示例改为 8 个已核验 canonical 名 |
| **C** | ★ **最隐蔽** | 工具拿不到 `config` ⇒ `user_id` 恒 `None` ⇒ `if uid:` 跳过 ⇒ **批改成功但 0 episode** | `memory/remember.py` 新增 `_resolve_config`：**显式参数优先，缺失时回落 `langgraph.config.get_config()`** |
| **D** | ★ **最隐蔽** | `normalize_topic` **主动改坏** canonical（删空格毁掉 21 个含空格名；别名表目标不可达） | `memory/topics.py` **canonical-aware 重写**（顺序：① canonical 原样 → ② 别名表 → ③ rag 同义词 → ④ 压缩空白） |

**缺陷 C 为何最难查**：工具输出完全正常（`评分：40/100`），批改成功、分数正确，
但 `user_id` 恒 `None` ⇒ 一条 episode 都不写。**只看工具输出与日志无法发现**，
只有断言 `EPISODES > 0` 才能抓到。

**缺陷 D 为何最隐蔽**：不报错、不丢数据，只是把 `knowledge_points` 悄悄改写成**非 canonical**，
于是聚合相等匹配**恒不命中**。单独看每条 episode 都「写成功了」。

### ★ 兜底逻辑自身引入的 3 个缺陷（D2-1/2/3，已修）

`rag/llm_calls.py` 的 `_try_kv_dict`（把模型飘移出的裸 KV 文本兜底成结构化）**自身**引入：

| 缺陷 | 症状 | 修法 |
|---|---|---|
| **D2-1** | `is_wrong` **语义反转** —— 白名单外行被拼进上一字段（`"true\ntopic: 平衡二叉树"` ⇒ `False`） | 续行**仅限** `_KV_MULTILINE_FIELDS = {feedback, error_analysis}`，其余非 key 行**直接丢弃** |
| **D2-2** | 首行有前言 ⇒ **整条兜底全盘放弃** | 加 `started` 标志：**扫描到第一个合法字段 key 才开始** KV 解析 |
| **D2-3** | `knowledge_points` 不在白名单 ⇒ **静默丢失** | 字段分类：scalar(`score/feedback/is_wrong/error_analysis`) vs **list(`knowledge_points`)**，KP 按 `list[str]` 切分解析 |

## 5.4 Step 2 — 最小 2-hit Gate（**已通过**）

**脚本**：`scripts/memory_step2_gate.py`（脚本级，**不跑 agent**，只花 2 次批改 LLM 调用）

**结果：✅ GATE 通过**

| 层 | 结果 |
|---|---|
| ① 批改 A/B | `score=0`（<60）✅ · KP=`['平衡二叉树','AVL树']` |
| ②③ Episode KP | **2/2 非空** ✅ |
| ④ `compute_weak_topics` | `['平衡二叉树','AVL树']` ✅ **两 KP 都达 2 hits** |
| ⑤ `profile.weak_topics` | `['平衡二叉树','AVL树']` ✅ |
| ⑥a 记忆卡 | `【学生记忆】薄弱：平衡二叉树；AVL树` ✅ |

**⇒ 完整链路：`两次低分 → KP 入库 → 每 KP 各计一次 → weak_hits=2 → Store → 记忆卡`**

> ⚠️ **注意本表中的 `AVL树` 是非 canonical 值**（模型当时的实际输出）。
> 当时 gate **只断言「KP 非空」，未断言「KP ∈ canonical」** ⇒ 这个盲区正是
> **缺陷 E 的早期征兆**（产出词表与 `kp_index` 不同源）。
> 后续已补 **⑧ 组（KP 规范名）** 护栏；该 case 的 gold 值也已改为 canonical 的「平衡二叉树」。

### ★ 首跑「假失败」的教训（必须传承）

初版 gold 写 `EXPECTED_KP = "AVL树"`（**只看了 `kp_ids=ds.tree.avl` 就猜**）⇒ gate 报失败。
查证：**KB 里 `ds.tree.avl` 的规范名是「平衡二叉树」**
（`kp_index['ds.tree.avl']['name']`；教材正文「平衡二叉树」4 次 vs「AVL 树」1 次）。

**⇒ 6 条 case 的 `expected_memory.values` 必须逐一查 `kp_index` 的规范名，不能凭 `kp_ids` 猜。**

### Session B 的 4 条硬条件

| # | 条件 |
|---|---|
| 1 | 新 `thread_id` |
| 2 | 相同 `user_id` |
| 3 | **不携带 Session A 的 message history** |
| 4 | **不允许 harness 手工注入 memory**（记忆**只能**由 `load_memory` 自动注入） |

## 5.5 Step 4 — 改 harness（**两缺口已补，Gate 通过**，2026-10-06）

| 缺口 | 实现 | 位置 |
|---|---|---|
| **① 每 case 独立 `user_id`** | 新增 `make_user_id(case_id)` —— 生成 `eval-{case_id}-{8位随机}`，**带随机后缀** ⇒ 同 case 重跑也是全新身份（与清理双保险） | `scripts/agent_behavior_smoke.py` |
| **② 跑前清理该 user 的 Store** | 新增 `_cleanup_user_store(store, user_id)` —— 清 `student/{uid}/profile` **与** `student/{uid}/episodes` **两个**命名空间；只清自己的 user | 同上 |
| **接线** | `run_sessions(..., cleanup_first=True)` 默认跑前清理；`CaseResult.user_id` 记录本次身份 | 同上 |

**验证**：`scripts/memory_step4_gate.py`（**零 LLM 成本**）—— **14 项**机械判据全绿：

- ① 独立 user_id：同 case 两次不等 / 跨 case 不等 / 字符集合法；
- ② 清理：seed 2 hits → 画像+记忆卡非空 → 清理后 episode/画像/weak_topics/记忆卡**全空**；
- ⑤ 隔离性：清理 A **不影响** B。

**★ 反向验证已做**（证明 Gate 不是恒绿）：猴补丁把 `_cleanup_user_store` 置为 no-op ⇒
Gate **退出码 1**、5 项清理判据变红。

**★ 一个踩到的坑（必须传承）**：`record_grade` 经 **`get_store()` 取进程级引用**，
不 `set_store()` 就**静默不写**（`safe_remember` 吞掉）—— seed 时"写不进 episode"就是这个原因。

**★ 收尾**：`EXPECTED_KP` 漂移已修（原 Step 2 设计文档中 gold 值
「AVL树」→ 规范名**「平衡二叉树」**；§五 的 LLM 输出示例保留原样）。

**⇒ ⑥b 已由 Step 5 真跑验证成立**（见 5.6）。

## 5.6 Step 5–8 — 真跑验证与结果（**已完成**，2026-10-06）

### Step 5 · paired control（Store ON vs OFF）

**脚本**：`scripts/memory_step5_paired.py`（同一批 6 条 case 跑两组，**只差 Store 开关**）

| 指标 | Store ON | Store OFF | 期望 | 判定 |
|---|---|---|---|---|
| 有效 case（`valid≠False`） | **6/6** | 2 | — | ON 组全有效 |
| **有 memory card** | **1** | **0** | ON>OFF | ✅ |
| **`recalled_actual=True`** | **1** | **0** | ON≥OFF | ✅ 无旁路 |
| `used` / `correct` | 2 / 2 | 0 / 0 | — | ✅ |

**⇒ 跨会话召回首次成立**：`mem-001` 记忆卡逐字为 `【学生记忆】\n薄弱：平衡二叉树`，
B 段回复开头即「**薄弱点：平衡二叉树（AVL）**」⇒ `used=True`、`correct=True`。
**Store OFF 组 0 卡 0 召回** ⇒ 「召回确实来自 Store」由**机械对照**确立。

**⇒ 缺陷 A + C 确证修复**：ON 组 6/6 全部 `valid`（修复前仅 1/6）。

**产物**：`PHASE1_MEMORY_STEP5_20261006_2144.md` · `phase1_memory_step5_store_{on,off}.jsonl`

### ★ 旧产物判定（**已归档，不可作基线**）

`*_pre_fix_20261006_2023*` 是**缺陷 A/C 修复前**跑的，其「memory card=0」**不可读作「Store 不起作用」**。
证据：`mem-001` 两个批改回合却只有 1 条 `grade_score` 且 `tool_calls=[]`；
B 段回复是「我无法知道你的薄弱知识点」的**拒答**。**用它当基线会得出方向性错误结论。**

### ★★ 缺陷 E（**已闭合：E-1~E-5 完成，方案 A 实测有效**）

**症状**：批改产出的 `knowledge_points` 是 LLM **自造自由文本**，非 `kp_index` canonical name。
直接查 `store.db` 取证：

| case | gold 期望 | 实际产出 | 命中 |
|---|---|---|---|
| mem-002 | `图` | `图的基本性质` / `握手定理` | **0/2** |
| mem-003 | `排序` | `堆的定义` / `完全二叉树` | 0/2 |
| mem-006 | `图` | `图的存储结构` / `简单路径与回路` / `拓扑排序` | 0/3 |

**机制**：自由文本 → `normalize_topic` 四步全不命中 → 原样返回 → **每词各成一个桶、各 1 hit**
→ `MIN_HITS=2` 永不满足 → `weak_topics=[]` → 无记忆卡。**正样本召回率被压到 1/3。**

**性质判定（勿混淆）**：**不是阈值问题**（`MIN_HITS` 工作正常），**也不是归一化问题**
（缺陷 D 已修），而是 **「上游产出词表与 `kp_index` 不同源」**。
缺陷 B（示例诱导）是 E 的**已修子集**，E 是剩余部分 —— **B 的修复未被推翻**。

**修法（用户裁决：方案 A —— 注入候选 canonical 词表）**，进展见 §八。

#### E-3 / E-4 落地事实（2026-10-07）

> ★ 上表是**修复前**从 `store.db` 取证的现场，保留说明成因；下表才是当前实现。
> ★★ **时效**：下面这张表记的是 **E-3/E-4 当时**的值（词表 162、system 1317 字符、
> `PROMPT_SET_VERSION=f09c75642029`）。**#8 之后**当前值为 **词表 158 / system 1293 / hash `2f485d2d7ef7`**
> —— 历史值**刻意不改写**（两侧都要留，见纪律 #20），现值看 §20.0 与头部 #8 行。

| 项 | 内容 |
|---|---|
| 注入点 | `src/prompts/service.py` → `_knowledge_points_block(names_by_subject())`，**import 期**拼进 `GRADE_PROMPT` 的 system |
| 词表来源 | **只经 `core.kp_vocab`**（与 `memory.topics.normalize_topic` 同源），**零硬编码** |
| 分组 | 【数据结构】52 / 【计算机组成原理】39 / 【操作系统】36 / 【计算机网络】35 = **162** |
| 排序 | 组内按名称排序 —— kp_index 行序变动不再改变 prompt，避免 `PROMPT_SET_VERSION` 把「数据重排」误报成「提示词变更」 |
| prompt 成本 | 批改 system **389 → 1317 字符**（+928），上界由 ⑫g 锁在 2000 |
| 别名 | **未注入**（`AVL` 不在 prompt 内）；⑫d 机械核对 |
| 降级 | kp_index 读不到 ⇒ 空词表 ⇒ 退回缺陷 B 的 8 个示例；服务不会起不来（⑫e） |
| `PROMPT_SET_VERSION` | **`f09c75642029`**（跨进程稳定） |
| 护栏 | `memory_step4fix_gate.py` 新增 **⑫ 组 9 项**，Gate 由 71 → **80**（E-4 当时）→ 85（修 #4/#6）→ **87**（修 #10 时补 ③j 2 项），零 LLM 成本 |

**⑫ 组判据**：a 接线生效 / b 无遗漏（canonical ⊆ prompt）/ c 无多余（prompt ⊆ canonical）/
d 未注入别名 / e 降级分支 / f 无花括号 / g 长度上界 / h 篡改文本被探测 / **i 双读校验**

**★★ ⑫i 的由来（务必传承这个发现）**：⑫a~⑫c 的两侧集合**都**来自 `kp_vocab`，
属**同义反复** —— 若 `kp_vocab` 自身解析漂移（漏学科、把 `links.jsonl` 的条目当 `name`、
去重并掉不同考点），这三项**依然全绿**。故补 ⑫i：**独立重解析 jsonl** 再与 `kp_vocab` 比一次
（实测 162 == 162，`direct ^ canonical` 为空）。
⇒ 通用规则：**护栏两侧若来自同一函数，它只证明「函数自洽」，不证明「函数正确」**。

**反向验证（三模式，均报红；用猴补丁，未改任何源文件）**：

| 篡改 | 报红的判据 |
|---|---|
| 摘掉接线（词表为空） | ⑫a `prompt 内 0 个` + ⑫b `缺失 162` |
| 只注入一个学科 | ⑫a `52 个` + ⑫b `缺失 110` |
| 混入自造词「图的基本性质」 | ⑫c `多余 1` |

### ★★ E-5 结果（**方案 A 有效**，2026-10-07 实测）

**设计**：配对对照，`scripts/memory_e5_probe.py`，同 6 题 / 同模型（`dashscope:qwen3.7-flash`）/
同温度（`TEMPERATURE_GRADING = 0.0`）/ 同 `call_structured` 路径，**唯一变量是词表块**。
臂 B 由 `_knowledge_points_block({})` **逐字复现 E-3 之前的 8 示例口径**
（已验证：两臂 system 除词表块外**逐字节相同**）。12 次批改调用。

| 臂 | `all_canonical`（题级） | 词级跟随率 | 期望入桶 | 空产出 |
|---|---|---|---|---|
| **A** 词表 162 | **5/6** | **7/8 = 0.875** | **6/6** | 0 |
| **B** 8 示例（=E-3 前） | 1/6 | 3/11 = **0.273** | 3/6 | 0 |

**Δ 词级跟随率 = +0.602**；**期望入桶 3/6 → 6/6**。

| 结论 | 依据 |
|---|---|
| **方案 A 足够**（正样本入桶率已打满） | 臂 A 6/6 题的**目标考点都进了正确的桶** |
| 词表还**收窄**了产出条数 | 8 词/6 题（≈1.33）vs 11 词/6 题（≈1.83）⇒ 少一半噪声桶，直接减轻 `MIN_HITS` 分裂 |
| 残留未清零 | 臂 A 仍造了 **1 个**：`无向图`（canonical 只有 `图`/`图的存储`/`图的遍历`）。但它同题也给了 `图的存储` ⇒ **只造成噪声桶，不阻断目标 KP 聚合** |
| §八 第 5 项「语义匹配兜底」 | **倾向不做**（方案 A 已打满入桶）。是否彻底关闭留待 **Step 9** 的 6 条 Memory 真跑再定 |

**产物**：`evals/results/task_eval/phase1_e5_prompt_following.jsonl`（12 条 = 6 题 × 2 臂，
含 `kp_raw` / `kp_normalized` / provenance）。探针**只测量、退出码恒 0**（不进 Gate ——
模型有随机性，做成硬门禁会偶发红灯）。

> ⚠️ **自纠（同类错误，勿再犯）**：`--reanalyse --write` 的**首版**按 `provenance=` 过滤注释行，
> 重写时把 provenance 头**丢了一次**。已修脚本（保留全部 `#` 行）并重建该行 ——
> 重建用的是**可重新计算**的字段（`code_version` / `PROMPT_SET_VERSION` / 两臂 system sha256），
> 运行时间取文件 mtime；`note` 字段在 provenance 里写明了这次重建。
> ★ 校验成立：重建后算出的两臂 system sha（`519859ab29be` / `0fe2deeddf69`）与首跑**逐位相同**
> ⇒ 证明 prompt 自那以后未变、重建可信。
> ⇒ **规则**：**重写产物 = 破坏性操作**，凡是「原地改写既有归档」的分支，必须先把
> **文件头/元信息**纳入保留清单，并跑一次**字段级比对**再确认写回。

#### ★ E-5 首跑我自己犯的错（必须传承）

**单值 gold 在「并存节点」上必然假阴性。** 我首跑把 gold 写成 `expected: "堆"` / `"排序"`，
于是两臂「入桶」都只有 3/6，看起来像产品问题。查 `kp_index` 后：

| 我写的 | 事实 |
|---|---|
| `堆` | **kp_index 里根本没有**，只有 `堆排序` ⇒ 臂 B 的 `堆` 其实是**自造词**（被我误算成命中） |
| `排序` | 存在，但 **`快速排序` 也在** —— 两者是**并存的两个节点**（章级 vs 算法级）⇒ 单值 gold 会把「合法地选了另一档粒度」判成未命中 |

⇒ **规则**：Memory/Verify 的 gold 一律用 **`expected_any` 可接受集**，且**逐题查 `kp_index`**
（与首跑「AVL树 → 平衡二叉树」同一条纪律的第 2 次应验）。
⇒ **修正 gold 不该重新付费**：探针支持 `--reanalyse [路径] --write`，
**零 LLM** 用当前 gold 原地重算入桶（`kp_raw` / `kp_normalized` 不动）。本次即靠它把 12 条
已有数据的入桶从 3/6 修正为 6/6，**没有再花一次 token**。

> ⚠️ **★ 归档可比性现在有洞（2026-10-07 实测取证，勿凭印象）**
>
> - `evals/results/task_eval/phase1_memory_step5_store_on.jsonl` 的记录字段里**没有** `prompt_set_version`
>   —— 实测字段只有 `code_version: 648d819-dirty` + `golden_sha256` + `date` + `judge`。
> - `PROMPT_SET_VERSION` 只进了 **LangSmith trace metadata**（`rag/llm_calls.py:67`）
>   和 `/api/info`（`service.py:237`），**没进 record schema**。
> - `provenance.code_version()` = `<short-sha>` + 当 `src/ scripts/ pyproject.toml .env.example`
>   有未提交改动时加 `-dirty` ⇒ **E-3 前后同为 `648d819-dirty`**。
>
> **⇒ 后果**：单看归档**无法判断某条结果是哪个 prompt 版本产出的**。Step 9「产品行为变更需重跑」
> 现在必然触发（批改 system 从 389 → 1317 字符），但**旧结果无法事后甄别**，只能整体作废重跑。
>
> **两个补洞选项（待用户裁决，未动代码）**：
> ① 提交这批改动，让 `code_version` 的 sha 真正变化（顺带解决 dirty 噪声）；
> ② 把 `PROMPT_SET_VERSION` 写进 task_eval 的 record schema（一处新增字段，成本最低、
> 且正好是它被设计出来的用途 —— 把「输出质量变化」归因到「提示词变化」）。

### 附带发现（两项，均已澄清）

1. **「`mem-002` 写入丢失」是误判，已撤回**。三项实验否定：探针 `record_grade` ×2
   → 611ms/310ms（< 1.5s 超时）**2 调用 2 条**；单条 case 跑后清理删 1 项、残留 **0**；
   重跑前后 `mem-*` 计数 **6 → 6 未增加**（零泄漏）。真因：库中残余属**更早运行的残骸**。
   ⇒ ★ **纪律**：`make_user_id` 带随机后缀 ⇒ 跨运行 `user_id` 不复用
   ⇒ **「同名前缀行数」≠「本次运行写入数」**，必须记**跑前/跑后计数差**。
2. **「A 段能否凑够 2 次批改」不稳定**：同一 `mem-001` 三轮分别为 2 / 2 / **1** 次
   ⇒ `case_invalid` 会在重跑间浮动。**报告须按每次运行的实际有效样本算分母，不可跨轮混用。**

---

# 六、代码改动清单（**44 项未提交**，2026-10-07 下午 `git status --short` 实测）

| 文件 | 改动 |
|---|---|
| `src/schema/grading.py` | Phase 1.5：加 `knowledge_points`；**缺陷 A**：`feedback`/`error_analysis` 改**截断**（软上限 800 / 500） |
| `src/schema/models.py` | （早期 Phase 0B 改动） |
| `src/prompts/service.py` | Phase 1.5：`GRADE_PROMPT`；**缺陷 A/B**：加长度约束 + KP 示例改 canonical；**E-3（2026-10-07）**：示例改为**从 `core.kp_vocab` 动态注入 canonical 词表**（按学科分组），空词表降级回 8 示例；**#8（2026-10-07）**：来源改 `prompt_names_by_subject()`（剔 4 个课程根节点，162→158、system 1293、hash → `2f485d2d7ef7`），并把注释里「实测失败率 62.5%」更正为 **5/9 = 55.6%** |
| `src/prompts/supervisor.py` | Phase 1：Verify 路由 + 反泄漏 |
| `src/prompts/agents.py` | Phase 1：knowledge_agent 历史真题 + `_TOOL_CONVENTION` |
| `src/agents/tools.py` | Phase 1.5：传 `knowledge_points` |
| `src/memory/weak_topics.py` | Phase 1.5：遍历 KP + `allow_legacy_fallback` |
| `src/memory/remember.py` | **缺陷 C**：`_resolve_config`（显式参数 → `get_config()` 回落） |
| `src/memory/topics.py` | **缺陷 D**：canonical-aware 重写；**缺陷 E**：词表解析**外移**至 `core.kp_vocab` |
| `src/rag/llm_calls.py` | **缺陷 A**：同 prompt 重试 + 工具标记清洗 + `_try_kv_dict` 兜底（含 D2-1/2/3 修复）；**2026-10-07**：`_try_kv_dict` 续行分支显式收窄 `current is not None`（清 pyrefly 2 error，**行为不变**） |
| `src/core/settings.py` | 新增 `STRUCTURED_OUTPUT_RETRIES: int = 1` |
| `scripts/agent_behavior_smoke.py` | （Phase 0B 改动）＋ **Step 4**：`make_user_id` / `_cleanup_user_store` / `run_sessions(cleanup_first=, store_enabled=)` / `CaseResult.user_id` / 跑后清理 checkpointer |
| **`src/core/kp_vocab.py`** | **★ 新增**（缺陷 E）：canonical 词表**单一事实源**。`canonical_names()` 保 **162 全量**（归一化侧用）；**#8 新增 `prompt_names_by_subject()` / `node_kinds()`** —— 按数据字段 `node_kind` 剔除 4 个课程根节点，只给 prompt 用。★ 其 docstring「只依赖 `json`/`pathlib`」在**效果上不成立**（`import core.kp_vocab` 会执行 `core/__init__` → `core.llm` → `langchain_openai`），属文档不准、登记备查 |
| `src/evaluation/task_eval/*` | **整个评测模块**（新增，未提交）。★ **2026-10-07 修三条口径**：`memory_scorer.py`（`used` 要求 `recalled_actual`；`correct_use` 按样本极性定义）、`report.py`（`failure_rate` 分母改「有效 n」+ 新增 `invalid_n` 字段 + 报告新增「有效 n」列）、`metrics.py`（`category_hit` 学科码 `cn` 恒判未命中 ⇒ 加别名对齐，未登记学科记 **N/A 而非 False**） |
| `evals/datasets/demo/`、`probes/`、`probes_phase1/` | case 数据（新增） |
| `evals/results/task_eval/*` | 评测产物 + 文档（新增） |
| `scripts/memory_step2_gate.py` | Step 2/3 Gate（11 项判据）（新增） |
| `scripts/memory_step4_gate.py` | Step 4 Gate（独立 user_id + 清理，零 LLM，14 项）（新增） |
| `src/evaluation/task_eval/{metrics,report,gold_sanity}.py` | **修 #7**：`metrics.degenerate_gold()`（样本 ≥5 且不同取值 ≤2）；`report` 把两极 gold 的 `score_tolerance` 置 N/A + 保留 `raw_rate` + 渲染 ⚠ 行；`gold_sanity` 新增**集合级 PENDING**（`_check_grade_score_spread`）并让 `render()` 打印其完整消息；**#7 续**：`metrics.verdict_agreement()` + `WRONG_SCORE_LINE=60`（引用 schema 定义）、`report` 新增 `verdict_agreement` 字段并把它列为 Grade **头号**、`n_a>0` 时打印「N 条未产出可解析分数」、`gold_sanity` 文案由"补部分分"更正为"改用 verdict_agreement" |
| `scripts/memory_step4fix_gate.py` | **Step 4/5 Gate（现 162 项：⑧~㉒ + ③a~③u）**（新增；⑫ 组 = E-4；③d~③j = 修 #4/#6/#10；⑫k = 修 #8；③l~③n = 修 #7 退化检测；③o~③r' = 修 #7 换指标 `verdict_agreement`；③s~③u = 修 #11/#12；⑬a~⑬l + ⑩e/⑩f = 修 #14/#15/#17 并钉住 #16 的契约；⑭ = #2 逐题口径；⑮ = provenance/死代码；⑯⑰ = 检索配置与逐轮落盘；⑱ = #21 主指标单一公式；⑲ = #22 KP 聚合取证；⑳ = #19 非众数占比；㉑ = 预检探推理端点 + 写链断裂标环境类；**㉒ = #24 OFF 臂必须真空白进程级 store**） |
| `scripts/memory_step5_paired.py` | **Step 5 paired control**（Store ON/OFF）（新增） |
| 其余 `scripts/*.py` | 探针构建 / 成本估算 / review 导出等工具（新增） |

---

# 七、★ 必须传承的纪律

| # | 纪律 |
|---|---|
| **1** | **消耗 token / 花钱的动作必须等用户明确说「开始」**（改配置 ≠ 可开跑） |
| **2** | **每次做任务前先商量设计口径，审过再实施** |
| **3** | **case validity ≠ product failure** —— case 不成立不得计入产品失败统计 |
| **4** | **alias 纪律**：来源是「教材怎么写」，不是「模型怎么输出」 |
| **5** | **1 条 probe 的差异不要外推**（LLM 有随机性；判定基于更大样本） |
| **6** | **判据不能过严也不能过松**：过严把成功判失败，过松骗过字符串检测 |
| **7** | Phase 0B frozen baseline **只读**；新实验用 `phase1_` 前缀新文件 |
| **8** | **快照纪律**：文件名带「**改动语义 + 阶段**」（禁 `before`/`backup`/`orig` 这类时间序命名）；`cp` 后**立即 `md5sum`**；恢复后 `diff` **逐位校验**才算成功 |
| **9** | **库中同名前缀行数 ≠ 本次运行写入数** —— `make_user_id` 带随机后缀、跨运行不复用 ⇒ 断言写入必须记**跑前/跑后计数差** |
| **10** | **护栏输出的数字是异常探测器** —— 统计数字与预期不符时，**先怀疑自己的操作/文件版本，再怀疑代码**（曾靠「全表 8 条 vs 应为 4 条」抓到快照拿错） |
| **11** | **改基线前先做隔离实验** —— 逐个关掉候选改动跑同一指标，判据是「关掉它能否**逐位复现**旧结果」，而不是「方向看起来对」 |
| **12** | **断言「某缺陷存在/不存在」前，先确认看的是哪一份 checkout** —— `HEAD` 相同 ≠ 内容相同，判据是 `git status` + 文件实际内容，**不是 commit hash** |
| **13** | **未提交文件禁止用 `git checkout -- <file>` 回退** —— 很多文件接手时已是 ` M` 状态，`checkout` 会把**他人/前轮**改动一起抹掉 ⇒ 用**快照**或 `git diff` 存 patch |
| **14** | **环境异常先于代码怀疑** —— 写入类断言成片变红时，**先探依赖服务**（本次即 embedding 502 导致 14 项 ❌，与代码无关） |
| **15** | **本机跑 Memory 三护栏必须带 `PYTHONIOENCODING=utf-8`** —— 否则 Windows GBK 控制台打印 ✅ 时抛 `UnicodeEncodeError`，**崩在 `print` 而不是判据失败**，且**退出码同样是 1**，极易误判成红灯（2026-10-07 实测踩过） |
| **16** | **护栏两侧若来自同一函数，它只证明「函数自洽」，不证明「函数正确」** —— ⑫a~⑫c 的 prompt 词表与 canonical 集合同出 `kp_vocab`，kp_vocab 自身漂移时全绿无感知；须**独立双读**再比（⑫i 即为此而加） |
| **17** | **gold 必须用「可接受集」并逐题查 `kp_index`** —— kp_index 里 `排序`（章级）与 `快速排序`（算法级）是**并存两个节点**，而 `堆` **根本不存在**（只有 `堆排序`）。写单值 gold 会把「合法地选了另一档粒度」判成未命中 ⇒ **假阴性产品失败**（E-5 首跑即犯，与首跑「AVL树」同类，第 2 次应验） |
| **18** | **修 gold 不该重新付费** —— 判据里凡「只依赖 gold」的项，用零 LLM 的重析（`memory_e5_probe.py --reanalyse --write`）原地重算；`kp_raw` / `kp_normalized` 这类**原始量**不变，重跑探针只是浪费 token 且引入新的随机性 |
| **19** | **本机配置 ≠ 仓库默认** —— `.env` 是未跟踪的本机文件，`pydantic_settings` 的 `find_dotenv()` 还会**向上层搜索**（worktree 会继承主目录 `.env`）。⇒ 别把「我这台机器上崩了」外推成「clone 会炸」（2026-10-07 我犯的：拿本机 `DEFAULT_MODEL=deepseek:deepseek-flash` 断定评委 clone 会失败，实际 `.env.example` 是留空自动推导，根本不崩） |
| **20** | **改指标口径必须同时登记新旧两侧数字，且绝不回写归档** —— 否则旧文档里的数字与新口径混用而无人察觉。本轮 `used` 修正后 ON 组 `used` 2→1、`correct_use` 2→4，两侧都写进 §20.5；归档与 `PHASE1_MEMORY_STEP5_FINDINGS.md` 保持原样并标注「不可混用」 |
| **21** | **重算归档时要一并套上原口径的有效性门** —— 我重算 Store OFF 组时只按新 scorer 跑，没管 `validity_valid`，于是报出一批 `None → False/True` 的**假 Δ**（那些 case 本就是 invalid ⇒ 记 N/A）。⇒ 离线重算的对照必须与产出该数字时的**完整判定链**一致，否则差异是重构产物而非语义变化 |
| **22** | **转述任何比率前先自己重算，并把分母的两种口径都算一遍** —— 本轮两个反例：审计员给「4/13 = 30.8%」把分母当「落分记录数」，漏掉「完全无落分记录」这种最硬失败形态（应为 5/9 = 55.6%）；我预测「修 #4 会下调已有数字」也只对了一半（`used` 降、`correct_use` 升）。⇒ 别人给的数和我给的预测，**同一条证据规则**适用 |
| **23** | **被多任务复用的指标函数，会用「另一个任务全绿」掩盖 bug** —— 查 `category_hit` 时只看汇总率永远发现不了问题：`qa`/`generate` 的 case 传 `network`（映射表有此键）⇒ 全 True；`grade`/`verify` 传 `cn`（映射表无此键）⇒ 恒 False。⇒ 排查手法：**按输入取值分组看命中分布**，别只看聚合值；出现「某个取值组全 True 或全 False」就是映射/口径断了的信号 |

---

# 八、下一步（按既定顺序）

| 步 | 动作 | 状态 |
|---|---|---|
| 1 | 改产品三层 | ✅ 完成 |
| 2 | 写 1 个最小 2-hit case | ✅ 完成 |
| 3 | 逐层检查（★ 闸门） | ✅ **通过**（脚本级 ①~⑤+⑥a） |
| **4** | **改 harness**：多段会话 + 捕获记忆卡 + 每 case 独立 user_id + 跑前清理 | ✅ **完成**（`scripts/memory_step4_gate.py` 14 项全绿 + 反向验证） |
| **5** | 验证 **new thread + same user_id**（Store 通、checkpointer 不通） | 🟡 **当时读作完成，现降级为「半边完成」**（`PHASE1_MEMORY_STEP5_20261006_2144.md`：ON 组 1 卡 1 召回、OFF 组 0 卡 0 召回）。★ **#24 作废了其中的 OFF 半边**：旧 OFF 臂只置 `agent.store=None`，没空白进程级 `get_store()` ⇒ 两组同一条件，「0 卡 0 召回」是 #22（画像恒空）造成的假象。**ON 侧「有卡且召回」这一半仍然成立**。带有效 OFF 对照的版本在 **§20.8.6**（`mem-002`，同 case 同前置条件） |
| **6** | 写完整 6 条 case + gold（**须查 `kp_index` 规范名**） | ✅ 完成（`evals/datasets/demo/memory_cases.jsonl` 6 条） |
| **7** | Sanity（逐层验收） | ✅ 完成（`memory_step4fix_gate.py` 当时 **71 项全绿**；⑫ 组后 80 → 85 → 87 → 89 → 93 → 98 → 116 → 128 → 129 → 134 → 138 → 148 → 157 → **现 162 项全绿**（128 之后：③j+ 数据集学科码扫描、⑯ 检索配置/top-k 落盘、⑰ 逐轮日志、⑱ #21 主指标单一公式、⑲ #22 KP 聚合取证、⑳ #19 非众数占比、㉑ 预检探推理端点、**㉒ #24 OFF 臂真空白进程级 store**）） |
| **8** | 跑 6 条 Memory | ✅ **完成**（paired control，消耗 token） |
| **9** | 若产品行为变化 → 重跑受影响基线 | ✅ **已跑（Step 9，2026-10-07）**：E-5 复测 12 次 + Memory 配对多轮 + grade/verify 探针补测；逐份 `code_version` 归属见 §20.8.5，配对终局见 §20.8.6。★ 未回写 0B 冻结基线（新结果一律 `phase1_` 前缀新档） |

### ★ 现在的决定清单（**D1~D11 已裁决并落地 ⇒ 只剩 D12**，2026-10-07 深夜）

| # | 决定 | 我的建议 | 代价 |
|---|---|---|---|
| ~~D1~~ | **#2 Generate 主指标口径**（池化 0.9423 / 逐题适用项全过 0.80 / 严格 5/5 = 0.00） | ✅ **已按建议落地（2026-10-07）**：主指标 = 逐题「适用项全过」**0.80（12/15 题）**，池化 **0.9423（49/52 项）** 降级为诊断（留着做对照）；护栏 **⑭a~⑭f** —— ⑭c 锁「同样本两口径必须分叉且池化偏高」（证明换口径真有信息量）、⑭d 锁两个已发表数字不许漂、⑭f 锁「整题不可测的题不许假装进分母」 | 已完成 |
| ~~D2~~ | **入库范围** | ✅ **已落地（2026-10-07 三次提交 + 标签）**：`src/evaluation/task_eval/`（12 个 .py）+ `src/core/kp_vocab.py` + `scripts/` 12 个护栏/探针 + `evals/datasets` 下 `demo / probes / probes_phase1` 三个目录 + `exam_answer_corrections.json` 全部入库；`.gitignore` 加了 `.claude/`（`.workbuddy-ai/` 由你删除，未写规则）。★ 本条原先的遗留「因此 **HANDOVER.md 本身在标签之外**」已由 **D11** 关闭：`evals/results/task_eval/*.md` 16 份（≈200KB）入库，`*.jsonl`/`*.log`/`*.report.json` 维持不入库 | 已完成 |
| ~~D3~~ | **§7.1 三处死代码** | ✅ **已落地，但事实与审计文档不符**（明细 §20.5.2）：`asearch_episodes` **真死 ⇒ 已删**（连模块文件一起；护栏 ⑮a/⑮b 用 **AST** 扫引用 —— 第一版用「文本里有没有这个词」，结果**扫到护栏自己的注释**、假红灯，已改；再植入一个 import 探针确认它会咬）；`verifier._arun_llm_relevance_check` **不是死代码**（`retriever.py:377/403` 在 `use_llm_verify=True` 时真会 `await` 它，只是全仓 24 处调用都传 `False`）⇒ **保留，建议做消融**（删要连 `use_llm_verify` 参数一起动，波及 20+ 脚本签名）；`service.py:89` handoff 过滤的注释**已自陈「没有活路径、属有备无患」**⇒ 不动 | 已完成（消融另计） |
| ~~D4~~ | **#3 归档 provenance 不含 `prompt_set_version`** | ✅ **已落地**：`CaseRecord.prompt_set_version` 由 `_attach_provenance` 从 `prompts` 取**活值**写入 ⇒ 新归档自描述跑在哪个提示词上；**老归档缺该键 ⇒ 读侧按空串（未知）处理，绝不回填当前 hash**（回填等于伪造 provenance）。护栏 **⑮d/⑮d'**（真跑 `run_case(run_agent=False)`，零 LLM）+ **⑮e 反向**（把 `PROMPT_SET_VERSION` 改成 SENTINEL ⇒ 新 record 必须跟着变；若写成硬编码字面量，⑮d 照样绿、这条必然红） | 已完成 |
| ~~D5~~ | **Step 9（真跑）** | ✅ **已跑完**（实测 252 次 LLM 调用 + E-5 的 12 次 + 探针 ≈26 次 + step2 复跑 2 次）；结果、归因与逐份 `code_version` 见 §20.8.1~§20.8.5 | 已完成 |
| ~~D6~~ | **#19 judge 校准表的 PASS 只有 2/30 的信息量** | ✅ **已按建议落地（① 加「非众数占比」）**：`CalibrationReport` 新增 `human_mode / informative_n / informative_share / rank_degenerate`，CLI 在占比 < 20% 时打 ⚠（真实表 = 2/30 ⇒ 会打）。★ **只加露出、不改判定**：阈值是「预先约定标准」、人工分是真实标注（改它=伪造数据），退出码不变。护栏 **⑳a~⑳d**（⑳c 反向：分布正常的表不许误报） | 已完成 |
| ~~D7~~ | **#20 §4「L3 闸门」按当前语料算不出来** | ✅ **已裁决（① 按 `EFFECT_PLAN §11` 走披露）**：论文口径固定为「§4 的判定**未做出**（既不是『是』也不是『否』），原因是 `question_id_recall@k` 在当前语料下不可计算」+ 三条证据（gold 有 / 语料 metadata 没有 / 归档字段出现 0 次）。❌ **禁止**用代理指标 `exam_hit@k` 冒充它去回答 §4 的因果问题 | 已完成（零成本） |
| ~~D8~~ | **#22 Memory 正样本天然测不到召回** | ✅ **已裁决（① 改 case）**，且实跑中做了**三次**修正：①A 段两题对齐同一考点；②发现 `mem-003` 第二题的**学生作答其实是对的**（一趟 Hoare 划分复算 = `38,49,65,97,76`）⇒ 模型判 100 分是判对的，错在 gold 要求两次都 <60 ⇒ **前置条件天然不可满足**（这同时**作废**了 §20.8.3 「错题被判 100 分 = 缺陷 A 症状」的归因，登记为 **#25**：真正的误判是反方向 —— 小根堆那题答对却被判 0 分）；③两条正样本的 `values` 由章名收到具体考点（**#26**：子串包含判定 + 章名 ⇒ 「召回成功」偏松）。★ 换进去的题面是**自拟辨析题**、不是真题原文 ⇒ 论文按此标注；未造 `human_score`、未动 L3 语料。指纹 `b5619085d7979a36` → `3c938365da7ce614`；结果见 §20.8.6 | 已完成（重跑消耗 token） |
| ~~D9~~ | **标签后 `src/` 又改了多个文件** ⇒ `V-2026-10-07` 不含产出 Step 9 数字的代码 | ✅ **已裁决（① 补 `V-2026-10-07B`）**：指向收尾验证通过后的 HEAD，并把 §20.8.5 的逐份版本归属并进 §20.4；§20.0 回填落点与**当时的**指纹/护栏计数（★ 自指限制照旧：落点 SHA 只能由后续提交回填） | 已完成（零成本） |
| ~~D10~~ | **#23 检索链上有一层「实现了但从未开启」**（`use_llm_verify` 全仓 24 处调用一律 `False`） | ✅ **已裁决（② 承认未验证并披露，不跑消融、不删）**：论文里检索章描述该层必须写「已实现，**默认关闭且未做消融**，本文所有检索数字均不含该层的贡献」；❌ 不得写成「相关性校验提升了检索质量」（无证据）。不删的理由：删要连参数一起动，波及 20+ 脚本签名 | 已完成（零成本） |
| ~~D11~~ | **交接与 findings 的 10 个 .md 是否在版本控制里** | ✅ **已裁决（① 入库）**：`evals/results/task_eval/*.md`（约 158KB）入版本控制；★ **`*.jsonl` / `*.log` / `*.report.json` 维持不入库**（3.7MB，其中单个 log 1.9MB）⇒ 归档的可追溯性仍由 §20.0 的文件指纹 + §20.8.5 的逐份 `code_version` 表承担，而不是靠二进制存档 | 已完成（零成本） |
| **D12**（新） | **#27 layer top-up 路径把 `knowledge_points` 写死成 `[]`** ⇒ 走这条路的 top-k 证据在 `kp_hit`/`kp_mrr`/`coverage` 眼里「没标考点」，检索指标被**系统性低估**；并给 §20.5.1 那 8 条 `coverage` N/A 提供了比「旧索引」更可能的解释（但归档没存 `evidence_id` ⇒ 仍不能定论） | 三条路：**(A)** 改产品 1 行（`_doc_to_evidence` 用解析器）—— 指标与对外契约一起真，但 `EvidenceDoc.knowledge_points` 是契约字段（`agents/tools.py:54` 带给 agent）⇒ **动检索链 ⇒ 新锚点 + qa/generate agent 侧要重跑（要 token）**；**(B)** 只改评测口径（`retrieval_probe._to_item` 空值时从 `metadata` 兜底解析）—— 零 token、不触发版本，`retrieval_gate`/探针当场可重测，代价是「指标」与「模型实际看到的」不一致；**(C)** 只披露。我建议 **(B) + 单独披露产品侧那半**（与 #10 同构） | (B) 零 token；(A) 需 agent 侧重跑 |

**⇒ ⑥b（agent 在新 thread 里实际召回）已由 Step 5 真跑验证成立（`mem-001`）。**

### ★ 缺陷 E 修复进展（**方案 A：注入候选 canonical 词表**）

**用户裁决**：方案 A —— 在 `GRADE_PROMPT` 注入候选 canonical 词表，从**上游**约束模型输出。

| 子步 | 内容 | 状态 |
|---|---|---|
| **E-1** | 新建 `src/core/kp_vocab.py` —— canonical 词表**单一事实源**（只依赖 `json`/`pathlib`） | ✅ **完成** |
| **E-2** | `memory/topics.py` 词表解析**外移**至 `core.kp_vocab`（薄代理，行为等价） | ✅ **完成** |
| **E-3** | `prompts/service.py` 的 `GRADE_PROMPT` 注入**按学科分组的词表块** | ✅ **完成**（`_knowledge_points_block(names_by_subject())`，import 期注入；空词表降级回 8 示例） |
| **E-4** | 加机械护栏（prompt 内词表须全 ∈ canonical）+ 反向验证 | ✅ **完成**（Gate 新增 **⑫ 组 9 项**；三模式篡改均报红；补 ⑫i 独立双读） |
| **E-5** | 小规模探针验证效果（**消耗 token**，需用户确认） | ✅ **完成**（`scripts/memory_e5_probe.py`，配对 12 次批改调用：Δ 词级跟随率 **+0.602**、期望入桶 **3/6 → 6/6**，见 §5.6） |

**E-1 ~ E-4 已完成的验证**（**不依赖 embedding**，故在环境阻塞下仍可信）：

- `core.kp_vocab.canonical_names()` 与旧实现**逐位一致**（162 个，集合相等 ✅）
- 按学科分组：ds **52** / co **39** / os **36** / cn **35** = **162**，分组并集 == 全集 ✅
- `normalize_topic` 行为回归：`AVL树 → 平衡二叉树` ✅、含空格名（`B+ 树` / `Cache 替换算法`）✅、
  `deadlock → 死锁` ✅、别名表 target 全 ∈ canonical ✅；`ruff` 通过
- 三护栏中 **⑪ 组 8 项全绿**（含 `⑪a' canonical 集合可加载 — 162 个`）
- **E-3 注入完整性**：`GRADE_PROMPT` system 内解析出 **162 个**词，与 `canonical_names()` **集合相等**（遗漏 0 / 多余 0）；`AVL` 等别名**未出现**；无花括号；system **1317 字符**
- **E-4**：⑫ 组 9 项全绿 + **三模式篡改均报红**；全量 Gate **98 项全绿**（E-4 当时 80；★ 现 116）、退出码 0；`import agents.grading_core, service.service` 冒烟通过 ⇒ **`prompts` → `core.kp_vocab` 无循环 import**（★ 但 `import core.kp_vocab` 会执行 `core/__init__` → `core.llm` → 拉起 `langchain_openai`，故该模块 docstring 的「只依赖 `json`/`pathlib`」**在效果上不成立** —— 属文档不准、非论文问题，登记备查）；`ruff check` / `ruff format` 通过

**设计要点（**已按下列不变量实现**；后续改动必须保持，括号为守护判据）**：

- **必须动态从 kp_index 读**，**不得硬编码** —— 硬编码会再次制造「不同源」，即缺陷 E 的成因。（⑫b/⑫c/⑫i）
- **不注入 `aliases`** —— 否则模型可能输出别名（`AVL`）而非 canonical（`平衡二叉树`）。（⑫d）
- 词表**无花括号**（已核验）⇒ 不破坏 `ChatPromptTemplate` 与 `prompts/__init__.py` 的 import 期校验。（⑫f；**若将来 kp_index 新增含花括号的考点名，服务会在 import 期直接崩**，这是刻意的「启动即失败」）
- 词表约 **925 字符**（162 名拼接）⇒ 注入成本可接受；批改 system 实测 **1317 字符**，上界 **2000** 由 ⑫g 锁定。
- **降级**：kp_index 读不到 ⇒ 词表为空 ⇒ 退回原有 8 个示例（服务不得因此起不来）。（⑫e）

### ★ 当前待办清单（**按序**，2026-10-07 更新）

| # | 项 | 状态 |
|---|---|---|
| 1 | 启动 Docker Desktop + embedding 容器 | ✅ **完成**（`/health` 双 200，`tei-embedding` / `tei-rerank` 均 Up） |
| 2 | 重跑三护栏 | ✅ **完成**（**11 / 14 / 87** 项全绿；87 = 71 + ⑫ 组 9 + ③d~③j 7。Step 5 前基线为 11 / 14 / 71） |
| 3 | 完成 **E-3 / E-4** | ✅ **完成**（词表注入 + ⑫ 组护栏 + 三模式反向验证，见 §5.6） |
| **4** | **E-5 小规模探针**：验证缺陷 E 是否真的解决 | ✅ **完成**（配对 12 次批改调用，**Δ 跟随率 +0.602 / 入桶 6/6**）。产物 `evals/results/task_eval/phase1_e5_prompt_following.jsonl`；判据按修正后的口径 = 「KP **全** ∈ canonical」+ 词级跟随率 + 归一后入桶，**不是** step2 原来的「KP 非空」 |
| 5 | 若 E-5 显示方案 A 不足 → 叠加「产出后按 kp_index 语义匹配再落库」 | ✅ **倾向不做**（E-5 显示方案 A 已把入桶打满；残留 1 个自造词只造噪声桶、不阻断目标 KP 聚合）。★ 该兜底会新增一条 embedding 依赖路径且属产品行为变更，**最终随 Step 9 真跑再确认** |
| 6 | **Step 9**：缺陷 E 修复后重跑 Memory 基线 | ⏸ **待授权**。属**产品行为变更**，**不得回写 Phase 0B 冻结基线**（新结果另存 `phase1_` 前缀文件）。★ 提示词已变 ⇒ 旧结果不可直接对比；**顺带补 step2 gate 在 E-3 后的复测** |
| **⚠** | **provenance 洞（已登记为 §20.5 #3）** | 归档 record **无 `prompt_set_version` 字段**，且 `code_version` 因工作区全未提交而 **E-3 前后同为 `648d819-dirty`** ⇒ 无法事后甄别某条结果出自哪个 prompt 版本。当前靠 §20 的**归属矩阵**人工对账；两个补洞选项：① 提交使 sha 变化（= 上面那条）；② 把 `PROMPT_SET_VERSION` 写进 `task_eval` 的 record schema（一处字段，成本最低，正是它的用途） |
| **⚠** | **review 偏离 #2 / #7：待你拍板（属论文叙述决策，不是代码 bug）** | **#2 解剖已完成、建议口径见 `docs/EXPERIMENTS.md` §20.5.1**。★ 真正的问题不是"选哪个公式"，而是**"五项"里只有 `correctness` + `coverage` 两项有区分力**：`structure`/`answerability` 恒 15/15（零区分力）、`difficulty` 是**双重断开的死项**（gold 全空 + `runner.py:475` 第二参硬编码 `None`）。`coverage` 的 8 个 N/A **疑似旧索引**产物——★ **全量**分页扫描（我先前用抽样外推成"100%"，已撤回）：总体 **82.8%**，四个学科集合 **99.0–100%**（仅剩 **10 条** `basic` 讲义 `detail` 块无标签），`questions` 66.2%（692 条真题答案块，但 **practice 可用层 = `["advanced","basic"]`，那些块不进包**）⇒ 因归档**未存每块来源/标签**，**能否重跑救活要由 Step 9 定论**。三数 = 池化 `0.9423` / 逐题适用项全过 `0.80` / 严格 5/5 `0.00`；建议取 **0.80 + 改名"本批 4 项适用"**。**#7** ✅ **已修完（换指标，不是补标）**：两极 gold 下 `score_tolerance` 判不可判（保留 `raw_rate`）、新增 `verdict_agreement` 当 Grade 头号指标（实测 0B 15/15、Phase 1 13/13 + 强制披露 2 条不可解析）、`sanity` 出集合级 PENDING、护栏 ③l~③r'。★ 原先写的「15 条按 rubric 人工标部分分」**是错的建议，已撤回**：L3 语料 674/674 全为 2 分选择题、学生作答仅 1 个字母 ⇒ 无部分分可标，硬补只能造题（= 造假 + 动语料）。Grade 轴的**真实**遗留问题只有一个：**2 条批改未产出可解析分数**。 |
| ✅ | **提交 + 打标签 `V-2026-10-07`** | 已完成（2026-10-07 收盘）：`63b3b79`（效果层代码 + 11 条口径修复）→ `c5d5bca`（gold 数据集）→ `0f24891`（文档，**= 标签落点**）→ 锚点回填提交。解析：`git rev-parse "V-2026-10-07^{}"` → `0f24891599c1…` |
| **✅** | ~~commit 阻塞项~~ **已修复**（2026-10-07，用户授权） | `src/rag/llm_calls.py` `_try_kv_dict` 续行分支改为**显式收窄** `current is not None and current in _KV_MULTILINE_FIELDS`。★ **不是行为改动**：`current` 只在命中合法 key 时与 `started` **同步赋值** ⇒ 走到该 `elif` 时 `current` 恒非 `None`；且 `None` 本就不属于 `frozenset[str]`，旧写法运行时同义，只是成员测试无法让 pyrefly 把 `str \| None` 收成 `str`。**验证**：`pyrefly check` → **0 errors**；⑨ 组 **15 项全绿**（⑨i `is_wrong` 不被污染 = else 侧、⑨j feedback 多行续行 = 进入侧，两侧都被覆盖）。⇒ **pre-commit 不再挡** |

---

# 九、关键文件速查

| 用途 | 路径 |
|---|---|
| 总方案 | `docs/EFFECT_PLAN.md` |
| **★ 效果版本锚点 `V-2026-10-07` + review 偏离账本** | `docs/EXPERIMENTS.md` **§20**（§20.4 = 结果归属矩阵，§20.5 = 9 条偏离含本轮 2 条已修）。★ **review 明细只存那一处**，本文件不复制副本 —— 两处记账必然漂移 |
| Phase 0B 冻结快照 | `evals/results/task_eval/PHASE0_FREEZE.md` |
| Phase 1 Verify 报告 | `evals/results/task_eval/PHASE1_VERIFY.md` |
| ~~Memory 过程文档~~（**已整理删除**） | 诊断 / 设计 v3 / Step2 设计 / case 重写 / Step4 审阅·修复 → **已移入回收站**（结论见 §五） |
| **★★ Step 5 结果与诊断（主文档）** | `evals/results/task_eval/PHASE1_MEMORY_STEP5_FINDINGS.md` |
| Step 5 配对报告 | `evals/results/task_eval/PHASE1_MEMORY_STEP5_20261006_2144.md` |
| 旧产物**数据**（**不可作基线**） | `phase1_memory_step5_store_{on,off}_pre_fix_20261006_2023.jsonl` |
| 目录约定 + TODO | `evals/results/task_eval/README.md` |
| **Memory case 数据** | `evals/datasets/demo/memory_cases.jsonl` |
| **★ canonical 词表（单一事实源）** | `src/core/kp_vocab.py` |
| **★ 批改词表注入实现（E-3）** | `src/prompts/service.py` → `_knowledge_points_block()` |
| **★ E-4 护栏（⑫ 组 9 项 + 探测器）** | `scripts/memory_step4fix_gate.py` → `check_12()` / `_vocab_tokens()` |
| **★ E-5 效果探针（配对，零判定）** | `scripts/memory_e5_probe.py`（`--reanalyse --write` = 零成本重析） |
| **E-5 归档** | `evals/results/task_eval/phase1_e5_prompt_following.jsonl`（12 条 = 6 题 × 2 臂） |
| Gate 脚本（3 个） | `scripts/memory_step2_gate.py` · `memory_step4_gate.py` · **`memory_step4fix_gate.py`** |
| Step 5 配对脚本 | `scripts/memory_step5_paired.py` |
| 冻结基线（**只读**） | `evals/results/task_eval/phase0_baseline_final.jsonl` |
| Phase 1 结果 | `evals/results/task_eval/phase1_baseline_v2.jsonl` |
| Step 5 原始 record | `evals/results/task_eval/phase1_memory_step5_store_{on,off}.jsonl` |
