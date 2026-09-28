# 总线

> domain_kp: co.bus
> document_id: basic-co-bus
> kb_depth: basic
> doc_role: textbook

## 学习目标

- 理解总线作为共享通道的角色
- 理解带宽与定时的基本口径
- 理解仲裁的必要性

---

## 总线概述

> section_id: basic-co-bus-overview
> kp_ids: []

**定义**：多个部件共享的传送指令、数据、地址与控制信号的通道。

**为什么**：点对点连线爆炸；共享总线降低成本，代价是争用与分时。

**分类思想**：数据/地址/控制总线；系统总线、I/O 总线等按范围划分。

---

## 总线带宽

> section_id: basic-co-bus-bandwidth
> kp_ids: [co.bus.bandwidth]
> primary_kp: co.bus.bandwidth

**定义**：单位时间总线能传送的数据量。

**口径**：带宽 ≈ 工作频率 × 总线宽度 ×（每周期传送次数）；注意**时钟频率**与**有效传输率**不是同一说法。

**为什么**：决定突发传输与外设吞吐上限。

---

## 仲裁与定时

> section_id: basic-co-bus-arbitration
> kp_ids: [co.bus.arbitration, co.bus.timing]
> primary_kp: co.bus.arbitration

**仲裁**

**问题**：多主设备谁用总线。

**思想**：集中式（链式、计数器、独立请求）与分布式；在公平、简单、速度之间取舍。

**定时**

**定义**：事件如何在时间上对齐（同步 / 异步 / 半同步）。

**思想**：同步靠公共时钟简单快；异步靠握手适应速度差异；总线事务有建立、传送、结束相位。
