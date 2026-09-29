# 2023 年 408 真题 · items

> document_id: exam-2023-items
> exam_year: 2023
> kb_depth: exams
> doc_role: exam_item
> source_type: third_party
> credibility: high
> explanation_status: scan

答案只在 metadata（answer_key），正文不印答案。

## 2023-Q1

> question_id: 2023-Q1
> exam_year: 2023
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: ds
> kp_ids: [ds.search.seq]
> answer_key: D
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: complete
> gap_status: none
> gap_fields: []

**题干**：下列对顺序存储的有序表（长度为 n）实现给定操作的算法中，平均时间复杂度为 O(1)的 是 。

- A. 查找包含指定值元素的算法
- B. 插入包含指定值元素的算法
- C. 删除第 i（1≤i≤n）个元素的算法
- D. 获取第 i（1≤i≤n）个元素的算法

---

## 2023-Q2

> question_id: 2023-Q2
> exam_year: 2023
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

**题干**：现有非空双向链表 L，其结点结构为： prev data next ，prev 是指向直接前驱结点的指针， next 是指向直接后继结点的指针。若要在 L 中指针 p 所指向的结点（非尾结点）之后插入指针 s 指向的新结点，则在执行了语句序列： “s->next=p->next; p->next=s”后，下列语句序列中还需要 执行的是 。

- A. s->next->prev=p; s->prev=p;
- B. p->next->prev=s ; s->prev=p;
- C. s->prev=s->next->prev; s->next->prev=s;
- D. p->next->prev=s->prev ; s->next->prev=p;

---

## 2023-Q3

> question_id: 2023-Q3
> exam_year: 2023
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: ds
> kp_ids: [ds.array.compressed]
> answer_key: A
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: complete
> gap_status: none
> gap_fields: []

**题干**：若采用三元组表存储结构存储稀疏矩阵 M 。则除三元组表外，下列数据中还需要保存的 是 。 I. M 的行数 II. M 中包含非零元素的行数 III. M 的列数 IV . M 中包含非零元素的列数

- A. 仅 I、III
- B. 仅 I、IV
- C. 仅 II、IV
- D. I 、II、III、IV

---

## 2023-Q4

> question_id: 2023-Q4
> exam_year: 2023
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

**题干**：在由 6 个字符组成的字符集 S 中，各字符出现的频次分别为 3, 4, 5, 6, 8, 10，为 S 构造的哈夫曼 编码的加权平均长度为 。

- A. 2.4
- B. 2.5
- C. 2.67
- D. 2.75

---

## 2023-Q5

> question_id: 2023-Q5
> exam_year: 2023
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: ds
> kp_ids: [ds.tree.traversal]
> answer_key: A
> reference_answer: null
> has_figure: true
> figure_status: missing
> completeness: partial
> gap_status: partial
> gap_fields: [figure]

**题干**：已知一棵二叉树的树形如下图所示，若其后序遍历为 f, d, b, e, c, a，则其先 （前）序遍历序列是 。

- A. a, e, d, f, b, c
- B. a, c, e, b, d, f
- C. c, e, b, e, f, d
- D. d, f, e, b, a, c

---

## 2023-Q6

> question_id: 2023-Q6
> exam_year: 2023
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: ds
> kp_ids: [ds.graph.mst]
> answer_key: B
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: complete
> gap_status: none
> gap_fields: []

**题干**：已知无向连通图 G 中各边的权值均为 1，下列算法中，一定能够求出图 G 中 从某顶点到其余各顶点最短路径的是 。 I. 普里姆（Prim）算法 II. 克鲁斯卡尔（Kruskal）算法 III. 图的广度优先搜索算法

- A. 仅 I
- B. 仅 III
- C. 仅 I、II
- D. I 、II、III

---

## 2023-Q7

> question_id: 2023-Q7
> exam_year: 2023
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: ds
> kp_ids: [ds.search.b_tree]
> answer_key: B
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: complete
> gap_status: none
> gap_fields: []

