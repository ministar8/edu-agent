# Exams 设计（L3 真题层）

> 状态：**设计定稿**（2026-09-28 设计通过）  
> 定位：**具体真题 / 答案 / 题目语境**，服务练习、批改、真题验证。  
> 层级：L1 Basic → 理解 ｜ L2 Advanced → 方法 ｜ **L3 Exams → 真题实践**。  
> 决策点 D0–D6 已全部冻结，详见 §13。

---

## 1. 分层定位

```text
L1 Basic     是什么 / 为什么 / 怎么工作
L2 Advanced  题型识别 / 方法 / 流程
L3 Exams     具体真题题干、选项、答案、解析、卷别语境   ← 本层
```

| L3 写 | L3 不写 |
|---|---|
| 真题题干、选项、填空线 | 方法步骤 / 题型套路（L2） |
| 标准答案、答案键 | 长篇原理推导（L1） |
| 官方/参考解析（若有） | 应试技巧、押题话术 |
| 卷别语境（年份、题号、分值、大题归属） | 书商页码、「王道 p.X」 |
| 可信度标注 | 自造题冒充真题 |

**边界**：L3 是**战例库**，不是方法库。用户问「这题怎么做」→ L2 给方法；用户要「真题验证 / 批改 / 练习」→ L3 给题。

---

## 2. 知识层 vs 资产层（★ 分层图）

### 2.0 Knowledge Architecture 总览（定稿图）

```text
                    ┌─────────────────┐
                    │ Knowledge Point │
                    │   统一考点体系   │
                    └────────┬────────┘
                             ▲
                ┌────────────┼────────────┐
                │            │            │
             teaches       trains      assesses
                │            │            │
          ┌─────┴─────┐ ┌────┴─────┐ ┌───┴────┐
          │ L1 Basic  │ │L2 Adv.   │ │L3 Exams│
          │   原理     │ │   方法    │ │  战例   │
          └───────────┘ └──────────┘ └───┬────┘
                                         │
                                  ┌──────┴──────┐
                                  │ Exam Assets │
                                  └──────┬──────┘
                              ┌──────────┼──────────┐
                              ↓          ↓          ↓
                           items      answer      paper
                              │          │          │
                            主检索      解析检索    溯源
```

### 2.1 知识层（L1/L2/L3 与 KP）

```text
Knowledge Point（统一考点）
        ↑ teaches     ↑ trains      ↑ assesses
        │             │              │
     L1 Basic      L2 Advanced     L3 Exams
     原理/思想      方法/题型       真题/战例
                                      │
                                      ▼
                               Exam Asset（见 §2.2）
```

| 层 | 边 | 含义 |
|---|---|---|
| L1 Basic | `teaches` → KP | 讲解 |
| L2 Advanced | `trains` → KP | 方法 / 训练 |
| L3 Exams | `assesses` → KP | 考查 |
| L2→L3 | `related_exams`（弱） | 推荐真题案例，非引用 |

**知识层只有三层 + KP**；items / answer / paper **不是**与 L1/L2/L3 平级的「内容层」。

### 2.2 资产层：L3 Exam Asset 的三种形态

```text
L3 Exam Asset（question:YYYY-QN）
        │
        ├── items   题干+选项+答案元数据   → 主检索
        ├── answer  解析                    → 解析检索
        └── paper   整卷语境                → 溯源（默认不进主 RAG）
```

| 形态 | doc_role | 检索 | 职责 |
|---|---|---|---|
| **items** | `exam_item` | 主检索 | 单题结构；练习/批改/真题验证入口 |
| **answer** | `exam_answer` | 解析检索 | 按题解析；讲解与批改反馈 |
| **paper** | `exam_paper` | 不进主 RAG | 整卷语境、溯源对照 |

**分工**：

```text
知识层   L3 = 「真题战例」这一层
资产层   Exam Asset = 该层在磁盘/索引里的三种载体
```

- 一个 `question:YYYY-QN` 可对应 items + answer 两份资产（同 section_id）
- paper 是**卷级**资产（`paper:YYYY`），服务溯源，不是题的同级兄弟「内容层」

### 2.3 Question 内部（语义主体）

```text
question:2019-Q41          ← 资产主键
  └── exam-2019-Q41        ← section_id
        ├── exam-2019-Q41-items-001
        └── exam-2019-Q41-answer-001

综合题小问（从属结构，非独立资产）：
  2019-Q41-1 → kp_ids + answer/reference
  2019-Q41-2 → …
  2019-Q41-3 → …
  整题 kp_ids = 并集；V1 assesses 仍挂整题
```

| 边 | from | to | 语义 |
|---|---|---|---|
| `teaches` | `basic:<section_id>` | KP | 讲解 |
| `trains` | `advanced:<section_id>` | KP | 方法/训练 |
| **`assesses`** | **`question:YYYY-QN`** | KP | 考查 |

**UNIQUE(from, type, to)**；一题可多 KP（综合题多条 assesses，禁止只锚一个）。

**小问是 Question 的从属结构，不是独立资产类型**。  
`question:YYYY-QN` 仍是唯一对外资产主键；小问 KP 信息内嵌在题上，供错题回链 / 掌握度 / 路径 / 分问批改。

---

## 3. Exam Asset 形态（D1 已定方向）

> 知识层见 §2.1；本节是**资产/存储形态**，不是第四层内容。

### 3.1 定论：items + answer 为主，paper 仅溯源

```text
knowledge/exams/
└── 2019/
    ├── items.md      # 主检索：题干 / 选项 / 答案字段 / 小问
    ├── answer.md     # 主检索：按题解析
    └── paper.md      # 非主检索：整卷原始语境 / 溯源（不进主 RAG）
```

| 文件 | doc_role | 进主 RAG？ | 职责 |
|---|---|---|---|
| `items.md` | `exam_item` | **✓ 主载体** | 单题结构化；批改/练习/真题验证入口 |
| `answer.md` | `exam_answer` | **✓** | 按题解析；讲解与批改反馈取材 |
| `paper.md` | `exam_paper` | **✗ 默认不进** | 整卷原始语境、卷面结构、溯源对照 |

