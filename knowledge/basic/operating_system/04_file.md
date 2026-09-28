# 文件管理

> domain_kp: os.file
> document_id: basic-os-file
> kb_depth: basic
> doc_role: textbook

## 学习目标

- 理解文件逻辑与物理结构
- 理解目录与空闲空间管理
- 理解磁盘调度的动机

---

## 文件逻辑与物理结构

> section_id: basic-os-file-logical
> kp_ids: [os.file.logical, os.file.physical]
> primary_kp: os.file.physical

**逻辑**：流式或记录式；用户看到的文件组织。

**物理**：文件在外存如何存放——顺序、链接、索引。

**思想**：逻辑抽象与物理布局解耦；结构影响随机访问与扩展成本。

---

## 文件分配方式

> section_id: basic-os-file-alloc
> kp_ids: [os.file.alloc]
> primary_kp: os.file.alloc

**顺序**：连续块，访问快，易碎片。

**链接**：离散块用指针串，无外碎，随机访问差。

**索引**：索引块记地址，随机访问好；大文件需多级索引。

**思想**：**索引换随机访问**；大文件用层次化索引扩展。

---

## 目录管理

> section_id: basic-os-file-dir
> kp_ids: [os.file.dir]
> primary_kp: os.file.dir

**问题**：命名、组织、检索文件。

**思想**：目录是「名字→文件控制块」的映射；树形/无环图目录支持层次与共享。

---

## 磁盘空闲空间管理

> section_id: basic-os-file-disk_free_space
> kp_ids: [os.file.disk_free_space]
> primary_kp: os.file.disk_free_space

**问题**：记录哪些块空闲，供分配使用。

**机制思想**：

- **空闲表/位图**：适合顺序与快速扫描
- **空闲链表**：适合大规模简单维护
- **成组链接**：大文件系统下压缩表项

---

## 磁盘调度

> section_id: basic-os-file-disk_schedule
> kp_ids: [os.file.disk_schedule]
> primary_kp: os.file.disk_schedule

**问题**：磁头移动寻道顺序如何安排。

**动机**：寻道时间占比高，调度直接影响吞吐与响应。

**思想**：SSTF、SCAN、C-SCAN 等在「平均寻道」与「公平」间取舍；SSD 无寻道后意义变化。
