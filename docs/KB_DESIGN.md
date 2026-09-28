# RAG 知识库设计（定稿）

> 状态：设计定稿（2026-09-28）  
> 链路模型：**基础知识 → 知识点 → 王道 → 真题**；**学习路径**独立。  
> 实现迁移见 §8（本期只交付设计，不改代码/目录）。

---

## 1. 目标

1. 内容按学习深度分层（L1 基础 / L2 王道 / L3 真题），检索可路由。  
2. **统一知识点体系**串联三层，服务扩展召回、批改回链、路径取材。  
3. 学习路径独立成库，直接服务 **L1/L2/L3 分级**与规划。  
4. 真题可溯源、可信度可过滤。

---

## 2. 逻辑模型

```text
                    408 知识库
                         │
          ┌──────────────┴──────────────┐
          ▼                             ▼
     内容体系 Content              学习体系 Learning Path
          │                             │
          ├─ L1 基础知识 basic          ├─ L1 基础学习路径
          │    └─ 四科                 │
          ├─ Knowledge Point           ├─ L2 408 强化路径
          │    └─ 统一知识点体系        │
          ├─ L2 王道 advanced           └─ L3 真题训练路径
          │    └─ 四科
          └─ L3 真题 exams
               └─ 2009 … 2025
```

| 单元 | 职责 | 检索角色 |
|---|---|---|
| **basic** | 四科概念/原理讲义 | 向量主库；L1 主力 |
| **knowledge_points** | 统一考点树 + 别名 + 锚定 | **关系层**（不进 RRF 主池） |
| **advanced** | 王道 408：深化、题型、技巧 | 向量主库；L2 主力 |
| **exams** | 真题：试卷/题目/答案解析 | 向量主库；L3 主力 |
| **learning_paths** | 学习阶段与路线 | 独立库；规划 + L1/L2/L3 分级依据 |

---

## 3. 目录结构（定稿命名）

```text
knowledge/
├── knowledge_points/              # 统一知识点（关系层）
│   ├── ds.jsonl                   # data_structure
│   ├── co.jsonl                   # computer_organization
│   ├── os.jsonl                   # operating_system
│   ├── cn.jsonl                   # computer_network
│   └── links.jsonl                # teaches / assesses / trains
│
├── basic/                         # L1 基础知识
│   ├── data_structure/
│   ├── computer_organization/
│   ├── operating_system/
│   └── computer_network/
│
├── advanced/                      # L2 王道（进阶）
│   ├── data_structure/
│   ├── computer_organization/
│   ├── operating_system/
│   └── computer_network/
│
├── exams/                         # L3 真题（按年）
│   ├── 2009/
│   │   ├── paper.md               # 整卷
│   │   ├── items.md               # 按题（选项/答案）
│   │   └── answer.md              # 解析
│   ├── 2010/
│   │   └── …
│   └── 2025/
│
└── learning_paths/                # 学习路径（独立）
    ├── l1_basic/
    ├── l2_advanced/
    └── l3_exams/
```

### 3.1 现状迁入

| 现路径 | 迁入 |
|---|---|
| `knowledge/{data_structure,computer_organization,operating_system,computer_network}/**` | `basic/<subject>/` |
| 各科 `*常考题型*`、解题模板、王道素材 | `advanced/<subject>/` |
| `questions/YYYY_408_exam.md` | `exams/YYYY/items.md` |
| `papers-rebuild/YYYY.md` | `exams/YYYY/paper.md` |
| `answers/YYYY-answer.md` | `exams/YYYY/answer.md` |
| `learning_paths/**` | `learning_paths/`（再拆 l1/l2/l3） |
| （新建）考点表 | `knowledge_points/{ds,co,os,cn}.jsonl` + `links.jsonl` |

---

## 4. Knowledge Point（统一知识点体系）

### 4.1 定位

- **存储**：`knowledge_points/<subject_code>/*.jsonl` + 全局 `links.jsonl`。  
- **不是**第四向量主库，不参与 `weighted_rrf_merge` 主池。  
- **id 全局唯一**：`<subject_code>.<path>`，如 `os.file.disk_free_space`。

**subject_code**：`ds` / `co` / `os` / `cn`。

### 4.2 `level` 语义（禁止误读）

| level | 含义 | 例 |
|---|---|---|
| 1 | 学科根 | `os` |
| 2 | 一级知识域 | `os.file` |
| 3 | 二级域 / 主要考点 | `os.file.physical` |
| 4 | 细粒度考点 | `os.file.disk_free_space` |

