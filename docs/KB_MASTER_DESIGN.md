# EDU-Agent 知识库数据库设计（总册）

> 状态：**定稿整合**（2026-09-28）  
> 范围：L1 Basic + KP + L2 Advanced + L3 Exams + links + gap inventory  
> 分册：`BASIC_DESIGN.md` / `ADVANCED_DESIGN.md` / `EXAMS_DESIGN.md` / `KB_DESIGN.md`（细节以分册为准，冲突以本总册冻结结论为准）  
> 学习路径：独立库，本册只定接口，不在本期落地。

---

## 0. Knowledge Architecture 总览

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
                            主检索     解析检索    溯源
```

| 概念 | 是什么 | 不是什么 |
|---|---|---|
| **KP** | 可被真题单独考查的语义单元 | 题型名 / 技巧名 / 目录镜像 |
| **L1 Basic** | 是什么 / 为什么 / 怎么工作 | 解题技巧、真题 |
| **L2 Advanced** | 题型识别 / 方法 / 流程 / 易错 | 整题+答案、原理长文 |
| **L3 Exams** | 真题战例（题干/选项/答案/解析/卷别） | 方法库 |
| **Exam Asset** | L3 在磁盘/索引里的三种载体 | 第四层内容 |

**知识层只有三层 + KP**；items / answer / paper 是**资产形态**，不是内容层。

---

## 1. Knowledge Point（关系层）

### 1.1 定位

- 存储：`knowledge/knowledge_points/{ds,co,os,cn}.jsonl` + 全局 `links.jsonl`
- **不进** RRF 主池；服务锚定、回链、统计、路径取材
- id 冻结：`^(ds|co|os|cn)\.[a-z0-9_]+(\.[a-z0-9_]+)*$`

**现状**：162 节点（ds 52 / co 39 / os 36 / cn 35）

### 1.2 节点要点（冻结）

| 字段 | 规则 |
|---|---|
| `level` | **树深 1–4**，≠ 难度 |
| `node_kind` | subject=1 / domain=2 / topic=3 / point=3\|4 |
| `importance` | 知识体系地位，≠ 考频 |
| `typical_question_types` | 先验考法；历史频次从 `assesses` 统计 |
| `parent_id` / `replaced_by` | 树结构与弃用 |
| `aliases` | **不跨节点** |
| `ids` | 英文 slug，发布后不改 |

**L2 不创建 KP**：题型名/方法名不是 KP；仅当考试知识体系出现新单元才扩。

---

## 2. 三层内容

### 2.1 L1 Basic（`kb_depth=basic` / `doc_role=textbook`）

| 项 | 约定 |
|---|---|
| 写 | 定义、动机、性质、机制、公式、算法思想 |
| 不写 | 真题答案、王道页码、解题技巧、应试话术 |
| 文档模型 | Domain → Document；Topic/Point → Section |
| 边 | section `teaches` → KP |
| 目录 | `knowledge/basic/{ds,co,os,cn 四科}/` |

**ID 链**：`basic-ds-tree-traversal-001 ⊂ basic-ds-tree-traversal ⊂ basic-ds-tree`

**现状**：27 章全量入库；`teaches` 137 条。

### 2.2 L2 Advanced（`kb_depth=advanced` / `doc_role=method`）

| 项 | 约定 |
|---|---|
| 写 | 题型识别、方法步骤、计算流程、易错、变式、综合拆解 |
| 不写 | 整题+答案全文、长篇原理、书商页码、口诀堆砌 |
| `doc_role=method` | **进阶能力型**应用结构 ≠ 单个技巧 |
| `topic_tags` | 仅检索辅助：选择/计算/代码/填空/分析 |
| `scope` | `single` \| `cross`（cross ⇒ `kp_ids` ≥ 2） |
| `related_exams` | **弱关联**推荐真题；≠ 引用/来源 |
| `difficulty` | 可选 1–5 |
| 边 | section `trains` → KP |
| 目录 | `knowledge/advanced/<subject>/<能力域>.md` |

**ID 链**：`advanced-ds-tree-bst_ops-001 ⊂ advanced-ds-tree-bst_ops`

**现状**：DS `03_tree.md` 试点入库；`trains` 16 条。

### 2.3 L3 Exams（`kb_depth=exams`）

见 §3；`assesses` 629 条，2009–2025 全量。

---

## 3. L3 Exam Assets

### 3.1 三种形态（D1）

```text
knowledge/exams/YYYY/
├── items.md    主检索：题干+选项+答案元数据
├── answer.md   解析检索
└── paper.md    溯源，默认不进主 RAG
```

| 形态 | doc_role | 进主 RAG | 职责 |
|---|---|---|---|
| items | `exam_item` | ✓ | 练习/批改/真题验证入口 |
| answer | `exam_answer` | ✓ | 解析 |
| paper | `exam_paper` | ✗ | 整卷语境/溯源；冲突以 items 为准 |

### 3.2 答案字段（D0b）

| question_type | `answer_key` | `reference_answer` |
|---|---|---|
| choice | `A`–`D` | `null` |
| fill | `string[]` | `null` |
| comprehensive | `null` | 多行参考答案 |

**互斥**，另一侧显式 `null`。小问同理。

### 3.3 答案只进 metadata（D4，冻结）

```text
items 正文   题干+选项（无答案、无 ✅）
metadata     answer_key / reference_answer
```

支撑练习 / 批改 / 讲解三模式；禁止答案进正文。

### 3.4 小问粒度（D0）

```text
question:2019-Q41  →  section exam-2019-Q41
                         ├── exam-2019-Q41-items-001
                         └── exam-2019-Q41-answer-001
  sub_questions[]  2019-Q41-1/2/3 → kp_ids + 答案字段
