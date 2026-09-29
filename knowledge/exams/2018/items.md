# 2018 年 408 真题 · items

> document_id: exam-2018-items
> exam_year: 2018
> kb_depth: exams
> doc_role: exam_item
> source_type: third_party
> credibility: high
> explanation_status: scan

答案只在 metadata（answer_key），正文不印答案。

## 2018-Q1

> question_id: 2018-Q1
> exam_year: 2018
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

**题干**：若栈 S1中保存整数，栈 S2中保存运算符，函数 F()依次执行下述各步操作： （1）从 S1中依次弹出两个操作数 a和 b； （2）从 S2中弹出一个运算符 op： （3）执行相应的运算 b op a; （4）将运算结果压入 S1中。 假定 S1中的操作数依次是 5, 8, 3, 2（2 在栈顶） ，S2 中的运算符依次是*, –, +（+在栈顶） 。调用 3 次 F()后，S1栈顶保存的值是 。

- A. －15
- B. 15
- C. －20
- D. 20

---

## 2018-Q2

> question_id: 2018-Q2
> exam_year: 2018
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
> has_figure: false
> figure_status: null
> completeness: partial
> gap_status: partial
> gap_fields: [answer]

**题干**：现有队列 Q与栈 S，初始时 Q中的元素依次是 1, 2, 3, 4, 5, 6（1 在队头） ，S 为空。若仅允许下列 3 种操作：①出队并输出出队元素：②出队并将出队元素入栈：③出栈并输出出栈元素，则不能得 到的输出序列是 。

- A. 1, 2, 5, 6, 4, 3
- B. 2, 3, 4, 5, 6, 1
- C. 3, 4, 5, 6, 1, 2
- D. 6, 5, 4, 3, 2, 1

---

## 2018-Q3

> question_id: 2018-Q3
> exam_year: 2018
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

**题干**：设有一个 12×12 的对称矩阵M，将其上三角部分的元素 mi, j （1≤i≤j≤12）按行优先存入 C 语言 的一维数组 N中，元素 m6, 6在 N中的下标是 。

- A. 50
- B. 51
- C. 55
- D. 66

---

## 2018-Q4

> question_id: 2018-Q4
> exam_year: 2018
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: ds
> kp_ids: [ds.tree.complete, ds.tree.binary_tree]
> answer_key: A
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: complete
> gap_status: none
> gap_fields: []

**题干**：设一棵非空完全二叉树 T的所有叶结点均位于同一层，且每个非叶结点都有 2 个子结点。若T有 k个叶结点，则 T的结点总数是 。

- A. 2k – 1
- B. 2k
- C. k 2
- D. 2k – 1

---

## 2018-Q5

> question_id: 2018-Q5
> exam_year: 2018
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: ds
> kp_ids: [ds.tree.huffman]
> answer_key: A
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: complete
> gap_status: none
> gap_fields: []

**题干**：已知字符集{a, b, c, d, e, f}，若各字符出现的次数分别为 6, 3, 8, 2, 10, 4，则对应字符集中各字符的 哈夫曼编码可能是 。

- A. 00, 1011, 01, 1010, 11, 100
- B. 00, 100, 110, 000, 0010, 01
- C. 10, 1011, 11, 0011, 00, 010
- D. 0011, 10, 11, 0010, 01, 000

---

## 2018-Q6

> question_id: 2018-Q6
> exam_year: 2018
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: ds
> kp_ids: [ds.tree.bst]
> answer_key: null
> reference_answer: null
> has_figure: true
> figure_status: missing
> completeness: partial
> gap_status: partial
> gap_fields: [answer, figure]

**题干**：己知二叉排序树如下图所示，元素之间应满足的大小关系是 。

- A. x1 < x2 < x5
- B. x1 < x4 < x5
- C. x3 < x5 < x4
- D. x4 < x3 < x5

---

## 2018-Q7

> question_id: 2018-Q7
> exam_year: 2018
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

**题干**：下列选项中，不是如下有向图的拓扑序列的是 。

- A. 1, 5, 2, 3, 6, 4
- B. 5, 1, 2, 6, 3, 4
- C. 5, 1, 2, 3, 6, 4
- D. 5, 2, 1, 6, 3, 4 --- page 2 --- 2018 年全国硕士研究生入学统一考试计算机科学与技术学科联考计算机学科专业基础综合试题 第 2 页（共 11 页）

---

## 2018-Q8

> question_id: 2018-Q8
> exam_year: 2018
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

**题干**：高度为 5 的 3 阶B 树含有的关键字个数至少是 。

- A. 15
- B. 31
- C. 62
- D. 242

---

