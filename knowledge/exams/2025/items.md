# 2025 年 408 真题 · items

> document_id: exam-2025-items
> exam_year: 2025
> kb_depth: exams
> doc_role: exam_item
> source_type: third_party
> credibility: high
> explanation_status: none

答案只在 metadata（answer_key），正文不印答案。

## 2025-Q1

> question_id: 2025-Q1
> exam_year: 2025
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: ds
> kp_ids: []
> answer_key: B
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: complete
> gap_status: none
> gap_fields: []

**题干**：下列程序段的时间复杂度是 。 int count=0, i, j; for(i=1; i*i<=n; i++) for(j=1; j<=i; j++) count ++;

- A. O(log n)
- B. O(n)
- C. O(n log n)
- D. O(n 2 )

---

## 2025-Q2

> question_id: 2025-Q2
> exam_year: 2025
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: ds
> kp_ids: [ds.stack_queue.stack]
> answer_key: B
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: complete
> gap_status: none
> gap_fields: []

**题干**：已知算法 A用于检查字符串中各类括号是否匹配，A执行过程中使用初始为空的栈保存遇到的括 号。若栈的容量是 3，则下列选项中，A不能．．处理的是 。

- A. (a + [b + (c + d) / e] + f) + g – h
- B. [a * ((b + c) / (d – e) + f / g) - h]
- C. [a * (b – (c – d) * e / (f + g)) – h]
- D. [a – (b + [c * (d + e) – f] + g + h)]

---

## 2025-Q3

> question_id: 2025-Q3
> exam_year: 2025
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: ds
> kp_ids: [ds.tree.forest_convert]
> answer_key: D
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: complete
> gap_status: none
> gap_fields: []

**题干**：若二叉树的结点值均为正整数，采用顺序存储方式保存在数组 R 中，用－1 表示结点不存在，则 下列数组中，不能．．表示一棵二叉树的是 。

- A. R[]={20, 15, 40, －1, －1, 35}
- B. R[]={ 15, 40, 10, 18, 35, －1, －1}
- C. R[]={15, 40, 10, －1, －1, －1, 12}
- D. R[]={ 17, 20, 35, －1, 18, 45, －1, －1, 19, 27}

---

## 2025-Q4

> question_id: 2025-Q4
> exam_year: 2025
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: ds
> kp_ids: [ds.tree.forest_convert]
> answer_key: D
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: complete
> gap_status: none
> gap_fields: []

**题干**：下列关于二叉树及森林的叙述中，正确的是

- A. 完全二叉树中不存在度为 1 的结点
- B. 任意一个森林都可以转换为一棵二叉树
- C. 二叉树的分支结点个数比叶结点个数少
- D. 表达式树的根中保存的是最先计算的运算符

---

## 2025-Q5

> question_id: 2025-Q5
> exam_year: 2025
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: ds
> kp_ids: [ds.tree.huffman]
> answer_key: B
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: complete
> gap_status: none
> gap_fields: []

**题干**：设字符集 S包含 7 个字符，各字符出现的频次分别为 2, 3, 4, 6, 8, 10, 11。现为 S中的各字符构造 哈夫曼编码，编码长度不小于．．．3 的字符个数是 。

- A. 2
- B. 3
- C. 4
- D. 5

---

## 2025-Q6

> question_id: 2025-Q6
> exam_year: 2025
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: ds
> kp_ids: [ds.graph.shortest_path]
> answer_key: D
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: complete
> gap_status: none
> gap_fields: []

**题干**：下列关于图的叙述中，正确的是 。

- A. 有向图必存在入度为 0 的顶点
- B. 有向无环图的拓扑有序序列存在且唯一
- C. 各顶点的度均大于等于 2 的无向图必有回路
- D. 可用 BFS 算法求出带权图中每一对顶点间的最短路径

---

## 2025-Q7

> question_id: 2025-Q7
> exam_year: 2025
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: ds
> kp_ids: [ds.search.block]
> answer_key: C
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: complete
> gap_status: none
> gap_fields: []

