# Retrieval Layer 设计（L3 检索层）

> 状态：**设计定稿**（2026-09-28 设计通过；D1–D7 全部冻结）  
> 前提：数据层已冻结（KP / L1 Basic / L2 Advanced / L3 Exams / gap inventory）  
> 定位：在现有多路召回管线上增加 **task_mode / eligibility / ranking / release / retrieval_policy**，不推倒重来。  
> 分册关系：本册管「怎么检、检什么、不漏什么」；**策略契约见 `RETRIEVAL_POLICY.md`**；`RETRIEVAL_PLAN.md` 仍管现有管线调优与「不做清单」。

---

## 0. 一句话

**数据层说「有什么」；Retrieval Layer 说「用户这个任务该看到什么、不该看到什么」。**

```text
用户问题
        ↓
Task Classifier → retrieval_policy（机器可执行）
        ↓
Candidate Eligibility（安全前置 where/路由）
        ↓
Retrieval / Layer Weight / Rerank
        ↓
Evidence Release Policy
        ↓
Evidence Pack → LLM / 专家 Agent
```

---

## 1. 与现状的边界

| 资产 | 现状 | 本设计 |
|---|---|---|
| 多路召回 / RRF / 阈值 / HyDE | 已落地且有门禁 | **沿用**，不在本册改权重配方 |
| `depth` shallow/standard/deep | 查询长度/复杂度分层 | **沿用**（管线深度 ≠ 知识层 L1/L2/L3） |
| `kb_depth` / `doc_role` | 已入库，检索几乎不消费 | **本册核心：消费它们** |
| 任务模式（练习/批改/讲解） | 未统一进检索 | **本册新增** |
| 集合 `questions` | L3 在用（alias） | 读侧兼容；收口见数据层 D5 |

**★ 命名消歧（冻结建议）**：

```text
depth = shallow | standard | deep     管线深浅（计算预算）
L1/L2/L3 = basic | advanced | exams   知识层（内容职责）
```

两套概念不得混称「一级/二级检索」。

---

## 2. 任务模式（D1 已定方向）

检索入口必须声明 **task_mode**，**默认 `learn`**。

| task_mode | 核心问题 | 例 |
|---|---|---|
| **`learn`** | 理解知识 | 「什么是死锁？」 |
| **`method`** | 学习怎么做题 | 「BST 删除怎么做？」 |
| **`practice`** | 生成/展示练习题 | 「给我一道 BST 练习题」 |
| **`grade`** | 批改学生作答 | 「学生答案是…请批改」 |
| **`explain`** | 解释某道题/答案/解析 | 「2019-Q11 为什么选 B？」 |
| **`verify`** | 验证某知识点是否被真题考过 | 「BST 删除考过哪些真题？」 |

### 2.0 ★ explain vs verify 边界（冻结）

```text
explain  对「某一道题」解释对错/步骤/答案   （有 question_id 或明确题面）
verify   对「某个知识点」查历史真题         （KP → assesses 列表）

「BST 删除怎么做？」           → method
「2019 这道 BST 为什么选 B？」  → explain
「BST 删除考过哪些真题？」      → verify
```

| | explain | verify |
|---|---|---|
| 输入锚点 | 具体题（年/题号/题面） | 知识点 / 方法名 |
| 输出 | 那道题的讲解 | 该点被考过的题列表/形态 |
| L3 用法 | 展开该题 items+answer | 列 `assesses` 真题，可给题干摘要 |

### 2.0.1 默认模式与路由（冻结方向）

```text
default task_mode = learn
```

| 检测信号 | 切换 |
|---|---|
| 「怎么做 / 步骤 / 怎么解」 | `method` |
| 「练习题 / 给我一道 / 出题」 | `practice` |
| 「批改 / 学生的答案是」 | `grade` |
| 「为什么选 / 解析 / 为什么是 X」**且**有年/题号或题面 | `explain` |
| 「考过吗 / 有哪些真题 / 是否考过」 | `verify` |

**为何默认 learn 而非 explain**：通用问答入口不应默认放开 L3 答案/解析进证据包；权限按需升级。

### 2.1 答案 / 解析 / 真题展开裁剪（冻结方向）

