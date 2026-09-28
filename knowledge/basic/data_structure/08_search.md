# 查找

> domain_kp: ds.search
> document_id: basic-ds-search
> kb_depth: basic
> doc_role: textbook

## 学习目标

- 理解基于比较的查找思想
- 理解树形查找与散列查找的路线差异
- 理解 B 树类结构的磁盘友好动机

---

## 顺序查找与折半查找

> section_id: basic-ds-search-linear
> kp_ids: [ds.search.seq, ds.search.binary_search]
> primary_kp: ds.search.binary_search

**顺序查找**

**定义**：从一端依次比较，直到命中或到端点。

**特点**：实现简单；适用任意线性存储；平均与规模同阶。

**折半查找**

**基本思想**：在**有序且可随机访问**的序列上，比较中间元素，把搜索区间每次减半。

**为什么**：有序性使「排除一半」成为可能，比较次数与 log n 同阶。

**条件**：有序 + 顺序存储（链表折半需代价）。动态插入破坏有序维护成本。

---

## 分块查找

> section_id: basic-ds-search-block
> kp_ids: [ds.search.block]
> primary_kp: ds.search.block

**定义**：把数据分块，块间有序、块内可无序；先定块，再块内找。

**为什么**：折半要求全序且随机访问；分块在「插入成本」与「查找速度」之间折中。

**思想**：**索引 + 顺序**两级结构——索引定范围，细节用简单方法。

---

## B 树与 B+ 树

> section_id: basic-ds-search-btree
> kp_ids: [ds.search.b_tree, ds.search.b_plus_tree]
> primary_kp: ds.search.b_tree

**定义**：多路平衡查找树；结点含多个关键字与多棵子树；所有叶结点在同一层。

**为什么**：磁盘/外存按块读写，**降低树高**等于减少 I/O 次数。二叉树在大数据量下太高。

**机制思想**：

- 结点内关键字有序，子树对应区间
- 插入/删除通过结点分裂与合并维持平衡
- B+ 树：关键字作索引，数据/记录集中在叶层，叶层链接便于范围扫描

**特点**：B 树常作**索引结构**；B+ 树更利于「范围查询 + 顺序遍历」。

---

## 散列表

> section_id: basic-ds-search-hash
> kp_ids: [ds.search.hash]
> primary_kp: ds.search.hash

**定义**：用散列函数把关键字映射到表位置，理想 O(1) 查找。

**为什么**：比较查找存在下界思想；若只需「在不在」，可用地址直接定位。

**机制**：

- 散列函数压缩关键字空间到表地址
- 冲突不可避免：链地址（同义词链）或开放定址（探查）
- 装填因子影响冲突与查找长度

**思想**：**用函数计算换比较次数**；代价是冲突处理与散列函数质量。稳定查找效率依赖分布与装填程度，不是绝对 O(1)。
