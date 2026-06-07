"""统一同义词映射

单一数据源（Single Source of Truth），供以下模块复用：
- recall.py：查询扩展（正向 + 反向映射）
- knowledge_graph.py：Tier 1 同义词精确匹配
- cleaner.py：入库时同义词归一

映射关系：
  SYNONYM_MAP   — 原始映射：{变体/标准词: 标准词}（含自映射，cleaner 用）
  SYNONYM_FORWARD — 正向映射：{变体: 标准词}（不含自映射，recall/kg 用）
  SYNONYM_REVERSE — 反向映射：{标准词: [所有变体]}（recall 扩展用）
"""

from __future__ import annotations

import re

# ── 原始同义词表（唯一维护点） ──────────────────────
# key = 变体或标准词, value = 标准词
# 自映射条目（如 "大语言模型": "大语言模型"）用于 cleaner 归一时不丢失
_SYNONYM_RAW: dict[str, str] = {
    # ── 数据结构 ──
    "DS": "数据结构",
    "数据结构": "数据结构",
    "BST": "二叉搜索树",
    "BST树": "二叉搜索树",
    "二叉搜索树": "二叉搜索树",
    "二叉排序树": "二叉搜索树",
    "二叉查找树": "二叉搜索树",
    "AVL": "平衡二叉树",
    "AVL树": "平衡二叉树",
    "平衡树": "平衡二叉树",
    "平衡二叉树": "平衡二叉树",
    "RBT": "红黑树",
    "红黑树": "红黑树",
    "B-树": "B树",
    "B Tree": "B树",
    "B树": "B树",
    "B+ Tree": "B+树",
    "B+树": "B+树",
    "Hash表": "散列表",
    "哈希表": "散列表",
    "散列表": "散列表",
    "Hash": "散列表",
    "哈希": "散列",
    "散列": "散列",
    "DFS": "深度优先搜索",
    "深搜": "深度优先搜索",
    "深度优先搜索": "深度优先搜索",
    "BFS": "广度优先搜索",
    "广搜": "广度优先搜索",
    "广度优先搜索": "广度优先搜索",
    "KMP": "KMP算法",
    "KMP算法": "KMP算法",
    "线性表": "线性表",
    "顺序表": "顺序表",
    "链表": "链表",
    "单链表": "单链表",
    "双向链表": "双向链表",
    "循环链表": "循环链表",
    "栈": "栈",
    "队列": "队列",
    "循环队列": "循环队列",
    "优先队列": "优先队列",
    "堆": "堆",
    "大根堆": "大根堆",
    "小根堆": "小根堆",
    "图": "图",
    "有向图": "有向图",
    "无向图": "无向图",
    "邻接矩阵": "邻接矩阵",
    "邻接表": "邻接表",
    "最小生成树": "最小生成树",
    "MST": "最小生成树",
    "最短路径": "最短路径",
    "Dijkstra": "Dijkstra算法",
    "Dijkstra算法": "Dijkstra算法",
    "迪杰斯特拉": "Dijkstra算法",
    "Floyd": "Floyd算法",
    "Floyd算法": "Floyd算法",
    "弗洛伊德": "Floyd算法",
    "Prim": "Prim算法",
    "Prim算法": "Prim算法",
    "普里姆": "Prim算法",
    "Kruskal": "Kruskal算法",
    "Kruskal算法": "Kruskal算法",
    "克鲁斯卡尔": "Kruskal算法",
    "拓扑排序": "拓扑排序",
    "AOV": "AOV网",
    "AOV网": "AOV网",
    "AOE": "AOE网",
    "AOE网": "AOE网",
    "关键路径": "关键路径",
    "排序": "排序",
    "快排": "快速排序",
    "快速排序": "快速排序",
    "归并排序": "归并排序",
    "冒泡排序": "冒泡排序",
    "插入排序": "插入排序",
    "选择排序": "选择排序",
    "希尔排序": "希尔排序",
    "基数排序": "基数排序",
    "查找": "查找",
    "二分查找": "二分查找",
    "折半查找": "二分查找",
    "线索二叉树": "线索二叉树",
    "哈夫曼树": "哈夫曼树",
    "哈夫曼编码": "哈夫曼编码",
    "并查集": "并查集",
    # ── 计算机组成原理 ──
    "CO": "计算机组成原理",
    "计组": "计算机组成原理",
    "计算机组成原理": "计算机组成原理",
    "CPU": "中央处理器",
    "中央处理器": "中央处理器",
    "ALU": "算术逻辑单元",
    "算术逻辑单元": "算术逻辑单元",
    "CU": "控制单元",
    "控制单元": "控制单元",
    "Cache": "高速缓存",
    "缓存": "高速缓存",
    "Cache存储器": "高速缓存",
    "高速缓存": "高速缓存",
    "I/O": "输入输出",
    "IO": "输入输出",
    "输入输出": "输入输出",
    "DMA": "直接存储器存取",
    "直接存储器存取": "直接存储器存取",
    "PCB": "进程控制块",
    "进程控制块": "进程控制块",
    "PC": "程序计数器",
    "程序计数器": "程序计数器",
    "IR": "指令寄存器",
    "指令寄存器": "指令寄存器",
    "MAR": "存储器地址寄存器",
    "存储器地址寄存器": "存储器地址寄存器",
    "MDR": "存储器数据寄存器",
    "存储器数据寄存器": "存储器数据寄存器",
    "PSW": "程序状态字",
    "程序状态字": "程序状态字",
    "TLB": "快表",
    "快表": "快表",
    "慢表": "慢表",
    "页表": "页表",
    "段表": "段表",
    "流水线": "指令流水线",
    "指令流水线": "指令流水线",
    "中断": "中断",
    "中断处理": "中断处理",
    "总线": "总线",
    "系统总线": "系统总线",
    "数据总线": "数据总线",
    "地址总线": "地址总线",
    "控制总线": "控制总线",
    "寻址方式": "寻址方式",
    "指令系统": "指令系统",
    "CISC": "CISC",
    "RISC": "RISC",
    "浮点数": "浮点数",
    "定点数": "定点数",
    "补码": "补码",
    "原码": "原码",
    "反码": "反码",
    "移码": "移码",
    "溢出": "溢出",
    "主存": "主存储器",
    "主存储器": "主存储器",
    "辅存": "辅助存储器",
    "辅助存储器": "辅助存储器",
    "虚拟内存": "虚拟存储器",
    "虚拟存储器": "虚拟存储器",
    "虚存": "虚拟存储器",
    "存储器": "存储器",
    "SRAM": "SRAM",
    "DRAM": "DRAM",
    "ROM": "ROM",
    "EPROM": "EPROM",
    # ── 操作系统 ──
    "OS": "操作系统",
    "操作系统": "操作系统",
    "进程": "进程",
    "线程": "线程",
    "PV操作": "信号量操作",
    "PV": "信号量操作",
    "P/V": "信号量操作",
    "P/V操作": "信号量操作",
    "信号量操作": "信号量操作",
    "P操作": "P操作",
    "V操作": "V操作",
    "信号量": "信号量",
    "临界区": "临界区",
    "临界资源": "临界资源",
    "管程": "管程",
    "Monitor": "管程",
    "互斥": "互斥",
    "同步": "同步",
    "死锁": "死锁",
    "死锁预防": "死锁预防",
    "死锁避免": "死锁避免",
    "死锁检测": "死锁检测",
    "死锁恢复": "死锁恢复",
    "银行家算法": "银行家算法",
    "分页": "分页存储",
    "分段": "分段存储",
    "分页存储": "分页存储",
    "分段存储": "分段存储",
    "段页式": "段页式存储",
    "段页式存储": "段页式存储",
    "页面置换": "页面置换算法",
    "页面置换算法": "页面置换算法",
    "FIFO": "FIFO置换算法",
    "FIFO置换算法": "FIFO置换算法",
    "LRU": "LRU置换算法",
    "LRU置换算法": "LRU置换算法",
    "LFU": "LFU置换算法",
    "LFU置换算法": "LFU置换算法",
    "OPT": "最佳置换算法",
    "最佳置换算法": "最佳置换算法",
    "抖动": "抖动",
    "缺页": "缺页中断",
    "缺页中断": "缺页中断",
    "调度": "调度",
    "进程调度": "进程调度",
    "作业调度": "作业调度",
    "磁盘调度": "磁盘调度",
    "FCFS": "先来先服务",
    "FCFS调度": "先来先服务",
    "先来先服务": "先来先服务",
    "SJF": "短作业优先",
    "SJF调度": "短作业优先",
    "短作业优先": "短作业优先",
    "RR": "时间片轮转",
    "RR调度": "时间片轮转",
    "时间片轮转": "时间片轮转",
    "优先级调度": "优先级调度",
    "多级反馈队列": "多级反馈队列",
    "文件系统": "文件系统",
    "索引节点": "索引节点",
    "inode": "索引节点",
    "FAT": "FAT",
    "磁盘": "磁盘",
    "扇区": "扇区",
    "磁道": "磁道",
    "柱面": "柱面",
    "SPOOL": "SPOOLing技术",
    "Spooling": "SPOOLing技术",
    "SPOOLing": "SPOOLing技术",
    "SPOOLing技术": "SPOOLing技术",
    "用户态": "用户态",
    "内核态": "内核态",
    "系统调用": "系统调用",
    # ── 计算机网络 ──
    "CN": "计算机网络",
    "计网": "计算机网络",
    "计算机网络": "计算机网络",
    "TCP": "传输控制协议",
    "TCP/IP": "TCP/IP协议",
    "TCP/IP协议": "TCP/IP协议",
    "传输控制协议": "传输控制协议",
    "UDP": "用户数据报协议",
    "用户数据报协议": "用户数据报协议",
    "IP": "网际协议",
    "MAC": "介质访问控制",
    "ARP": "地址解析协议",
    "地址解析协议": "地址解析协议",
    "RARP": "逆地址解析协议",
    "逆地址解析协议": "逆地址解析协议",
    "ICMP": "网际控制报文协议",
    "网际控制报文协议": "网际控制报文协议",
    "DNS": "域名系统",
    "域名系统": "域名系统",
    "HTTP": "超文本传输协议",
    "HTTPS": "安全超文本传输协议",
    "安全超文本传输协议": "安全超文本传输协议",
    "FTP": "文件传输协议",
    "文件传输协议": "文件传输协议",
    "SMTP": "简单邮件传输协议",
    "简单邮件传输协议": "简单邮件传输协议",
    "POP3": "邮局协议",
    "IMAP": "互联网消息访问协议",
    "DHCP": "动态主机配置协议",
    "动态主机配置协议": "动态主机配置协议",
    "NAT": "网络地址转换",
    "网络地址转换": "网络地址转换",
    "OSPF": "开放最短路径优先",
    "开放最短路径优先": "开放最短路径优先",
    "BGP": "边界网关协议",
    "边界网关协议": "边界网关协议",
    "RIP": "路由信息协议",
    "路由信息协议": "路由信息协议",
    "子网掩码": "子网掩码",
    "子网划分": "子网划分",
    "CIDR": "无类域间路由",
    "无类域间路由": "无类域间路由",
    "IPv4": "IPv4",
    "IPv6": "IPv6",
    "三次握手": "TCP三次握手",
    "TCP三次握手": "TCP三次握手",
    "四次挥手": "TCP四次挥手",
    "TCP四次挥手": "TCP四次挥手",
    "滑动窗口": "滑动窗口",
    "拥塞控制": "拥塞控制",
    "慢开始": "慢开始",
    "拥塞避免": "拥塞避免",
    "快重传": "快重传",
    "快恢复": "快恢复",
    "CSMA/CD": "CSMA/CD协议",
    "CSMA": "CSMA/CD协议",
    "CSMA/CD协议": "CSMA/CD协议",
    "以太网": "以太网",
    "集线器": "集线器",
    "交换机": "交换机",
    "路由器": "路由器",
    "网桥": "网桥",
    "物理层": "物理层",
    "数据链路层": "数据链路层",
    "网络层": "网络层",
    "传输层": "传输层",
    "应用层": "应用层",
    "OSI": "OSI参考模型",
    "OSI参考模型": "OSI参考模型",
    "协议栈": "协议栈",
    "端口号": "端口号",
    "套接字": "套接字",
    "Socket": "套接字",
    "MTU": "最大传输单元",
    "最大传输单元": "最大传输单元",
    "MSS": "最大报文段长度",
    "最大报文段长度": "最大报文段长度",
    "RTT": "往返时延",
    "往返时延": "往返时延",
    "CRC": "循环冗余校验",
    "循环冗余校验": "循环冗余校验",
    "HDLC": "HDLC协议",
    "HDLC协议": "HDLC协议",
    "PPP": "PPP协议",
    "PPP协议": "PPP协议",
    "GBN": "回退N帧协议",
    "回退N帧协议": "回退N帧协议",
    "SR": "选择重传协议",
    "选择重传协议": "选择重传协议",
    "带宽": "带宽",
    "时延": "时延",
    "吞吐量": "吞吐量",
    "分组交换": "分组交换",
    "电路交换": "电路交换",
    "报文交换": "报文交换",
    # ── 通用 ──
    "KG": "知识图谱",
    "知识图谱": "知识图谱",
    "RAG": "检索增强生成",
    "检索增强生成": "检索增强生成",
    "LLM": "大语言模型",
    "大语言模型": "大语言模型",
    "大模型": "大语言模型",
    "NLP": "自然语言处理",
    "自然语言处理": "自然语言处理",
    "AI": "人工智能",
    "人工智能": "人工智能",
}