**题干**：下列关于非空 B 树的叙述中，正确的是 。 I. 插入操作可能增加树的高度 II. 删除操作一定会导致叶结点的变化 III. 查找某关键字总是要查找到叶结点 IV . 插入的新关键字最终位于叶结点中

- A. 仅 I
- B. 仅 I、II
- C. 仅 III、IV
- D. 仅 I、II、IV

---

## 2023-Q8

> question_id: 2023-Q8
> exam_year: 2023
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

**题干**：对含有 600 个元素的有序顺序表进行折半查找，关键字间的比较次数最多是 。

- A. 9
- B. 10
- C. 30
- D. 300

---

## 2023-Q9

> question_id: 2023-Q9
> exam_year: 2023
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

**题干**：现有长度为 5、初始为空的散列表 HT，散列表函数 H(k)=(k+4)%5，用线性探查再散列法解决冲 突。若将关键字序列 2022, 12, 25 依次插入 HT 中，然后删除关键字 25，则 HT 中查找失败的平 均查找长度为 。

- A. 1
- B. 1.6
- C. 1.8
- D. 2.2

---

## 2023-Q10

> question_id: 2023-Q10
> exam_year: 2023
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: ds
> kp_ids: [ds.sort.quick_sort]
> answer_key: C
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: complete
> gap_status: none
> gap_fields: []

**题干**：下列排序算法中，不稳定的是 。 I. 希尔排序 II. 归并排序 III. 快速排序 IV . 堆排序 V . 基数排序

- A. I、II
- B. II 、V
- C. I 、III、IV
- D. III 、IV、V

---

## 2023-Q11

> question_id: 2023-Q11
> exam_year: 2023
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: ds
> kp_ids: [ds.sort.quick_sort]
> answer_key: D
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: complete
> gap_status: none
> gap_fields: []

**题干**：使用快速排序算法对数据进行升序排序，若经过一次划分后得到的数据序列是 68, 11, 70, 23, 80, --- page 2 --- 2023 年全国硕士研究生入学统一考试计算机学科专业基础综合试题 第 2 页（共 11 页） 77, 48, 81, 93, 88，则该次划分的枢轴是 。

- A. 11
- B. 70
- C. 80
- D. 81

---

## 2023-Q12

> question_id: 2023-Q12
> exam_year: 2023
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

**题干**：若机器 M 的主频为 1.5GHz，在 M 上执行程序 P 的指令条数为 5×10 5 ，P 的平均 CPI 为 1.2，则 P 在 M 上的指令执行速度和用户 CPU 时间分别为 。

- A. 0.8GIPS，0.4ms
- B. 0.8GIPS，0.4μs
- C. 1.25GIPS，0.4ms
- D. 1.25GIPS，0.4μs

---

## 2023-Q13

> question_id: 2023-Q13
> exam_year: 2023
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: co
> kp_ids: [co.representation.complement]
> answer_key: A
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: complete
> gap_status: none
> gap_fields: []

**题干**：若 short 型变量 x = -8 190，则 x 的机器数是 。

- A. E002H
- B. E 001H
- C. 9FFFH
- D. 9FFEH

---

## 2023-Q14

> question_id: 2023-Q14
> exam_year: 2023
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: co
> kp_ids: [co.representation.ieee754]
> answer_key: A
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: complete
> gap_status: none
> gap_fields: []

**题干**：已知 float 型变量用 IEEE 754 单精度浮点数格式表示。若 float 型变量 x 的机器数为 8020 0000H， 则 x 的值是 。

- A. –2–128
- B. – 1.01×2–127
- C. – 1.01×2–126
- D. 非数（NAN）

---

## 2023-Q15

> question_id: 2023-Q15
> exam_year: 2023
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: co
> kp_ids: [co.storage.main_memory]
> answer_key: C
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: complete
> gap_status: none
> gap_fields: []

