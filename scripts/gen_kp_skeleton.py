"""生成四科 Knowledge Point 骨架（level 1–3）到 knowledge_points/*.jsonl。

原则：
- 考纲/讲义章节 → level 2 domain
- 主要考点 → level 3 topic/point
- id 英文 slug 冻结；name 中文
"""

from __future__ import annotations

import json
from pathlib import Path

OUT = Path(r"C:\Users\26452\Desktop\edu-agent\knowledge\knowledge_points")
OUT.mkdir(parents=True, exist_ok=True)

# (id, name, parent, level, node_kind, type, importance, question_types, aliases, tags)


def n(
    id: str,
    name: str,
    parent: str | None,
    level: int,
    kind: str,
    typ: str,
    imp: str = "major",
    qtypes: list[str] | None = None,
    aliases: list[str] | None = None,
    tags: list[str] | None = None,
) -> dict:
    return {
        "id": id,
        "name": name,
        "subject": id.split(".", 1)[0],
        "parent_id": parent,
        "level": level,
        "node_kind": kind,
        "type": typ,
        "importance": imp,
        "question_types": qtypes or ["choice"],
        "aliases": aliases or [],
        "tags": tags or [],
        "status": "active",
    }


CHOICE_CALC = ["choice", "calculation"]
CHOICE = ["choice"]
CHOICE_CODE = ["choice", "code"]
ALL = ["choice", "calculation", "comprehensive", "code"]

