# Phase 1 · Step 5 · Memory 跨会话召回 + paired control —— 结果与诊断

**日期**：2026-10-06
**状态**：已真跑两轮（均消耗 token）。**第一轮（缺陷修复前）因链路断而结论无效、已归档；
第二轮（修复后）已确证「跨会话召回成立」，并新发现缺陷 E。**
**provenance**：本轮含 `schema/grading.py` + `prompts/service.py` + `rag/llm_calls.py` + `memory/remember.py` + `memory/topics.py` + `core/settings.py` 产品改动 ⇒ **不得回写 Phase 0B 冻结基线**

> **阅读指引**：一至六节是最初诊断（含 4 个缺陷 A–D）。
> **第七节起为重跑附录**，含：旧产物判定（无效）、新结果、**新缺陷 E**、
> 以及一节**已撤回的错误推断**（记为「非缺陷」，供后人避坑）。

---

## 〇、当前有效结论（2026-10-06 重跑后）

1. **跨会话召回已成立**：`mem-001` 在 A 段批改 → 写 Store → B 段**新会话**读 Store →
   记忆卡 `【学生记忆】\n薄弱：平衡二叉树` → 回复采纳 ⇒ `recalled_actual / used / correct` 全 True。
2. **paired control 干净**：Store OFF 组「0 卡 / 0 召回」，ON 组「1 卡 / 1 召回」⇒
   召回**确实来自 Store**（机械对照，非推断）。
3. **Store 清理契约已验证生效**（跑前删、跑后删、零泄漏）⇒ 测量本身可信。
4. **新缺陷 E 未修**：批改产出的 `knowledge_points` 是 LLM 自造自由文本
   （`图的基本性质`/`堆的定义`…），非 canonical ⇒ 聚合桶互不相同 ⇒ 3 条正样本只有 1 条召回。
   **这是当前最值得投入的一项。**

---

## 一、一句话结论（最初诊断）

Step 5 首轮**没有**验证出「跨会话召回成立」，但**不是因为 Memory 产品不行**，
而是**批改 → 落库 → 聚合链路存在 4 个真实缺陷**，任一都会让 A 段写不出 `weak_topics`：

| 缺陷 | 性质 | 影响 | 状态 |
|---|---|---|---|
| **A** `feedback` 超长 ⇒ 批改硬失败 | 真实产品缺陷 | 实测批改失败率 **62.5%** | **已修（3 处收口）** |
| **B** `GRADE_PROMPT` KP 示例名非 canonical | 真实产品缺陷 | 诱导模型输出漂移 KP ⇒ 聚合错配 | **已修（含 3 处漏改）** |
| **C** 工具拿不到 `config` ⇒ `record_grade` 被静默跳过 | 真实产品缺陷 | 批改**成功**但 **EPISODES=0** ⇒ 永不召回 | **已修（根治）** |
| **D** `normalize_topic` 主动改坏 canonical name | 真实产品缺陷 | **21 个含空格 canonical + 1 个别名映射**被改坏 ⇒ 聚合永久错配 | **已修（canonical-aware 重写）** |

**缺陷 C 是真正的"沉默杀手"**：工具输出完全正常（`评分：40/100`），批改成功、分数正确，
但 `user_id` 恒为 `None` ⇒ `if uid:` 分支被跳过 ⇒ **一条 episode 都不写**。
只看工具输出、日志无异常，无法发现；只有断言 `EPISODES > 0` 才能抓到。

**缺陷 D 是最隐蔽的"系统性错配源"**：它不报错、不丢数据，只是把 `knowledge_points`
悄悄改写成**不是 canonical** 的字符串，于是聚合时的相等匹配**恒不命中**。
单独看每一条 episode 都"写成功了"，只有把 `normalize_topic` 拿去和 kp_index 全量比对才能发现。

**case-validity 层正确地拦下了首轮污染**：12 次 case run 中 **9 次**判为 `case_invalid`
（前置条件没凑成），**没有被误记成产品失败** —— 这正是该层要防的事。

---

## 二、paired control 结果（首轮，受缺陷污染）

| 指标 | Store ON | Store OFF | 说明 |
|---|---|---|---|
| case 数 | 6 | 6 | — |
| 有效 case（valid≠False） | 1 | 2 | 其余为 `case_invalid` |
| **有 memory card 的 case** | **0** | **0** | 两组皆 0 |
| **recalled_actual=True** | **0** | **0** | 两组皆 0 |
| recalled_pass=True | 1 | 2 | 均为「负样本期望不召回且确实没召回」 |
| used / correct_use | 0 / 0 | 0 / 0 | — |
| `case_invalid` | 5 | 4 | 合计 9 |

**paired control 的干净性**：Store OFF 组「有卡=0、召回=0」⇒ 旁路无污染。
但 Store ON 组**也是 0** ⇒ 对照失去意义（ON 组本身就没有可召回的东西）。
**修完缺陷后必须重跑**才能得到有效对照。

---

## 三、根因（已定位到具体代码行）

### 缺陷 A：`feedback` 超长 ⇒ 批改硬失败

实测日志：

```
LLM call failed [grading]: ValidationError: 1 validation error for GradingResult
feedback
  String should have at most 800 characters
  [type=string_too_long, input_value='结构描述基本正确...\n<parameter=score>\n95']
```

链路：