**paper 规则（冻结方向）**：

| 项 | 约定 |
|---|---|
| 保留 | **保留文件**，不删、不合并进 items |
| 检索 | **不进主 RRF / 默认路由**；仅溯源、排版对照、卷别语境查询 |
| 内容 | 卷头、大题结构、分值、原卷顺序；**不**重复结构化题干作主答案源 |
| 权重 | 若误入候选，应可被 `doc_role=exam_paper` 过滤掉 |
| 与 items 关系 | 以 `question_id` 对齐；冲突时 **items 为准**（已清洗结构） |

**为何不是纯 C、也不是纯 A**：

- 纯 C（只 items+answer）：丢整卷语境与 PDF 重排溯源，图题/排版争议无法回看  
- 纯 A（paper 进主检索）：整卷噪声大，会污染「按题」检索  
- **C + paper 溯源**：主路径干净，溯源可查

### 3.2 否决案（备查）

| 案 | 否决原因 |
|---|---|
| 单 `items` 文件（题+答案+解析同节） | 答案泄漏进检索；解析长短不齐撑爆 chunk |
| paper 进主 RRF | 整卷噪声；与 items 重复 |

### 3.3 入库策略

| 文件 | 入向量库 | 集合 |
|---|---|---|
| `items.md` | ✓ | `questions`（= L3） |
| `answer.md` | ✓ | `questions` |
| `paper.md` | **默认否**（或独立低权/溯源索引） | 不进主召回；`doc_role=exam_paper` 可识别 |

---

## 4. 单题结构（items）

### 4.0 ★ 答案字段拆分（已定方向）

`answer_key` 一词不能同时表示「选项字母 / 填空值 / 综合参考答案」。拆成两个概念：

| 字段 | 语义 | 适用 |
|---|---|---|
| **`answer_key`** | **客观题答案键**（可机读、可自动判分） | `choice`：`A`–`D`；`fill`：值列表 |
| **`reference_answer`** | **主观题参考答案**（叙述/推导/代码/多步结果） | `comprehensive`；填空长答案也可用 |

```text
question_type=choice         answer_key=B          reference_answer=null
question_type=fill           answer_key=["…","…"]  reference_answer=null
question_type=comprehensive  answer_key=null       reference_answer=…
```

**互斥**：同一题上二者只填一个（另一个显式 `null`）。  
**小问同理**：小问是客观结果 → `answer_key`；小问是推导/代码 → `reference_answer`。

### 4.1 选择题示例

```markdown
## 2019-Q11

> question_id: 2019-Q11
> exam_year: 2019
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: none
> kp_ids: [os.file.disk_free_space, os.file.file_allocation]
> answer_key: B
> reference_answer: null

**题干**：…

- A. …
- B. …
- C. …
- D. …
```

### 4.2 填空题示例

```markdown
## 2020-Q05

> question_id: 2020-Q05
> exam_year: 2020
> question_type: fill
> score: 2
> source_type: third_party
> credibility: high
> explanation_status: none
> kp_ids: [ds.tree.huffman]
> answer_key:
>   - "57"
>   - "3.5"
> reference_answer: null

**题干**：…
```

### 4.3 综合题示例（含小问粒度）

```markdown
## 2019-Q41

> question_id: 2019-Q41
> exam_year: 2019
> question_type: comprehensive
> score: 10
> part: 二、综合应用题
> source_type: third_party
> credibility: high
> explanation_status: none
> kp_ids: [ds.tree.bst, ds.tree.traversal, ds.search.b_tree]
> answer_key: null
> reference_answer: |
>   （1）…推导…
>   （2）…推导…
>   （3）…推导…
> sub_questions:
>   - id: 2019-Q41-1
>     label: （1）
>     kp_ids: [ds.tree.bst]
>     answer_key: null
>     reference_answer: …
>   - id: 2019-Q41-2
>     label: （2）
>     kp_ids: [ds.tree.traversal]
>     answer_key: null
>     reference_answer: …
>   - id: 2019-Q41-3
>     label: （3）
>     kp_ids: [ds.search.b_tree]
>     answer_key: null
>     reference_answer: …
>   # 若某小问是客观结果（如「高度为 __」），则：
>   #   answer_key: "3"
>   #   reference_answer: null

**题干**：…

**（1）** …
**（2）** …
**（3）** …
```

### 4.4 字段

| 字段 | 必填 | 取值 | 说明 |
|---|---|---|---|
| `question_id` | ✓ | `YYYY-QN` | **冻结**；链上 `question:YYYY-QN` |
| `exam_year` | ✓ | 2009–2025 | |
| `question_type` | ✓ | `choice` / `fill` / `comprehensive` | 408 现行题型 |
| `score` | 可选 | int | 整题分值 |
| `part` | 可选 | 大题名 | 卷内位置语境 |
| `credibility` | ✓ | `high` / `medium` / `low` | **题级可覆盖**卷级默认；见 §5 |
| `source_type` | ✓ | `official` / `third_party` / `recall` | 来源类型；≠ 可信度 |
| `explanation_status` | ✓ | `none` / `scan` / `verified` | **正式字段，枚举冻结**；见 §5.3 |
| `kp_ids` | ✓ | KP id 列表 | **整题** KP 并集；assesses 边来源；可空→记 gap |
| **`subject`** | ✓ | `ds`/`co`/`os`/`cn`/`mixed` | **题目所属学科**（独立于 KP）；KP 未标时仍必填；综合题可 `mixed` |
| **`answer_key`** | 题型定 | `A`–`D` \| `string[]`（fill） | **仅客观题**；综合题 `null` |
| **`reference_answer`** | 题型定 | 文本（可多行） | **仅主观/综合**；客观题 `null` |
| `sub_questions` | 综合题建议 | 见 §4.6 | 小问列表（id / kp_ids / answer_key \| reference_answer） |
| **`has_figure`** | ✓ | bool | 题面是否含图（正式字段） |
| **`figure_status`** | has_figure 时 ✓ | `present` / `missing` | 图是否在库；见 §4.4.1 |
| **`completeness`** | ✓ | `complete` / `partial` / `incomplete` | **题目必要字段**是否齐全（**不含解析**）；见 §9.1 |
| **`gap_status`** | ✓ | `none` / `missing` / `partial` | 粗粒度；**不**做多缺口编码 |
| **`gap_fields`** | ✓ | `string[]` | **真源**：`stem`/`options`/`answer`/`sub_questions`/`figure` |