| task_mode | item 正文 | `answer_key` | `reference_answer` | `answer` chunk | `related_exams` / 具体 `question_id` |
|---|---|---|---|---|---|
| `learn` | ✓ | ✗ | ✗ | ✗ | ✗ |
| `method` | ✓ | ✗ | ✗ | ✗ | ✗ |
| `practice` | ✓ | **✗** | **✗** | **✗** | **✗** |
| `grade` | ✓ | ✓ | ✓ | 按 `explanation_status` | 题号可 |
| `explain` | ✓ | ✓ | ✓ | ✓ | ✓（目标题） |
| `verify` | 摘要/题干可 | ✗（列表态） | ✗ | ✗ | ✓（列表，非展开答案） |

### 2.2 ★ practice 防泄题（冻结方向）

`practice` 允许：

- KP 概念名  
- L1 原理 / L2 方法（可作**出题素材**，不作标准答案）

`practice` **禁止**：

| 禁止项 | 原因 |
|---|---|
| 展开具体 `question_id`（如 `2019-Q2`） | 「给我一道练习」不能吐真题原题编号 |
| `related_exams` 弱链 | 同上 |
| KP → `assesses` → question 自动展开 | 图扩不得在 practice 泄题 |
| `answer_key` / `reference_answer` / `answer` chunk | 练习无答案 |

```text
「给我一道 BST 练习题」
  → 可用 L2 方法结构 + KP 出新题
  → 不得给出：2019-Q2、答案 B、真题全文
```

**实现**：`practice` 下 `assesses` 图扩整段关闭；证据剥离 `question_id`/答案字段；缓存键隔离。

### 2.3 决策点 D1（已定方向，待确认收口）

| 项 | 结论 |
|---|---|
| 枚举 | 保留六模式，职责按 §2 |
| 默认 | **`learn`** |
| explain vs verify | 题目解释 vs 知识点考过什么 |
| practice | 隐藏 `related_exams` + 禁 `assesses` 展开 + 无答案 |

---

## 2b. Retrieval Policy（★ 决策 D7 — 建议采纳）

### 2b.1 动机

Agent/工具不应各自理解「method 该搜什么」。  
检索层先产出**机器可执行策略**，下游只执行。

### 2b.2 契约（草案）

```yaml
retrieval_policy:
  task_mode: method
  preferred_layers: [advanced, basic]
  excluded_layers: []          # 或 null
  answer_policy: hidden        # hidden | released
  explanation_policy: hidden   # hidden | released | verified_only
  related_exam_policy: weak    # off | weak | strong
  kp_expansion: enabled        # enabled | disabled
  graph_expansion: disabled    # V1 恒 disabled
  depth: standard              # 管线深浅（与知识层分离）
  layer_policy_id: experiment.v1
```

由 **Task Classifier**（规则+可选 LLM）生成；**不是**让 LLM 现场编。

### 2b.3 与本项目 LangGraph 的接口（【代码】对齐）

现状：

```text
teaching_graph: START → load_memory → supervisor → END
supervisor: knowledge_agent / question_agent / grading_agent
tools: aknowledge_search / atext_search
        → aretrieve_evidence_with_retry(query, depth, use_rerank)
query_classifier: RetrievalDepth(shallow|standard|deep|code|text_only)
```

建议落点：

```text
用户问题
   ↓
Task Classifier          （可挂 supervisor 前，或工具入口解析）
   ↓
Retrieval Policy         （类型化对象，进 state / tool kwargs）
   ↓
Retriever                （eligibility where + 路由）
   ↓
Layer Weight + Rerank
   ↓
Evidence Policy          （release 裁剪）
   ↓
Evidence Pack
   ↓
LLM / 专家 Agent
```

| LangGraph 位置 | 放什么 |
|---|---|
| `teaching_graph` 或 supervisor 入口 | Task Classifier → `retrieval_policy` 写入 state |
| `agents/tools.py` `_retrieve_payload` | 读 policy：`depth` / eligibility / 图扩开关 |
| `rag/retriever.py` | 接受 policy（或已拆好的 eligibility+ranking 参数） |
| Evidence Policy | 读 `answer_policy` / `explanation_policy` |

与现有映射（初稿）：

| 专家 | 典型 task_mode | preferred_layers |
|---|---|---|
| knowledge_agent | `learn` / `method` | basic / advanced |
| question_agent | `practice` | advanced（出题素材）+ basic |
| grading_agent | `grade` / `explain` | exams + advanced |