```
GRADE_PROMPT（**未约束 feedback 长度**）
  → 模型输出 feedback > 800 字符（常混入工具标记 `<parameter=score>`、解体过程）
  → Pydantic GradingResult 校验失败（schema/grading.py max_length=800）
  → call_structured 捕获异常返回 None（rag/llm_calls.py）
  → agrade_answer 抛 RuntimeError("批改失败")
  → grade_student_answer 工具返回 "批改失败：批改失败"
  → 不写 episode、无分数
  → compute_weak_topics 无输入 ⇒ profile.weak_topics 为空
  → B 段 load_memory 注入空卡 ⇒ recalled_actual=False
```

**量化（配对对照，同一模型/同一 prompt/同一批样本）**：

| 配置 | 批改成功率 |
|---|---|
| 修复前（`RETRIES=0` 等价） | **3/8 = 37.5%** |
| 修复后 | **10/10 = 100%** |

**注意**：修完后 `RETRIES=1` 与 `RETRIES=0` 都是 10/10 —— 说明**截断**是主要贡献，
重试是「备用而未触发」的保险。重试逻辑另用**注入式假 LLM** 独立验证（6/6 通过）。

### 缺陷 B：`GRADE_PROMPT` 的 KP 示例名非 canonical（**同类 bug 的第三处**）

- 原始 `prompts/service.py` 示例：**`AVL树` / `图论` / `TCP流量控制`**；
- 我在 `schema/grading.py` 修过后，`GRADE_PROMPT` **漏改**；
- 更严重：我**第一次修 `GRADE_PROMPT` 时又写错了 3 个新示例名**：

  | 我写的 | kp_index 实际 canonical | 结论 |
  |---|---|---|
  | `二叉搜索树` | `二叉排序树` | ✗ 漏改（第二次仍错） |
  | `页面置换` | `页面置换算法` | ✗ 漏改（第二次仍错） |
  | `Cache 映射` | `Cache 映射方式` | ✗ 漏改（第二次仍错） |

  ⇒ **共 6 处非 canonical 示例名**，现已全部核验修正（`⑧c` 护栏锁定）。
  实测模型输出 `['二叉排序树', '平衡二叉树']` 是对的 —— 但**风险一直在**。

**教训**：修 canonical 示例名**必须用机械护栏**（见 §五 `⑧`），
人工核对源码字符串会因**跨行拼接**而漏看后半句（我已踩过：正则只抽到 4/8 个示例名）。

### 缺陷 C：工具拿不到 `config` ⇒ `record_grade` 被静默跳过（★ 根治）

**证据**（经真实 agent 图跑，与 Step 5 harness 同路径）：

```
工具输出:    '评分：0/100\n结论：\n错因与建议：概念混淆。...'   ← 批改成功
record_grade 调用次数: 0                                      ← 但一条都没写
EPISODES: 0
```

**根因**：LangChain **不会**把运行时 `RunnableConfig` 注入工具函数的 `config` 参数。
实测对比：

| 取值方式 | 结果 |
|---|---|
| 函数参数 `config` | `None` ❌ |
| `langgraph.config.get_config()` | 能拿到真值 ✅ |

工具里写的是 `uid = user_id_from_config(config)` ⇒ 恒 `None` ⇒ `if uid:` 跳过 ⇒ 不落库。

**修复**：`memory/remember.py` 的 `_resolve_config()` —— 显式参数优先，
缺失时**回落到运行时上下文**；三个 `*_from_config` 共用。
修复后经真实图复验：`record_grade 调用=1`、`EPISODES=1`、
`kp=['二叉排序树','平衡二叉树']`。

**端到端验证**（两次低分批改）：

```
批改 40/100 ×2  →  EPISODES: 2  →  PROFILE.weak_topics: ['二叉排序树', '平衡二叉树']
```

### 缺陷 D：`normalize_topic` 主动改坏 canonical name（★ 最隐蔽）

**证据**（直接探针）：

```
normalize_topics(['TCP 流量控制', '页面置换算法', 'Cache 映射方式', '平衡二叉树'])
  → ['TCP流量控制', '页面置换', 'Cache映射方式', '平衡二叉树']
                          ↑ 3/4 被改坏
```

**两条独立的破坏路径**（`src/memory/topics.py`）：

1. `_WS.sub("", text)` **删掉全部空白** —— 而 kp_index 里 **21 个** canonical name
   本身**含空格**：

   | 被改坏的 canonical（示例） | 改后（不再是 canonical） |
   |---|---|
   | `TCP 流量控制` / `TCP 拥塞控制` / `TCP 连接管理` | `TCP流量控制` … |
   | `Cache 替换算法` / `Cache 映射方式` / `Cache 写策略` | `Cache替换算法` … |
   | `B+ 树` / `KMP 算法` / `信号量与 PV 操作` | `B+树` / `KMP算法` … |
   | `介质访问控制 MAC` / `IP 转发与分片` / `浮点数 IEEE754` | … |
   | （完整 21 个见 `⑪b` 护栏输出） | |

2. `_TOPIC_ALIASES` 里 `"页面置换算法": "页面置换"` —— **把 canonical 改成了非 canonical**
   （kp_index 的 canonical 恰恰是 `页面置换算法`）。

**影响面**：`normalize_topic` 是 Memory 写入 / 派生的**唯一入口** ——
`Episode.knowledge_points ← normalize_topics(模型输出)`，之后与 kp_index 做**相等匹配**。
改名即**永久错配**：`weak_topics` 全是漂移值，`recalled` / `used` 恒 False。

**根因**：旧实现「凭硬编码别名表**猜**什么是规范名」，且**先删空白、再查别名表、从不参考 kp_index**。
正确做法是**以 kp_index 为权威**：输入若已是 canonical，**原样返回**。

