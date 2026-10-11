"""集合路由：学科关键词推断与集合路由解析（从 recall.py 拆出，行为等价）。"""

from __future__ import annotations

import re

from rag.common.rag_utils import extract_query_terms, normalize_query_text
from rag.common.synonyms import expand_query_with_synonyms
from rag.retrieval.query_classifier import QueryCategory, classify_query


def _contains_collection_keyword(text: str, keyword: str) -> bool:
    key = keyword.lower()
    if not key:
        return False
    if not re.fullmatch(r"[a-z0-9_./+-]+", key):
        return key in text
    return re.search(rf"(?<![a-z0-9_]){re.escape(key)}(?![a-z0-9_])", text) is not None


SUBJECT_COLLECTIONS = [
    "data_structure",
    "computer_organization",
    "operating_system",
    "computer_network",
]

# 学科集合 → 代码库集合（`knowledge/code/<科>/`）。代码类查询额外命中它。
_CODE_COLLECTION = {
    "data_structure": "code_ds",
    "computer_organization": "code_co",
    "operating_system": "code_os",
    "computer_network": "code_cn",
}

_COLLECTION_KEYWORDS = {
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


def _infer_subject_collections(query: str) -> list[str]:
    normalized = normalize_query_text(query).lower()
    expanded = expand_query_with_synonyms(normalized, max_expansions=6).lower()
    # 空格是**排版差异**、不是语义差异：关键词表里写的是 `ip地址` / `mac地址`，
    # 而查询常写成 `IP 地址` / `MAC 地址`。不做这一步，这类写法**一个关键词都匹配不上**
    # （实测 `'ip地址' in 'ip 地址与 mac 地址有什么区别？'` → False），
    # `resolve_collection_routes` 于是退化成「全 4 科检索」—— 学科收窄机制直接失效，
    # 错学科的文档得以挤进首条。去掉空格再匹配一次即可。
    compact = normalized.replace(" ", "")
    matched: list[str] = []
    for collection, keywords in _COLLECTION_KEYWORDS.items():
        if any(
            _contains_collection_keyword(normalized, keyword)
            or _contains_collection_keyword(expanded, keyword)
            or _contains_collection_keyword(compact, keyword)
            for keyword in keywords
        ):
            matched.append(collection)
    return matched


def resolve_collection_routes(
    query: str, collection_name: str, cat: QueryCategory | None = None
) -> list[str]:
    if collection_name:
        return [collection_name]

    # 默认：优先根据学科关键词缩小集合范围，避免每次跨 4 科全量多路召回
    normalized = normalize_query_text(query)
    terms = extract_query_terms(normalized)
    if cat is None:
        cat = classify_query(query, terms)
    collections = _infer_subject_collections(normalized) or list(SUBJECT_COLLECTIONS)

    if cat.is_exercise:
        collections.append("exams")
    # ★ 原先这里要求 `cat.is_structured and 含路径类词` —— **条件过严**：
    # 纯学习路径查询（如「408 应该怎么学」）`is_learning_path=True` 但 `is_structured=False`，
    # 于是拿不到 `learning_paths` 集合（24 chunk 对这类查询**完全不可达**）。
    # 正确的信号是 `cat.is_learning_path`（由 `_RULE_MARKERS["learning_path"]` 判定）；
    # 额外保留「路径 / 路线 / 学习计划」三个标记，是为了覆盖规则表未收录的写法（不丢原有覆盖面）。
    if cat.is_learning_path or any(marker in normalized for marker in ("路径", "路线", "学习计划")):
        collections.append("learning_paths")

    # 代码类查询：额外命中代码库（`code_<科>`），与四科讲义并列召回。
    # （原 `is_code` 曾指向从未创建的 `answers` 集合，见下方注释；现改为指向 code 库。）
    if getattr(cat, "is_code", False):
        for col in list(collections):
            code_col = _CODE_COLLECTION.get(col)
            if code_col:
                collections.append(code_col)

    # ⚠️ 这里曾有两条对 `answers` 集合的引用（`is_answer` 与 `is_code` 时追加），
    # 但**该集合从未被创建**：`knowledge/` 下无 `answers/` 目录，
    # `ingest.DEFAULT_CATEGORIES` 也不含它。实测每次命中都抛
    # `Collection [answers] does not exist` —— 白花一次 Chroma 往返，
    # 且这条 WARNING 与「真实集合故障」长得**一模一样**，会掩盖真信号。
    # 2026-09-24 移除。若将来真要建 `answers` 集合（存标准答案供批改），
    # 需连同入库配置一起加回，不要只改这里。
    # 注：`is_code` 原本也指向 `answers` —— 语义上本就不通（代码内容在 4 科集合的
    # `code_mixed` chunk 里），一并去掉。

    deduped: list[str] = []
    seen: set[str] = set()
    for name in collections:
        if name in seen:
            continue
        seen.add(name)
        deduped.append(name)
    return deduped
