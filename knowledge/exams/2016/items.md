# 2016 年 408 真题 · items

> document_id: exam-2016-items
> exam_year: 2016
> kb_depth: exams
> doc_role: exam_item
> source_type: third_party
> credibility: high
> explanation_status: scan

答案只在 metadata（answer_key），正文不印答案。

## 2016-Q1

> question_id: 2016-Q1
> exam_year: 2016
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: ds
> kp_ids: [ds.linear.linked_list]
> answer_key: null
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: partial
> gap_status: partial
> gap_fields: [answer]

**题干**：已知表头元素为 c 的单链表在内存中的存储状态如下表所示。 地址 元素 链接地址 1000H a 1010H 1004H b 100CH 1008H c 1000H 100CH d NULL 1010H e 1004H 1014H 现将 f 存放于 1014H 处并插入到单链表中，若 f 在逻辑上位于 a 和 e 之间，则 a, e, f 的“链接地 址”依次是 。

- A. 1010H，1014H，1004H
- B. 1010H，1004H，1014H
- C. 1014H，1010H，1004H
- D. 1014H，1004H，1010H

---

## 2016-Q2

> question_id: 2016-Q2
> exam_year: 2016
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: ds
> kp_ids: [ds.linear.linked_list]
> answer_key: D
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: complete
> gap_status: none
> gap_fields: []

**题干**：已知一个带有表头结点的双向循环链表 L，结点结构为 prev data next ，其中，prev 和 next 分别是指向其直接前驱和直接后继结点的指针。现要删除指针 p 所指的结点，正确的语句序列 是 。

- A. p->next->prev=p->prev; p->prev->next=p->prev; free(p);
- B. p->next->prev=p->next; p->prev->next=p->next; free(p);
- C. p->next->prev=p->next; p->prev->next=p->prev; free(p);
- D. p->next->prev=p->prev;p->prev->next=p->next; free(p);

---

## 2016-Q3

> question_id: 2016-Q3
> exam_year: 2016
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: ds
> kp_ids: [ds.stack_queue.stack]
> answer_key: null
> reference_answer: null
> has_figure: true
> figure_status: missing
> completeness: partial
> gap_status: partial
> gap_fields: [answer, figure]

**题干**：设有下图所示的火车车轨，入口到出口之间有 n 条轨道，列车的行进方向均为从左至右，列车可 驶入任意一条轨道。现有编号为 1～9 的 9 列列车，驶入的次序依次是 8，4，2，5，3，9，1， 6，7。若期望驶出的次序依次为 1～9，则 n 至少是 。

- A. 2
- B. 3
- C. 4
- D. 5

---

## 2016-Q4

> question_id: 2016-Q4
> exam_year: 2016
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: ds
> kp_ids: [ds.array.compressed]
> answer_key: null
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: partial
> gap_status: partial
> gap_fields: [answer]

**题干**：有一个 100 阶的三对角矩阵 M，其元素 mi,j （1≤i≤100，1≤j≤100）按行优先依次压缩存入下 标从 0 开始的一维数组 N 中。元素 m30, 30 在 N 中的下标是 。

- A. 86
- B. 87
- C. 88
- D. 89

---

## 2016-Q5

> question_id: 2016-Q5
> exam_year: 2016
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: ds
> kp_ids: [ds.tree.forest_convert]
> answer_key: null
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: partial
> gap_status: partial
> gap_fields: [answer]

**题干**：若森林 F 有 15 条边、25 个结点，则 F 包含树的个数是 。

- A. 8
- B. 9
- C. 10
- D. 11

---

## 2016-Q6

> question_id: 2016-Q6
> exam_year: 2016
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: ds
> kp_ids: [ds.graph.traversal]
> answer_key: null
> reference_answer: null
> has_figure: true
> figure_status: missing
> completeness: partial
> gap_status: partial
> gap_fields: [answer, figure]

**题干**：下列选项中，不是下图深度优先搜索序列的是 。

- A. V1, V5, V4, V3, V2
- B. V1, V3, V2, V5, V4
- C. V1, V2, V5, V4, V3
- D. V1, V2, V3,V4, V5 --- page 2 --- 2016 年全国硕士研究生入学统一考试计算机科学与技术学科联考计算机学科专业基础综合试题 第 2 页（共 12 页）

