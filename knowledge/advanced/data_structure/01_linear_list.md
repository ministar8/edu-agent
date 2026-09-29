# 线性表 · 解题能力

> domain_kp: ds.linear
> document_id: advanced-ds-linear
> kb_depth: advanced
> doc_role: method

## 本章解决什么

- 顺序表 / 链表基本操作与边界
- 双链表、循环链表变形题
- 插入删除指针画法与错误模式
- 特殊矩阵压缩下标计算
- KMP 匹配过程与 next 求法

---

## 顺序表插入删除与定位

> section_id: advanced-ds-linear-seq_ops
> kp_ids: [ds.linear.seq_list, ds.linear.list]
> primary_kp: ds.linear.seq_list
> topic_tags: [代码, 计算]
> scope: single
> difficulty: 2

**识别信号**：给顺序表存储位置，问插入/删除后元素地址、移动次数，或写插入删除代码。

**方法步骤**：

1. **插入第 i 个位置**（1-based）：从后往前把 `a[n-1]…a[i-1]` 后移，空出 i，再写入；平均移动 `(n)/2` 次  
2. **删除第 i 个**：读出后从 i 往后前移，平均移动 `(n-1)/2` 次  
3. 地址题：`LOC(a_i) = LOC(a_1) + (i-1)*L`，插入后原元素下标会变  
4. 代码题：先判表满/表空、`i` 合法（`1≤i≤n+1` 插入；`1≤i≤n` 删除）

**易错点**：

- 插入位置合法范围与删除不同（插入可到 `n+1`）  
- 移动方向：插入从后往前，删除从前往后  
- 下标从 0 还是 1 开始要与题面一致  

**变式**：给定操作序列求最终表；比较顺序表与链表某操作的时间复杂度。

---

## 链表插入删除与建表

> section_id: advanced-ds-linear-linked_ops
> kp_ids: [ds.linear.linked_list, ds.linear.seq_list]
> primary_kp: ds.linear.linked_list
> topic_tags: [代码, 分析]
> scope: single
> difficulty: 2

**识别信号**：写单链表插入/删除/逆置/建表，或判断给定指针操作序列是否正确。

**方法步骤**：

1. **插入**：`s->next = p->next; p->next = s;`（顺序不能反）  
2. **删除 p 的后继**：`q = p->next; p->next = q->next; free(q)`  
3. **头插建表**：逆序；**尾插建表**：正序（需尾指针）  
4. **逆置**：三指针 `pre/cur/nxt` 逐个头插，或递归  

**易错点**：

- 插入先挂 `s->next` 再改 `p->next`，反了会丢链  
- 删除后继比删除自身方便；删自身需前驱  
- 释放结点前先保存 `next`  

**变式**：删除最小值结点；合并两个递增链表；带尾指针的循环链表拼接。

---

## 双链表与循环链表

> section_id: advanced-ds-linear-linked_variants
> kp_ids: [ds.linear.doubly_linked, ds.linear.circular_linked]
> primary_kp: ds.linear.doubly_linked
> topic_tags: [代码, 选择]
> scope: single
> difficulty: 2

**识别信号**：双链表结点前插/删除，或循环链表判断空、拼接两表。

**方法步骤**：

1. **双链表后插 s 于 p 后**：改四条指针 `s->next/pre` 与 `p->next->pre`、`p->next`  
2. **双链表删除 p**：`p->pre->next = p->next; p->next->pre = p->pre`  
3. **循环单链表空**：`head->next == head`  
4. **两循环表拼接**：先取各表尾，再 O(1) 对接；用尾指针比头指针方便  

**易错点**：

- 双链表改链顺序导致 `p->next` 丢失  
- 循环链表死循环：判断应用 `p != head`  
- 尾指针循环链表与头指针结构不要混用公式  

**变式**：循环双链表；约瑟夫环（循环链表模拟）。

---

## 特殊矩阵压缩存储

> section_id: advanced-ds-linear-matrix_compress
> kp_ids: [ds.array.compressed, ds.array.symmetric, ds.array.triangular, ds.array.sparse]
> primary_kp: ds.array.compressed
> topic_tags: [计算, 选择]
> scope: single
> difficulty: 3

