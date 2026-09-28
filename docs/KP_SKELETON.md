# 四科 Knowledge Point 骨架（可修改稿）

> 图例：`*` core · `+` major · `.` minor
> 标注：`[node_kind/L{level}/{type}] typical_question_types`
> 粒度：一个 KP = 真题可单独考查的语义单元；aliases 只放同义名
> 改完可改 `knowledge_points/*.jsonl`，或改 `scripts/gen_kp_skeleton.py` 重生成。

## 数据结构 `ds` — 52 节点

- `ds` 数据结构 `[subject/L1/concept]` * choice
  - `ds.array` 数组与特殊矩阵 `[domain/L2/structure]` + choice
    - `ds.array.compressed` 压缩存储 `[topic/L3/structure]` + choice,calculation
      - `ds.array.sparse` 稀疏矩阵 `[point/L4/structure]` + choice
      - `ds.array.symmetric` 对称矩阵 `[point/L4/structure]` + choice
      - `ds.array.triangular` 三角矩阵 `[point/L4/structure]` + choice
  - `ds.graph` 图 `[domain/L2/structure]` + choice
    - `ds.graph.aoe` 关键路径 `[point/L3/algorithm]` + choice,calculation  ← AOE
    - `ds.graph.mst` 最小生成树 `[point/L3/algorithm]` * choice,calculation  ← Prim、Kruskal
    - `ds.graph.shortest_path` 最短路径 `[point/L3/algorithm]` * choice,calculation  ← Dijkstra、Floyd
    - `ds.graph.storage` 图的存储 `[topic/L3/structure]` + choice
    - `ds.graph.topo` 拓扑排序 `[point/L3/algorithm]` * choice,calculation,comprehensive,code
    - `ds.graph.traversal` 图的遍历 `[point/L3/algorithm]` * choice,calculation,comprehensive,code  ← DFS、BFS
  - `ds.linear` 线性表 `[domain/L2/structure]` + choice
    - `ds.linear.linked_list` 链表 `[point/L3/structure]` + choice,code
      - `ds.linear.circular_linked` 循环链表 `[point/L4/structure]` + choice
      - `ds.linear.doubly_linked` 双链表 `[point/L4/structure]` + choice
    - `ds.linear.list` 线性表概念 `[topic/L3/structure]` + choice
    - `ds.linear.seq_list` 顺序表 `[point/L3/structure]` + choice,code
  - `ds.search` 查找 `[domain/L2/algorithm]` + choice
    - `ds.search.b_plus_tree` B+ 树 `[point/L3/structure]` + choice,calculation,comprehensive,code
    - `ds.search.b_tree` B 树 `[point/L3/structure]` * choice,calculation,comprehensive,code
    - `ds.search.binary_search` 折半查找 `[point/L3/algorithm]` * choice,calculation,comprehensive,code  ← 二分查找
    - `ds.search.block` 分块查找 `[point/L3/algorithm]` + choice,calculation
    - `ds.search.hash` 散列表 `[point/L3/structure]` * choice,calculation,comprehensive,code  ← 哈希表
    - `ds.search.seq` 顺序查找 `[point/L3/algorithm]` . choice
  - `ds.sort` 排序 `[domain/L2/algorithm]` + choice
    - `ds.sort.bubble` 冒泡排序 `[point/L3/algorithm]` + choice
    - `ds.sort.heap` 堆排序 `[point/L3/algorithm]` * choice,calculation,comprehensive,code
    - `ds.sort.insertion` 直接插入排序 `[point/L3/algorithm]` + choice,calculation
    - `ds.sort.merge` 归并排序 `[point/L3/algorithm]` * choice,calculation,comprehensive,code
    - `ds.sort.quick_sort` 快速排序 `[point/L3/algorithm]` * choice,calculation,comprehensive,code
    - `ds.sort.radix` 基数排序 `[point/L3/algorithm]` + choice
    - `ds.sort.select` 简单选择排序 `[point/L3/algorithm]` + choice,calculation
    - `ds.sort.shell` 希尔排序 `[point/L3/algorithm]` + choice
  - `ds.stack_queue` 栈和队列 `[domain/L2/structure]` + choice
    - `ds.stack_queue.queue` 队列 `[topic/L3/structure]` + choice,calculation,comprehensive,code
      - `ds.stack_queue.circular_queue` 循环队列 `[point/L4/structure]` + choice,calculation,comprehensive,code
    - `ds.stack_queue.stack` 栈 `[topic/L3/structure]` + choice,calculation,comprehensive,code
      - `ds.stack_queue.match` 括号匹配 `[point/L4/method]` + choice,code
  - `ds.string` 串 `[domain/L2/structure]` + choice
    - `ds.string.match` 模式匹配 `[topic/L3/algorithm]` + choice
      - `ds.string.kmp` KMP 算法 `[point/L4/algorithm]` * choice,calculation,comprehensive,code  ← KMP
  - `ds.tree` 树与二叉树 `[domain/L2/structure]` + choice
    - `ds.tree.avl` 平衡二叉树 `[point/L3/structure]` * choice,calculation,comprehensive,code  ← AVL
    - `ds.tree.binary_tree` 二叉树 `[topic/L3/structure]` + choice
      - `ds.tree.complete` 完全二叉树 `[point/L4/structure]` + choice,calculation
      - `ds.tree.threaded` 线索二叉树 `[point/L4/structure]` + choice
      - `ds.tree.traversal` 二叉树遍历 `[point/L4/algorithm]` * choice,calculation,comprehensive,code
    - `ds.tree.bst` 二叉排序树 `[point/L3/structure]` * choice,calculation,comprehensive,code  ← BST、二叉查找树
    - `ds.tree.forest_convert` 树与森林转换 `[point/L3/method]` + choice,calculation
    - `ds.tree.huffman` 哈夫曼编码 `[point/L3/algorithm]` * choice,calculation  ← 哈夫曼树

