# 排序 · 解题能力

> domain_kp: ds.sort
> document_id: advanced-ds-sort
> kb_depth: advanced
> doc_role: method

## 本章解决什么

- 各排序一趟结果与稳定性
- 快速排序划分过程
- 堆排序建堆与调整
- 归并/基数复杂度
- 算法选择依据

---

## 一趟排序结果与稳定性

> section_id: advanced-ds-sort-one_pass
> kp_ids: [ds.sort.insertion, ds.sort.select, ds.sort.bubble, ds.sort.shell]
> primary_kp: ds.sort.insertion
> topic_tags: [选择, 分析]
> scope: single
> difficulty: 2

**识别信号**：问「第一趟/第二趟结果」「是否稳定」「已基本有序时谁快」。

**方法步骤**：

1. **直接插入**：前 i 个有序；稳定；初始有序 O(n)  
2. **冒泡**：每趟沉底/冒顶一个最值；稳定  
3. **简单选择**：每趟选最小放前端；**不稳定**  
4. **希尔**：分组插入；不稳定；增量序列影响复杂度  

**易错点**：

- 稳定性：选择、希尔、快排、堆排**不稳定**  
- 「一趟」定义（冒泡一趟 vs 插入一趟）按教材  
- 基本有序时快排退化为 O(n²)  

**变式**：给序列写第 k 趟；判断两关键字相对位置是否保持。

---

## 快速排序划分

> section_id: advanced-ds-sort-quick
> kp_ids: [ds.sort.quick_sort]
> primary_kp: ds.sort.quick_sort
> topic_tags: [计算, 代码]
> scope: single
> difficulty: 3

**识别信号**：一趟划分后序列、枢轴最终位置、最坏时间复杂度原因。

**方法步骤**：

1. 取枢轴，左右交替扫描，小左大右，相遇填枢轴  
2. 一趟后枢轴归位，左小右大，但左右不一定有序  
3. 最坏（已有序）O(n²)；平均 O(n log n)；不稳定  
4. 递归栈平均 O(log n)  

**易错点**：

- 把一趟划分写成整趟有序  
- 枢轴选法影响树高，不是算法稳定性  
- 快速排序辅助空间不是 O(1)  

**变式**：三数取中；给序列写完整过程；求比较次数。

---

## 堆排序建堆与调整

> section_id: advanced-ds-sort-heap
> kp_ids: [ds.sort.heap, ds.tree.complete]
> primary_kp: ds.sort.heap
> topic_tags: [计算, 分析]
> scope: single
> difficulty: 3

**识别信号**：初始堆、调整后堆、堆排序趟数、小根堆插入。

**方法步骤**：

1. **完全二叉树**顺序存储：`i` 的孩子 `2i,2i+1`（1-based）  
2. **建堆**：从 `⌊n/2⌋` 到 1 下沉  
3. **排序**：堆顶与末尾交换，再对 n-1 下沉  
4. 小根堆每次取最小；堆排不稳定  

**易错点**：

- 上浮/下沉写反  
- 「第 i 趟」是选出第 i 大/小  
- 堆与 BST 混淆（堆只保证父子序）  

**变式**：插入关键字后调整；求第 k 大用小根堆。

---

## 归并与基数

> section_id: advanced-ds-sort-merge_radix
> kp_ids: [ds.sort.merge, ds.sort.radix, ds.sort.heap]
> primary_kp: ds.sort.merge
> topic_tags: [计算, 选择]
> scope: single
> difficulty: 2

**识别信号**：归并趟数、外部排序、基数排序分配收集过程。

**方法步骤**：

1. **2-路归并**：趟数 `⌈log2 n⌉`；稳定；O(n log n)；空间 O(n)  
2. **基数排序**：按位从低到高分配收集；稳定；O(d(n+r))  
3. 选择排序时结合 n、稳定性、空间、初始状态  

**易错点**：

- 归并与快排空间复杂度对比  
- 基数按高位先排会错  
- 把内部排序直接用于超大外存数据  

**变式**：求归并趟数与比较次数；多路归并败者树用途。

---

## 排序综合比较

> section_id: advanced-ds-sort-compare
> kp_ids: [ds.sort.quick_sort, ds.sort.heap, ds.sort.merge, ds.sort.insertion]
> primary_kp: ds.sort.merge
> topic_tags: [分析, 选择]
> scope: cross
> difficulty: 3

**识别信号**：按 n/稳定性/空间/初态选排序；比较趟数与移动次数。

**方法步骤**：

1. **n 小、基本有序** → 直接插入  
2. **n 大、要稳定** → 归并  
3. **n 大、要省空间、可不稳定** → 堆排  
4. **平均最快** → 快排（警惕已序退化）  

**易错点**：

- 堆排空间 O(1) 但不稳定  
- 归并稳定但空间 O(n)  
- 快排最坏 O(n²)  

**变式**：场景选算法；给序列判可能的排序方法。

