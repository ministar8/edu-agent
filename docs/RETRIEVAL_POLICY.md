# Retrieval Policy（策略契约）

> 状态：**设计定稿**（2026-09-28 定稿；含 exam_resources / grade 分情况 / context 优先级 / depth 升级 / layer_policy_id 白名单）  
> 上游：`RETRIEVAL_LAYER_DESIGN.md`（架构）· `KB_MASTER_DESIGN.md`（数据层）  
> 本册：**机器可执行策略**的字段、默认表、生成规则、消费契约 —— Agent/工具不再各自解释「该搜什么」。

---

## 1. 定位

```text
用户问题
   ↓
Task Classifier
   ↓
Retrieval Policy          ← 本册（唯一策略真源）
   ↓
eligibility / ranking / release
   ↓
Retriever → Rerank → Evidence Policy → Evidence Pack → LLM
```

| | |
|---|---|
| **是** | 类型化、可序列化、可校验的检索配置 |
| **不是** | 自然语言 prompt；也不是 LLM 现场发挥的搜索计划 |

**原则**：一张 policy 表推导全部模式行为；禁止在 tools / prompt / retriever 多处手写模式分支。

---

## 2. Schema（冻结）

```yaml
retrieval_policy:
  # —— 身份 ——
  task_mode: learn | method | practice | grade | explain | verify
  policy_version: "1.0"
  layer_policy_id: "default" | "experiment.v1" | ...

  # —— 知识层 ——
  preferred_layers: [basic | advanced | exams]   # 有序偏好，soft
  excluded_layers: []                            # 尽量空；硬排除见 eligibility
  legacy_weight_class: default | downrank | drop

  # —— 披露 ——
  answer_policy: hidden | released
  explanation_policy: hidden | released | verified_only
  related_exam_policy: off | weak | strong

  # —— 图/扩展 ——
  kp_expansion: enabled | disabled
  graph_expansion: disabled                      # V1 恒 disabled
  related_exam_expansion: enabled | disabled     # 随 related_exam_policy

  # —— 管线 ——
  depth: shallow | standard | deep | code | text_only   # 计算预算默认值（≠ 知识层；可被复杂度升级，见 §3.3）
  k: int | null                                  # null = 用 depth 默认；可随 depth 升级调整
  use_rerank: true | false                       # 仍受 .env RERANK_ENABLED 否决

  # —— L3 资源资格（eligibility，见 §2.2）——
  exam_resources:
    question: allowed | forbidden   # items（题干/选项）
    answer: allowed | forbidden     # answer chunk + 答案字段资产
    paper: allowed | forbidden      # 整卷溯源（默认多关）

  # —— 披露（release，字段级）——
  answer_policy: hidden | released
  explanation_policy: hidden | released | verified_only
  related_exam_policy: off | weak | strong

  # —— 安全（release，与 §2.1 一致）——
  allow_question_id_leak: bool                   # Pack 能否出现 question_id
  cache_scope: "policy_v1"
```

**类型建议**：`schema/retrieval_policy.py`（Pydantic）；非法组合构建时拒绝。

### 2.1 ★ `allow_question_id_leak` 语义（冻结）

```text
控制的是最终 Evidence Pack 是否出现 question_id
不是「数据库内部是否存在 question_id」
```

release 剥离；索引/metadata 可保留。practice 不新增 `exam_reference` 字段，用 `related_exam_policy: off` + 本字段。

### 2.2 ★ `exam_resources` 资源级资格（冻结）

L3 Exam Asset 三种形态（`items` / `answer` / `paper`）分别管控：

| 资源 | 对应 | 谁看 |
|---|---|---|
| `question` | `doc_role=exam_item`（题干+选项） | verify/explain/grade 可；practice **禁** |
| `answer` | `doc_role=exam_answer` + 答案字段 | grade/explain 可；practice/verify **禁** |
| `paper` | `doc_role=exam_paper` | explain 按需；其余默认禁 |

```yaml
practice:
  exam_resources: { question: forbidden, answer: forbidden, paper: forbidden }

verify:
  exam_resources: { question: allowed,   answer: forbidden, paper: forbidden }

explain:
  exam_resources: { question: allowed,   answer: allowed,   paper: allowed }
```

**为何不用 `allow_exam_answer_chunk: bool`**：

| 粗开关 | 资源级 |
|---|---|
| 只能说「要不要 answer chunk」 | verify 可见题目、不可见答案 |
| eligibility 与 release 边界糊 | `question/answer/paper` 进池与否清晰 |
| 与 D1 三文件模型不对齐 | **items / answer / paper 一一对应** |

