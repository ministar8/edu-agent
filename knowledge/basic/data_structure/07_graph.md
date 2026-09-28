# 图

> domain_kp: ds.graph
> document_id: basic-ds-graph
> kb_depth: basic
> doc_role: textbook

## 学习目标

- 理解图的逻辑结构与存储映射思想
- 理解遍历、生成树、最短路径等算法的核心机制
- 理解拓扑与关键路径的依赖思想

---

## 图的概念与存储

> section_id: basic-ds-graph-storage
> kp_ids: [ds.graph.storage]
> primary_kp: ds.graph.storage

**定义**：顶点集与边集；有向/无向；度、路径、连通、回路。

**为什么**：表达「多对多」关系——网络、课程依赖、工程活动、社交关系。

**存储**：

- 邻接矩阵：直观，适合稠密图，O(1) 判边，空间 O(n²)
- 邻接表：适合稀疏图，遍历邻接点快
- 十字链表等：兼顾有向与逆邻接

**思想**：存储选择由「边稀疏程度 + 主要操作（判边 / 列邻接）」决定。

---

## 图的遍历

> section_id: basic-ds-graph-traversal
> kp_ids: [ds.graph.traversal]
> primary_kp: ds.graph.traversal

**定义**：从某起点访问所有可达顶点且不重复。

**机制**：

- 深度优先（DFS）：沿一条路走到底再回溯；可用栈或递归
- 广度优先（BFS）：按层扩展；用队列

**为什么**：连通分量、环检测、可达性都建立在遍历之上。

**特点**：图有回路，必须**标记已访问**，否则死循环；与树遍历相比，图遍历额外处理「多父/环」。

---

## 最小生成树

> section_id: basic-ds-graph-mst
> kp_ids: [ds.graph.mst]
> primary_kp: ds.graph.mst

**定义**：连通带权无向图中，边权和最小的生成树。

**为什么**：在保证连通的前提下总代价最小——布线、组网。

**机制思想**：

- 贪心：每步选「当前安全的最小权边」
- 不同算法对「安全边」判定不同（切分性质 vs 森林合并）

**性质**：生成树边数为 n−1；若边权互异则树唯一。

---

## 最短路径

> section_id: basic-ds-graph-shortest_path
> kp_ids: [ds.graph.shortest_path]
> primary_kp: ds.graph.shortest_path

**定义**：两点间权值和最小的路径；单源或全源。

**为什么**：路由、导航、依赖最短链。

**机制思想**：

- 无负权时，Dijkstra 思想：每次确定当前最近未决顶点
- 全源 Floyd 思想：逐点允许作为中转，动态更新距离
- 有负权时需另设机制（如 Bellman-Ford 的松弛迭代）

**要点**：算法差异来自「松弛顺序」与「允许负权与否」。

---

## 拓扑排序

> section_id: basic-ds-graph-topo
> kp_ids: [ds.graph.topo]
> primary_kp: ds.graph.topo

**定义**：把有向无环图（DAG）顶点排成线性序列，使得所有边从前向后。

**为什么**：表达**先修/依赖**顺序——课程安排、编译依赖、任务调度。

**机制思想**：

- 反复取「入度为 0」的顶点输出，并删除其出边
- 最终输出全部顶点 ⇒ 无环；否则有环

**特点**：序列不一定唯一；检测环是拓扑排序的天然副产品。

---

## 关键路径

> section_id: basic-ds-graph-aoe
> kp_ids: [ds.graph.aoe]
> primary_kp: ds.graph.aoe

**定义**：AOE 网中，源点到汇点的最长路径；路径上活动为关键活动。

**为什么**：决定工程最短工期；非关键活动有可延时余量（机动时间）。

**机制**：

- 顶点为事件，边为活动及权值（工期）
- 求最早/最晚发生时间，二者相等的顶点在关键路径上
- 活动余量 = 最晚开始 − 最早开始

**思想**：**最长路径约束工期**；与最短路径相反，这里是「时间下界」问题。