# ── 派生映射 ──────────────────────────────────────────

# cleaner 用：含自映射的完整映射
SYNONYM_MAP: dict[str, str] = dict(_SYNONYM_RAW)
SYNONYM_MAP_CASEFOLD: dict[str, str] = {k.casefold(): v for k, v in SYNONYM_MAP.items()}

# recall / kg 用：正向映射（不含自映射）
SYNONYM_FORWARD: dict[str, str] = {k: v for k, v in _SYNONYM_RAW.items() if k != v}
SYNONYM_FORWARD_CASEFOLD: dict[str, str] = {k.casefold(): v for k, v in SYNONYM_FORWARD.items()}

# recall 用：反向映射（标准词 → 所有变体列表）
SYNONYM_REVERSE: dict[str, list[str]] = {}
for _k, _v in _SYNONYM_RAW.items():
    if _k != _v:
        SYNONYM_REVERSE.setdefault(_v, [])
        if _k not in SYNONYM_REVERSE[_v]:
            SYNONYM_REVERSE[_v].append(_k)

# recall 用：预编译正则（按长度降序，避免短词先匹配）
_SYNONYM_EXPAND_KEYS = sorted(SYNONYM_MAP.keys(), key=len, reverse=True)
SYNONYM_EXPAND_RE: re.Pattern[str] = re.compile(
    "|".join(re.escape(k) for k in _SYNONYM_EXPAND_KEYS), re.IGNORECASE
) if _SYNONYM_EXPAND_KEYS else re.compile(r"(?!)", re.IGNORECASE)