```text
eligibility  exam_resources.*   → 进不进候选池
ranking      preferred_layers   → 排前排后
release      answer_policy 等   → Pack 字段/题号
```

**V1 默认**：`paper: forbidden`（溯源不进主 RAG）；explain 可开。

---

## 3. 默认策略表（冻结基线；权重数字仍可配）

> 下表是 **policy 字段默认**，不是 layer_weight 数字。权重数字见 experiment profile。

### 3.1 六模式默认

| 字段 | learn | method | practice | grade | explain | verify |
|---|---|---|---|---|---|---|
| `preferred_layers` | basic, advanced | advanced, basic | advanced, basic | exams, advanced | exams, advanced, basic | exams, advanced |
| `exam_resources.question` | forbidden | forbidden | **forbidden** | allowed | allowed | **allowed** |
| `exam_resources.answer` | forbidden | forbidden | **forbidden** | allowed | allowed | **forbidden** |
| `exam_resources.paper` | forbidden | forbidden | **forbidden** | forbidden | **allowed** | forbidden |
| `legacy_weight_class` | downrank | downrank | drop | default | default | downrank |
| `answer_policy` | hidden | hidden | **hidden** | released | released | hidden |
| `explanation_policy` | hidden | hidden | **hidden** | verified_only | released | hidden |
| `related_exam_policy` | off | off | **off** | weak | strong | weak |
| `kp_expansion` | enabled | enabled | enabled | enabled | enabled | enabled |
| `graph_expansion` | disabled | disabled | disabled | disabled | disabled | disabled |
| `allow_question_id_leak` | false | false | **false** | true | true | **true**（列表态） |
| `depth` 默认 | shallow/standard | standard | standard | standard | standard | standard |

> `depth` 仅为默认计算预算，可按 query complexity 升级（§3.2），**不得**带动安全字段。

### 3.2 ★ depth：计算预算，不是 task_mode 的锁死值（冻结）

```text
depth = 管线计算预算（k / HyDE / 分解 / rerank…）
task_mode = 安全与披露
两者必须独立
```

| 规则 | |
|---|---|
| policy 里的 `depth` | **默认值**，由 task_mode 套表 |
| Retriever | 可按 **query complexity** **升级** depth（shallow→standard→deep） |
| **禁止** | 为省算力把 depth **降到**突破安全语义（如 practice 变相扩大资源） |
| **禁止** | depth 升级带动 `exam_resources` / `answer_policy` 等安全字段变化 |

**例**：

```text
learn · default depth=shallow
  「解释死锁为什么发生」     → 保持 shallow/standard
  「综合分析复杂死锁场景」   → 允许升 standard/deep

practice · default depth=standard
  长题干多约束出题           → 可升 deep
  ❌ 升 deep 后不得因此放开 L3 answer / question_id
```

| 字段类 | 可否随复杂度调 | 谁定 |
|---|---|---|
| `depth` / `k` / `use_rerank` | **可升**（计算预算） | Retriever / query_classifier |
| `exam_resources` / `answer_policy` / `explanation_policy` / `allow_question_id_leak` / `related_exam_policy` | **锁死** | Task Classifier / policy 表 |

```text
安全字段 ≠ 计算字段
practice + deep 仍然是 practice 的安全策略
```

### 3.3 安全不变量（校验器强制）

```text
practice:
  exam_resources == {question: forbidden, answer: forbidden, paper: forbidden}
  answer_policy == hidden
  explanation_policy == hidden
  related_exam_policy == off
  allow_question_id_leak == false
  graph_expansion == disabled

learn / method:
  exam_resources.answer == forbidden
  answer_policy == hidden

verify:
  exam_resources.question == allowed
  exam_resources.answer == forbidden
  answer_policy == hidden
  allow_question_id_leak == true

explain / grade:
  exam_resources.answer == allowed
  answer_policy == released
```

非法组合 → **构建 policy 时抛错**。

---

## 4. Task Classifier 规则（冻结）

**规则优先，LLM 兜底**（V1 可先纯规则）。

### 4.0 ★ 输入优先级（冻结）

```text
conversation context    对话状态（上一 mode / 是否刚出题）
      ↓
explicit query signal   当前句关键词
      ↓
agent prior             supervisor 专家（knowledge/question/grading）
      ↓
default = learn
```

**当前句不一定包含完整 task**，必须看上下文。

**例（多轮）**：

