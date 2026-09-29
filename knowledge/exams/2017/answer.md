# 2017 年 408 真题 · answer

> document_id: exam-2017-answer
> exam_year: 2017
> kb_depth: exams
> doc_role: exam_answer
> source_type: third_party
> explanation_status: scan

## 2017-Q1

> question_id: 2017-Q1
> explanation_status: scan
> answer_key: B

：

sum +=++i; 相当千廿i; sum = sum + i; 。进行到第 k 趟循环， sum = (l+k)*k/2 。显然需要进
行 O(n112) 趟循环，因此这也是该函数的时间复杂度。

## 2017-Q2

> question_id: 2017-Q2
> explanation_status: scan
> answer_key: C

：

I 的反例：计算斐波拉契数列迭代实现只需要一个循环即可实现。 III 的反例：入栈序列
为 1 、 2, 进行如下操作 PUSH 、 PUSH 、 POP 、 POP, 出栈次序为 2 、 1; 进行如下操作 PUSH 、
POP 、 PUSH 、 POP, 出栈次序为 1 、 2 。 IV, 栈是一种受限的线性表，只允许在一端进行操作。
因此 II 正确。

## 2017-Q3

> question_id: 2017-Q3
> explanation_status: scan
> answer_key: null

：

三元组表的结点存储了行 row 、列 col 、值 value 三种信息，是主要用来存储稀疏矩阵的一种
数据结构。十字链表将行单链表和列单链表结合起来存储稀疏矩阵。邻接矩阵空间复杂度达 O(n2),
不适千存储稀疏矩阵。二叉链表又名左孩子右兄弟表示法，可用千表示树或森林。因此 A 正确。

## 2017-Q4

> question_id: 2017-Q4
> explanation_status: scan
> answer_key: null

：

先序序列是先父结点，接着左子树，然后右子树。中序序列是先左子树，接着父结点，然
后右子树，递归进行。如果所有非叶结点只有右子树，先序序列和中序序列都是先父结点，然
后右子树，递归进行，因此 B 正确。

## 2017-Q5

> question_id: 2017-Q5
> explanation_status: scan
> answer_key: null

：

后序序列是先左子树，接着右子树，最后父结点，递归进行。根结点左子树的叶结点首先
被访问，它是 e 。接下来是它的父结点 a, 然后是 a 的父结点 c 。接着访问根结点的右子树。它
的叶结点 b 首先被访问，然后是 b 的父结点 d, 再者是 d 的父结点 g 。最后是根结点 f。因此 d
与 a 同层， B 正确。
CBBDD 3. 
11. 
19. 
27. 
35. 
4. 
12. 
20. 
28. 
36. 
5. 
13. 
21. 
29. 
37. 
6. 
14. 
22. 
30. 
38. 
7. 
15. 
23. 
31. 
39. 
AACBC BDDBA DABDC BCDBD BCDDA ADABB 8. 
16. 
24. 
32. 
40. 
--- page 2 ---

## 2017-Q6

> question_id: 2017-Q6
> explanation_status: scan
> answer_key: null

：

哈夫曼编码是前缀编码，各个编码的前缀各不相同，因此直接拿编码序列与哈夫曼编码一
一比对即可。序列可分割为0100 011 001 001 011 11 0101, 译码结果是a fee f g d, 
选项D 正确。

## 2017-Q7

> question_id: 2017-Q7
> explanation_status: scan
> answer_key: null

：

无向图边数的两倍等于各顶点度数的总和。由于其他顶点的度均小于3, 可以设它们的度
都为2, 设它们的数量是X, 可列出方程4x3 + 3x4 + 2x = 16x2, 解得x = 3。4 + 3 + 3 = 11, B 
正确。

## 2017-Q9

> question_id: 2017-Q9
> explanation_status: scan
> answer_key: B

：

B+树是应文件系统所需而产生的B-树的变形， 前者比后者更加适用于实际应用中的操作
系统的文件索引和数据库索引，因为前者磁盘读写代价更低，查询效率更加稳定。编译器中的
词法分析使用有穷自动机和语法树。网络中的路由表快速查找主要靠高速缓存、路由表压缩技
术和快速查找算法。系统一般使用空闲空间链表管理磁盘空闲块。所以B正确。

## 2017-Q10

> question_id: 2017-Q10
> explanation_status: scan
> answer_key: null

：

归并排序代码比选择插入排序更复杂，前者空间复杂度是O(n), 后者是0(1)。但是前者时
间复杂度是O(nlogn), 后者是O(n2)。 所以B正确。

## 2017-Q11

> question_id: 2017-Q11
> explanation_status: scan
> answer_key: D

：

插入排序、选择排序、起泡排序原本时间复杂度是O(n2), 更换为链式存储 后的时间复杂度
还是O(n2)。希尔排序和堆排序都利用了顺序存储的随机访问特性，而链式存储不支持这种性质，
所以时间复杂度会增加，因此选D。