**题干**：已知查找表中有 400 个元素， 查找每个元素的概率相同。 采用分块查找法进行查找， 且均匀分块。 若采用顺序查找法确定元素所在的块，且块内也采用顺序查找法，为使查找效率最高，则每块包 含的元素个数应为 。

- A. 8
- B. 10
- C. 20
- D. 25

---

## 2025-Q8

> question_id: 2025-Q8
> exam_year: 2025
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: ds
> kp_ids: [ds.search.b_tree]
> answer_key: C
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: complete
> gap_status: none
> gap_fields: []

**题干**：给定 7 个不同的关键字，能够构造的不同 4 阶B 树的个数最多是 。

- A. 7
- B. 8
- C. 9
- D. 10

---

## 2025-Q9

> question_id: 2025-Q9
> exam_year: 2025
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: ds
> kp_ids: [ds.search.hash]
> answer_key: C
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: complete
> gap_status: none
> gap_fields: []

**题干**：下列关于散列方法处理冲突的叙述中，正确的是 。

- A. 只要散列表不满，线性探查再散列一定能找到一个空闲位置
- B. 只要散列表不满，二次探查再散列一定能找到一个空闲位置
- C. 线性探查再散列处理的冲突，一定是发生在同义词之间的冲突
- D. 二次探查再散列处理的冲突，一定是发生在非同义词之间的冲突

---

## 2025-Q10

> question_id: 2025-Q10
> exam_year: 2025
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: ds
> kp_ids: [ds.sort.quick_sort]
> answer_key: A
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: complete
> gap_status: none
> gap_fields: []

**题干**：下列排序算法中，最坏情况下元素移动次数最少的是 。

- A. 起泡排序
- B. 直接插入排序
- C. 快速排序
- D. 简单选择排序 --- page 2 --- 2025 年全国硕士研究生入学统一考试计算机学科专业基础综合试题 第 2 页（共 12 页）

---

## 2025-Q11

> question_id: 2025-Q11
> exam_year: 2025
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: ds
> kp_ids: [ds.search.binary_search]
> answer_key: D
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: complete
> gap_status: none
> gap_fields: []

**题干**：对含 9 个关键字的初始序列进行排序，若序列的变化情况如下表所示，则下列排序算法中，采用 的是 。 初始序列 5, 25, 40, 30, 10, 20, 45, 15, 35 第 1 趟排序后的序列 5, 10, 20, 30, 15, 35, 45, 25, 40 第 2 趟排序后的序列 5, 10, 15, 25, 20, 30, 40, 35, 45

- A. 希尔排序
- B. 基数排序
- C. 归并排序
- D. 折半插入排序

---

## 2025-Q12

> question_id: 2025-Q12
> exam_year: 2025
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: os
> kp_ids: [os.process.state]
> answer_key: A
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: complete
> gap_status: none
> gap_fields: []

**题干**：在 32 位计算机上执行下列C 语言代码段后，ui 的值是 。 short si=-32767; unsigned int ui=si;

- A. 2 15 – 1
- B. 2 15 + 1
- C. 2 32 – 2 15 – 1
- D. 2 32 – 2 15 + 1

---

## 2025-Q13

> question_id: 2025-Q13
> exam_year: 2025
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: co
> kp_ids: [co.representation.ieee754]
> answer_key: D
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: complete
> gap_status: none
> gap_fields: []

**题干**：已知 float 型变量用 IEEE 754 单精度浮点数格式表示。若float 型变量 x 的机器数为 4730 0000H， 则 x的值是 。

- A. 0.375×2 14
- B. 1.375×2 14
- C. 0.375×2 15
- D. 1.375×2 15

---

## 2025-Q14

> question_id: 2025-Q14
> exam_year: 2025
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: co
> kp_ids: [co.representation.complement]
> answer_key: D
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: complete
> gap_status: none
> gap_fields: []

**题干**：假设 8 位字长的计算机中，两个带符号整数x 和 y 的补码表示分别为[x]补=A3H、[y]补=75H，则通 过补码加减运算器得到的 x – y的值及 OF 标志分别为 。

- A. 24, 0
- B. 24, 1
- C. 46, 0
- D. 46, 1

---

## 2025-Q15