**答案字段与题型对照**：

| `question_type` | `answer_key` | `reference_answer` |
|---|---|---|
| `choice` | `A`–`D` | `null` |
| `fill` | `string[]`（按空位顺序） | `null` |
| `comprehensive` | `null`（若整题无客观键） | 必填叙述；小问可各自选键或参考答案 |

### 4.4.1 ★ `has_figure` / `figure_status`（正式 Schema 字段）

408 真题里**图不是装饰**（AOE 网、树形、时序、框图…），是解题必要信息。缺图时必须显式声明，禁止模型脑补。

```text
has_figure     题面有没有图          true | false
figure_status  图在不在知识库里      present | missing   （仅 has_figure=true 时有效）
```

| `has_figure` | `figure_status` | 含义 |
|---|---|---|
| `false` | —（可省略/`null`） | 无图题 |
| `true` | `present` | 图已提取入库（资产里有图） |
| `true` | `missing` | 题面提到图，但库里没有图 |

**正文配合**：

```markdown
> has_figure: true
> figure_status: missing

**题干**：下图所示的 AOE 网……（题 5 图）
<!-- figure missing：知识库未收录原图 -->
```

**Agent 规则（冻结）**：

| `figure_status` | 行为 |
|---|---|
| `present` | 可展示/引用图 |
| `missing` | **明说「该题包含图，但当前知识库缺失题图」**；禁止脑补图形内容 |
| `has_figure=false` | 正常作答 |

```text
figure_status=missing
  → 输出：该题包含图，但当前知识库缺失题图。
  → 不编造 AOE / 树 / 时序图的结构
```

**禁止**字段：`publisher` / `book` / `page` / 应试标签。

### 4.5 `question_type` 与 KP `typical_question_types` 对齐

| L3 | KP 先验（typical_question_types） |
|---|---|
| `choice` | `choice` |
| `fill` | `fill` |
| `comprehensive` | `comprehensive` / `code` / `design` / `calculation` |

L3 的 `question_type` = **本题实际题型**；KP 的 `typical_question_types` = **允许/典型考法**（先验）。  
历史频次一律从 `assesses` 统计，禁止写回 KP。

### 4.6 ★ 综合题小问粒度（方向已定）

**问题**：综合题多小问各考不同 KP。若只写：

```text
question:2019-Q41 ──assesses──→ ds.tree.bst
                   ──assesses──→ ds.tree.traversal
                   ──assesses──→ ds.search.b_tree
```

会丢掉「**哪一小问考哪个 KP**」——直接影响错题回链、KP 掌握度、学习路径、分问批改。

**模型（不推翻 Question 主资产）**：

| 层 | 职责 | 是否独立资产 |
|---|---|---|
| **Question** `2019-Q41` | 主资产；卷别、题干、整题答案、assesses | ✓ |
| **Sub-question** `2019-Q41-1` | 小问定位 + **细粒度 KP** + 分问答案 | ✗（从属结构） |

```yaml
question_id: 2019-Q41
kp_ids: [ds.tree.bst, ds.tree.traversal, ds.search.b_tree]   # 并集
sub_questions:
  - id: 2019-Q41-1
    label: （1）
    kp_ids: [ds.tree.bst]
  - id: 2019-Q41-2
    label: （2）
    kp_ids: [ds.tree.traversal]
  - id: 2019-Q41-3
    label: （3）
    kp_ids: [ds.search.b_tree]
```

**规则（冻结）**：

| 项 | 约定 |
|---|---|
| **主键** | 仍是 `question_id = YYYY-QN`；**禁止**把小问提升为独立 asset_type |
| **assesses（V1）** | `from = question:YYYY-QN` → KP；**不**改成 subquestion |
| **KP 传递** | 整题 `kp_ids` = 各小问 `kp_ids` 的并集（无小问结构时人工标整题） |
| **小问 id** | `YYYY-QN-K`（K 从 1 起，与正文 `（K）` 对应） |
| **定位符（预留）** | `question:2019-Q41#1` = 第 1 小问；V1 **不**进 `links`，仅服务批改/讲解/记忆定位 |
| **选择/填空** | 无小问结构；`kp_ids` 直接挂整题 |

**V1 不写 subquestion 边**，但**必须存**小问 KP 映射。将来升级路径：

```text
V1  question:2019-Q41 ──assesses──→ KP     （整题）
V2+ question:2019-Q41#1 ──assesses──→ KP   （可选细化；UNIQUE 仍成立）
```

**消费方（V1 就能用）**：

| 场景 | 用法 |
|---|---|
| 错题回链 | 「错在（2）」→ `sub_questions[1].kp_ids` → 补 L1/L2 |
| KP 掌握度 | 按小问 KP 聚合错题，比整题粒度准 |
| 学习路径 | 综合题可拆入不同 KP 练习池 |
| 分问批改 | 客观小问对 `answer_key`；主观小问比对 `reference_answer`；反馈绑小问 KP |

---

## 5. 来源与可信度（D2 已定方向）

### 5.0 ★ 拆分：`source_type` ≠ `credibility`

旧模型把「从哪来」和「有多可信」揉在一个 `credibility` 里（`syllabus`/`third_party`/`recall`），语义不正：
「大纲/官方」不是可信度，是来源；第三方重排也可以很可信。

