# Basic 基础知识设计（L1 概念知识层）

> 状态：设计定稿（2026-09-28）  
> 定位：**不是教材复刻**，而是给 Agent 的概念层：是什么 / 为什么 / 性质 / 机制 / 公式 / 算法思想。  
> 层级：**L1 Basic → 理解** ｜ L2 Advanced → 方法题型 ｜ L3 Exams → 真题实践。

---

## 1. 任务边界

| 写 | 不写 |
|---|---|
| 定义、动机、性质 | 真题编号 / 答案 |
| 核心机制与步骤 | 王道页码、应试套路 |
| 基础公式、复杂度 | 长篇完整实现 |
| 算法**思想**（非实现） | 题型技巧（归 advanced） |
| 「为什么学它」（知识意义） | **「选择题/计算题高频」「常考」「考点」** |

---

## 2. 文档模型（Domain → Document）

```text
Domain   →  Document
Topic    →  Section (H2)
Point    →  Section (H2/H3)
Section  →  Chunk（入库切分）
```

**默认一个 Domain 一个文档**；Domain 过大才按 Topic 拆成子目录文件。  
**禁止**默认「一 Topic 一文件」——AVL/BST/遍历拆开会丢概念关联；细检索交给 Chunk。

```text
# 默认
basic/data_structure/06_tree.md     # 含二叉树、BST、AVL、遍历…

# 仅当 Domain 过大
basic/computer_organization/03_storage/
  ├── 01_main_memory.md
  ├── 02_cache.md
  └── 03_virtual_memory.md
```

拆分阈值：**不设硬性字数**；以「单文件过大难维护 / 单 Topic 自成一体且与兄弟节关联弱」为准。

---

## 3. 目录（四科）

```text
knowledge/basic/
├── data_structure/
│   ├── 01_intro.md
│   ├── 02_linear_list.md
│   ├── 03_stack_queue.md
│   ├── 04_array_matrix.md
│   ├── 05_string.md
│   ├── 06_tree.md
│   ├── 07_graph.md
│   ├── 08_search.md
│   └── 09_sort.md
├── computer_organization/
│   ├── 01_overview.md
│   ├── 02_representation.md
│   ├── 03_storage.md
│   ├── 04_instruction.md
│   ├── 05_cpu.md
│   ├── 06_bus.md
│   └── 07_io.md
├── operating_system/
│   ├── 01_overview.md
│   ├── 02_process.md
│   ├── 03_memory.md
│   ├── 04_file.md
│   └── 05_io.md
└── computer_network/
    ├── 01_arch.md
    ├── 02_physical.md
    ├── 03_datalink.md
    ├── 04_network.md
    ├── 05_transport.md
    └── 06_application.md
```

**绪论 / 概述保留**（如 `01_intro.md`：基本概念、算法与复杂度等）——**不必强行绑定大量 KP**。

---

## 4. ★ Basic 与 KP 的关系

> **KP 是知识锚点，不是教材目录的镜像。**

| 允许 | 禁止 |
|---|---|
| Basic 章 **略宽于** KP 树（绪论、导言、综合小结） | 为了「教材有这一章」**反向造 KP** |
| 一节挂多个 `kp_ids` | 只有一节就强制建一个 domain |
| 无 KP 的节（纯导论）仍可入库 | 用 KP 树硬切教材章节目录 |

教材章节 ⊇ KP 覆盖范围；锚不上的内容可以「只检索、不进图」。

---

## 5. KP 引用语义

| 字段 | 层级 | 含义 |
|---|---|---|
| **`domain_kp`** | Document | 本文档归属的 KP **Domain**（1 个） |
| **`kp_ids`** | Section | 该节**正文实际讲到**的 KP（可多个） |
| **`primary_kp`** | Section | **可选**；该节**主考点**，必须 ∈ `kp_ids` |

```markdown
# 树与二叉树
> domain_kp: ds.tree

## 二叉树遍历
> kp_ids: [ds.tree.traversal, ds.tree.binary_tree]
> primary_kp: ds.tree.traversal
```

规则：

1. `domain_kp` 必须是 `node_kind=domain` 的 id  
2. 禁止把 domain id 塞进 `kp_ids` 凑数  
3. 无 `primary_kp` 时：默认 `kp_ids[0]` 为主，或展开时等权  
4. links：每条 `kp_id` 各写一条 `teaches`；**边不标主从**  

