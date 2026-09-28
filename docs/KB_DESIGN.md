# RAG 知识库重设计（KB Architecture v2）

> 依据业务划分（用户定稿）：
> **基础知识（四科）→ 进阶（王道）→ 真题 → 学习路径规划**，下挂 **Relation（知识点关系）**。
> 迁移与门禁见 §7。与 `ARCHITECTURE.md` 冲突时，知识库结构以本文为准。

---

## 1. 目标与原则

| 目标 | 含义 |
|---|---|
| **四块分责** | 基础 / 进阶 / 真题 / 学习路径 各管一类问题 |
| **检索可路由** | 按查询意图加权，避免概念与真题互相抢 top-k |
| **可信度可过滤** | 真题分大纲原题 / 第三方原题 / 回忆版 |
| **关系可扩展** | 考点把四块串起来（出题、批改、规划） |
| **可回归** | 迁移后必须过 `retrieval_gate` + `probe_gate` |

原则：Relation **不进向量主池**；假 embedding 结论不外推。

---

## 2. 逻辑模型（四块 + 一层关系）

```text
                         EDU-Agent KB
                               │
     ┌─────────────┬───────────┼───────────┬─────────────┐
     ▼             ▼           ▼           ▼             │
 基础知识        进阶         真题      学习路径规划       │
 (Basics)     (Advanced)    (Exams)   (Learning Path)    │
     │             │           │           │             │
     └─────────────┴───────────┴───────────┴─────────────┘
                               ▼
                        Relation Layer
                      知识点关系 / 考点映射
```

| 块 | 内容 | 主要服务 |
|---|---|---|
| **基础知识** | 数据结构 / 组成原理 / 操作系统 / 计算机网络 讲义 | 概念讲解、原理问答 |
| **进阶** | 王道 408 系列（强化、题型、技巧） | 备考深化、专项突破 |
| **真题** | 2009–2025 试卷、选项、答案、解析 | 练习、出题仿写、批改 |
| **学习路径规划** | 阶段计划、科目顺序、重点章节 | 规划与进度建议 |
| **Relation** | 考点树、别名、内容↔考点锚定 | 扩展召回、错题回链、规划取材 |

---

## 3. 目录结构

```text
knowledge/
  basic/                          # 基础知识
    data_structure/
    computer_organization/
    operating_system/
    computer_network/
  advanced/                       # 进阶（王道）
    wangdao/                      # 王道讲义/强化（按四科可再分子目录）
    tactics/                      # 题型与技巧（若与王道材料拆开）
  exams/                          # 真题
    items/                        # 按题：YYYY_408_exam.md
    papers/                       # 整卷 md
    answers/                      # 答案解析 md
  learning_path/                  # 学习路径规划
    plans/                        # 阶段计划、月/周安排
    routes/                       # 科目顺序、重点章节路线
  relation/                       # 知识点关系（非向量主库）
    knowledge_graph.jsonl
    links.jsonl
```

### 现状迁入

| 现路径 | 迁入 | `kb_part` |
|---|---|---|
| 四科讲义 `knowledge/{ds,co,os,cn}/` | `basic/…` | `basic` |
| 各科常考题型、解题模板 | `advanced/tactics/` 或 `advanced/wangdao/…` | `advanced` |
| `learning_paths/` | `learning_path/` | `learning_path` |
| `questions/*_408_exam.md` | `exams/items/` | `exams` |
| `papers-rebuild/*.md` | `exams/papers/` | `exams` |
| `answers/*-answer.md` | `exams/answers/` | `exams` |

> **王道材料**：若你本地有 PDF/笔记，放入 `advanced/wangdao/`，按四科分子目录；入库时 `doc_role=wangdao`。

---

## 4. 向量集合

**首期推荐**：集合跟「块」走，学科进 metadata（真题跨四科）。

```text
collections:
  basic_data_structure
  basic_computer_organization
  basic_operating_system
  basic_computer_network
  advanced_kb
  exam_bank
  learning_path_kb
```