**修复**（`src/memory/topics.py` 重写）：引入 `_canonical_names()`（惰性加载 + 缓存 + 失败静默降级），
顺序定为：

```
① 已是 canonical  → 原样返回（保空格、保大小写、不查别名表）
② 命中本模块别名表 → 用目标值（目标值也须 canonical）
③ rag 同义词兜底   → **仅当目标值 ∈ canonical** 才采纳（拦住反向映射）
④ 其余            → 压缩空白稳定化
```

顺序**不可换**：canonical 判定必须在「删空白」和「别名表」**之前**。

**验证**：

| 判据 | 结果 |
|---|---|
| 162 个 canonical 经 `normalize_topic` **恒等** | ✅ 0 破坏 |
| 21 个含空格 canonical 不被去空格 | ✅ |
| **别名表全部 target ∈ canonical**（全表断言，非抽样） | ✅ 4/4 条可达 |
| 别名表条目归一正确（`belady`→`页面置换算法`、`虚存`→`虚拟内存`、`信号量`→`进程同步`） | ✅ |
| **反向映射被拦住**（`二叉排序树` 是 canonical，而 `SYNONYM_MAP` 有 `二叉排序树→二叉搜索树`） | ✅ 保持原样 |

**★ 归因更正（`AVL树 → 平衡二叉树`）**：此例**不是**「别名表正确命中」——
`AVL树` **不在** `_TOPIC_ALIASES` 里，它是靠第 ③ 步 **rag 同义词兜底**命中的。
实际链路：

```
'AVL树' → ① 不是 canonical → ② 不在本模块别名表 → ③ rag 兜底命中 '平衡二叉树' ✅
```

之所以要更正，是因为**否则会高估 `normalize_topic` 的确定性**：
把「薄覆盖兜底的偶然命中」误读成「别名表的稳定覆盖」。
（`belady` / `虚存` / `信号量` 才是真正的别名表覆盖案例。）

**★ 覆盖面更正（338 → 69）**：`rag/synonyms.SYNONYM_MAP` 共 338 条，
其中 **269 条目标值非 canonical**（约 80%），**只有 69 条**可安全采纳。
之所以不能直接用 338，是因为 `SYNONYM_MAP` 是**检索用**同义词表（服务 RAG 召回），
其值域与 kp_index 的 canonical 域本就是两个不同的东西；
且里面有**与 kp_index 方向相反**的映射（`'二叉排序树' → '二叉搜索树'`，
而 canonical 恰恰是 `二叉排序树`），无条件复用会把对的改错。

⇒ 正确表述应为：「当前只有 **69 条** synonym 的目标值属于 canonical KP，
   因此只有这 69 条可以安全进入 canonical-aware normalization。」
   ——这**反向证明**了 canonical-target filter 的必要性（否则 80% 会污染结果）。

`'图论'` / `'TCP流量控制'` 因目标不是 canonical 而被跳过、保持原样 ——
这是**正确的保守行为**：归一不该做知识纠错。

**★ 第二处同类缺陷（review 时发现并已修）**：`"deadlock": "进程死锁"` ——
kp_index 里**根本没有**「进程死锁」这个考点（只有「死锁」），
故归一后落到**不可达值**，聚合照样不命中。已改为 `"deadlock": "死锁"`。
同时清理 3 条**恒等自映射死代码**（`死锁`/`虚拟内存`/`进程同步` ——
键本身已是 canonical ⇒ 顺序 ① 已原样返回，② 永不触发）。
新增 gate `⑪f`（全表断言 target ∈ canonical）与 `⑪g`（死代码检查）把这两类钉死。

---

## 四、本轮已修的（含性质标注）

| # | 文件 | 改动 | 性质 |
|---|---|---|---|
| 1 | `src/prompts/service.py` | `GRADE_PROMPT` 加 feedback/error_analysis **长度约束**（≤200/150 字） | **修 bug**（缺陷 A 的 prompt 侧） |
| 2 | `src/prompts/service.py` | KP 示例名改 canonical（**8 处**，抽验 8/8 全 canonical） | **修 bug**（缺陷 B） |
| 3 | `src/schema/grading.py` | `feedback`/`error_analysis` 由「超长拒绝」改**截断**；`feedback` 允许缺省 | **修 bug**（缺陷 A 根治 A2 变体） |
| 4 | `src/core/settings.py` | 新增 `STRUCTURED_OUTPUT_RETRIES: int = 1` | **补能力**（缺陷 A 重试开关） |
| 5 | `src/rag/llm_calls.py` | `call_structured` 加**同 prompt 重试**（超时不重试）+ **工具标记清洗兜底** | **补能力**（缺陷 A 根治 A1+A3） |
| 6 | `src/memory/remember.py` | `_resolve_config()`：显式优先 + **运行时上下文回落** | **修 bug**（缺陷 C 根治） |
| 7 | `src/memory/topics.py` | `normalize_topic` 重写为 **canonical-aware**（①canonical 原样 → ②别名表 → ③rag 同义词（目标须 canonical）→ ④压缩空白） | **修 bug**（缺陷 D 根治） |
| 8 | `src/memory/topics.py` | **review 补修**：`deadlock` 目标 `进程死锁` → `死锁`（原目标**不可达**）；清 3 条恒等自映射死代码 | **修 bug**（缺陷 D 的同类残留） |
| 9 | `scripts/memory_step4fix_gate.py` | 新增 `⑧` KP 规范名 / `⑨` 抗格式飘移 / `⑩` context-fallback / `⑪` topic 归一（含 `⑪f` 全表断言、`⑪g` 死代码检查） | **补测试** |