## 2017-Q12

> question_id: 2017-Q12
> explanation_status: scan
> answer_key: C

：

运行时间＝指令数xCPI/主频。Ml的时间＝指令数x2/1.5, M2的时间＝指令数xl/1.2,
两者之比为(2/1.5):(1/1.2) = 1.6。故选C。

## 2017-Q13

> question_id: 2017-Q13
> explanation_status: scan
> answer_key: C

：

由4个DRAM芯片采用交叉编址方式构成主存可知主存地址最低二位表示该字节存储的
--- page 3 ---
芯片编号。double型变量占64位， 8 个字节。 它的主存地址804 001 AH最低二位是 10, 说明 
它从编号为 2 的 芯片开始存储（编号从0 开始）。一个存储周期可以对所有芯片各读取一个字节，
因此需要 3轮， 故选C。

## 2017-Q14

> question_id: 2017-Q14
> explanation_status: scan
> answer_key: A

：

时间局部性是一旦 一条指令被执行， 则在不久的将来 它可能再次被执行。 空间局部性是一
旦 一个存储单元被访问， 那么它附近的存储单元也很快被访问。显然， 这里的循环指令本身具
有时间局部性， 它对数组a的访问具有空间局部性， 故选A。

## 2017-Q15

> question_id: 2017-Q15
> explanation_status: scan
> answer_key: D

：

在变址操作时， 将计算机指令中的地址与变址寄存器中的地址相加， 得到有效地址， 指令
提供数组首地址， 由变址寄存器来定位数据中的各元素。所以它最适合按下标顺序访问一维数
组元素， 故选D。
相对寻址以PC 为基地址， 以指令中的地址为偏移量确定有效地址。寄存器寻址则是在指
令中指出需要使用的寄存器。直接寻址是在指令的地址字段直接指出操作数的有效地址。

## 2017-Q16

> question_id: 2017-Q16
> explanation_status: scan
> answer_key: A

：

三地址指令有29条， 所以它的操作码至少为 5位。以5 位进行计算， 它剩余32 - 29 = 3
种操作码给二地址。而二地址另外多了6位给操作码， 因此它的数量最大达3x64 = 192。所以
指令字长最少为23位， 因为计算机按字节编址， 需要是8 的倍数， 所以指令字长至少应该是
24位， 故选A。

## 2017-Q17

> question_id: 2017-Q17
> explanation_status: scan
> answer_key: C

：

超标量是 指在 CPU中有 一条以上的流水线， 并且每个时钟周期内可以完成一条以上的指
令，其实质是以空间换时间。I错误，它不影响流水线功能段的处理时间； II、III正确。故选C。

## 2017-Q18

> question_id: 2017-Q18
> explanation_status: scan
> answer_key: null

：

主存储器就是我们通常说的主存， 在CPU外， 存储指令和数据， 由RAM 和ROM 实现。
控制存储器用来存放实现 指令系统的所有微指令， 是一种只读型存储器， 机器运行时只读不写，
在CPU的控制器内。cs 按照微指令的地址访问， 所以B错误。

## 2017-Q19

> question_id: 2017-Q19
> explanation_status: scan
> answer_key: A

：

五阶段流水线可分为取指(IF)、译码／取数(ID)、执行(EXC)、存储器读(MEM)、写回
(Write Back)。数字系统中， 各个子系统通过数据总线连接形成的数据传送路径称为数据通路，
包括程序计数器、算术逻辑运算部件 、通用寄存器组、取指部件等， 不包括控制部件， 故选A。

## 2017-Q20

> question_id: 2017-Q20
> explanation_status: scan
> answer_key: D

：

多总线结构用速率高的总线连接高速设备用速率低的总线连接低速设备。一般来说，CPU
是计算机的核心， 是计算机中速度最快的设备之一，所 以A正确。突发传送方式把多个数据单
元作为一个独立传输处理， 从而最大化设备的吞吐量。现实中 一般用支待突发传送方式的总线
提高存储器的读写效率，B正确。各总线通过桥接器 相连， 后者起流量交换作用。PCI-Express
总线都采用串行数据包传输数据， 所以选D。

## 2017-Q21

> question_id: 2017-Q21
> explanation_status: scan
> answer_key: D

：

I/0端口又称I/0接口， 是CPU与设备之间的交接面。 由于主机和 I/0设备的工作方式和
工作速度有很大差异，1/0端口就应运而生。在执行一条指令时，CPU 使用地址总线 选择所请
求的 I/0端口，使 用数据总线在CPU寄存器和端口之间传输数据。所以选D。

## 2017-Q22

> question_id: 2017-Q22
> explanation_status: scan
> answer_key: null

：