**题干**：某计算机的 CPU 有 30 根地址线，按字节编址，CPU 和主存芯片连接时，要求主存芯片占满所有 可能存储地址空间，并且 RAM 区和 ROM 区所分配的空间大小比为 3:1。若 RAM 在连续低地址 区，ROM 在连续高地址区，则 ROM 的地址范围 。

- A. 0000 0000H～0FFF FFFFH
- B. 1000 0000H～2FFF FFFFH
- C. 3000 0000H～3FFF FFFFH
- D. 4000 0000H～4FFF FFFFH

---

## 2023-Q16

> question_id: 2023-Q16
> exam_year: 2023
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: co
> kp_ids: [co.representation.complement]
> answer_key: B
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: complete
> gap_status: none
> gap_fields: []

**题干**：己知 x、y 为 int 类型，当 x=100、y=200 时，执行“ x 减 y”指令得到的溢出标志 OF 和借位标志 CF 分别为 0、1，那么当 x=10，y=–20 时，执行该指令得到的 OF 和 CF 分别是 。

- A. OF=0，CF=0
- B. OF= 0，CF=1
- C. OF= 1，CF=0
- D. OF= 1，CF=1

---

## 2023-Q17

> question_id: 2023-Q17
> exam_year: 2023
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: co
> kp_ids: [co.cpu.datapath]
> answer_key: A
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: complete
> gap_status: none
> gap_fields: []

**题干**：某运算类型指令中有一个地址码为通用寄存器编号，对应通用寄存器中存放的是操作数或操作数 的地址，CPU 区分两者的依据是 。

- A. 操作数的寻址方式
- B. 操作数的编码方式
- C. 通用寄存器的编号
- D. 通用寄存器的内容

---

## 2023-Q18

> question_id: 2023-Q18
> exam_year: 2023
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: co
> kp_ids: [co.cpu.datapath]
> answer_key: B
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: complete
> gap_status: none
> gap_fields: []

**题干**：数据通路由组合逻辑元件（操作元件）和时序逻辑元件组成（状态元件）组成，以下给出的元件 中，属于操作元件的是 。 I. 算术逻辑部件（ALU） II. 程序计数器（PC） III. 通用寄存器组（GPRs） IV . 多路选择器（MUX）

- A. 仅 I、II
- B. 仅 I、IV
- C. 仅 II、III
- D. 仅 I、II、IV

---

## 2023-Q19

> question_id: 2023-Q19
> exam_year: 2023
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

**题干**：某系统采用“取指、译码/取数、执行、访存、写回”5 段流水线，RISC 处理器中执行如下指令序 列（第一列为指令序号） ，其中s0、s1、s2、s3、t2 表示寄存器编号。 I1 add s2, s1, s0 //R[s2]←R[s1]+R[s0] I2 load s3, 0(s2) //R[s3]←M[R[s2]+0] I3 beq t2, s3, L1 //if R[t2]=R[s3] jump to L1 I4 addi t2, t2, 20 //R[t2]←R[t2] + 20 I5 L1:... 若采用转发（旁路）技术处理数据冒险，采用硬件阻塞方式处理控制冒险，则在 I1~I4 执行过程 中，发生流水线阻塞的指令有 。

- A. 仅 I3
- B. 仅 I2、I4
- C. 仅 I3、I4
- D. I 2、I3、I4

---

## 2023-Q20

> question_id: 2023-Q20
> exam_year: 2023
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: co
> kp_ids: [co.bus.bandwidth]
> answer_key: D
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: complete
> gap_status: none
> gap_fields: []

**题干**：某存储总线宽度为 64b， 总线时钟频率为 1GHz， 在总线上传输一个数据或地址需要一个时钟周期， 不支持突发传送方式。若通过该总线连接 CPU 和主存，主存每次准备一个 64b 数据需要 6ns，主 存块大小为 32B，则读取一个主存块需要的时间是 。

- A. 8ns
- B. 11ns
- C. 26ns
- D. 32ns

---

## 2023-Q21

