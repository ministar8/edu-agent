# 存储系统

> domain_kp: co.storage
> document_id: basic-co-storage
> kb_depth: basic
> doc_role: textbook

## 学习目标

- 理解存储层次的动机
- 理解 Cache 的映射、替换、写策略
- 理解虚拟存储的基本思想

---

## 存储层次

> section_id: basic-co-storage-hierarchy
> kp_ids: [co.storage.hierarchy]
> primary_kp: co.storage.hierarchy

**基本思想**：寄存器→Cache→主存→外存，速度递减、容量递增、位价递减。

**为什么**：CPU 与主存速度差持续存在；用少量快存挡住大部分访存。

**机制**：依靠**局部性**（时间局部、空间局部）把常用数据搬到上层。

---

## Cache

> section_id: basic-co-storage-cache
> kp_ids: [co.storage.cache]
> primary_kp: co.storage.cache

**定义**：位于 CPU 与主存之间的小容量高速存储，对软件透明。

**为什么**：命中时访存延迟接近 Cache；目标是提高命中率。

**机制**：主存块调入 Cache 行；地址划分标记/组号/块内地址；缺失时调块并可能替换。

---

## Cache 映射方式

> section_id: basic-co-storage-cache_mapping
> kp_ids: [co.storage.cache_mapping]
> primary_kp: co.storage.cache_mapping

**定义**：主存块可放到 Cache 哪些行的规则。

**思想**：

- **全相联**：任意行，灵活、冲突少，查找代价高
- **直接映射**：固定一行，硬件简单，冲突多
- **组相联**：折中——组间直接、组内全相联

**特点**：映射越灵活，同样容量下冲突失效越少，但查找与实现越复杂。

---

## 替换算法与写策略

> section_id: basic-co-storage-cache_replace_write
> kp_ids: [co.storage.cache_replace, co.storage.cache_write]
> primary_kp: co.storage.cache_write

**替换**（相联时）

**思想**：缺块且组满时选一行调出（如 LRU 等）；策略影响后续命中。

**写策略**

**问题**：写 Cache 后主存如何同步。

**机制思想**：

- **写直达**：同时写主存，一致性简单、总线压力大
- **写回**：置脏位，调出时写回，带宽省、一致性复杂

---

## 主存储器

> section_id: basic-co-storage-main_memory
> kp_ids: [co.storage.main_memory]
> primary_kp: co.storage.main_memory

**定义**：CPU 可直接寻址的工作存储（DRAM 等）。

**机制**：按地址译码读写；容量、带宽、延迟是核心参数。

**思想**：主存是 Cache 与外存之间的「工作集」所在地。

---

## 虚拟存储器

> section_id: basic-co-storage-virtual_memory
> kp_ids: [co.storage.virtual_memory]
> primary_kp: co.storage.virtual_memory

**定义**：把「逻辑地址空间」与「物理内存」解耦，使程序看到连续大空间。

**为什么**：物理内存有限且需多道程序共享；让编译与用户不关心实页位置。

**机制思想**：

- 地址转换（页表/段表）完成虚→实
- 不在内存则缺页，由系统调入
- 与 Cache 类似：映射、查找、替换，只是尺度更大、涉及磁盘
