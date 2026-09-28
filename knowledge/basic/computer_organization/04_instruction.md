# 指令系统

> domain_kp: co.instruction
> document_id: basic-co-instruction
> kb_depth: basic
> doc_role: textbook

## 学习目标

- 理解指令格式与寻址方式
- 理解 ISA 的软件/硬件边界
- 理解 RISC 与 CISC 的设计取向

---

## 指令格式

> section_id: basic-co-instruction-format
> kp_ids: [co.instruction.format]
> primary_kp: co.instruction.format

**定义**：指令由操作码与地址码（及扩展字段）构成，规定「做什么」与「操作数在哪」。

**为什么**：操作种类与寻址能力要在「指令长度 / 灵活性 / 译码成本」间平衡。

**思想**：定长利于译码流水；变长利于编码密度——格式是机器语言与硬件的契约。

---

## 寻址方式

> section_id: basic-co-instruction-addressing
> kp_ids: [co.instruction.addressing]
> primary_kp: co.instruction.addressing

**定义**：形成操作数有效地址的方式（立即、直接、间接、寄存器、偏移、变址等）。

**为什么**：同一算法在不同数据布局下需要不同的地址形成路径。

**思想**：寻址是**地址计算的语义**；有效地址 ≠ 物理地址（若有虚拟存储）。

---

## ISA 与 RISC/CISC

> section_id: basic-co-instruction-isa
> kp_ids: [co.instruction.isa, co.instruction.risc_cisc]
> primary_kp: co.instruction.isa

**ISA**

**定义**：指令集体系结构——软件可见的指令、寄存器、数据类型、存储模型等契约。

**为什么**：是软件与硬件的分界面；同一 ISA 可有不同微结构实现。

**RISC / CISC**

**思想**：

- CISC：指令功能强、格式多、面向编译器简化
- RISC：指令规整、Load/Store 型、利于流水与优化

**特点**：取向不同，不能简单说「谁更快」；现代 CPU 常在 ISA 层做减法、在微结构层做加法。
