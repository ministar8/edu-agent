# 数组与特殊矩阵

> domain_kp: ds.array
> document_id: basic-ds-array
> kb_depth: basic
> doc_role: textbook

## 学习目标

- 理解多维数组的存储映射思想
- 理解压缩存储利用的对称性/稀疏性

---

## 数组与存储映射

> section_id: basic-ds-array-storage
> kp_ids: []

**基本思想**：多维下标映射到一维地址；行优先或列优先决定扫描序。

**为什么**：物理内存是线性的，必须有确定映射才能 O(1) 计算地址。

**特点**：随机访问快；大小固定；中间插入删除代价高。

---

## 压缩存储

> section_id: basic-ds-array-compressed
> kp_ids: [ds.array.compressed]
> primary_kp: ds.array.compressed

**定义**：对含规律的矩阵只存有效元素，并建立下标到存储位置的映射。

**为什么**：n 阶对称矩阵可少存约一半；稀疏矩阵中大量为零，全存浪费空间。

**机制**：

- 对称/三角：按规则只存下三角或上三角
- 稀疏：三元组（行、列、值）或十字链表等，换映射效率

**思想**：**用映射换空间**；是否压缩取决于「零/对称元素比例」与「是否频繁随机存取」。

---

## 对称 / 三角 / 稀疏矩阵

> section_id: basic-ds-array-forms
> kp_ids: [ds.array.symmetric, ds.array.triangular, ds.array.sparse, ds.array.compressed]
> primary_kp: ds.array.compressed

**对称矩阵**

**定义**：A[i][j] = A[j][i]。只需存一半加对角线。

**三角矩阵**

**定义**：上三角或下三角区域全为常数（常为 0）。存非常数区 + 常数。

**稀疏矩阵**

**定义**：非零元素个数远少于总元素。

**特点**：

- 三元组存「谁非零」，适合按非零元遍历
- 若需任意 A[i][j]，需索引结构辅助定位
- 压缩提高空间利用率，可能牺牲随机访问常数

**思想**：压缩存储的本质是**承认结构冗余**，并用额外索引/公式恢复下标语义。