多重中断系统在保护被中断进程现场时关中断， 执行中断处理程序时开中断，B错误。
--- page 4 ---
CPU 一般在 一条指令执行结束的阶段采样 中断请求信号，查看是否存在中断请求，然后决定
是否响应 中断 ，A、D正确。中断请求 一般来自CPU以外的事件，异常 一般发生在 CPU内部，
C正确。

## 2017-Q23

> question_id: 2017-Q23
> explanation_status: scan
> answer_key: null

：

先来先服务 调度算法是作业来得越早，优先级越高，因此会选择JI。短作业优先调度算法
是作业运行时间越短，优先级越高，因此会选择J3。所以D正确。

## 2017-Q24

> question_id: 2017-Q24
> explanation_status: scan
> answer_key: null

：

执行 系统调用的过程是这样的：正在运行的进程先传递系统调用参数，然后由陷入(trap)
指令负责将用户态转化为内核态，并将返回地址压入堆栈以备后用 ，接下来 CPU执行相应的内
核态服务程 序，最后返回 用户态。所以C正确。

## 2017-Q25

> question_id: 2017-Q25
> explanation_status: scan
> answer_key: B

：

回收起始地址为 60K、 大小为140KB的分区时，它与表中 第一个分区和第四个分区合并，
成为 起始地址为20K、大小为380KB的分区，剩余3个空闲分区。在回收内存后，算法 会对空
闲分区链按分区大小由小到大进行 排序，表中的第二个分区排第一。所以选择B。

## 2017-Q26

> question_id: 2017-Q26
> explanation_status: scan
> answer_key: D

：

绝大多 数操作系统为改善磁盘访问时间，以簇为单位进行 空间分配 ，因此选D。

## 2017-Q27

> question_id: 2017-Q27
> explanation_status: scan
> answer_key: null

：

进程 切换带来系统开销，切换次数越多，开销越大，A正确。 当前进程的时间片用完后，
它的状态由执行态变为就绪态，B 错误。时钟中断是系统中特定的周期性时钟节拍。 操作系统
通过它来确定时间间隔，实现 时间的延时和任务的超时 ，C 正确。现代操作系统为了保证性能
最优，通常根据响应时间、系统开销、 进程数量、进程运行时间、进程切换开销等因素确定 时
间片大小， D正确。

## 2017-Q28

> question_id: 2017-Q28
> explanation_status: scan
> answer_key: D

：

多道程序系统通过组织作业（编码或数据 ）使CPU总有一个作业可执行 ，从而提高了CPU
的利用率、系统吞吐量和1/0设备利用率，I、III、IV是优点。但系统要付出额外的开销来组织
作业和切换作业，II错误。所以选D。

## 2017-Q29

> question_id: 2017-Q29
> explanation_status: scan
> answer_key: B

：

一个新的磁盘是一个空白版，必须分成扇区以便磁盘控制器能读和写，这个过程称为低级
格式化（或物理格式化）。低级 格式化为磁盘的每个扇区采 用特别的数据结构，包括校验码 ，III
错误。 为了使用 磁盘存储文件，操作系统还需要将其数据结构记录在 磁盘上。这 分为两步。第
一步是将磁盘 分为由一个或多个柱面组成的分区，每个分区可以作为一个独立的磁盘 ，I错误。
在分区之后，第二步是逻辑格式化（创建文件系统）。在这 一步，操作系统将初始的文件系统数
据结构存储到磁盘上。这些数据结构 包括空闲和已分配的空间和一个初始 为空的目录，II、IV
正确。所以选B。

## 2017-Q30

> question_id: 2017-Q30
> explanation_status: scan
> answer_key: D

：

可以把用户访问权限抽象为一个矩阵，行代表用户 ，列代表访问权限。这个矩阵有4行5
列，1代表true, 0代表false, 所以需要20位， 选D。

## 2017-Q31

> question_id: 2017-Q31
> explanation_status: scan
> answer_key: null

：

硬链接指通过索引结点进行连接。一个文件在 物理存储器上有 一个索引节点号。存在多个
文件名指向同 一个索引节点，II正确。两个进程各自维护自己的文件描述符，III正确，I错误。
所以选择B。
--- page 5 ---

## 2017-Q32

> question_id: 2017-Q32
> explanation_status: scan
> answer_key: B

：

在开始 DMA 传输时，主机向内存 写入DMA命令块 ，向 DMA控制器写入该命令块的地
址，启动1/0设备。 然后，CP U继续其他工作， DMA控制器则继续下去直接操作内存总线，
将地址放到总线上 开始传输。当整个传输完成后，DMA控制器中断CPU。因此执行顺序是2, 3, 
l, 4, 选B。

## 2017-Q33

> question_id: 2017-Q33
> explanation_status: scan
> answer_key: A

：

