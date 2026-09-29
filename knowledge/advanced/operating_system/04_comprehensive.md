# 综合拆解 · 解题能力

> domain_kp: os
> document_id: advanced-os-comprehensive
> kb_depth: advanced
> doc_role: method

## 本章解决什么

- 同步 + 调度 + 内存综合题拆解
- 时间计算串用

---

## 系统综合拆解

> section_id: advanced-os-comprehensive-system
> kp_ids: [os.process.sync, os.memory.paging, os.process.schedule]
> primary_kp: os.process.sync
> topic_tags: [分析, 计算]
> scope: cross
> difficulty: 4

**识别信号**：一题含 PV、调度、地址转换或缺页。

**分析方法**：

1. **分问挂 KP**：同步？内存？调度？  
2. **定状态**：进程状态图 / 页表 / 就绪队列  
3. **分步算**：先正确性再时间  
4. **隔离中间结果**  

**易错点**：

- 同步与调度原因混（阻塞 vs 就绪）  
- 缺页次数与地址转换重复计  
- 综合题写成单一模板  

**变式**：给程序片段求完成时间与安全状态。

---

## 时间与吞吐串用

> section_id: advanced-os-comprehensive-timing
> kp_ids: [os.process.schedule, os.memory.virtual, os.file.disk_schedule]
> primary_kp: os.process.schedule
> topic_tags: [计算, 分析]
> scope: cross
> difficulty: 3

**识别信号**：周转时间、带权周转、I/O 等待与 CPU 利用。

**方法步骤**：

1. **周转** = 完成 − 到达；**带权** = 周转 / 运行  
2. 多队列/优先级影响平均等待  
3. I/O 与 CPU 交叠可提高利用率  

**易错点**：

- 周转与响应时间混  
- 忽略 I/O 阻塞  
- 用单核公式算多核  

**变式**：给到达序列画甘特图求平均周转。