```text
source_type   来源类型（从哪来）
credibility   可信程度（有多可信）
explanation_status  解析文字状态（有没有可读解析）
```

### 5.1 `source_type`（来源类型）

| 值 | 含义 | 例 |
|---|---|---|
| `official` | 官方/大纲/命题机构原题 | 教育部考试大纲样题、官方公布卷 |
| `third_party` | 第三方整理/重排/OCR/结构化 | `papers-rebuild`、`questions`、`answers` |
| `recall` | 回忆版 | 考生回忆、论坛整理 |

**禁止**：把 `official` 当高可信同义词写进 `credibility`。

### 5.2 `credibility`（可信程度）

| 值 | 含义 | 批改默认 |
|---|---|---|
| `high` | 题干/答案可靠，可作标准答案 | ✓ |
| `medium` | 基本可用，可能有排版/个别错 | ✓（响应回传） |
| `low` | 只供参考，不作自动判分依据 | **默认不用** |

**题级优先**：文档可给卷级默认值，**题级可覆盖**（某题回忆补全 → 该题 `low`）。

### 5.3 ★ `explanation_status`（正式 Schema 字段，题级必填，枚举冻结）

**枚举（冻结，勿再加值）**：

| 值 | 含义 | 知识库里有没有可引用解析文本 |
|---|---|---|
| **`none`** | 没有解析（无材料，或仅扫描图、**无**可抽取文字） | ✗ |
| **`scan`** | 有解析文本，来源为扫描/OCR/第三方转换，**尚未人工确认** | ✓ 未校验 |
| **`verified`** | 已人工或高置信度校验的解析 | ✓ 可信 |

```text
explanation_status: none | scan | verified
```

**★ `scan` 消歧（冻结）**：

```text
scan ≠ 「有扫描件」
scan = 「有可引用的解析文字，但未经人工确认」

无文字可抽的纯扫描图 → none（不是 scan）
OCR 转出来的文字     → scan
人工核对过的解析     → verified
```

| 歧义写法 | 正确 |
|---|---|
| 「scan = 有扫描 PDF」 | ✗ |
| 「scan = OCR 出来了就算 verified」 | ✗ |
| 「scan = 已经看过」 | ✗ |
| **scan = 有文字、未确认** | ✓ |

**与旧四值对照（迁移映射）**：

| 旧 | 新 | 说明 |
|---|---|---|
| `none` | `none` | 无解析文字 |
| `scan`（纯图） | `none` | 无可抽取文字 |
| `ocr` | `scan` | OCR 文本，未核对 |
| `text` | `scan` 或 `verified` | 未核对→`scan`；已核对→`verified` |

**语义**：描述**解析文本的有无 + 是否校验**，不是「题目可信度」。  
与 `answer_key` / `reference_answer` **独立**：可以有答案键但 `explanation_status=none`。

**Agent 批改 / 讲解消费规则（冻结）**：

| `explanation_status` | 行为 |
|---|---|
| `verified` | 可引用解析作讲解与批改反馈 |
| `scan` | **允许参考**，但必须提示「解析未经人工校验，可能有误」 |
| `none` | **不要假装能检索解析**；只用 `answer_key`/`reference_answer`，或明确说无文字解析 |

```text
explanation_status=verified → 可正常使用
explanation_status=scan     → 参考 + 提示「未校验」
explanation_status=none     → 不假装有解析、不编造
```

**与 `credibility` 分工**：

| 字段 | 管什么 |
|---|---|
| `credibility` | 题干/答案键可不可信 |
| `explanation_status` | 解析文本在不在、校验没有 |

**校验升迁**：

```text
none → scan      （补 OCR / 换文字版解析）
scan → verified  （人工确认或高置信校验）
禁止：scan 直接标 verified 而不做确认
```

### 5.4 当前语料标注（迁移默认值）

| 来源 | source_type | credibility | explanation_status |
|---|---|---|---|
| `papers-rebuild/` | `third_party` | `medium`（约 5 错/100KB） | `none`（无解析文本） |
| `questions/` 结构化题干+✅键 | `third_party` | `high`（键）/ `medium`（干） | `none` |
| `answers/` 文字版（09–18,20,22,23） | `third_party` | `medium` | **`scan`**（OCR/未核对） |
| `answers/` 扫描件（19,21,24,25） | `third_party` | — | **`none`**（无文字） |
| 未来官方文字解析 | `official` | `high` | `verified` |
| 回忆补题 | `recall` | `low` | 可变 |

### 5.5 用法约定

```yaml
# 第三方重排 + 答案键清晰 + 无文字解析
source_type: third_party
credibility: high          # 键可信
explanation_status: none

# 回忆版
source_type: recall
credibility: low
explanation_status: none
```

| 场景 | 行为 |
|---|---|
| 批改自动判分 | 默认用 `credibility ∈ {high, medium}` 的 `answer_key` |
| `recall` / `low` | 可检索展示，**不进**默认批改池 |
| Agent 响应 | 回传 `source_type` + `credibility`，不把第三方键说成「官方标准答案」 |
| 综合题 | `reference_answer` 旁标注 `credibility`；OCR 噪声解析标 `scan` 仍保留，核对后升 `verified` |

---

## 6. ID 与 chunk（D3 冻结 + chunk_id 防冲突修订）

### 6.0 ID 链

```text
asset_ref     question:2019-Q11
                  ↓
section_id    exam-2019-Q11              ← 语义主体（冻结）
                  │
                  ├── items chunk   exam-2019-Q11-items-001
                  └── answer chunk  exam-2019-Q11-answer-001
```

| 层 | 格式 | 例 | 用途 |
|---|---|---|---|
| asset_ref | `question:YYYY-QN` | `question:2019-Q11` | links / related_exams |
| **section_id** | `exam-YYYY-QN` | `exam-2019-Q11` | 语义主体；assesses 对应；**冻结不变** |
| **chunk_id** | 见 §6.0.1 | `exam-2019-Q11-items-001` | 检索载体；**全库唯一** |
| document_id | `exam-YYYY-{items,answer,paper}` | `exam-2019-items` | 文件 |

