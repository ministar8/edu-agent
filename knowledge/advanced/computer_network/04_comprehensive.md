# 综合拆解 · 解题能力

> domain_kp: cn
> document_id: advanced-cn-comprehensive
> kb_depth: advanced
> doc_role: method

## 本章解决什么

- 跨层时延与吞吐
- 应用层协议与网络综合

---

## 时延与吞吐综合

> section_id: advanced-cn-comprehensive-delay
> kp_ids: [cn.arch.performance, cn.transport.tcp, cn.datalink.flow_control]
> primary_kp: cn.arch.performance
> topic_tags: [计算, 分析]
> scope: cross
> difficulty: 4

**识别信号**：端到端时延、瓶颈链路、并行 TCP 连接。

**分析方法**：

1. **时延** = 传播 + 发送 + 处理 + 排队  
2. **发送** = 报文长 / 带宽；多跳累加  
3. **吞吐** = min(链路带宽) 与并发连接  
4. 画时间线核对 RTT  

**易错点**：

- 传播与发送延时混  
- 单位 ms / Mbps 不统一  
- 只算上行忽略确认  

**变式**：求下载时间；N 段链路瓶颈。

---

## 应用层与网络综合

> section_id: advanced-cn-comprehensive-app
> kp_ids: [cn.application.dns, cn.application.http, cn.transport.tcp]
> primary_kp: cn.application.dns
> topic_tags: [计算, 分析]
> scope: cross
> difficulty: 3

**识别信号**：DNS 解析次数、HTTP 连接复用、RTT 计数。

**方法步骤**：

1. **DNS**：本地缓存/递归/迭代；数 RTT  
2. **HTTP**：非持久每文档 2 RTT+ 传输；持久省握手  
3. **CDN / P2P** 降低瓶颈  

**易错点**：

- 递归与迭代查询次数  
- TCP 建立与请求响应 RTT 重复  
- 忽略 DNS  

**变式**：求页面加载 RTT；比较 HTTP/1.1 与 HTTP/2。

---

## 网络体系结构与协议要素

> section_id: advanced-cn-comprehensive-architecture
> kp_ids: [cn.arch.model, cn.arch.performance]
> primary_kp: cn.arch.model
> topic_tags: [分析, 选择]
> scope: cross
> difficulty: 2

**识别信号**：协议三要素、分层职责、交换方式对比、性能指标计算。

**方法步骤**：

1. **协议三要素**：语法（格式）、语义（含义）、时序（顺序）  
2. **分层**：OSI 七层 / TCP/IP 四层；对等层通信，下层为上层服务  
3. **交换对比**：电路（建连/固定带宽）· 报文（存转整包）· 分组（存转小段，时延更优）  
4. **性能**：时延=发送+传播+处理+排队；丢包多因排队溢出；吞吐≤瓶颈链路  

**易错点**：

- 实现 vs 体系结构（抽象）  
- 电路交换与虚电路混用  
- 把协议当成「软件」而非规则集合  

**变式**：给场景选交换方式；画分层封装；算端到端时延。

---

## 成帧与差错控制

> section_id: advanced-cn-comprehensive-framing
> kp_ids: [cn.datalink.framing, cn.datalink.error_control]
> primary_kp: cn.datalink.framing
> topic_tags: [计算, 选择]
> scope: single
> difficulty: 2

**识别信号**：成帧方法、比特填充、CRC 校验位、海明码距。

**方法步骤**：

1. **成帧**：字符计数 / 字节填充 / 比特填充 / 违规编码  
2. **比特填充**：数据中 5 个 1 插一个 0，防与标志重复  
3. **CRC**：生成多项式 r 次 → r 位校验；模 2 除  
4. **海明**：`2^r ≥ m+r+1`；最小码距 d 可检 `d-1` 错、纠 `⌊(d-1)/2⌋`  

**易错点**：

- 字节填充 vs 比特填充  
- CRC 是检错不是纠错（除非再编码）  
- 码距与检/纠错能力公式  

**变式**：给数据流写填充后比特串；求校验位数。

---

## 分层封装与接口原语

> section_id: advanced-cn-comprehensive-encapsulation
> kp_ids: [cn.arch.model]
> primary_kp: cn.arch.model
> topic_tags: [分析, 选择]
> scope: single
> difficulty: 2

**识别信号**：PDU 名称、封装拆封、服务与协议区别、SAP/接口。