**识别信号**：对称/三角/稀疏矩阵存入一维数组，求某元素下标或一维长度。

**方法步骤**：

1. **对称矩阵**：只存下三角（或上三角），先算前 `i-1` 行元素个数再加列偏移；注意 `i,j` 谁大谁小  
2. **三角矩阵**：同对称，再加常量区一个位置  
3. **稀疏矩阵三元组**：存 `(row, col, value)`，求某位置需查表；**不能** O(1) 随机存  
4. 下标题：统一 0-based / 1-based，写清「按列优先还是按行优先」  

**易错点**：

- 下标从 0 还是 1 开始导致差 1  
- 对称矩阵 `a_ij` 与 `a_ji` 存哪一半搞反  
- 把压缩存储当成能 O(1) 访问任意元素  

**变式**：给下标求原矩阵坐标；比较三元组与十字链表适用场景。

---

## KMP 匹配与 next 数组

> section_id: advanced-ds-linear-kmp_match
> kp_ids: [ds.string.kmp, ds.string.match]
> primary_kp: ds.string.kmp
> topic_tags: [计算, 代码]
> scope: single
> difficulty: 3

**识别信号**：求 `next` / `nextval`，或问匹配过程中字符比较次数。

**方法步骤**：

1. **next[j]（1-based）**：模式前缀 `1…j-1` 的**最长相等前后缀**长度 + 1  
2. **nextval**：若 `p[j] == p[next[j]]` 则继承 `nextval[next[j]]`，否则等于 `next[j]`  
3. **匹配失败**：`i` 不回溯，`j = next[j]`；比较次数要按实际走的路径数  
4. 求 next 时对 `j=1` 约定 `0` 或 `1` 必须按教材定义，与选项对齐  

**易错点**：

- next 定义不同教材下标不同，先确认约定再算  
- 把「前后缀长度」与「next 值」差 1  
- nextval 未优化时与 next 混用  

**变式**：手工模拟匹配到成功/失败；改写求 `nextval`；求平均比较次数。

---

## 数组地址与特殊矩阵

> section_id: advanced-ds-linear-matrix_addr
> kp_ids: [ds.array.compressed, ds.array.symmetric, ds.array.sparse]
> primary_kp: ds.array.symmetric
> topic_tags: [计算, 选择]
> scope: single
> difficulty: 3

**识别信号**：多维数组地址公式；对称/三角/稀疏下标互转。

**方法步骤**：

1. **行优先** `LOC = base + (i·n + j)·L`（0-based）；列优先对称互换  
2. **对称下三角**：第 i 行有 i 个元素；`k = i(i-1)/2 + j`（1-based，j≤i）  
3. **上三角**：`k = (i-1)(2n-i+2)/2 + (j-i)` 等，先推「前面多少个」  
4. **三元组**：非零元 `(row,col,value)`；矩阵转置重排行列  

**易错点**：

- 0/1 起始差 1  
- 行优先/列优先公式对调  
- 对称存哪半区搞反  

**变式**：给 N[k] 求 i,j；两矩阵压缩空间比较。

---

## 链表操作与变形

> section_id: advanced-ds-linear-linked_ops2
> kp_ids: [ds.linear.linked_list, ds.linear.doubly_linked, ds.linear.circular_linked]
> primary_kp: ds.linear.linked_list
> topic_tags: [代码, 分析]
> scope: single
> difficulty: 3

**识别信号**：逆置；合并有序链表；循环链表判空与拼接；双链表改链顺序。

**方法步骤**：

1. **逆置**：三指针迭代或递归头插  
2. **合并两递增**：双指针摘结点，尾插  
3. **循环判空**：`head->next==head`；拼接用尾指针 O(1)  
4. **双链表**：先挂 `s->next/pre` 再改邻居  

**易错点**：

- 逆置丢 next  
- 合并未处理剩余链  
- 双链表改链顺序反了  

**变式**：带尾指针循环链表交集；删除重复结点。


