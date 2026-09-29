# 网络层 · 解题能力

> domain_kp: cn.network
> document_id: advanced-cn-network_ip
> kb_depth: advanced
> doc_role: method

## 本章解决什么

- 子网划分与 CIDR
- IP 分片
- 路由与转发
- ARP / ICMP

---

## IP 地址与子网划分

> section_id: advanced-cn-network_ip-subnet
> kp_ids: [cn.network.ip_address, cn.network.ip]
> primary_kp: cn.network.ip_address
> topic_tags: [计算, 分析]
> scope: single
> difficulty: 3

**识别信号**：给 IP/掩码求网络地址、子网数、主机数、地址类型。

**方法步骤**：

1. **与掩码按位与**得网络号  
2. **CIDR** `/n`：主机位 `32-n`，可用主机 `2^{32-n}−2`  
3. **分子网**：借位；判断子网号/广播/可用  
4. 私有地址段、特殊地址（网络号全 0/1）  

**易错点**：

- 可用主机数忘减 2  
- 掩码写点分与 `/n` 转换  
- 子网号与网络号层级混  

**变式**：划分 n 个子网求掩码；判断两地址是否同网。

---

## IP 分片与转发

> section_id: advanced-cn-network_ip-fragment
> kp_ids: [cn.network.ip_forward, cn.network.ip]
> primary_kp: cn.network.ip_forward
> topic_tags: [计算, 分析]
> scope: single
> difficulty: 3

**识别信号**：给 MTU 求分片数、MF/片偏移、总长度。

**方法步骤**：

1. 数据区按 **8 字节**对齐再切  
2. **片偏移** = 数据起始/8；**MF** 表示后续是否还有  
3. 总长 = 头 + 数据；各片 ID 相同  
4. 转发查路由表，TTL 减 1，重新计算首部校验和  

**易错点**：

- 偏移单位是 8B 不是 1B  
- MF/DF 标志位含义  
- 片偏移最后一片是否 8 对齐  

**变式**：给 4000B 数据与 MTU 1400 画各片字段。

---

## 路由算法与 ARP/ICMP

> section_id: advanced-cn-network_ip-routing
> kp_ids: [cn.network.routing, cn.network.arp, cn.network.icmp]
> primary_kp: cn.network.routing
> topic_tags: [计算, 选择]
> scope: single
> difficulty: 3

**识别信号**：RIP/OSPF 特点、路由表构建、ARP 解析流程。

**方法步骤**：

1. **RIP**：距离向量，最多 15 跳；慢收敛  
2. **OSPF**：链路状态，Dijkstra；收敛快  
3. **ARP**：IP→MAC；同网广播解析  
4. **ICMP**：差错与查询；Ping 用回显  

**易错点**：

- RIP 跳数限制  
- ARP 作用层次  
- 路由与转发职责  

**变式**：给距离向量表迭代；说明 ARP 缓存未命中过程。
