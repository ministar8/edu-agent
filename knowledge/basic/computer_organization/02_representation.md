# 数据表示与运算

> domain_kp: co.representation
> document_id: basic-co-representation
> kb_depth: basic
> doc_role: textbook

## 学习目标

- 理解定点数的编码方式
- 理解补码的动机与运算特点
- 理解浮点数 IEEE754 的表示思想

---

## 定点数表示

> section_id: basic-co-representation-fixed_point
> kp_ids: [co.representation.fixed_point]
> primary_kp: co.representation.fixed_point

**定义**：小数点位置固定的数的表示（纯整数或纯小数）。

**为什么**：硬件需确定「符号如何编码、数值位如何解释」。

**编码**：原码、反码、补码、移码——差别在符号位与数值位的关系，以及 0 的个数、加减是否统一。

---

## 补码

> section_id: basic-co-representation-complement
> kp_ids: [co.representation.complement]
> primary_kp: co.representation.complement

**定义**：补码将负数表示为「模减去其绝对值」在位向量上的结果；加减法可统一用加法实现。

**为什么**：原码加减要判断符号与绝对值，电路复杂；补码使**加减法电路统一**。

**性质**：

- 0 的表示唯一
- 负数范围可比正数多表示一个最小负数
- 溢出不等于「进位」，需单独判溢出

**思想**：用**同余**把减法变成加法，减少硬件分支。

---

## 整数运算与溢出

> section_id: basic-co-representation-integer_op
> kp_ids: [co.representation.integer_op, co.representation.overflow]
> primary_kp: co.representation.overflow

**机制**：补码加减按位加/加反码+1；乘除有原码一位乘、补码乘等实现路径。

**溢出**：结果超出该位数可表示范围。

**为什么**：无符号与有符号对同一比特串的「进位/溢出」语义不同。

**判定思想**：有符号溢出看**符号位进位与次高位进位是否一致**（或双符号位），不能只看「有无进位」。

---

## 浮点数 IEEE754

> section_id: basic-co-representation-ieee754
> kp_ids: [co.representation.ieee754]
> primary_kp: co.representation.ieee754

**定义**：浮点数拆为符号、阶码（指数）、尾数，形如 N = (−1)^S × M × 2^E。

**为什么**：扩大可表示范围，并在阶码与精度之间折中。

**机制**：

- 单精度：1 符号 + 8 阶 + 23 尾数；阶用移码，尾数用原码规格化
- 隐藏位：规格化后最高位 1 不显式存储，多换 1 位精度
- 特殊值：±0、±∞、NaN

**思想**：**科学计数法的硬件化**；阶码管范围，尾数管精度，二者独立编码。
