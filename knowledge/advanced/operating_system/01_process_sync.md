# 进程同步 · 解题能力

> domain_kp: os.process
> document_id: advanced-os-process_sync
> kb_depth: advanced
> doc_role: method

## 本章解决什么

- 信号量与 PV 填空
- 经典同步问题模板
- 死锁判定与银行家

---

## 信号量 PV 填空

> section_id: advanced-os-process_sync-pv
> kp_ids: [os.process.pv, os.process.semaphore, os.process.sync]
> primary_kp: os.process.pv
> topic_tags: [代码, 分析]
> scope: single
> difficulty: 3

**识别信号**：给生产者消费者/读者写者代码填 P/V；求信号量初值。

**方法步骤**：

1. **互斥** `mutex=1`：临界区夹 P(mutex)/V(mutex)  
2. **同步** `empty=n, full=0`：先 P 资源再 P 互斥；顺序不能反  
3. 初值 = 可用资源数或空位数  
4. **死锁检查**：若 P 在 V 前且资源不够会阻塞  

**易错点**：

- P/V 顺序颠倒导致死锁  
- 互斥信号量初值写成 0  
- 忘记 V 导致饿死  

**变式**：填缺失的 P/V；判断是否死锁；改信号量语义。

---

## 经典同步问题

> section_id: advanced-os-process_sync-classic
> kp_ids: [os.process.classic_sync, os.process.sync]
> primary_kp: os.process.classic_sync
> topic_tags: [代码, 分析]
> scope: single
> difficulty: 3

**识别信号**：生产者消费者、哲学家、读者写者、睡眠理发师。

**方法步骤**：

1. **生产者消费者**：empty/full + mutex  
2. **读者写者**：readcount + rw_mutex + mutex  
3. **哲学家**：限制同时进餐人数 / 破环 / 奇偶拿筷  
4. 写清「同步关系」与「互斥关系」再写 PV  

**易错点**：

- 读者写者中 readcount 未互斥  
- 哲学家对称解会死锁  
- 用忙等替代信号量不满足题目要求  

**变式**：只给一个信号量实现；证明无死锁。

---

## 死锁与银行家

> section_id: advanced-os-process_sync-deadlock
> kp_ids: [os.process.deadlock, os.process.bankers]
> primary_kp: os.process.deadlock
> topic_tags: [计算, 分析]
> scope: single
> difficulty: 3

**识别信号**：资源分配图、安全序列、是否可分配某请求。

**方法步骤**：

1. **必要条件**：互斥、占有等待、不可剥夺、环路  
2. **安全序列**：Need 可满足则分配，试推进程  
3. **银行家**：Request ≤ Need 且 ≤ Available → 试分配看是否安全  
4. 不安全 ≠ 死锁，只是可能  

**易错点**：

- 把不安全当已死锁  
- Need/Allocation/Max 列读错  
- 环路不是有环就死锁（同类资源）  

**变式**：给矩阵求安全序列；求某请求能否满足。

---

## 处理机调度方法

> section_id: advanced-os-process_sync-schedule
> kp_ids: [os.process.schedule, os.process.state]
> primary_kp: os.process.schedule
> topic_tags: [计算, 分析]
> scope: single
> difficulty: 3

**识别信号**：FCFS/SJF/HRRN/时间片；平均周转/等待；甘特图。

**方法步骤**：

1. **FCFS**：简单，护航效应  
2. **SJF/SPF**：平均等待优；长作业可能饥饿  
3. **HRRN**：响应比 `(w+s)/s`，兼顾等待与运行  
4. **时间片轮转**：响应好；片大退化为 FCFS  
5. **多级反馈**：动态优先级与时间片  

**易错点**：

- 周转 vs 等待 vs 响应公式  
- 抢占与非抢占 SJF 结果不同  
- 并发与并行在单核上的区分  

**变式**：给到达时间画甘特图；求平均带权周转。

---

## 经典同步与 PV 扩展

> section_id: advanced-os-process_sync-classic_pv
> kp_ids: [os.process.classic_sync, os.process.pv, os.process.monitor]
> primary_kp: os.process.classic_sync
> topic_tags: [代码, 分析]
> scope: single
> difficulty: 3

**识别信号**：多类资源 PV；管程条件变量；写读者写者变体。

**方法步骤**：

1. **多重资源**：信号量数组；按序申请防死锁  
2. **读者写者**：读优先/写优先变体（计数与互斥组合）  
3. **管程**：条件变量 wait/signal；Hoare vs Mesa 语义  
4. **死锁避免**：资源有序分配；银行家预判  

**易错点**：

- signal 与 V 在管程/信号量中含义  
- 忙等用循环代替 P  
- 多个互斥锁嵌套顺序  

**变式**：改写 PV 防死锁；给伪代码填管程过程。

---

## 调度算法计算与选择

> section_id: advanced-os-process_sync-schedule_calc
> kp_ids: [os.process.schedule]
> primary_kp: os.process.schedule
> topic_tags: [计算, 分析]
> scope: single
> difficulty: 3

**识别信号**：平均周转/等待/带权周转；响应比；比较算法优劣。

**方法步骤**：

1. **完成时间**画甘特图  
2. **周转** = 完成 − 到达；**等待** = 周转 − 运行  
3. **带权周转** = 周转 / 运行；越接近 1 越公平  
4. **HRRN**：`R = (w+s)/s`，非抢占  

**易错点**：

- 等待不含运行时间  
- 抢占后重排队  
- 多核把并发当并行  

**变式**：给 5 作业求三指标；SJF vs FCFS 对比。

---

## 进程状态与转换

> section_id: advanced-os-process_sync-state
> kp_ids: [os.process.state, os.process.thread]
> primary_kp: os.process.state
> topic_tags: [选择, 分析]
> scope: single
> difficulty: 2

**识别信号**：三态/五态图；阻塞与就绪转换；线程模型。

**方法步骤**：

1. **三态**：就绪–运行–阻塞；创建/终止  
2. **阻塞→就绪**：I/O 完成中断；**不能**阻塞→运行  
3. **挂起**：就绪挂起/阻塞挂起（五态/七态）  
4. **线程**：共享地址空间；切换比进程轻  

**易错点**：

- 死锁是阻塞不是就绪  
- 线程仍共享打开文件表（进程级）  
- 状态转换触发事件记反  

**变式**：给事件序列画状态图；判转换是否可能。


