# 文件与磁盘 · 解题能力

> domain_kp: os.file
> document_id: advanced-os-file_disk
> kb_depth: advanced
> doc_role: method

## 本章解决什么

- 文件分配方式与存取
- 目录与索引结点
- 磁盘调度与访问时间
- 空闲空间管理

---

## 文件分配方式

> section_id: advanced-os-file_disk-alloc
> kp_ids: [os.file.alloc, os.file.physical]
> primary_kp: os.file.alloc
> topic_tags: [计算, 选择]
> scope: single
> difficulty: 2

**识别信号**：连续/链接/索引分配的随机访问、文件长度、开销。

**方法步骤**：

1. **连续**：随机存取快；外碎片；动态扩难  
2. **链接**：顺序存取；无外碎片；不能随机  
3. **索引**：支持随机；索引块开销；大文件多级索引  
4. 算访问磁盘次数：先算是否需读索引/ FAT  

**易错点**：

- 链接说成可随机  
- 索引分配算盘块时忘索引块  
- 与内存分配碎片类型混淆  

**变式**：求读某盘块 I/O 次数；选合适分配方式。

---

## 目录与 inode

> section_id: advanced-os-file_disk-dir
> kp_ids: [os.file.dir, os.file.logical]
> primary_kp: os.file.dir
> topic_tags: [计算, 分析]
> scope: single
> difficulty: 2

**识别信号**：目录项大小、文件数上限、硬链接软链接。

**方法步骤**：

1. **目录项** = 文件名 + inode 号；inode 存元数据与盘块指针  
2. 文件数上限由 inode 数决定  
3. **硬链接**同 inode；**软链**存路径  
4. 打开文件表：系统一张 + 每进程一张  

**易错点**：

- 目录项长度算文件名上限  
- 删除文件时链接计数  
- 打开文件表项删除时机  

**变式**：给目录项大小求最大文件名；比较两链接。

---

## 磁盘调度与访问时间

> section_id: advanced-os-file_disk-schedule
> kp_ids: [os.file.disk_schedule]
> primary_kp: os.file.disk_schedule
> topic_tags: [计算, 分析]
> scope: single
> difficulty: 3

**识别信号**：FCFS/SSTF/SCAN/CS-SCAN 移动距离；平均寻道。

**方法步骤**：

1. **访问时间** = 寻道 + 旋转延迟 + 传输  
2. **SSTF**：最短寻道优先；可能饿死  
3. **SCAN/LOOK**：电梯；到端折返或到最远请求折返  
4. **C-SCAN**：单向，回程不服务  

**易错点**：

- SCAN 是否到物理端点（LOOK 区别）  
- 磁头初始位置影响总距离  
- 只算寻道忽略旋转  

**变式**：给请求序列画路径；求平均寻道。

---

## 磁盘空闲空间

> section_id: advanced-os-file_disk-free
> kp_ids: [os.file.disk_free_space]
> primary_kp: os.file.disk_free_space
> topic_tags: [选择, 计算]
> scope: single
> difficulty: 2

**识别信号**：位示图、空闲表、空闲链表的适用与开销。

**方法步骤**：

1. **位示图**：一盘块一位；适合大容量  
2. **空闲表**：连续区间；适合连续分配  
3. **空闲链**：盘块/组链接  
4. 成本：内存占用 vs 释放/分配速度  

**易错点**：

- 位示图位与盘块对应  
- 空闲表项方向  
- 与 FAT 混淆  

**变式**：求位示图大小；给释放序列更新结构。

---

## 设备管理与缓冲

> section_id: advanced-os-file_disk-device_io
> kp_ids: [os.io.device, os.io.buffer, os.io.software]
> primary_kp: os.io.device
> topic_tags: [分析, 选择]
> scope: cross
> difficulty: 3

**识别信号**：缓冲区个数、SPOOLing、设备独立性、I/O 软件层次职责。

**方法步骤**：

1. **单/双缓冲**：单缓冲约 `max(C,T)+M`；双缓冲可重叠输入输出  
2. **循环缓冲**：多缓冲区轮转，平滑生产消费速度差  
3. **SPOOLing**：独占设备→共享；井+预输入+缓输出  
4. **设备独立性**：逻辑设备名→驱动映射，换物理设备不改用户程序  
5. **I/O 软件层**：用户层 → 设备独立软件 → 驱动 → 中断处理  

**易错点**：

- 双缓冲时间公式里通信与加工是否重叠  
- SPOOLing 把独占模拟成共享，不是真并行独占  
- 驱动属内核，库函数不等于系统调用  

**变式**：求缓冲个数与吞吐；判断是否设备独立；层次填空。

---

## I/O 控制方式与设备分配

> section_id: advanced-os-file_disk-io_control
> kp_ids: [os.io.device, os.io.software, co.io.interrupt_io]
> primary_kp: os.io.software
> topic_tags: [分析, 选择]
> scope: cross
> difficulty: 3

**识别信号**：程序查询/中断/DMA 对比；设备分配表；I/O 时间重叠。

**方法步骤**：

1. **查询**：CPU 忙等，利用率低；实现简单  
2. **中断**：每字/块中断一次；CPU 可并行其它进程  
3. **DMA/通道**：成块传；占用总线/内存周期，结束后中断  
4. **设备分配**：设备控制表 DCT → 控制器 → 通道；安全分配 vs 不安全  
5. **时间分析**：CPU 与 I/O 交叠提高系统吞吐  

**易错点**：

- 中断次数与数据量成正比  
- DMA 不等于完全不占 CPU（初始化/结束）  
- 独占设备分配不当会死锁  

**变式**：比较三方式 CPU 占用；画多进程 I/O 甘特图。

---

## 缓冲与假脱机计算

> section_id: advanced-os-file_disk-buffer_spool
> kp_ids: [os.io.buffer, os.io.device]
> primary_kp: os.io.buffer
> topic_tags: [计算, 选择]
> scope: single
> difficulty: 3

**识别信号**：单双缓冲时间；缓冲区个数与吞吐；SPOOLing 组件。

**方法步骤**：

1. **单缓冲**：`T ≈ max(C, T_in) + M`（块传输+处理串行化）  
2. **双缓冲**：输入与处理可重叠，`T ≈ max(C, T_in)` 量级  
3. **缓冲区个数 k**：提高并行度，但内存与切换开销上升  
4. **SPOOLing**：预输入 → 井 → 缓输出；独占→共享打印机模型  

**易错点**：

- 单缓冲公式里的 M（复制）是否计入  
- 双缓冲不是无限吞吐  
- 井是磁盘，不是内存缓冲  

**变式**：给 C/T 求吞吐；判断是否需要三缓冲。

---

## 设备独立性与驱动接口

> section_id: advanced-os-file_disk-device_indep
> kp_ids: [os.io.device, os.io.software]
> primary_kp: os.io.device
> topic_tags: [分析, 选择]
> scope: single
> difficulty: 2

**识别信号**：逻辑设备名；驱动与中断程序分工；设备无关 I/O 软件。

**方法步骤**：

1. **逻辑设备名 LUT**：用户用逻辑名，OS 映射物理设备  
2. **设备独立软件**：统一接口、缓冲、错误报告  
3. **驱动**：寄存器级操作、排队、中断入口  
4. **中断处理**：唤醒驱动/进程，完成收尾  

**易错点**：

- 把驱动写成用户库  
- 设备独立 ≠ 设备无关性能  
- spooling 与设备独立目标不同  

**变式**：分层职责配对；改设备是否改用户程序。



