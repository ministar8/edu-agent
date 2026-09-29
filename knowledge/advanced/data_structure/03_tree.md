# 树与二叉树 · 解题能力

> domain_kp: ds.tree
> document_id: advanced-ds-tree
> kb_depth: advanced
> doc_role: method

## 本章解决什么

- 由遍历序列还原二叉树
- 二叉树计数与性质类问题
- BST / AVL 操作与判定
- 哈夫曼编码计算
- 树与森林转换的处理路径

---

## 由遍历序列还原二叉树

> section_id: advanced-ds-tree-build_from_traversal
> kp_ids: [ds.tree.traversal, ds.tree.binary_tree]
> primary_kp: ds.tree.traversal
> topic_tags: [计算, 分析]
> scope: single
> difficulty: 2
> related_exams:
>   - question:2019-Q2

**识别信号**：题面给出「先序+中序」「后序+中序」等两序列，要求还原树、求遍历序或计数。

**方法步骤**：

1. 先序首元素（或后序末元素）为根  
2. 在中序里用根切成左子树中序 / 右子树中序  
3. 按同样区间长度切先序/后序，得到左右子树的对应序列  
4. 对左右子树递归  
5. 写层序时按还原后的树逐层输出  

**易错点**：

- 只有先序+后序一般**不能**唯一确定树（除单支等特殊情况）  
- 中序划分时根只能用一次，且左右区间长度要与先/后序区间对齐  
- 有重复关键字时须额外约定，否则多解  

**变式**：给先序+中序求后序；给层序+中序还原；或只问「是否唯一」。

---

## 二叉树性质与计数

> section_id: advanced-ds-tree-counting
> kp_ids: [ds.tree.binary_tree, ds.tree.complete]
> primary_kp: ds.tree.complete
> topic_tags: [计算, 选择]
> scope: single
> difficulty: 2

**识别信号**：求结点数、叶结点数、高度、某层最多结点、完全二叉树编号关系。

**计算流程**：

1. 先列已知：n、n0/n1/n2、深度 k、层序编号  
2. 用关系式：n0 = n2 + 1；深度为 k 至多 2^k − 1；完全二叉树 ⌊log₂ n⌋ + 1  
3. 完全二叉树编号：左 2i、右 2i+1、父 ⌊i/2⌋  
4. 高度类问题优先把「结点数↔高度」关系写成不等式再求范围  

**易错点**：

- 混淆「深度为 k」与「有 k 个结点」  
- n0 = n2 + 1 只对二叉树成立  
- 完全二叉树编号从 1 开始时父子公式与从 0 开始不同  

**变式**：已知叶结点数求总结点数范围；已知完全二叉树 n，求度为 1 的结点个数（0 或 1）。

---

## BST 判定与操作

> section_id: advanced-ds-tree-bst_ops
> kp_ids: [ds.tree.bst, ds.tree.binary_tree]
> primary_kp: ds.tree.bst
> topic_tags: [分析, 代码]
> scope: single
> difficulty: 3

**识别信号**：按关键字插入/删除；判断序列是否为 BST 查找过程；求 ASL。

**方法步骤**：

1. **判定 BST**：中序递增；或递归检查左子树 < 根 < 右子树  
2. **插入**：从根比较，小左大右，插到空位为叶  
3. **删除**：叶子直接删；单支接唯一孩子；双支用中序前驱（左子树最右）或后继（右子树最左）替换后再删该前驱/后继  
4. **查找路径**：路径上的关键字比较顺序唯一；插入失败点即为插入位置  

**易错点**：

- 删除双支结点时只换值不换结构，或换完仍保留两个孩子  
- 与排序树、堆混淆：BST 中序有序；堆只保证父子序  
- 查找长度含比较次数，不等于深度  

**变式**：给出插入序列画出 BST；给出 BST 判删除后是否仍为 BST；计算平均查找长度。

---

## AVL 失衡与旋转

> section_id: advanced-ds-tree-avl_rotate
> kp_ids: [ds.tree.avl, ds.tree.bst]
> primary_kp: ds.tree.avl
> topic_tags: [分析, 计算]
> scope: single
> difficulty: 3

**识别信号**：插入关键字后求树形、根结点、或问是否平衡。

**方法步骤**：

1. 按 BST 规则插入，从插入点向上找**第一个**失衡结点（最小不平衡子树）  
2. 看「失衡结点 → 插入方向所在的子树 → 再到插入点」的路径形态：LL / RR / LR / RL  
3. 对最小不平衡子树做对应旋转（单旋或双旋）  
4. 旋转后保持中序有序，再向上检查是否仍失衡（一般只需处理最小不平衡子树）  