> question_id: 2025-Q15
> exam_year: 2025
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: co
> kp_ids: [co.cpu.datapath]
> answer_key: D
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: complete
> gap_status: none
> gap_fields: []

**题干**：某 32 位计算机按字节编址，采用小端方式存放数据，编译器按边界对齐方式为下列C 语言结构 型数组变量 employee 分配存储空间。 struct record{ int id; char name[10]; int salary; } employee[200]; 若 employee 的首地址为 0000 A0B0H，employee[1].id 的机器数为 1234 5678H，则该机器数中的 56H所在存储单元的地址是 。

- A. 0000 A0C3H
- B. 0000 A0C4H
- C. 0000 A0C5H
- D. 0000 A0C6H

---

## 2025-Q16

> question_id: 2025-Q16
> exam_year: 2025
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: co
> kp_ids: [co.cpu.datapath]
> answer_key: C
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: complete
> gap_status: none
> gap_fields: []

**题干**：下列选项中，由指令集体系结构（ISA）规定的是 。

- A. 是否采用阵列乘法器
- B. 是否采用定长指令字格式
- C. 是否采用微程序控制器
- D. 是否采用单总线数据通路

---

## 2025-Q17

> question_id: 2025-Q17
> exam_year: 2025
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: co
> kp_ids: [co.cpu.pipeline]
> answer_key: B
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: complete
> gap_status: none
> gap_fields: []

**题干**：下列关于 RISC 的叙述中，错误．．的是

- A. 多采用硬连线方式实现控制器
- B. 通常采用 Load/Store 型指令设计风格
- C. 难以采用流水线数据通路实现微架构
- D. 多采用寄存器传递过程调用时的参数

---

## 2025-Q18

> question_id: 2025-Q18
> exam_year: 2025
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: co
> kp_ids: [co.cpu.pipeline]
> answer_key: C
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: complete
> gap_status: none
> gap_fields: []

**题干**：下列关于 CPI 和 CPU时钟周期的叙述中，错误．．的是

- A. 不同类型指令的 CPI 可能不一样
- B. 程序的 CPI 与 Cache缺失率无关
- C. 单周期 CPU 的时钟周期以最耗时指令所用时间为准
- D. 流水线 CPU 的时钟周期以最长流水段所用时间为准

---

## 2025-Q19

> question_id: 2025-Q19
> exam_year: 2025
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: co
> kp_ids: [co.cpu.pipeline]
> answer_key: B
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: complete
> gap_status: none
> gap_fields: []

**题干**：下列关于 CPU 中的数据通路和控制器的叙述中，错误．．的是

- A. 通用寄存器组中应该包含程序计数器
- B. 控制器中一定包含指令操作码的译码电路
- C. 单周期 CPU 中的控制器比多周期 CPU 中的更简单
- D. 流水线 CPU 需解决数据相关和控制相关等冒险问题

---

## 2025-Q20

> question_id: 2025-Q20
> exam_year: 2025
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: co
> kp_ids: [co.bus.bandwidth]
> answer_key: A
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: complete
> gap_status: none
> gap_fields: []

**题干**：某处理器总线采用同步、并行传输方式，每个总线时钟周期传送 4 次数据（quadpumped 技术） 。 若该总线的工作频率为 1333MHz（实际单位是 MT/s，表示每秒传送 1333M 次） ，总线宽度为 64 位，则总线带宽约为 。

- A. 10.66 GB/s
- B. 42.66 GB/s
- C. 85.31 GB/s
- D. 341.25 GB/s --- page 3 --- 2025 年全国硕士研究生入学统一考试计算机学科专业基础综合试题 第 3 页（共 12 页）

---

## 2025-Q21

> question_id: 2025-Q21
> exam_year: 2025
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: co
> kp_ids: [co.cpu.exception]
> answer_key: A
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: complete
> gap_status: none
> gap_fields: []

**题干**：下列设备中，适合采用 DMA输入/输出方式的是 。 I. 键盘 II. 网卡 III. 固态硬盘 IV . 针式打印机

- A. 仅 I、II
- B. 仅 II、III
- C. 仅 II、IV
- D. 仅 III、IV

---