> question_id: 2023-Q21
> exam_year: 2023
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: co
> kp_ids: [co.cpu.exception]
> answer_key: D
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: complete
> gap_status: none
> gap_fields: []

**题干**：下列关于硬件和异常/中断关系的叙述中，错误的是（ ） 。

- A. CPU 在执行一条指令过程中检测异常事件
- B. CPU 在执行完一条指令时检测中断请求信号
- C. 开中断时 CPU 检测到中断请求后就进行中断响应
- D. 外部设备通过中断控制器向 CPU 发中断结束信号

---

## 2023-Q22

> question_id: 2023-Q22
> exam_year: 2023
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

**题干**：下列关于 I/O 控制方式的叙述中，错误的是 。

- A. 查询方式下，通过 CPU 执行查询程序进行 I/O 操作 --- page 3 --- 2023 年全国硕士研究生入学统一考试计算机学科专业基础综合试题 第 3 页（共 11 页）
- B. 中断方式下，通过 CPU 执行中断服务程序进行 I/O 操作
- C. DMA 方式下，通过 CPU 执行 DMA 传送程序进行 I/O 操作
- D. 对于 SSD、网络适配器等高速设备，采用 DMA 方式输入/输出

---

## 2023-Q23

> question_id: 2023-Q23
> exam_year: 2023
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

**题干**：与宏内核操作系统相比，下列特征中，微内核操作系统具有的是 。 I. 较好的性能 II. 较高的可靠性 III. 较高的安全性 IV . 较强的可扩展性

- A. 仅 II、IV
- B. 仅 I、II、III
- C. 仅 I、III、IV
- D. 仅 II、III、IV

---

## 2023-Q24

> question_id: 2023-Q24
> exam_year: 2023
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: ds
> kp_ids: [ds.linear.linked_list]
> answer_key: A
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: complete
> gap_status: none
> gap_fields: []

**题干**：在操作系统内核中，中断向量表适合采用的数据结构是 。

- A. 数组
- B. 队列
- C. 单向链表
- D. 双向链表

---

## 2023-Q25

> question_id: 2023-Q25
> exam_year: 2023
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: os
> kp_ids: [os.memory.allocate]
> answer_key: C
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: complete
> gap_status: none
> gap_fields: []

**题干**：某系统采用页式存储管理， 用位图管理空闲页框。 若页大小为 4KB， 物理内存大小为 16GB， 则位 图所占空间的大小是 。

- A. 128B
- B. 128KB
- C. 512KB
- D. 4MB

---

## 2023-Q26

> question_id: 2023-Q26
> exam_year: 2023
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: os
> kp_ids: [os.process.state]
> answer_key: D
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: complete
> gap_status: none
> gap_fields: []

**题干**：下列操作完成时，导致 CPU 从内核态转为用户态的是 。

- A. 阻塞进程
- B. 执行 CPU 调度
- C. 唤醒进程
- D. 执行系统调用

---

## 2023-Q27

> question_id: 2023-Q27
> exam_year: 2023
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

**题干**：下 列 由 当 前 线 程 引 起 的 事 件 或 执 行 的 操 作 中 ， 可 能 导 致 该 线 程 由 执 行 形 态 变 为 就 绪 态 的 是 。

- A. 键盘输入
- B. 缺页异常
- C. 主动出让 CPU
- D. 执行信号量的 wait()操作

---

## 2023-Q28

> question_id: 2023-Q28
> exam_year: 2023
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

**题干**：对于采用虚拟内存管理方式的系统，下列关于进程虚拟地址空间的叙述中，错误的是 。

- A. 每个进程都有自已独立的虚拟地址空间
- B. C 语言中 malloc()函数返回的是虚拟地址
- C. 进程对数据段和代码段可以有不同的访问权限
- D. 虚拟地址空间的大小由内存和硬盘的大小决定

---

## 2023-Q29

> question_id: 2023-Q29
> exam_year: 2023
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: ds
> kp_ids: [ds.stack_queue.queue]
> answer_key: B
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: complete
> gap_status: none
> gap_fields: []