OSI参考模型共7层，除去物理层和应用 层，剩五层。 它们会向PD U引入20Bx5 = lOOB
的额外开销。 应用层是最顶层 ，所以它 的数据传输效率为400B/500B= 80%, 选A。

## 2017-Q34

> question_id: 2017-Q34
> explanation_status: scan
> answer_key: D

：

可用奈奎斯特采样定理计算无噪声情况下的极限数据传输速率， 用香农第二定理计算有噪
信道极限数据传输速率。 2叭og2N�叭og2(1 + SIN), W是信道带宽，N是信号状态数， SIN是信
噪比，将数据代入计算可得N�32, 选D 。 分贝数=IOlog心IN。

## 2017-Q35

> question_id: 2017-Q35
> explanation_status: scan
> answer_key: B

：

IEEE 802.11 数据帧有四种子类型，分别是IBSS、 From AP、 ToAP、 WDS。 这里的数据帧 F
是从笔记本电脑发送往访问接入点CAP),所以属于To AP子类型。这种帧地址l是RA (BSSI D), 
地址 2是SA, 地址 3是 DA。 RA是Receiver Address的缩写，BSSI D是basic service set identifier 
的缩写，SA是source address的缩写，DA是destinati on address的缩写。 因此地址 l是AP的MAC,
地址2是H的M AC, 地址3是R的MAC, 选B。

## 2017-Q36

> question_id: 2017-Q36
> explanation_status: scan
> answer_key: null

：

根据 RFC文档描述，0.0.0.0/32 可以作为本主机在本网络上的源地址。 127.0.0.1是回送地
址，以它 为目的 IP地址的数据将被立即返回到本机。200.10.10.3是C类IP地址。255.255.255.255
是广播地址。

## 2017-Q37

> question_id: 2017-Q37
> explanation_status: scan
> answer_key: D

：

RIP是一种分布式的基于距离向量的路由选择协议，通过广播 U DP报文来交换路由信息。
OSPF是一个内部网关协议，不使用 传输协议，如UDP或TCP, 而是直接用IP包封装它的数
据。 BGP是一个外部网关协议， 用TCP封装它的数据。 因此选D。

## 2017-Q38

> question_id: 2017-Q38
> explanation_status: scan
> answer_key: C

：

这个网络有16位的主机号，平均分成128个规模相同的子网，每个子网有7位的子网号，9
位的主机号。除去一个网络地址和广播地址，可分配的最大1P地址个数是29-2=512-2=510,
故选C。

## 2017-Q39

> question_id: 2017-Q39
> explanation_status: scan
> answer_key: A

：

按照慢开始算法，发送窗口 = min{拥塞窗口，接收窗口｝，初始的拥塞窗口为最大报文段
长度1KB海经过一个RTT, 拥塞窗口翻倍，因此需至少经过5个RTT, 发送窗口才能达到32KB,
所以选A。 这里假定乙能及时处理接收到的数据，空闲的接收缓存�32KB。

## 2017-Q40

> question_id: 2017-Q40
> explanation_status: scan
> answer_key: C

：

FTP协议使用控制连接和数据连接，控制连接存在于整个FTP会话过程中，数据连接在每
次文件传输时才建立，传输结束就关闭，A 和 B是正确的。默认情况下 FTP协议使用TCP 20 
端口进行 数据连接，TCP 21端口进行控制连接。 但是是否使用TCP 20端口建立数据连接与传
输模式 有关，主动方式使用TCP20端口， 被动方式由服务器和客户端自行协商决定，C错， D
对。所以选C。
--- page 6 ---
二、综合应用题
41. 解答：
(I)算法的基本设计思想
表达式树的中序序列加上必要的括号即为等价的中缀表达式。可以基于二叉树的中序遍历
策略得到所需的表达式。(3分）
表达式树中分支结点所对应的子表达式的计算次序， 由该分支结点所处的位置决定。为得
到正确的中缀表达式， 需要在生成遍历序列的同时，在适当位置增加必要的括号。显然， 表达
式的最外层（对应根结点）及操作数（对应叶结点）不需要添加括号。(2分）
(2)算法实现(IQ分）
将二叉树的中序遍历递归算法稍加改造即可得本题答案。除根结点和叶结点外， 遍历到其
他结点时在遍历其左子树之前加上左括号， 在遍历完右子树后加上右括号。
void B 七reeToE(BTree *root 
BtreeToExp(root, 1); ／／根的高度为1
void. 13七reeToE:xp(BTree *roqt, int deep) 
｛ 
／／空结点返回if(root == NULL) return; 
else if(root->left==NULL&&r�ot 今right==NULL) !/若为叶结点
printf ("%s", root->data); //输出操作数，不加括号
else{ 
if (deep>l) printf (" ("); //若有子表达式则加1层括号
BtreeToExp(root

