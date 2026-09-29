# 2020 年 408 真题 · items

> document_id: exam-2020-items
> exam_year: 2020
> kb_depth: exams
> doc_role: exam_item
> source_type: third_party
> credibility: high
> explanation_status: scan

答案只在 metadata（answer_key），正文不印答案。

## 2020-Q1

> question_id: 2020-Q1
> exam_year: 2020
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: ds
> kp_ids: [ds.array.symmetric]
> answer_key: C
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: complete
> gap_status: none
> gap_fields: []

**题干**：将一个 10×10 对称矩阵 M 的上三角部分的元素叫 mi, j（1≤i≤j≤10）按列优先存入 C 语言的一 维数组 N 中，元素 m7, 2 在 N 中的下标是 。

- A. 15
- B. 16
- C. 22
- D. 23

---

## 2020-Q2

> question_id: 2020-Q2
> exam_year: 2020
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

**题干**：对空栈 S 进行 Push 和 Pop 操作，入栈序列为 a, b, c, d, e，经过 Push, Push, Pop, Push, Pop, Push, Push, Pop 操作后得到的出栈序列是 。

- A. b, a, c
- B. b, a, e
- C. b, c, a
- D. b, c, e

---

## 2020-Q3

> question_id: 2020-Q3
> exam_year: 2020
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: ds
> kp_ids: [ds.tree.binary_tree, ds.tree.complete]
> answer_key: A
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: complete
> gap_status: none
> gap_fields: []

**题干**：对于任意一棵高度为 5 且有 10 个结点的二叉树，若采用顺序存储结构保存，每个结点占 1 个存 储单元（仅存放结点的数据信息） ，则存放该二叉树需要的存储单元数量至少是 。

- A. 31
- B. 16
- C. 15
- D. 10

---

## 2020-Q4

> question_id: 2020-Q4
> exam_year: 2020
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

**题干**：已知森林 F 及与之对应的二叉树 T，若 F 的先根遍历序列是 a, b, c, d, e, f，中根遍历序列是 b, a, d, f, e, c,则 T 的后根遍历序列是 。

- A. b, a, d, f, e, c
- B. b, d, f, e, c, a
- C. b, f, e, d, c, a
- D. f, e, d, c, b, a

---

## 2020-Q5

> question_id: 2020-Q5
> exam_year: 2020
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: ds
> kp_ids: [ds.tree.bst]
> answer_key: B
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: complete
> gap_status: none
> gap_fields: []

**题干**：下列给定的关键字输入序列中，不能生成如下二叉排序树的是 。

- A. 4, 5, 2, 1, 3
- B. 4, 5, 1, 2, 3
- C. 4, 2, 5, 3, 1
- D. 4, 2, 1, 3, 5

---

## 2020-Q6

> question_id: 2020-Q6
> exam_year: 2020
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: ds
> kp_ids: [ds.graph.traversal, ds.graph.topo]
> answer_key: B
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: complete
> gap_status: none
> gap_fields: []

**题干**：修改递归方式实现的图的深度优先搜索（DFS）算法，将输出（访问）顶 点信息的语句移到退出递归前（即执行输出语句后立刻退出递归） 。采用 修改后的算法遍历有向无环图 G，若输出结果中包含 G 中的全部顶点，则输出的顶点序列是 G 的 。

- A. 拓扑有序序列
- B. 逆拓扑有序序列
- C. 广度优先搜索序列
- D. 深度优先搜索序列

---

## 2020-Q7

> question_id: 2020-Q7
> exam_year: 2020
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

**题干**：已知无向图 G 如下所示，使用克鲁斯卡尔（Kruskal）算法 求图 G 的最小生成树,加到最小生成树中的边依次 是 。

- A. (b, f), (b, d), (a, e), (c, e), (b, e)
- B. (b, f), (b, d), (b, e), (a, e), (c, e)
- C. (a, e), (b, e), (c, e), (b, d), (b, f)
- D. (a, e), (c, e), (b, e), (b, f), (b, d)

---

## 2020-Q8

> question_id: 2020-Q8
> exam_year: 2020
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: ds
> kp_ids: [ds.graph.aoe]
> answer_key: B
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: complete
> gap_status: none
> gap_fields: []

**题干**：若使用 AOE 网估算工程进度，则下列叙述中正确的是 。

- A. 关键路径是从原点到汇点边数最多的一条路径
- B. 关键路径是从原点到汇点路径长度最长的路径
- C. 增加任一关键活动的时间不会延长工程的工期
- D. 缩短任一关键活动的时间将会缩短工程的工期

