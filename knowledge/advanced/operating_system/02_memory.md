# 内存管理 · 解题能力

> domain_kp: os.memory
> document_id: advanced-os-memory
> kb_depth: advanced
> doc_role: method

## 本章解决什么

- 地址转换与页表
- 页面置换与缺页率
- 分段/段页
- 虚存有效访问时间

---

## 页表地址转换

> section_id: advanced-os-memory-paging
> kp_ids: [os.memory.paging, os.memory.tlb]
> primary_kp: os.memory.paging
> topic_tags: [计算, 分析]
> scope: single
> difficulty: 3

**识别信号**：逻辑地址→物理地址；页表项位数；多级页表。

**方法步骤**：

1. 逻辑地址 = 页号 + 页内偏移  
2. 查页表得块号，物理 = 块号 + 偏移  
3. **多级页表**：页目录 + 页表；页表项含 PPN  
4. **TLB** 命中免访存页表  

**易错点**：

- 页大小与页号位数对数关系  
- 页表项含状态位，不是只 PPN  
- 逻辑/物理页号混用  

**变式**：求有效访问时间；算多级页表空间。

---

## 页面置换与缺页

> section_id: advanced-os-memory-replace
> kp_ids: [os.memory.page_replace, os.memory.page_fault]
> primary_kp: os.memory.page_replace
> topic_tags: [计算, 选择]
> scope: single
> difficulty: 3

**识别信号**：FIFO/LRU/OPT 缺页次数；Belady 异常。

**方法步骤**：

1. **OPT**：置换未来最久不用  
2. **LRU**：置换最久未用  
3. **FIFO**：可能 **Belady**（分配多缺页多）  
4. **Clock**：二次机会  

**易错点**：

- 初始页也算缺页（题是否要求）  
- LRU 与 FIFO 结果不同  
- Belady 只对 FIFO  

**变式**：给访问串算缺页率；比较算法。

---

## 分段与段页式

> section_id: advanced-os-memory-segmentation
> kp_ids: [os.memory.segmentation, os.memory.allocate]
> primary_kp: os.memory.segmentation
> topic_tags: [计算, 选择]
> scope: single
> difficulty: 2

**识别信号**：段表地址、段页式两级访存、共享保护。

**方法步骤**：

1. 逻辑 = 段号 + 段内（页号+偏移）  
2. **段页**：段表→页表→物理，三次访存（+TLB）  
3. 段共享以段为单位；页以页为单位  

**易错点**：

- 段页式访存次数  
- 段长不定与页长固定对比  
- 外碎片/内碎片归属写反  

**变式**：求地址转换步骤；比较分页分段。

---

## 虚存与有效访问时间

> section_id: advanced-os-memory-virtual
> kp_ids: [os.memory.virtual, os.memory.page_fault]
> primary_kp: os.memory.virtual
> topic_tags: [计算, 分析]
> scope: single
> difficulty: 3

**识别信号**：EAT、缺页率、工作集、抖动。

**方法步骤**：

1. **EAT** = `(1-p)×访存 + p×(缺页处理+访存)`  
2. 含 TLB 再分命中率  
3. **工作集**：窗口内活跃页；抖动 = 调页过于频繁  

**易错点**：

- EAT 公式漏缺页后的访存  
- 把虚拟容量当物理  
- 缺页与 TLB 缺失混  

**变式**：求 p 使 EAT 小于阈值；说明多道程序度。