```text
轮 1: 给我一道 BST 题。     → practice
轮 2: 我的答案是 C。         → 无「批改」字样
      但 context = practice + user answer
      ⇒ grade   （不是 learn）
```

| 触发 | 说明 |
|---|---|
| context=practice 且本轮像作答（「我的答案 / 选了 / 我写的」） | **升 grade** |
| context=practice 且本轮仍是「再来一道」 | 仍 practice |
| context=grade 且本轮「那第二问呢」 | 续 grade |
| 本轮明确「为什么选 B」且带题号/题面 | explain（压过 context） |

**信号冲突时**：显式信号 **可压过** context；context **压过** agent prior；prior **压过** default。

### 4.1 信号表（当前句关键词）

| 信号（大小写不敏感） | task_mode |
|---|---|
| 默认 | **`learn`** |
| 怎么做 / 步骤 / 怎么解 / 如何计算 / 方法 | `method` |
| 练习题 / 给我一道 / 出题 / 来一道 | `practice` |
| 批改 / 学生的答案 / 对错 / 打分 / 我的答案是 / 选了 | `grade` |
| 为什么选 / 解析 / 为什么是 / 这道题为什么 | `explain`（需年/题号或明确题面） |
| 考过吗 / 有没有真题 / 哪些年考过 / 是否考过 | `verify` |

**同句多信号优先级**（在 context 之后）：`practice` > `grade` > `explain` > `verify` > `method` > 默认 `learn`  
（「给我一道…并批改」→ practice；「2019-Q11 为什么选 B」→ explain。）

**输出**：完整 `retrieval_policy` 对象，不是只输出 mode 字符串。

### 4.2 ★ grade 的 preferred_layers（冻结）

**grade ≠ 只搜 L3。** 批改有两种上下文，policy 生成时必须区分：

| 情况 | 信号 | preferred_layers | exam_resources |
|---|---|---|---|
| **A. 有明确题目** | 「2019-Q11 我选 C 对吗」/ 年+题号 / 贴原题 | **exams 优先**（+ advanced 方法对照） | question: allowed · answer: allowed |
| **B. 无题目、自由作答** | 「这是我写的大题答案…批改」/ 无 question_id | **basic + advanced + exams**（评分依据） | question: allowed · answer: allowed（若有对照题） |

```text
grade
  → 有 question context  → L3 为主（题干/参考答案对照）
  → 无 question context  → L1/L2 提供评分依据 + 可能的 L3 相似题
```

| | |
|---|---|
| Schema | **不改**（仍是六模式 + preferred_layers） |
| 生成规则 | Classifier / `build_policy` 在 `task_mode=grade` 时按「有无 question context」选层 |
| answer_policy | 两情况都是 `released`（批改要对答案/评分标准） |
| explanation_policy | 仍 `verified_only`（缺校验解析须提示） |

**例**：

```text
「2019-Q11 我选 C，对吗？」
  → grade · preferred_layers=[exams, advanced]

「这是我写的生产者消费者 PV 代码，请批改」
  → grade · preferred_layers=[advanced, basic, exams]
```

**禁止**：一律 `grade → only exams`，导致自由作答题没有评分依据。

---

## 5. 消费契约

### 5.1 Task Classifier → Policy

```text
输入: user_query, conversation_hint(可选), agent_id(可选)
输出: retrieval_policy
```

- supervisor 路由到的专家可提供 **prior**（knowledge→learn/method，question→practice，grading→grade/explain）  
- Classifier 用 prior + query 修正 mode，再套默认表生成 policy  
- **grade 再判「有无 question context」**（§4.2）→ 得到 preferred_layers

### 5.2 Retriever / tools（eligibility + ranking）

| policy 字段 | 用途 |
|---|---|
| **`exam_resources.question/answer/paper`** | where / 路由：`doc_role ∈ {exam_item, exam_answer, exam_paper}` 按资源放行或禁止 |
| `allow_question_id_leak` | Pack 剥 `question_id`（release） |
| `preferred_layers` | layer_weight 排序偏好 |
| `kp_expansion` | query→KP→单跳 |
| `graph_expansion` | V1 恒 disabled |
| `depth` / `k` / `use_rerank` | 现有管线参数 |
| `layer_policy_id` | experiment 权重 profile |

### 5.3 Evidence Policy（release）

| policy 字段 | 用途 |
|---|---|
| `answer_policy` | `hidden` → 剥 `answer_key`/`reference_answer`，`answer_released=false` |
| `explanation_policy` | `hidden` 不给解析；`verified_only` 只 verified；`released` 给且标 scan |
| `related_exam_policy` | `off` 不做真题导航；`weak` 低权；`strong` 可展开（explain） |
| **`allow_question_id_leak`** | **false → Pack 剥离** `question_id` / 题号字符串（**仅 release**，不动索引） |