## 2018-Q9

> question_id: 2018-Q9
> exam_year: 2018
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: ds
> kp_ids: [ds.search.hash]
> answer_key: B
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: complete
> gap_status: none
> gap_fields: []

**题干**：现有长度为 7、初始为空的散列表HT，散列函数：H(k) = k % 7，用线性探测再散列法解决冲 突。将关键字 22, 43, 15 依次插入到HT后，查找成功的平均查找长度是 。

- A. 1.5
- B. 1.6
- C. 2
- D. 3

---

## 2018-Q10

> question_id: 2018-Q10
> exam_year: 2018
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: ds
> kp_ids: [ds.sort.shell]
> answer_key: D
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: complete
> gap_status: none
> gap_fields: []

**题干**：对初始数据序列（8, 3, 9, 11, 2, 1, 4, 7, 5, 10, 6）进行希尔排序。若第一趟排序结果为（1, 3, 7, 5, 2, 6, 4, 9, 11, 10, 8） ，第二趟排序结果为（1, 2, 6, 4, 3, 7, 5, 8, 11, 10, 9） ，则两趟排序采用的增量 （间隔）依次是 。

- A. 3, 1
- B. 3, 2
- C. 5, 2
- D. 5, 3

---

## 2018-Q11

> question_id: 2018-Q11
> exam_year: 2018
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: ds
> kp_ids: [ds.sort.heap]
> answer_key: null
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: partial
> gap_status: partial
> gap_fields: [answer]

**题干**：在将数据序列(6, 1, 5, 9, 8, 4, 7)建成大根堆时，正确的序列变化过程是 。

- A. 6, 1, 7, 9, 8, 4, 5→6, 9, 7, 1, 8, 4, 5→9, 6, 7, 1, 8, 4, 5→9, 8, 7, 1, 6, 4, 5
- B. 6, 9, 5, 1, 8, 4, 7→6, 9, 7, 1, 8, 4, 5→9, 6, 7, 1, 8, 4, 5→9, 8, 7, 1, 6, 4, 5
- C. 6, 9, 5, 1, 8, 4, 7→9, 6, 5, 1, 8, 4, 7→9, 6, 7, 1, 8, 4, 5→9, 8, 7, 1, 6, 4, 5
- D. 6, 1, 7, 9, 8, 4, 5→7, 1, 6, 9, 8, 4, 5→7, 9, 6, 1, 8, 4, 5→9, 7, 6, 1, 8, 4, 5→9, 8, 6, 1, 7, 4, 5

---

## 2018-Q12

> question_id: 2018-Q12
> exam_year: 2018
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: co
> kp_ids: [co.overview.von_neumann]
> answer_key: null
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: partial
> gap_status: partial
> gap_fields: [answer]

**题干**：冯·诺依曼结构计算机中数据采用二进制编码表示，其主要原因是 。 I. 二进制的运算规则简单 II. 制造两个稳态的物理器件较容易 III. 便于用逻辑门电路实现算术运算

- A. 仅 I、II
- B. 仅 I、III
- C. 仅 II、III
- D. I 、II和 III

---

## 2018-Q13

> question_id: 2018-Q13
> exam_year: 2018
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: co
> kp_ids: [co.representation.complement]
> answer_key: null
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: partial
> gap_status: partial
> gap_fields: [answer]

**题干**：假定带符号整数采用补码表示，若 int 型变量 x和 y的机器数分别是 FFFF FFDFH 和 0000 0041H，则 x、y的值以及 x – y的机器数分别是 。

- A. x = －65, y = 41, x – y 的机器数溢出
- B. x = －33, y = 65, x – y 的机器数为 FFFF FF9DH
- C. x = －33, y = 65, x – y 的机器数为 FFFF FF9EH
- D. x = －65, y = 41, x – y 的机器数为 FFFF FF96H

---

## 2018-Q14

> question_id: 2018-Q14
> exam_year: 2018
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: co
> kp_ids: [co.representation.ieee754]
> answer_key: C
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: complete
> gap_status: none
> gap_fields: []

**题干**：IEEE 754 单精度浮点格式表示的数中，最小的规格化正数是 。

- A. 1.0×2-126
- B. 1.0×2-127
- C. 1.0×2-128
- D. 1.0×2-149

---

## 2018-Q15

> question_id: 2018-Q15
> exam_year: 2018
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

**题干**：某 32 位计算机按字节编址，采用小端（Little Endian）方式。若语句“int i = 0; ”对应指令的机 器代码为“C7 45 FC 00 00 00 00” ，则语句“int i = －64; ”对应指令的机器代码是 。

