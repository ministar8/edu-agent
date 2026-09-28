# 进程管理

> domain_kp: os.process
> document_id: basic-os-process
> kb_depth: basic
> doc_role: textbook

## 学习目标

- 理解进程/线程与状态转换
- 理解调度与同步的基本问题
- 理解死锁的成因与避免思路

---

## 进程与线程

> section_id: basic-os-process-thread
> kp_ids: [os.process.thread]
> primary_kp: os.process.thread

**定义**：进程是资源分配与执行的基本实体（有独立地址空间）；线程是 CPU 调度的轻量执行流。

**为什么**：把「资源拥有」与「执行调度」拆开，提高并发粒度与切换效率。

---

## 进程状态与转换

> section_id: basic-os-process-state
> kp_ids: [os.process.state]
> primary_kp: os.process.state

**基本状态**：就绪、运行、阻塞（等待）。

**机制**：调度选中→运行；时间片完→就绪；等待事件→阻塞；事件完成→就绪。

**思想**：状态机刻画「能否立刻运行」与「在等什么」。

---

## 处理机调度

> section_id: basic-os-process-schedule
> kp_ids: [os.process.schedule]
> primary_kp: os.process.schedule

**问题**：在就绪队列中选择谁运行。

**思想**：吞吐、响应、公平、周转——不同策略侧重不同；抢占与否影响响应性。

---

## 进程同步

> section_id: basic-os-process-sync
> kp_ids: [os.process.sync]
> primary_kp: os.process.sync

**问题**：并发执行时对共享资源的访问要保持正确次序与互斥。

**为什么**：交错执行可能导致「与预期序列不一致」的结果（竞态）。

**机制思想**：互斥（临界区）与同步（前驱关系）是两个相关但不同的约束。

---

## 信号量与 PV

> section_id: basic-os-process-semaphore
> kp_ids: [os.process.semaphore, os.process.pv]
> primary_kp: os.process.semaphore

**定义**：信号量为可增减的整型量，配合 P（wait）/ V（signal）操作。

**思想**：用**计数与阻塞队列**表达资源可用量与等待关系；P 申请、V 释放。

**机制**：P 减到负则等待；V 唤醒等待者——互斥与同步都可由此编码。

---

## 管程与经典同步问题

> section_id: basic-os-process-monitor
> kp_ids: [os.process.monitor, os.process.classic_sync]
> primary_kp: os.process.classic_sync

**管程**：把共享数据与操作封装为带条件等待的临界对象，降低信号量误用。

**经典问题**：生产者消费者、哲学家进餐、读者写者——用有限缓冲、资源分配、读写并发等模型表达同步约束。

**思想**：同步问题的本质是**不变式 + 等待/唤醒规则**，工具只是表达方式。

---

## 死锁

> section_id: basic-os-process-deadlock
> kp_ids: [os.process.deadlock]
> primary_kp: os.process.deadlock

**定义**：一组进程互相持有对方所需资源并循环等待，都无法推进。

**成因**：互斥、占有并等待、不可剥夺、循环等待（必要条件）。

**处理思想**：预防（破坏条件）、避免（分配前判断安全）、检测+恢复、鸵鸟（忽略）。

---

## 银行家算法

> section_id: basic-os-process-bankers
> kp_ids: [os.process.bankers]
> primary_kp: os.process.bankers

**基本思想**：分配前试探「是否存在安全序列」，仅在安全时分配。

**为什么**：在允许互斥与等待的同时，避免进入不安全（可能死锁）状态。

**机制**：工作向量模拟可回收资源；能完成所有进程则安全。
