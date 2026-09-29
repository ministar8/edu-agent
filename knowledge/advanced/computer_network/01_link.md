# 数据链路层 · 解题能力

> domain_kp: cn.datalink
> document_id: advanced-cn-link
> kb_depth: advanced
> doc_role: method

## 本章解决什么

- 停等 / 滑动窗口效率
- CRC 与海明
- CSMA/CD 与以太网
- 信道利用率

---

## 停等与滑动窗口

> section_id: advanced-cn-link-flow
> kp_ids: [cn.datalink.flow_control, cn.datalink.error_control]
> primary_kp: cn.datalink.flow_control
> topic_tags: [计算, 分析]
> scope: single
> difficulty: 3

**识别信号**：信道利用率、窗口大小、序号位数、后退 N/选择重传。

**方法步骤**：

1. **停等**：`U = T_data / (T_data + T_prop*2 + T_ack + T_proc)`  
2. **窗口 W**：连续发；`U ≤ min(1, W·T_data / RTT+T_data…)`  
3. **GBN**：出错重传后续；**SR**：只重传出错帧  
4. 序号位数 n ⇒ 循环序号空间；SR 窗口 ≤ 2^{n-1}  

**易错点**：

- 把单向传播延时当 RTT  
- 窗口与序号范围关系  
- 停等利用率公式忘确认帧时间  

**变式**：求最大窗口；给丢包算重传帧数。

---

## CRC 与海明

> section_id: advanced-cn-link-error
> kp_ids: [cn.datalink.error_control, cn.datalink.framing]
> primary_kp: cn.datalink.error_control
> topic_tags: [计算, 选择]
> scope: single
> difficulty: 2

**识别信号**：CRC 校验位、海明码位数与纠错能力。

**方法步骤**：

1. **CRC**：模 2 除；生成多项式 r 次则 r 校验位  
2. **海明**：`2^r ≥ m+r+1`；检错纠错能力  
3. 双向检查：CRC 检突发，海明检单位错  

**易错点**：

- 模 2 运算与算术减法混  
- 海明不等式写反  
- 最小码距与检/纠错能力  

**变式**：求校验位数；给码字判是否合法。

---

## CSMA/CD 与以太网

> section_id: advanced-cn-link-mac
> kp_ids: [cn.datalink.mac, cn.datalink.ethernet]
> primary_kp: cn.datalink.mac
> topic_tags: [计算, 选择]
> scope: single
> difficulty: 3

**识别信号**：最小帧长、争用期、冲突域/广播域、截断二进制指数。

**方法步骤**：

1. **争用期** = 2τ；**最小帧长** = 2τ × 数据率  
2. **退避**：r 取 0…2^k−1，k=min(n,10)  
3. **CSMA/CA**：IFS、退避；无线  
4. 交换机分冲突域；VLAN 分广播域  

**易错点**：

- 最小帧长单位 bit/byte  
- 冲突域与广播域  
- CD 与 CA 场景  

**变式**：求单向传播延时；问某局域网冲突域个数。

---

## 差错控制与流量控制综合

> section_id: advanced-cn-link-error_flow
> kp_ids: [cn.datalink.error_control, cn.datalink.flow_control]
> primary_kp: cn.datalink.flow_control
> topic_tags: [计算, 分析]
> scope: cross
> difficulty: 3

**识别信号**：停等/GBN/SR 重传帧数；窗口与序号；信道利用率。

**方法步骤**：

1. **停等**：超时重发当前帧；U = Tdata/(Tdata+2Tprop+…)  
2. **GBN**：出错重传 N 及之后；接收窗口=1  
3. **SR**：只重传出错帧；收发窗口均 >1；序号空间 ≥ 2W  
4. **利用率**：窗口饱和时 U→1；链路越长越需加大 W  

**易错点**：

- GBN 与 SR 重传个数不同  
- 序号循环与窗口关系  
- 忘记确认帧占时间  

**变式**：超时后重发几帧；求最小序号位数。

