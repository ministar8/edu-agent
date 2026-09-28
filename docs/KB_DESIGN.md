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
├── knowledge_points/              # 统一知识点体系（按学科维护）
│   ├── data_structure/
│   ├── computer_organization/
│   ├── operating_system/
│   └── computer_network/
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
| （新建）考点表 | `knowledge_points/<subject>/*.md` 或 `.jsonl` |

---

## 4. Knowledge Point（统一知识点体系）

### 4.1 定位

- **存储**：`knowledge_points/<subject>/`，文件或 JSONL。  
- **不是**第四向量主库，不参与 `weighted_rrf_merge` 主池。  
- **id 全局唯一**：`<subject>.<path>`，如 `data_structure.tree.binary_search`。

### 4.2 节点与边

```json
{
  "id": "operating_system.file.disk_free_space",
  "name": "磁盘空闲空间管理",
  "subject": "operating_system",
  "parent": "operating_system.file.storage",
  "aliases": ["位示图", "空闲表", "空闲链表", "空闲块"],
  "level": 3
}
```

锚定边（`links.jsonl`）：

| type | 含义 |
|---|---|
| `teaches` | basic/advanced chunk → KP |
| `assesses` | exam_id → KP |
| `practices` | learning_path 节点 → KP |

### 4.3 用法

| 场景 | 行为 |
|---|---|
| L1 概念 | 命中 KP → 定位 basic 章节 |
| L2 题型 | KP → advanced 讲解/技巧 |
| L3 练习/批改 | KP → 真题与解析；错题回链 KP |
| 学习路径 | 路径阶段 → KP 集合 → 推荐材料 |

---

## 5. 元数据

| 字段 | 取值 | 说明 |
|---|---|---|
| `kb_depth` | `basic` / `advanced` / `exams` / `learning_path` | 与顶层目录一致 |
| `doc_role` | `textbook` / `wangdao` / `tactic` / `exam_paper` / `exam_item` / `exam_answer` / `plan` | 细类 |
| `subject` | 四科或 `mixed` | |
| `exam_year` | 2009–2025 | 仅真题 |
| `exam_id` | `YYYY-QN` | 按题 |
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
2. 真题带 `exam_id` + `credibility`  
3. KP 可支撑 扩展/回链/路径取材  
4. 门禁 6 路由 + 探针 5 条可回归  