def _lookup_standard(term: str) -> str:
    return SYNONYM_MAP.get(term) or SYNONYM_MAP_CASEFOLD.get(term.casefold()) or ""


def _is_embedded_ascii_match(text: str, match: re.Match) -> bool:
    matched = match.group(0)
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_./+-]*", matched):
        return False
    start, end = match.span()
    prev_char = text[start - 1] if start > 0 else ""
    next_char = text[end] if end < len(text) else ""
    return bool(
        (prev_char and re.fullmatch(r"[A-Za-z0-9_]", prev_char))
        or (next_char and re.fullmatch(r"[A-Za-z0-9_]", next_char))
    )


def expand_query_with_synonyms(query: str, max_expansions: int = 8) -> str:
    """同义词查询扩展：将用户查询中的术语扩展为所有同义表述

    例："什么是OS" → "什么是OS 操作系统"
    """
    # 使用共享的 extract_query_terms 获取已有 token（避免重复 jieba 调用）
    from app.rag.rag_utils import extract_query_terms
    existing = {t.casefold() for t in extract_query_terms(query)}
    # 补充英文缩写
    for t in re.findall(r"[A-Za-z_][A-Za-z0-9_\.]{0,}", query):
        existing.add(t.casefold())

    query_lower = query.casefold()
    # 标准词已是 query 子串 → 不重复追加
    for m in SYNONYM_EXPAND_RE.finditer(query):
        if _is_embedded_ascii_match(query, m):
            continue
        std = _lookup_standard(m.group(0))
        if std and std.casefold() in query_lower:
            existing.add(std.casefold())

    expansions: list[str] = []
    seen: set[str] = set()

    def _add(term: str) -> None:
        if len(expansions) >= max_expansions:
            return
        lower = term.casefold()
        if lower not in seen and lower not in existing:
            seen.add(lower)
            expansions.append(term)

    for m in SYNONYM_EXPAND_RE.finditer(query):
        if _is_embedded_ascii_match(query, m):
            continue
        matched = m.group(0)
        standard = _lookup_standard(matched)
        if not standard:
            continue
        _add(standard)
        for variant in SYNONYM_REVERSE.get(standard, []):
            _add(variant)
        if len(expansions) >= max_expansions:
            break

    if not expansions:
        return query
    return query + " " + " ".join(expansions)