**`exam-` 与 `question:` 分工**：

```text
question:2019-Q11   ← 资产类型前缀（links、asset_ref 解析用）
exam-2019-Q11       ← 入库 section_id（向量库 / 回链）
```

互转：`question:` + `YYYY-QN` ⇄ `exam-` + `YYYY-QN`（题号段不变）。

**禁止**：改用 `question-` / `questions-` 作 section 前缀。

### 6.0.1 ★ chunk_id 防冲突（修订 D3 的编号段）

**问题**：items 与 answer 同 `section_id`，若都用 `exam-2019-Q11-001` 会撞 ID，污染 upsert / 删除 / 去重 / 回链 / 增量重建。

**规则（冻结）**：`section_id` 不变；**chunk_id 在 section 后插入 role 段**。

```text
items:   exam-YYYY-QN-items-NNN
answer:  exam-YYYY-QN-answer-NNN
paper:   exam-YYYY-paper-NNN        # 若入索引；按卷切，不挂 QN
```

| 文档 | chunk_id 模式 | 例 |
|---|---|---|
| `items.md` | `exam-YYYY-QN-items-NNN` | `exam-2019-Q11-items-001` |
| `answer.md` | `exam-YYYY-QN-answer-NNN` | `exam-2019-Q11-answer-001` |
| `paper.md` | `exam-YYYY-paper-NNN` | `exam-2019-paper-001`（默认不入主 RAG） |

**ID 链规则（L3 特化）**：

```text
chunk_id.startswith(section_id)     # exam-2019-Q11-items-001 ⊂ exam-2019-Q11  ✓
section 与 document 不要求前缀包含   # exam-2019-Q11 与 exam-2019-items 是「同题双文档」
```

| 对比 | L1 / L2 | L3 |
|---|---|---|
| section | 一节一文 | **一题两文**（items + answer） |
| chunk_id | `<section_id>-NNN` | `<section_id>-{items\|answer}-NNN` |
| chunk 唯一性 | section 内唯一 | **全集合唯一**（role 段消歧） |

**不变**：

```text
question:2019-Q11  →  exam-2019-Q11  →  exam-2019-Q11-items-001 / exam-2019-Q11-answer-001
```

`question:YYYY-QN` 与 `exam-YYYY-QN` 的映射**不受影响**。

### 6.1 document_id

| 文件 | document_id | doc_role |
|---|---|---|
| `items.md` | `exam-YYYY-items` | `exam_item` |
| `answer.md` | `exam-YYYY-answer` | `exam_answer` |
| `paper.md` | `exam-YYYY-paper` | `exam_paper` |

### 6.2 chunk 切分

- 一题 = 一 section（`exam-YYYY-QN`）；短题单 chunk，综合题可切小问但仍共享 `section_id`
- **items / answer 各自成 chunk 族**，靠 chunk_id 的 `items` / `answer` 段消歧
- 整卷 `paper.md` **默认不进主 RRF**（`doc_role=exam_paper` 可识别）
- 答案 `answer.md` 按 `question_id` 对齐，与 items **同 `section_id`**，不同 `document_id`

**ID 校验（L3）**：

```text
chunk_id.startswith(section_id)          # 必须
doc_role ∈ chunk_id 中的 role 段          # items|answer|paper
chunk_id 全集合唯一                        # upsert / 删除 / 去重依赖
```

**不要**再套用 L1/L2 的 `section_id.startswith(document_id)`——L3 是同题双文档。

---

## 7. 元数据（chunk 级继承）

| 字段 | 来源 | 例 |
|---|---|---|
| `kb_depth` | 文档 | `exams` |
| `doc_role` | 文件类型 | `exam_item` / `exam_answer` / `exam_paper` |
| `exam_year` | 文档 | `2019` |
| `question_id` | section | `2019-Q11` |
| `source_type` | 文档/题 | `third_party` |
| `credibility` | 文档/题 | `high`/`medium`/`low` |
| `explanation_status` | 题 | `none`/`scan`/`verified`（必填，冻结） |
| `question_type` | 题 | `choice` |
| `knowledge_points` | section.kp_ids | JSON 列表 |
| `answer_key` | 题 | 客观题；`B` 或 `["…"]`；综合 `null` |
| `reference_answer` | 题 | 主观/综合参考答案；客观 `null` |
| `sub_questions` | 综合题 | JSON 列表（id/label/kp_ids/answer_key\|reference_answer） |
| `has_figure` | 题 | bool（正式） |
| `figure_status` | 题 | `present`/`missing`（has_figure 时必填） |
| `completeness` | 题 | `complete`/`partial`/`incomplete`（题目必要字段，不含解析） |
| `gap_status` | 题 | `none`/`missing`/`partial` |
| `gap_fields` | 题 | JSON 列表（**真源**） |
| `subject` | 题 | `ds`/`co`/`os`/`cn`/`mixed` | 题目所属学科（≠ 由 KP 推导） |

**批改分离原则**：

```text
检索「题干」→ exam_item（答案只进元数据，正文不印答案）
检索「解析」→ exam_answer
检索「这题答案」→ item.answer_key 或 item.reference_answer + answer 解析
```

### 7.1 ★ D4 答案只进 metadata（已冻结）

```text
items.md 正文     题干 + 选项（+ 小问）     ← 不写答案
items metadata   answer_key / reference_answer
answer.md        长解析（按 explanation_status）
```

**反例（禁止）**：

```markdown
### 第11题
题干……
- A. …
- B. …
答案：B          ← 禁止进 item 正文
```

**正例**：

```markdown
> answer_key: B
> reference_answer: null

**题干**：…
- A. …
- B. …
```

**为何必须只进 metadata**：