---

## 6. 资产 ID 链

```text
chunk_id        basic-ds-tree-traversal-001
    ↓
section_id      basic-ds-tree-traversal
    ↓
document_id     basic-ds-tree
    ↓
domain_kp       ds.tree
    ↓
kp_ids / primary_kp
```

| 层 | 格式 | 例 |
|---|---|---|
| `document_id` | `basic-<subject_code>-<domain_slug>` | `basic-ds-tree` |
| `section_id` | `<document_id>-<section_slug>` | `basic-ds-tree-traversal` |
| `chunk_id` | `<section_id>-<NNN>` | `basic-ds-tree-traversal-001` |

- `subject_code`：`ds`/`co`/`os`/`cn`  
- slug 与 KP 末段尽量对齐，**不强制全等**（`06_tree` ↔ `ds.tree`）  
- id **冻结**；改标题不改 id  

---

## 7. 文内结构模板

```markdown
# <Domain 名>

> domain_kp: <domain id>

## 学习目标
- 理解树、二叉树的基本概念
- 掌握二叉树的基本性质
- 理解常见遍历方法的基本思想

## <Topic/Point 名>
> kp_ids: [<kp id>, ...]
> primary_kp: <可选>

**定义**：…
**为什么**：…
**性质**：…
**机制**：…
**公式 / 思想**：…
```

**内容维度 ≠ 强制字段**：定义 / 为什么 / 性质 / 机制 / 公式 / 思想是 **L1 应覆盖的维度**，不要求每个 H2 机械套同一组标签。按节选材组织，例如：

```markdown
## 先序遍历

**基本思想**
…

**实现机制**
…

**特点**
…
```

禁止为整齐而空写「为什么」；小节允许只写其中若干维。

### 7.1 学习目标（每章要有）

| 要求 | 说明 |
|---|---|
| **要有** | 每章开头「学习目标」 |
| 语义 | **学什么**（理解/掌握/了解） |
| 禁止 | 「完成第 X 道王道题 / 刷 N 题」等 **L2 应试表述** |

例（L1）：

- 理解树、二叉树的基本概念  
- 掌握二叉树的基本性质  
- 理解常见遍历方法的基本思想  

### 7.2 先修（prerequisites）——暂缓

| 决定 | 说明 |
|---|---|
| **不写进正文** | 避免 Basic / KP Graph / Learning Path 三者语义混杂 |
| 表达位置 | **KP Graph V2**：`ds.tree --requires--> ds.linear_list` |
| Path Agent | 将来读图，不读 Basic 教材正文 |

---

## 8. 入库元数据

| 字段 | 值 |
|---|---|
| `kb_depth` | `basic` |
| `doc_role` | `textbook` |
| `subject` | 四科之一 |
| `document_id` / `section_id` / `chunk_id` | §6 |
| `knowledge_points` | 自 section `kp_ids` |
| `primary_kp` | 自 section（可选） |

`teaches` 边：`from = basic:<section_id>` → `to = kp_id`。

### 8.1 边的语义主体（定稿）

**`teaches` 的语义主体 = Section；Chunk 只是检索载体。**

```text
Section (basic-ds-tree-traversal)
   │ teaches
   │
   ├── Chunk 001   ← 不各自生成 teaches
   ├── Chunk 002
   └── Chunk 003
         │
         ▼
        KP (ds.tree.traversal)
```

| 允许 | 禁止 |
|---|---|
| 一个 Section 一条（或对多个 KP 多条）`teaches` | 每个 Chunk 各生成一条 `teaches` |
| Chunk 继承 section 的 KP 元数据（检索用） | 用 chunk_id 充当 `from` 去建边 |

**原因**：一节切成 N 个 chunk 时，若 per-chunk 建边会重复 N 条同一关系，污染统计与图。  
检索需要粒度时读 **chunk + 其 `section_id`/`knowledge_points`**，不读 `links`。

---

## 9. 不做

- 不写真题/答案、不写王道题型  
- 不默认 Topic 一文件  
- 不为对齐教材目录而创建 KP  
- 不把 `primary_kp` 写进 links 边  