ds = [
    n("ds", "数据结构", None, 1, "subject", "concept", "core", ["choice"]),
    # 线性表
    n("ds.linear", "线性表", "ds", 2, "domain", "structure"),
    n("ds.linear.list", "线性表", "ds.linear", 3, "topic", "structure"),
    n("ds.linear.seq_list", "顺序表", "ds.linear", 3, "point", "structure", qtypes=CHOICE_CODE),
    n("ds.linear.linked_list", "链表", "ds.linear", 3, "point", "structure", qtypes=CHOICE_CODE),
    n("ds.linear.doubly_linked", "双链表", "ds.linear.linked_list", 4, "point", "structure"),
    n("ds.linear.circular_linked", "循环链表", "ds.linear.linked_list", 4, "point", "structure"),
    # 栈和队列
    n("ds.stack_queue", "栈和队列", "ds", 2, "domain", "structure"),
    n("ds.stack_queue.stack", "栈", "ds.stack_queue", 3, "topic", "structure"),
    n("ds.stack_queue.queue", "队列", "ds.stack_queue", 3, "topic", "structure"),
    n("ds.stack_queue.circular_queue", "循环队列", "ds.stack_queue.queue", 4, "point", "structure"),
    n(
        "ds.stack_queue.match",
        "括号匹配",
        "ds.stack_queue.stack",
        4,
        "point",
        "method",
        qtypes=CHOICE_CODE,
    ),
    # 特殊矩阵
    n("ds.array", "数组与特殊矩阵", "ds", 2, "domain", "structure"),
    n("ds.array.compressed", "压缩存储", "ds.array", 3, "topic", "structure", qtypes=CHOICE_CALC),
    n("ds.array.symmetric", "对称矩阵", "ds.array.compressed", 4, "point", "structure"),
    n("ds.array.triangular", "三角矩阵", "ds.array.compressed", 4, "point", "structure"),
    n("ds.array.sparse", "稀疏矩阵", "ds.array.compressed", 4, "point", "structure"),
    # 串
    n("ds.string", "串", "ds", 2, "domain", "structure"),
    n("ds.string.match", "模式匹配", "ds.string", 3, "topic", "algorithm"),
    n(
        "ds.string.kmp",
        "KMP 算法",
        "ds.string.match",
        4,
        "point",
        "algorithm",
        "core",
        ALL,
        ["KMP"],
    ),
    # 树
    n("ds.tree", "树与二叉树", "ds", 2, "domain", "structure"),
    n("ds.tree.binary_tree", "二叉树", "ds.tree", 3, "topic", "structure"),
    n(
        "ds.tree.traversal",
        "二叉树遍历",
        "ds.tree.binary_tree",
        4,
        "point",
        "algorithm",
        "core",
        ALL,
    ),
    n("ds.tree.threaded", "线索二叉树", "ds.tree.binary_tree", 4, "point", "structure"),
    n(
        "ds.tree.forest_convert",
        "树与森林转换",
        "ds.tree",
        3,
        "point",
        "method",
        "major",
        CHOICE_CALC,
    ),
    n(
        "ds.tree.huffman",
        "哈夫曼编码",
        "ds.tree",
        3,
        "point",
        "algorithm",
        "core",
        CHOICE_CALC,
        ["哈夫曼树"],
    ),
    n(
        "ds.tree.bst",
        "二叉排序树 BST",
        "ds.tree",
        3,
        "point",
        "structure",
        "core",
        ALL,
        ["二叉查找树"],
    ),
    n("ds.tree.avl", "平衡二叉树 AVL", "ds.tree", 3, "point", "structure", "core", ALL),
    # 图
    n("ds.graph", "图", "ds", 2, "domain", "structure"),
    n("ds.graph.storage", "图的存储", "ds.graph", 3, "topic", "structure"),
    n("ds.graph.traversal", "图的遍历", "ds.graph", 3, "point", "algorithm", "core", ALL),
    n(
        "ds.graph.mst",
        "最小生成树",
        "ds.graph",
        3,
        "point",
        "algorithm",
        "core",
        CHOICE_CALC,
        ["Prim", "Kruskal"],
    ),
    n(
        "ds.graph.shortest_path",
        "最短路径",
        "ds.graph",
        3,
        "point",
        "algorithm",
        "core",
        CHOICE_CALC,
        ["Dijkstra", "Floyd"],
    ),
    n("ds.graph.topo", "拓扑排序", "ds.graph", 3, "point", "algorithm", "core", ALL),
    n("ds.graph.aoe", "AOE 关键路径", "ds.graph", 3, "point", "algorithm", "major", CHOICE_CALC),
    # 查找
    n("ds.search", "查找", "ds", 2, "domain", "algorithm"),
    n(
        "ds.search.binary_search",
        "折半查找",
        "ds.search",
        3,
        "point",
        "algorithm",
        "core",
        ALL,
        ["二分查找", "Binary Search"],
    ),
    n("ds.search.b_tree", "B 树", "ds.search", 3, "point", "structure", "core", ALL, ["B树"]),
    n("ds.search.b_plus_tree", "B+ 树", "ds.search", 3, "point", "structure", "major", ALL),
    n("ds.search.hash", "散列表", "ds.search", 3, "point", "structure", "core", ALL, ["哈希表"]),
    # 排序
    n("ds.sort", "排序", "ds", 2, "domain", "algorithm"),
    n("ds.sort.insertion", "插入排序", "ds.sort", 3, "point", "algorithm"),
    n("ds.sort.shell", "希尔排序", "ds.sort", 3, "point", "algorithm"),
    n("ds.sort.bubble", "冒泡排序", "ds.sort", 3, "point", "algorithm"),
    n("ds.sort.quick_sort", "快速排序", "ds.sort", 3, "point", "algorithm", "core", ALL),
    n("ds.sort.select", "简单选择排序", "ds.sort", 3, "point", "algorithm"),
    n("ds.sort.heap", "堆排序", "ds.sort", 3, "point", "algorithm", "core", ALL),
    n("ds.sort.merge", "归并排序", "ds.sort", 3, "point", "algorithm", "core", ALL),
    n("ds.sort.radix", "基数排序", "ds.sort", 3, "point", "algorithm"),
]

