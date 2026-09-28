# 传输层

> domain_kp: cn.transport
> document_id: basic-cn-transport
> kb_depth: basic
> doc_role: textbook

## 学习目标

- 理解传输层的端到端角色
- 理解 TCP 连接、流量与拥塞思想
- 理解 UDP 的定位

---

## UDP

> section_id: basic-cn-transport-udp
> kp_ids: [cn.transport.udp]
> primary_kp: cn.transport.udp

**定义**：无连接、不保证可靠交付的用户数据报协议。

**为什么**：开销小、延迟低；适合可容忍丢失或自带可靠性的应用。

**思想**：把「是否可靠」交给应用选择。

---

## TCP 概述

> section_id: basic-cn-transport-tcp
> kp_ids: [cn.transport.tcp]
> primary_kp: cn.transport.tcp

**定义**：面向连接、可靠、字节流传输协议。

**为什么**：应用层不应自己解决丢失、乱序、重复问题。

**思想**：传输层提供**进程到进程**的端到端抽象，屏蔽网络层尽力而为。

---

## TCP 连接管理

> section_id: basic-cn-transport-tcp_handshake
> kp_ids: [cn.transport.tcp_handshake]
> primary_kp: cn.transport.tcp_handshake

**机制**：建立（三次握手）、释放（四次挥手）。

**为什么**：双方确认收发能力与序号起始，避免旧连接干扰；释放要双向关闭。

**思想**：可靠连接是**状态机 + 确认**，不是单纯「发消息」。

---

## 流量控制与拥塞控制

> section_id: basic-cn-transport-tcp_flow
> kp_ids: [cn.transport.tcp_flow, cn.transport.tcp_congestion]
> primary_kp: cn.transport.tcp_congestion

**流量控制**：接收窗口限制发送速率，防压垮接收方。

**拥塞控制**：网络整体过载时降速（慢开始、拥塞避免、快重传、快恢复等思想）。

**区别**：流量控是**收端问题**；拥塞控是**全网问题**。二者共同决定发送窗口。