---

## 2016-Q7

> question_id: 2016-Q7
> exam_year: 2016
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: ds
> kp_ids: [ds.graph.topo]
> answer_key: null
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: partial
> gap_status: partial
> gap_fields: [answer]

**题干**：若将 n 个顶点 e 条弧的有向图采用邻接表存储，则拓扑排序算法的时间复杂度是 。

- A. O(n)
- B. O(n + e)
- C. O(n 2 )
- D. O(ne)

---

## 2016-Q8

> question_id: 2016-Q8
> exam_year: 2016
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: ds
> kp_ids: [ds.graph.shortest_path]
> answer_key: null
> reference_answer: null
> has_figure: true
> figure_status: missing
> completeness: partial
> gap_status: partial
> gap_fields: [answer, figure]

**题干**：使用迪杰斯特拉(Dijkstra)算法求下图中从顶点 1 到其他各顶点的最短路径，依次得到的各最短路 径的目标顶点是 。

- A. 5, 2, 3, 4, 6
- B. 5, 2, 3, 6, 4
- C. 5, 2, 4, 3, 6
- D. 5, 2, 6, 3, 4

---

## 2016-Q9

> question_id: 2016-Q9
> exam_year: 2016
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: ds
> kp_ids: [ds.search.binary_search]
> answer_key: B
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: complete
> gap_status: none
> gap_fields: []

**题干**：在有 n（n＞1000）个元素的升序数组 A 中查找关键字 x。查找算法的伪代码如下所示。 k=0; while(k<n 且A[k]<x) k=k+3; if(k<n 且A[k]==x) 查找成功; else if (k-1<n 且A[k-1]==x) 查找成功; else if(k-2<n且A[k-2]==x) 查找成功; else查找失败; 本算法与折半查找算法相比，有可能具有更少比较次数的情形是 。

- A. 当 x 不在数组中
- B. 当 x 接近数组开头处
- C. 当 x 接近数组结尾处
- D. 当 x 位于数组中间位置

---

## 2016-Q10

> question_id: 2016-Q10
> exam_year: 2016
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: ds
> kp_ids: [ds.search.b_tree]
> answer_key: null
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: partial
> gap_status: partial
> gap_fields: [answer]

**题干**：B+树不同于 B 树的特点之一是 。

- A. 能支持顺序查找
- B. 结点中含有关键字
- C. 根结点至少有两个分支
- D. 所有叶结点都在同一层上

---

## 2016-Q11

> question_id: 2016-Q11
> exam_year: 2016
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: ds
> kp_ids: [ds.sort.quick_sort]
> answer_key: null
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: partial
> gap_status: partial
> gap_fields: [answer]

**题干**：对 10TB 的数据文件进行排序，应使用的方法是 。

- A. 希尔排序
- B. 堆排序
- C. 快速排序
- D. 归并排序

---

## 2016-Q12

> question_id: 2016-Q12
> exam_year: 2016
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: co
> kp_ids: [co.instruction.isa]
> answer_key: null
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: partial
> gap_status: partial
> gap_fields: [answer]

**题干**：将高级语言源程序转换为机器级目标代码文件的程序是 。

- A. 汇编程序
- B. 链接程序
- C. 编译程序
- D. 解释程序

---

## 2016-Q13

> question_id: 2016-Q13
> exam_year: 2016
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: os
> kp_ids: [os.process.state]
> answer_key: null
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: partial
> gap_status: partial
> gap_fields: [answer]

**题干**：有如下 C 语言程序段 short si = -32767; unsigned short usi = si; 执行上述两条语句后，usi 的值为 。

- A. －32767
- B. 32767
- C. 32768
- D. 32769

---

## 2016-Q14

> question_id: 2016-Q14
> exam_year: 2016
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: co
> kp_ids: [co.cpu.datapath]
> answer_key: null
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: partial
> gap_status: partial
> gap_fields: [answer]

**题干**：计算机字长为 32 位，按字节编址，采用小端（Little Endian）方式存放数据。假定有一个 double 型变量，其机器数表示为 1122 3344 5566 7788H，存放在 0000 8040H 开始的连续存储单元中， 则存储单元 0000 8046H 中存放的是 。