co = [
    n("co", "计算机组成原理", None, 1, "subject", "concept", "core", ["choice"]),
    n("co.overview", "计算机系统概述", "co", 2, "domain", "concept"),
    n(
        "co.overview.performance",
        "性能指标",
        "co.overview",
        3,
        "point",
        "concept",
        "core",
        CHOICE_CALC,
        ["CPI", "CPU 时间"],
    ),
    n("co.overview.von_neumann", "冯·诺依曼结构", "co.overview", 3, "point", "concept"),
    # 数据表示
    n("co.representation", "数据表示与运算", "co", 2, "domain", "concept"),
    n(
        "co.representation.integer",
        "整数表示",
        "co.representation",
        3,
        "topic",
        "concept",
        "core",
        CHOICE_CALC,
    ),
    n(
        "co.representation.fixed_point",
        "定点数",
        "co.representation.integer",
        4,
        "point",
        "concept",
    ),
    n(
        "co.representation.complement",
        "补码",
        "co.representation.integer",
        4,
        "point",
        "concept",
        "core",
        ALL,
        ["原码", "反码"],
    ),
    n(
        "co.representation.ieee754",
        "IEEE 浮点数",
        "co.representation",
        3,
        "point",
        "concept",
        "core",
        ALL,
        ["浮点数", "阶码", "尾数"],
    ),
    n(
        "co.representation.alu",
        "定点运算",
        "co.representation",
        3,
        "point",
        "algorithm",
        "major",
        CHOICE_CALC,
    ),
    # 存储
    n("co.storage", "存储系统", "co", 2, "domain", "structure"),
    n("co.storage.hierarchy", "存储层次", "co.storage", 3, "topic", "concept"),
    n(
        "co.storage.cache",
        "Cache",
        "co.storage",
        3,
        "point",
        "structure",
        "core",
        ALL,
        ["高速缓存"],
    ),
    n(
        "co.storage.cache_mapping",
        "Cache 映射",
        "co.storage.cache",
        4,
        "point",
        "method",
        "core",
        ALL,
    ),
    n("co.storage.cache_replace", "替换算法", "co.storage.cache", 4, "point", "algorithm"),
    n(
        "co.storage.main_memory",
        "主存",
        "co.storage",
        3,
        "point",
        "structure",
        "major",
        CHOICE_CALC,
    ),
    n("co.storage.virtual_memory", "虚拟存储器", "co.storage", 3, "point", "concept", "major", ALL),
    # 指令
    n("co.instruction", "指令系统", "co", 2, "domain", "concept"),
    n("co.instruction.format", "指令格式", "co.instruction", 3, "topic", "concept"),
    n(
        "co.instruction.addressing",
        "寻址方式",
        "co.instruction",
        3,
        "point",
        "concept",
        "core",
        ALL,
    ),
    n(
        "co.instruction.isa",
        "指令体系结构 ISA",
        "co.instruction",
        3,
        "point",
        "concept",
        "major",
        CHOICE,
    ),
    n(
        "co.instruction.risc_cisc",
        "RISC 与 CISC",
        "co.instruction",
        3,
        "point",
        "concept",
        "major",
        CHOICE,
    ),
    # CPU
    n("co.cpu", "中央处理器", "co", 2, "domain", "structure"),
    n("co.cpu.datapath", "数据通路", "co.cpu", 3, "topic", "structure"),
    n(
        "co.cpu.controller",
        "控制器",
        "co.cpu",
        3,
        "point",
        "structure",
        "core",
        ALL,
        ["微程序", "硬布线"],
    ),
    n(
        "co.cpu.pipeline",
        "指令流水线",
        "co.cpu",
        3,
        "point",
        "concept",
        "core",
        ALL,
        ["流水线", "冒险"],
    ),
    n(
        "co.cpu.pipeline_hazard",
        "流水线冒险",
        "co.cpu.pipeline",
        4,
        "point",
        "concept",
        "core",
        ALL,
    ),
    n("co.cpu.exception", "中断与异常", "co.cpu", 3, "point", "concept", "core", ALL),
    # 总线
    n("co.bus", "总线", "co", 2, "domain", "structure"),
    n("co.bus.bandwidth", "总线带宽", "co.bus", 3, "point", "concept", "core", CHOICE_CALC),
    n("co.bus.arbitration", "总线仲裁", "co.bus", 3, "point", "concept"),
    # IO
    n("co.io", "输入输出系统", "co", 2, "domain", "structure"),
    n("co.io.interface", "I/O 接口", "co.io", 3, "topic", "structure"),
    n("co.io.mode", "I/O 方式", "co.io", 3, "point", "concept", "core", ALL, ["程序中断", "DMA"]),
    n("co.io.dma", "DMA", "co.io.mode", 4, "point", "concept", "core", ALL),
]