**题干**：进程 P1、P2 和 P3 进入就绪队列的时刻， 优先级 （值越大优先权越高） 以及CPU 的执行时间如下 表所示： 进程名 进入就绪队列的时刻 优先数 CPU 执行时间 P1 0ms 1 60ms P2 20ms 10 42ms P3 30ms 100 13ms 若系统采用基于优先权的抢占式 CPU 调度算法，从 0ms 时刻开始进行调度，则 P1、P2 和 P3 的平均周转时间为 。

- A. 60ms
- B. 61ms
- C. 70ms
- D. 71ms

---

## 2023-Q30

> question_id: 2023-Q30
> exam_year: 2023
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: os
> kp_ids: [os.memory.paging]
> answer_key: C
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: complete
> gap_status: none
> gap_fields: []

**题干**：进程 R 和 S 共享数据 data，若 data 在 R 和 S 中所在页的页号分别为 p1 和 p2，两个页所对应的页 框号分别为 f1 和 f2，则下列叙述中，正确的是 。

- A. p1 和 p2 一定相等，f1 和 f2 一定相等
- B. p 1 和 p2 一定相等，f1 和 f2 不一定相等
- C. p1 和 p2 不一定相等，f1 和 f2 一定相等
- D. p 1 和 p2 不一定相等，f1 和 f2 不一定相等

---

## 2023-Q31

> question_id: 2023-Q31
> exam_year: 2023
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: os
> kp_ids: [os.file.dir]
> answer_key: B
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: complete
> gap_status: none
> gap_fields: []

**题干**：若文件 F 仅被进程 P 打开并访问，则当进程 P 关闭 F 时，下列操作中，文件系统需要完成的 是 。

- A. 删除目录文件中 F 的目录项
- B. 释放 F 的索引节点所占的内存空间
- C. 释放 F 的索引节点所占的外存空间
- D. 将文件磁盘索引结点中的链接计数减 1

---

## 2023-Q32

> question_id: 2023-Q32
> exam_year: 2023
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: os
> kp_ids: [os.io.device]
> answer_key: D
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: complete
> gap_status: none
> gap_fields: []

**题干**：下列因素中，设备分配需要考虑的是 。 I.设备的类型 II. 设备的访问权限 III.设备的占用状态 IV . 逻辑设备与物理设备的映射关系

- A. 仅 I、II
- B. 仅 II、III
- C. 仅 III、IV
- D. I 、II、III、IV

---

## 2023-Q33

> question_id: 2023-Q33
> exam_year: 2023
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: co
> kp_ids: [co.bus.bandwidth]
> answer_key: D
> reference_answer: null
> has_figure: true
> figure_status: missing
> completeness: partial
> gap_status: partial
> gap_fields: [figure]

**题干**：在下图所示的分组交换网络中，主机 H1 和 H2 通过路由器互连，2 段链路的带宽均为 100 Mb/s、 时延带宽积（即单向传播时延×宽带）均为 1000b。若 H1 向 H2 发送 1 个大小为 1 MB 的文件， 分组长度为 1000B， 则从H1 开始发送时刻起到 H2 收到文件全部数据时刻止， 所需的时间至少是 （注：M=10 6 ） 。 --- page 4 --- 2023 年全国硕士研究生入学统一考试计算机学科专业基础综合试题 第 4 页（共 11 页）

- A. 80.02ms
- B. 80.08ms
- C. 80.09ms
- D. 80.10ms

---

## 2023-Q34

> question_id: 2023-Q34
> exam_year: 2023
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: co
> kp_ids: [co.bus.bandwidth]
> answer_key: C
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: complete
> gap_status: none
> gap_fields: []

**题干**：某无噪声理想信道带宽为 4MHz，采用 QAM 调制，若该信道的最大数据传输速率是 48Mb/s，则 该信道采用的 QAM 调制方案是 。

- A. QAM–16
- B. QAM– 32
- C. QAM– 64
- D. QAM– 128

