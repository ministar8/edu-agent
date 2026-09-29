# 存储与 Cache · 解题能力

> domain_kp: co.storage
> document_id: advanced-co-storage
> kb_depth: advanced
> doc_role: method

## 本章解决什么

- Cache 映射与地址划分
- 命中率与 AMAT
- 替换/写策略
- 多体交叉与虚拟存储

---

## Cache 地址划分与映射

> section_id: advanced-co-storage-cache_mapping
> kp_ids: [co.storage.cache_mapping, co.storage.cache]
> primary_kp: co.storage.cache_mapping
> topic_tags: [计算, 分析]
> scope: single
> difficulty: 3

**识别信号**：给地址位数、块大小、Cache 容量，求标记/组号/块内地址位数。

**方法步骤**：

1. **直接映射**：地址 = 标记 + 行号 + 块内；行数 = C/B  
2. **全相联**：标记 = 块号；组号无  
3. **组相联**：地址 = 标记 + 组号 + 块内；组数 = 行数/路数  
4. 位数：块内 `log2 B`，行/组号 `log2(行数或组数)`，剩余为标记  

**易错点**：

- 组数与行数混（r 路组相联）  
- 按字节还是按字编址  
- 标记位忘了减  

**变式**：判断命中某地址在第几行；求标记位宽。

---

## 命中率与 AMAT

> section_id: advanced-co-storage-cache_amat
> kp_ids: [co.storage.cache, co.storage.hierarchy]
> primary_kp: co.storage.cache
> topic_tags: [计算, 选择]
> scope: single
> difficulty: 2

**识别信号**：求平均访问时间、比较两种 Cache 方案。

**方法步骤**：

1. **AMAT** = `t_cache + (1-h) × t_penalty`（或含多级）  
2. 多级：`AMAT = t1 + (1-h1)×(t2 + (1-h2)×t_mem)`  
3. 用命中率代入比较，注意时间单位一致  

**易错点**：

- 把缺失率当命中率  
- 惩罚时间含主存访问  
- 多级公式括号错  

**变式**：给访问序列算实际命中率；求达到某 AMAT 的 h。

---

## 替换与写策略

> section_id: advanced-co-storage-cache_replace_write
> kp_ids: [co.storage.cache_replace, co.storage.cache_write]
> primary_kp: co.storage.cache_replace
> topic_tags: [选择, 分析]
> scope: single
> difficulty: 2

**识别信号**：LRU/FIFO/OPT 替换哪一块；写回/写直达与一致性。

**方法步骤**：

1. **OPT**：换出未来最久不用  
2. **FIFO**：换出最早进入  
3. **LRU**：换出最久未使用  
4. **写直达**：同时写主存；**写回**：脏块换出才写  

**易错点**：

- LRU 与 FIFO 在序列题结果不同  
- 写回需脏位  
- 全相联才可任意替换，直接映射无选择  

**变式**：给访问串画 Cache 内容；比较缺页/缺失次数。

---

## 多体交叉与主存

> section_id: advanced-co-storage-main_memory
> kp_ids: [co.storage.main_memory, co.storage.hierarchy]
> primary_kp: co.storage.main_memory
> topic_tags: [计算, 选择]
> scope: single
> difficulty: 2

**识别信号**：低位交叉存取带宽、DRAM 刷新、容量扩展。

**方法步骤**：

1. **n 体低位交叉**：连续地址连续模块，可流水出字  
2. **带宽**与模 n 地址映射  
3. **容量扩展**：位扩展/字扩展/字位同时  
4. 存取周期与总线周期关系  

**易错点**：

- 低位交叉与高位交叉地址映射反  
- 字扩展时片选地址位  
- 把存储周期当存取时间  

**变式**：求最大带宽；算芯片数量。

---

## 层次存储与局部性

> section_id: advanced-co-storage-hierarchy_loc
> kp_ids: [co.storage.hierarchy, co.storage.cache]
> primary_kp: co.storage.hierarchy
> topic_tags: [分析, 选择]
> scope: single
> difficulty: 2

**识别信号**：局部性原理；层次结构动机；等效访问时间。

**方法步骤**：

1. **时间局部性**：最近访问再访问；**空间局部性**：邻近地址  
2. **层次**：寄存器→Cache→主存→辅存；容量↑ 速度↓ 成本↓  
3. **等效访问**看命中率加权  
4. 虚拟存储在主存–辅存，Cache 在 CPU–主存  

**易错点**：

- 局部性不是「一定」  
- 把虚存与 Cache 层次混  
- 多级 Cache 命中率是复合概率  

**变式**：说明循环程序局部性；算二级 Cache AMAT。