- A. 22H
- B. 33H
- C. 77H
- D. 66H

---

## 2016-Q15

> question_id: 2016-Q15
> exam_year: 2016
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: co
> kp_ids: [co.storage.cache]
> answer_key: null
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: partial
> gap_status: partial
> gap_fields: [answer]

**题干**：有如下 C 语言程序段： for(k=0; k<1000; k++) a[k] = a[k]+32 若数组 a 及变量 k 均为 int 型，int 型数据占 4B，数据 Cache 采用直接映射方式，数据区大小为 1KB、块大小为 16B，该程序段执行前 Cache 为空，则该程序段执行过程中访问数组 a 的 Cache 缺失率约为 。

- A. 1.25％
- B. 2.5％
- C. 12.5％
- D. 25％

---

## 2016-Q16

> question_id: 2016-Q16
> exam_year: 2016
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: co
> kp_ids: [co.storage.main_memory]
> answer_key: null
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: partial
> gap_status: partial
> gap_fields: [answer]

**题干**：某存储器容量为 64KB，按字节编址，地址 4000H～5FFFH 为 ROM 区，其余为 RAM 区。若采 用 8K×4 位的 SRAM 芯片进行设计，则需要该芯片的数量是 。

- A. 7
- B. 8
- C. 14
- D. 16 --- page 3 --- 2016 年全国硕士研究生入学统一考试计算机科学与技术学科联考计算机学科专业基础综合试题 第 3 页（共 12 页）

---

## 2016-Q17

> question_id: 2016-Q17
> exam_year: 2016
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: co
> kp_ids: [co.instruction.format]
> answer_key: C
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: complete
> gap_status: none
> gap_fields: []

**题干**：某指令格式如下所示。 OP M I D 其中 M 为寻址方式，I 为变址寄存器编号，D 为形式地址。若采用先变址后间址的寻址方式，则 操作数的有效地址是 。

- A. I + D
- B. (I) + D
- C. ((I) + D)
- D. ((I)) + D

---

## 2016-Q18

> question_id: 2016-Q18
> exam_year: 2016
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: co
> kp_ids: [co.cpu.datapath]
> answer_key: null
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: partial
> gap_status: partial
> gap_fields: [answer]

**题干**：某计算机主存空间为 4GB，字长为 32 位，按字节编址，采用 32 位字长指令字格式。若指令按 字边界对齐存放，则程序计数器（PC）和指令寄存器（IR）的位数至少分别是 。

- A. 30、30
- B. 30、32
- C. 32、30
- D. 32、32

---

## 2016-Q19

> question_id: 2016-Q19
> exam_year: 2016
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: co
> kp_ids: [co.cpu.pipeline]
> answer_key: null
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: partial
> gap_status: partial
> gap_fields: [answer]

**题干**：在无转发机制的五段基本流水线（取指、译码/读寄存器、运算、访写回寄存器）中，下列指令 序列存在数据冒险的指令对是 I1：add R1, R2, R3; (R2) + (R3)→R1 I 2：add R5, R2, R4; (R2) + (R4)→R5 I3：add R4, R5, R3; (R5) + (R3)→R4 I 4：add R5, R2, R6; (R2) + (R6)→R5

- A. I1 和 12
- B. I 2 和 I3
- C. I 2 和 I4
- D. I 3 和 I4

---

## 2016-Q20

> question_id: 2016-Q20
> exam_year: 2016
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: co
> kp_ids: [co.cpu.pipeline]
> answer_key: null
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: partial
> gap_status: partial
> gap_fields: [answer]

**题干**：单周期处理器中所有指令的指令周期为一个时钟周期。下列关于单周期处理器的叙述中，错误的 是 。

- A. 可以采用单总线结构数据通路
- B. 处理器时钟频率较低
- C. 在指令执行过程中控制信号不变
- D. 每条指令的 CPI 为 1

---

## 2016-Q21

> question_id: 2016-Q21
> exam_year: 2016
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: co
> kp_ids: [co.bus.bandwidth]
> answer_key: null
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: partial
> gap_status: partial
> gap_fields: [answer]