---

## 2020-Q9

> question_id: 2020-Q9
> exam_year: 2020
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: ds
> kp_ids: [ds.sort.heap]
> answer_key: C
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: complete
> gap_status: none
> gap_fields: []

**题干**：下列关于大根堆（至少含 2 个元素）的叙述中，正确的是 。 I. 可以将堆视为一棵完全二叉树 II. 可以采用顺序存储方式保存堆 III. 可以将堆视为一棵二叉排序树 IV . 堆中的次大值一定在根的下一层

- A. 仅 I、II
- B. 仅 II、III
- C. 仅 I、II 和 IV
- D. 仅 I、III 和 IV

---

## 2020-Q10

> question_id: 2020-Q10
> exam_year: 2020
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

**题干**：依次将关键字 5, 6, 9, 13, 8, 2, 12, 15 插入初始为空的 4 阶 B 树后，根结点中包含的关键字 是 。

- A. 8
- B. 6,9
- C. 8, 13
- D. 9, 12 --- page 2 --- 2020 年全国硕士研究生入学统一考试计算机科学与技术学科联考计算机学科专业基础综合试题 第 2 页（共 12 页）

---

## 2020-Q11

> question_id: 2020-Q11
> exam_year: 2020
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: ds
> kp_ids: [ds.sort.insertion, ds.sort.select]
> answer_key: A
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: complete
> gap_status: none
> gap_fields: []

**题干**：对大部分元素已有序的数组进行排序时，直接插入排序比简单选择排序效率更高，其原因 是 。 I. 直接插入排序过程中元素之间的比较次数更少 II. 直接插入排序过程中所需要的辅助空间更少 III. 直接插入排序过程中元素的移动次数更少

- A. 仅 I
- B. 仅 III
- C. 仅 I、II
- D. I 、II 和 III

---

## 2020-Q12

> question_id: 2020-Q12
> exam_year: 2020
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

**题干**：下列给出的部件中，其位数（宽度）一定与机器字长相同的是 。 I. ALU II. 指令寄存器 III. 通用寄存器 IV . 浮点寄存器

- A. 仅 I 、II
- B. 仅 I 、III
- C. 仅 II 、III
- D. 仅 II、III、IV

---

## 2020-Q13

> question_id: 2020-Q13
> exam_year: 2020
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: co
> kp_ids: [co.representation.complement, co.representation.ieee754]
> answer_key: A
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: complete
> gap_status: none
> gap_fields: []

**题干**：已知带符号整数用补码表示，float 型数据用 IEEE 754 标准表示，假定变量 x 的类型只可能是 int 或 float,当 x 的机器数为 C800 0000H 时，x 的值可能是 。

- A. －7×2 27
- B. －2 16
- C. 2 17
- D. 25×2 27

---

## 2020-Q14

> question_id: 2020-Q14
> exam_year: 2020
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

**题干**：在按字节编址，采用小端方式的 32 位计算机中，按边界对齐方式为以下 C 语言结构型变量 a 分 配存储空间： Struct record{ short x1; int x2; } a; 若 a 的首地址为 2020 FE00H，a 的成员变量 x2 的机器数为 1234 0000H，则其中 34H 所在存储单 元的地址是 。

- A. 2020 FE03H
- B. 2020 FE04H
- C. 2020 FE05H
- D. 2020 FE06H

---

## 2020-Q15

> question_id: 2020-Q15
> exam_year: 2020
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: co
> kp_ids: [co.storage.cache, os.memory.tlb]
> answer_key: D
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: complete
> gap_status: none
> gap_fields: []

**题干**：下列关于 TLB 和 Cache 的叙述中，错误的是 。

- A. 命中率都与程序局部性有关
- B. 缺失后都需要去访问主存
- C. 缺失处理都可以由硬件实现
- D. 都由 DRAM 存储器组成

---

## 2020-Q16

> question_id: 2020-Q16
> exam_year: 2020
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: co
> kp_ids: [co.instruction.format, co.instruction.addressing]
> answer_key: A
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: complete
> gap_status: none
> gap_fields: []

**题干**：某计算机采用 16 位定长指令字格式，操作码位数和寻址方式位数固定，指令系统有 48 条指令， 支持直接、间接、立即、相对 4 种寻址方式。单地址指令中，直接寻址方式的可寻址范围 是 。

- A. 0～255
- B. 0～1023
- C. －128～127
- D. －512～511

---

## 2020-Q17

> question_id: 2020-Q17
> exam_year: 2020
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