---

## 2023-Q35

> question_id: 2023-Q35
> exam_year: 2023
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: cn
> kp_ids: [cn.datalink.flow_control]
> answer_key: B
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: complete
> gap_status: none
> gap_fields: []

**题干**：假设通过同一信道，数据链路层分别采用停止–等待协议、GBN 协议和 SR 协议（发送窗口和接 收窗口相等） 传输数据， 3 个协议数据帧长相同， 忽略确认帧长度， 帧序号位数为 3 比特。 若对应 3 个协议的发送方最大信道利用率分别是 U1、U2 和 U3， 则U1、U2 和 U3 满足的关系是 。

- A. U1≤U2≤U3
- B. U 1≤U3≤U2
- C. U 2≤U3≤U1
- D. U 3≤U2≤U1

---

## 2023-Q36

> question_id: 2023-Q36
> exam_year: 2023
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

**题干**：已知 10BaseT 以太网的争用时间片为 51.2μs。若网卡在发送某帧时发生了连续 4 次冲突，则基于 二进制指数退避算法确定的再次尝试重发该帧前等待的最长时间是 。

- A. 51.2μs
- B. 204.8μs
- C. 768μs
- D. 819.2μs

---

## 2023-Q37

> question_id: 2023-Q37
> exam_year: 2023
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: cn
> kp_ids: [cn.datalink.error_control]
> answer_key: D
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: complete
> gap_status: none
> gap_fields: []

**题干**：若甲向乙发送数据时采用 CRC 校验， 生成多项式为G(X)=X 4 +X+1(即 G=10011)， 则乙接收到下列 比特串时，可以断定其在传输过程中未发生错误的是 。

- A. 1 0111 0000
- B. 1 0111 0100
- C. 1 0111 1000
- D. 1 0111 1100

---

## 2023-Q38

> question_id: 2023-Q38
> exam_year: 2023
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: ds
> kp_ids: [ds.graph.topo]
> answer_key: A
> reference_answer: null
> has_figure: true
> figure_status: missing
> completeness: partial
> gap_status: partial
> gap_fields: [figure]

**题干**：某网络拓扑如下图所示，其中路出器 R2 实现 NAT 功能。若主机 H 向 Internet 发送 1 个 IP 分组， 则经过 R2 转发后，该 IP 分组的源 IP 地址是 。

- A. 195.123.0.33
- B. 192.123.0.35
- C. 192.168.0.1
- D. 192.168.0.3

---

## 2023-Q39

> question_id: 2023-Q39
> exam_year: 2023
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: cn
> kp_ids: [cn.network.ip_address]
> answer_key: B
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: complete
> gap_status: none
> gap_fields: []

**题干**：主机 168.16.84.24/20 所在子网的最小可分配 IP 地址和最大可分配 IP 地址分别是 。

- A. 168.16.80.1, 168.16.84.254
- B. 168.16.80.1, 168.16.95.254
- C. 168.16.84.1, 168.16.84.254
- D. 168.16.84.1, 168.16.95.254

---

## 2023-Q40

> question_id: 2023-Q40
> exam_year: 2023
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: ds
> kp_ids: [ds.stack_queue.stack]
> answer_key: D
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: complete
> gap_status: none
> gap_fields: []

**题干**：下列关于 IPv4 和 IPv6 的叙述中，正确的是（ ） 。 I. IPv6 地址空间是 IPv4 地址空间的 96 倍 II. IPv4 首部和 IPv6 的基本首部的长度均可变 III. IPv4 向 IPv6 过渡可以采用双协议栈和隧道技术 IV . IPv6 首部的 Hop Limit 等价于 IPv4 首部的 TTL 字段

- A. 仅 I、II
- B. 仅 I、IV
- C. 仅 II、III
- D. 仅 III、IV --- page 5 --- 2023 年全国硕士研究生入学统一考试计算机学科专业基础综合试题 第 5 页（共 11 页）

---

