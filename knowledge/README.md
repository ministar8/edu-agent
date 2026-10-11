# knowledge/ 知识库

> 本目录是 RAG 的**语料层**，已按 **L1 `basic/` · L2 `advanced/` · L3 `exams/` + 代码库 `code/`** 组织。
> **改本目录前先读本文**；入库规则见 `../docs/KB_MASTER_DESIGN.md`，检索依赖见 `src/rag/`。

## 结构

| 层 | 目录 | 内容 | 入库脚本 | 向量集合 |
|---|---|---|---|---|
| **L1** | `basic/<科>/` | 基础概念（考纲精编） | `scripts/ingest/ingest_basic_all.py` | 四科集合（同名） |
| **L2** | `advanced/<科>/` | 解题方法层（`doc_role=method`） | `scripts/ingest/ingest_advanced.py` | 四科集合 |
| **L3** | `exams/<年>/` | 真题 `items`/`answer`（★ `paper.md` 仅溯源、**不入库**） | `scripts/ingest/ingest_exams.py` | `exams` |
| **L3** | `exams/<科>.md` | 章节例题集 | `scripts/ingest/ingest_exam_practice.py` | `exams` |
| **code** | `code/<科>/` | 代码实现（**独立库**） | `scripts/ingest/ingest_code.py` | `code_<科>` |
| — | `knowledge_points/` · `learning_paths/` · `rules/` · `schema/` | KP 图谱 · 学习路径 · 契约 | — | — |

## 关键约束（改动前必读）

1. **代码库是独立一层**（`kb_depth: code`，集合 `code_<科>`）：**不进 L1/L2/L3 融合池**，只供
   「代码类」查询（`recall.py` 的 `is_code` 路由）定向召回。四科 code 集合齐全（无代码的科建空集合）。
2. **不要在被入库目录内放说明文件**：`SUPPORTED_EXTENSIONS = {.pdf,.txt,.md,.docx}`
   （`src/rag/loader.py`），任何 `.md/.txt` 都会被当语料摄取。说明文件只放**根目录**（如本 README）。
3. **主链 `rag.ingest` 只入 `learning_paths`**（`DEFAULT_CATEGORIES = ["learning_paths"]`）——
   四科讲义目录已退役，各层一律由上面的**专用脚本**入库。
4. **KP 锚定**：各层 section 用 `> section_id` + `> kp_ids`（可选 `> primary_kp`）头挂知识点；
   边写入 `knowledge_points/links.jsonl`：
   `basic/code ──teaches──→ KP`、`advanced/practice ──trains──→ KP`、`question ──assesses──→ KP`。

## 支撑目录

| 目录 | 内容 |
|---|---|
| `knowledge_points/` | 四科 KP（`*.jsonl`）+ `links.jsonl` + `schema.md`（**知识图谱**：节点=考点、边=教学关系） |
| `learning_paths/` | 学习路线与重点章节 |
| `rules/` | Basic 写作 / 切分 / 元数据 / 门禁规则 |
| `schema/` | KP / 文档 / Chunk 的 JSON Schema |

> 旧体系（顶层四科讲义、`questions`、`papers-rebuild`、`answers`）已于 2026-10-10 归档移出本目录。
