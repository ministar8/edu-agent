# 2012 年 408 真题 · items

> document_id: exam-2012-items
> exam_year: 2012
> kb_depth: exams
> doc_role: exam_item
> source_type: third_party
> credibility: high
> explanation_status: scan

答案只在 metadata（answer_key），正文不印答案。

## 2012-Q1

> question_id: 2012-Q1
> exam_year: 2012
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

**题干**：求整数 n（n≥0）阶乘的算法如下，其时间复杂度是 。 int fact (int n){ if(n<=1) return 1 return n*fact(n-10) }

- A. O(log2n)
- B. O(n)
- C. O(nlog2n)
- D. O(n 2 )

---

## 2012-Q2

> question_id: 2012-Q2
> exam_year: 2012
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: ds
> kp_ids: [ds.stack_queue.stack]
> answer_key: A
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: complete
> gap_status: none
> gap_fields: []

**题干**：已知操作符包括‘+’ 、 ‘-’ 、 ‘*’ 、 ‘/’ 、 ‘(’和‘)’ 。将中缀表达式a+b-a*((c+d)/e-f)+g 转换为等价 的后缀表达式 ab+acd+e/f-*-g+时，用栈来存放暂时还不能确定运算次序的操作符，若栈初始时为 空，则转换过程中同时保存在栈中的操作符的最大个数是 。

- A. 5
- B. 7
- C. 8
- D. 11

---

## 2012-Q3

> question_id: 2012-Q3
> exam_year: 2012
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
> has_figure: false
> figure_status: null
> completeness: complete
> gap_status: none
> gap_fields: []

**题干**：若一棵二叉树的前序遍历序列为 a, e, b, d, c ，后序遍历序列为 b, c, d, e, a ，则根结点的孩子结 点 。

- A. 只有 e
- B. 有 e、b
- C. 有 e、c
- D. 无法确定

---

## 2012-Q4

> question_id: 2012-Q4
> exam_year: 2012
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: ds
> kp_ids: [ds.tree.avl]
> answer_key: B
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: complete
> gap_status: none
> gap_fields: []

**题干**：若平衡二叉树的高度为 6，且所有非叶结点的平衡因子均为 1，则该平衡二叉树的结点总数 为 。

- A. 10
- B. 20
- C. 32
- D. 33

---

## 2012-Q5

> question_id: 2012-Q5
> exam_year: 2012
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: ds
> kp_ids: [ds.graph.storage]
> answer_key: C
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: complete
> gap_status: none
> gap_fields: []

**题干**：对有 n个结点、e条边且使用邻接表存储的有向图进行广度优先遍历， 其算法时间复杂度是 。

- A. O(n)
- B. O(e)
- C. O(n + e)
- D. O(ne)

---

## 2012-Q6

> question_id: 2012-Q6
> exam_year: 2012
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: ds
> kp_ids: [ds.graph.topo]
> answer_key: C
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: complete
> gap_status: none
> gap_fields: []

**题干**：若用邻接矩阵存储有向图，矩阵中主对角线以下的元素均为零，则关于该图拓扑序列的结论 是 。

- A. 存在，且唯一
- B. 存在，且不唯一
- C. 存在，可能不唯一
- D. 无法确定是否存在

---

## 2012-Q7

> question_id: 2012-Q7
> exam_year: 2012
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: ds
> kp_ids: [ds.graph.shortest_path]
> answer_key: C
> reference_answer: null
> has_figure: true
> figure_status: missing
> completeness: partial
> gap_status: partial
> gap_fields: [figure]

**题干**：如右图所示的有向带权图，若采用迪杰斯特拉 （Dijkstra） 算法求从源点a到其他各顶点的最短路径， 则得到的第一条最短路径的目标顶点是 b， 第二条最短 路径的目标顶点是 c， 后续得到的其余各最短路径的目 标顶点依次是 。

- A. d, e, f
- B. e, d, f
- C. f, d, e
- D. f, e, d

---

## 2012-Q8

> question_id: 2012-Q8
> exam_year: 2012
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: ds
> kp_ids: [ds.graph.mst]
> answer_key: A
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: complete
> gap_status: none
> gap_fields: []