```

- 小问**不是**独立资产；整题 `kp_ids` = 小问并集
- **V1 assesses 挂整题**；预留 `question:YYYY-QN#K`，不进 links

### 3.5 来源 / 可信度 / 解析 / 图（D2 系列）

| 字段 | 枚举 | 语义 |
|---|---|---|
| `source_type` | `official` \| `third_party` \| `recall` | 从哪来 |
| `credibility` | `high` \| `medium` \| `low` | 有多可信（题级可覆盖） |
| `explanation_status` | `none` \| `scan` \| `verified` | **scan = 有文字、未校验**；纯图无字 = `none` |
| `has_figure` | bool | 题面有无图 |
| `figure_status` | `present` \| `missing` | 图在不在库；missing 时 Agent 明说、不脑补 |

```text
source_type  ≠  credibility
explanation_status 独立于 completeness
figure_status 独立字段
```

---

## 4. ID 体系（冻结）

### 4.1 三层对照

```text
asset_ref          question:2019-Q11
                         ↓
section_id         exam-2019-Q11
                         ↓
chunk_id           exam-2019-Q11-items-001
                   exam-2019-Q11-answer-001
```

| 层 | L1 | L2 | L3 |
|---|---|---|---|
| document_id | `basic-ds-tree` | `advanced-ds-tree` | `exam-2019-items` / `-answer` / `-paper` |
| section_id | `basic-ds-tree-traversal` | `advanced-ds-tree-bst_ops` | `exam-2019-Q11` |
| chunk_id | `<section>-NNN` | `<section>-NNN` | `<section>-{items\|answer}-NNN` |

**L3 特化**：同题双文档，chunk 靠 role 段消歧；**不**套用 `section ⊂ document` 前缀链。  
**校验**：`chunk_id.startswith(section_id)` + 全集合唯一。

### 4.2 asset_ref

```text
<asset_type>:<asset_id>   按第一个 : 切分
```

| asset_type | asset_id | 例 |
|---|---|---|
| `question` | `YYYY-QN` | `question:2019-Q11` |
| `paper` | `YYYY` | `paper:2019` |
| `basic` / `advanced` | section_id | `basic:basic-ds-tree-traversal` |
| `learning_path` | path id | `learning_path:path.l2.os.memory` |

互转：`question:YYYY-QN` ⇄ `exam-YYYY-QN`（题号段不变）。

---

## 5. Metadata（chunk 级）

### 5.1 通用

| 字段 | 取值 |
|---|---|
| `kb_depth` | `basic` / `advanced` / `exams` / `learning_path` |
| `doc_role` | `textbook` / `method` / `exam_item` / `exam_answer` / `exam_paper` / … |
| `subject` | `ds` / `co` / `os` / `cn` / `mixed`（**题目所属学科**，≠ 由 KP 推导） |
| `document_id` / `section_id` / `chunk_id` | §4 |
| `knowledge_points` | JSON 列表字符串 |
| `primary_kp` | 可选，∈ kp_ids |

### 5.2 L2 附加

`topic_tags` / `scope` / `difficulty` / `related_exams`

### 5.3 L3 附加

`question_id` / `exam_year` / `question_type` / `score` / `part`  
`answer_key` / `reference_answer`  
`source_type` / `credibility` / `explanation_status`  
`has_figure` / `figure_status`  
`completeness` / `gap_status` / `gap_fields`  
`sub_questions`（综合题）

### 5.4 completeness 与 gap（D6）

```text
completeness   complete | partial | incomplete   仅题目必要字段（不含解析）
gap_status     none | missing | partial          粗粒度
gap_fields     [stem|options|answer|figure|…]    真源
```

| question_type | complete 条件 |
|---|---|
| choice | 干+选项+`answer_key` |
| fill | 干+`answer_key` |
| comprehensive | 干+小问结构+`reference_answer` |

