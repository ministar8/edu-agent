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

## 3. 目录（能力域命名，与 L1 对齐）

```text
knowledge/advanced/
├── data_structure/
│   ├── 01_linear_list.md
│   ├── 02_stack_queue.md
│   ├── 03_tree.md
│   ├── 04_graph.md
│   ├── 05_search.md
│   ├── 06_sort.md
│   └── 07_comprehensive.md
├── computer_organization/
│   ├── 01_representation.md
│   ├── 02_storage_cache.md
│   ├── 03_pipeline.md
│   ├── 04_bus_io.md
│   └── 05_comprehensive.md
├── operating_system/
│   ├── 01_process_sync.md
│   ├── 02_memory.md
│   ├── 03_file_disk.md
│   └── 04_comprehensive.md
└── computer_network/
    ├── 01_link.md
    ├── 02_network_ip.md
    ├── 03_transport.md
    └── 04_comprehensive.md
```

### 3.1 三层职责（禁止混入文件名）

| 层 | 回答 | 例 |
|---|---|---|
| **文件名 / 目录** | **讲哪一块（能力域）** | `03_tree.md` |
| **`doc_role`** | **什么层次的内容** | `method`（L2 进阶） |
| **`topic_tags`** | **检索辅助（题型/形态）** | `计算` / `选择` / `代码`…（不含「综合」） |

**禁止**在文件名堆 `_methods` / `_calc` / `_analysis` 等类型后缀——  
那会把「能力域」与「内容类型」混进路径，导致 `tree_methods` 里既有计算又有综合，语义不稳。

| 原则 | 说明 |
|---|---|
| 默认一能力域一文 | 与 Basic domain 对齐 |
| `*_comprehensive.md` | 仅表示跨域综合，允许作为独立能力域 |
| 无书商结构 | 不做「王道章节」镜像 |  

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
> topic_tags: [计算, 选择]
> scope: cross

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
| `topic_tags` | **检索辅助**（题型/形态，见 §5.1） |
| `scope` | 可选：`single` / `cross`（是否跨考点） |
| `related_exams` | 可选：`question:YYYY-QN` 列表（L2→L3，见 §5.3） |
| `document_id` / `section_id` / `chunk_id` | 上图 |
| `knowledge_points` / `primary_kp` | section 级 |

### 5.1 `topic_tags`（仅检索辅助，不参与层级判断）

| 允许（题型/形态） | 禁止 |
|---|---|
| `选择` `计算` `代码` `填空` `分析` | `L1/L2/L3`、`核心/高频/必考`、`综合/简单/困难` |

```text
topic_tags  = 检索辅助标签
scope       = single | cross     ← 「综合」走这里，不进 topic_tags
importance  = 只在 KP，不在 section
```

防止 `topic_tags` 长成第二套知识分类。

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

### 5.2 `trains` 语义（冻结，不再改名）

```text
trains = L2 内容针对某 Knowledge Point 提供题型、方法或应用训练
```

```text
L1  ──teaches──→  KP
L2  ──trains──→   KP
L3  ──assesses──→ KP
```

| 规则 | |
|---|---|
| 名称 | **冻结为 `trains`**；弃用 `practices`，禁止再改回 |
| from | `advanced:<section_id>`（L2 section） |
| to | KP id |
| 语义 | 针对该 KP 的**题型 / 方法 / 应用训练**，不是「做过题」的事实记录 |
| 唯一 | `UNIQUE(from, type, to)` |

### 5.3 `related_exams`（L2→L3 指针，非正文依赖）

```markdown
> related_exams:
>   - question:2019-Q5
>   - question:2022-Q12
```

| 含义 | **该方法与哪些真题的考查形态相关** |
|---|---|
| **不是** | 「L2 内容抄自这些真题」 |
| 位置 | section **元数据**，不写叙述正文 |
| 格式 | `asset_ref`：`question:YYYY-QN` |
| 用法 | 先 L2 方法；用户再问「有真题吗？」→ 经此拉 L3 |

```text
L2 Method
   ├── trains ──────────→ KP
   └── related_exams ───→ L3 question
```

**禁止**：题号进正文当来源；L2 **不得依赖** `related_exams` 才讲得清方法。

三元关系（总纲）：

| 从 | 边 | 到 |
|---|---|---|
| L1 section | `teaches` | KP |
| L2 section | `trains` | KP |
| L3 question | `assesses` | KP |

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
