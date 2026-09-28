# Advanced 设计（L2 进阶知识 / 解题能力层）

> 状态：设计定稿（2026-09-28）  
> 定位：**408 进阶知识 + 解题能力**，不是书商资料库。  
> RAG 消费的是**整理后的 L2**；「王道」不进知识库一级概念。

---

## 1. 分层定位

```text
L1 Basic     是什么 / 为什么 / 怎么工作（原理、思想）
L2 Advanced  面向做题与应用的结构化进阶知识          ← 本层
L3 Exams     具体真题 / 答案 / 题目语境
```

| L2 写 | L2 不写 |
|---|---|
| 题型识别、计算方法、算法应用 | 整题题干+选项+标准答案全文（L3） |
| 解题流程、综合分析、代码模板 | 长篇原理推导（L1） |
| 易错模式 | 书名/页码/「王道 p.X」 |
| 变式与形态 | 「必考/押题」话术 |

来源可以是教材/辅导书/自研，**入库去来源化**，只保留方法结构。

---

## 2. ★ `doc_role=method` 语义（定稿）

```text
doc_role: method
```

**含义**：面向 408 **解题与知识应用**组织的**结构化进阶知识**，包括：

- 题型识别  
- 计算方法  
- 算法应用  
- 解题流程  
- 综合分析  
- 代码模板  
- 易错模式  

**`method` ≠ 小技巧 / 口诀。**  
禁止把 L2 全部写成「技巧条」；必须是**可执行、可识别、可纠错**的方法结构。

---

## 3. 目录

```text
knowledge/advanced/
├── data_structure/
│   ├── 01_linear_list_methods.md
│   ├── 02_stack_queue_methods.md
│   ├── 03_tree_methods.md
│   ├── 04_graph_methods.md
│   ├── 05_search_methods.md
│   ├── 06_sort_methods.md
│   └── 07_ds_comprehensive.md
├── computer_organization/
│   ├── 01_representation_calc.md
│   ├── 02_storage_cache_calc.md
│   ├── 03_pipeline_analysis.md
│   ├── 04_bus_io_calc.md
│   └── 05_co_comprehensive.md
├── operating_system/
│   ├── 01_process_sync_methods.md
│   ├── 02_memory_calc.md
│   ├── 03_file_disk_calc.md
│   └── 04_os_comprehensive.md
└── computer_network/
    ├── 01_link_calc.md
    ├── 02_network_ip_calc.md
    ├── 03_transport_analysis.md
    └── 04_cn_comprehensive.md
```

- 默认一方法域一文；过大再拆  
- `*_comprehensive.md`：跨考点综合拆解  
- **无**「王道章节」镜像结构  

---

## 4. 文档结构

```markdown
# 树与二叉树 · 解题能力

> domain_kp: ds.tree
> document_id: advanced-ds-tree
> kb_depth: advanced
> doc_role: method

## 本章解决什么
…

## 由遍历序列还原二叉树
> section_id: advanced-ds-tree-build_from_traversal
> kp_ids: [ds.tree.traversal, ds.tree.binary_tree]
> primary_kp: ds.tree.traversal
> topic_tags: [综合, 计算]

**识别信号** …
**方法步骤** …
**易错点** …
**变式** …
```

| 段 | 作用 |
|---|---|
| 识别信号 | 题面如何暴露此法（题型识别） |
| 方法步骤 | 可执行流程（解题流程 / 计算方法） |
| 易错点 | 边界、漏情况（易错模式） |
| 变式 | 形态变化；不贴整题选项答案 |

可选：**代码模板**（算法应用 / 代码模板）、**综合拆解**（综合分析）。

---

## 5. 资产 ID 与元数据

```text
chunk_id      advanced-ds-tree-build_from_traversal-001
  → section_id  advanced-ds-tree-build_from_traversal
    → document_id advanced-ds-tree
      → domain_kp ds.tree
        → trains → KP
```

| 字段 | 值 |
|---|---|
| `kb_depth` | `advanced` |
| `doc_role` | **`method`** |
| `topic_tags` | 可选：`计算` / `选择` / `综合` / `代码`… |
| `document_id` / `section_id` / `chunk_id` | 上图 |
| `knowledge_points` / `primary_kp` | section 级 |

**禁止**字段：`publisher` / `book` / `page` / 书名主键。

links：

```json
{
  "from": "advanced:advanced-ds-tree-build_from_traversal",
  "to": "ds.tree.traversal",
  "type": "trains"
}
```

| 边 | 含义 |
|---|---|
| `teaches` | L1 → KP |
| **`trains`** | **L2 → KP** |
| `assesses` | L3 question → KP |

---

## 6. 边界对照

| 表述 | 层 |
|---|---|
| AVL 旋转保持中序有序 | L1 原理 |
| 判 LL/RR/LR/RL，再单旋/双旋 | L2 方法 |
| 2019-Q… 全题+答案 | L3 战例 |

---

## 7. 质检清单

- [ ] `doc_role=method`，非技巧口诀堆砌  
- [ ] 含识别/步骤/易错等方法维（可组合）  
- [ ] 无整题+答案全文  
- [ ] 无书商/页码  
- [ ] `trains` 边  
- [ ] 不与 L1 重复长原理  

---

## 8. 不做

- 不镜像王道目录  
- 不为「技巧名」造 KP  
- 不灌整卷真题进 advanced  