# 预编译：normalize_synonyms 用正则（模块加载时构建一次）
_SYNONYM_NORM_KEYS = sorted(SYNONYM_MAP.keys(), key=len, reverse=True)
SYNONYM_NORM_RE = re.compile("|".join(re.escape(k) for k in _SYNONYM_NORM_KEYS)) if _SYNONYM_NORM_KEYS else re.compile(r"(?!)")


def normalize_synonyms(text: str) -> tuple[str, int]:
    """同义词归一：将文本中的同义表述替换为标准术语"""
    count = 0

    def _replace(m: re.Match) -> str:
        nonlocal count
        count += 1
        return SYNONYM_MAP[m.group(0)]

    result = SYNONYM_NORM_RE.sub(_replace, text)
    return result, count


def expand_synonyms_for_kg(topic: str) -> list[str]:
    """将 topic 通过同义词表扩展为所有标准词变体（knowledge_graph 用）

    Args:
        topic: 待扩展的主题词

    Returns:
        所有同义变体列表（含标准词自身）
    """
    results: list[str] = []
    # 正向映射：topic → 标准词
    standard = SYNONYM_FORWARD.get(topic)
    if standard:
        results.append(standard)
    # topic 本身也可能是标准词，收集所有映射到它的变体
    for variant, std in SYNONYM_MAP.items():
        if std == topic and variant != topic:
            results.append(variant)
    return results