| 场景 | 需要 |
|---|---|
| 练习模式 | 出题干，**禁止**带答案 |
| 批改模式 | 允许答案（判分） |
| 讲解模式 | 允许答案 + 解析 |

若答案进正文，检索「2019-Q11 是什么题」会直接把答案 chunk 冲出来，练习模式无法干净出题。

| 选项 | 结论 |
|---|---|
| A. 只进 metadata | **✓ 冻结采用** |
| B. 正文加粗 ✅ | ✗ 否决（检索漏答案） |
| C. 双写 | ✗ 否决（练习模式仍会漏） |

**迁移**：现状 `questions/` 的 `**B. …** ✅` 剥离进 `answer_key`；正文改回普通选项。

---

## 8. 目录与集合（D5 已定方向）

### 8.1 目录（冻结）

```text
knowledge/exams/
├── 2009/
│   ├── items.md
│   ├── answer.md
│   └── paper.md      # 仅溯源，不进主 RAG
├── …
└── 2025/
```

### 8.2 向量集合：最终名 `exams`，`questions` 仅迁移期 alias

```text
现状  questions collection  ← 迁移期 alias（短期可跑）
目标  exams collection      ← 最终统一名
```

| 阶段 | 集合名 | 说明 |
|---|---|---|
| 过渡 | `questions`（alias） | 现网代码路径已通；双写/读旧写新 |
| **最终** | **`exams`** | 与 `kb_depth=exams` / 目录 `exams/` 对齐 |

**为何不永久留 `questions`**：

```text
questions  语义会被撑爆：
  ├── exam items（真题）          ← 本层
  ├── practice questions（练习题）
  ├── generated questions（出题）
  └── diagnostic questions（诊断）
```

`questions` 当「所有题」会把 **L3 真题** 与未来练习/生成/诊断题搅在一起。  
**L3 只存真题** → 集合名用 `exams`；练习/生成题另集合，勿共用。

**迁移纪律**：

1. 内容迁 `knowledge/exams/YYYY/`（items 剥答案进 metadata）  
2. 集合：`questions` → `exams`（alias 过渡，门禁稳后收口）  
3. **红线**：未过门禁不删旧集合；alias 期双写或读兼容  
4. 代码/文档写「`exams` = L3 真题」；勿再把 `questions` 当全量题库

### 8.3 现状迁入

| 现路径 | 内容 | 迁入 |
|---|---|---|
| `questions/YYYY_408_exam.md` | 已按题结构化（选项+✅答案） | `exams/YYYY/items.md`（剥离答案进元数据） |
| `papers-rebuild/YYYY.md` | 整卷重排噪声 | `exams/YYYY/paper.md`（**仅溯源，不进主 RAG**） |
| `answers/YYYY-answer.md` | 解析（质量不齐） | `exams/YYYY/answer.md`（有则迁） |

---

## 9. 数据缺口策略（D6 已定稿）

### 9.0 原则

```text
真实数据优先，缺口显式记录，不人工臆补。
年份覆盖率 < 数据真实性。
```

没有可靠题干 / 答案 / 解析时，**不**用低可信来源拼接成「完整题」。硬补会污染 RAG。

### 9.1 字段（正式 Schema）

| 字段 | 取值 | 角色 |
|---|---|---|
| **`completeness`** | `complete` \| `partial` \| `incomplete` | **整体状态**（题目必要字段，不含解析） |
| **`gap_status`** | `none` \| `missing` \| `partial` | **粗粒度**：有没有缺口 / 哪一层 |
| **`gap_fields`** | `string[]` | **真源**：具体缺什么 |

**★ 谁是真源**：

```text
gap_fields   →  真源（缺什么，多值可组合）
gap_status   →  由 gap_fields 推导的粗标记（单值，不做多缺口编码）
completeness →  整题验收状态（只看必要字段）
```

**禁止**把 `gap_status` 写成 `missing_answer` / `missing_figure` 这类多缺口编码——组合缺口说不清。

**`gap_status` 枚举（冻结）**：

| 值 | 含义 | 典型 |
|---|---|---|
| `none` | 无题目资产缺口 | `gap_fields: []` |
| `partial` | 有题干，但缺部分必要字段 | `gap_fields: [answer, figure]` |
| `missing` | 无题干 / 整题不可用 | `gap_fields: [stem, …]` |

**`gap_fields` 常用值**：`stem` / `options` / `answer` / `sub_questions` / `figure`  
（**不含** `explanation`——解析只归 `explanation_status`。）

**推导规则**：

```text
gap_fields 仅含必要字段缺口
  []                         → gap_status=none
  有缺口且含 stem            → gap_status=missing,  completeness=incomplete
  有缺口且不含 stem          → gap_status=partial,  completeness=partial

explanation 缺失             → 只影响 explanation_status，不进 gap_fields
```

**`completeness` 定义（不含解析）**：

| question_type | 必要字段（缺一 → 非 complete） |
|---|---|
| `choice` | 题干 + 选项 + `answer_key` |
| `fill` | 题干 + `answer_key` |
| `comprehensive` | 题干 + 小问结构（若有）+ `reference_answer`（或分问答案） |

**对照（多缺口组合）**：

| 场景 | completeness | gap_status | gap_fields | explanation_status |
|---|---|---|---|---|
| 干+选项+键全，无解析 | `complete` | `none` | `[]` | `none` |
| 干+选项+键全，OCR 解析未核对 | `complete` | `none` | `[]` | `scan` |
| 无答案键 | `partial` | `partial` | `["answer"]` | 任意 |
| 无答案键 + 无图资产 | `partial` | `partial` | `["answer", "figure"]` | 任意 |
| 综合题缺小问 | `partial` | `partial` | `["sub_questions"]` | 任意 |
| 连题干都没有 | `incomplete` | `missing` | `["stem", …]` | 任意 |

**字段分工（真正解耦）**：

