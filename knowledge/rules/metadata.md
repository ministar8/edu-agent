# Metadata Rules

KB 元数据与 links 契约。

---

## 1. 内容资产

| 字段 | 说明 |
|---|---|
| `kb_depth` | `basic` / `advanced` / `exams` / `learning_path` |
| `doc_role` | `textbook` / `method`（L2） / `tactic` / `exam_paper` / `exam_item` / `exam_answer` / `plan` |
| `subject` | `ds` / `co` / `os` / `cn` / `mixed` |
| `document_id` / `section_id` / `chunk_id` | 见 chunking.md |
| `knowledge_points` | JSON 数组字符串（section.kp_ids） |
| `primary_kp` | section 可选 |

真题另有：`exam_year` / `question_id`（`YYYY-QN`）/ `credibility`。

---

## 2. KP 节点

见 `schema/knowledge_point.schema.json`。

要点：

- `level` = 树深 ≠ 难度  
- `importance` = 知识体系地位 ≠ 考频  
- `typical_question_types` = 先验考法 ≠ 历史  
- 历史考次：`question ──assesses──→ KP` 动态统计  

---

## 3. links（`knowledge_points/links.jsonl`）

```json
{"from": "basic:basic-ds-tree-traversal", "to": "ds.tree.traversal", "type": "teaches"}
```

| 字段 | 规则 |
|---|---|
| `from` | `asset_type:asset_id`（封闭枚举） |
| `to` | KP id |
| `type` | `teaches` \| `assesses` \| `trains` |

### asset_type

| type | from 侧 | 语义 |
|---|---|---|
| `teaches` | `basic` | 讲解 |
| **`trains`** | `advanced` | L2 针对 KP 的题型/方法/应用训练（**名称冻结**，不用 practices） |
| `assesses` | `question` | 考查 |

```text
basic section     ──teaches──→  KP
advanced section  ──trains──→   KP
question          ──assesses──→ KP
```

- 学习路径 **不进** 三条边；用 `path.kp_ids`  
- **语义主体 = Section**，不是 Chunk  
- **UNIQUE(from, type, to)**  
- 一题可多 KP（综合题多条 assesses）  

### asset_ref 解析

按**第一个** `:` 切 `asset_type` + `asset_id`。

| asset_type | asset_id 例 |
|---|---|
| `paper` | `2019` |
| `question` | `2019-Q11` |
| `basic` / `advanced` | `basic-ds-tree-traversal` 或 `relpath#section` |
| `practice` | `wangdao-os-023` |
| `learning_path` | `path.l2.os.memory` |

---

## 4. 校验

1. KP id 正则与 subject 前缀  
2. parent_id 存在  
3. node_kind ↔ level  
4. deprecated ⇒ replaced_by  
5. links：UNIQUE、to 存在、type/from 匹配  
