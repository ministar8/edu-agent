# 网络层

> domain_kp: cn.network
> document_id: basic-cn-network
> kb_depth: basic
> doc_role: textbook

## 学习目标

- 理解 IP 编址与转发
- 理解 ARP/ICMP 的分工
- 理解路由与 NAT 的思想

---

## IP 协议

> section_id: basic-cn-network-ip
> kp_ids: [cn.network.ip]
> primary_kp: cn.network.ip

**定义**：提供无连接、尽力而为的分组传输；核心是编址与转发。

**为什么**：把「不同链路、不同拓扑」统一成「从源到宿的分组路径」。

---

## IP 地址与子网

> section_id: basic-cn-network-ip_address
> kp_ids: [cn.network.ip_address]
> primary_kp: cn.network.ip_address

**定义**：网络号+主机号；子网划分、CIDR 前缀聚合。

**思想**：层次化地址便于路由聚合，减少路由表规模。

---

## 转发与分片

> section_id: basic-cn-network-ip_forward
> kp_ids: [cn.network.ip_forward]
> primary_kp: cn.network.ip_forward

**转发**：路由器按目的网络查表选下一跳。

**分片**：超过 MTU 时拆片，目的主机重组。

**思想**：网络层提供**跳到跳的分组服务**；端到端完整性常靠上层补强。

---

## ARP 与 ICMP

> section_id: basic-cn-network-arp
> kp_ids: [cn.network.arp, cn.network.icmp]
> primary_kp: cn.network.arp

**ARP**：由 IP 地址解析 MAC 地址（同一链路）。

**ICMP**：网络层控制/差错报告（不可达、超时等）。

**思想**：二者是 IP 的**辅助协议**——地址解析与状态反馈，不是端到端数据通道。

---

## 路由算法

> section_id: basic-cn-network-routing
> kp_ids: [cn.network.routing]
> primary_kp: cn.network.routing

**问题**：如何得到「去往目的的下一跳」。

**思想**：

- **距离向量**：邻居交换距离信息，分布式收敛
- **链路状态**：全网链路信息，计算最短路径树

**要点**：路由是**控制面**；转发是**数据面**。

---

## NAT 与 IPv6

> section_id: basic-cn-network-nat
> kp_ids: [cn.network.nat, cn.network.ipv6]
> primary_kp: cn.network.nat

**NAT**：私有地址与公有地址转换，缓解地址短缺。

**IPv6**：更大地址空间、简化头部、改进扩展与自动配置。

**思想**：编址与路由规模问题是推动协议演进的核心动力。
