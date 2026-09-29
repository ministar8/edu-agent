# 传输层 · 解题能力

> domain_kp: cn.transport
> document_id: advanced-cn-transport
> kb_depth: advanced
> doc_role: method

## 本章解决什么

- TCP 三次握手/四次挥手
- 流量控制与拥塞窗口
- 序号确认与超时
- UDP 特点

---

## TCP 连接管理

> section_id: advanced-cn-transport-handshake
> kp_ids: [cn.transport.tcp_handshake, cn.transport.tcp]
> primary_kp: cn.transport.tcp_handshake
> topic_tags: [计算, 分析]
> scope: single
> difficulty: 3

**识别信号**：SYN/FIN 序号确认号计算；状态迁移；半连接。

**方法步骤**：

1. **握手**：SYN=1, seq=x → SYN-ACK, seq=y, ack=x+1 → ACK, ack=y+1  
2. **挥手**：FIN → ACK → FIN → ACK；TIME_WAIT 2MSL  
3. **确认号** = 期望下一个序号  
4. 传过数据序号递增按字节  

**易错点**：

- 确认号是「下一个要收」不是「已收」  
- SYN/FIN 占一个序号  
- 四次挥手保活与 TIME_WAIT 作用  

**变式**：给握手字段填空；求已传字节数。

---

## 流量控制与拥塞控制

> section_id: advanced-cn-transport-congestion
> kp_ids: [cn.transport.tcp_flow, cn.transport.tcp_congestion]
> primary_kp: cn.transport.tcp_congestion
> topic_tags: [计算, 分析]
> scope: single
> difficulty: 3

**识别信号**：rwnd/cwnd 窗口增长；慢启动拥塞避免；快重传。

**方法步骤**：

1. 发送窗口 = min(rwnd, cwnd)  
2. **慢启动**指数涨到 ssthresh，后线性  
3. **超时**：ssthresh=cwnd/2，cwnd=1  
4. **快重传**：三重复 ACK；**快恢复**：cwnd 减半线性  

**易错点**：

- 流量控制（rwnd）与拥塞控制（cwnd）混  
- 超时与三 ACK 处理不同  
- 单位 MSS vs 字节  

**变式**：给丢包事件求 cwnd 变化；求有效吞吐。

---

## UDP 与可靠性

> section_id: advanced-cn-transport-udp
> kp_ids: [cn.transport.udp, cn.transport.tcp]
> primary_kp: cn.transport.tcp
> topic_tags: [选择, 分析]
> scope: single
> difficulty: 2

**识别信号**：TCP/UDP 对比；适用场景；是否面向连接。

**方法步骤**：

1. **UDP**：无连接、不保证可靠、开销小、支持多播广播  
2. **TCP**：面向连接、可靠、有序、拥塞控制  
3. 应用选型：DNS 用 UDP；HTTP 用 TCP  

**易错点**：

- 把 UDP 说成完全不可靠到无校验  
- 连接由应用层建立与 TCP 连接混  
- 首部长度与伪首部校验  

**变式**：场景选协议；说明 QUIC 差异。
