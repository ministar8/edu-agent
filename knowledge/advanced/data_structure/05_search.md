# 查找 · 解题能力

> domain_kp: ds.search
> document_id: advanced-ds-search
> kb_depth: advanced
> doc_role: method

## 本章解决什么

- 折半查找过程与 ASL
- 分块查找结构
- B 树 / B+ 树插入删除与阶
- 散列表构造、冲突、ASL

---

## 折半查找与 ASL

> section_id: advanced-ds-search-binary
> kp_ids: [ds.search.binary_search, ds.search.seq]
> primary_kp: ds.search.binary_search
> topic_tags: [计算, 分析]
> scope: single
> difficulty: 2

**识别信号**：有序表折半查找比较次数、成功/失败 ASL、画判定树。

**方法步骤**：

1. 仅**顺序存储 + 有序**可折半  
2. `low/high/mid`，`mid=(low+high)//2`（下标约定 0/1 写清）  
3. **判定树**：中点为根，左右子表递归；成功 ASL = 各结点深度和/ n  
4. 失败 ASL = 外结点（失败结点）加权深度  

**易错点**：

- 链表写折半  
- ASL 计入比较次数与「路径长」差 1  
- mid 取整方向影响树形与序列  

**变式**：给查找序列反推关键字位置；比较顺序查找 ASL。

---

## 分块查找

> section_id: advanced-ds-search-block
> kp_ids: [ds.search.block]
> primary_kp: ds.search.block
> topic_tags: [计算, 选择]
> scope: single
> difficulty: 2

**识别信号**：索引顺序结构，问 ASL、块长选择、平均比较次数。

**方法步骤**：

1. 块间有序、块内无序（或有序）  
2. 先查索引（折半或顺序），再块内顺序查  
3. ASL = 索引 ASL + 块内 ASL  
4. 最优块长约为 √n  

**易错点**：

- 索引项存的是块内最大/最小值写混  
- 块内也折半却按块内无序估 ASL  
- 与单纯折半比较复杂度  

**变式**：给 n、块长求 ASL；改造为块内有序。

---

## B 树插入删除与阶

> section_id: advanced-ds-search-btree
> kp_ids: [ds.search.b_tree, ds.search.b_plus_tree]
> primary_kp: ds.search.b_tree
> topic_tags: [计算, 分析]
> scope: single
> difficulty: 3

**识别信号**：m 阶 B 树插入关键字后根结点内容、最小高度、删除结点后形态。

**方法步骤**：

1. **m 阶**：非根非叶结点关键字数 `⌈m/2⌉-1 ~ m-1`；子树数 `⌈m/2⌉ ~ m`  
2. **插入**：落在叶；满则分裂，中位数上提  
3. **删除**：叶上删；不足向兄弟借或与兄弟/父合并  
4. **B+ 树**：数据全在叶，叶链表有序；适合范围查  

**易错点**：

- 阶 m 与关键字数上限关系差 1  
- 分裂时上提元素是否留在右子树  
- B 树与 B+ 树查询路径（B+ 必到叶）  

**变式**：给插入序列画根；最小/最大结点数与高度；删除后是否仍是 B 树。

---

## 散列表构造与 ASL

> section_id: advanced-ds-search-hash
> kp_ids: [ds.search.hash]
> primary_kp: ds.search.hash
> topic_tags: [计算, 分析]
> scope: single
> difficulty: 3

**识别信号**：散列函数、线性/链地址法插入过程、查找失败/成功 ASL。

**方法步骤**：

1. **构造**：除留余数 `H(k)=k%p`，p 取素数  
2. **线性探测**：冲突 `H_i=(H_0+i) mod m`，一次聚集  
3. **链地址**：冲突挂链；ASL 按链长  
4. **查找失败 ASL**：对每个可能散列地址等概率，探测到空位的平均次数  

**易错点**：

- 成功 ASL 与失败 ASL 分母不同  
- 线性探测删除需标记（墓碑）  
- 装填因子 α 与 ASL 关系定性记反  

**变式**：二次探测、再哈希；给插入序列画表；求等概率下失败 ASL。

---

## 查找方法选择与 ASL 综合

> section_id: advanced-ds-search-asl_choice
> kp_ids: [ds.search.seq, ds.search.binary_search, ds.search.block, ds.search.hash]
> primary_kp: ds.search.binary_search
> topic_tags: [计算, 分析]
> scope: cross
> difficulty: 3

**识别信号**：给 n、查找概率、存储方式，选算法并算平均查找长度。

**方法步骤**：

1. **有序顺序存储** → 折半；ASL 成功约 `log2(n+1)-1` 量级  
2. **无序** → 顺序；ASL 成功 `(n+1)/2`  
3. **块间有序** → 分块；ASL = 索引 ASL + 块内 ASL  
4. **等概率精确查找** → 散列；成功 ASL 与 α 相关  
5. **范围查 / 有序遍历** → B+ 树或有序表  

**易错点**：

- 失败 ASL 与成功 ASL 分母不同  
- 链式存储不能折半  
- 装填因子过高时散列退化  

**变式**：两结构对比；给查找序列求平均比较次数。

---

## 折半与分块计算

> section_id: advanced-ds-search-binary_block
> kp_ids: [ds.search.binary_search, ds.search.block]
> primary_kp: ds.search.binary_search
> topic_tags: [计算, 选择]
> scope: single
> difficulty: 2

**识别信号**：折半判定树高度；失败 ASL；块长优化。

**方法步骤**：

1. 折半比较次数 ≤ `⌊log2 n⌋+1`  
2. **失败 ASL** 用外结点（含空隙）加权  
3. **分块**：最优块长 ≈ `√n`  
4. 索引折半 + 块内顺序 vs 全折半的适用  

**易错点**：

- 判定树外结点数 n+1  
- 块内有序可再折半但 ASL 公式变  
- 成功与失败概率不等权  

**变式**：给 n 求最大比较次数；算分块 ASL。


