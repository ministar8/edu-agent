# 总线与 I/O · 解题能力

> domain_kp: co.bus
> document_id: advanced-co-bus_io
> kb_depth: advanced
> doc_role: method

## 本章解决什么

- 总线带宽计算
- 中断 / DMA / 通道流程
- I/O 编址与接口

---

## 总线带宽与定时

> section_id: advanced-co-bus_io-bandwidth
> kp_ids: [co.bus.bandwidth, co.bus.timing]
> primary_kp: co.bus.bandwidth
> topic_tags: [计算, 选择]
> scope: single
> difficulty: 2

**识别信号**：给总线宽度、频率、时钟，求带宽；同步/异步定时。

**方法步骤**：

1. **带宽** = 数据宽度 × 有效频率；或位数/传输时间  
2. **半周期/全周期**传数是否双倍要按题  
3. **同步**：公共时钟；**异步**：握手不互锁/半互锁/全互锁  

**易错点**：

- 把时钟频率直接当传输频率（忽略握手/周期）  
- 总线宽度与数据总线宽度混  
- 突发传输未乘首/后续代价  

**变式**：求一次块传所需时间；比较两总线方案。

---

## 中断方式 I/O

> section_id: advanced-co-bus_io-interrupt
> kp_ids: [co.io.interrupt_io, co.cpu.exception, co.io.interface]
> primary_kp: co.io.interrupt_io
> topic_tags: [分析, 选择]
> scope: single
> difficulty: 2

**识别信号**：中断响应流程、屏蔽字、中断向量表、与 DMA 对比。

**方法步骤**：

1. CPU 发启动指令 → 设备准备 → 中断请求 → 响应（执行完指令）  
2. **隐指令**：保存断点、关中断、跳向量  
3. **屏蔽字**决定是否可被嵌套  
4. 适用：低速设备；单位数据量小  

**易错点**：

- 响应时关中断时机  
- 中断向量是入口地址不是设备号  
- 与轮询、DMA 时间特性对比错  

**变式**：画多级中断时间线；求有效带宽。

---

## DMA 方式

> section_id: advanced-co-bus_io-dma
> kp_ids: [co.io.dma, co.io.interface]
> primary_kp: co.io.dma
> topic_tags: [计算, 分析]
> scope: single
> difficulty: 3

**识别信号**：周期挪用、DMA 与 CPU 访存冲突、计数器作用。

**方法步骤**：

1. **CPU 初始化**：内存地址、计数、方向  
2. **DMA 与 CPU 抢主存**：周期挪用 / 交替访问  
3. 传完中断 CPU  
4. 高速设备成块传  

**易错点**：

- DMA 不需要 CPU 但需要总线/访存周期  
- 挪用周期与 CPU 无关指令时序  
- 与通道方式范围混淆  

**变式**：求挪用次数；给设备速率算占用比。