**题干**：下列给出的处理器类型中，理想情况下，CPI 为 1 的是 。 I. 单周期 CPU II. 多周期 CPU III. 基本流水线 CPU IV . 超标量流水线 CPU

- A. 仅 I、II
- B. 仅 I、III
- C. 仅 II、IV
- D. 仅 III、IV

---

## 2020-Q18

> question_id: 2020-Q18
> exam_year: 2020
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

**题干**：下列关于“自陷” （Trap，也称陷阱）的叙述中，错误的是 。

- A. 自陷是通过陷阱指令预先设定的一类外部中断事件
- B. 自陷可用于实现程序调试时的断点设置和单步跟踪
- C. 自陷发生后 CPU 将转去执行操作系统内核相应程序
- D. 自陷处理完成后返回到陷阱指令的下一条指令执行

---

## 2020-Q19

> question_id: 2020-Q19
> exam_year: 2020
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

**题干**：QPI 总线是一种点对点全工同步串行总线，总线上的设备可同时接收和发送信息，每个方向可同 时传输 20 位信息（16 位数据 +4 位校验位） ，每个QPI 数据包有 80 位信息，分 2 个时钟周期传 送，每个时钟周期传递 2 次。因此，QPI 总线带宽为：每秒传送次数×2B×2。若 QPI 时钟频率 为 2.4GHz,则总线带宽为 。

- A. 4.8GBps
- B. 9.6GBps
- C. 19.2GBps
- D. 38.4GBps

---

## 2020-Q20

> question_id: 2020-Q20
> exam_year: 2020
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

**题干**：下列事件中，属于外部中断事件的是 。 I. 访存时缺页 II. 定时器到时 III. 网络数据包到达

- A. 仅 I 、II
- B. 仅 I 、III
- C. 仅 II、III
- D. I 、II 和 III

---

## 2020-Q21

> question_id: 2020-Q21
> exam_year: 2020
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

**题干**：外部中断包括不可屏蔽中断（NMI）和可屏蔽中断，下列关于外部中断的叙述中，错误的 是 。

- A. CPU 处于关中断状态时，也能响应 NMI 请求 --- page 3 --- 2020 年全国硕士研究生入学统一考试计算机科学与技术学科联考计算机学科专业基础综合试题 第 3 页（共 12 页）
- B. 一旦可屏蔽中断请求信号有效，CPU 将立即响应
- C. 不可屏蔽中断的优先级比可屏蔽中断的优先级高
- D. 可通过中断屏蔽字改变可屏蔽中断的处理优先级

---

## 2020-Q22

> question_id: 2020-Q22
> exam_year: 2020
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: co
> kp_ids: [co.io.dma]
> answer_key: C
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: complete
> gap_status: none
> gap_fields: []

**题干**：若设备采用周期挪用 DMA 方式进行输入和输出，每次 DMA 传送的数据块大小为 512 字节，相 应的 I/O 接口中有一个 32 位数数据缓冲寄存器。对于数据输入过程，下列叙述中，错误的 是 。

- A. 每准备好 32 位数据，DMA 控制器就发出一次总线请求
- B. 相对于 CPU，DMA 控制器的总线使用权的优先级更高
- C. 在整个数据块的传送过程中，CPU 不可以访问主存储器
- D. 数据块传送结束时，会产生“DMA 传送结束”中断请求

---

## 2020-Q23

> question_id: 2020-Q23
> exam_year: 2020
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: os
> kp_ids: [os.file.logical]
> answer_key: B
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: complete
> gap_status: none
> gap_fields: []

**题干**：若多个进程共享同一个文件 F，则下列叙述中，正确的是 。

- A. 各进程只能用“读”方式打开文件 F
- B. 在系统打开文件表中仅有一个表项包含 F 的属性
- C. 各进程的用户打开文件表中关于 F 的表项内容相同
- D. 进程关闭 F 时，系统删除 F 在系统打开文件表中的表项

---

## 2020-Q24

> question_id: 2020-Q24
> exam_year: 2020
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

**题干**：下列选项中，支持文件长度可变、随机访问的磁盘存储空间分配方式是 。

- A. 索引分配
- B. 链接分配
- C. 连续分配
- D. 动态分区分配

---

## 2020-Q25

> question_id: 2020-Q25
> exam_year: 2020
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: os
> kp_ids: [co.cpu.exception, os.overview.syscall]
> answer_key: D
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: complete
> gap_status: none
> gap_fields: []

**题干**：下列与中断相关的操作中，由操作系统完成的是 。 I. 保存被中断程序的中断点 II. 提供中断服务 III. 初始化中断向量表 IV . 保存中断屏蔽字

