# 综合拆解 · 解题能力

> domain_kp: co
> document_id: advanced-co-comprehensive
> kb_depth: advanced
> doc_role: method

## 本章解决什么

- 多部件耦合题拆解
- 性能公式串用

---

## 多部件耦合拆解

> section_id: advanced-co-comprehensive-system
> kp_ids: [co.cpu.pipeline, co.storage.cache, co.representation.ieee754]
> primary_kp: co.cpu.pipeline
> topic_tags: [分析, 计算]
> scope: cross
> difficulty: 4

**识别信号**：一题同时涉及浮点运算、Cache、流水线或中断。

**分析方法**：

1. **拆问**：表示？访存？流水？  
2. **定接口**：地址格式、数据格式先固定  
3. **分步算**：先数据路径，再时间  
4. **核对单位**：ns / cycle / byte 一致  

**易错点**：

- 浮点格式与整型混算  
- Cache 缺失惩罚与流水停顿重复计  
- 忘记启动 I/O 的初始化开销  

**变式**：给混合程序求 CPI 与 AMAT。

---

## 性能公式串用

> section_id: advanced-co-comprehensive-performance
> kp_ids: [co.overview.performance, co.cpu.pipeline, co.storage.cache]
> primary_kp: co.overview.performance
> topic_tags: [计算, 选择]
> scope: cross
> difficulty: 3

**识别信号**：综合问 CPU 时间、MIPS、加速比。

**方法步骤**：

1. **CPU 时间** = IC × CPI × 时钟周期  
2. **AMAT** 影响有效 CPI：`CPI = CPI_base + 缺失率 × 惩罚`  
3. 改进加速比要算端到端  

**易错点**：

- MIPS 忽略指令数差异  
- 只优化局部最贵部件（Amdahl）  
- 把峰值当实际  

**变式**：两方案加速比；给缺失率求等效 CPI。

---

## 指令格式与寻址方式

> section_id: advanced-co-comprehensive-addressing
> kp_ids: [co.instruction.format, co.instruction.addressing]
> primary_kp: co.instruction.addressing
> topic_tags: [计算, 选择]
> scope: single
> difficulty: 3

**识别信号**：寻址方式有效地址；指令字长与地址范围；相对寻址转移。

**方法步骤**：

1. **有效地址 EA**：直接=形式地址 A；间接=(A)；寄存器=R；基址/变址组合  
2. **相对寻址**：`EA=(PC)+A`；转移范围与 A 位数、PC 自增有关  
3. **立即数**：操作数在指令中；无访存  
4. **格式**：定长/变长；操作码扩展；地址码位数 ↔ 可寻址范围  

**易错点**：

- 相对寻址 EA 与 PC 修改时机  
- 间接寻址多一次访存  
- 字节编址 vs 字编址影响位数  

**变式**：求可寻址范围；算转移指令目标地址。

---

## 处理器类型与 CPI

> section_id: advanced-co-comprehensive-cpi
> kp_ids: [co.cpu.pipeline, co.cpu.datapath]
> primary_kp: co.cpu.pipeline
> topic_tags: [计算, 分析]
> scope: cross
> difficulty: 3

**识别信号**：单周期/多周期/流水 CPI；加权平均 CPI。

**方法步骤**：

1. **单周期**：CPI=1，周期=最慢段  
2. **多周期**：CPI≈指令段数；周期短  
3. **流水**：理想 CPI=1；有冒险则 >1  
4. **加权** `CPI = Σ (CPIi × 比例i)`；再乘时钟周期  

**易错点**：

- 把加速比当 CPI 倒数  
- 忽略访存层次对 CPI 影响  
- 超标量仍写 CPI=1  

**变式**：给混合指令求 CPU 时间；两处理器对比。

---

## 寻址与指令综合

> section_id: advanced-co-comprehensive-addr_calc
> kp_ids: [co.instruction.addressing, co.instruction.format]
> primary_kp: co.instruction.format
> topic_tags: [计算, 分析]
> scope: cross
> difficulty: 3

**识别信号**：形式地址/有效地址；指令字长与寻址范围；PC 变化。

**方法步骤**：

1. **直接**：EA=A；范围由 A 位数决定  
2. **相对**：EA=(PC)+A；转移距离有限但位置无关  
3. **基址+变址**：EA=(BR)+A+(XR)；数组/表驱动  
4. **取指后 PC** 已指向下一指令，相对寻址以此为基准  

**易错点**：

- 相对寻址基准是「本条指令的 PC」  
- 间接多一层括号表示访存  
- 按字节编址时地址+1 还是 +字长  

**变式**：求目标地址；比较两种寻址代码长度。


