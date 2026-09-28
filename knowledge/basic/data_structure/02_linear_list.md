# 线性表

> domain_kp: ds.linear
> document_id: basic-ds-linear
> kb_depth: basic
> doc_role: textbook

## 学习目标

- 理解线性表的抽象概念
- 理解顺序表与链表的存储思想
- 理解双链表、循环链表的结构动机

---

## 线性表概念

> section_id: basic-ds-linear-list
> kp_ids: [ds.linear.list]
> primary_kp: ds.linear.list

**定义**：线性表是 n 个同类型元素的有限序列，除首尾外每个元素有唯一前驱与后继。

**为什么**：表达「一对一」关系；是栈、队列、串、数组等结构的共同抽象基础。

**基本运算的思想**：插入与删除改变元素间邻接关系；查找按位序或按值扫描。结构选择决定这些操作是 O(1)、O(n) 还是与位置相关。

---

## 顺序表

> section_id: basic-ds-linear-seq_list
> kp_ids: [ds.linear.seq_list]
> primary_kp: ds.linear.seq_list

**定义**：用一段连续存储单元依次存放元素，逻辑位序与物理地址一致。

**为什么**：地址计算直接（第 i 个元素 O(1) 访问），利于随机访问与缓存局部性。

**机制**：

- 以「下标 → 基址 + i×元素大小」定位
- 插入/删除需要成片搬移元素，代价与位置有关，平均约 O(n)
- 容量固定或需扩容；扩容有搬移成本

**特点**：随机访问强，中间插入删除弱；空间与元素个数通常成块绑定。

---

## 链表

> section_id: basic-ds-linear-linked_list
> kp_ids: [ds.linear.linked_list]
> primary_kp: ds.linear.linked_list

**定义**：结点由数据域与指针域组成，靠指针串联，不必连续存放。

**为什么**：把「邻接关系」从「地址相邻」中解耦，插入删除只改指针，无需搬移整段数据。

**机制**：

- 单链表：每个结点指向后继
- 头结点：统一空表与非空表的插入删除代码路径
- 查找仍需沿链扫描，平均 O(n)；访问第 i 个非随机

**思想**：用**指针**表达关系，用**遍历**换随机访问能力。何时优于顺序表，取决于操作谱（频繁中间插入 vs 频繁随机读）。

---

## 双链表与循环链表

> section_id: basic-ds-linear-linked_variants
> kp_ids: [ds.linear.doubly_linked, ds.linear.circular_linked]
> primary_kp: ds.linear.doubly_linked

**双链表**

**定义**：结点增加 prior 指针，可双向遍历。

**为什么**：已知结点时删除/插入只需该结点附近指针，不必回头找前驱。

**循环链表**

**定义**：尾结点的后继指回头（或头结点），形成环。

**为什么**：从任一结点可访问全表，便于轮转、环形调度等场景。

**思想**：链表变体是在「导航能力」与「指针维护成本」之间做局部增强，不改变线性逻辑本身。