**`level` = 分类树结构深度，不是难度、重要度、考试频率。**  
（`co.cpu.pipeline` 可以 level=3 但比多数 level=4 更难。）  
**V1 不提供 `difficulty`**：难度挂在 Question / Content Chunk 上，不挂在 KP 上（KP 是「知识是什么」；`2019-Q11` 才可以是难题）。  
L1/L2/L3 由 `kb_depth` + learning_paths 决定。

**`node_kind` ↔ `level`（相关但非严格 1:1）**：

| node_kind | level |
|---|---|
| `subject` | **1** |
| `domain` | **2** |
| `topic` | **3** |
| `point` | **3 或 4** |

- 禁止：`subject≠1`、`domain≠2`、`topic≠3`。  
- 允许：`co.cpu.pipeline` 为 `node_kind=point` 且 `level=3`（可直接学/考，不必为「叶子」硬拆 level 4）。  
- `point` 在 4 表示更细的拆分子项。

### 4.3 节点 Schema

| 字段 | 类型 | 必填 | 取值 / 规则 |
|---|---|---|---|
| `id` | string | ✓ | `^(ds\|co\|os\|cn)\.[a-z0-9_]+(\.[a-z0-9_]+)*$`；**slug 英文，一经发布不改** |
| `name` | string | ✓ | 规范中文名，≤40 字；可改名，**不改 id** |
| `subject` | enum | ✓ | `ds`/`co`/`os`/`cn`，与 id 前缀一致 |
| `parent_id` | string\|null | ✓ | 引用父 KP 的 `id`；根为 null |
| `level` | int | ✓ | 1–4，**仅树深** |
| `node_kind` | enum | ✓ | `subject` / `domain` / `topic` / `point` |
| `type` | enum | ✓ | `concept` / `principle` / `algorithm` / `structure` / `protocol` / `method` / `term` |
| `importance` | enum | ✓ | `core` / `major` / `minor` |
| `typical_question_types` | string[] | ✓ | **典型/允许考法**（非历史统计） |

**`typical_question_types` 枚举**：`choice` / `fill` / `calculation` / `comprehensive` / `code` / `design`。

**`typical_question_types` 语义**：该 KP **典型/允许的考法**（课程与考纲视角）。  
**不是**历史统计——历史分布由 `question ──assesses──→ KP` **动态计算**。V1 不必追绝对精确。

**`importance` 语义**：知识体系中的地位（core/major/minor），**不是**真题频次。  
「近 N 年考过几次 / 最近出现年份」一律从 `assesses` 边统计，禁止写回 `importance`。
| `aliases` | string[] | | 曾用名、别名、英文（**中文改名时旧名迁入此处**） |
| `tags` | string[] | | **仅**非结构化：`易错` / `易混` / `陷阱`…**禁止**核心/高频/大题 |
| `status` | enum | ✓ | `active` / `deprecated` |
| `replaced_by` | string[] | | **数组**；仅 `status=deprecated` 时必填 |

**约束**：

- **`node_kind` ↔ `level`**：`subject=1`，`domain=2`，`topic=3`，`point=3|4`（见 §4.2）。  
- `domain` 的 `parent_id` 必须是 `subject|domain`。  
- 检索/出题/路径默认只落在 `node_kind ∈ {topic, point}`。  
- `importance` / `typical_question_types` **不得**写入 `tags`。  
- **id 冻结**：slug 用英文（`binary_search` 不用 `折半查找`）；中文规范名变更只改 `name`，旧名进 `aliases`。  
- **粒度原则**：一个 KP = 真题可**单独考查**的语义单元。若子节点必须与父节点一起考才成立，则应合并；若子节点可被单题独立指向（如 TCP vs tcp_handshake），则拆分。`aliases` 只放同义名，不放「关联但不同的知识」（生产者消费者 ≠ PV，可另建 `classic_sync`）。

**废弃（含 1 拆 N）**：

```json
{
  "id": "os.mem.legacy_memory",
  "status": "deprecated",
  "replaced_by": ["os.mem.virtual_memory", "os.mem.page_replacement"]
}
```

示例：

```json
{
  "id": "os.file.disk_free_space",
  "name": "磁盘空闲空间管理",
  "subject": "os",
  "parent_id": "os.file.physical",
  "level": 3,
  "node_kind": "point",
  "type": "method",
  "importance": "core",
  "question_types": ["choice", "calculation"],
  "aliases": ["位示图", "空闲表", "空闲链表"],
  "tags": ["易错"],
  "status": "active"
}
```