**题干**：下列关于总线设计的叙述中，错误的是 。

- A. 并行总线传输比串行总线传输速度快
- B. 采用信号线复用技术可减少信号线数量
- C. 采用突发传输方式可提高总线数据传输率
- D. 采用分离事务通信方式可提高总线利用率

---

## 2016-Q22

> question_id: 2016-Q22
> exam_year: 2016
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: co
> kp_ids: [co.cpu.exception]
> answer_key: null
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: partial
> gap_status: partial
> gap_fields: [answer]

**题干**：异常是指令执行过程中在处理器内部发生的特殊事件，中断是来自处理器外部的请求事件。下列 关于中断或异常情况的叙述中，错误的是 。

- A. “访存时缺页”属于中断
- B. “整数除以 0”属于异常
- C. “DMA 传送结束”属于中断
- D. “存储保护错”属于异常

---

## 2016-Q23

> question_id: 2016-Q23
> exam_year: 2016
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: co
> kp_ids: [co.cpu.exception]
> answer_key: null
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: partial
> gap_status: partial
> gap_fields: [answer]

**题干**：下列关于批处理系统的叙述中，正确的是 I. 批处理系统允许多个用户与计算机直接交互 II. 批处理系统分为单道批处理系统和多道批处理系统 III. 中断技术使得多道批处理系统和 I/O 设备可与 CPU 并行工作

- A. 仅 II、III
- B. 仅 II
- C. 仅 I、II
- D. 仅 I、III

---

## 2016-Q24

> question_id: 2016-Q24
> exam_year: 2016
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: os
> kp_ids: [os.process.state]
> answer_key: null
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: partial
> gap_status: partial
> gap_fields: [answer]

**题干**：某单 CPU 系统中有输入和输出设备各 1 台，现有 3 个并发执行的作业，每个作业的输入、计算 和输出时间均分别为 2ms、3ms 和 4ms，且都按输入、计算和输出的顺序执行，则执行完 3 个作 业需要的时间最少是 。

- A. 15ms
- B. 17ms
- C. 22ms
- D. 27ms

---

## 2016-Q25

> question_id: 2016-Q25
> exam_year: 2016
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: os
> kp_ids: [os.process.deadlock]
> answer_key: C
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: complete
> gap_status: none
> gap_fields: []

**题干**：系统中有 3 个不同的临界资源 R1, R2 和 R3，被 4 个进程 p1, p2, p3 及 p4 共享。各进程对资源的需求 为：p1 申请 R1 和 R2，p2 申请 R2 和 R3，p3 申请 R1 和 R3，p4 申请 R2。若系统出现死锁，则处于死锁 状态的进程数至少是 。

- A. 1
- B. 2
- C. 3
- D. 4

---

## 2016-Q26

> question_id: 2016-Q26
> exam_year: 2016
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: os
> kp_ids: [os.memory.paging]
> answer_key: null
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: partial
> gap_status: partial
> gap_fields: [answer]

**题干**：某系统采用改进型 CLOCK 置换算法，页表项中字段 A 为访问位，M 为修改位。A = 0 表示页最 近没有被访问，A = 1 表示页最近被访问过。M=0 表示页没有被修改过，M=1 表示页被修改过。 按(A, M)所有可能的取值，将页分为四类：(0, 0), (1, 0), (0, 1)和(1, 1)，则该算法淘汰页的次序 为 。

- A. (0, 0), (0, 1), (1, 0), (1, 1)
- B. ( 0, 0), (1, 0), (0, 1), (1, 1)
- C. (0, 0), (0, 1), (1, 1), (1, 0)
- D. ( 0, 0), (1, 1), (1, 0), (0, 1)

---

## 2016-Q27

> question_id: 2016-Q27
> exam_year: 2016
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: co
> kp_ids: [co.cpu.exception]
> answer_key: null
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: partial
> gap_status: partial
> gap_fields: [answer]

**题干**：使用 TSL（Test and Set Lock）指令实现进程互斥的伪代码如下所示。 do{ … while(TSL(&lock)); --- page 4 --- 2016 年全国硕士研究生入学统一考试计算机科学与技术学科联考计算机学科专业基础综合试题 第 4 页（共 12 页） critical section; lock=FALSE … }while(TRUE) 下列与该实现机制相关的叙述中，正确的是 。