**方法步骤**：

1. **PDU**：应用报文 · 传输段/用户数据报 · 网络分组/数据报 · 链路帧 · 比特流  
2. **封装**：逐层加首部（链路可加尾部）；接收逆拆  
3. **服务**：下层向上提供；**协议**：对等层规则  
4. **面向连接服务** ≠ 某层协议一定面向连接（可组合）  

**易错点**：

- 把 SAP 当成 IP 地址  
- 封装后「地址」在哪一层变  
- 服务原语（request/indication…）与协议混谈  

**变式**：给报文画封装；问第几层查 MAC/IP。

---

## 应用层协议方法

> section_id: advanced-cn-comprehensive-application
> kp_ids: [cn.application.dns, cn.application.http, cn.application.email]
> primary_kp: cn.application.dns
> topic_tags: [分析, 选择]
> scope: cross
> difficulty: 2

**识别信号**：DNS 解析次数；HTTP 连接与 RTT；邮件协议角色。

**方法步骤**：

1. **DNS**：递归/迭代；缓存命中减 RTT；记录类型 A/CNAME/MX  
2. **HTTP**：非持久 2RTT+ 传输；持久复用 TCP；Cookie 状态  
3. **邮件**：SMTP 推 · POP/IMAP 拉；MIME 扩展  
4. **RTT 记账**：DNS + TCP 握手 + 请求/响应（按连接复用次数）  

**易错点**：

- 迭代查询每次由主机再问  
- SMTP 不是拉协议  
- 忽略 DNS 缓存  

**变式**：算完整访问时延；比 HTTP/1.1 与 HTTP/2 多路复用。

---

## 体系结构对比与性能指标

> section_id: advanced-cn-comprehensive-arch_compare
> kp_ids: [cn.arch.model, cn.arch.performance]
> primary_kp: cn.arch.performance
> topic_tags: [分析, 计算]
> scope: cross
> difficulty: 2

**识别信号**：OSI vs TCP/IP；时延/吞吐/丢包率计算。

**方法步骤**：

1. **OSI 七层** vs **TCP/IP 四层**：应用合并、网络层核心  
2. **时延**：发送 L/R + 传播 d/v + 处理 + 排队；多跳累加  
3. **吞吐** = min(R1…Rn)；瓶颈决定端到端速率  
4. **丢包**：队列满 → 拥塞丢包；FCS 失败 → 差错丢包  

**易错点**：

- 传播时延与发送时延公式混  
- 吞吐用平均带宽错  
- 分层数错记导致协议归属错  

**变式**：N 段链路求总时延；识别瓶颈。

---

## 网络服务与接口原语

> section_id: advanced-cn-comprehensive-service
> kp_ids: [cn.arch.model]
> primary_kp: cn.arch.model
> topic_tags: [选择, 分析]
> scope: single
> difficulty: 2

**识别信号**：面向连接/无连接；服务原语；可靠与不可靠。

**方法步骤**：

1. **面向连接**：建连→传→释放（TCP、虚电路）  
2. **无连接**：独立分组（UDP、数据报）  
3. **可靠服务**：确认、重传、排序、流量控制  
4. **原语**：request / indication / response / confirm  

**易错点**：

- TCP 可靠 ≠ 整个网络可靠  
- 无连接也可可靠（应用层）  
- 服务类型与协议实现不是一一对应  

**变式**：选协议匹配服务要求；画原语时序。

---

## 应用层 DNS/HTTP 计算

> section_id: advanced-cn-comprehensive-dns_http
> kp_ids: [cn.application.dns, cn.application.http]
> primary_kp: cn.application.dns
> topic_tags: [计算, 分析]
> scope: single
> difficulty: 3

**识别信号**：DNS 查询次数；页面加载时间；连接复用收益。

**方法步骤**：

1. **DNS**：本地无缓存时递归 3+ 次 RTT；缓存命中 0 次  
2. **非持久 HTTP**：TCP 2 次 RTT + 文档传输  
3. **持久**：连接复用，省握手  
4. **并行连接** vs **流水**：前者开多 TCP，后者同一连接连续发  

**易错点**：

- DNS 每级迭代一次 RTT  
- HTTPS 额外 TLS 握手  
- 图片资源数不乘 DNS（缓存）  

**变式**：求首次访问总时间；改持久/并行后节省多少。