**题干**：下列关于最小生成树的叙述中，正确的是 I. 最小生成树的代价唯一 II. 所有权值最小的边一定会出现在所有的最小生成树中 III. 使用普里姆(Prim)算法从不同顶点开始得到的最小生成树一定相同 IV . 使用普里姆算法和克鲁斯卡尔(Kruskal)算法得到的最小生成树总不相同

- A. 仅 I
- B. 仅 II
- C. 仅 I、III
- D. 仅 II、IV

---

## 2012-Q9

> question_id: 2012-Q9
> exam_year: 2012
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
> has_figure: true
> figure_status: missing
> completeness: partial
> gap_status: partial
> gap_fields: [figure]

**题干**：已知一棵 3 阶B-树，如下图所示。删除关键字 78 得到一棵新B-树，其最右叶结点中的关键字 是 。

- A. 60
- B. 60 62
- C. 62,65
- D. 65 --- page 2 --- 2012 年全国硕士研究生入学统一考试计算机科学与技术学科联考计算机学科专业基础综合试题 第 2 页（共 11 页）

---

## 2012-Q10

> question_id: 2012-Q10
> exam_year: 2012
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

**题干**：在内部排序过程中，对尚未确定最终位置的所有元素进行一遍处理称为一趟排序。下列排序方法 中，每一趟排序结束都至少能够确定一个元素最终位置的方法是 。 I. 简单选择排序 II. 希尔排序 III. 快速排序 IV . 堆排序 V . 二路归并排序

- A. 仅 I、III、IV
- B. 仅 I、III、V
- C. 仅 II、III、IV
- D. 仅 III、IV、V

---

## 2012-Q11

> question_id: 2012-Q11
> exam_year: 2012
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

**题干**：对一待排序序列分别进行折半插入排序和直接插入排序，两者之间可能的不同之处是 。

- A. 排序的总趟数
- B. 元素的移动次数
- C. 使用辅助空间的数量
- D. 元素之间的比较次数

---

## 2012-Q12

> question_id: 2012-Q12
> exam_year: 2012
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: co
> kp_ids: [co.overview.performance]
> answer_key: D
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: complete
> gap_status: none
> gap_fields: []

**题干**：假定基准程序 A 在某计算机上的运行时间为 100 秒，其中 90 秒为CPU 时间，其余为 I/O 时间。 若 CPU 速度提高 50%, I/O速度不变，则运行基准程序 A所耗费的时间是 。

- A. 55s
- B. 60s
- C. 65s
- D. 70s

---

## 2012-Q13

> question_id: 2012-Q13
> exam_year: 2012
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

**题干**：假定编译器规定 int 和 short 型长度分别为 32 位和 16 位，执行下列C 语言语句： unsigned short x=65530; unsigned int y=x; 得到 y的机器数为 。

- A. 0000 7FFAH
- B. 0000 FFFAH
- C. FFFF 7FFAH
- D. FFFF FFFAH

---

## 2012-Q14

> question_id: 2012-Q14
> exam_year: 2012
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

**题干**：float类型（即 IEEE 754 单精度浮点数格式）能表示的最大正整数是 。

- A. 2 126 －2 103
- B. 2 127 －2 104
- C. 2 121 －2 103
- D. 2 128 －2 104

---

## 2012-Q15

> question_id: 2012-Q15
> exam_year: 2012
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

**题干**：某计算机存储器按字节编址，采用小端方式存放数据。假定编译器规定 int 型和 short 型长度分别 为 32 位和 16 位，并且数据按边界对齐存储。某C 语言程序段如下： struct { int a; char b; short c; } record; record.a=273; 若 record变量的首地址为 0xC008,则地址 0xC008 中内容及record.c的地址分别为 。

- A. 0x00、0xC00D
- B. 0x00、0xC00E
- C. 0x11、0xC00D
- D. 0x11、0xC00E

---

## 2012-Q16

> question_id: 2012-Q16
> exam_year: 2012
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

**题干**：下列关于闪存（Flash Memory）的叙述中，错误的是。

- A. 信息可读可写，并且读、写速度一样快
- B. 存储元由 MOS 管组成，是一种半导体存储器
- C. 掉电后信息不丢失，是一种非易失性存储器
- D. 采用随机访问方式，可替代计算机外部存储器

