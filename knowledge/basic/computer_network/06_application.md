# 应用层

> domain_kp: cn.application
> document_id: basic-cn-application
> kb_depth: basic
> doc_role: textbook

## 学习目标

- 理解 DNS 的目录服务思想
- 理解 HTTP 的请求/响应模型
- 理解邮件与文件传输的基本分工

---

## DNS

> section_id: basic-cn-application-dns
> kp_ids: [cn.application.dns]
> primary_kp: cn.application.dns

**定义**：域名与 IP 地址之间的分布式目录服务。

**为什么**：人用名字、机器用地址；需要可扩展的层次命名与缓存。

**思想**：**分层命名 + 分布式授权**；缓存降低查询延迟与根服务器压力。

---

## HTTP

> section_id: basic-cn-application-http
> kp_ids: [cn.application.http]
> primary_kp: cn.application.http

**定义**：Web 上请求/响应协议，基于传输层可靠流。

**思想**：无状态请求 + 缓存/长连接/版本演进；方法、状态码是语义接口。

---

## 电子邮件

> section_id: basic-cn-application-email
> kp_ids: [cn.application.email]
> primary_kp: cn.application.email

**机制**：用户代理、传输（SMTP）、接收（POP3/IMAP）分工。

**思想**：**存储转发**的异步消息系统，与会话式请求响应不同。

---

## FTP

> section_id: basic-cn-application-ftp
> kp_ids: [cn.application.ftp]
> primary_kp: cn.application.ftp

**定义**：文件传送协议；控制连接与数据连接分离。

**思想**：控制面与数据面分离，便于命令交互与批量传输并行。