**好处**：LangGraph 节点只传 `retrieval_policy`，不再把「搜哪层、有无答案」散落在 prompt 与工具 docstring 里。

### 2b.4 与 eligibility / release 的关系

```text
retrieval_policy.task_mode
   → eligibility 规则表（exam_resources.question/answer/paper）
   → ranking（preferred_layers + layer_weight profile）
   → release（answer_policy / explanation_policy）
```

Policy 是**单一真源**；三类规则从它派生，禁止多处手写模式表。

### 2b.5 决策点 D7（建议采纳）

| 项 | 结论 |
|---|---|
| 是否要 `retrieval_policy` | **建议是** |
| 产生 | Task Classifier（规则优先） |
| 消费 | tools → retriever → Evidence Policy |
| LangGraph | state 携带；专家不再自解释检索范围 |

---

## 3. 层偏好与路由（D2 已定方向）

### 3.1 query → 层偏好（soft，非硬路由）——架构冻结

```text
真实问题常跨层 ⇒ soft preference，不是「方法题只搜 advanced」
```

例：「TLB 缺页时地址转换」→ L1 原理 + L2 计算 + L3 类似真题 都要。

```text
概念/原理/是什么     → 偏 L1 basic
怎么做/方法/步骤/易错 → 偏 L2 advanced
真题/某年/第N题/答案  → 偏 L3 exams
综合/大题/证明        → L1+L2+L3 都要
```

| 信号 | 偏好 |
|---|---|
| 「定义 / 原理 / 为什么 / 区别」 | L1 ↑ |
| 「怎么做 / 步骤 / 判定 / 计算 / 模板」 | L2 ↑ |
| 「真题 / 2019 / 第 11 题 / 答案」 | L3 ↑ |
| `related_exams` / `question:` 命中 | L3 强 |

**禁止**硬路由：「方法类 query → 只查 advanced」。

### 3.2 layer_weight ——机制冻结，**系数不冻结**

```text
score' = score × layer_weight(kb_depth | task_mode, query_class)
```

| 层 | 说明 |
|---|---|
| **架构协议** | 必须存在 soft 加权；维度 = `kb_depth × task_mode`（可再乘 query_class） |
| **配置** | `layer_weight.basic / advanced / exams / legacy` 全部 **configurable** |
| **实验** | 数字只存在于 experiment profile，**不进架构文档** |

```yaml
# 仅示例：实验配置，不是协议
layer_weight:
  basic: configurable
  advanced: configurable
  exams: configurable
  legacy: configurable

experiment:
  v1:
    method:
      basic: 0.8
      advanced: 1.2
      exams: 0.7
  v2:
    learn:
      basic: 1.0
      exams: 0.5
```

**为何系数不进协议**：

- 不同召回路（semantic / BM25 / meta）的 score **天然不可比**，先乘层权会放大错序  
- 权重必须 A/B + `retrieval_gate` 实测后才能冻结某一 profile  
- 架构只保证「可按层偏置」，不保证「0.8/1.2 是对的」

**合法/非法**：

| | |
|---|---|
| ✓ | 实验目录下改 profile、对照基线、出报告 |
| ✗ | 把 1.2 写死进 retriever 当真理 |
| ✗ | 无实验数据就宣称某系数为「标准」 |

### 3.3 硬过滤（建议；与加权正交）

| 规则 | |
|---|---|
| `practice` | `doc_role=exam_answer` 整路丢弃；item 答案字段剥掉；禁 `assesses` 展开 |
| `learn` | `doc_role∈{exam_answer}` 降权或丢弃 |
| 所有模式 | `gap_status=missing` 且无题干 → 不进池 |
| 所有模式 | `figure_status=missing` → 保留但标记 |
| `explain` 要求完整解析 | 优先 `explanation_status=verified`，`scan` 强制提示 |

### 3.4 决策点 D2（已定方向）

| 项 | 结论 |
|---|---|
| 机制 | **soft 加权**（禁止硬路由到单层） |
| 系数 | **不冻结**；`layer_weight` 可配置 |
| 实验 | `experiment.vN` profile + 门禁对照 |
| legacy | `kb_depth` 空的旧讲义 → `legacy` 档，权重可配 |

---

## 4. KP / 关系增强（D3 已定方向）

### 4.1 V1：单跳定向（架构冻结）