- A. 仅 I、II
- B. 仅 I、II、IV
- C. 仅 III、IV
- D. 仅 II、III、IV

---

## 2020-Q26

> question_id: 2020-Q26
> exam_year: 2020
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: os
> kp_ids: [os.process.schedule]
> answer_key: D
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: complete
> gap_status: none
> gap_fields: []

**题干**：下列与进程调度有关的因素中，在设计多级反馈队列调度算法时需要考虑的是 。 I. 就绪队列的数量 II. 就绪队列的优先级 III. 各就绪队列的调度算法 IV . 进程在就绪队列间的迁移条件

- A. 仅 I、II
- B. 仅 III、IV
- C. 仅 II 、III、IV
- D. I 、II、III 和 IV

---

## 2020-Q27

> question_id: 2020-Q27
> exam_year: 2020
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: os
> kp_ids: [os.process.bankers]
> answer_key: B
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: complete
> gap_status: none
> gap_fields: []

**题干**：某系统中有 A、B 两类资源各 6 个，t 时刻资源分配及需求情况如下表所示 进程 A 已分配数量 B 已分配数量 A 需求总量 B 需求总量 P1 2 3 4 4 P2 2 1 3 1 P3 1 2 3 4 t 时刻安全性检测的结果是 。

- A. 存在安全序列 P1、P2、P3
- B. 存在安全序列 P2、P1、P3
- C. 存在安全序列 P2、P3、P1
- D. 不存在安全序列

---

## 2020-Q28

> question_id: 2020-Q28
> exam_year: 2020
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: os
> kp_ids: [os.memory.virtual, os.memory.page_fault]
> answer_key: D
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: complete
> gap_status: none
> gap_fields: []

**题干**：下列因素中，影响请求分页系统有效（平均）访存时间的是 。 I. 缺页率 II. 磁盘读写时间 III. 内存访问时间 IV . 执行缺页处理程序的 CPU 时间

- A. 仅 II、III
- B. 仅 I、IV
- C. 仅 I、III、IV
- D. I 、II、III 和 IV

---

## 2020-Q29

> question_id: 2020-Q29
> exam_year: 2020
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: os
> kp_ids: [os.process.thread]
> answer_key: B
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: complete
> gap_status: none
> gap_fields: []

**题干**：下列关于父进程与子进程的叙述中，错误的是 。

- A. 父进程与子进程可以并发执行
- B. 父进程与子进程共享虚拟地址空间
- C. 父进程与子进程有不同的进程控制块
- D. 父进程与子进程不能同时使用同一临界资源

---

## 2020-Q30

> question_id: 2020-Q30
> exam_year: 2020
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

**题干**：对于具备设备独立性的系统，下列叙述中，错误的是 。

- A. 可以使用文件名访问物理设备
- B. 用户程序使用逻辑设备名访问物理设备
- C. 需要建立逻辑设备与物理设备之间的映射关系
- D. 更换物理设备后必须修改访问该设备的应用程序 --- page 4 --- 2020 年全国硕士研究生入学统一考试计算机科学与技术学科联考计算机学科专业基础综合试题 第 4 页（共 12 页）

---

## 2020-Q31

> question_id: 2020-Q31
> exam_year: 2020
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

**题干**：某文件系统的目录项由文件名和索引结点号构成。若每个目录项长度为 64 字节，其中 4 字节存 放索引结点号，60 字节存放文件名。文件名由小写英文字母构成，则该文件系统能创建的文件 数量的上限为 。

- A. 2 26
- B. 2 32
- C. 2 60
- D. 2 64

---

## 2020-Q32

> question_id: 2020-Q32
> exam_year: 2020
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

**题干**：下列准则中，实现临界区互斥机制必须遵循的是 。 I. 两个进程不能同时进入临界区 II. 允许进程访问空闲的临界资源 III. 进程等待进入临界区的时间是有限的 IV . 不能进入临界区的执行态进程立即放弃 CPU

- A. 仅 I 、IV
- B. 仅 II 、III
- C. 仅 I 、II、III
- D. 仅 I 、III、IV

---

## 2020-Q33

> question_id: 2020-Q33
> exam_year: 2020
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
> has_figure: true
> figure_status: missing
> completeness: partial
> gap_status: partial
> gap_fields: [figure]

**题干**：下图描述的协议要素是 。 I. 语法 II. 语义 III. 时序

- A. 仅 I
- B. 仅 II
- C. 仅 III
- D. I、II 和 III

