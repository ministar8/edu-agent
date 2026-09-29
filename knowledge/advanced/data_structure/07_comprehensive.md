# 综合拆解 · 解题能力

> domain_kp: ds
> document_id: advanced-ds-comprehensive
> kb_depth: advanced
> doc_role: method

## 本章解决什么

- 一题多问时的拆解路径
- 树/图/表混合题的结构选择
- 复杂度与结构特性对照

---

## 一题多问的拆解路径

> section_id: advanced-ds-comprehensive-breakdown
> kp_ids: [ds.tree.traversal, ds.graph.traversal, ds.sort.quick_sort]
> primary_kp: ds.tree.traversal
> topic_tags: [分析, 计算]
> scope: cross
> difficulty: 4

**识别信号**：综合题同时出现建结构、算复杂度、给序列、问性质等多问。

**分析方法**：

1. **拆子问**：标出每问绑定的 KP（遍历？建堆？划分？）  
2. **定结构**：需要树先还原/建堆；需要图先画邻接  
3. **按问作答**：性质用公式；构造用算法步骤；序列用模拟  
4. **隔离**：小问之间不共享错误中间结果  

**易错点**：

- 第一问树形画错污染后续  
- 综合题仍用单一技巧硬套  
- 只写结果不写「用了哪条性质/哪次操作」  

**变式**：先序+中序还原再求 ASL；图遍历后再拓扑。

---

## 结构选择对照

> section_id: advanced-ds-comprehensive-structure_choice
> kp_ids: [ds.linear.seq_list, ds.linear.linked_list, ds.search.hash, ds.graph.storage]
> primary_kp: ds.linear.seq_list
> topic_tags: [分析, 选择]
> scope: cross
> difficulty: 3

**识别信号**：给操作特征（频繁插入、随机访问、判邻接）选合适结构。

**分析方法**：

| 特征 | 优先 |
|---|---|
| 随机访问 | 顺序表 / 邻接矩阵 |
| 频繁插删 | 链表 / 邻接表 |
| 精确查找 O(1) | 散列 |
| 有序查找 | 折半 / B+ 树 |
| 最小生成 / 最短路 | 图 + 对应算法 |

**易错点**：

- 只看时间复杂度忽略空间与稳定性  
- 稠密图仍选邻接表  
- 散列不适合范围查询  

**变式**：给场景列优缺点；混合结构（块链）用途。

---

## 复杂度与特性速查

> section_id: advanced-ds-comprehensive-complexity
> kp_ids: [ds.sort.quick_sort, ds.sort.merge, ds.search.binary_search, ds.graph.shortest_path]
> primary_kp: ds.sort.quick_sort
> topic_tags: [选择, 分析]
> scope: cross
> difficulty: 3

**识别信号**：直接问时间/空间复杂度、最坏情况、是否稳定。

**方法步骤**：

1. 查表定位算法  
2. 写清**最坏/平均**与是否含递归栈  
3. 稳定性单独答  

| 算法 | 平均 | 最坏 | 空间 | 稳定 |
|---|---|---|---|---|
| 直接插入 | O(n²) | O(n²) | O(1) | ✓ |
| 快排 | O(n log n) | O(n²) | O(log n) | ✗ |
| 堆排 | O(n log n) | O(n log n) | O(1) | ✗ |
| 归并 | O(n log n) | O(n log n) | O(n) | ✓ |
| 折半 | O(log n) | O(log n) | O(1) | — |

**易错点**：

- 快排空间写成 O(1)  
- 把平均当最坏  
- 稳定性漏答  

**变式**：两算法对比；在约束下选算法并说明理由。