os = [
    n("os", "操作系统", None, 1, "subject", "concept", "core", ["choice"]),
    n("os.overview", "操作系统概述", "os", 2, "domain", "concept"),
    n("os.overview.feature", "基本特征", "os.overview", 3, "point", "concept"),
    n("os.overview.syscall", "系统调用", "os.overview", 3, "point", "concept", "core", ALL),
    n("os.overview.mode", "内核态与用户态", "os.overview", 3, "point", "concept", "core", ALL),
    # 进程
    n("os.process", "进程管理", "os", 2, "domain", "concept"),
    n("os.process.thread", "进程与线程", "os.process", 3, "topic", "concept", "core", ALL),
    n("os.process.state", "进程状态与转换", "os.process", 3, "point", "concept", "core", ALL),
    n(
        "os.process.schedule",
        "处理机调度",
        "os.process",
        3,
        "point",
        "algorithm",
        "core",
        ALL,
        ["CPU 调度"],
    ),
    n("os.process.sync", "进程同步", "os.process", 3, "topic", "concept", "core", ALL),
    n("os.process.deadlock", "死锁", "os.process", 3, "point", "concept", "core", ALL),
    n(
        "os.process.pv",
        "信号量与 PV",
        "os.process.sync",
        4,
        "point",
        "method",
        "core",
        ALL,
        ["生产者消费者"],
    ),
    n(
        "os.process.bankers",
        "银行家算法",
        "os.process.deadlock",
        4,
        "point",
        "algorithm",
        "core",
        ALL,
    ),
    # 内存
    n("os.memory", "内存管理", "os", 2, "domain", "concept"),
    n("os.memory.allocate", "内存分配", "os.memory", 3, "topic", "method"),
    n(
        "os.memory.partition",
        "分区分配",
        "os.memory.allocate",
        4,
        "point",
        "method",
        "major",
        ALL,
        ["动态分区"],
    ),
    n("os.memory.paging", "分页管理", "os.memory", 3, "point", "concept", "core", ALL),
    n("os.memory.segmentation", "分段管理", "os.memory", 3, "point", "concept", "core", ALL),
    n("os.memory.virtual", "虚拟内存", "os.memory", 3, "point", "concept", "core", ALL),
    n("os.memory.page_fault", "缺页异常", "os.memory.virtual", 4, "point", "concept", "core", ALL),
    n(
        "os.memory.page_replace",
        "页面置换算法",
        "os.memory.virtual",
        4,
        "point",
        "algorithm",
        "core",
        ALL,
    ),
    n("os.memory.tlb", "TLB 快表", "os.memory.paging", 4, "point", "structure", "major", ALL),
    # 文件
    n("os.file", "文件管理", "os", 2, "domain", "concept"),
    n("os.file.logical", "文件逻辑结构", "os.file", 3, "topic", "concept"),
    n("os.file.physical", "文件物理结构", "os.file", 3, "topic", "structure"),
    n(
        "os.file.alloc",
        "文件分配方式",
        "os.file.physical",
        4,
        "point",
        "method",
        "core",
        ALL,
        ["连续分配", "链接分配", "索引分配"],
    ),
    n("os.file.dir", "目录", "os.file", 3, "point", "structure"),
    n(
        "os.file.disk_free_space",
        "磁盘空闲空间管理",
        "os.file.physical",
        3,
        "point",
        "method",
        "core",
        ALL,
        ["位示图", "空闲表", "空闲链表"],
        ["易错"],
    ),
    n("os.file.disk_schedule", "磁盘调度", "os.file", 3, "point", "algorithm", "core", ALL),
    # IO
    n("os.io", "输入输出管理", "os", 2, "domain", "concept"),
    n("os.io.software", "I/O 软件层次", "os.io", 3, "topic", "concept"),
    n("os.io.buffer", "缓冲管理", "os.io", 3, "point", "concept", "major", ALL),
    n("os.io.device", "设备管理", "os.io", 3, "point", "concept", "major", ALL),
]