### 4.4 边（`links.jsonl`）

```json
{
  "from": "question:2019-Q11",
  "to": "os.file.disk_free_space",
  "type": "assesses"
}
```

| 端 | 含义 |
|---|---|
| **`from`** | **资产引用** `asset_type:asset_id` —— 必须能定位到具体资产 |
| **`to`** | **KP id** —— 必须存在于 `*.jsonl` 节点表 |
| **`type`** | `teaches` / `assesses` / `trains` |

#### asset_ref 统一格式

```text
<asset_type>:<asset_id>
```

| asset_type | asset_id 形态 | 例 |
|---|---|---|
| `paper` | 年份 | `paper:2019` |
| `question` | `YYYY-QN` | `question:2019-Q11` |
| `basic` | `<relpath>#<section>` | `basic:os/file.md#磁盘空闲` |
| `advanced` | `<relpath>#<section>` | `advanced:os/文件大题.md#位示图` |
| `practice` | 题目稳定 id | `practice:wangdao-os-023` |
| `learning_path` | 路径节点 id | `learning_path:path.l2.os.memory` |

**解析规则**：按**第一个** `:` 切成 `asset_type` + `asset_id`；`asset_type` 为封闭枚举，**禁止**各数据源自造前缀。

**完整性约束**：`UNIQUE(from, type, to)` —— 同一资产、同一关系、同一考点**至多一条边**，否则「KP 被多少真题考过」等统计会被重复边污染。

**一对多**：一道真题 **必须允许** 连多个 KP（综合题）：

```json
{"from": "question:2022-Q25", "to": "os.process.sync", "type": "assesses"}
{"from": "question:2022-Q25", "to": "os.process.pv", "type": "assesses"}
{"from": "question:2022-Q25", "to": "os.memory.paging", "type": "assesses"}
```

禁止「一题只锚一个 KP」。

### 4.4.1 KP Coverage Test（反向检查）

骨架上线后必须用 **2009–2025 真题** 做覆盖测试：

```text
question → 能否落到现有 KP？
  ✅ 有明确 KP     → 写 assesses 边
  ❌ KP GAP       → 先记 gap，禁止硬贴最近节点
```

对每个 GAP 三选一：

| 判断 | 动作 |
|---|---|
| 现有 KP 太粗 | **拆分** |
| 考纲有但树里没有 | **新增 KP** |
| 一题综合多点 | **多条 assesses**（合法） |

产出：`knowledge_points/coverage_report.md`（gap 清单 + 处置）。

| type | 语义 | from（asset_type） | to |
|---|---|---|---|
| **`teaches`** | 讲解该考点 | `basic` / `advanced` | KP |
| **`assesses`** | 考查该考点 | `question` | KP |
| **`trains`** | 强化/训练该考点 | `practice` | KP |

```text
基础教材  ──teaches──→  KP
真题题   ──assesses──→ KP
王道/专项 ──trains──→   KP
```

**真题层级**：

```text
paper:2019
  └── question:2019-Q11
            └── assesses → KP
```

**学习路径不进 links**；路径节点用 `kp_ids[]`（`from` 侧如需反查可用 `learning_path:path.l2.os.memory` 作工具索引，但**不作 teaches/assesses/trains 边**）：

```json
{
  "id": "path.l2.os.memory",
  "title": "内存管理强化",
  "level": "L2",
  "kp_ids": ["os.mem.page", "os.mem.segment", "os.mem.virtual"],
  "materials": ["advanced:os/内存强化.md", "question:2021-Q28"]
}
```

### 4.5 文件布局

```text
knowledge/knowledge_points/
├── ds.jsonl
├── co.jsonl
├── os.jsonl
├── cn.jsonl
└── links.jsonl
```

- **`links.jsonl` 全库一个**：边是整张 Knowledge Graph 的集合；查询「KP → 全部真题/基础/王道」时单文件最方便。规模到几十万条再考虑按科拆。  
- 节点按学科四文件，便于分科维护与 diff。

### 4.5.1 首批叶节点构建策略

**原则**：以**现有真题 + 已有讲义/王道材料反推**为主，**考纲作骨架约束**（只定 level1–2 域与命名边界）。

