# 串

> domain_kp: ds.string
> document_id: basic-ds-string
> kb_depth: basic
> doc_role: textbook

## 学习目标

- 理解串作为特殊线性表的抽象
- 理解模式匹配问题的定义
- 理解 KMP 相对朴素匹配的思想跃迁

---

## 串的基本概念

> section_id: basic-ds-string-concept
> kp_ids: []

**定义**：串是元素为字符的线性表；主串与子串；串长。

**为什么**：文本处理中的匹配、查找、替换都建立在「子串位置」上。

**特点**：逻辑上仍是线性表，但算法关注「模式」而非单元素。

---

## 模式匹配

> section_id: basic-ds-string-match
> kp_ids: [ds.string.match]
> primary_kp: ds.string.match

**定义**：在主串中查找模式串第一次出现的位置（或全部位置）。

**朴素思想**：对齐后逐位比较，失配则模式后移一位，再从头比。

**为什么慢**：已比较过的前缀信息被丢弃，最坏可到 O(nm) 量级。

**要点**：改进方向是**利用已匹配前缀的结构**，避免无意义回退——这正是 KMP 的出发点。

---

## KMP 算法

> section_id: basic-ds-string-kmp
> kp_ids: [ds.string.kmp, ds.string.match]
> primary_kp: ds.string.kmp

**基本思想**：失配时主串指针不回退；根据模式自身的前后缀信息，决定模式右移多少。

**为什么**：已匹配的前缀隐含「模式开头与这段前缀后缀的重合关系」，可直接跳过必然失败的对齐。

**机制**：

- 对模式预处理出前缀（部分匹配）信息
- 比较中失配，按预处理表移动模式
- 主串只扫描一遍量级

**思想**：**把「模式自相似性」编译成表**，用预处理换匹配时的回溯减少。匹配问题的核心从「逐位试」变成「结构信息利用」。