> 注：本轮产品改动实际涉及 **6 个源文件**（#1–#8 中 `core/settings.py` 与 `memory/topics.py` 各出现两次）。
> 工作区另有 **6 个文件**（`agents/tools.py`、`memory/weak_topics.py`、`schema/models.py`、
> `prompts/agents.py`、`prompts/supervisor.py`、`scripts/agent_behavior_smoke.py`）
> 带的是**前轮 Phase 1/1.5 的未提交改动**，非本轮 —— review 时已逐一核对 diff 区分。

**关于缺陷 A 的修改位置**：三处收口，各司其职 ——
- prompt 侧（#1）：从源头**降低**超长概率；
- schema 侧（#3）：超长时**截断**而非丢弃整次批改（展示字段不该当事实源）；
- 调用层（#4/#5）：失败时**重试** + 工具标记**清洗兜底**。

### 关于 `max_length` 契约的显式说明（回应"schema 有 max_length ⇒ prompt 需提及"）

`schema/grading.py` 的 `feedback` **已移除 `max_length`**（改由 `field_validator(mode="before")`
截断），故当前**不存在**「schema 强制 800 而 prompt 未提及」的契约缺口。
`error_analysis` 同理。**保留的硬约束只有 `score: ge=0, le=100` 与必填字段**，
这些在 prompt 里都有对应表述。

---

## 五、新增机械护栏（全部零 LLM 成本）

`scripts/memory_step4fix_gate.py` 从 39 项扩到 **64 项**（+25；含终验 0 ❌），新增四组：

| 组 | 内容 | 关键判据 |
|---|---|---|
| **⑧** KP 规范名 | 扫 prompt/schema 里的「例如：…」示例名，与 `kp_index`（162 个 canonical）比对 | ⑧c 有非 canonical ⇒ 红 |
| **⑨** 抗格式飘移 | 截断而非拒绝 / 真错误仍拒绝 / 标记清洗 / 兜底重建 / 重试接线 | ⑨b 真错误必须仍被拒 |
| **⑩** context-fallback | 显式优先 / 上下文回落 / 无上下文不炸 / 端到端落库派生 | ⑩d 经 config 解析取 uid |
| **⑪** topic 归一 | 162 canonical 恒等 / 含空格不删 / 别名仍纠正 / **反向映射被拦** / 写入路径保序去重 / **⑪f 别名表全表 target ∈ canonical** / **⑪g 无自映射死代码** | ⑪a 有 canonical 被改坏 ⇒ 红；⑪f 有不可达 target ⇒ 红 |

**反向验证（证明护栏真能抓 bug，非永久绿）**：

| 护栏 | 破坏方式 | 是否变红 |
|---|---|---|
| ⑧c | prompt 示例名改回 `页面置换`/`Cache 映射` | ✅ 红（并指出具体名字） |
| ⑨b | — | 负例恒断言 |
| ⑩b/⑩d/⑩d'/⑩d'' | 去掉 `_resolve_config` 的上下文回落 | ✅ 4 项同时红，且精确复现原缺陷（`uid=None`→`0 条`→`[]`） |
| **⑪a/⑪b/⑪e** | **破坏①：把 canonical 判定挪到「删空白」之后** | ✅ 3 项同时红，**精确复现 21/162 被改坏**（全是含空格名） |
| **⑪a/⑪e** | **破坏②：恢复 `"页面置换算法"→"页面置换"` 别名 + 旧查表顺序** | ✅ 2 项同时红，精确报出 `['死锁','页面置换算法']` |
| **⑪c/⑪f** | **破坏③：把 `deadlock` 目标改回不可达值 `进程死锁`** | ✅ 2 项同时红，精确报出 `'deadlock' → '进程死锁'` |
| **⑪c/⑪f/⑪g** | **破坏④：注入恒等自映射 `"死锁": "死锁"`** | ✅ 3 项同时红，报出 3 条死代码 |

> ★ ⑪ 的四组反向验证**逐位复现了原缺陷**（21 个含空格名 / 2 个别名受害名 /
> 1 个不可达目标 / 3 条死代码），证明护栏不是"恒绿装饰"。
> 每次验证后均 `diff`（md5sum）确认 `topics.py` 与快照**逐位一致**。
>
> ⚠️ 过程中的一次操作失误已自查纠正：反向验证 G 时我误 `cp` 了 **P0 改动之前**的快照，
> 导致 P0 修正被瞬时覆盖（gate 报「全表 8 条」暴露异常）。已按编辑内容重新落盘，
> 并以 `md5sum` 复核落盘版本正确。**教训：备份要按「改动后」命名并即时校验 md5。**

**护栏自身踩过的坑**：⑧ 首版正则按「行」匹配，而 Python 长字符串**跨行拼接** ⇒
只抽到 4/8 个示例名，注入非 canonical 名时**没变红**。修正为「先归一化引号+换行再匹配」后，
抽取覆盖 8/8、注入即红。

---

## 六、剩余待办

### 待重跑 Step 5（建议）

4 个缺陷已修，但**首轮的 ON/OFF 数字全部受污染**，需重跑才能得到有效对照。
重跑前建议先确认：`⑩` + `⑪` 组护栏全绿（保证「落库链路通 + KP 名不被改坏」）
+ 用 `--dry-run` 估算调用量。

### 待用户裁决

1. **`STRUCTURED_OUTPUT_RETRIES` 默认值**：现为 `1`（成本 +最多 1 次失败调用）。
   若希望更稳可设 `2`；若严格控制成本可设 `0`（但截断修复后 `0` 也已 10/10）。
