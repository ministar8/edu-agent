# 2015 年 408 真题 · answer

> document_id: exam-2015-answer
> exam_year: 2015
> kb_depth: exams
> doc_role: exam_answer
> source_type: third_party
> explanation_status: scan

## 2015-Q1

> question_id: 2015-Q1
> explanation_status: scan
> answer_key: A

：

递归调用函数时，在系统栈里保存的函数信息需满足先进后出的特点，依次调用了 main(),
S(l), S(O), 故栈底到栈顶的信息依次是 main(), S(1), S(O) 。

## 2015-Q2

> question_id: 2015-Q2
> explanation_status: scan
> answer_key: B

：

根据二叉树前序遍历和中序遍历的递归算法中递归工作栈的状态变化得出：前序序列和中
序序列的关系相当于以前序序列为入栈次序，以中序序列为出栈次序。因为前序序列和中序序
列可以唯一地确定一棵二叉树，所以题意相当千“以序列 a, b, c, d 为入栈次序，则出栈序列的
个数为多少“，对于 n 个不同元素进栈，出栈序列的个数为—-c;n= 14 。
n+l 
3. 
11. 
19. 
27. 
35. 
4. 
12. 
20. 
28. 
36. 
CBCCC ACBCA CDDCC DBBBA DABAB DACAB BCDBA 5. 
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
8. 
16. 
24. 
32. 
40.

## 2015-Q3

> question_id: 2015-Q3
> explanation_status: scan
> answer_key: C

：

在哈夫曼树中，左右孩子权值之和为父结点权值。仅以分析选项 A 为例：若两个 10 分别
属千两棵不同的子树，根的权值不等于其孩子的权值和，不符；若两个 10 属于同棵子树，其权
值不等千其两个孩子（叶结点）的权值和，不符。 B 、 C 选项的排除方法一样。

## 2015-Q4

> question_id: 2015-Q4
> explanation_status: scan
> answer_key: C

：

只有两个结点的平衡二叉树的根结点的度为 1, A 错误。中序遍历后可以得到一个降序序
列，树中最大元素一定无左子树（可能有右子树），因此不一定是叶结点， B 错误。最后插入的
结点可能会导致平衡调整，而不一定是叶结点， C 错误。

## 2015-Q5

> question_id: 2015-Q5
> explanation_status: scan
> answer_key: C

：

画出该有向图图形如下。
采用图的深度优先遍历，共 5 种可能： <vo, VJ, V3, V2>, <vo, V2, V3, V1>, <vo, V2, Vi, V3>, <vo, V3, 
V2, V1>, <vo, V3, V1, V2>, 选 D 。

## 2015-Q6

> question_id: 2015-Q6
> explanation_status: scan
> answer_key: A

：

从 V4 开始， Kruskal 算法选中的第一条边一定是权值最小的 (V1,V4), B 错误。由于 V1 和
--- page 2 ---
V4 已经可达，第二条边含有V 1和V4 的权值为8 的一定符合Prim 算法，排除
A、D。

## 2015-Q7

> question_id: 2015-Q7
> explanation_status: scan
> answer_key: C

：

画出查找路径图，因为折半查找的判定树是一棵二叉排序树，看其是否满足二叉排序树的
要求。 ＾ 
500 
180 
450 
450 
显然，选项A的查找路径不满足。

## 2015-Q8

> question_id: 2015-Q8
> explanation_status: scan
> answer_key: B

：

