# 操作系统概述

> domain_kp: os.overview
> document_id: basic-os-overview
> kb_depth: basic
> doc_role: textbook

## 学习目标

- 理解 OS 的基本角色
- 理解内核态/用户态
- 理解系统调用的意义

---

## 基本角色与特征

> section_id: basic-os-overview-feature
> kp_ids: [os.overview.feature]
> primary_kp: os.overview.feature

**定义**：操作系统管理硬件资源，并向上提供抽象与执行环境。

**核心机制思想**：

- **并发**：多任务交替或并行推进
- **共享**：资源被多任务受控使用
- **虚拟**：给每任务独占假象
- **异步**：执行走走停停，结果可再现（在一定条件下）

---

## 内核态与用户态

> section_id: basic-os-overview-mode
> kp_ids: [os.overview.mode]
> primary_kp: os.overview.mode

**定义**：CPU 特权级；内核态可执行特权指令、访问全部资源，用户态受限。

**为什么**：防止错误或恶意程序破坏系统与其他进程。

**思想**：**硬件协助的权限边界**；陷入（trap）是进入内核的受控入口。

---

## 系统调用

> section_id: basic-os-overview-syscall
> kp_ids: [os.overview.syscall]
> primary_kp: os.overview.syscall

**定义**：用户程序请求内核服务的接口（文件、进程、设备等）。

**为什么**：用户不能直接操作硬件；必须经内核完成共享资源访问。

**机制**：调用号+参数 → 陷入内核 → 执行内核例程 → 返回用户。

**思想**：系统调用是**用户与内核之间的 API 门**，与库函数层次不同。
