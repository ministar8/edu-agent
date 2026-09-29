# 2014 年 408 真题 · items

> document_id: exam-2014-items
> exam_year: 2014
> kb_depth: exams
> doc_role: exam_item
> source_type: third_party
> credibility: high
> explanation_status: scan

答案只在 metadata（answer_key），正文不印答案。

## 2014-Q1

> question_id: 2014-Q1
> exam_year: 2014
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: ds
> kp_ids: []
> answer_key: C
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: complete
> gap_status: none
> gap_fields: []

**题干**：下列程序段的时间复杂度是 。 count=0; for (k=1; k<=n;k*=2) for (j=1; j<=n; j++) count++;

- A. O(log2n)
- B. O(n)
- C. O(nlog2n)
- D. O(n 2 )

---

## 2014-Q2

> question_id: 2014-Q2
> exam_year: 2014
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

**题干**：假设栈初始为空，将中缀表达式 a/b＋(c*d－e*f)/g 转换为等价的后缀表达式的过程中，当扫描到 f 时，栈中的元素依次是 。

- A. ＋ ( * －
- B. ＋ ( － *
- C. / ＋ ( * － *
- D. / ＋ － *

---

## 2014-Q3

> question_id: 2014-Q3
> exam_year: 2014
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: ds
> kp_ids: [ds.stack_queue.queue]
> answer_key: A
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: complete
> gap_status: none
> gap_fields: []

**题干**：循环队列放在一维数组 A[0…M－1]中，end1 指向队头元素，end2 指向队尾元素的后一个位置。 假设队列两端均可进行入队和出队操作，队列中最多能容纳 M－1 个元素。初始时为空。下列判 断队空和队满的条件中，正确．．的是 。

- A. 队空：end1 == end2; 队满：end1 == (end2 + 1) mod M
- B. 队空：end1 == end2; 队满：end2 == (end1 + 1) mod (M－1)
- C. 队空：end2 == (end1 + 1) mod M; 队满：end1 == (end2 + 1) mod M
- D. 队空：end1 == (end2 + 1) mod M; 队满：end2 == (end1 + 1) mod (M－1)

---

## 2014-Q4

> question_id: 2014-Q4
> exam_year: 2014
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: ds
> kp_ids: [ds.tree.traversal]
> answer_key: D
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: complete
> gap_status: none
> gap_fields: []

**题干**：若对如下的二叉树进行中序线索化，则结点 x的左、右线索指向的结点分别是 。

- A. e、c
- B. e、a
- C. d、c
- D. b、a

---

## 2014-Q5

> question_id: 2014-Q5
> exam_year: 2014
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: ds
> kp_ids: [ds.tree.forest_convert]
> answer_key: C
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: complete
> gap_status: none
> gap_fields: []

**题干**：将森林 F 转换为对应的二叉树 T，F 中叶结点的个数等于 。

- A. T中叶结点的个数
- B. T中度为 1 的结点个数
- C. T中左孩子指针为空的结点个数
- D. T中右孩子指针为空的结点个数

---

## 2014-Q6

> question_id: 2014-Q6
> exam_year: 2014
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: ds
> kp_ids: [ds.tree.huffman]
> answer_key: null
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: partial
> gap_status: partial
> gap_fields: [answer]

**题干**：5 个字符有如下 4 种编码方案，不是．．前缀编码的是 。

- A. 01, 0000, 0001, 001, 1
- B. 011, 000, 001, 010, 1
- C. 000, 001, 010, 011, 100
- D. 0, 100, 110, 1110, 1100

---

## 2014-Q7

> question_id: 2014-Q7
> exam_year: 2014
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: ds
> kp_ids: [ds.graph.topo]
> answer_key: D
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: complete
> gap_status: none
> gap_fields: []

**题干**：对如下所示的有向图进行拓扑排序，得到的拓扑序列可能是 。

- A. 3, 1, 2, 4, 5, 6
- B. 3, 1, 2, 4, 6, 5
- C. 3, 1, 4, 2, 5, 6
- D. 3, 1, 4, 2, 6, 5

---

## 2014-Q8

> question_id: 2014-Q8
> exam_year: 2014
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: ds
> kp_ids: [ds.search.hash]
> answer_key: D
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: complete
> gap_status: none
> gap_fields: []

**题干**：用哈希（散列）方法处理冲突（碰撞）时可能出现堆积（聚集）现象。下列选项中，会受堆积现 象直接影响的是 。

- A. 存储效率
- B. 散列函数
- C. 装填（装载）因子
- D. 平均查找长度 --- page 2 --- 2014 年全国硕士研究生入学统一考试计算机科学与技术学科联考计算机学科专业基础综合试题 第 2 页（共 11 页）

---

## 2014-Q9

> question_id: 2014-Q9
> exam_year: 2014
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: ds
> kp_ids: [ds.search.b_tree]
> answer_key: D
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: complete
> gap_status: none
> gap_fields: []

**题干**：在一棵具有 15 个关键字的 4 阶B 树中，含关键字的结点个数最多是 。

- A. 5
- B. 6
- C. 10
- D. 15

---

## 2014-Q10

> question_id: 2014-Q10
> exam_year: 2014
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: ds
> kp_ids: [ds.sort.shell]
> answer_key: B
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: complete
> gap_status: none
> gap_fields: []

**题干**：用希尔排序方法对一个数据序列进行排序时，若第 1 趟排序结果为 9, 1, 4, 13, 7, 8, 20, 23, 15，则 该趟排序采用的增量（间隔）可能是 。

- A. 2
- B. 3
- C. 4
- D. 5

---

## 2014-Q11

> question_id: 2014-Q11
> exam_year: 2014
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

**题干**：下列选项中，不可能是快速排序第 2 趟排序结果的是 。

- A. 2, 3, 5, 4, 6, 7, 9
- B. 2, 7, 5, 6, 4, 3, 9
- C. 3, 2, 5, 4, 7, 6, 9
- D. 4, 2, 3, 5, 7, 6, 9

---

## 2014-Q12

> question_id: 2014-Q12
> exam_year: 2014
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

**题干**：程序 P 在机器 M 上的执行时间是 20 秒，编译优化后，P 执行的指令数减少到原来的 70%，而 CPI 增加到原来的 1.2 倍，则P 在 M 上的执行时间是 。

- A. 8.4 秒
- B. 11.7 秒
- C. 14 秒
- D. 16.8 秒

---

## 2014-Q13

> question_id: 2014-Q13
> exam_year: 2014
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: co
> kp_ids: [co.representation.complement]
> answer_key: C
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: complete
> gap_status: none
> gap_fields: []

**题干**：若 x=103, y =－25, 则下列表达式采用 8 位定点补码运算实现时，会发生溢出的是 。

- A. x＋y
- B. －x＋y
- C. x －y
- D. －x－y

---

## 2014-Q14

> question_id: 2014-Q14
> exam_year: 2014
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

**题干**：float型数据常用 IEEE754 单精度浮点格式表示。假设两个float型变量 x和 y分别存放在 32 位寄 存器 f1和 f2中，若(f1)=CC90 0000H, (f2)= B0C0 0000H, 则 x和 y之间的关系为 。

- A. x < y且符号相同
- B. x < y 且符号不同
- C. x > y 且符号相同
- D. x > y 且符号不同

---

## 2014-Q15

> question_id: 2014-Q15
> exam_year: 2014
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: co
> kp_ids: [co.storage.main_memory]
> answer_key: A
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: complete
> gap_status: none
> gap_fields: []

**题干**：某容量为 256MB 的存储器由若干 4Mx8 位的DRAM 芯片构成，该 DRAM 芯片的地址引脚和数 据引脚总数是 。

- A. 19
- B. 22
- C. 30
- D. 36

---

## 2014-Q16

> question_id: 2014-Q16
> exam_year: 2014
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: ds
> kp_ids: [ds.search.hash]
> answer_key: D
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: complete
> gap_status: none
> gap_fields: []

**题干**：采用指令 Cache与数据 Cache分离的主要目的是 。

- A. 降低 Cache的缺失损失
- B. 提高 Cache的命中率
- C. 降低 CPU 平均访存时间
- D. 减少指令流水线资源冲突

---

## 2014-Q17

> question_id: 2014-Q17
> exam_year: 2014
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

**题干**：某计算机有 16 个通用寄存器，采用 32 位定长指令字，操作码字段（含寻址方式位）为 8 位， Store 指令的源操作数和目的操作数分别采用寄存器直接寻址和基址寻址方式。若基址寄存器可 使用任一通用寄存器，且偏移量用补码表示，则 Store 指令中偏移量的取值范围是 。

- A. －32768～＋32767
- B. －32767～＋32768
- C. －65536～＋65535
- D. －65535～＋65536

---

## 2014-Q18

> question_id: 2014-Q18
> exam_year: 2014
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: co
> kp_ids: [co.cpu.controller]
> answer_key: C
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: complete
> gap_status: none
> gap_fields: []

**题干**：某计算机采用微程序控制器，共有 32 条指令，公共的取指令微程序包含 2 条微指令，各指令对 应的微程序平均由 4 条微指令组成，采用断定法（下地址字段法）确定下条微指令地址，则微指 令中下地址字段的位数至少是 。

- A. 5
- B. 6
- C. 8
- D. 9

---

## 2014-Q19

> question_id: 2014-Q19
> exam_year: 2014
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

**题干**：某同步总线采用数据线和地址线复用方式，其中地址/数据线有 32 根，总线时钟频率为 66MHz， 每个时钟周期传送两次数据（上升沿和下降沿各传送一次数据） ，该总线的最大数据传输率（总 线带宽）是 。

- A. 132MB/s
- B. 264MB/s
- C. 528MB/s
- D. 1056MB/s

---

## 2014-Q20

> question_id: 2014-Q20
> exam_year: 2014
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

**题干**：一次总线事务中，主设备只需给出一个首地址，从设备就能从首地址开始的若干连续单元读出或 写入多个数据。这种总线事务方式称为 。

- A. 并行传输
- B. 串行传输
- C. 突发传输
- D. 同步传输

---

## 2014-Q21

> question_id: 2014-Q21
> exam_year: 2014
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: co
> kp_ids: [co.storage.main_memory]
> answer_key: D
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: complete
> gap_status: none
> gap_fields: []

**题干**：下列有关 I/O接口的叙述中，错误的是 。

- A. 状态端口和控制端口可以合用同一个寄存器
- B. I/O 接口中 CPU 可访问的寄存器称为 I/O端口
- C. 采用独立编址方式时，I/O端口地址和主存地址可能相同
- D. 采用统一编址方式时，CPU 不能用访存指令访问 I/O端口

---

## 2014-Q22

> question_id: 2014-Q22
> exam_year: 2014
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

**题干**：若某设备中断请求的响应和处理时间为 100ns，每 400ns 发出一次中断请求，中断响应所允许的 最长延迟时间为 50ns，则在该设备持续工作过程中，CPU 用于该设备的 I/O时间占整个 CPU 时 间的百分比至少是 。

- A. 12.5%
- B. 25%
- C. 37.5%
- D. 50%

---

## 2014-Q23

> question_id: 2014-Q23
> exam_year: 2014
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

**题干**：下列调度算法中，不可能导致饥饿现象的是 。

- A. 时间片轮转
- B. 静态优先数调度 --- page 3 --- 2014 年全国硕士研究生入学统一考试计算机科学与技术学科联考计算机学科专业基础综合试题 第 3 页（共 11 页）
- C. 非抢占式短作业优先
- D. 抢占式短作业优先

---

## 2014-Q24

> question_id: 2014-Q24
> exam_year: 2014
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: os
> kp_ids: [os.process.deadlock]
> answer_key: null
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: partial
> gap_status: partial
> gap_fields: [answer]

**题干**：某系统有 n台互斥使用的同类设备，三个并发进程分别需要 3、4、5 台设备，可确保系统不发生 死锁的设备数 n最小为 。

- A. 9
- B. 10
- C. 11
- D. 12

---

## 2014-Q25

> question_id: 2014-Q25
> exam_year: 2014
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

**题干**：下列指令中，不能在用户态执行的是 。

- A. trap指令
- B. 跳转指令
- C. 压栈指令
- D. 关中断指令

---

## 2014-Q26

> question_id: 2014-Q26
> exam_year: 2014
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

**题干**：一个进程的读磁盘操作完成后，操作系统针对该进程必做的是 。

- A. 修改进程状态为就绪态
- B. 降低进程优先级
- C. 给进程分配用户内存空间
- D. 增加进程时间片大小

---

## 2014-Q27

> question_id: 2014-Q27
> exam_year: 2014
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: os
> kp_ids: [os.file.disk_free_space]
> answer_key: A
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: complete
> gap_status: none
> gap_fields: []

**题干**：现有一个容量为 10GB 的磁盘分区， 磁盘空间以簇（Cluster）为单位进行分配，簇的大小为 4KB，若采用位图法管理该分区的空闲空间，即用一位（bit）标识一个簇是否被分配，则存放该 位图所需簇的个数为 。

- A. 80
- B. 320
- C. 80K
- D. 320K

---

## 2014-Q28

> question_id: 2014-Q28
> exam_year: 2014
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

**题干**：下列措施中，能加快虚实地址转换的是 。 I. 增大块表（TLB）容量 II. 让页表常驻内存 III. 增大交换区（swap）

- A. 仅 I
- B. 仅 II
- C. 仅 I、II
- D. 仅 II、III

---

## 2014-Q29

> question_id: 2014-Q29
> exam_year: 2014
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: os
> kp_ids: [os.io.device]
> answer_key: B
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: complete
> gap_status: none
> gap_fields: []

**题干**：在一个文件被用户进程首次打开的过程中，操作系统需要做的是 。

- A. 将文件内容读到内存中
- B. 将文件控制块读到内存中
- C. 修改文件控制块中的读写权限
- D. 将文件的数据缓冲区首指针返回给用户进程

---

## 2014-Q30

> question_id: 2014-Q30
> exam_year: 2014
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

**题干**：在页式虚拟存储管理系统中，采用某些页面置换算法，会出现 Belady 异常现象，即进程的缺页 次数会随着分配给该进程的页框个数的增加而增加。下列算法中，可能出现 Belady 异常现象的 是 。 I. LRU算法 II. FIFO算法 III. OPT算法

- A. 仅 II
- B. 仅 I、II
- C. 仅 I、III
- D. 仅 II、III

---

## 2014-Q31

> question_id: 2014-Q31
> exam_year: 2014
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

**题干**：下列关于管道（Pipe）通信的叙述中，正确的是 。

- A. 一个管道可实现双向数据传输
- B. 管道的容量仅受磁盘容量大小限制
- C. 进程对管道进行读操作和写操作都可能被阻塞
- D. 一个管道只能有一个读进程或一个写进程对其操作

---

## 2014-Q32

> question_id: 2014-Q32
> exam_year: 2014
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

**题干**：下列选项中，属于多级页表优点的是 。

- A. 加快地址变换速度
- B. 减少缺页中断次数
- C. 减少页表项所占字节数
- D. 减少页表所占的连续内存空间

---

## 2014-Q33

> question_id: 2014-Q33
> exam_year: 2014
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

**题干**：在 OSI参考模型中，直接为会话层提供服务的是 。

- A. 应用层
- B. 表示层
- C. 传输层
- D. 网络层

---

## 2014-Q34

> question_id: 2014-Q34
> exam_year: 2014
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

**题干**：某以太网拓扑及交换机当前转发表如下图所示，主机 00-e1-d5-00-23-a1 向主机 00-e1-d5-00-23-c1 发送 1 个数据帧，主机 00-e1-d5-00-23-c1 收到该帧后，向主机 00-e1-d5-00-23-a1 发送 1 个确认 帧，交换机对这两个帧的转发端口分别是 。

- A. {3}和{1}
- B. {2, 3}和{1}
- C. {2,3}和{1, 2}
- D. {1, 2, 3}和{1}

---

## 2014-Q35

> question_id: 2014-Q35
> exam_year: 2014
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: cn
> kp_ids: [cn.physical.bandwidth]
> answer_key: D
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: complete
> gap_status: none
> gap_fields: []

**题干**：下列因素中，不会影响信道数据传输速率的是 。

- A. 信噪比
- B. 频率宽带
- C. 调制速率
- D. 信号传播速度 --- page 4 --- 2014 年全国硕士研究生入学统一考试计算机科学与技术学科联考计算机学科专业基础综合试题 第 4 页（共 11 页）

---

## 2014-Q36

> question_id: 2014-Q36
> exam_year: 2014
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

**题干**：主机甲与主机乙之间使用后退 N 帧协议（GBN）传输数据，甲的发送窗口尺寸为 1000，数据帧 长为 1000 字节，信道带宽为 100Mbps，乙每收到一个数据帧立即利用一个短帧（忽略其传输延 迟）进行确认，若甲、乙之间的单向传播延迟是 50ms，则甲可以达到的最大平均数据传输速率 约为

- A. 10Mbps
- B. 20Mbps
- C. 80Mbps
- D. 100Mbps

---

## 2014-Q37

> question_id: 2014-Q37
> exam_year: 2014
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

**题干**：站点 A、B、C 通过 CDMA 共享链路，A、B、C 的码片序列（chipping sequence）分别是(1, 1, 1, 1)、(1,－1, 1, －1)和(1, 1, －1, －1)。若 C 从链路上收到的序列是(2, 0, 2, 0, 0, －2, 0, －2, 0, 2, 0, 2), 则 C 收到 A发送的数据是 。

- A. 000
- B. 101
- C. 110
- D. 111

---

## 2014-Q38

> question_id: 2014-Q38
> exam_year: 2014
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

**题干**：主机甲和主机乙已建立了 TCP 连接，甲始终以 MSS = 1KB 大小的段发送数据，并一直有数据发 送；乙每收到一个数据段都会发出一个接收窗口为 10KB 的确认段。若甲在 t 时刻发生超时时拥 塞窗口为 8KB，则从 t 时刻起，不再发生超时的情况下，经过 10 个RTT后，甲的发送窗口 是 。

- A. 10KB
- B. 12KB
- C. 14KB
- D. 15KB

---

## 2014-Q39

> question_id: 2014-Q39
> exam_year: 2014
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

**题干**：下列关于 UDP协议的叙述中，正确的是 。 I. 提供无连接服务 II. 提供复用/分用服务 III. 通过差错校验，保障可靠数据传输

- A. 仅 I
- B. 仅 I、II
- C. 仅 II、III
- D. I 、II、III

---

## 2014-Q40

> question_id: 2014-Q40
> exam_year: 2014
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: cn
> kp_ids: [cn.network.arp]
> answer_key: D
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: complete
> gap_status: none
> gap_fields: []

**题干**：使用浏览器访问某大学 Web网站主页时， 不可能使用到的协议是 。

- A. PPP
- B. ARP
- C. UDP
- D. SMTP --- page 5 --- 2014 年全国硕士研究生入学统一考试计算机科学与技术学科联考计算机学科专业基础综合试题 第 5 页（共 11 页）

---