2. **provenance**：本轮改动含产品行为变更（prompt / schema / remember / llm_calls / topics / settings）。
   按用户指示**不得回写 Phase 0B 冻结基线**；若纳入 Phase 1 应形成新 provenance。

---

## 七、附带发现（已处理）

1. ✅ **canonical 示例名的一致性** —— 已加 `⑧` 机械护栏（扫全库 prompt/schema）。
2. ✅ **`normalize_topic` 的 canonical 保护** —— 已加 `⑪` 机械护栏（全量 162 名恒等 + 反向映射负例）。
3. ⚠️ **`compute_weak_topics` 的 `'str' object has no attribute 'score'`** ——
   **复核结论：不是产品缺陷**。直接探针复现失败，真实链路 `record_grade → arecent_episodes
   → compute_weak_topics` 全程正常（`asearch` 返回 dict、`coerce_episode` 正常收成 Episode）。
   该报错来自**早期探针脚本自身**：把 `store.asearch` 的 `SearchItem` 列表或裸字符串直接
   传给了 `compute_weak_topics`。**产品代码无需改动**。
4. ⚠️ **`agents/tools.py` 的 `config` 参数仍暴露在 `tool_call_schema`** ——
   现因 `_resolve_config` 回落已**不影响功能**，但模型仍会看到一个无用的 `config` 参数。
   建议后续加 `Annotated[..., InjectedToolArg]` 把它从 schema 移除（本次未改，避免扩大改动面）。
5. ℹ️ **全库扫描非 canonical 名的残余**：`AVL树` / `图论` 的其余出现位置均为
   注释、反例、同义词映射表、检索关键词（`rag/recall.py:408` 的 `"图论"` 是**检索关键词**，
   用途与 KP 聚合不同）⇒ **无需改动**。

---

## 八、第二轮 review 新发现（**兜底逻辑自身引入的缺陷** —— 已修复）

> ★ 性质说明：以下 3 条**不是** Step 5 首轮暴露的，而是**上轮为修缺陷 A 而新增的兜底逻辑
>   （`_try_kv_dict` / `_salvage_from_raw`）自身带来的**。首轮数据**无法证伪它们**
>   （首轮日志中「批改失败」0 处 —— 失败表现为 `case_invalid`，从未走到兜底路径）。
>   ⇒ 这说明：**修复代码本身也需要独立的边界测试，不能只依赖「修完后真跑通过」。**
>
> **状态：3 条已全部修复**（`_try_kv_dict` 重写），并补 `⑨g`/`⑨h`/`⑨i`/`⑨j`/`⑨k` 五项护栏。

### D2-1（严重）`is_wrong` 语义**反转**：白名单外字段污染上一字段

`_try_kv_dict` 只认 `_KV_SCALAR_FIELDS = {score, feedback, is_wrong, error_analysis}`。
遇到**白名单外的行**（`knowledge_points:` / `topic:` / `reason:` / 甚至 `# 备注`）时，
它会走 `elif current is not None:` 分支，把该行**拼接进上一字段的值**：

```python
# 输入
'score: 55\nfeedback: 有遗漏\nis_wrong: true\ntopic: 平衡二叉树'
# 内部得到
is_wrong = "true\ntopic: 平衡二叉树"     # ← 被污染
# 判定
"true\ntopic: ...".strip().lower() in {"true","1","yes","是"}  →  False
```

**实测可达**：

```
输入 is_wrong=true, score=55  →  兜底结果 is_wrong=False, score=55
                                  ↑ score<60 却说「没错」—— 语义反转
```

**危害**：不是丢失而是**反转**。`is_wrong` 与 `score` 直接打架，且该值会写进 episode。
触发面**宽**（任何 `is_wrong` 之后的非白名单行）。**现有护栏 `⑨d` 只断言 `score`，不会变红。**

### D2-2（严重）首行有前言 ⇒ **整条兜底全盘放弃**

`_try_kv_dict` 的首行若非 `key:` 形态，直接 `return None`（连已解析的字段一起丢）：

```
'好的，批改如下：\nscore: 40...\nis_wrong: true'  →  None   （连 score 都救不回）
'\n\nscore: 40...'                                →  None   （前置空行同样致死）
'Let me grade this.\nscore: 40...'                →  None
```

**危害**：模型飘移时的典型形态恰是「前面带一句话」—— 实测日志里就有 `Let's output.`。
**兜底在最需要它的场景下失效**。注意 `_salvage_from_raw` 有「首行必须是 key」的隐含前提，
但上游模型输出**没有这个保证**。

### D2-3（中）`knowledge_points` 不在兜底白名单 ⇒ 静默丢失

`GradingResult` 有 5 个字段，白名单只有 4 个（缺 `knowledge_points`）。后果：

- 走兜底成功时，`knowledge_points` 走 schema 默认值 **`[]`**（静默丢失）；
- 与 **`allow_legacy_fallback=False`**（Phase 1.5 评测要求）叠加 ⇒ 该 episode **不参与聚合**；
- 极端情况：「救回了批改，却丢了 KP」⇒ `weak_topics` 少一条命中。

### 修复（已完成）

`_try_kv_dict` 重写为三条**顺序敏感**的规则（`src/rag/llm_calls.py`）：