## 计算机组成原理 `co` — 39 节点

- `co` 计算机组成原理 `[subject/L1/concept]` * choice
  - `co.bus` 总线 `[domain/L2/structure]` + choice
    - `co.bus.arbitration` 总线仲裁 `[point/L3/concept]` + choice
    - `co.bus.bandwidth` 总线带宽 `[point/L3/concept]` * choice,calculation
    - `co.bus.timing` 总线定时 `[point/L3/concept]` . choice
  - `co.cpu` 中央处理器 `[domain/L2/structure]` + choice
    - `co.cpu.controller` 控制器 `[point/L3/structure]` * choice,calculation,comprehensive,code  ← 微程序、硬布线
    - `co.cpu.datapath` 数据通路 `[topic/L3/structure]` + choice
    - `co.cpu.exception` 中断与异常 `[point/L3/concept]` * choice,calculation,comprehensive,code  ← 中断
    - `co.cpu.pipeline` 指令流水线 `[point/L3/concept]` * choice,calculation,comprehensive,code  ← 流水线技术
      - `co.cpu.pipeline_hazard` 流水线冒险 `[point/L4/concept]` * choice,calculation,comprehensive,code  ← 冒险、冲突
      - `co.cpu.pipeline_stall` 流水线停顿与转发 `[point/L4/method]` + choice,calculation,comprehensive,code  ← forwarding、旁路
  - `co.instruction` 指令系统 `[domain/L2/concept]` + choice
    - `co.instruction.addressing` 寻址方式 `[point/L3/concept]` * choice,calculation,comprehensive,code
    - `co.instruction.format` 指令格式 `[topic/L3/concept]` + choice,calculation,comprehensive,code
    - `co.instruction.isa` 指令体系结构 ISA `[point/L3/concept]` + choice
    - `co.instruction.risc_cisc` RISC 与 CISC `[point/L3/concept]` + choice
  - `co.io` 输入输出系统 `[domain/L2/structure]` + choice
    - `co.io.channel` 通道方式 `[point/L3/concept]` . choice
    - `co.io.dma` DMA 方式 `[point/L3/concept]` * choice,calculation,comprehensive,code
    - `co.io.interface` I/O 接口 `[topic/L3/structure]` + choice
    - `co.io.interrupt_io` 程序中断方式 `[point/L3/concept]` * choice,calculation,comprehensive,code
  - `co.overview` 计算机系统概述 `[domain/L2/concept]` + choice
    - `co.overview.performance` 性能指标 `[point/L3/concept]` * choice,calculation  ← CPI、CPU 时间
    - `co.overview.von_neumann` 冯·诺依曼结构 `[point/L3/concept]` + choice
  - `co.representation` 数据表示与运算 `[domain/L2/concept]` + choice
    - `co.representation.fixed_point` 定点数表示 `[topic/L3/concept]` + choice
      - `co.representation.complement` 补码 `[point/L4/concept]` * choice,calculation,comprehensive,code  ← 原码、反码
    - `co.representation.ieee754` 浮点数 IEEE754 `[point/L3/concept]` * choice,calculation,comprehensive,code  ← 阶码、尾数
    - `co.representation.integer_op` 整数运算 `[point/L3/algorithm]` + choice,calculation
    - `co.representation.overflow` 溢出判断 `[point/L3/concept]` + choice,calculation  ← OF
  - `co.storage` 存储系统 `[domain/L2/structure]` + choice
    - `co.storage.cache` Cache `[point/L3/structure]` * choice,calculation,comprehensive,code  ← 高速缓存
      - `co.storage.cache_mapping` Cache 映射方式 `[point/L4/method]` * choice,calculation,comprehensive,code  ← 全相联、组相联
      - `co.storage.cache_replace` Cache 替换算法 `[point/L4/algorithm]` + choice,calculation,comprehensive,code
      - `co.storage.cache_write` Cache 写策略 `[point/L4/method]` + choice,calculation,comprehensive,code  ← 写直达、写回
    - `co.storage.hierarchy` 存储层次 `[topic/L3/concept]` + choice
    - `co.storage.main_memory` 主存储器 `[point/L3/structure]` + choice,calculation
    - `co.storage.virtual_memory` 虚拟存储器 `[point/L3/concept]` * choice,calculation,comprehensive,code