| 步骤 | 做法 |
|---|---|
| 1 骨架 | 按考纲建 `subject` + `domain`（level 1–2），定 `parent_id` 树 |
| 2 反推叶 | 从 `exams` 的 `assesses` 候选、`basic`/`advanced` 标题与 `knowledge_tagger` 抽 **topic/point** |
| 3 收敛 | 同义合并进 `aliases`；id 用英文 slug 并冻结 |
| 4 锚定 | 反写 `links.jsonl`（teaches/assesses/trains） |
| 5 补缺 | 讲义有而真题未考的仍建 KP（标 `importance`），真题有而讲义无的标 `tags:["需补讲义"]`（可选） |

**不做**：一次按考纲铺满全部细枝；优先覆盖**当前语料与 2009–2025 真题已出现**的考点。

### 4.6 用法

| 场景 | 行为 |
|---|---|
| L1 概念 | KP → `teaches` → basic 章节 |
| L2 题型 | KP → `trains` + advanced |
| L3 练习/批改 | `assesses` 真题；错题 → KP → `teaches` 回 basic |
| 学习路径 | `path.kp_ids` → 拉 material |
| 门禁 | 黄金集 `knowledge_points` 对齐 KP **id** |

---

## 5. 元数据

| 字段 | 取值 | 说明 |
|---|---|---|
| `kb_depth` | `basic` / `advanced` / `exams` / `learning_path` | 与顶层目录一致 |
| `doc_role` | `textbook` / `wangdao` / `tactic` / `exam_paper` / `exam_item` / `exam_answer` / `plan` | 细类 |
| `subject` | 四科或 `mixed` | |
| `exam_year` | 2009–2025 | 仅真题 |
| `question_id` | `YYYY-QN` | 按题；链上用 `question:YYYY-QN` |
| `credibility` | `syllabus` / `third_party` / `recall` | 真题可信度 |
| `knowledge_points` | JSON 列表 | 指向 KP id |

可信度：`syllabus`（大纲原题）> `third_party`（第三方原题/重排）> `recall`（回忆版；批改默认不用）。

---

## 6. 向量集合（首期）

```text
basic_data_structure
basic_computer_organization
basic_operating_system
basic_computer_network
advanced_data_structure
advanced_computer_organization
advanced_operating_system
advanced_computer_network
exams
learning_paths
```

`knowledge_points` 不建向量集合（或仅建同名映射表，不进召回主路径）。

---

## 7. L1 / L2 / L3

### 7.1 内容侧重

| 层 | 主集合 | 辅助 |
|---|---|---|
| L1 概念 | `basic_*` | KP 定位 |
| L2 对比/题型/强化 | `advanced_*` | basic 作背景；KP 扩展 |
| L3 综合/代码/真题 | `exams` | advanced + basic；KP 扩展 |

### 7.2 学习路径

| 路径 | 内容 |
|---|---|
| `learning_paths/l1_basic/` | 基础顺序、重点章 |
| `learning_paths/l2_advanced/` | 408 强化节奏 |
| `learning_paths/l3_exams/` | 真题训练轮次 |

规划 API 读路径库，再按 KP 拉取对应 basic/advanced/exams 材料。

---

## 8. 迁移与验收（后续实现，非本期）

| 步骤 | 动作 | 验收 |
|---|---|---|
| M1 | 按 §3 建目录并迁文件 | 结构符合定稿 |
| M2 | 写入 §5 元数据 | 抽样正确 |
| M3 | KP 最小表 + 锚定边 | 可查 exam→kp |
| M4 | `ingest` / `recall` 对齐集合名与 `kb_depth` | `rag.ingest --rebuild` 成功 |
| M5 | `retrieval_gate` + `probe_gate` | 通过或重录基线并说明 |

**红线**：未过门禁不删旧集合；假 embedding 结论不外推。

---

## 9. 本期范围

- ✅ 定稿逻辑模型、目录命名、元数据、L1–L3、KP 职责  
- ✅ 迁移映射与验收清单（供 P0）  
- ❌ 不迁移目录、不改 `ingest`/`recall`、不重录基线  

---

## 10. 成功判据（实现后）

1. 概念题证据以 `basic` 为主，强化题以 `advanced` 为主，练习批改以 `exams` 为主  
2. 真题带 `question_id`（`question:YYYY-QN`）+ `credibility`  
3. KP 可支撑 扩展/回链/路径取材  
4. 门禁 6 路由 + 探针 5 条可回归  
