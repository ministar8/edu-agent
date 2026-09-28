# 体系结构

> domain_kp: cn.arch
> document_id: basic-cn-arch
> kb_depth: basic
> doc_role: textbook

## 学习目标

- 理解分层的网络体系结构
- 理解基本性能指标

---

## 网络体系结构

> section_id: basic-cn-arch-model
> kp_ids: [cn.arch.model]
> primary_kp: cn.arch.model

**定义**：把通信任务划分为层次，每层向上提供服务、向下使用服务；对等层有协议。

**为什么**：通信问题复杂（物理传、成帧、路由、应用语义）；分层降低耦合、便于实现替换。

**思想**：

- **封装**：上层数据作为下层载荷，加首部
- **协议**：对等实体的约定（语法、语义、时序）
- **接口**：相邻层之间的服务访问点

常见模型：OSI 七层与 TCP/IP 四层——层次划分不同，分层原则一致。

---

## 网络性能指标

> section_id: basic-cn-arch-performance
> kp_ids: [cn.arch.performance]
> primary_kp: cn.arch.performance

**口径**：

- 时延：发送、传播、处理、排队
- 带宽：链路最高数据率
- 吞吐：实际通过量
- 往返时间 RTT

**思想**：性能是多段时延之和；「带宽高」不等于「RTT 短」。