由题中
“
失配s[ i] :/; 玵］时，i=j=S", 可知题中的主串和模式串 的位序都是从0开始的（要
注意灵活应变）。按照next数组生成算法，对于t有
编号
t 
。 2 3 4 5
a a 
next 一1
1-b-o
a
-0
b一1 c-2
依据KMP算法
”
当失配时，i不变，j回退到next[j]的位置并重新比较
”，当失配s[i]f; t[j]
时，i=j =5, 由上表不难得出next[j]= next[5] = 2 (位序从0开始）。从而最后结果应为i= 5 (i 
保持不变），j=2。

## 2015-Q9

> question_id: 2015-Q9
> explanation_status: scan
> answer_key: C

：

基数排序的元素移动次数与关键字的初始排列次序无关，而其他三种排序都是与关键字的
初始排列明显相关的。

## 2015-Q10

> question_id: 2015-Q10
> explanation_status: scan
> answer_key: A

：

删除8后，将12 移动到堆顶，第一次是15和10比较，第二次是10和12比较并交换，
第三次还需比较12和16, 故比较次数为3次。
,/\� I\ / \ 
j�; i� 气芒＼、巴
，矗 全、
(10) 
夕
－
／
气、一
--�---
(15) i'12 
£-\ .--< (21 -,'
. 
34 i v 
: 16) 
, _ _j \�i 
--、
(12 J 
--、／
、
��---! 15) (10 
;--\ . ,.1-· 
(21, ， 
＼ ) (34) (16) 
、、j , __令

## 2015-Q11

> question_id: 2015-Q11
> explanation_status: scan
> answer_key: C

：

希尔排序的思想是： 先将待排元素序列分割成若干子序列（由相隔某个
“
增量
”
的元素组
成），分别进行直接插入排序，然后依次缩减增量再进行排序，待整个序列中的元素基本有序（增
量足够小）时，再对全体元素进行一次直接插入排序。

## 2015-Q12

> question_id: 2015-Q12
> explanation_status: scan
> answer_key: D

：

硬件能直接执行的只能是机器语言（二进制编码），汇编语言是为了增强机器语言的可诙
性和记忆性的语言，经过汇编后才能被执行。

## 2015-Q13

> question_id: 2015-Q13
> explanation_status: scan
> answer_key: D

：

补码整数表示时，负数的符号位为I, 数值位按位取反，末位加I, 因此剩下的2个"I "
--- page 3 ---
在最低位时，表示的是最小整数，为10000011, 转换成真值为-125。

## 2015-Q14

> question_id: 2015-Q14
> explanation_status: scan
> answer_key: C

：

对阶是较小的阶码对齐至较 大的阶码，I 正确。右规和尾数舍入过程，阶码加1而可能上
溢，II正确， 同理III也正确。尾数溢出时可能仅产生误差，结果不一 定溢出，IV正确。
15 .. 解析：
直接映射的 地址结构如下 ：
I 主存字块标记 I Cache字块标记 1 字块内地址
按字节编址，块大小为4x32bit= 16B = 24 B, 则
“
字块内 地址
”
占4位；
“
能存放4K字数
据的Cache"即Cache的存储容量为4K字（注意单位），则Cache共有IK= 210 个Cache行，
Cache字块标记占10位；主存字块标记占32-10 -4= 18位。
Cache的总容量包括：存储容量和标记阵列容量（有效位、 标记位、 一致性维护位和替换
算法 控制位）。标记阵列中的有效位和标记位是一 定有的，而 一致性维护位（脏位） 和替换算法
控制位的 取舍 标准是看题眼，题目中，明确说明了采用写回法，因此 一 定包含 一致性维护位，
而关于替换算法的词眼题目中未提及，所以不予考虑。
从而每个Cache行 标记项包含18+ 1 + 1 = 20位， 标记阵列容量为： 210 x20位=20K位，
存储容量为： 4Kx32位 =128K位，则总容量为128K+ 20K = 148K位。

## 2015-Q15

> question_id: 2015-Q15
> explanation_status: scan
> answer_key: C

：

正确答案：C。（详见 `knowledge/answers/2015-answer.pdf`）

## 2015-Q16

> question_id: 2015-Q16
> explanation_status: scan
> answer_key: D

：

上述指令的执行过程可划分为取数、 运算和写回过程， 取数时读取xaddr可能不需要访问
主存而直接访问Cache, 而写 直通方式需要把数据 同时 写入Cache和主存，因此至少访问 1次。

## 2015-Q17

> question_id: 2015-Q17
> explanation_status: scan
> answer_key: B

：

DRAM使用电容存储，所以必须隔 一段时间刷新 一次，如果存储单元没有被刷新，存储的
信息就会丢失。SDRAM表示同步动态随机存储器。

## 2015-Q18

> question_id: 2015-Q18
> explanation_status: scan
> answer_key: B

：

每个访存地址对应的存储模块序号(0, I, 2, 3)如下所示。
访存地址 I 8005 I 8006 I 8007 l 8008 I 8001 I 8002 I 8003 I 8004 I 8000 
模块序号
2 3 。 2 3 。 。
其中，模块序号＝访存地址％存储器交叉模块数。
判断可能发生访存冲突的规则是：给定的访存地址在相邻的四次访问中出现在同 一 个存储
模块内。据此，根据上表可知8004和8000对应的模块号都为o, 即表明这两次的访问出现在
同 一模块内且在相邻的访问请求中，满足发生冲突的条件。

## 2015-Q19

> question_id: 2015-Q19
> explanation_status: scan
> answer_key: B

：

在同步通信方式中，系统采用一 个统一的时钟信号，而不是由各设备提供，否则没法实现
统一的时钟。

## 2015-Q20

> question_id: 2015-Q20
> explanation_status: scan
> answer_key: A

：

存取时间＝寻道时间＋延迟时间＋传输时间。存取 一 个扇区的平均延迟时间为旋转半
周的时间，即为(60/7200)/2= 4. l 7ms, 传输时间为(60/7200)/1000= O.Olms, 因此访问 一 个扇区
的平均存取时间为4.17+ O.Ql + 8 = 12.18ms, 保留 一位小数则为12.2ms。

## 2015-Q21

> question_id: 2015-Q21
> explanation_status: scan
> answer_key: D

：

在程序中断I/0方式中，CPU和打印机直接交换， 打印字符直接传输到打印机的 I/0端口，
不会涉及主存地址，而 CPU和打印机通过I/0端口中状态口和控制口来实现交互。
--- page 4 ---

## 2015-Q22

> question_id: 2015-Q22
> explanation_status: scan
> answer_key: A

：

内中断是指来自CPU和内存内部产生的中断，包括程序运算引起的各种错误，如地址非法、
校验错、 页面失效、 非法指令、 用户程序执行特权指令自行中断(INT)和除数为零等，以上
中断都在指令的执行过程中产生的，故A正确。这种检测 异常的工作肯定是由CPU (包括控制
器和运算器）实现的，故B正确。内中断不能被屏蔽，一旦出现应立即处理，C正确。对于D,
考虑到特殊情况， 如除数为零和自行中断(INT) 都会自动跳过中断指令， 所以不会返回到发
生异常的指令继续执行，故错误。

## 2015-Q23

> question_id: 2015-Q23
> explanation_status: scan
> answer_key: B

：

外部中断处理过程，PC值由中断隐指令自动保存，而通用寄存器 内容由操作系统保存。

## 2015-Q24

> question_id: 2015-Q24
> explanation_status: scan
> answer_key: A

：

考虑到部分指令可能出现异常（导致中断），从而转到核心态。指令A有除零 异常的可能，
指令B为 中断指令，指令D有缺页异常的可能，指令C不会发生异常。

## 2015-Q25

> question_id: 2015-Q25
> explanation_status: scan
> answer_key: D

：

P(wait)操作表示进程请求某 一资源，A、B和C都 因为请求某 一资源会进入阻塞态，而D
只是被剥夺了处理机资源，进入就绪态，一旦得到处理机即可运行。

## 2015-Q26

> question_id: 2015-Q26
> explanation_status: scan
> answer_key: D

：

死锁的处理采用三种策略：死锁预防、死锁避免、 死锁检测和解除。
死锁预防，采用破坏产生死锁的四个必要条件中的一个或几个，以防止发生死锁。其中之
一的
“
破坏循环等待条件
”
，一般采用顺序资源分配法，首先给系统的资源编号，规定每个进程
必须按编号递增的顺序请求资源，也就是限制了用户申请资源的顺序，故I的前半句属于死锁
预防的范畴。
银行家算法是最著名的死锁避免算法，其中的最大需求矩阵M心”迁义了每 一个进程对m
类资源的最大需求量，系统在执行安全性算法中都会检查此次资源试分配后，系统是否处于安
全状态，若不安全则将本次的试探分配作废。
在死锁的检测和解除中，在系统为进程分配资源时不采取任何措施，但提供死锁的检测和
解除的手段。故II、 III正确。

## 2015-Q27

> question_id: 2015-Q27
> explanation_status: scan
> answer_key: A

：

可以采用书中常规的解法思路，也可以采用便捷法。对页号序列从后往前计数，直到数到
4 (页框数） 个不同的数字为止，这个停止的数字就是要淘汰的页号（最近最久未使用的页），
题中为页号2 。

## 2015-Q28

> question_id: 2015-Q28
> explanation_status: scan
> answer_key: C

：

磁盘和内存的速度差异，决定了可以将内存经常访问的文件调入磁盘缓冲区，从高速缓存
中复制的访问比磁盘I/0的机械操作要快很多。

## 2015-Q29

> question_id: 2015-Q29
> explanation_status: scan
> answer_key: A

：

10个直接索引指针指向的数据块大小为lOxlK.B = 10KB。
每个索引指针占4B, 则每个磁盘块可存放1KB/4B = 256个索引指针，一级索引指针指向
的数据块大小为256x1KB = 256KB, 二级索引指针指向的数据块大小为256x256x1K.B = i6 K.B = 
64MB。
按字节编址，偏移量为1234 时， 因1234B < 10KB, 则由直接索引指针可得到其所在的磁
盘块地址。文件的索引结点已在内存中，则地址可直接得到，故仅需l次访盘即可。
偏移量为307400时，因10KB + 256KB < 307400B < 64MB_, 可知该偏移量的内容在二级索
--- page 5 ---
引指针所指向 的某个磁盘块中， 索引结点已在内存中， 故先访盘2次得到文件所在 的磁盘块地
址，再访盘 1次即可读出内容， 故共需3次访盘。

## 2015-Q30

> question_id: 2015-Q30
> explanation_status: scan
> answer_key: B

：

对各进程进行固定分配时页面数不变， 不可能出现全局置换。而A、B 、D是现代操作系
统中常见的3种策略。

## 2015-Q31

> question_id: 2015-Q31
> explanation_status: scan
> answer_key: B

：

盘块号＝起始块号+L盘块号 /(1024x8)」=32 + L4o96121(1024x8)」=·32+ 50 = 82, 这里问的
是块内字节号而不是位号， 因此还需要除以8(1字节=8位）， 块内字节号= L(盘块号％
(1024x8))/8」 =1。

## 2015-Q32

> question_id: 2015-Q32
> explanation_status: scan
> answer_key: C

：

SCAN算法就是电梯调度算法。顾名思义， 如果开始时磁头向外移动就一直要到最外侧，
然后再返回向内侧移动，就 像电梯若往下则 一直要下到最底层需求才会再上升 一样。当期磁头
位于58号并从外侧向内侧移动，先依次访问1 30和 199, 然后再返回向外侧移动，依次访问42
和15, 故磁头移过的磁道数是：(199-58) + (199-15) = 325。

## 2015-Q33

> question_id: 2015-Q33
> explanation_status: scan
> answer_key: D

：

POP3建立在TCP连接上， 使用的是有连接可靠的数据传输服务。

## 2015-Q34

> question_id: 2015-Q34
> explanation_status: scan
> answer_key: B

：

NRZ是最简单的串行编码技术， 用两个电压来代表两个二进制数， 如高电平表示1, 低电
平表示 o, 题中编码1符合。NRZI则是用电平的一次翻转来表示1, 与前一个NRZI 电平相同
的电平表示0。曼彻斯特编码将 一个码元分成两个相等的间隔， 前一个间隔为低电平后 一个间
隔为高电平表示l; 0的 表示正好相反， 题中编码2符合。

## 2015-Q35

> question_id: 2015-Q35
> explanation_status: scan
> answer_key: A

：

不考虑确认帧的开销， 一个帧发送完后经过一个单程传播时延到达接收方， 再经过一个单
程传播时延发送 方收到应答， 从而继续发送。要使得传输效率最大化， 就是不用等确认也可以
连续发送多个帧。设连续发送n个帧， 一个帧的发送时 延为1000B/128kbps= 62.5ms。对于采用
滑动窗口协议的流水线机制，我们有如下公式：链路利用率 =(nx发送时延） /(RTT+发送时延）。
依题意， 有(nx62.5ms)/(62.5ms+ 250msx2)�80%, 得 n� 7.2, 帧序号的比特数K需要满足
2k �n+ 1。从而， 帧序号的比特数至少为4。

## 2015-Q36

> question_id: 2015-Q36
> explanation_status: scan
> answer_key: null

：

CSM幻CD适用于有线网络， 而CSMA/CA则 广泛应用于无线局域网。其他选项关于
CSMA/CD的描述都是正确的。

## 2015-Q37

> question_id: 2015-Q37
> explanation_status: scan
> answer_key: null

：

从本质上说，交换机就是 一个多 端口的网桥CA正确）， 工作在数据链路层（因此不能实现
不同网络层协议的网络互联，D错误）， 交换机能经济地将网络分成小的冲突域CB错误）。广
播域属千网络层概念， 只有网络层设备（如路由器）才能分割广播域CC错误）。

## 2015-Q39

> question_id: 2015-Q39
> explanation_status: scan
> answer_key: null

：

发送窗口的上限值=min[接收窗口，拥塞窗口］。4个RTT后，乙收到的数据全部存入缓存，
不被取走， 接收窗口只剩下1KB (16-1-2-4-8= 1)缓存， 使得甲的发 送窗口为1KB。
--- page 6 ---

## 2015-Q40

> question_id: 2015-Q40
> explanation_status: scan
> answer_key: null

：

Connection: 连接方式， Close 表明为非持续连接方式， keep-alive 表示持续连接方式。 Cookie
值是由服务器产生的， HTTP 请求报文中有 Cookie 报头表示曾经访问过 www.test.edu.cn 服务器。
二、 综合应用题
41. 解答：
1)算法的基本设计思想
算法的核心思想是用空间换时间。 使用辅助数组记录链表中已出现的数值， 从而只需对链
表进行一趟扫描。
因为ldatal�n, 故辅助数组 q 的大小为 n + 1, 各元素的初值均为 0 。依次扫描链表中的各
结点， 同时检查 q[ldatal]的值， 如果为 o, 则保留该结点， 并令 q[jdatal] = 1; 否则，将该结点从
链表中删除。
2) 使用 C 语言描述的单链表结点的数据类型定义
typedef struct node {
1.nt data; 
struct node *link; 
}NODE; 
Typedef NODE *PNODE; 
3)算法实现
void func (PNODE h,int n)
PNODE p=h,r; 
int *q,m; 
q=(int *)malloc(sizeof(int)*(n+l)); //申请n+l 个位置的辅助空间
for(int i =O;i<n+l;i++) · //数组元素初值置 0
*(q+i)=O; 
while(p->link!=NULL) 
｛ 
m=p->link->data>O? p->link->data:-p->link->data; 
if(*(q+m) ==O) II判断该结点的 data 是否已出现过
｛ 
*(q+m) =l; 
p=p->link; 
else 
r=p->link; 
p->link=r->link 
free (r); 
fre.e (q); 
II首次