- A. 退出临界区的进程负责唤醒阻塞态进程
- B. 等待进入临界区的进程不会主动放弃 CPU
- C. 上述伪代码满足“让权等待”的同步准则
- D. while(TSL(&lock))语句应在关中断状态下执行

---

## 2016-Q28

> question_id: 2016-Q28
> exam_year: 2016
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: co
> kp_ids: [co.cpu.exception]
> answer_key: null
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: partial
> gap_status: partial
> gap_fields: [answer]

**题干**：某进程的段表内容如下所示。 段号 段长 内存起始地址 权限 状态 0 100 6000 只读 在内存 1 200 … 读写 不在内存 2 300 4000 读写 在内存 当访问段号为 2、段内地址为 400 的逻辑地址时，进行地址转换的结果是 。

- A. 段缺失异常
- B. 得到内存地址 4400
- C. 越权异常
- D. 越界异常

---

## 2016-Q29

> question_id: 2016-Q29
> exam_year: 2016
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: os
> kp_ids: [os.memory.virtual]
> answer_key: null
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: partial
> gap_status: partial
> gap_fields: [answer]

**题干**：某进程访问页面的序列如下所示。 若工作集的窗口大小为 6，则在 t 时刻的工作集为 。

- A. {6, 0, 3, 2}
- B. {2, 3, 0, 4}
- C. {0, 4, 3, 2, 9}
- D. {4, 5, 6, 0, 3, 2}

---

## 2016-Q30

> question_id: 2016-Q30
> exam_year: 2016
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: os
> kp_ids: [os.process.state]
> answer_key: null
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: partial
> gap_status: partial
> gap_fields: [answer]

**题干**：进程 P1 和 P2 均包含并发执行的线程，部分伪代码描述如下所示。 //进程P1 int x = 0; Thread1() { int a; a=1; x += 1; } Thread2() { int a; a=2; x += 2; } //进程P2 int x = 0; Thread3() { int a; a = x; x += 3; } Thread4() { int b b=x; x += 4; } 下列选项中，需要互斥执行的操作是 。

- A. a = 1 与 a = 2
- B. a = x 与 b = x
- C. x += 1 与 x += 2
- D. x +=1 与 x+=3

---

## 2016-Q31

> question_id: 2016-Q31
> exam_year: 2016
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: os
> kp_ids: [os.io.device]
> answer_key: null
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: partial
> gap_status: partial
> gap_fields: [answer]

**题干**：下列关于 SPOOLing 技术的叙述中，错误的是 。

- A. 需要外存的支持
- B. 需要多道程序设计技术的支持
- C. 可以让多个作业共享一台独占设备
- D. 由用户作业控制设备与输入/输出井之间的数据传送

---

## 2016-Q32

> question_id: 2016-Q32
> exam_year: 2016
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: os
> kp_ids: [os.process.state]
> answer_key: null
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: partial
> gap_status: partial
> gap_fields: [answer]

**题干**：下列关于管程的叙述中，错误的是

- A. 管程只能用于实现进程的互斥
- B. 管程是由编程语言支持的进程同步机制
- C. 任何时候只能有一个进程在管程中执行
- D. 管程中定义的变量只能被管程内的过程访问 题 33～41 均依据题 33～41 图回答。

---

## 2016-Q33

> question_id: 2016-Q33
> exam_year: 2016
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: cn
> kp_ids: [cn.arch.model]
> answer_key: C
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: complete
> gap_status: none
> gap_fields: []

**题干**：在 OSI 参考模型中，RI、Switch、Hub 实现的最高功能层分别是 。

- A. 2、2、1
- B. 2、2、2
- C. 3、2、1
- D. 3、2、2 --- page 5 --- 2016 年全国硕士研究生入学统一考试计算机科学与技术学科联考计算机学科专业基础综合试题 第 5 页（共 12 页）

---

## 2016-Q34

> question_id: 2016-Q34
> exam_year: 2016
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: co
> kp_ids: [co.bus.bandwidth]
> answer_key: null
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: partial
> gap_status: partial
> gap_fields: [answer]