```text
completeness        题目本身完不完整（必要字段）
gap_status          粗：none | missing | partial
gap_fields          细：具体缺什么（真源）
explanation_status  解析有没有、什么质量（增强，独立）
figure_status       图在不在（资产层）
credibility         题干/答案可不可信
```

无解析 ⇒ `explanation_status: none`，**不**进 `gap_fields`，**不**降 `completeness`。

### 9.2 处理规则（冻结）

1. **题目必要字段齐全** → `completeness=complete`（解析可有可无）  
2. **缺题目必要字段** → 保存已有数据；`completeness=partial` + `gap_status`/`gap_fields`  
3. **整题缺失 / 无题干** → 只建 gap 记录；**不生成虚构题目**；**不进正常题目 RAG**  
4. **解析缺失** → 只标 `explanation_status=none`，**不**标 partial  
5. **2018–2025 年 41–47** = **优先补全范围**，不是强制补全范围  
6. **后续发现可靠来源** → `gap → complete` 或 `explanation_status` 升级，重跑入库 + assesses + `retrieval_gate`

```text
题目必要字段  →  决定 completeness
解析          →  只进 explanation_status（增强）
图            →  has_figure + figure_status（可影响 completeness）
```

### 9.3 检索过滤（冻结）

| 检索意图 | 过滤 |
|---|---|
| 正常题目检索 | `completeness != incomplete` 且 `"stem" ∉ gap_fields` |
| 解析检索 | `explanation_status ∈ {scan, verified}` |
| 可直接引用的解析 | `explanation_status = verified` |
| 批改自动判分 | 有 `answer_key`/`reference_answer` 且 `credibility ∈ {high, medium}` |

**反例**：`2019-Q11` 可以是 `complete` + `explanation_status=none`。  
问「2019-Q11 为什么选 B？」→ 可给答案键；**不得**编造解析。

```text
question_id: 2019-Q11
completeness: complete          # 干+选项+键齐全
gap_status: none
answer_key: B
explanation_status: none        # 无解析 ≠ 不完整
```

### 9.4 补全清单（数据验收）

```text
题目资产补全：completeness != complete → 按 gap_fields 清单（真源）
解析增强补全：`explanation_status = none` → 补 OCR/文字后为 `scan`；核对后 `verified`（不进 gap_fields）
```

两条清单分开，互不拖累。不必人工记「哪些年份没补」。

### 9.5 现状缺口对照

| 缺口 | 实况 | 标注 |
|---|---|---|
| **综合应用题（41–47）** | 2013/2018–2025 的 `questions/` 几乎只有 1–40；2020 有标题无正文 | 整题缺 → `incomplete`/`missing` 或仅 gap 记录 |
| **解析文字** | 2019/21/24/25 无解析；2023 等 OCR 噪声 | **只** `explanation_status`；**不**降 `completeness` |
| **答案键缺失** | 未标 ✅ 的题 | `partial` + `gap_fields:["answer"]`；不进批改默认池 |
| **图题** | 「题 N 图」无图 | `has_figure`+`figure_status=missing` + `gap_fields` 含 `figure` |
| **KP 覆盖** | 对不进 162 KP | coverage gap，禁止硬贴 |

### 9.6 ★ gap inventory（正式产物，不是「处理失败」）

```text
L3 数据
   ├── complete          ← 正常资产
   └── gap               ← 一等公民产物
        ├── answer
        ├── figure
        ├── knowledge_points
        └── question_body   (stem / options / sub_questions)
```

| 观念 | |
|---|---|
| **旧（错）** | 缺答案/缺 KP/缺图 = 处理失败 |
| **新（定）** | 缺口是**清单资产**；有 gap 记录 = 处理成功地识别了缺口 |

**产物路径**（每次 build/ingest 后落盘）：

```text
knowledge/exams/gap_inventory.jsonl
```

**记录格式**（一行一缺口）：

```json
{
  "asset": "question:2019-Q34",
  "year": 2019,
  "gap_type": "answer",
  "gap_fields": ["answer"],
  "completeness": "partial",
  "source": "knowledge/exams/2019/items.md",
  "note": "站点答案表未标 ✅",
  "status": "open"
}
```

| gap_type | 含义 |
|---|---|
| `question_body` | 缺题干/选项/小问 |
| `answer` | 缺 answer_key / reference_answer |
| `figure` | 缺题图 |
| `knowledge_points` | kp_ids 空或无法锚定 |
| `comprehensive` | 年卷综合题整段缺失（挂在 `paper:YYYY`） |

**补全回路（冻结）**：

```text
gap inventory
    ↓ 找到缺口
补原始资料
    ↓ 只解析缺口字段
重新入库受影响资产（按 question_id 定点更新）
    ↓ 状态 open → filled
不必重跑 2009–2025 全量
```

**纪律**：

1. build/ingest **必须**同步产出 gap inventory（含 `status: open`）  
2. 补资料后改 `status: filled` + `filled_at` / `filled_source`  
3. 禁止把 gap 记录当报错清掉；**清单本身就是交付物**  
4. 质量抽检看两份：正常题抽样 + gap 清单抽样

### 9.7 批量策略（两阶段）

```text
2009–2017 批量 → 质量抽检 → 2018–2025 批量 → 最终 Gate
```

| 阶段 | 验证点 |
|---|---|
| 2009–2017 | **历史资料格式变化**（排版/答案来源/扫描质量） |
| 质量抽检 | 正常题 + gap 清单双抽样 |
| 2018–2025 | 与试点同格式的收口 |
| 最终 Gate | `retrieval_gate` + 全量 gap inventory |

**不做**：2009→2025 一把梭。

---

## 10. assesses 锚定流程

```text
1. 解析 items.md → question_id 列表
2. 每题标 kp_ids
   - 选择/填空：整题 kp_ids
   - 综合题：先标 sub_questions[].kp_ids，再取并集写入整题 kp_ids
3. 写 links.jsonl（V1 整题粒度，不写小问边）：
   {"from": "question:2019-Q41", "to": "ds.tree.bst", "type": "assesses"}
   {"from": "question:2019-Q41", "to": "ds.tree.traversal", "type": "assesses"}
4. 小问映射存 items 元数据 sub_questions（不进 links）
5. 反查：KP → 历史考次统计；L2 related_exams → 必须能解析到 question_id
6. GAP：对不上的题/小问写 coverage_report，禁止硬贴最近节点
```

