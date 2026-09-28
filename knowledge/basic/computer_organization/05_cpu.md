# 中央处理器

> domain_kp: co.cpu
> document_id: basic-co-cpu
> kb_depth: basic
> doc_role: textbook

## 学习目标

- 理解数据通路与控制器的分工
- 理解指令流水的加速原理与冒险
- 理解中断/异常的响应机制

---

## 数据通路

> section_id: basic-co-cpu-datapath
> kp_ids: [co.cpu.datapath]
> primary_kp: co.cpu.datapath

**定义**：执行指令所需的数据寄存器、ALU、总线与连接的集合。

**为什么**：把「取指—译码—执行—访存—写回」变成可并行或分时的硬件路径。

---

## 控制器

> section_id: basic-co-cpu-controller
> kp_ids: [co.cpu.controller]
> primary_kp: co.cpu.controller

**定义**：产生控制信号序列，协调数据通路完成指令（硬布线 / 微程序）。

**为什么**：指令步骤必须有序、与数据通路节拍对齐。

**思想**：控制单元是「时序的指挥者」；硬布线重速度，微程序重灵活与规整。

---

## 指令流水线

> section_id: basic-co-cpu-pipeline
> kp_ids: [co.cpu.pipeline]
> primary_kp: co.cpu.pipeline

**定义**：把指令执行拆成多阶段，多条指令在不同阶段重叠执行。

**为什么**：提高**吞吐率**；单条延迟不降甚至略升，但单位时间完成更多指令。

**机制**：

- 阶段划分要相对均匀，否则慢段成为瓶颈
- 理想吞吐接近每周期 1 条

**思想**：**重叠执行**换吞吐；代价是阶段间的传递与同步。

---

## 流水线冒险

> section_id: basic-co-cpu-pipeline_hazard
> kp_ids: [co.cpu.pipeline_hazard]
> primary_kp: co.cpu.pipeline_hazard

**定义**：使流水无法继续按理想节奏推进的依赖与冲突。

**分类思想**：

- 结构冒险：资源争用
- 数据冒险：后续指令需要前序尚未写回的数据
- 控制冒险：转移是否改变取指方向不确定

**为什么**：并行后指令间的语义约束变成硬件必须处理的问题。

---

## 停顿与转发

> section_id: basic-co-cpu-pipeline_stall
> kp_ids: [co.cpu.pipeline_stall]
> primary_kp: co.cpu.pipeline_stall

**机制**：转发（旁路）把前序结果尽早送到后续阶段；无法解决则插入停顿（气泡）。

**思想**：用**旁路网络**减少等待；剩余的依赖用时间换正确性。

---

## 中断与异常

> section_id: basic-co-cpu-exception
> kp_ids: [co.cpu.exception]
> primary_kp: co.cpu.exception

**定义**：打断正常指令流去处理突发事件或错误，再返回或跳转。

**机制**：识别来源、保存现场、跳处理程序、恢复或结束。

**思想**：**异步事件的同步接口**；CPU 与外设、错误处理解耦。