## 2025-Q22

> question_id: 2025-Q22
> exam_year: 2025
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: co
> kp_ids: [co.cpu.exception]
> answer_key: B
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: complete
> gap_status: none
> gap_fields: []

**题干**：下列选项中，会触发外部中断请求的事件是 。

- A. DMA传送结束
- B. 总线事务结束
- C. 页故障处理结束
- D. 执行断点指令

---

## 2025-Q23

> question_id: 2025-Q23
> exam_year: 2025
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: co
> kp_ids: [co.cpu.exception]
> answer_key: A
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: complete
> gap_status: none
> gap_fields: []

**题干**：在采用页式虚拟存储管理方式的系统中，当发生进程上下文切换时，下列寄存器中，操作系统不． 需要．．更新的是 。

- A. 通用寄存器
- B. 页表基址寄存器
- C. 程序计数器
- D. 内核中断向量表基址寄存器

---

## 2025-Q24

> question_id: 2025-Q24
> exam_year: 2025
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: os
> kp_ids: [os.overview.feature]
> answer_key: D
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: complete
> gap_status: none
> gap_fields: []

**题干**：下列关于虚拟化技术的叙述中，错误．．的是 。

- A. 操作系统可以运行在虚拟机上
- B. 虚拟化技术支持在一台计算机上构建多个虚拟机
- C. 虚拟机监控程序（VMM）与操作系统的特权级相同
- D. 虚拟化技术支持在一台计算机上模拟不同的指令集体系结构

---

## 2025-Q25

> question_id: 2025-Q25
> exam_year: 2025
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: ds
> kp_ids: [ds.linear.linked_list]
> answer_key: C
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: complete
> gap_status: none
> gap_fields: []

**题干**：某基于优先权的进程调度程序中，进程就绪队列采用优先权由高到低的有序单链表实现。若就绪 队列长度为 n，则就绪队列的插入操作和从就绪队列中选出将要执行进程的操作的时间复杂度分 别是 。

- A. O(1)，O(1)
- B. O(1)，O(n)
- C. O(n)，O(1)
- D. O(n)，O(n)

---

## 2025-Q26

> question_id: 2025-Q26
> exam_year: 2025
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: co
> kp_ids: [co.cpu.exception]
> answer_key: C
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: complete
> gap_status: none
> gap_fields: []

**题干**：某页式虚拟存储管理系统采用固定分配局部置换的 LRU 算法。若系统为进程 P 分配了 3 个页框， P 从某时刻开始的页访问序列为 0, 1, 2, 0, 5, 1, 4, 3, 0, 2, 3, 2, 0，且 0, 1, 2 三个页已在内存中，则 完成上述页序列的访问时，系统执行缺页异常处理程序的次数为 。

- A. 5
- B. 6
- C. 7
- D. 8

---

## 2025-Q27

> question_id: 2025-Q27
> exam_year: 2025
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: co
> kp_ids: [co.instruction.addressing]
> answer_key: B
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: complete
> gap_status: none
> gap_fields: []

**题干**：在页式虚拟存储管理系统中，确定进程正常运行所需的最少页框数时，下列因素中需要考虑的 是 。

- A. 代码段长度
- B. 进程的虚拟地址空间大小
- C. 物理内存大小
- D. 指令系统支持的寻址方式

---

## 2025-Q28

> question_id: 2025-Q28
> exam_year: 2025
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: os
> kp_ids: [os.memory.virtual]
> answer_key: D
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: complete
> gap_status: none
> gap_fields: []

**题干**：下列关于虚拟文件系统（VFS）的叙述中，正确的是 。

- A. VFS是在虚拟内存中建立的文件系统
- B. VFS能提高不同文件系统中文件的访问速度
- C. VFS定义了可以访间不同文件系统的统一接口
- D. 通过 VFS 只能访问本地文件，不能访问网络文件

---

## 2025-Q29

> question_id: 2025-Q29
> exam_year: 2025
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: os
> kp_ids: [os.file.dir]
> answer_key: C
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: complete
> gap_status: none
> gap_fields: []