```text
query → KP 匹配 → 对应层定向召回
```

| mode | 图边 | 拉什么 |
|---|---|---|
| `learn` | KP `teaches` | L1 section |
| `method` | KP `trains` | L2 section |
| `verify` | KP `assesses` | 真题列表（题干摘要；按模式裁答案） |

例：

```text
method
  → ds.tree.bst
  → trains
  → L2 BST methods
```

**V1 做**：query → KP → **一层边**定向加权/加路。  
**V1 不做**：多跳展开。

### 4.2 V2 起才考虑的多跳（明确排除 V1）

```text
KP → parent → siblings → related KP
   → assesses → related exams → L1 …
```

| 禁止（V1） | 原因 |
|---|---|
| parent / children 自动上浮下钻 | 检索范围膨胀 |
| siblings / related KP | 噪声 |
| KP→assesses→L2/L1 再回流 | 多跳无界 |
| assesses 全量铺进 method/learn 证据 | 泄题 + 稀释 |

**V1 红线**：最多 **query → KP → 单跳目标层**。

### 4.3 `related_exams`（弱导航，非核心召回）

```text
L2 section ──related_exams──→ question   弱关联导航
question   ──assesses───────→ KP         核心关系（真源）
```

| | |
|---|---|
| **是** | L2 页上的「推荐真题案例」导航；`verify`/`explain` 可点进 |
| **不是** | 核心召回关系；不能取代 `assesses` |
| 权重 | 补充证据 RRF **≤ 0.5**（可配）；`practice` 下整段关闭 |
| 冲突 | 与 `assesses` 不一致时以 **`assesses` 为准** |

### 4.4 决策点 D3（已定方向）

| 项 | 结论 |
|---|---|
| KP 图扩 | **V1 单跳**；多跳 **V2** |
| 核心关系 | `question ──assesses──→ KP` |
| `related_exams` | 弱导航；非核心；practice 禁用 |

---

## 5. 证据契约与 Evidence Policy（D4 已定方向）

### 5.0 ★ 组件边界（冻结方向）

```text
Retriever
   ↓
Candidate Results     ← 含完整 metadata（索引原样）
   ↓
Evidence Policy       ← 唯一的权限/裁剪边界
   ↓
Evidence Pack
   ↓
Agent
```

| 组件 | 职责 | 不做什么 |
|---|---|---|
| BM25 / Vector / RRF / Reranker | 打分与排序 | **不**判断「这个模式能不能看答案」 |
| **Evidence Policy** | 按 `task_mode` 裁 content/metadata、置 flags | 不改索引、不改召回配方 |
| Agent | 按 flags 说话 | 不绕过 Policy 自行补答案 |

**禁止**：让多路召回/Reranker 各自实现一套答案权限。

### 5.1 不从索引删答案

```text
索引           answer_key / reference_answer 始终在
retrieval result
   ↓
Evidence Policy
   ↓
answer_released=false   （practice / learn / …）
   ↓
content/metadata 裁剪后才进 Evidence Pack
```

| | |
|---|---|
| ✓ | Policy 层剥离字段；`explain` 仍拿同一 answer asset |
| ✗ | 为 practice 从 Chroma 删答案 |
| ✗ | 两套索引（有答案库/无答案库） |

### 5.2 Evidence Pack

```text
Evidence
├── content          已按 task_mode 裁剪
├── metadata
│   ├── kb_depth / doc_role / section_id / chunk_id
│   ├── question_id / exam_year          （L3）
│   ├── answer_key / reference_answer    （仅 answer_released）
│   ├── explanation_status / figure_status
│   ├── completeness / gap_status
│   └── source_type / credibility
└── flags
    ├── layer: L1|L2|L3|legacy
    ├── answer_released: bool
    ├── explanation_released: bool
    ├── figure_missing: bool
    └── explanation_unverified: bool     （scan）
```

**Agent 约束**：

| flag | 行为 |
|---|---|
| `figure_missing` | 「该题包含图，但知识库缺失题图」 |
| `explanation_unverified` | 「解析未经人工校验」 |
| `answer_released=false` | 禁止输出答案键 |
| `credibility=low` | 不作标准答案 |

### 5.3 ★ 语义缓存隔离（冻结：安全边界，不只是性能）

**必须隔离**。缓存 key 至少包含：

