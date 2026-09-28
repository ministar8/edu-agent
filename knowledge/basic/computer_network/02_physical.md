# 物理层

> domain_kp: cn.physical
> document_id: basic-cn-physical
> kb_depth: basic
> doc_role: textbook

## 学习目标

- 理解物理层关心的问题
- 理解信道容量的两个经典口径

---

## 信道与传输

> section_id: basic-cn-physical-channel
> kp_ids: [cn.physical.channel]
> primary_kp: cn.physical.channel

**问题**：比特如何在介质上传送（调制、编码、同步、方向、连接方式）。

**思想**：物理层是**比特与信号的接口**，不保证帧与可靠交付。

---

## 传输介质

> section_id: basic-cn-physical-medium
> kp_ids: [cn.physical.medium]
> primary_kp: cn.physical.medium

**思想**：双绞线、同轴、光纤、无线——在带宽、距离、抗干扰、成本间选择。

---

## 信道容量

> section_id: basic-cn-physical-bandwidth
> kp_ids: [cn.physical.bandwidth]
> primary_kp: cn.physical.bandwidth

**定义**：信道无差错传输的速率上限。

**两个口径**：

- **奈氏**：无噪声下，极限与带宽有关（码元速率）
- **香农**：有噪声下，极限与带宽、信噪比有关

**思想**：**编码与信道条件共同决定可靠速率**；不能只堆发射功率。