**L2 `related_exams` 验收**：`question:YYYY-QN` 必须存在于 items，否则链接悬空。  
（将来若支持 `question:2019-Q41#2`，仍须能落到同题的 sub_questions。）

---

## 11. 质检清单（设计验收，非入库）

- [ ] `kb_depth=exams` + `doc_role ∈ {exam_paper, exam_item, exam_answer}`  
- [ ] `paper.md` 不进主 RAG（`doc_role=exam_paper` 可识别/可过滤）  
- [ ] `section_id = exam-YYYY-QN`（冻结）  
- [ ] chunk_id：`exam-YYYY-QN-items-NNN` / `exam-YYYY-QN-answer-NNN`（全库唯一，不冲突）  
- [ ] `question_id` = `YYYY-QN`，与 `question:` 前缀可互转  
- [ ] `source_type` + `credibility` 必填（题级可覆盖卷级）  
- [ ] `credibility ∈ {high, medium, low}`（不是来源枚举）  
- [ ] item **正文无答案**（无「答案：」「✅」）；答案仅 metadata  
- [ ] `answer_key` 与正文选项一致（choice）  
- [ ] `answer_key` / `reference_answer` 与 `question_type` 对照表一致（互斥，另一侧 `null`）  
- [ ] assesses：`UNIQUE`、to 存在、from 前缀 `question:`（**整题**）  
- [ ] 综合题：`sub_questions[].id = YYYY-QN-K` 与正文 `（K）` 对齐  
- [ ] 综合题：整题 `kp_ids` = 小问 `kp_ids` 并集  
- [ ] 小问 KP 不得写入 links 作为独立 from（V1）  
- [ ] 小问答案：客观结果用 `answer_key`，推导/代码用 `reference_answer`  
- [ ] L2 `related_exams` 可解析  
- [ ] 无书商/页码/应试话术  
- [ ] 无 L2 方法步骤混进题干  
- [ ] `has_figure` 必填；`true` 时 `figure_status ∈ {present, missing}`  
- [ ] `figure_status=missing` 时 Agent 明示缺图，不编造图形  
- [ ] `gap_status ∈ {none, missing, partial}`；详情以 `gap_fields` 为准  
- [ ] `gap_fields` 不含 `explanation`（解析只归 `explanation_status`）  
- [ ] `complete` 允许 `explanation_status=none`（无解析不降完整度）  
- [ ] 整题缺失不臆补、不进正常题目 RAG  
- [ ] 无题干（`stem` ∈ `gap_fields` 或 `incomplete`）不进正常题目检索  
- [ ] `explanation_status` 必填 ∈ `{none, scan, verified}`  
- [ ] `scan` 仅表示「有文字、未校验」；纯扫描无文字必须是 `none`  
- [ ] `scan`/`none` 不得当作有解析文本使用（Agent 规则）  

---

## 12. 不做

- 不镜像「王道真题讲解」结构  
- 不把方法写进 L3 题干  
- 不为「题型名」造 KP  
- 不用 `recall` 冒充原题（`source_type=recall` + `credibility=low`）  
- 不在缺解析年份硬造解析  
- **不把小问提升为独立资产 / 不把 assesses from 改成 subquestion（V1）**

---

## 13. 决策点汇总

| # | 主题 | 状态 | 结论 / 待定 |
|---|---|---|---|
| **D0** | **综合题小问粒度** | **已定方向** | Question 主资产 + `sub_questions[]`（id/kp_ids/答案字段）；**V1 assesses 仍挂整题**；预留 `question:YYYY-QN#K` |
| **D0b** | **答案字段拆分** | **已定方向** | `answer_key` 仅客观题（choice=`A`–`D` / fill=`string[]`）；`reference_answer` 仅综合/主观；互斥，另一侧 `null` |
| **D1** | **文件布局** | **已定方向** | **C + paper 溯源**：`items.md`+`answer.md` 进主 RAG；`paper.md` 保留整卷语境/溯源，**默认不进主 RAG** |
| **D2** | **来源 / 可信度 / 解析状态** | **已定方向** | `source_type`（official/third_party/recall）≠ `credibility`（high/medium/low）；题级可覆盖 |
| **D2b** | **`explanation_status`** | **已冻结** | `none` \| `scan` \| `verified`；**scan = 有文字、未校验**（纯图无文字 = `none`）；scan 参考+提示；none 不假装有解析 |
| **D2c** | **`has_figure` / `figure_status`** | **已冻结** | 正式 Schema；`present`/`missing`；缺图时明说「知识库缺失题图」，禁止脑补 |
| **D3** | **section_id / chunk_id** | **冻结+修订** | `section_id=exam-YYYY-QN` 不变；chunk_id 改为 `exam-YYYY-QN-{items\|answer}-NNN`（防 items/answer 撞 ID）；paper `exam-YYYY-paper-NNN` |
| **D4** | **答案位置** | **已冻结** | **只进 metadata**（`answer_key`/`reference_answer`）；item 正文仅题干+选项；否决正文 ✅ / 双写 |
| **D5** | **目录与集合** | **已定方向** | 目录 `knowledge/exams/YYYY/`；集合**最终 `exams`**；`questions` 仅迁移期 alias，不永久保留 |
| **D6** | **综合题数据缺口策略** | **已定稿** | 真实数据优先；`gap_fields` 为真源，`gap_status` 仅 `none/missing/partial`；`completeness` 不含解析；缺则记 gap 不臆补 |

全部决策点已定稿 → 试点 2019 → ingest + assesses + 回链/负向 + `retrieval_gate` → 再扩年份。
