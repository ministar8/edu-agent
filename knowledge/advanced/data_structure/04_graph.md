# 图 · 解题能力

> domain_kp: ds.graph
> document_id: advanced-ds-graph
> kb_depth: advanced
> doc_role: method

## 本章解决什么

- 邻接矩阵/邻接表选择与复杂度
- DFS / BFS 遍历与应用
- 最小生成树（Prim / Kruskal）
- 最短路径（Dijkstra / Floyd）
- 拓扑排序与 AOE 关键路径

---

## 图的存储与复杂度选择

> section_id: advanced-ds-graph-storage
> kp_ids: [ds.graph.storage]
> primary_kp: ds.graph.storage
> topic_tags: [选择, 分析]
> scope: single
> difficulty: 2

**识别信号**：给顶点边规模，问邻接矩阵/表空间、两顶点是否邻接、度的计算代价。

**方法步骤**：

1. **邻接矩阵**：空间 O(n²)；判邻接 O(1)；求度扫一行 O(n)；适合稠密图  
2. **邻接表**：空间 O(n+e)；判邻接 O(度)；求度 O(度)；适合稀疏图  
3. 无向图边结点数 2e，有向 e；矩阵对称性可验无向  
4. 十字链表/邻接多重表：有向/无向专用结构，了解用途即可  

**易错点**：

- 稠密稀疏与 n、e 关系判断反了  
- 无向图邻接表边结点数忘乘 2  
- 用矩阵求所有顶点度仍写 O(1)  

**变式**：两种存储下 BFS/DFS 空间；图的边数范围。

---

## DFS / BFS 遍历与序列

> section_id: advanced-ds-graph-traversal
> kp_ids: [ds.graph.traversal, ds.graph.storage]
> primary_kp: ds.graph.traversal
> topic_tags: [代码, 分析]
> scope: single
> difficulty: 2

**识别信号**：给图写 DFS/BFS 序列；问遍历生成树；连通分量个数。

**方法步骤**：

1. **DFS**：递归或显式栈；沿一条路径走到底再回溯；序列依赖邻接点顺序  
2. **BFS**：队列；按层；最短路径（无权）层数  
3. **非连通图**：外层对每个未访问顶点启动一次  
4. 邻接表 vs 矩阵：同一图、同一邻接顺序才有唯一序列  

**易错点**：

- 忘记标记访问导致死循环  
- 非连通图只遍历一个分量  
- 用邻接矩阵默认下标序，与邻接表出边序混用  

**变式**：判断图是否连通；求连通分量；DFS 栈状态快照。

---

## 最小生成树 Prim / Kruskal

> section_id: advanced-ds-graph-mst
> kp_ids: [ds.graph.mst]
> primary_kp: ds.graph.mst
> topic_tags: [计算, 分析]
> scope: single
> difficulty: 3

**识别信号**：求 MST、加边顺序、判断某边是否在 MST 中、MST 代价。

**方法步骤**：

1. **Prim**：从一点长树，每次取连接树内外的最小边；适合稠密  
2. **Kruskal**：边按权排序，不成环则选；并查集判环；适合稀疏  
3. **环性质**：环上最大权边一定不在任何 MST（唯一最大时）  
4. 权相同时 MST 不唯一，边集可不同、总权相同  

**易错点**：

- Kruskal 忘判环  
- 把「某边在某个 MST」与「在所有 MST」混淆  
- 有向图套无向 MST 算法  

**变式**：求 MST 数量（权相同时）；判断边一定在 MST；增加一点后 MST 增量更新。

---

## 最短路径 Dijkstra / Floyd

> section_id: advanced-ds-graph-shortest
> kp_ids: [ds.graph.shortest_path]
> primary_kp: ds.graph.shortest_path
> topic_tags: [计算, 分析]
> scope: single
> difficulty: 3

**识别信号**：单源最短路、任意两点最短路、判断负权、路径条数。

**方法步骤**：

1. **Dijkstra**：贪心确定最短顶点；无负权；复杂度 O(n²) 或堆 O((n+e)log n)  
2. **Floyd**：三重循环动态规划；允许负权（无负环）；O(n³)  
3. **路径还原**：记录前驱  
4. 判负环：Floyd 对角线或 Bellman-Ford  

**易错点**：

- Dijkstra 遇负权仍用  
- Floyd 初始化 `d[i][i]=0`、无穷大写法溢出  
- 把「边权非负」与「路径长非负」混用  

**变式**：最短路径条数；给邻接矩阵跑一轮 Dijkstra 填表。

---

## 拓扑排序与关键路径

> section_id: advanced-ds-graph-topo_aoe
> kp_ids: [ds.graph.topo, ds.graph.aoe]
> primary_kp: ds.graph.topo
> topic_tags: [计算, 分析]
> scope: cross
> difficulty: 3

**识别信号**：拓扑序列个数/是否唯一；AOE 最早最迟时间、关键活动。

**方法步骤**：

1. **拓扑**：入度 0 入队/栈；删点删边；有环则无拓扑序  
2. **唯一性**：每步若同时有多个入度 0，则序列不唯一  
3. **AOE**：  
   - 事件 `ve`（最早）顺拓扑，`vl`（最迟）逆拓扑  
   - 活动 `e=ve(弧尾)`，`l=vl(弧头)-权`  
   - `e==l` 为关键活动  
4. 关键路径可能多条；工期 = 源点 `ve`  

**易错点**：

- `vl` 从汇点倒推公式写反  
- 关键活动连成的路径才叫关键路径，单个活动不等价  
- 拓扑排序与 DFS 后序逆序的关系记混  

**变式**：求最短工期；哪些活动提前可缩工期；判断拓扑序是否合法。