```text
cache_key = f(
  query,
  task_mode,
  depth,
  layer_policy      # layer_weight profile / 过滤规则版本
)
```

| 不足 | 后果 |
|---|---|
| 只有 query | practice 复用 explain 缓存 → **答案泄漏** |
| 有 query+mode、无 layer_policy | 换实验权重却命中旧缓存，结论失真 |
| 有 query、无 depth | shallow/deep 证据包粒度串用 |

**危险序（禁止发生）**：

```text
explain 先查 → 缓存含 answer_key
     ↓
practice 后查 → 复用 → 答案泄漏    ✗ 安全事故

practice 先查 → 无答案
     ↓
explain 后查 → 复用 → 讲解缺答案   ✗ 功能错误
```

| 规则 | |
|---|---|
| ✓ | `task_mode` **必进** key；不同 mode **永不共享** cache entry |
| ✓ | `layer_policy` / profile 版本进 key（实验可复现） |
| ✓ | `depth` 进 key |
| ✓ | 同 key 下存的是**已裁剪**的 Evidence Pack，不是 Retriever 原始结果 |
| ✗ | 为省空间把 practice/explain 存进同一 entry 再靠后处理剥离 |
| ✗ | 删索引答案来「配合」缓存 |

**与 §5.1 关系**：索引不删答案；泄漏面在 **Policy 出口** 与 **缓存键** 两处都必须关死。

### 5.4 决策点 D4（已定方向）

| 项 | 结论 |
|---|---|
| 裁剪组件 | **Evidence Policy 唯一出口** |
| 位置 | Retriever 之后、Agent 之前（非 BM25/RRF/Reranker 内） |
| 索引 | **不删答案**；只在 Pack 裁剪 |
| **缓存** | **强制隔离**：key ⊇ `{query, task_mode, depth, layer_policy}`；存 Pack 非原结果；**安全边界** |

---

## 6. 规则三类：Eligibility / Ranking / Release（D5 已定方向）

### 6.0 ★ 总览（冻结）

```text
Candidate Eligibility     能不能进候选池？
        ↓
Retrieval                 多路召回 / RRF
        ↓
Layer Weight              soft 层加权（可配）
        ↓
Rerank                    重排
        ↓
Evidence Release Policy   最终能交给 Agent 什么？
        ↓
Agent
```

| 类 | 问题 | 时机 | 例 |
|---|---|---|---|
| **eligibility** | 进不进池？ | **召回前 / 路由级** | practice + `exam_answer` → **NO** |
| **ranking** | 进池后排前排后？ | 融合/加权/重排 | method + `advanced` → ↑ |
| **release** | 交给 Agent 什么？ | Evidence Policy | explain + `scan` → 可给 + `explanation_unverified=true` |

**原则**：

```text
安全/权限     → eligibility（前置）
相关性/偏好   → ranking
披露/提示     → release
```

### 6.1 Eligibility（候选资格）——前置

| 规则 | 判定 | 说明 |
|---|---|---|
| `exam_resources.answer=forbidden`（practice/learn/verify） | **NO** | `doc_role=exam_answer` 不进池 |
| `exam_resources.question=forbidden`（practice） | **NO** | `exam_item` 不进池 |
| `exam_resources.paper=forbidden`（默认多数模式） | **NO** | `exam_paper` 不进池 |
| `practice` + `assesses`/`related_exams` 展开 | **NO** | 图扩关闭 |
| 无题干 gap（`stem` missing） | **NO** | 无用占位 |
| `figure_status=missing` | **YES** | 仍可进，release 再提示 |

```text
practice + exam_resources 全 forbidden → NO   （eligibility）
verify  + question:yes, answer:no          → 可看题不看答案
method + advanced                      → ↑     （ranking）
explain + scan                         → ✓ + flag  （release）
```

**禁止**：把 eligibility 拖到 RRF/Rerank 之后再删——敏感证据已参与排序。

### 6.2 Ranking（排序偏好）——中段

| 规则 | 例 |
|---|---|
| layer_weight soft | method 时 `advanced` ↑（系数可配） |
| `related_exams` 弱补充 | 权重 ≤ 0.5，可配 |
| KP 单跳定向加权 | V1 |
| legacy 降权 | `kb_depth` 空 |

**不做**：用 ranking 实现安全禁入（那属于 eligibility）。