**易错点**：

- 从根旋转而不是最小不平衡子树  
- LR / RL 用成单旋  
- 旋转后忘了树仍须是 BST  

**变式**：连续插入多个值；问最终根；问某一结点的平衡因子。

---

## 哈夫曼编码与 WPL

> section_id: advanced-ds-tree-huffman_calc
> kp_ids: [ds.tree.huffman, ds.tree.binary_tree]
> primary_kp: ds.tree.huffman
> topic_tags: [计算, 选择]
> scope: single
> difficulty: 2

**识别信号**：给频次/权值，求 WPL、编码长度、带权路径或判断是否哈夫曼树。

**计算流程**：

1. 每次取最小两个权合并，新权为和  
2. 记录合并过程中的树高或直接用 WPL = Σ wᵢ × lᵢ  
3. 若求「编码长度不小于 k 的字符个数」：画出树或累计各叶子深度  
4. 结点数：n 个叶子 ⇒ 2n − 1（仅有度 0 与 2）  

**易错点**：

- 把「合并次数」或「总权」当成 WPL  
- 相同权值不同合并顺序树形可不同，但 **WPL 唯一**  
- 编码长 = 深度（根到叶边数），勿少算一层  

**变式**：已知 WPL 与部分权求另一权；比较两棵二叉树是否都可能是哈夫曼树。

---

## 树、森林与二叉树转换

> section_id: advanced-ds-tree-forest_convert
> kp_ids: [ds.tree.forest_convert, ds.tree.binary_tree]
> primary_kp: ds.tree.forest_convert
> topic_tags: [分析]
> scope: single
> difficulty: 2

**识别信号**：树/森林的遍历序与对应二叉树遍历序关系；给树求对应二叉树的某遍历。

**方法步骤**：

1. **树 → 二叉树**：长子作左孩子；兄弟作右孩子（左孩子右兄弟）  
2. **森林 → 二叉树**：各树根视为兄弟链，再按上条  
3. 用对应关系：树/森林的先根 ≈ 二叉树先序；树/森林的后根 ≈ 二叉树中序  
4. 求遍历时可先转二叉树再写，或直接按定义写  

**易错点**：

- 把「兄弟」画成左孩子  
- 树的后根与二叉树后序对应错误（应为中序）  
- 森林中多棵树的根之间的兄弟关系被画成子树  

**变式**：给二叉树求原森林的遍历；判断某序列是否可能为对应遍历。

---

## 综合拆解：树形题的处理路径

> section_id: advanced-ds-tree-comprehensive
> kp_ids: [ds.tree.traversal, ds.tree.bst, ds.tree.avl, ds.tree.huffman]
> primary_kp: ds.tree.traversal
> topic_tags: [分析, 计算]
> scope: cross
> difficulty: 4

**识别信号**：一题内同时出现遍历、树形结构、插入/编码等多问。

**分析方法**：

1. **拆子问**：先标出每问绑定的 KP（遍历？BST？哈夫曼？）  
2. **定结构**：需要还原树的先还原；需要静态树的直接画  
3. **按问作答**：计数用性质式；构造用插入/旋转；编码用合并  
4. **检查**：每问只依赖本问结构，避免前面小问的中间树写错污染后面  

**易错点**：

- 跨问复用错误的树形  
- 只写结果不写「用哪条性质/哪次旋转」  
- 综合题里仍用单一题型套路硬套  

**变式**：综合大题中先序+中序、再 BST 插入、再求 WPL 的串联结构。

---

## BST / AVL 判定与构造

> section_id: advanced-ds-tree-bst_avl
> kp_ids: [ds.tree.bst, ds.tree.avl]
> primary_kp: ds.tree.bst
> topic_tags: [分析, 代码]
> scope: cross
> difficulty: 3

**识别信号**：判断序列是否 BST 查找/插入过程；AVL 插入后树形与平衡因子。

**方法步骤**：

1. **BST 查找路径唯一**；失败插入点即叶子位置  
2. **判 BST**：中序递增，或递归「左 < 根 < 右」  
3. **AVL 插入**：先 BST 插入，再自底向上找最小不平衡子树  
4. **LL/RR 单旋，LR/RL 双旋**；旋后保持中序有序  

**易错点**：

- 删除双支：只换值（前驱/后继）或先删前驱，不能留两子乱序  
- AVL 从根旋而非最小不平衡子树  
- 旋转后忘再向上查平衡  

**变式**：给插入序画树；判 T1/T3 是否相同；求平衡因子。