```
┌─ ① 扫描定位起点 ──────────────────────────────────────────
│  逐行扫，**遇到第一个合法字段 key 才开始解析**。
│  之前的行（前言/空行/解释文字）一律忽略 —— 但不是「所有非 key 行都忽略」，
│  而是「进入解析前忽略、进入解析后按 ② 处理」，避免把真正的异常输出静默吞掉。
├─ ② 续行规则（严格） ─────────────────────────────────────
│  非 key 行**仅当**当前字段 ∈ `_KV_MULTILINE_FIELDS`（feedback / error_analysis，
│  它们本来就是多行文本）时，才作为**续行**并入上一字段；
│  否则**直接丢弃该行**（绝不拼进 is_wrong / score / knowledge_points）。
└─ ③ 字段分类解析 ─────────────────────────────────────────
   scalar（score / is_wrong / feedback / error_analysis）按标量语义；
   list（knowledge_points）按**分隔符切分**（顿号/逗号/分号/换行）为 list[str]，
   绝不把整个字符串硬塞进 list 字段。
```

字段分类显式化（不再让 `_KV_SCALAR_FIELDS` 承担「全部字段」概念）：

| 集合 | 内容 |
|---|---|
| `_KV_SCALAR_FIELDS` | `score` / `feedback` / `is_wrong` / `error_analysis` |
| `_KV_LIST_FIELDS` | `knowledge_points` |
| `_KV_ALL_FIELDS` | 上面两者之并（= schema 全部 5 字段） |
| `_KV_MULTILINE_FIELDS` | `feedback` / `error_analysis`（**仅这两个允许续行**） |

**验证**（修复前 → 修复后）：

| 用例 | 修复前 | 修复后 |
|---|---|---|
| `is_wrong: true` 后接 `topic:` / `知识点:` / `reason:` / `# 备注` | `False`（**反转**） | `True` ✅ |
| 首行 `好的，批改如下：` / `Let me grade this.` / 前置空行 | `None`（**全盘放弃**） | 正确解析出 `score` ✅ |
| `knowledge_points: 平衡二叉树、二叉排序树` | 丢失 / 污染上一字段 | `['平衡二叉树','二叉排序树']` ✅ |
| 多行 `feedback`（续行） | 可续行但会污染 is_wrong | 续行正常**且**不污染 ✅ |

### 护栏补强（已完成）

| 护栏 | 判据 |
|---|---|
| `⑨d-全字段` | 兜底结果**每个字段**都正确（原来只断言 `score` ⇒ 漏检 D2-1/D2-3） |
| `⑨g` | `_KV_ALL_FIELDS` 必须**覆盖 schema 全部字段**（漏一个 ⇒ 红） |
| `⑨h` | 首行前言/空行 ⇒ 仍解析出 `score`（防 D2-2 回归） |
| `⑨i` | `is_wrong` 不被后续非 key 行污染（防 D2-1 回归） |
| `⑨j` | 多行字段续行仍生效且不污染 `is_wrong` |
| `⑨k` | `knowledge_points` 按 list 解析（非硬塞字符串） |

**反向验证**（回注三个缺陷）：`⑨g` / `⑨h` / `⑨i` / `⑨k` **四项同时变红**，
且各自精确报出缺陷 —— `⑨g` 报 `缺失: ['knowledge_points']`、
`⑨h` 报 `失败: 3`、`⑨i` 报 `被污染: 4 例`。
（`⑨j` 仍绿：职责不同 —— 旧行为对 feedback 续行仍生效，污染问题由 `⑨i` 负责。）

### ⚠️ 遗留边界（**需用户裁决，未改**）

`_salvage_from_raw` 的入口守卫 `if cleaned == raw: return None` 意味着
**「无工具标记 ⇒ 不兜底」**（由 `⑨d'` 明确断言，是**有意设计**：避免把正常自然语言散文
硬塞进 schema）。但它留下一个能力边界：

```
有标记 + 裸KV  → 兜底 ✅（含前言/多行/KP）
有标记 + JSON  → 兜底 ✅
无标记 + 裸KV  → 不兜底 ⚠️ ⇒ 报错 ⇒ 批改失败
```

问题是：模型飘移出的裸文本**不一定带 `<parameter=...>` 标记**（实测存在干净裸文本
`score: 40\nfeedback: ...`）。这类场景会让批改失败。
**是否放宽该守卫（如「裸文本且能解析出必填字段 ⇒ 也兜底」），需用户决策** ——
放宽会增加「把散文误当结构化输出」的风险，故本次未动。

---

# 附录 · 重跑（缺陷 A/B/C/D 修复后）与缺陷 E

**重跑时间**：2026-10-06T21:44–21:50（耗时 5m52s，exit=0）
**产物**：`PHASE1_MEMORY_STEP5_20261006_2144.md`、`phase1_memory_step5_store_{on,off}.jsonl`
**旧产物（缺陷修复前）**：`*_pre_fix_20261006_2023.jsonl`（数据保留）；
其配套报告 `PHASE1_MEMORY_STEP5_20261006_2014_pre_fix.md` 已随过程文档一并移入回收站。

## 一、旧产物为何不可作基线（已核实）

| 证据 | 内容 |
|---|---|
| ① 工具调用缺失 | `mem-001` A 段 2 个批改回合，`grade_scores` **仅 1 条**，`tool_calls=[]` ⇒ 第 2 次批改**未发生工具调用**（缺陷 C 表征） |
| ② B 段是拒答 | 最终回复逐字为「我无法知道你的薄弱知识点——知识库中没有你的学习记录…」 |
| ③ 分数未解析 | `mem-003` `grade_scores=[None,100.0]`，`validity_reason=第 1 次批改得分未能解析` |
| ④ 平凡通过 | `mem-005` 唯一 valid 且 `recalled_pass=True` —— B 段什么都没记住，恰好与「不该召回」对齐，**不构成能力证据** |