---

## 2012-Q17

> question_id: 2012-Q17
> exam_year: 2012
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: co
> kp_ids: [co.storage.cache]
> answer_key: C
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: complete
> gap_status: none
> gap_fields: []

**题干**：假设某计算机按字编址，Cache有 4 个行，Cache 和主存之间交换的块大小为 1 个字。若Cache 的 内容初始为空，采用 2 路组相联映射方式和LRU 替换策略。访问的主存地址依次为 0, 4, 8, 2, 0, 6, 8, 6, 4, 8 时， 命中 Cache的次数是 。

- A. 1
- B. 2
- C. 3
- D. 4

---

## 2012-Q18

> question_id: 2012-Q18
> exam_year: 2012
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: os
> kp_ids: [os.process.sync]
> answer_key: C
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: complete
> gap_status: none
> gap_fields: []

**题干**：某计算机的控制器采用微程序控制方式， 微指令中的操作控制字段采用字段直接编码法， 共有 33 个微命令， 构成 5 个互斥类， 分别包含 7、 3、 12、 5 和 6 个微命令， 则操作控制字段至少有 。

- A. 5 位
- B. 6 位
- C. 15 位
- D. 33 位

---

## 2012-Q19

> question_id: 2012-Q19
> exam_year: 2012
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

**题干**：某同步总线的时钟频率为 100MHz, 宽度为 32 位， 地址/数据线复用， 每传输一个地址或数据占 用一个时钟周期。若该总线支持突发（猝发）传输方式， 则一次“主存写”总线事务传输 128 位 数据所需要的时间至少是 。

- A. 20ns
- B. 40ns
- C. 50ns
- D. 80ns

---

## 2012-Q20

> question_id: 2012-Q20
> exam_year: 2012
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

**题干**：下列关于 USB 总线特性的描述中，错误的是 。

- A. 可实现外设的即插即用和热拔插
- B. 可通过级联方式连接多台外设 --- page 3 --- 2012 年全国硕士研究生入学统一考试计算机科学与技术学科联考计算机学科专业基础综合试题 第 3 页（共 11 页）
- C. 是一种通信总线， 连接不同外设
- D. 同时可传输 2 位数据， 数据传输率高

---

## 2012-Q21

> question_id: 2012-Q21
> exam_year: 2012
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

**题干**：下列选项中，在 I/O总线的数据线上传输的信息包括 。 I. I/O接口中的命令字 II. I/O 接口中的状态字 III. 中断类型号

- A. 仅 I、II
- B. 仅 I、III
- C. 仅 II、III
- D. I 、II、III

---

## 2012-Q22

> question_id: 2012-Q22
> exam_year: 2012
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

**题干**：响应外部中断的过程中，中断隐指令完成的操作，除保护断点外，还包括 。 I. 关中断 II. 保存通用寄存器的内容 III. 形成中断服务程序入口地址并送 PC

- A. 仅 I、II
- B. 仅 I、III
- C. 仅 II、III
- D. I 、II、III

---

## 2012-Q23

> question_id: 2012-Q23
> exam_year: 2012
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

**题干**：下列选项中，不可能在用户态发生的事件是 。

- A. 系统调用
- B. 外部中断
- C. 进程切换
- D. 缺页

---

## 2012-Q24

> question_id: 2012-Q24
> exam_year: 2012
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

**题干**：中断处理和子程序调用都需要压栈以保护现场， 中断处理一定会保存而子程序调用不需要保存其 内容的是 。

- A. 程序计数器
- B. 程序状态字寄存器
- C. 通用数据寄存器
- D. 通用地址寄存器

---

## 2012-Q25

> question_id: 2012-Q25
> exam_year: 2012
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: os
> kp_ids: [os.memory.virtual]
> answer_key: B
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: complete
> gap_status: none
> gap_fields: []

**题干**：下列关于虚拟存储器的叙述中，正确的是 。

- A. 虚拟存储只能基于连续分配技术
- B. 虚拟存储只能基于非连续分配技术
- C. 虚拟存储容量只受外存容量的限制
- D. 虚拟存储容量只受内存容量的限制

---

## 2012-Q26

> question_id: 2012-Q26
> exam_year: 2012
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

