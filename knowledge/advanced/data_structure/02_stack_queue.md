# 栈和队列 · 解题能力

> domain_kp: ds.stack_queue
> document_id: advanced-ds-stack_queue
> kb_depth: advanced
> doc_role: method

## 本章解决什么

- 出栈序列合法性判断
- 循环队列空满与容量
- 括号/表达式匹配
- 栈与队列互相实现

---

## 出栈序列合法性

> section_id: advanced-ds-stack_queue-pop_order
> kp_ids: [ds.stack_queue.stack]
> primary_kp: ds.stack_queue.stack
> topic_tags: [选择, 分析]
> scope: single
> difficulty: 2

**识别信号**：给入栈序列 `a,b,c…`，问哪些出栈序列可能/不可能。

**方法步骤**：

1. **模拟法**：按出栈序列逐个匹配，需要则压入未入元素，栈顶相同则弹出  
2. **排除法**：某元素出栈时，比它大且后出现的必须仍保持相对顺序（可画栈图）  
3. 合法序列等价于：对任意 i<j<k，出栈中不允许出现 `…k…i…j…` 这种「逆序对破坏栈序」模式  
4. 求所有合法序列数：Catalan 数 `C(2n,n)/(n+1)`（n 个元素）  

**易错点**：

- 「最后入栈一定最先出」不成立，只是若后出需中途弹出  
- 只比较相邻两数不够，要模拟完整过程  
- 与队列 FIFO 混淆  

**变式**：给操作序列 Push/Pop 求出栈结果；合法序列计数。

---

## 循环队列空满与运算

> section_id: advanced-ds-stack_queue-circular_queue
> kp_ids: [ds.stack_queue.circular_queue, ds.stack_queue.queue]
> primary_kp: ds.stack_queue.circular_queue
> topic_tags: [代码, 计算]
> scope: single
> difficulty: 2

**识别信号**：循环队列 `front/rear`，判空/判满、求元素个数、写入队出队。

**方法步骤**：

1. **牺牲一个单元**：空 `front == rear`；满 `(rear+1)%M == front`；元素数 `(rear-front+M)%M`  
2. **计数器 size**：空 `size==0`；满 `size==M`  
3. **标记 tag**：空满都可 `front==rear`，用 tag 区分  
4. 入队：`Q[rear]=x; rear=(rear+1)%M`；出队：`x=Q[front]; front=(front+1)%M`  

**易错点**：

- 满判定写成 `rear == M`（忘记取模）  
- 元素个数公式对「牺牲单元」与「计数器」方案不同  
- `front` 指向队头元素还是队头前一空位，约定不同公式不同  

**变式**：求队列长度；两栈共享数组；输出非法状态判断。

---

## 括号匹配与表达式求值

> section_id: advanced-ds-stack_queue-match_eval
> kp_ids: [ds.stack_queue.match, ds.stack_queue.stack]
> primary_kp: ds.stack_queue.match
> topic_tags: [代码, 分析]
> scope: single
> difficulty: 2

**识别信号**：括号/引号匹配，中缀转后缀，后缀表达式求值。

**方法步骤**：

1. **括号匹配**：左括号入栈，右括号判栈顶是否同类；结束时栈空  
2. **中缀→后缀**：操作数直接输出；运算符栈按优先级弹出；括号特判  
3. **后缀求值**：遇数入栈，遇运算符弹两数运算再入栈  
4. 中缀求值可两栈（操作数栈+运算符栈）  

**易错点**：

- 同类括号优先级表背错（`^` 右结合等）  
- 表达式非法（缺操作数/括号不配）未检测  
- 一元负号与二元减号区分  

**变式**：前缀表达式求值；给出中缀画求值栈快照。

---

## 用队列实现栈 / 用栈实现队列

> section_id: advanced-ds-stack_queue-implement
> kp_ids: [ds.stack_queue.stack, ds.stack_queue.queue]
> primary_kp: ds.stack_queue.stack
> topic_tags: [代码, 分析]
> scope: cross
> difficulty: 3

**识别信号**：只允许栈实现队列（或反之），分析入队/出队复杂度。

**方法步骤**：

1. **双栈实现队列**：入队压 `in`；出队若 `out` 空则把 `in` 全倒入 `out` 再弹；均摊 O(1)  
2. **双队列实现栈**：入栈进主队；出栈把主队前 n-1 个倒入辅助队，弹队尾  
3. 复杂度题要写**均摊**还是**最坏**  

**易错点**：

- 倒栈/倒队时机弄反导致顺序错  
- 只分析单次操作最坏，忽略均摊  
- 用双端队列当栈写入题  

**变式**：用一个队列实现栈；最小栈（辅助栈存最小值）。