⇒ 旧产物中「memory card=0 / recalled_actual=0」**不可读作「Store 不起作用」**，
只是「A 段没写成 ⇒ B 段自然无卡」的必然后果。**用它当基线会得出方向性错误结论。**

## 二、重跑结果（配对对照）

| 指标 | Store ON | Store OFF | 差值 | 期望 | 判定 |
|---|---|---|---|---|---|
| case 数 | 6 | 6 | — | 相同 | ✅ |
| 有效 case（valid≠False） | **6** | 2 | +4 | — | ON 组全有效 |
| **有 memory card 的 case** | **1** | **0** | **+1** | ON>OFF | ✅ 对照干净 |
| **recalled_actual=True** | **1** | **0** | **+1** | ON≥OFF | ✅ 无旁路 |
| recalled_pass=True | 4 | 2 | +2 | — | — |
| used=True | 2 | 0 | +2 | — | ✅ |
| correct_use=True | 2 | 0 | +2 | — | ✅ |

### 逐条（Store ON）

| case | validity | A段得分 | 批改次数 | card数 | recalled_actual | pass | 期望召回 |
|---|---|---|---|---|---|---|---|
| mem-001 | True | [0.0, 0.0] | 2 | **1** | **True** | **True** | True |
| mem-002 | True | [0.0, 0.0] | 2 | 0 | False | False | True ❌ |
| mem-003 | True | [0.0, 40.0] | 2 | 0 | False | False | True ❌ |
| mem-004 | True | [0.0] | 1 | 0 | False | True | False ✅ |
| mem-005 | True | [] | 0 | 0 | False | True | False ✅ |
| mem-006 | True | [100.0, 100.0] | 2 | 0 | False | True | False ✅ |

### 相比旧跑的三项实质改善

1. **A 段批改链路通了**：ON 组 6/6 全部 `valid`（旧跑仅 1/6）。`mem-001`/`mem-002` **两次批改都成功**（旧跑只有 1 次）⇒ **缺陷 A + C 已确证修复**。
2. **跨会话召回首次成立**：`mem-001` 记忆卡逐字为 `【学生记忆】\n薄弱：平衡二叉树`，且 B 段回复开头即「**薄弱点：平衡二叉树（AVL）**」⇒ `used=True`、`correct=True`。这是**修复后链路端到端打通的第一个正证据**。
3. **paired control 对照干净且有意义**：OFF 组 0 卡 0 召回，ON 组 1 卡 1 召回 ⇒ 「召回确实来自 Store」由机械对照确立。

### 清理契约：已独立验证生效（负面结论也有价值）

本节原本担心「Store 清理没生效、数据在 case 间串味」。**三项实验证明清理是好的**：

| 实验 | 结果 |
|---|---|
| `run_sessions` 单条最小 case 并回读 `notes` | `跑前清理：删除 0 项` → `跑后清理 Store：删除 1 项` → 跑后残留 episode = **0**、`weak_topics=[]` |
| 重跑 `mem-001` 前后比较 `mem-*` 残留计数 | 跑前 6 → 跑后 **6（未增加）** ⇒ 本次运行**零泄漏** |
| `store.db` 中残余行的 `created_at` | 全为 13:47–13:49，属**更早运行的历史残骸**（早期版本跑后清理尚未补齐） |

⇒ **「Store ON 记住了什么」这一测量本身是可信的**，paired control 的有效性不受污染。
（同时也提醒：**库中同名前缀行数 ≠ 本次运行写入数**，因 `user_id` 带随机后缀、跨运行不复用。
详见第四节。）

## 三、★ 新缺陷 E：批改产出的 KP 名不是 canonical ⇒ 召回被系统性抑制

**性质**：真实产品缺陷（**与 A/B/C/D 均不同**，是**第五个**独立缺陷）
**位置**：LLM 产出 `knowledge_points` 的**上游**——即 prompt 未约束产出必须是 canonical name；
`normalize_topic`（缺陷 D 已修好）无法把它「救」回 canonical。
**影响**：正样本召回率被压到 **1/3**。
**独立复现**：直接探针 `record_grade(knowledge_points=['图的基本性质','握手定理'])` ×2
⇒ `weak_topics = ['图的基本性质', '握手定理']`（**自由文本原样入库**，与 gold 期望的 `图` 无关）。

### 证据（直接查 `store.db`，非推断）

| case | gold 期望 KP | LLM 实际写入 `knowledge_points` | 命中 |
|---|---|---|---|
| mem-001 | `平衡二叉树` | `平衡二叉树` ✅、`AVL树的插入与调整` ❌ | 1/2 |
| mem-002 | `图` | `图的基本性质` ❌、`握手定理` ❌ | **0/2** |
| mem-003 | `排序` | `堆的定义` ❌、`完全二叉树` ✅* | 0/2 |
| mem-004 | `平衡二叉树` | `平衡二叉树` ✅、`二叉树性质与计数` ❌ | 1/2 |
| mem-006 | `图` | `图的存储结构` ❌、`简单路径与回路` ❌、`拓扑排序` ✅* | 0/3 |

\* `完全二叉树`/`拓扑排序` 确是 canonical，但**与 gold 期望的 `排序`/`图` 不同名** ⇒ 聚合时是**另一个桶**，不补充期望桶的 hit 数。

`normalize_topic` 对这些自由文本的实测返回值（四步规则**全不命中**，故原样返回）：

