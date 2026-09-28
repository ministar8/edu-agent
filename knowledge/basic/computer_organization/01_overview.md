# 计算机系统概述

> domain_kp: co.overview
> document_id: basic-co-overview
> kb_depth: basic
> doc_role: textbook

## 学习目标

- 理解计算机系统的层次与基本组成
- 理解性能度量的基本口径
- 理解冯·诺依曼结构的核心思想

---

## 计算机的基本组成

> section_id: basic-co-overview-organization
> kp_ids: []

**基本思想**：硬件由运算器、控制器、存储器、输入/输出组成；软件与硬件共同完成计算任务。

**为什么**：把「自动计算」拆成可独立改进的部件——存储、执行、交互。

**特点**：指令与数据同在存储器中；CPU 从存储器取指执行；I/O 与主机交换信息。

---

## 冯·诺依曼结构

> section_id: basic-co-overview-von_neumann
> kp_ids: [co.overview.von_neumann]
> primary_kp: co.overview.von_neumann

**定义**：以「存储程序」为核心的计算机组织方式：指令与数据以二进制存储，按地址顺序取指执行。

**为什么**：改变程序等于改变存储内容，机器无需重新接线即可换任务。

**机制**：

- 指令与数据用同一存储、可统一寻址
- 指令由操作码与地址码构成
- 以运算器/控制器为中心演进为以存储器为中心（现代组织）

**思想**：**存储程序**——「程序也是数据」，控制流与数据流在统一存储上耦合。

---

## 性能指标

> section_id: basic-co-overview-performance
> kp_ids: [co.overview.performance]
> primary_kp: co.overview.performance

**定义**：衡量计算机完成任务快慢与吞吐能力的量。

**口径**：

- **响应时间**（执行时间）：完成单个任务的时间
- **吞吐率**：单位时间完成的任务数
- **CPI**：每条指令平均时钟周期数
- **CPU 执行时间** = 指令数 × CPI × 时钟周期

**为什么**：同一程序在不同机器上的「感觉快慢」可能来自指令数、CPI 或主频的不同组合。

**思想**：性能是**乘积分解**；优化要指明落在哪一项，而不是笼统说「更快」。