## 操作系统 `os` — 36 节点

- `os` 操作系统 `[subject/L1/concept]` * choice
  - `os.file` 文件管理 `[domain/L2/concept]` + choice
    - `os.file.dir` 目录管理 `[point/L3/structure]` + choice,calculation,comprehensive,code
    - `os.file.disk_schedule` 磁盘调度 `[point/L3/algorithm]` * choice,calculation,comprehensive,code
    - `os.file.logical` 文件逻辑结构 `[topic/L3/concept]` + choice
    - `os.file.physical` 文件物理结构 `[topic/L3/structure]` + choice
      - `os.file.alloc` 文件分配方式 `[point/L4/method]` * choice,calculation,comprehensive,code  ← 连续分配、链接分配、索引分配
      - `os.file.disk_free_space` 磁盘空闲空间管理 `[point/L4/method]` * choice,calculation,comprehensive,code  ← 位示图、空闲表、空闲链表
  - `os.io` 输入输出管理 `[domain/L2/concept]` + choice
    - `os.io.buffer` 缓冲管理 `[point/L3/concept]` + choice,calculation,comprehensive,code
    - `os.io.device` 设备管理 `[point/L3/concept]` + choice,calculation,comprehensive,code
    - `os.io.software` I/O 软件层次 `[topic/L3/concept]` + choice
  - `os.memory` 内存管理 `[domain/L2/concept]` + choice
    - `os.memory.allocate` 内存分配 `[topic/L3/method]` + choice
      - `os.memory.partition` 分区分配 `[point/L4/method]` + choice,calculation,comprehensive,code  ← 动态分区
    - `os.memory.paging` 分页管理 `[point/L3/concept]` * choice,calculation,comprehensive,code
      - `os.memory.tlb` TLB 快表 `[point/L4/structure]` + choice,calculation,comprehensive,code
    - `os.memory.segmentation` 分段管理 `[point/L3/concept]` * choice,calculation,comprehensive,code
    - `os.memory.virtual` 虚拟内存 `[point/L3/concept]` * choice,calculation,comprehensive,code
      - `os.memory.page_fault` 缺页异常 `[point/L4/concept]` * choice,calculation,comprehensive,code
      - `os.memory.page_replace` 页面置换算法 `[point/L4/algorithm]` * choice,calculation,comprehensive,code
  - `os.overview` 操作系统概述 `[domain/L2/concept]` + choice
    - `os.overview.feature` 基本特征 `[point/L3/concept]` + choice
    - `os.overview.mode` 内核态与用户态 `[point/L3/concept]` * choice,calculation,comprehensive,code
    - `os.overview.syscall` 系统调用 `[point/L3/concept]` * choice,calculation,comprehensive,code
  - `os.process` 进程管理 `[domain/L2/concept]` + choice
    - `os.process.deadlock` 死锁 `[point/L3/concept]` * choice,calculation,comprehensive,code
      - `os.process.bankers` 银行家算法 `[point/L4/algorithm]` * choice,calculation,comprehensive,code
    - `os.process.schedule` 处理机调度 `[point/L3/algorithm]` * choice,calculation,comprehensive,code  ← CPU 调度
    - `os.process.state` 进程状态与转换 `[point/L3/concept]` * choice,calculation,comprehensive,code
    - `os.process.sync` 进程同步 `[topic/L3/concept]` * choice,calculation,comprehensive,code
      - `os.process.classic_sync` 经典同步问题 `[point/L4/method]` * choice,calculation,comprehensive,code  ← 生产者消费者、哲学家进餐、读者写者
      - `os.process.monitor` 管程 `[point/L4/concept]` + choice,calculation,comprehensive,code
      - `os.process.pv` PV 操作 `[point/L4/method]` * choice,calculation,comprehensive,code
      - `os.process.semaphore` 信号量机制 `[point/L4/concept]` * choice,calculation,comprehensive,code  ← 信号量
    - `os.process.thread` 进程与线程 `[topic/L3/concept]` * choice,calculation,comprehensive,code