- A. C7 45 FC C0 FF FF FF
- B. C 7 45 FC 0C FF FF FF
- C. C7 45 FC FF FF FF C0
- D. C 7 45 FC FF FF FF 0C

---

## 2018-Q16

> question_id: 2018-Q16
> exam_year: 2018
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: co
> kp_ids: [co.representation.integer_op]
> answer_key: null
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: partial
> gap_status: partial
> gap_fields: [answer]

**题干**：整数 x的机器数为 1101 1000，分别对 x进行逻辑右移 1 位和算术右移 1 位操作，得到的机器数 分别是 。

- A. 1110 1100，1110 1100
- B. 0110 1100，1110 1100
- C. 1110 1100，0110 1100
- D. 0110 1100，0110 1100

---

## 2018-Q17

> question_id: 2018-Q17
> exam_year: 2018
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

**题干**：假定 DRAM 芯片中存储阵列的行数为 r、列数为 c，对于一个 2K×1 位的DRAM 芯片，为保证 其地址引脚数最少，并尽量减少刷新开销，则 r、c的取值分别是 。

- A. 2048、1
- B. 64、32
- C. 32、64
- D. 1、2048

---

## 2018-Q18

> question_id: 2018-Q18
> exam_year: 2018
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

**题干**：按字节编址的计算机中，某 double型数组 A的首地址为 2000H，使用变址寻址和循环结构访问 数组 A，保存数组下标的变址寄存器初值为 0，每次循环取一个数组元素，其偏移地址为变址值 乘以 sizeof(double)，取完后变址寄存器内容自动加 1。若某次循环所取元素的地址为 2100H，则 进入该次循环时变址寄存器的内容是 。

- A. 25
- B. 32
- C. 64
- D. 100

---

## 2018-Q19

> question_id: 2018-Q19
> exam_year: 2018
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

**题干**：减法指令“sub R1, R2, R3”的功能为“(R1) – (R2)→R3”,该指令执行后将生成进位/借位标志 CF 和溢出标志 OF。若(R1)=FFFF FFFFH，(R2)=FFFF FFF0H，则该减法指令执行后，CF 与 OF 分 别为 。

- A. CF = 0, OF = 0
- B. CF= 1，OF = 0
- C. CF = 0，OF = 1
- D. CF = 1，OF = 1

---

## 2018-Q20

> question_id: 2018-Q20
> exam_year: 2018
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: co
> kp_ids: [co.cpu.pipeline]
> answer_key: D
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: complete
> gap_status: none
> gap_fields: []

**题干**：若某计算机最复杂指令的执行需要完成 5 个子功能，分别由功能部件A～E实现，各功能部件所 --- page 3 --- 2018 年全国硕士研究生入学统一考试计算机科学与技术学科联考计算机学科专业基础综合试题 第 3 页（共 11 页） 需时间分别为 80ps、50ps、50ps、70ps 和 50ps,采用流水线方式执行指令，流水段寄存器延时为 20ps，则 CPU 时钟周期至少为 。

- A. 60ps
- B. 70ps
- C. 80ps
- D. 100ps

---

## 2018-Q21

> question_id: 2018-Q21
> exam_year: 2018
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

**题干**：下列选项中，可提高同步总线数据传输率的是 。 I. 增加总线宽度 II. 提高总线工作频率 III. 支持突发传输 IV . 采用地址/数据线复用

- A. 仅 I、II
- B. 仅 I、II、III
- C. 仅 III、IV
- D. I 、II、III 和 IV

---

## 2018-Q22

> question_id: 2018-Q22
> exam_year: 2018
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

**题干**：下列关于外部 I/O中断的叙述中，正确的是 。

- A. 中断控制器按所接收中断请求的先后次序进行中断优先级排队
- B. CPU 响应中断时，通过执行中断隐指令完成通用寄存器的保护
- C. CPU 只有在处于中断允许状态时，才能响应外部设备的中断请求
- D. 有中断请求时，CPU 立即暂停当前指令执行，转去执行中断服务程序

---

## 2018-Q23

> question_id: 2018-Q23
> exam_year: 2018
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: os
> kp_ids: [os.overview.feature]
> answer_key: C
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: complete
> gap_status: none
> gap_fields: []

**题干**：下列关于多任务操作系统的叙述，正确的是 。 I. 具有并发和并行的特点 II. 需要实现对共享资源的保护 III. 需要运行在多 CPU 的硬件平台上

- A. 仅 I
- B. 仅 II
- C. 仅 I、II
- D. I 、II、III

---

## 2018-Q24

> question_id: 2018-Q24
> exam_year: 2018
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: ds
> kp_ids: [ds.stack_queue.queue]
> answer_key: D
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: complete
> gap_status: none
> gap_fields: []