### 6.3 Release（披露策略）——Evidence Policy

| 规则 | 例 |
|---|---|
| 答案字段 | `answer_released`；practice/learn=false |
| 解析 | `explanation_unverified`（scan）必须提示 |
| 图 | `figure_missing` 明说缺图 |
| 可信度 | `credibility=low` 不作标准答案 |

release **不删索引**，只裁 Pack + 置 flags（见 §5）。

### 6.4 三类对照表

| 问题 | 类 | 失败模式若放错 |
|---|---|---|
| practice 能不能看到真题答案 | **eligibility**（`exam_resources.answer`） | 泄题 |
| verify 能看题不能看答案 | **eligibility**（`question:yes, answer:no`） | 边界糊 |
| method 是否优先 L2 | **ranking** | 只降相关，不泄密 |
| scan 解析能否给 Agent | **release** | 须带提示 |
| 无题干要不要召回 | **eligibility** | 空结果占位 |
| legacy 讲义排多前 | **ranking** | |
| 答案元数据能否进 Pack | **release** | 与 eligibility 双保险 |

### 6.5 集合（V1）

| 集合 | 说明 |
|---|---|
| 四科 subject | L1+L2+legacy |
| `questions` | L3（alias）；`exam_resources` 控 item/answer/paper |
| `learning_paths` | 另册 |

### 6.6 决策点 D5（已定方向）

| 项 | 结论 |
|---|---|
| 模型 | **eligibility → ranking → release** 三类 |
| 安全 | 必须落 eligibility（前置 where/路由） |
| 偏好 | 落 ranking（layer_weight，可配） |
| 披露 | 落 release（Policy flags） |
| 禁止 | 安全规则只靠 release；ranking 当权限用 |

---

## 7. 与现有 depth 的交叉

| depth \ task | learn | method | practice | grade/explain |
|---|---|---|---|---|
| shallow | L1 主 | — | — | — |
| standard | L1+L2 | L2 主 | L3 主 | L2+L3 |
| deep | 全层 | L2+L3 | L3 | 全层 + 图扩 |

- **depth** 管计算：k、HyDE、分解、rerank  
- **task_mode + 层偏好** 管内容：看到哪层、有无答案  

**禁止**把 `depth=L1` 写成知识层 L1。

---

## 8. 门禁（D6 已定方向）

### 8.0 门禁总表

| 门 | 测什么 | 性质 |
|---|---|---|
| 现有 `retrieval_gate` | 管线退化 | **必须**；不得因层加权跌出基线 |
| **Answer Leakage Gate** | 答案是否泄进无权模式 | **安全门**，新增 |
| **Mode Gate** | 各 task_mode 行为 | 新增 |
| **Layer Gate** | 层召回质量（recall + precision） | 新增 |
| 缓存隔离 | practice/explain 不串缓存 | 安全门 |

阈值**不**在本册冻结；**指标定义**冻结，profile 里标定。

### 8.1 ★ Answer Leakage Gate（安全门）

**测试集**：专备 `practice` query 一组，例如：

```text
给我一道死锁题
给我一道 BST 删除练习
出一道哈夫曼编码的计算题
```

**检查项**（不只看 top-k 有无 `exam_answer`）：

| 断言 | 期望 |
|---|---|
| Evidence 里 `answer_key` 出现次数 | **0** |
| `reference_answer` 出现次数 | **0** |
| `exam_answer` chunk 条数 | **0** |
| 具体 `question_id`（如 `2019-Q2`）泄漏 | **0** |
| 缓存 key 跨 mode 复用 | **禁止** |

```text
✗ 只查 top-k 是否有 doc_role=exam_answer
✓ 还要扫 metadata：答案可能藏在 answer_key 字段
✓ 还要扫图扩：related_exams / assesses 不得吐题号
```

**失败即整体失败**（安全门不进容差）。

### 8.2 Mode Gate

| 模式 | 至少断言 |
|---|---|
| `learn` | 有 basic 可见；无 answer_key |
| `method` | 有 advanced 可见；无答案 |
| `practice` | 泄漏门全 0 |
| `grade` | 有 `answer_key`（在 released 时） |
| `explain` | 目标题可展开；scan 有 unverified flag |
| `verify` | 返回 KP/真题列表；默认不带答案键 |