cn = [
    n("cn", "计算机网络", None, 1, "subject", "concept", "core", ["choice"]),
    n("cn.arch", "体系结构", "cn", 2, "domain", "concept"),
    n(
        "cn.arch.model",
        "网络体系结构",
        "cn.arch",
        3,
        "topic",
        "concept",
        "core",
        ALL,
        ["OSI", "TCP/IP"],
    ),
    n(
        "cn.arch.performance",
        "网络性能指标",
        "cn.arch",
        3,
        "point",
        "concept",
        "major",
        CHOICE_CALC,
    ),
    # 物理层
    n("cn.physical", "物理层", "cn", 2, "domain", "concept"),
    n("cn.physical.channel", "信道与传输", "cn.physical", 3, "topic", "concept"),
    n("cn.physical.medium", "传输介质", "cn.physical", 3, "point", "concept"),
    n(
        "cn.physical.bandwidth",
        "信道容量",
        "cn.physical",
        3,
        "point",
        "concept",
        "major",
        CHOICE_CALC,
        ["奈氏", "香农"],
    ),
    # 数据链路层
    n("cn.datalink", "数据链路层", "cn", 2, "domain", "concept"),
    n("cn.datalink.framing", "成帧", "cn.datalink", 3, "topic", "concept"),
    n(
        "cn.datalink.error_control",
        "差错控制",
        "cn.datalink",
        3,
        "point",
        "algorithm",
        "core",
        ALL,
        ["CRC", "海明码"],
    ),
    n(
        "cn.datalink.flow_control",
        "流量控制",
        "cn.datalink",
        3,
        "point",
        "concept",
        "core",
        ALL,
        ["滑动窗口"],
    ),
    n(
        "cn.datalink.mac",
        "介质访问控制 MAC",
        "cn.datalink",
        3,
        "point",
        "concept",
        "core",
        ALL,
        ["CSMA/CD"],
    ),
    n("cn.datalink.ethernet", "以太网", "cn.datalink", 3, "point", "structure", "core", ALL),
    n("cn.datalink.vlan", "VLAN", "cn.datalink", 3, "point", "concept", "major"),
    # 网络层
    n("cn.network", "网络层", "cn", 2, "domain", "concept"),
    n("cn.network.ip", "IP 协议", "cn.network", 3, "topic", "protocol", "core", ALL),
    n(
        "cn.network.ip_address",
        "IP 地址与子网",
        "cn.network.ip",
        4,
        "point",
        "concept",
        "core",
        ALL,
        ["子网划分", "CIDR"],
    ),
    n(
        "cn.network.routing",
        "路由算法",
        "cn.network",
        3,
        "point",
        "algorithm",
        "core",
        ALL,
        ["RIP", "OSPF"],
    ),
    n("cn.network.arp", "ARP / ICMP", "cn.network", 3, "point", "protocol", "major", ALL),
    n("cn.network.nat", "NAT", "cn.network", 3, "point", "concept", "major"),
    n("cn.network.ipv6", "IPv6", "cn.network", 3, "point", "protocol", "minor"),
    # 传输层
    n("cn.transport", "传输层", "cn", 2, "domain", "protocol"),
    n("cn.transport.udp", "UDP", "cn.transport", 3, "point", "protocol", "major", ALL),
    n("cn.transport.tcp", "TCP", "cn.transport", 3, "topic", "protocol", "core", ALL),
    n(
        "cn.transport.tcp_handshake",
        "TCP 连接管理",
        "cn.transport.tcp",
        4,
        "point",
        "protocol",
        "core",
        ALL,
        ["三次握手", "四次挥手"],
    ),
    n(
        "cn.transport.tcp_flow",
        "TCP 流量与拥塞控制",
        "cn.transport.tcp",
        4,
        "point",
        "concept",
        "core",
        ALL,
    ),
    # 应用层
    n("cn.application", "应用层", "cn", 2, "domain", "protocol"),
    n("cn.application.dns", "DNS", "cn.application", 3, "point", "protocol", "core", ALL),
    n("cn.application.http", "HTTP", "cn.application", 3, "point", "protocol", "major", ALL),
    n(
        "cn.application.email",
        "电子邮件",
        "cn.application",
        3,
        "point",
        "protocol",
        "minor",
        ["choice"],
        ["SMTP", "POP3"],
    ),
    n("cn.application.ftp", "FTP", "cn.application", 3, "point", "protocol", "minor"),
]


def write_subject(code: str, nodes: list[dict]) -> None:
    path = OUT / f"{code}.jsonl"
    with path.open("w", encoding="utf-8") as f:
        for node in nodes:
            f.write(json.dumps(node, ensure_ascii=False) + "\n")
    print(f"{path.name}: {len(nodes)} nodes")


def main() -> int:
    write_subject("ds", ds)
    write_subject("co", co)
    write_subject("os", os)
    write_subject("cn", cn)
    # links 空文件占位
    links = OUT / "links.jsonl"
    if not links.exists():
        links.write_text("", encoding="utf-8")
    print("links.jsonl ready")
    print("TOTAL", sum(map(len, [ds, co, os, cn])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
