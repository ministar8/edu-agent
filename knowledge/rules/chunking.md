# Chunking Rules

Section → Chunk 切分规范。

---

## 1. 分层

```text
Document  →  Domain 语境
Section   →  语义关系主体（teaches / kp_ids）
Chunk     →  检索载体（向量、RAG top-k）
```

**Chunk 不生成 teaches 边**；避免一节切 N 块产生 N 条重复关系。

---

## 2. 切分顺序

1. 按 H2/H3 定 **Section**（边界即 section_id）  
2. Section 内再切 **Chunk**（沿用 `rag.splitter`：语义单元贪心合并）  
3. 代码块 / 公式块 / 表格 **保持完整**（不跨 chunk 硬切）

---

## 3. ID

| 层 | 格式 | 例 |
|---|---|---|
| document_id | `basic-<subject>-<domain_slug>` | `basic-ds-tree` |
| section_id | `<document_id>-<section_slug>` | `basic-ds-tree-traversal` |
| chunk_id | `<section_id>-<NNN>` | `basic-ds-tree-traversal-001` |

- subject：`ds` / `co` / `os` / `cn`  
- id **冻结**（改标题不改 id）  
- NNN 三位，按切分顺序  

---

## 4. 最小长度

- 沿用 `MIN_CHUNK_LENGTH`（默认 80 字符）过滤碎片  
- 过滤后若 section 仅剩极短块，可与邻块合并，但**仍属同一 section_id**

---

## 5. 元数据继承

Chunk 必须继承自 Section / Document：

| 字段 | 来源 |
|---|---|
| `document_id` / `section_id` / `chunk_id` | 结构 |
| `kb_depth` / `doc_role` / `subject` | 文档层 |
| `domain_kp` | document |
| `knowledge_points` / `primary_kp` | section |
| `content_hash` | 入库去重 |

---

## 6. 去重

`add_documents(dedup=True)` 按 `content_hash` 跳过已存在正文；重跑 ingest 幂等。