## 计算机网络 `cn` — 35 节点

- `cn` 计算机网络 `[subject/L1/concept]` * choice
  - `cn.application` 应用层 `[domain/L2/protocol]` + choice
    - `cn.application.dns` DNS `[point/L3/protocol]` * choice,calculation,comprehensive,code
    - `cn.application.email` 电子邮件 `[point/L3/protocol]` . choice  ← SMTP、POP3
    - `cn.application.ftp` FTP `[point/L3/protocol]` . choice
    - `cn.application.http` HTTP `[point/L3/protocol]` * choice,calculation,comprehensive,code
  - `cn.arch` 体系结构 `[domain/L2/concept]` + choice
    - `cn.arch.model` 网络体系结构 `[topic/L3/concept]` * choice,calculation,comprehensive,code  ← OSI、TCP/IP
    - `cn.arch.performance` 网络性能指标 `[point/L3/concept]` + choice,calculation
  - `cn.datalink` 数据链路层 `[domain/L2/concept]` + choice
    - `cn.datalink.error_control` 差错控制 `[point/L3/algorithm]` * choice,calculation,comprehensive,code  ← CRC、海明码
    - `cn.datalink.ethernet` 以太网 `[point/L3/structure]` * choice,calculation,comprehensive,code
    - `cn.datalink.flow_control` 流量控制 `[point/L3/concept]` * choice,calculation,comprehensive,code  ← 滑动窗口
    - `cn.datalink.framing` 成帧 `[topic/L3/concept]` + choice
    - `cn.datalink.mac` 介质访问控制 MAC `[point/L3/concept]` * choice,calculation,comprehensive,code  ← CSMA/CD
    - `cn.datalink.vlan` VLAN `[point/L3/concept]` + choice
  - `cn.network` 网络层 `[domain/L2/concept]` + choice
    - `cn.network.arp` ARP `[point/L3/protocol]` * choice,calculation,comprehensive,code  ← 地址解析
    - `cn.network.icmp` ICMP `[point/L3/protocol]` * choice,calculation,comprehensive,code  ← 网际控制报文、差错报告
    - `cn.network.ip` IP 协议 `[topic/L3/protocol]` * choice,calculation,comprehensive,code
      - `cn.network.ip_address` IP 地址与子网 `[point/L4/concept]` * choice,calculation,comprehensive,code  ← 子网划分、CIDR
      - `cn.network.ip_forward` IP 转发与分片 `[point/L4/concept]` + choice,calculation,comprehensive,code
    - `cn.network.ipv6` IPv6 `[point/L3/protocol]` . choice
    - `cn.network.nat` NAT `[point/L3/concept]` + choice
    - `cn.network.routing` 路由算法 `[point/L3/algorithm]` * choice,calculation,comprehensive,code  ← RIP、OSPF
  - `cn.physical` 物理层 `[domain/L2/concept]` + choice
    - `cn.physical.bandwidth` 信道容量 `[point/L3/concept]` * choice,calculation  ← 奈氏、香农
    - `cn.physical.channel` 信道与传输 `[topic/L3/concept]` + choice
    - `cn.physical.medium` 传输介质 `[point/L3/concept]` + choice
  - `cn.transport` 传输层 `[domain/L2/protocol]` + choice
    - `cn.transport.tcp` TCP `[topic/L3/protocol]` * choice,calculation,comprehensive,code
      - `cn.transport.tcp_congestion` TCP 拥塞控制 `[point/L4/algorithm]` * choice,calculation,comprehensive,code
      - `cn.transport.tcp_flow` TCP 流量控制 `[point/L4/concept]` * choice,calculation,comprehensive,code
      - `cn.transport.tcp_handshake` TCP 连接管理 `[point/L4/protocol]` * choice,calculation,comprehensive,code  ← 三次握手、四次挥手
    - `cn.transport.udp` UDP `[point/L3/protocol]` + choice,calculation,comprehensive,code
