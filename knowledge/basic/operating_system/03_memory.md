# 内存管理

> domain_kp: os.memory
> document_id: basic-os-memory
> kb_depth: basic
> doc_role: textbook

## 学习目标

- 理解内存分配与地址映射
- 理解分页与 TLB
- 理解虚拟内存与缺页机制

---

## 内存分配

> section_id: basic-os-memory-allocate
> kp_ids: [os.memory.allocate]
> primary_kp: os.memory.allocate

**问题**：把有限物理内存分给多个进程。

**思想**：连续分配简单但易碎片；离散分配把地址翻译成本换灵活性。

---

## 分区分配

> section_id: basic-os-memory-partition
> kp_ids: [os.memory.partition]
> primary_kp: os.memory.partition

**机制**：固定/动态分区；空闲区表 + 分配策略（首次适应、最佳、最坏等）。

**思想**：策略影响外部碎片与查找时间；紧凑是昂贵的补救。

---

## 分页管理

> section_id: basic-os-memory-paging
> kp_ids: [os.memory.paging]
> primary_kp: os.memory.paging

**定义**：把进程空间与物理内存都分成固定大小页/框，页表完成映射。

**为什么**：消除外部碎片，支持离散存放。

**机制**：逻辑地址 = 页号 + 页内偏移；页表项含框号与存取控制。

---

## TLB

> section_id: basic-os-memory-tlb
> kp_ids: [os.memory.tlb]
> primary_kp: os.memory.tlb

**定义**：页表项的高速缓存（快表），加速虚→实翻译。

**为什么**：每次访存都查页表会使有效访存翻倍。

**思想**：与 Cache 同类——**翻译路径上的高速小表**。

---

## 分段与段页式

> section_id: basic-os-memory-segmentation
> kp_ids: [os.memory.segmentation]
> primary_kp: os.memory.segmentation

**定义**：按逻辑模块分段，段长不等；或段内再分页（段页式）。

**为什么**：分页保护与共享以页为单位，逻辑信息不完整；分段更贴程序结构。

**思想**：分页偏「物理效率」，分段偏「逻辑保护」，段页式折中。

---

## 虚拟内存

> section_id: basic-os-memory-virtual
> kp_ids: [os.memory.virtual]
> primary_kp: os.memory.virtual

**定义**：进程看到比物理内存更大的地址空间；仅当前工作集在内存。

**为什么**：多进程并存 + 程序局部性 ⇒ 可只装需要的部分。

---

## 缺页与置换

> section_id: basic-os-memory-page_fault
> kp_ids: [os.memory.page_fault, os.memory.page_replace]
> primary_kp: os.memory.page_fault

**缺页**：访问页不在内存，陷入内核调页。

**置换**：内存满时选一页调出（如 LRU、FIFO、OPT 思想）。

**思想**：用**缺页中断**换更大的空间；算法目标是降低缺页次数，代价是页表与磁盘 I/O。