**题干**：操作系统的 I/O 子系统通常由四个层次组成，每一层明确定义了与邻近层次的接口。其合理的层 次组织排列顺序是

- A. 用户级 I/O软件、设备无关软件、设备驱动程序、中断处理程序
- B. 用户级 I/O软件、设备无关软件、中断处理程序、设备驱动程序
- C. 用户级 I/O软件、设备驱动程序、设备无关软件、中断处理程序
- D. 用户级 I/O软件、中断处理程序、设备无关软件、设备驱动程序

---

## 2012-Q27

> question_id: 2012-Q27
> exam_year: 2012
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: os
> kp_ids: [os.process.deadlock]
> answer_key: D
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: complete
> gap_status: none
> gap_fields: []

**题干**：假设 5 个进程P0、P1、P2、P3、P4 共享三类资源 R1、R2、R3 , 这些资源总数分别为 18、6、22。T0 时刻的资源分配情况如下表所示， 此时存在的一个安全序列是 。 进程 已分配资源 资源最大需求 R1 R2 R3 R1 R 2 R 3 P0 3 2 3 5 5 10 P1 4 0 3 5 3 6 P2 4 0 5 4 0 11 P3 2 0 4 4 2 5 P4 3 1 4 4 2 4

- A. P0, P2, P4, P1, P3
- B. P 1, P0, P3, P4, P2
- C. P 2, P1, P0, P3, P4
- D. P 3, P4, P2, P1, P0

---

## 2012-Q28

> question_id: 2012-Q28
> exam_year: 2012
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: os
> kp_ids: [os.overview.syscall]
> answer_key: A
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: complete
> gap_status: none
> gap_fields: []

**题干**：若一个用户进程通过 read 系统调用读取一个磁盘文件中的数据，则下列关于此过程的叙述中，正 确的是 。 I. 若该文件的数据不在内存中，则该进程进入睡眠等待状态。 II. 请求 read 系统调用会导致 CPU 从用户态切换到核心态 III. read系统调用的参数应包含文件的名称

- A. 仅 I、II
- B. 仅 I、III
- C. 仅 II、III
- D. I 、II 和 III

---

## 2012-Q29

> question_id: 2012-Q29
> exam_year: 2012
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: os
> kp_ids: [os.process.schedule]
> answer_key: B
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: complete
> gap_status: none
> gap_fields: []

**题干**：一个多道批处理系统中仅有 P1和 P2 两个作业，P2比 P1晚 5ms 到达，它们的计算和 I/O 操作顺序 如下： P1：计算 60ms，I/O 80ms，计算 20ms P 2：计算 120ms，I/O 40ms，计算 40ms 若不考虑调度和切换时间， 则完成两个作业需要的时间最少是 。

- A. 240ms
- B. 260ms
- C. 340ms
- D. 360ms

---

## 2012-Q30

> question_id: 2012-Q30
> exam_year: 2012
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

**题干**：若某单处理器多进程系统中有多个就绪态进程， 则下列关于处理机调度的叙述中， 错误的是 。

- A. 在进程结束时能进行处理机调度
- B. 创建新进程后能进行处理机调度
- C. 在进程处于临界区时不能进行处理机调度 --- page 4 --- 2012 年全国硕士研究生入学统一考试计算机科学与技术学科联考计算机学科专业基础综合试题 第 4 页（共 11 页）
- D. 在系统调用完成并返回用户态时能进行处理机调度

---

## 2012-Q31

> question_id: 2012-Q31
> exam_year: 2012
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: os
> kp_ids: [os.process.thread]
> answer_key: A
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: complete
> gap_status: none
> gap_fields: []

**题干**：下列关于进程和线程的叙述中，正确的是 。

- A. 不管系统是否支待线程，进程都是资源分配的基本单位
- B. 线程是资源分配的基本单位，进程是调度的基本单位
- C. 系统级线程和用户级线程的切换都需要内核的支持
- D. 同一进程中的各个线程拥有各自不同的地址空间

---

## 2012-Q32

> question_id: 2012-Q32
> exam_year: 2012
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: os
> kp_ids: [os.file.alloc]
> answer_key: B
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: complete
> gap_status: none
> gap_fields: []

