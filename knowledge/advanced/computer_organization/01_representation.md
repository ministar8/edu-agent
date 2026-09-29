# 数据表示与运算 · 解题能力

> domain_kp: co.representation
> document_id: advanced-co-representation
> kb_depth: advanced
> doc_role: method

## 本章解决什么

- 补码/移码转换与范围
- 溢出判断
- IEEE754 编码与规格化
- 定点加减与位运算

---

## 补码转换与表示范围

> section_id: advanced-co-representation-complement
> kp_ids: [co.representation.complement, co.representation.fixed_point]
> primary_kp: co.representation.complement
> topic_tags: [计算, 选择]
> scope: single
> difficulty: 2

**识别信号**：给十进制/原码/反码求补码，或问 n 位补码表示范围。

**方法步骤**：

1. **正数**：原反补相同  
2. **负数**：原→反（符号位外取反）→补（末位+1）；或「除符号位外取反加 1」  
3. **范围**：n 位补码 `−2^{n-1} ~ 2^{n-1}−1`；原码对称少表示一个负数  
4. 互逆：补码再求补得到原码（符号位不动）  

**易错点**：

- 把 `−0` 当补码独立码点  
- n 位含不含符号位写错  
- 十六进制转补码时按无符号处理  

**变式**：求 `−1` 的十六进制补码；给位串求真值。

---

## 溢出判断

> section_id: advanced-co-representation-overflow
> kp_ids: [co.representation.overflow, co.representation.integer_op]
> primary_kp: co.representation.overflow
> topic_tags: [计算, 分析]
> scope: single
> difficulty: 2

**识别信号**：加减后是否溢出；用双符号位/V 判断；结果范围。

**方法步骤**：

1. **一位符号位**：同号相加、结果变号 → 溢出  
2. **双符号位**：两位不同 → 溢出  
3. **V 标志**：`V = C_n xor C_{n-1}`（进位异或）  
4. 无符号数与有符号数溢出条件不同，分开答  

**易错点**：

- 无符号进位与有符号溢出混用  
- 减法先转加法（加相反数）再判  
- 只看结果符号不看操作数符号  

**变式**：给 A、B 求 A+B 并判溢出；比较无符号/有符号解释。

---

## IEEE754 浮点

> section_id: advanced-co-representation-ieee754
> kp_ids: [co.representation.ieee754]
> primary_kp: co.representation.ieee754
> topic_tags: [计算, 选择]
> scope: single
> difficulty: 3

**识别信号**：浮点机器数 ↔ 真值；规格化；阶码范围。

**方法步骤**：

1. **单精度**：1+8+23；阶码偏置 127；尾数隐藏 1  
2. **真值 → 机器数**：写科学计数法 → 调整阶码 → 偏置阶 → 拼符号  
3. **机器数 → 真值**：拆符号/阶/尾，还原 `1.m × 2^{E-127}`  
4. **特殊**：全 0 阶全 0 尾 = 0；全 1 阶 = Inf/NaN  

**易错点**：

- 隐藏位忘加 1  
- 偏置值 127 与移码范围混  
- 小数点位置与右规/左规搞反  

**变式**：两浮点数比较；给十六进制机器数求真值；判断能否精确表示 0.1。

---

## 定点加减与移位

> section_id: advanced-co-representation-integer_op
> kp_ids: [co.representation.integer_op, co.representation.fixed_point]
> primary_kp: co.representation.integer_op
> topic_tags: [计算, 代码]
> scope: single
> difficulty: 2

**识别信号**：补码加减步骤、算术移位结果、乘除加符号位处理。

**方法步骤**：

1. **补码加减**：`[A]+[B]` 或 `[A]+[−B]`，符号位参与运算  
2. **算术左移**：低位补 0，高位丢出需判溢出  
3. **算术右移**：补符号位  
4. **乘法**：原码一位乘符号单独异或；补码 Booth 看末位  

**易错点**：

- 移位与逻辑移位混用（负数右移）  
- 加减时符号位进位当溢出  
- 乘法部分积符号扩展错  

**变式**：求移位后真值；手工 Booth 乘法一轮。