---

## 2020-Q34

> question_id: 2020-Q34
> exam_year: 2020
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: cn
> kp_ids: [cn.network.ip]
> answer_key: B
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: complete
> gap_status: none
> gap_fields: []

**题干**：下列关于虚电路网络的叙述中，错误的是 。

- A. 可以确保数据分组传输顺序
- B. 需要为每条虚电路预分配带宽
- C. 建立虚电路时需要进行路由选择
- D. 依据虚电路号（VCID）进行数据分组转发

---

## 2020-Q35

> question_id: 2020-Q35
> exam_year: 2020
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: cn
> kp_ids: [cn.datalink.ethernet]
> answer_key: C
> reference_answer: null
> has_figure: true
> figure_status: missing
> completeness: partial
> gap_status: partial
> gap_fields: [figure]

**题干**：在下图所示的网络中，冲突域和广播域的个数分别是 。

- A. 2, 2
- B. 2, 4
- C. 4, 2
- D. 4, 4

---

## 2020-Q36

> question_id: 2020-Q36
> exam_year: 2020
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

**题干**：假设主机甲采用停–等协议向主机乙发送数据帧，数据帧长与确认帧长均为 1000B，数据传输速 率是 10kbps，单向传播延时是 200ms。则甲的最大信道利用率为 。

- A. 80%
- B. 66.7%
- C. 44.4%
- D. 40% --- page 5 --- 2020 年全国硕士研究生入学统一考试计算机科学与技术学科联考计算机学科专业基础综合试题 第 5 页（共 12 页）

---

## 2020-Q37

> question_id: 2020-Q37
> exam_year: 2020
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
> has_figure: true
> figure_status: missing
> completeness: partial
> gap_status: partial
> gap_fields: [figure]

**题干**：某 IEEE 802.11 无线局域网中，主机 H 与 AP 之间发送或接收 CSMA/CA 帧的过程如下图所示。 在 H 或 AP 发送帧前所等待的帧间间隔时间（IFS）中，最长的是 。

- A. IFS1
- B. IFS2
- C. IFS3
- D. IFS4

---

## 2020-Q38

> question_id: 2020-Q38
> exam_year: 2020
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: cn
> kp_ids: [cn.transport.tcp_congestion]
> answer_key: D
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: complete
> gap_status: none
> gap_fields: []

**题干**：若主机甲与主机乙已建立一条 TCP 连接，最大段长（MSS）为 1KB，往返时间（RTT）为 2ms，则在不出现拥塞的前提下，拥塞窗口从 8KB 增长到 32KB 所需的最长时间是 。

- A. 4ms
- B. 8ms
- C. 24ms
- D. 48ms

---

## 2020-Q39

> question_id: 2020-Q39
> exam_year: 2020
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: cn
> kp_ids: [cn.transport.tcp]
> answer_key: C
> reference_answer: null
> has_figure: false
> figure_status: null
> completeness: complete
> gap_status: none
> gap_fields: []

**题干**：若主机甲与主机乙建立 TCP 连接时，发送的 SYN 段中的序号为 1000，在断开连接时，甲发送给 乙的 FIN 段中的序号为 5001，则在无任何重传的情况下，甲向乙已经发送的应用层数据的字节 数为 。

- A. 4002
- B. 4001
- C. 4000
- D. 3999

---

## 2020-Q40

> question_id: 2020-Q40
> exam_year: 2020
> question_type: choice
> score: 2
> part: 一、单项选择题
> source_type: third_party
> credibility: high
> explanation_status: scan
> subject: cn
> kp_ids: [cn.application.dns]
> answer_key: D
> reference_answer: null
> has_figure: true
> figure_status: missing
> completeness: partial
> gap_status: partial
> gap_fields: [figure]

**题干**：假设下图所示网络中的本地域名服务器只提供递归查询服务，其他域名服务器均只提供迭代查询 服务；局域网内主机访问 Internet 上各服务器的往返时间（RTT）均为 10ms,忽略其他各种时延。 若主机 H 通过超链接 http://www.abc.com/index.html 请求浏览纯文本 Web 页 index.html,则从点击 超链接开始到浏览器接收到 index.html 页面为止，所需的最短时间与最长时间分别是 。

- A. 10ms, 40ms
- B. 10ms, 50ms
- C. 20ms, 40ms
- D. 20ms, 50ms --- page 6 --- 2020 年全国硕士研究生入学统一考试计算机科学与技术学科联考计算机学科专业基础综合试题 第 6 页（共 12 页）

---