**题干**：某系统采用基于优先权的非抢占式进程调度策略，完成一次进程调度和进程切换的系统时间开销 为 1μs。在 T时刻就绪队列中有 3 个进程P1、P2和 P3，其在就绪队列中的等待时间、需要的 CPU 时间和优先权如下表所示。 进程 等待时间 需要的 CPU 时间 优先权 P1 30μs 12μs 10 P2 15μs 24μs 30 P3 18μs 36μs 20 若优先权值大的进程优先获得 CPU，从 T时刻起系统开始进程调度，系统的平均周转时间 为 。

- A. 54μs
- B. 73μs
- C. 74μs
- D. 75μs

---

## 2018-Q25

> question_id: 2018-Q25
> exam_year: 2018
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: os
> kp_ids: [os.process.state]
> answer_key: B
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: complete
> gap_status: none
> gap_fields: []

**题干**：属于同一进程的两个线程 thread1 和thread2 并发执行，共享初值为 0 的全局变量x。thread1 和 thread2 实现对全局变量x加 1 的机器级代码描述如下。 thread1 thread 2 mov R1, x //(x) → R 1 inc R1 //(R 1) + 1 → R 1 mov x, R1 //(R 1) → x mov R2, x //(x) → R 2 inc R2 //(R 2) + 1 → R 2 mov x, R2 //(R 2) → x 在所有可能的指令执行序列中，使 x的值为 2 的序列个数是 。

- A. 1
- B. 2
- C. 3
- D. 4

---

## 2018-Q26

> question_id: 2018-Q26
> exam_year: 2018
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

**题干**：假设系统中有 4 个同类资源，进程P1, P2和 P3需要的资源数分别为 4, 3 和 1，P1, P2和 P3已申请到 的资源数分别为 2, 1 和 0，则执行安全性检测算法的结果是 。

- A. 不存在安全序列，系统处于不安全状态
- B. 存在多个安全序列，系统处于安全状态
- C. 存在唯一安全序列 P3, P1, P2，系统处于安全状态
- D. 存在唯一安全序列 P3, P2, P1，系统处于安全状态

---

## 2018-Q27

> question_id: 2018-Q27
> exam_year: 2018
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: os
> kp_ids: [os.process.state]
> answer_key: C
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: complete
> gap_status: none
> gap_fields: []

**题干**：下列选项中，可能导致当前进程 P 阻塞的事件是 。 I. 进程 P 申请临界资源 II. 进程 P 从磁盘读数据 III. 系统将 CPU 分配给高优先权的进程

- A. 仅 I
- B. 仅 II
- C. 仅 I、II
- D. I 、II、III

---

## 2018-Q28

> question_id: 2018-Q28
> exam_year: 2018
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: ds
> kp_ids: [ds.stack_queue.queue]
> answer_key: null
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: partial
> gap_status: partial
> gap_fields: [answer]

**题干**：若 x是管程内的条件变量，则当进程执行 x.wait()时所做的工作是 。

- A. 实现对变量 x的互斥访问
- B. 唤醒一个在 x上阻塞的进程 --- page 4 --- 2018 年全国硕士研究生入学统一考试计算机科学与技术学科联考计算机学科专业基础综合试题 第 4 页（共 11 页）
- C. 根据 x的值判断该进程是否进入阻塞状态
- D. 阻塞该进程，并将之插入 x的阻塞队列中

---

## 2018-Q29

> question_id: 2018-Q29
> exam_year: 2018
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

**题干**：当定时器产生时钟中断后，由时钟中断服务程序更新的部分内容是 。 I. 内核中时钟变量的值 II. 当前进程占用 CPU 的时间 III. 当前进程在时间片内的剩余执行时间

- A. 仅 I、II
- B. 仅 II、III
- C. 仅 I、III
- D. I、II、III

---

## 2018-Q30

> question_id: 2018-Q30
> exam_year: 2018
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: os
> kp_ids: [os.process.schedule]
> answer_key: A
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: complete
> gap_status: none
> gap_fields: []

**题干**：系统总是访问磁盘的某个磁道而不响应对其他磁道的访问请求，这种现象称为磁臂黏着。下列磁 盘调度算法中，不会导致磁臂黏着的是 。

- A. 先来先服务（FCFS）
- B. 最短寻道时间优先（SSTF）
- C. 扫描算法（SCAN）
- D. 循环扫描算法（CSCAN）

---

## 2018-Q31

> question_id: 2018-Q31
> exam_year: 2018
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: co
> kp_ids: [co.storage.cache]
> answer_key: D
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: complete
> gap_status: none
> gap_fields: []

