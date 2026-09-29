# 流水线 · 解题能力

> domain_kp: co.cpu
> document_id: advanced-co-pipeline
> kb_depth: advanced
> doc_role: method

## 本章解决什么

- 流水线时空图与加速比
- 三种冒险识别与处理
- 转发/停顿对 CPI 影响
- 中断与流水线

---

## 流水线周期与加速比

> section_id: advanced-co-pipeline-throughput
> kp_ids: [co.cpu.pipeline]
> primary_kp: co.cpu.pipeline
> topic_tags: [计算, 选择]
> scope: single
> difficulty: 2

**识别信号**：求流水线时间、加速比、吞吐率；画时空图。

**方法步骤**：

1. **周期** Δt = max(段时) + 流水寄存器延迟（若题给）  
2. **n 条指令**：`T = (k + n − 1) × Δt`  
3. **加速比** `S = T_串行 / T_流水`  
4. 吞吐率 `TP = n / T`  

**易错点**：

- 指令数 n 与段数 k 混  
- 加速比不等于段数（指令多时趋近 k）  
- 理想流水与实际（有冒险）分开  

**变式**：非均匀段时求周期；超流水/超标量对比。

---

## 数据相关与旁路

> section_id: advanced-co-pipeline-hazard
> kp_ids: [co.cpu.pipeline_hazard, co.cpu.pipeline_stall]
> primary_kp: co.cpu.pipeline_hazard
> topic_tags: [分析, 计算]
> scope: single
> difficulty: 3

**识别信号**：判断 RAW/WAR/WAW；能否用转发；插入气泡个数。

**方法步骤**：

1. **RAW**：后用先写；真相关  
2. **WAR/WAW**：乱序才有的名相关；顺序流水少  
3. **算术逻辑**后接 ALU：EX→EX 转发可免停顿  
4. **Load-Use**：至少停 1 拍（MEM 后才可用）  

**易错点**：

- Load-Use 与普通数据相关处理一样  
- 把分支相关当数据相关  
- 转发仍需比较前递路径是否在时钟内  

**变式**：给指令序列画停顿/转发；求 CPI 与加速比。

---

## 控制相关与中断

> section_id: advanced-co-pipeline-control
> kp_ids: [co.cpu.pipeline_hazard, co.cpu.exception]
> primary_kp: co.cpu.pipeline_hazard
> topic_tags: [分析, 选择]
> scope: single
> difficulty: 3

**识别信号**：分支预测失败代价；中断响应与精确异常。

**方法步骤**：

1. **分支冒险**：预测错则冲刷已取指；延迟槽可吸收部分代价  
2. **中断**：执行完当前指令后检测（或按段）  
3. **精确异常**：异常前指令完成，后指令不保留  

**易错点**：

- 中断嵌套与流水线冲刷范围  
- 把异常当子程序调用  
- 分支延迟槽填错指令  

**变式**：求预测失败时的 CPI；说明如何实现精确中断。