### 8.3 ★ Layer Gate —— recall + precision（不只占比）

**反例（不够）**：

```text
method top10: advanced 4 / basic 3 / exams 3
advanced 占比 ≥ 阈值 → 通过
但目标 L2 方法节根本没命中 → 仍应失败
```

**指标定义（冻结）**：

| 指标 | 定义 |
|---|---|
| **layer_recall@k** | 标注的**目标层证据**是否出现在 top-k |
| **layer_precision@k** | top-k 中属于目标层的比例 |
| （可选）target_hit | 期望的**具体 chunk/section** 是否命中 |

例：`method` query，期望层 `advanced`：

```text
advanced@5  recall     目标 L2 是否进 top-5
advanced@10 precision  top-10 里 advanced 占比
```

| 层 | 典型期望 |
|---|---|
| learn | `basic` 可召回 |
| method | `advanced` 召回 + precision |
| verify | `exams` 召回 |
| explain | 目标 `question_id` hit |

**不用现在定阈值**；profile 里标定。但 **recall 与 precision 必须都进方案**。

### 8.4 与现有 gate 的关系

```text
retrieval_gate     管线不退化（基线）
+ leakage gate     答案不泄漏（安全）
+ mode gate        模式语义
+ layer gate       层召回质量
```

改 layer_weight / eligibility / policy 后：**先跑 leakage，再跑 retrieval_gate**。

### 8.5 决策点 D6（已定方向）

| 项 | 结论 |
|---|---|
| 门禁集 | 现有 gate + **Leakage** + Mode + Layer |
| Leakage | **独立安全门**；查 metadata 与图扩，不只 top-k |
| Layer | **recall + precision**（+ 可选 target_hit），禁止只看占比 |
| 阈值 | 不进架构；experiment profile 标定 |

---

## 9. 实施顺序（建议，待定）

```text
R1  证据契约 + task_mode 入口（不改召回配方）
R2  practice/explain 答案裁剪（负向验收）
R3  kb_depth soft 加权（experiment profile，对照基线）
R4  KP 单跳定向（V1）；多跳图扩明确挂 V2
R5  mode/layer/leakage 门禁并入 CI（先 leakage 后 retrieval_gate）
```

**红线（继承 RETRIEVAL_ROADMAP）**：

- 不做 query 术语归一（已证伪）  
- 不做入库归一（已撤销）  
- 不用假 embedding 结论外推  
- 改召回配方必须跑 `retrieval_gate`

---

## 10. 决策点汇总

| # | 主题 | 倾向 | 状态 |
|---|---|---|---|
| **D1** | task_mode 枚举与答案策略 | **已定方向**：六模式；默认 **`learn`**；explain=讲题 / verify=知识点考过；practice 禁答案 + 禁 `question_id`/`related_exams`/`assesses` 展开 | **已定方向** |
| **D2** | 层偏好机制 | **已定方向**：soft 加权（禁硬路由）；**系数不冻结**，`layer_weight` 可配置 + experiment profile | **已定方向** |
| **D3** | KP/图扩 | **已定方向**：V1 仅 query→KP→单跳层；多跳 V2；`related_exams` 弱导航、核心仍是 `assesses` | **已定方向** |
| **D4** | 证据契约 / 裁剪 / 缓存 | **已定方向**：Evidence Policy 唯一出口；索引不删答案；**缓存 key ⊇ {query, task_mode, depth, layer_policy}，安全边界** | **已定方向** |
| **D5** | 规则分类 | **已定方向**：**eligibility → ranking → release**；安全进 eligibility，偏好进 ranking，披露进 release | **已定方向** |
| **D6** | 门禁 | **已定方向**：现有 gate + **Answer Leakage（安全）** + Mode + Layer（**recall+precision**，不只占比）；阈值进 profile | **已定方向** |
| **D7** | **Retrieval Policy** | **已冻结**：Task Classifier 产出机器可执行 policy；tools/retriever/Policy 消费；接现有 LangGraph | **已冻结** |

全部决策点已定稿 → 实施 R1–R5（见 §9）。

---

## 11. 不做

- 不重写召回/RRF/HyDE 本体（本册只加层与模式）  
- 不做 query/入库术语归一  
- 不把 learning path 检索塞进本册  
- 不在 practice 路径缓存答案  
- 不用 `depth` 字段冒充知识层
