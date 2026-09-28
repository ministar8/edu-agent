# 数据链路层

> domain_kp: cn.datalink
> document_id: basic-cn-datalink
> kb_depth: basic
> doc_role: textbook

## 学习目标

- 理解成帧、差错、流控
- 理解 MAC 与共享信道
- 理解以太网与 VLAN 的组织思想

---

## 成帧

> section_id: basic-cn-datalink-framing
> kp_ids: [cn.datalink.framing]
> primary_kp: cn.datalink.framing

**问题**：把比特流切成帧并识别边界（字符填充、比特填充等）。

**思想**：为上层提供**有边界的传输单元**。

---

## 差错控制

> section_id: basic-cn-datalink-error_control
> kp_ids: [cn.datalink.error_control]
> primary_kp: cn.datalink.error_control

**问题**：检测/纠正传输中的比特错误。

**思想**：

- **检错**（如 CRC）：发现错误，交上层重传
- **纠错**（如海明）：冗余定位并改正

**机制**：校验码是「数据的函数」；距离越大，纠错能力越强。

---

## 流量控制

> section_id: basic-cn-datalink-flow_control
> kp_ids: [cn.datalink.flow_control]
> primary_kp: cn.datalink.flow_control

**问题**：发送方不压垮接收方。

**思想**：滑动窗口——允许多帧在途，窗口大小限制未确认帧；停等可视为窗口特例。

---

## 介质访问控制 MAC

> section_id: basic-cn-datalink-mac
> kp_ids: [cn.datalink.mac]
> primary_kp: cn.datalink.mac

**问题**：共享信道上多站点如何有序发送。

**思想**：

- 受控访问、随机访问（如 CSMA/CD 载波监听 + 冲突处理）
- 冲突不可避免时用退避均衡竞争

---

## 以太网与 VLAN

> section_id: basic-cn-datalink-ethernet
> kp_ids: [cn.datalink.ethernet, cn.datalink.vlan]
> primary_kp: cn.datalink.ethernet

**以太网**：帧格式、MAC 地址、交换机转发学习。

**VLAN**：在交换网上划分逻辑广播域。

**思想**：二层关注**帧的投递**；VLAN 用标签切分广播范围，兼顾安全与组织。