```
'图的基本性质'    -> '图的基本性质'     canonical=False
'握手定理'        -> '握手定理'         canonical=False
'堆的定义'        -> '堆的定义'         canonical=False
'图的存储结构'    -> '图的存储结构'     canonical=False
'简单路径与回路'  -> '简单路径与回路'   canonical=False
'AVL树的插入与调整'-> 'AVL树的插入与调整' canonical=False
```

### 机制（为什么必然导致不召回）

```
LLM 产出 '图的基本性质'（自由文本）
  → normalize_topic：不是 canonical、不在别名表、无 rag 同义词 ⇒ 原样返回
  → compute_weak_topics：每个自由文本各成一个桶，各计 1 hit
  → MIN_HITS=2 要求同名累计 2 次，但两条 episode 的自由文本**互不相同**
  → weak_topics = []  ⇒ 记忆卡为空 ⇒ recalled_actual=False
```

⇒ **这不是阈值问题，也不是归一化问题（D 已修），而是「上游产出的词表与 kp_index 不同源」**。

### 与既有结论的关系（重要，避免夸大）

- **不能推翻**缺陷 B 的修复：`GRADE_PROMPT` 示例名改成 canonical 后，模型**部分**跟随
  （`平衡二叉树`/`拓扑排序`/`完全二叉树` 已产出 canonical），说明 prompt 约束**有效但不足**。
- **缺陷 B 属「示例诱导」，缺陷 E 属「无强制词表」** —— B 是 E 的一个已修子集，E 是剩余部分。
- 旧 findings 里 `AVL树 → 平衡二叉树` 的「**rag 兜底成功案例**」结论**依然成立**（`normalize_topic('AVL树')` 确实返回 `平衡二叉树`）；但**本例说明 rag 兜底的覆盖面远小于需要**：`AVL树的插入与调整` 就不在兜底范围。

## 四、~~`mem-002` 写入丢失~~ —— **已排查，判定为「非缺陷」（撤回）**

> **本节结论已撤回。** 初版据此推断「`ToolMessage` 捕获 2 次批改、Store 只落 1 条 ⇒ 写入丢失」。
> 经三项独立实验，**该推断不成立**，记录于此以免后人重蹈。

### 当时的观察与误判

`store.db` 中 `mem-002` 只有 1 条 episode，而 `grade_scores` 记了 2 次 ⇒ 被读作「写入丢失」。

### 三项排查（全部否定该推断）

| 实验 | 结果 | 排除的假设 |
|---|---|---|
| ① 直接探针 `record_grade` ×2（DEBUG 级日志） | 两次均成功，耗时 **611ms / 310ms**（远低于 `MEMORY_WRITE_TIMEOUT=1.5s`），**2 次调用 ⇒ 2 条 episode** | **写入超时/失败**不成立 |
| ② `run_sessions` 单条最小 case（含 `notes` 回读） | `跑后清理 Store：删除 1 项`，跑后残留 episode = **0**、`weak_topics=[]` | **清理契约失效**不成立 |
| ③ 重跑 `mem-001` 并比对跑前后残留计数 | 跑前 `mem-*` = 6、跑后 **仍 = 6**（未增加）；`eval-mem-001-b352c543` 依旧是同一批旧记录 | **本次运行泄漏**不成立 |

### 真正原因

`store.db` 里那 6 条 episode 的 `created_at` 全在 **13:47–13:49**。
它们**不是本次 ON/OFF 组留下的**（本次每组的 `user_id` 带随机后缀，且已在各自 `finally` 中被清掉），
而是**更早运行的残骸**：早期版本 `run_sessions` 的跑后清理尚未补齐，故旧数据一直留在库里。

⇒ 判据：**「同名前缀的行数」不能当作「本次运行的写入数」** —— `make_user_id` 每次带随机后缀，
不同次运行的 `user_id` **永不复用**，库里同名 case 的行可能来自任意历史运行。
要断言「本次写了几条」，必须**记跑前/跑后计数差**，而非看总量。

### 附带暴露的真实不稳定（需记录）

同一 `mem-001` case，三轮运行的 A 段批改次数分别是：

| 轮次 | A 段批改次数 | `validity` |
|---|---|---|
| ON 组（重跑主轮） | 2 | True |
| OFF 组 | 2 | False（第 2 次得分 100 越界） |
| 单条复跑（本次排查） | **1** | False（`1 < 下限 2`） |

⇒ **「A 段能否凑够 2 次批改」本身不稳定**（取决于 supervisor 是否把第二题也路由到 `grading_agent`）。
这是 **case 前置条件与 LLM 路由随机性** 的交互，**不是产品缺陷**；
但意味着 `case_invalid` 会在重跑间波动，报告须按**每次运行实际的有效样本**计算，不可跨轮混用分母。

## 五、`mem-003` / `mem-006` 的「黄金集假设漂移」风险（未触发，但需标注）

重跑中两条**均 `valid=True`**，故本次**未**复现 `case_invalid`。但：

- `mem-003` 第二次批改给 **40 分**（旧跑给了 100 分）—— 同一题的判分在两次运行间**差 60 分**；
- `mem-006` 两次都给 **100 分**（符合 `[60,100]` 期望）。

⇒ 判分**跨 run 不稳定**。若某次运行恰好给出界外分数，该 case 即 `case_invalid`。
**性质是「黄金集假设与 LLM 判断的漂移」，不是产品失败**，报告中须单列，
且**不得**把这类样本计成「不召回」。

> **provenance 再声明**：本轮结论基于含 6 个源文件产品改动的代码，
> **不得回写 Phase 0B 冻结基线**。