**无解析 ≠ 不完整**：`complete` + `explanation_status=none` 合法。

---

## 6. links（关系边）

```text
basic section     ──teaches──→  KP
advanced section  ──trains──→   KP     （名称冻结，不用 practices）
question          ──assesses──→ KP
```

| 规则 | |
|---|---|
| 唯一 | `UNIQUE(from, type, to)` |
| 语义主体 | Section / Question，**不是 Chunk** |
| 多 KP | 一题/一节可多边 |
| 学习路径 | **不进**三条边；用 `path.kp_ids` |
| L2→L3 | `related_exams` 弱关联，不是 links 边 |

**现状**：links 782（teaches 137 / trains 16 / assesses 629）

---

## 7. gap inventory（正式产物）

```text
knowledge/exams/gap_inventory.jsonl
```

```text
L3 数据
   ├── complete
   └── gap  ← 一等公民，不是处理失败
        ├── answer
        ├── figure
        ├── knowledge_points
        ├── question_body
        └── comprehensive
```

**补全回路**：

```text
gap inventory → 补原始资料 → 只解析缺口字段
  → 按 question_id 定点更新 → status: open → filled
  → 不必重跑 2009–2025
```

**现状**：273 条 open（answer 160 / kp 60 / figure 42 / comprehensive 11）

---

## 8. 目录与向量集合

### 8.1 目录

```text
knowledge/
├── knowledge_points/     KP + links
├── basic/                L1
├── advanced/             L2
├── exams/                L3（2009–2025）
│   ├── YYYY/{items,answer,paper}.md
│   └── gap_inventory.jsonl
├── learning_paths/       规划（独立，后续）
└── rules/ + schema/      契约
```

### 8.2 向量集合

| 集合 | 内容 | 状态 |
|---|---|---|
| `data_structure` 等四科 | L1（+旧讲义残留） | 在用 |
| `questions` | L3 exams（**迁移期 alias**） | 在用 |
| `exams` | 最终名 | 未建；门禁稳后收口 |
| `learning_paths` | 路径 | 在用 |

**红线**：未过门禁不删旧集合；`questions` 不永久保留。

---

## 9. 质检与门禁

| 门 | 范围 |
|---|---|
| 回链 | ID 链、KP 存在、links UNIQUE、from/to 合法 |
| 负向 | 答案不进 item 正文；无书商话术；缺图不脑补；related_exams 可解析 |
| `retrieval_gate` | 改检索链后必跑；指标 ≥ 基线 |
| `probe_gate` | 细粒度探针；需真实 embedding |
| gap 清单 | 与 items 元数据一致 |

---

## 10. 落地现状（2026-09-28）

| 层 | 资产 | 边 | 门禁 |
|---|---|---|---|
| KP | 162 节点 | — | 校验通过 |
| L1 Basic | 27 章 | teaches 137 | PASS |
| L2 Advanced | DS 树试点 | trains 16 | PASS |
| L3 Exams | 2009–2025 全量 | assesses 629 | PASS |
| gap | inventory 273 | — | 正式产物 |

**跨年份验证**：2019（扫描无解析）+ 2020（OCR 解析/图/跨科/综合缺口）+ 2009–2017（历史答案格式）— Schema / ID / gap **零改动**。

---

## 11. 不做清单（红线）

1. 不为技巧名 / 题型名造 KP  
2. L2 不建 KP  
3. 答案不进 items 正文  
4. 不臆补真题 / 解析 / 图  
5. `gap_status` 不做多缺口编码（真源在 `gap_fields`）  
6. 学习路径不进 teaches/trains/assesses  
7. 未过门禁不删旧集合  
8. 不镜像书商目录；不写王道页码/押题话术

---

## 12. 后续

| 项 | 说明 |
|---|---|
| L2 扩章 | 按 `ADVANCED_DESIGN.md` 目录继续四科 |
| 集合收口 | `questions` → `exams` |
| gap 回填 | 按 inventory 补答案/图/KP，定点更新 |
| 学习路径 | L1/L2/L3 路径库 + `path.kp_ids` |
| 检索路由 | 按 `kb_depth` / `doc_role` 分流（练习禁答案等） |

---

## 13. 分册索引

| 文档 | 内容 |
|---|---|
| **本册** | 总架构 + 冻结结论 |
| `BASIC_DESIGN.md` | L1 细节 |
| `ADVANCED_DESIGN.md` | L2 细节 |
| `EXAMS_DESIGN.md` | L3 细节（D0–D6） |
| `KB_DESIGN.md` | 早期总图（以本册为准） |
| `knowledge/rules/*` | 写作/切分/元数据/门禁规则 |
| `knowledge/schema/*` | JSON Schema |