**题干**：下列选项中，不能改善磁盘设备 I/O性能的是

- A. 重排 I/O请求次序
- B. 在一个磁盘上设置多个分区
- C. 预读和滞后写
- D. 优化文件物理块的分布

---

## 2012-Q33

> question_id: 2012-Q33
> exam_year: 2012
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: cn
> kp_ids: [cn.arch.model]
> answer_key: B
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: complete
> gap_status: none
> gap_fields: []

**题干**：在 TCP/IP 体系结构中，直接为 ICMP 提供服务的协议是 。

- A. PPP
- B. IP
- C. UDP
- D. TCP

---

## 2012-Q34

> question_id: 2012-Q34
> exam_year: 2012
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: cn
> kp_ids: [cn.physical.channel]
> answer_key: C
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: complete
> gap_status: none
> gap_fields: []

**题干**：在物理层接口特性中， 用于描述完成每种功能的事件发生顺序的是。

- A. 机械特性
- B. 功能特性
- C. 过程特性
- D. 电气特性

---

## 2012-Q35

> question_id: 2012-Q35
> exam_year: 2012
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: cn
> kp_ids: [cn.datalink.mac]
> answer_key: A
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: complete
> gap_status: none
> gap_fields: []

**题干**：以太网的 MAC 协议提供的是 。

- A. 无连接不可靠服务
- B. 无连接可靠服务
- C. 有连接不可靠服务
- D. 有连接可靠服务

---

## 2012-Q36

> question_id: 2012-Q36
> exam_year: 2012
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

**题干**：两台主机之间的数据链路层采用后退 N 帧协议(GBN)传输数据，数据传输速率为 16kbps, 单向传 播时延为 270ms, 数据帧长度范围是 128～512 字节，接收方总是以与数据帧等长的帧进行确认。 为使信道利用率达到最高，帧序号的比特数至少为 。

- A. 5
- B. 4
- C. 3
- D. 2

---

## 2012-Q37

> question_id: 2012-Q37
> exam_year: 2012
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

**题干**：下列关于 IP 路由器功能的描述中，正确的是 。 I. 运行路由协议，设置路由表 II. 监测到拥塞时，合理丢弃 IP 分组 III. 对收到的 IP 分组头进行差错校验，确保传输的 IP 分组不丢失 IV . 根据收到的 IP 分组的目的 IP 地址，将其转发到合适的输出线路上

- A. 仅 III、IV
- B. 仅 I、II、III
- C. 仅 I、II、IV
- D. I、II、III、IV

---

## 2012-Q38

> question_id: 2012-Q38
> exam_year: 2012
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: cn
> kp_ids: [cn.datalink.mac]
> answer_key: A
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: complete
> gap_status: none
> gap_fields: []

**题干**：ARP 协议的功能是 。

- A. 根据 IP 地址查询 MAC 地址
- B. 根据 MAC 地址查询 IP 地址
- C. 根据域名查询 IP 地址
- D. 根据 IP 地址查询域名

---

## 2012-Q39

> question_id: 2012-Q39
> exam_year: 2012
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: cn
> kp_ids: [cn.network.ip_address]
> answer_key: D
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: complete
> gap_status: none
> gap_fields: []

**题干**：某主机的 IP 地址为 180.80.77.55, 子网掩码为 255.255.252.0。若该主机向其所在子网发送广播分 组，则目的地址可以是

- A. 180.80.76.0
- B. 180.80.76.255
- C. 180.80.77.255
- D. 180.80.79.255

---

## 2012-Q40

> question_id: 2012-Q40
> exam_year: 2012
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
> has_figure: true
> figure_status: missing
> completeness: partial
> gap_status: partial
> gap_fields: [figure]

**题干**：若用户 1 与用户 2 之间发送和接收电子邮件的过程如下图所示， 则图中①、②、③阶段分别使 用的应用层协议可以是 。

- A. SMTP、SMTP、SMTP
- B. POP3、SMTP、POP3
- C. POP3、SMTP、SMTP
- D. SMTP、SMTP、POP3 --- page 5 --- 2012 年全国硕士研究生入学统一考试计算机科学与技术学科联考计算机学科专业基础综合试题 第 5 页（共 11 页）

---