**题干**：某文件系统采用目录和索引节点管理文件，当用户在目录中新建文件 F 时，下列操作中，文件系 统不会．．做的是 。

- A. 对 F 的索引节点进行初始化
- B. 在目录文件中写入 F 的索引节点号
- C. 在目录文件中写入 F 的访问权限信息
- D. 在目录文件中增加一条 F 对应的目录项

---

## 2025-Q30

> question_id: 2025-Q30
> exam_year: 2025
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: os
> kp_ids: [os.memory.virtual]
> answer_key: C
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: complete
> gap_status: none
> gap_fields: []

**题干**：下列关于内存映射文件（memory-mapped files）机制的叙述中，正确的是 。 I. 可实现进程之间的通信 II. 可实现页到磁盘块的映射 III. 将文件映射到进程的虚拟地址空间 IV . 将文件映射到系统的物理地址空间

- A. 仅 I、III
- B. 仅 I、IV
- C. 仅 II、III
- D. 仅 I、II、III

---

## 2025-Q31

> question_id: 2025-Q31
> exam_year: 2025
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: os
> kp_ids: [os.file.alloc]
> answer_key: A
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: complete
> gap_status: none
> gap_fields: []

**题干**：下列选项中，文件系统可用于记录外存空闲空间使用情况的是 。

- A. 目录
- B. 系统打开文件表
- C. 文件分配表（FAT）
- D. 文件控制块（FCB）

---

## 2025-Q32

> question_id: 2025-Q32
> exam_year: 2025
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: os
> kp_ids: [os.file.disk_schedule]
> answer_key: C
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: complete
> gap_status: none
> gap_fields: []

**题干**：下列选项中，文件系统需要为温彻斯特硬盘和固态硬盘都提供的功能是 。

- A. 划分扇区
- B. 确定盘块大小
- C. 降低寻道时间
- D. 实现均衡磨损 --- page 4 --- 2025 年全国硕士研究生入学统一考试计算机学科专业基础综合试题 第 4 页（共 12 页）

---

## 2025-Q33

> question_id: 2025-Q33
> exam_year: 2025
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: ds
> kp_ids: [ds.graph.topo]
> answer_key: B
> reference_answer: null
> has_figure: true
> figure_status: missing
> completeness: partial
> gap_status: partial
> gap_fields: [figure]

**题干**：某网络拓扑及各链路带宽如题 33 图所示。网络按电路交换方式运行时，主机H1 与H2 建立一条 带宽为 10Mb/s 的电路，建立电路时间为 32μs；按分组交换方式运行时，分组长度为 400B，忽略 分组首部开销。现 H1 向H2 发送一个 2MB（1M = 10 6 ）的文件，分别采用电路交换、报文交换、 分组交换方式时，H2 至少需要TCS、TMS、TPS时间才能接收到全部文件内容，则 TCS、TMS、TPS满 足的关系是 题 33 图

- A. TCS > TMS > TPS
- B. TMS > TPS > TCS
- C. TMS > TCS > TPS
- D. TPS > TMS > TCS

---

## 2025-Q34

> question_id: 2025-Q34
> exam_year: 2025
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: cn
> kp_ids: [cn.datalink.error_control]
> answer_key: B
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: complete
> gap_status: none
> gap_fields: []

**题干**：若某差错编码的编码集为{1001 1010, 0101 1100, 1111 0000, 0000 1111}，则该差错编码的检错和纠 错能力是

- A. 不超过 2 位错的 100%检错、不超过 1 位错的纠错
- B. 不超过 2 位错的 100%检错、不超过 2 位错的纠错
- C. 不超过 3 位错的 100%检错、不超过 1 位错的纠错
- D. 不超过 3 位错的 100%检错、不超过 2 位错的纠错

---

## 2025-Q35

> question_id: 2025-Q35
> exam_year: 2025
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: ds
> kp_ids: [ds.search.hash]
> answer_key: C
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: complete
> gap_status: none
> gap_fields: []

**题干**：在某个 10BaseT以太网的冲突域内，若主机甲向主机乙发送数据帧时发生了连续 11 次冲突，则甲 再次尝试发送该数据帧的最大间隔时间是 。