**题干**：若连接和 R3 链路的频率带宽为 8kHz，信噪比为 30dB，该链路实际数据传输速率约为理论最大 数据传输速率的 50%。则该链路的实际数据传输速率约是 。

- A. 8kbps
- B. 20Kbps
- C. 40kbps
- D. 80kbps 题 33～41 图

---

## 2016-Q35

> question_id: 2016-Q35
> exam_year: 2016
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: cn
> kp_ids: [cn.datalink.ethernet]
> answer_key: null
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: partial
> gap_status: partial
> gap_fields: [answer]

**题干**：若主机 H2 向主机 H4 发送 1 个数据帧，主机 H4 向主机 H2 立即发送一个确认帧，则除 H4 外， 从物理层上能够收到该确认帧的主机还有 。

- A. 仅 H2
- B. 仅 H3
- C. 仅 H1、H2
- D. 仅 H2、H3

---

## 2016-Q36

> question_id: 2016-Q36
> exam_year: 2016
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: cn
> kp_ids: [cn.datalink.mac]
> answer_key: null
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: partial
> gap_status: partial
> gap_fields: [answer]

**题干**：若 Hub 再生比特流过程中，会产生 1.535μs 延时，信号传播速度为 200m/μs，不考虑以太网帧的 前导码，则 H3 与 H4 之间理论上可以相距的最远距离是 。

- A. 200m
- B. 205m
- C. 359m
- D. 512m

---

## 2016-Q37

> question_id: 2016-Q37
> exam_year: 2016
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: cn
> kp_ids: [cn.network.routing]
> answer_key: null
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: partial
> gap_status: partial
> gap_fields: [answer]

**题干**：假设 R1、R2、R3 采用 RIP 协议交换路由信息，且均己收敛。若 R3 检测到网络 201.1.2.0/25 不 可达，并向通告一次新的距离向量，则 R2 更新后，其到达该网络的距离是 。

- A. 2
- B. 3
- C. 16
- D. 17

---

## 2016-Q38

> question_id: 2016-Q38
> exam_year: 2016
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: co
> kp_ids: [co.cpu.pipeline]
> answer_key: null
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: partial
> gap_status: partial
> gap_fields: [answer]

**题干**：假设连接 R1、R2 和 R3 之间的点对点链路使用 201.1.3.x/30 地址，当 H3 访问 Web 服务器 S 时，R2 转发出去的封装 HTTP 请求报文的 IP 分组的源 IP 地址和目的 IP 地址分别是 。

- A. 192.168.3.251, 130.18.10.1
- B. 192.168.3.251, 201.1.3.9
- C. 201.1.3.8, 130.18.10.1
- D. 201.1.3.10, 130.18.10.1

---

## 2016-Q39

> question_id: 2016-Q39
> exam_year: 2016
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: cn
> kp_ids: [cn.network.ip_address]
> answer_key: null
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: partial
> gap_status: partial
> gap_fields: [answer]

**题干**：若 H1 与 H2 的默认网关和子网掩码均分别配置为 192.168.3.1 和 255.255.255.128，H3 和 H4 的默 认网关和子网掩码均分别配置为 192.168.3.254 和 255.255.255.128，则下列现象中可能发生的 是 。

- A. H1 不能与 H2 进行正常 IP 通信
- B. H2 与 H4 均不能访问 Internet
- C. H1 不能与 H3 进行正常 IP 通信
- D. H3 不能与 H4 进行正常 IP 通信

---

## 2016-Q40

> question_id: 2016-Q40
> exam_year: 2016
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: cn
> kp_ids: [cn.application.dns]
> answer_key: null
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: partial
> gap_status: partial
> gap_fields: [answer]

**题干**：假设所有域名服务器均采用迭代查询方式进行域名解析。当 H4 访问规范域名为 www.abc.xyz.com 的网站时，域名服务器 201.1.1.1 完成该域名解析过程中，可能发出 DNS 查询 的最少和最多次数分别是

- A. 0，3
- B. 1，3
- C. 0，4
- D. 1，4 --- page 6 --- 2016 年全国硕士研究生入学统一考试计算机科学与技术学科联考计算机学科专业基础综合试题 第 6 页（共 12 页）

---