**题干**：下列优化方法中，可以提高文件访问速度的是 。 I. 提前读 II. 为文件分配连续的簇 III. 延迟写 IV . 采用磁盘高速缓存

- A. 仅 I、II
- B. 仅 II、III
- C. 仅 I、III、IV
- D. I、II、III、IV

---

## 2018-Q32

> question_id: 2018-Q32
> exam_year: 2018
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: os
> kp_ids: [os.process.sync]
> answer_key: null
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: partial
> gap_status: partial
> gap_fields: [answer]

**题干**：下列同步机制中，可以实现让权等待的是 。

- A. Peterson方法
- B. swap指令
- C. 信号量方法
- D. TestAndSet指令

---

## 2018-Q33

> question_id: 2018-Q33
> exam_year: 2018
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: cn
> kp_ids: [cn.transport.tcp]
> answer_key: null
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: partial
> gap_status: partial
> gap_fields: [answer]

**题干**：下列 TCP/IP 应用层协议中，可以使用传输层无连接服务的是 。

- A. FTP
- B. DNS
- C. SMTP
- D. HTTP

---

## 2018-Q34

> question_id: 2018-Q34
> exam_year: 2018
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: cn
> kp_ids: [cn.physical.channel]
> answer_key: null
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: partial
> gap_status: partial
> gap_fields: [answer]

**题干**：下列选项中，不属于物理层接口规范定义范畴的是 。

- A. 接口形状
- B. 引脚功能
- C. 物理地址
- D. 信号电平

---

## 2018-Q35

> question_id: 2018-Q35
> exam_year: 2018
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: cn
> kp_ids: [cn.datalink.mac]
> answer_key: D
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: complete
> gap_status: none
> gap_fields: []

**题干**：IEEE 802.11 无线局域网的MAC 协议 CSMA/CA 进行信道预约的方法是 。

- A. 发送确认帧
- B. 采用二进制指数退避
- C. 使用多个 MAC 地址
- D. 交换 RTS与 CTS 帧

---

## 2018-Q36

> question_id: 2018-Q36
> exam_year: 2018
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: cn
> kp_ids: [cn.datalink.flow_control]
> answer_key: D
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: complete
> gap_status: none
> gap_fields: []

**题干**：主机甲采用停–等协议向主机乙发送数据，数据传输速率是 3kbps,单向传播延时是 200ms，忽略 确认帧的传输延时。当信道利用率等于 40%时，数据帧的长度为 。

- A. 240 比特
- B. 400 比特
- C. 480 比特
- D. 800 比特

---

## 2018-Q37

> question_id: 2018-Q37
> exam_year: 2018
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: cn
> kp_ids: [cn.datalink.mac]
> answer_key: D
> reference_answer: null
> has_figure: true
> figure_status: missing
> completeness: partial
> gap_status: partial
> gap_fields: [figure]

**题干**：路由器 R 通过以太网交换机 S1 和S2 连接两个网络，R 的接口、主机 H1 和H2 的IP 地址与 MAC 地址如下图所示。若 H1 向H2 发送 1 个IP 分组 P，则 H1 发出的封装P 的以太网帧的目的 MAC 地址、H2 收到的封装P 的以太网帧的源 MAC 地址分别是 。

- A. 00-a1-b2-c3-d4-62, 00-1a-2b-3c-4d-52
- B. 00-a1-b2-c3-d4-62, 00-a1-b2-c3-d4-61
- C. 00-1a-2b-3c-4d-51, 00-1a-2b-3c-4d-52
- D. 00-1a-2b-3c-4d-51, 00-a1-b2-c3-d4-61

---

## 2018-Q39

> question_id: 2018-Q39
> exam_year: 2018
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: cn
> kp_ids: [cn.transport.udp]
> answer_key: B
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: complete
> gap_status: none
> gap_fields: []

**题干**：UDP协议实现分用（demultiplexing）时所依据的头部字段是 。

- A. 源端口号
- B. 目的端口号
- C. 长度
- D. 校验和

---

## 2018-Q40

> question_id: 2018-Q40
> exam_year: 2018
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: cn
> kp_ids: [cn.application.http]
> answer_key: D
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: complete
> gap_status: none
> gap_fields: []

**题干**：无须转换即可由 SMTP协议直接传输的内容是 。

- A. JPEG 图像
- B. MPEG 视频
- C. EXE 文件
- D. ASCII文本 --- page 5 --- 2018 年全国硕士研究生入学统一考试计算机科学与技术学科联考计算机学科专业基础综合试题 第 5 页（共 11 页）

---