- A. 0.512ms
- B. 0.5632ms
- C. 52.3776ms
- D. 104.8064ms

---

## 2025-Q36

> question_id: 2025-Q36
> exam_year: 2025
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: cn
> kp_ids: [cn.network.ip_address]
> answer_key: C
> reference_answer: null
> has_figure: true
> figure_status: missing
> completeness: partial
> gap_status: partial
> gap_fields: [figure]

**题干**：一台新接入网络的主机 H通过 DHCP服务器动态请求 IP地址过程中， 与DHCP服务器交换 DHCP 报文的部分过程如题 36 图所示。封装DHCPREQUEST 报文的 IP 数据报的目的 IP 地址和源 IP 地 址分别是 题 36 图

- A. 192.168.5.1, 0.0.0.0
- B. 192.168.5.1, 192.168.5.9
- C. 255.255.255.255, 0.0.0.0
- D. 255.255.255.255, 192.168.5.9

---

## 2025-Q37

> question_id: 2025-Q37
> exam_year: 2025
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: co
> kp_ids: [co.cpu.pipeline]
> answer_key: C
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: complete
> gap_status: none
> gap_fields: []

**题干**：假设路由器实现 NAT功能， 内网中主机H的 IP 地址为 192.168.1.5/24。 若H运行某应用向 Internet 发送了一个 UDP 报文段，则路由器在转发封装该 UDP 报文段的 IP 数据报的过程中，UDP 报文 段的首部字段会被修改的是 I. 源端口号 II. 目的端口号 III. 总长度 IV . 校验和

- A. 仅 I、III
- B. 仅 I、IV
- C. 仅 II、III
- D. 仅 II、IV --- page 5 --- 2025 年全国硕士研究生入学统一考试计算机学科专业基础综合试题 第 5 页（共 12 页）

---

## 2025-Q38

> question_id: 2025-Q38
> exam_year: 2025
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: cn
> kp_ids: [cn.transport.tcp]
> answer_key: B
> reference_answer: null
> has_figure: true
> figure_status: missing
> completeness: partial
> gap_status: partial
> gap_fields: [figure]

**题干**：主机甲通过 TCP 向主机乙发送数据的部分过程如题 38 图所示，seq为序号，ack_seq为确认序号， rcvwnd 为接收窗口。甲在 t0 时刻的拥塞窗口和发送窗口均为 2000B，拥塞控制值为 8000B， MSS=1000B，甲始终以 MSS 发送 TCP 段。若甲在 t1时刻收到如图所示的确认段，则甲在未收到 新的确认段之前，还可以继续向乙发送的 TCP 段数是 题 38 图

- A. 2
- B. 3
- C. 4
- D. 5

---

## 2025-Q39

> question_id: 2025-Q39
> exam_year: 2025
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: cn
> kp_ids: [cn.transport.tcp]
> answer_key: A
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: complete
> gap_status: none
> gap_fields: []

**题干**：Time 是一个提供时间查询服务的 C/S 架构网络应用，支持客户通过 UDP 或 TCP 向 Time 服务器 请求时间服务。若某客户与某Time服务器通信的往返时间 RTT=8ms，则该客户分别通过UDP和 TCP 向该服务器请求服务，所需的最少时间分别是

- A. 8ms, 8ms
- B. 8ms, 16ms
- C. 16ms, 8ms
- D. 16ms, 16ms

---

## 2025-Q40

> question_id: 2025-Q40
> exam_year: 2025
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: cn
> kp_ids: [cn.transport.tcp]
> answer_key: B
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: complete
> gap_status: none
> gap_fields: []

**题干**：下列关于 POP3 协议的叙述中，正确的是 I. 支持用户代理从邮件服务器读取邮件 II. 支持用户代理向邮件服务器发送邮件 III. 支持邮件服务器之间发送与接收邮件 IV . 支持通过一条 TCP 连接收取多封邮件

- A. 仅 I、IV
- B. 仅 II、III
- C. 仅 I、II、III
- D. 仅 I、III、IV --- page 6 --- 2025 年全国硕士研究生入学统一考试计算机学科专业基础综合试题 第 6 页（共 12 页）

---

