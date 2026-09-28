# 栈和队列

> domain_kp: ds.stack_queue
> document_id: basic-ds-stack_queue
> kb_depth: basic
> doc_role: textbook

## 学习目标

- 理解栈与队列的受限访问语义
- 理解顺序与链式实现如何满足该语义
- 理解循环队列解决的问题

---

## 栈

> section_id: basic-ds-stack_queue-stack
> kp_ids: [ds.stack_queue.stack]
> primary_kp: ds.stack_queue.stack

**定义**：只能在同一端进行插入与删除的线性表（后进先出 LIFO）。

**为什么**：许多过程天然「后开始的先结束」——函数调用、括号匹配、深度优先、表达式求值。

**机制**：

- 栈顶指针指示可操作端
- 进栈先写数据再移动栈顶；出栈相反
- 可顺序存储也可链式存储

**思想**：用**访问受限**换取与「嵌套/回退」语义对齐；不是数据变少，而是约束更贴问题。

---

## 栈应用：括号匹配

> section_id: basic-ds-stack_queue-match
> kp_ids: [ds.stack_queue.match, ds.stack_queue.stack]
> primary_kp: ds.stack_queue.match

**基本思想**：左括号入栈；遇右括号与栈顶匹配并出栈；结束时栈空则匹配成功。

**为什么**：括号嵌套与栈的 LIFO 一一对应——最近未闭合的左括号应最先被右括号闭合。

**特点**：

- 只存「尚未闭合」的左括号即可
- 失配时分：右括号无对应左括号、类型不匹配、结束时栈非空

---

## 队列

> section_id: basic-ds-stack_queue-queue
> kp_ids: [ds.stack_queue.queue]
> primary_kp: ds.stack_queue.queue

**定义**：只在一端插入、另一端删除的线性表（先进先出 FIFO）。

**为什么**：与「到达顺序处理」一致——任务排队、广度优先、缓冲、打印队列。

**机制**：

- 队头出、队尾进
- 链式实现可天然两端操作
- 顺序实现若不处理「假溢出」，队头出队后的空位无法复用

---

## 循环队列

> section_id: basic-ds-stack_queue-circular_queue
> kp_ids: [ds.stack_queue.circular_queue]
> primary_kp: ds.stack_queue.circular_queue

**定义**：把顺序队列的存储空间视为环，下标取模回绕。

**为什么**：复用出队后的空间，避免整体搬移或频繁扩容。

**机制**：

- front / rear 在环上移动
- 区分空与满：牺牲一个单元、加计数器、或标志位
- 入队出队均为 O(1)

**思想**：用**环形下标**把「线性逻辑」映射到固定数组，是逻辑结构与物理结构分离的典型例子。