若要少集合，也可压成 4 个：`basic_*` 保留四科，`advanced_kb` / `exam_bank` / `learning_path_kb`。

### 查询意图默认加权

| 任务 | basic | advanced | exams | learning_path |
|---|---|---|---|---|
| 概念/原理 | **高** | 中 | 低 | 低 |
| 深化/题型技巧 | 中 | **高** | 中 | 低 |
| 出题/练习 | 中 | 中 | **高** | 低 |
| 批改 | 中 | 中 | **高** | 低 |
| 怎么规划复习 | 低 | 中 | 低 | **高** |

权重进 `recall` 路由表，不改门禁指标定义。

---

## 5. 元数据 Schema

| 字段 | 取值 | 说明 |
|---|---|---|
| `kb_part` | `basic` / `advanced` / `exams` / `learning_path` | 四块 |
| `doc_role` | `textbook` / `wangdao` / `tactic` / `exam_item` / `exam_paper` / `exam_answer` / `plan` | 细类 |
| `subject` | `data_structure` / `computer_organization` / `operating_system` / `computer_network` / `mixed` | 学科 |
| `exam_year` | 2009–2025 | 真题 |
| `exam_id` | 如 `2021-Q5` | 按题 |
| `credibility` | `syllabus` / `third_party` / `recall` | 真题可信度 |
| `knowledge_points` | JSON 列表 | 已有 tagger |

**可信度**：`syllabus`（大纲原题）> `third_party`（第三方原题/重排）> `recall`（回忆版，默认批改不用）。

---

## 6. Relation Layer

| 能力 | 用途 |
|---|---|
| 考点层级 | 章节树 + 别名（CPU↔中央处理器） |
| 锚定 | 真题/王道题 → 考点 |
| 扩展 | 概念命中后带 1~2 条真题/例题 |
| 规划 | 路径节点 → 应读 basic/advanced 章节 + 练习真题 |
| 回链 | 批改错题 → 薄弱考点 → basic 章节 |

存储：`relation/*.jsonl`，**不建图数据库、不进 RRF 主池**。

---

## 7. 迁移与回归

| 步骤 | 动作 | 验收 |
|---|---|---|
| M1 | 建 `basic/ advanced/ exams/ learning_path/ relation/` | 目录符合 §3 |
| M2 | 文件迁入；写 `kb_part`/`doc_role`/`exam_*`/`credibility` | 抽样 metadata 正确 |
| M3 | `ingest` 类目与集合名对齐 | `rag.ingest --rebuild` 成功 |
| M4 | `recall` 按 `kb_part` 加权（默认≈现行为） | 门禁不红 |
| M5 | 重录门禁/探针基线 | `--update-baseline` 并说明 |
| M6 | Relation 最小 JSONL | 可查 exam→kp |

**硬门禁**：`retrieval_gate` + `probe_gate`。未过门禁禁止删旧集合。

---

## 8. 代码落点

| 模块 | 改动 |
|---|---|
| `rag/ingest.py` | 目录与 `DEFAULT_CATEGORIES` |
| `rag/recall.py` | `kb_part` 加权 |
| `rag/_metadata_spec.py` | 新字段 |
| `evaluation/retrieval_gate.py` | 类目映射 |
| `scripts/convert_rebuild_papers.py` | 输出到 `exams/items` |

---

## 9. 分期

| 期 | 内容 |
|---|---|
| **P0** | 四块目录 + metadata + 集合映射（行为≈现状） |
| **P1** | 召回按块加权 |
| **P2** | Relation + 学习路径取材 |
| **P3** | 可信度过滤、王道材料扩量 |

---

## 10. 不做

- Relation 不做第四向量库  
- 不用启发式猜选项/答案  
- 门禁未过不删旧集合  
- 假 embedding 涨跌不外推  

---

## 11. 成功判据

1. 概念题证据以 **basic** 为主；技巧题以 **advanced** 为主；练习批改以 **exams** 为主  
2. 规划类问题优先命中 **learning_path**  
3. 真题带 `exam_id` + `credibility`  
4. 门禁 6 路由 + 探针 5 条可回归  
