"""向量集合身份登记处（全仓唯一真源）。

所有集合名、集合→代码库映射、关键词→集合映射在此定义。
检索链、离线入库、评测门禁均从此处 import，**不再自行定义集合名**。

设计约定：
- 集合名小写，多词用下划线，与 Chroma 集合名和 ChromaDB collection name 保持一致。
- 学科集合（L1/L2 讲义）与 考试集合（L3 真题/章节题型）与 代码库集合 与 学习路径集合 互不重叠。
"""

from __future__ import annotations

# ── 学科集合（L1/L2 讲义，四科）────────────────────────────────────
SUBJECT_COLLECTIONS: list[str] = [
    "data_structure",
    "computer_organization",
    "operating_system",
    "computer_network",
]

# 考试集合（L3 真题 + 章节题型）
EXAMS_COLLECTION: str = "exams"

# 学习路径集合
LEARNING_PATHS_COLLECTION: str = "learning_paths"

# 学科集合 → 代码库集合（`knowledge/code/<科>/`，代码类查询额外命中）
CODE_COLLECTION: dict[str, str] = {
    "data_structure": "code_ds",
    "computer_organization": "code_co",
    "operating_system": "code_os",
    "computer_network": "code_cn",
}

# 关键词 → 集合名映射（用于查询分类时的集合缩小）
COLLECTION_KEYWORDS: dict[str, tuple[str, ...]] = {
    "data_structure": (
        "数据结构",
        "线性表",
        "顺序表",
        "链表",
        "栈",
        "队列",
        "数组",
        "矩阵",
        # ★ 单字关键词会**作为子串**误命中（`_contains_collection_keyword` 对非 ASCII
        #   走的是 `key in text`）。实测（2026-09-27）：
        #   `串` 命中「IPv4 点分十进制**字符串**转换为 32 位整数」（属 network）；
        #   `图` 命中「**位示图**法」「**资源分配图**化简」（属 operating_system）。
        #   故把两个单字项**展开成语义明确的词形**，覆盖不变、误命中消失。
        #   其余两个单字项（`栈` / `树`）经全量黄金集核查无同类误命中，保持不变。
        "主串",
        "子串",
        "字符串匹配",
        "kmp",
        "树",
        "二叉树",
        "森林",
        "哈夫曼",
        "图的",
        "图论",
        "无向图",
        "有向图",
        "邻接表",
        "查找",
        "散列",
        "哈希",
        "排序",
        "avl",
        "红黑树",
        "b树",
        "b+树",
        "最短路径",
        "最小生成树",
        "拓扑排序",
        "关键路径",
        "迪杰斯特拉",
        "弗洛伊德",
        "普里姆",
        "克鲁斯卡尔",
        "bst",
        "rbt",
        "mst",
        "dijkstra",
        "floyd",
        "prim",
        "kruskal",
        "bfs",
        "dfs",
    ),
    "computer_organization": (
        "计组",
        "组成原理",
        "计算机组成",
        "cpu",
        "中央处理器",
        "指令系统",
        "指令周期",
        "指令执行",
        "总线",
        "存储器",
        "cache",
        "高速缓存",
        "主存",
        "磁盘",
        "运算器",
        "控制器",
        "流水线",
        "io系统",
        "输入输出",
        "指令流水线",
        "微程序",
        "中断",
        "dma",
        "寻址方式",
        # 数据表示（C2，2026-09-27）：原先只有「浮点数」，而实际提问常写
        # 「float 的 32 位二进制表示」「读出阶码与尾数」—— 一个关键词都匹配不上，
        # 于是推断为空、退化成全 4 科检索（探针 #17）。
        "浮点数",
        "阶码",
        "尾数",
        "float",
        "ieee754",
        "补码",
        "alu",
        "tlb",
        "快表",
        "页表",
        "段表",
        # 段页式在知识库里**两科都有**（CO 的「存储系统」讲段页式虚拟存储器，
        # OS 的「内存管理」讲段页式存储管理），所以两边都收录 —— 不收窄到单科，
        # 但至少不让它退化成"全 4 科检索"。
        "段页式",
        "虚拟存储器",
        "存储层次",
        "co",
        "i/o",
        "io",
    ),
    "operating_system": (
        "操作系统",
        "进程",
        "线程",
        "进程调度",
        "死锁",
        "同步",
        "互斥",
        "信号量",
        "pv操作",
        "内存管理",
        "分页",
        "分段",
        "段页式",
        "虚拟内存",
        "虚拟存储器",
        "文件管理",
        "文件系统",
        # ★ 空闲空间管理的四个方法（空闲表法 / 空闲链表法 / 位示图法 / 成组链接法）都属
        #   OS 的「文件管理」，但词表原先一个都没收 ⇒ 这类查询要么退化成「全 4 科」、
        #   要么被 DS 的单字「图」误判走（探针 #19）。这里只收**语义无歧义**的 `位示图`
        #   （`空闲` 太宽，CO 的磁盘容量题也会含它，不收）。
        "位示图",
        "设备管理",
        "进程通信",
        "管道",
        "共享内存",
        "银行家算法",
        "页面置换",
        "lru",
        # ★ 「磁盘」**两科都有**（C1，2026-09-27）：CO 的「存储系统」讲磁盘容量/磁盘阵列，
        #   OS 的「文件管理」讲磁盘空闲空间管理（空闲表/空闲链表/位示图）、磁盘调度。
        #   原先只收在 CO ⇒ 「磁盘空闲空间管理」这类查询被**收窄到只搜 CO**，
        #   而答案在 `operating_system/04_文件管理.md` ⇒ 目标 chunk **从不进召回池**
        #   （探针 #9 实测 dropped_by = not_recalled）。
        #   按本表既有先例（`段页式` / `虚拟存储器` 同样两科都收）两边都收录 ——
        #   不收窄到单科，但也不让它退化成「全 4 科检索」。
        "磁盘",
        "磁盘调度",
        "作业调度",
        "进程状态",
        "就绪",
        "阻塞",
        "时间片",
        "os",
        "pv",
        "p/v",
        "管程",
        "monitor",
        "spooling",
        "spooling技术",
        "fcfs",
        "sjf",
        "rr",
    ),
    "computer_network": (
        "计网",
        "计算机网络",
        "物理层",
        "数据链路层",
        "网络层",
        "传输层",
        "应用层",
        "tcp",
        "udp",
        "ip地址",
        "http",
        "dns",
        "拥塞控制",
        "以太网",
        "三次握手",
        "四次挥手",
        "滑动窗口",
        "子网掩码",
        "mac地址",
        "arp",
        "csma",
        "路由协议",
        "ospf",
        "rip",
        "bgp",
        "nat",
        "dhcp",
        "icmp",
        "曼彻斯特",
        "波特率",
        "带宽",
        "时延",
        "吞吐量",
        "cidr",
        "无类域间路由",
        "tcp/ip",
        "ipv4",
        "ipv6",
        "mtu",
        "mss",
        "rtt",
        "crc",
        "hdlc",
        "ppp",
        "gbn",
        "sr",
    ),
}

# 所有集合的完整名单（用于验证/去重/全量遍历）
ALL_COLLECTIONS: list[str] = [
    *SUBJECT_COLLECTIONS,
    EXAMS_COLLECTION,
    LEARNING_PATHS_COLLECTION,
    *CODE_COLLECTION.values(),
]

__all__ = [
    "SUBJECT_COLLECTIONS",
    "EXAMS_COLLECTION",
    "LEARNING_PATHS_COLLECTION",
    "CODE_COLLECTION",
    "COLLECTION_KEYWORDS",
    "ALL_COLLECTIONS",
]