### 5.4 语义缓存

```text
cache_key ⊇ {query, task_mode, depth, layer_policy_id, policy_version}
```

不同 `task_mode` **永不共享** entry；entry 内存放 **已裁剪 Evidence Pack**。

---

## 6. LangGraph 落点（与现码对齐）

```text
teaching_graph: load_memory → supervisor
supervisor: knowledge | question | grading
tools._retrieve_payload → aretrieve_evidence_with_retry
```

| 步骤 | 建议 |
|---|---|
| 1 | `schema/retrieval_policy.py` 定义模型 + 校验 |
| 2 | `agents/retrieval_policy.py`：`build_policy(query, agent_prior) -> RetrievalPolicy` |
| 3 | supervisor/handoff 时把 policy 写入 **state** 或 tool `config` |
| 4 | `tools._retrieve_payload` 读 policy，拆成 retriever 参数 |
| 5 | Evidence Policy 消费 `answer_policy` 等，产出 Pack + flags |

**专家 prompt**：只写职责，**不写**「你只能搜 advanced」；层策略全在 policy。

---

## 7. 策略矩阵速查

```text
                learn   method  practice  grade   explain  verify
L3 question     NO      NO      NO        YES     YES      YES
L3 answer       NO      NO      NO        YES     YES      NO
L3 paper        NO      NO      NO        NO      YES      NO
answer字段      hide    hide    HIDE      show    show     hide
explanation     hide    hide    HIDE      verify  show     hide
related_exams   —       —       OFF       weak    strong   weak
题号 in Pack    NO      NO      NO        YES     YES      YES(列表)
graph_exp       —       —       —         —       —        —   (V1全关)
```

---

## 8. 验收（与 Retrieval Layer §8 对齐）

| 门 | Policy 相关断言 |
|---|---|
| Leakage | practice 的 **Evidence Pack** 内无 `answer_key`/`reference_answer`/`question_id`（扫 Pack，不扫库） |
| Eligibility | `exam_resources` 禁止的 `doc_role` 不得出现在该 mode 候选池 |
| Mode | 各 mode 的 policy 字段与默认表一致 |
| Layer | preferred_layers 驱动 recall/precision 指标 |
| 校验 | 非法组合（practice+released / verify+answer:allowed）构建失败 |
| 缓存 | task_mode 不同则无共享 entry |

**Leakage 扫描范围**：最终下发给 Agent/LM 的 Evidence Pack 与缓存 entry；  
**不要**把「库内 metadata 含 question_id」判成泄漏。

---

## 9. 版本与实验

| 项 | 规则 |
|---|---|
| `policy_version` | 字段语义变更时递增；进缓存 key |
| `layer_policy_id` | **只指排序 profile**；见 §9.1 能改/不能改 |
| 安全字段 | **不可**被 experiment 关掉 |

### 9.1 ★ `layer_policy_id` 可改 / 不可改（冻结）

```text
experiment.v1 / v2 …  只能动「排序与计算」
绝不能动「安全与披露」
```

| **可以改** | 说明 |
|---|---|
| `layer_weight`（basic/advanced/exams/legacy） | soft 加权系数 |
| rerank 系数 / 轻量重排参数 | 排序 |
| `top_k` / `k` 默认值 | 计算预算 |
| KP 单跳加权强度 | 排序 |

| **不能改** | 说明 |
|---|---|
| `answer_policy` | 披露 |
| `explanation_policy` | 披露 |
| `related_exam_policy` | 披露/导航 |
| `exam_resources` | eligibility |
| `allow_question_id_leak` | 泄漏面 |
| 泄漏门验收阈值（安全门） | 通过标准不许为 recall 放水 |

```text
✗ experiment.v2「为了提升 recall，允许 answer 进 practice」
✓ experiment.v2「只调 advanced 在 method 下的 layer_weight」
```

**校验**：加载 `layer_policy_id` 时白名单校验；profile 里出现安全字段 → **拒绝加载**。

---

## 10. 不做

- 不让 LLM 自由生成检索计划当策略  
- 不用 `allow_exam_answer_chunk` 粗开关（已改为 `exam_resources`）  
- 不在 prompt / tools / retriever 重复维护模式表  
- V1 不做多跳 `graph_expansion`  
- 不用 layer_weight 冒充 eligibility  
- practice 下任何路径不得吐 `question_id` 或答案
