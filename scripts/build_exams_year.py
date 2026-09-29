"""把 knowledge/questions/YYYY_408_exam.md 转成 L3 定稿格式（items.md + answer.md + paper.md）。

用法：
    uv run python scripts/build_exams_year.py 2019
    uv run python scripts/build_exams_year.py 2020
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "knowledge" / "questions"
ANSWERS = ROOT / "knowledge" / "answers"
OUT = ROOT / "knowledge" / "exams"

# 题号 → {subject, kp_ids}；kp_ids 空 = 覆盖 gap（禁止硬贴）
KP_MAP: dict[int, dict[int, dict]] = {
    2019: {
        1: {"subject": "ds", "kp_ids": []},
        2: {"subject": "ds", "kp_ids": ["ds.tree.forest_convert", "ds.tree.traversal"]},
        3: {"subject": "ds", "kp_ids": ["ds.tree.huffman"]},
        4: {"subject": "ds", "kp_ids": ["ds.tree.avl"]},
        5: {"subject": "ds", "kp_ids": ["ds.graph.aoe"]},
        6: {"subject": "ds", "kp_ids": ["ds.graph.storage"]},
        7: {"subject": "ds", "kp_ids": ["ds.sort.quick_sort", "ds.sort.insertion"]},
        8: {"subject": "ds", "kp_ids": ["ds.search.hash"]},
        9: {"subject": "ds", "kp_ids": ["ds.string.kmp"]},
        10: {"subject": "ds", "kp_ids": ["ds.sort.quick_sort"]},
        11: {"subject": "ds", "kp_ids": ["ds.sort.merge"]},
        12: {"subject": "co", "kp_ids": ["co.overview.von_neumann"]},
        13: {"subject": "co", "kp_ids": ["co.representation.fixed_point"]},
        14: {"subject": "os", "kp_ids": ["os.memory.paging", "os.memory.page_fault"]},
        15: {"subject": "co", "kp_ids": ["co.cpu.pipeline", "co.cpu.pipeline_hazard"]},
        16: {"subject": "co", "kp_ids": ["co.cpu.pipeline_stall"]},
        17: {"subject": "co", "kp_ids": ["co.storage.cache"]},
        18: {"subject": "co", "kp_ids": ["co.storage.cache_mapping"]},
        19: {"subject": "co", "kp_ids": ["co.instruction.addressing"]},
        20: {"subject": "co", "kp_ids": ["co.instruction.format"]},
        21: {"subject": "os", "kp_ids": ["os.process.schedule"]},
        22: {"subject": "os", "kp_ids": ["os.process.state"]},
        23: {"subject": "os", "kp_ids": ["os.file.alloc"]},
        24: {"subject": "os", "kp_ids": ["os.file.disk_free_space"]},
        25: {"subject": "os", "kp_ids": ["os.process.sync", "os.process.pv"]},
        26: {"subject": "os", "kp_ids": ["os.process.deadlock"]},
        27: {"subject": "os", "kp_ids": ["os.memory.segmentation"]},
        28: {"subject": "os", "kp_ids": ["os.memory.page_replace"]},
        29: {"subject": "os", "kp_ids": ["os.memory.virtual"]},
        30: {"subject": "os", "kp_ids": ["os.file.dir"]},
        31: {"subject": "os", "kp_ids": ["os.memory.paging"]},
        32: {"subject": "os", "kp_ids": ["os.memory.partition"]},
        33: {"subject": "cn", "kp_ids": ["cn.arch.model"]},
        34: {"subject": "cn", "kp_ids": ["cn.physical.medium"]},
        35: {"subject": "cn", "kp_ids": ["cn.datalink.flow_control"]},
        36: {"subject": "cn", "kp_ids": ["cn.datalink.mac"]},
        37: {"subject": "cn", "kp_ids": ["cn.network.ip_address"]},
        38: {"subject": "cn", "kp_ids": ["cn.transport.tcp"]},
        39: {"subject": "cn", "kp_ids": ["cn.transport.tcp_handshake"]},
        40: {"subject": "cn", "kp_ids": ["cn.application"]},
    },
    2020: {
        1: {"subject": "ds", "kp_ids": ["ds.array.symmetric"]},
        2: {"subject": "ds", "kp_ids": ["ds.stack_queue.stack"]},
        3: {"subject": "ds", "kp_ids": ["ds.tree.binary_tree", "ds.tree.complete"]},
        4: {"subject": "ds", "kp_ids": ["ds.tree.forest_convert"]},
        5: {"subject": "ds", "kp_ids": ["ds.tree.bst"]},
        6: {"subject": "ds", "kp_ids": ["ds.graph.traversal", "ds.graph.topo"]},
        7: {"subject": "ds", "kp_ids": ["ds.graph.mst"]},
        8: {"subject": "ds", "kp_ids": ["ds.graph.aoe"]},
        9: {"subject": "ds", "kp_ids": ["ds.sort.heap"]},
        10: {"subject": "ds", "kp_ids": ["ds.search.b_tree"]},
        11: {"subject": "ds", "kp_ids": ["ds.sort.insertion", "ds.sort.select"]},
        12: {"subject": "co", "kp_ids": ["co.cpu.datapath"]},
        13: {
            "subject": "co",
            "kp_ids": ["co.representation.complement", "co.representation.ieee754"],
        },
        14: {"subject": "co", "kp_ids": ["co.storage.main_memory"]},
        15: {"subject": "co", "kp_ids": ["co.storage.cache", "os.memory.tlb"]},
        16: {"subject": "co", "kp_ids": ["co.instruction.format", "co.instruction.addressing"]},
        17: {"subject": "co", "kp_ids": ["co.cpu.pipeline"]},
        18: {"subject": "co", "kp_ids": ["co.cpu.exception"]},
        19: {"subject": "co", "kp_ids": ["co.bus.bandwidth"]},
        20: {"subject": "co", "kp_ids": ["co.cpu.exception"]},
        21: {"subject": "co", "kp_ids": ["co.cpu.exception"]},
        22: {"subject": "co", "kp_ids": ["co.io.dma"]},
        23: {"subject": "os", "kp_ids": ["os.file.logical"]},
        24: {"subject": "os", "kp_ids": ["os.file.alloc"]},
        25: {"subject": "os", "kp_ids": ["co.cpu.exception", "os.overview.syscall"]},
        26: {"subject": "os", "kp_ids": ["os.process.schedule"]},
        27: {"subject": "os", "kp_ids": ["os.process.bankers"]},
        28: {"subject": "os", "kp_ids": ["os.memory.virtual", "os.memory.page_fault"]},
        29: {"subject": "os", "kp_ids": ["os.process.thread"]},
        30: {"subject": "os", "kp_ids": ["os.io.device"]},
        31: {"subject": "os", "kp_ids": ["os.file.dir"]},
        32: {"subject": "os", "kp_ids": ["os.process.sync"]},
        33: {"subject": "cn", "kp_ids": ["cn.arch.model"]},
        34: {"subject": "cn", "kp_ids": ["cn.network.ip"]},
        35: {"subject": "cn", "kp_ids": ["cn.datalink.ethernet"]},
        36: {"subject": "cn", "kp_ids": ["cn.datalink.flow_control"]},
        37: {"subject": "cn", "kp_ids": ["cn.datalink.mac"]},
        38: {"subject": "cn", "kp_ids": ["cn.transport.tcp_congestion"]},
        39: {"subject": "cn", "kp_ids": ["cn.transport.tcp"]},
        40: {"subject": "cn", "kp_ids": ["cn.application.dns"]},
    },
}

# 年份默认 explanation_status：2019 扫描无文字=none；2020 有 OCR 文字=scan
YEAR_EXP: dict[int, str] = {2019: "none", 2020: "scan"}

# 年卷级缺口（综合题等）
YEAR_GAPS: dict[int, list[str]] = {
    2019: ["comprehensive 41-47 整段缺失"],
    2020: ["comprehensive 仅有标题无正文，41-47 缺失"],
}

# 关键字 → KP（2009–2017 批量自动标注；冲突取首命中；人工 KP 优先）
# 顺序敏感：更具体的规则放前面
AUTO_KP_RULES: list[tuple[str, list[str], str]] = [
    (r"哈夫曼|霍夫曼|WPL", ["ds.tree.huffman"], "ds"),
    (r"平衡二叉|AVL|LL 旋转|RR 旋转", ["ds.tree.avl"], "ds"),
    (r"二叉排序|BST|二叉查找树", ["ds.tree.bst"], "ds"),
    (r"线索二叉", ["ds.tree.threaded"], "ds"),
    (r"森林|树.*二叉树|左孩子右兄弟|后根遍历|先根遍历", ["ds.tree.forest_convert"], "ds"),
    (r"完全二叉树|满二叉树", ["ds.tree.complete", "ds.tree.binary_tree"], "ds"),
    (r"先序|中序|后序|层序|遍历序列|还原.*树|构造二叉树", ["ds.tree.traversal"], "ds"),
    (r"B\+?树|B 树|B树", ["ds.search.b_tree"], "ds"),
    (r"散列|哈希|hash|冲突", ["ds.search.hash"], "ds"),
    (r"折半|二分查找", ["ds.search.binary_search"], "ds"),
    (r"KMP|模式匹配|next 数组|改进 KMP", ["ds.string.kmp"], "ds"),
    (r"最小生成树|普里姆|克鲁斯卡尔|Prim|Kruskal", ["ds.graph.mst"], "ds"),
    (r"最短路径|Dijkstra|Floyd|迪杰斯特拉", ["ds.graph.shortest_path"], "ds"),
    (r"拓扑|AOV", ["ds.graph.topo"], "ds"),
    (r"关键路径|AOE|最早开始|最迟开始", ["ds.graph.aoe"], "ds"),
    (r"邻接矩阵|邻接表|十字链表|图的存储", ["ds.graph.storage"], "ds"),
    (r"DFS|BFS|深度优先|广度优先|图的遍历", ["ds.graph.traversal"], "ds"),
    (r"快速排序|快排", ["ds.sort.quick_sort"], "ds"),
    (r"堆排序|大根堆|小根堆|堆是一", ["ds.sort.heap"], "ds"),
    (r"归并排序|败者树|置换选择", ["ds.sort.merge"], "ds"),
    (r"直接插入|插入排序", ["ds.sort.insertion"], "ds"),
    (r"简单选择|选择排序", ["ds.sort.select"], "ds"),
    (r"冒泡排序", ["ds.sort.bubble"], "ds"),
    (r"希尔排序", ["ds.sort.shell"], "ds"),
    (r"基数排序", ["ds.sort.radix"], "ds"),
    (r"对称矩阵|上三角|下三角|稀疏矩阵|三元组", ["ds.array.compressed"], "ds"),
    (r"链表|单链表|双链表|循环链表|头结点", ["ds.linear.linked_list"], "ds"),
    (r"顺序表", ["ds.linear.seq_list"], "ds"),
    (r"栈|出栈|入栈|括号匹配|表达式求值", ["ds.stack_queue.stack"], "ds"),
    (r"队列|循环队列|队头|队尾", ["ds.stack_queue.queue"], "ds"),
    (r"时间复杂度|空间复杂度|O\(log|O\(n", [], "ds"),
    (r"冯·诺依曼|存储程序", ["co.overview.von_neumann"], "co"),
    (r"CPI|流水线|超标量|冒险|转发|停顿", ["co.cpu.pipeline"], "co"),
    (r"中断|异常|陷阱|自陷|Trap|NMI|DMA|周期挪用", ["co.cpu.exception"], "co"),
    (
        r"Cache|高速缓存|命中率|替换算法|写回|写通|全相联|组相联|直接映射",
        ["co.storage.cache"],
        "co",
    ),
    (r"TLB|快表|页表|多级页表|缺页", ["os.memory.paging"], "os"),
    (r"虚拟存储器|虚拟内存|请求分页|工作集|抖动", ["os.memory.virtual"], "os"),
    (r"页面置换|LRU|FIFO|OPT|Belady", ["os.memory.page_replace"], "os"),
    (r"动态分区|首次适应|最佳适应|最坏适应|伙伴|紧凑|对换", ["os.memory.partition"], "os"),
    (r"分段|段页式", ["os.memory.segmentation"], "os"),
    (r"IEEE ?754|浮点|阶码|尾数", ["co.representation.ieee754"], "co"),
    (r"补码|原码|反码|移码|溢出", ["co.representation.complement"], "co"),
    (
        r"机器字长|ALU|数据通路|指令寄存器|通用寄存器|小端|大端|边界对齐|结构型",
        ["co.cpu.datapath"],
        "co",
    ),
    (r"指令格式|操作码|地址码|定长指令", ["co.instruction.format"], "co"),
    (r"寻址|直接寻址|间接寻址|立即寻址|相对寻址|基址|变址", ["co.instruction.addressing"], "co"),
    (r"RISC|CISC", ["co.instruction.risc_cisc"], "co"),
    (r"总线|QPI|带宽|仲裁|同步总线|异步总线", ["co.bus.bandwidth"], "co"),
    (r"主存|DRAM|SRAM|存储体|多体交叉|低位交叉", ["co.storage.main_memory"], "co"),
    (r"通道|I/O 接口|程序中断方式|I/O 控制器", ["co.io.interface"], "co"),
    (r"进程调度|调度算法|时间片|多级反馈|优先级|响应比|周转", ["os.process.schedule"], "os"),
    (r"进程状态|就绪|执行|阻塞|三态|进程控制块|PCB", ["os.process.state"], "os"),
    (r"线程|进程与线程|父进程|子进程|fork|进程创建", ["os.process.thread"], "os"),
    (r"死锁|银行家|安全序列|资源分配图|死锁预防|死锁避免", ["os.process.deadlock"], "os"),
    (
        r"临界区|互斥|信号量|P 操作|V 操作|PV|生产者|消费者|读者写者|哲学家",
        ["os.process.sync"],
        "os",
    ),
    (r"管程|条件变量", ["os.process.monitor"], "os"),
    (r"文件分配|索引分配|链接分配|连续分配|FAT|文件物理", ["os.file.alloc"], "os"),
    (r"目录|索引结点|inode|目录项|路径名|硬链接|软链接", ["os.file.dir"], "os"),
    (r"文件逻辑|记录|文件长度|共享文件|打开文件表", ["os.file.logical"], "os"),
    (r"磁盘调度|SCAN|C-SCAN|电梯|寻道|旋转延迟", ["os.file.disk_schedule"], "os"),
    (r"位示图|空闲表|空闲链表|磁盘空闲", ["os.file.disk_free_space"], "os"),
    (r"缓冲|设备独立性|SPOOLing|假脱机|设备分配", ["os.io.device"], "os"),
    (r"系统调用|内核态|用户态|特权指令|中断向量表", ["os.overview.syscall"], "os"),
    (r"OSI|TCP/IP 体系|协议要素|语法|语义|时序|网络体系", ["cn.arch.model"], "cn"),
    (r"香农|奈奎斯特|信道容量|带宽.*bps|码元", ["cn.physical.bandwidth"], "cn"),
    (r"双绞线|光纤|同轴|传输介质|导向传输", ["cn.physical.medium"], "cn"),
    (r"滑动窗口|停等|后退 N|选择重传|信道利用率|帧长", ["cn.datalink.flow_control"], "cn"),
    (
        r"CSMA|CDMA|ALOHA|冲突域|广播域|以太网|MAC 地址|交换机|VLAN|802\.11|CSMA/CA|IFS",
        ["cn.datalink.mac"],
        "cn",
    ),
    (r"CRC|海明|差错控制|检错|纠错", ["cn.datalink.error_control"], "cn"),
    (r"IP 地址|子网|CIDR|超网|掩码|划分子网", ["cn.network.ip_address"], "cn"),
    (r"IP 分片|TTL|首部|转发|路由表", ["cn.network.ip_forward"], "cn"),
    (r"路由|RIP|OSPF|BGP|距离向量|链路状态", ["cn.network.routing"], "cn"),
    (r"ARP|ICMP|IGMP", ["cn.network.arp"], "cn"),
    (r"NAT|IPv6", ["cn.network.nat"], "cn"),
    (r"虚电路|数据报", ["cn.network.ip"], "cn"),
    (
        r"TCP|三次握手|四次挥手|拥塞窗口|滑动窗口|MSS|确认序号|SYN|FIN|流量控制|快重传",
        ["cn.transport.tcp"],
        "cn",
    ),
    (r"UDP", ["cn.transport.udp"], "cn"),
    (r"DNS|域名|递归查询|迭代查询", ["cn.application.dns"], "cn"),
    (r"HTTP|SMTP|POP|FTP|电子邮件|P2P|C/S|客户/服务器", ["cn.application.http"], "cn"),
]


def auto_kp(stem: str) -> tuple[str, list[str]]:
    """关键字规则起草 subject/kp_ids；无命中则空 kp。"""
    text = stem
    for pat, kps, subj in AUTO_KP_RULES:
        if re.search(pat, text, re.I):
            return subj, list(kps)
    return "mixed", []


def parse_questions(text: str) -> list[dict]:
    parts = re.split(r"(?m)^### 第(\d+)题\s*$", text)
    qs: list[dict] = []
    for i in range(1, len(parts) - 1, 2):
        num = int(parts[i])
        body = parts[i + 1]
        # 剥掉 **解析** 及其后正文（进 answer，不进 items 正文）
        exp = ""
        m_exp = re.split(r"(?m)^\s*\*\*解析\*\*", body, maxsplit=1)
        if len(m_exp) == 2:
            body, exp = m_exp[0], m_exp[1]
        exp = re.sub(r"(?m)^--- page \d+ ---$", "", exp)
        exp = re.sub(r"(?m)^\s*[.·]?\s*\d{3}\s*[.·]\s*$", "", exp)
        exp = re.sub(r"(?m)^<!--.*?-->$", "", exp)
        exp = exp.strip()

        lines = body.splitlines()
        stem_lines: list[str] = []
        opts: list[tuple[str, str]] = []
        ans: str | None = None
        in_opts = False
        for ln in lines:
            mo = re.match(r"^\s*-\s*\*?\*?([A-D])[.、．]\s*(.*)$", ln)
            if mo:
                in_opts = True
                letter = mo.group(1)
                rest = mo.group(2)
                if rest.startswith("**"):
                    rest = rest[2:]
                if rest.endswith("**"):
                    rest = rest[:-2]
                if rest.endswith("** ✅"):
                    rest = rest[: -len("** ✅")]
                if "✅" in rest:
                    ans = letter
                    rest = rest.replace("✅", "").strip()
                rest = re.sub(r"\*\*", "", rest).strip()
                opts.append((letter, rest))
                continue
            if in_opts:
                continue
            if ln.strip().startswith("**解析"):
                break
            stem_lines.append(ln)
        stem = "\n".join(stem_lines).strip()
        if ans is None:
            m = re.search(r"\*\*([A-D])[.、．]", body)
            if m:
                ans = m.group(1)
        qs.append({"num": num, "stem": stem, "opts": opts, "answer_key": ans, "inline_exp": exp})
    return qs


def infer_answer_from_text(text: str) -> str | None:
    """从解析正文抽客观题答案键。"""
    if not text:
        return None
    for pat in (
        r"【参考答案】\s*[（(]?([A-D])[）)]?",
        r"故选\s*[（(]?([A-D])[）)]?",
        r"(?:所以|因此|本题)?选\s*[（(]?([A-D])[）)]?\s*(?:[。．.、]|$)",
        r"正确选项为\s*[（(]?([A-D])[）)]?",
        r"答案(?:是|为|选)\s*[（(]?([A-D])[）)]?",
    ):
        m = re.search(pat, text)
        if m:
            return m.group(1)
    return None


def parse_booklet_table_answers(text: str) -> dict[int, str]:
    """从答案册表格行抽 N→字母（容忍 OCR 噪声的 |N.|X| 形态）。"""
    out: dict[int, str] = {}
    # |1.|B|2.|C|... 或 |01.|C|02.|D|
    for m in re.finditer(r"\|\s*0*(\d{1,2})\s*[.．]\s*\|\s*([A-D])\s*\|", text):
        n, ans = int(m.group(1)), m.group(2)
        out.setdefault(n, ans)
    # 答案表行：|1.|B|2.<br>C| — 抓 「数字.| 字母」
    for m in re.finditer(r"0*(\d{1,2})\s*[.．]\s*(?:<br>)?\s*([A-D])\b", text):
        n, ans = int(m.group(1)), m.group(2)
        if n <= 45 and n not in out:
            out[n] = ans
    return out


def parse_answer_booklet(path: Path) -> tuple[dict[int, str], dict[int, str]]:
    """返回 (题号→解析正文, 题号→答案键)。"""
    if not path.exists():
        return {}, {}
    text = path.read_text(encoding="utf-8", errors="replace")
    table_ans = parse_booklet_table_answers(text)
    exps: dict[int, str] = {}

    # 主形态：行首「N. 解析：」或「## N. 【解析】」
    # 先做粗切，再过滤「解析」不在段首附近的假命中
    pat = re.compile(
        r"(?m)^\s*#{0,3}\s*0*(\d{1,2})\s*[.．•]\s*\**\s*(?:【)?解析",
    )
    hits = list(pat.finditer(text))
    for i, m in enumerate(hits):
        n = int(m.group(1))
        if n < 1 or n > 45:
            continue
        start = m.end()
        end = hits[i + 1].start() if i + 1 < len(hits) else min(start + 2500, len(text))
        body = text[start:end]
        body = re.sub(r"(?m)^--- page \d+ ---$", "", body)
        body = re.sub(r"(?m)^\s*[.·]?\s*0?\d{3}\s*[.·]\s*$", "", body)
        body = re.sub(r"(?m)^<!--.*?-->$", "", body)
        body = body.strip()
        if len(body) < 20:
            continue
        # 同题只保留第一段较长的
        if n not in exps or len(exps[n]) < len(body):
            exps[n] = body[:2000]

    for n, body in exps.items():
        if n not in table_ans:
            a = infer_answer_from_text(body)
            if a:
                table_ans[n] = a
    return exps, table_ans


def has_figure(stem: str) -> bool:
    return bool(re.search(r"下图|如图|题\s*\d+\s*图|图所示|下图描述|下图所示", stem))


def build_year(year: int) -> None:  # noqa: C901
    src = SRC / f"{year}_408_exam.md"
    if not src.exists():
        raise SystemExit(f"missing {src}")
    text = src.read_text(encoding="utf-8", errors="replace")
    qs = parse_questions(text)
    booklet_exp, booklet_ans = parse_answer_booklet(ANSWERS / f"{year}-answer.md")
    out_dir = OUT / str(year)
    out_dir.mkdir(parents=True, exist_ok=True)
    exp_default = YEAR_EXP.get(year, "none")
    # 有文字答案册 → 默认 scan；纯扫描 → none
    if year not in YEAR_EXP:
        bp = ANSWERS / f"{year}-answer.md"
        exp_default = "scan" if bp.exists() and bp.stat().st_size > 2000 else "none"
    kp_year = KP_MAP.get(year, {})
    year_gaps = list(YEAR_GAPS.get(year, []))
    # 综合题：源文件有「综合应用」标题但无 ### 第41题 → 记年卷缺口
    if "综合应用" in text and "### 第41题" not in text:
        note = "comprehensive 仅有标题或无正文，41-47 缺失"
        if note not in year_gaps:
            year_gaps.append(note)

    items: list[str] = [
        f"# {year} 年 408 真题 · items",
        "",
        f"> document_id: exam-{year}-items",
        f"> exam_year: {year}",
        "> kb_depth: exams",
        "> doc_role: exam_item",
        "> source_type: third_party",
        "> credibility: high",
        f"> explanation_status: {exp_default}",
        "",
        "答案只在 metadata（answer_key），正文不印答案。",
        "",
    ]
    answer: list[str] = [
        f"# {year} 年 408 真题 · answer",
        "",
        f"> document_id: exam-{year}-answer",
        f"> exam_year: {year}",
        "> kb_depth: exams",
        "> doc_role: exam_answer",
        "> source_type: third_party",
        f"> explanation_status: {exp_default}",
        "",
    ]
    if exp_default == "none":
        answer.append("本卷无文字解析（explanation_status=none）；答案键见 items metadata。")
        answer.append("")

    # 主循环结果暂存，供 gap inventory 使用（与 items 同源，避免二次计算不一致）
    computed: list[dict] = []

    for q in qs:
        n = q["num"]
        qid = f"{year}-Q{n}"
        meta = kp_year.get(n)
        if meta is None:
            subj, kps = auto_kp(q["stem"] + " " + " ".join(o[1] for o in q["opts"]))
            meta = {"subject": subj, "kp_ids": kps}
        subj = meta["subject"]
        kps = meta["kp_ids"]
        fig = has_figure(q["stem"])
        ans = q["answer_key"] or booklet_ans.get(n) or ""
        exp_text = (q.get("inline_exp") or "").strip() or (booklet_exp.get(n) or "").strip()
        # 解析里的「故选 X」可补答案键
        if not ans:
            ans = infer_answer_from_text(exp_text) or ""
        exp_status = "scan" if exp_text else ("none" if exp_default == "none" else exp_default)

        gap_fields = []
        if not q["stem"]:
            gap_fields.append("stem")
        if not q["opts"]:
            gap_fields.append("options")
        if not ans:
            gap_fields.append("answer")
        if fig:
            gap_fields.append("figure")
        complete = (
            "incomplete" if "stem" in gap_fields else ("partial" if gap_fields else "complete")
        )
        gap_status = (
            "none" if not gap_fields else ("missing" if "stem" in gap_fields else "partial")
        )
        computed.append(
            {
                "qid": qid,
                "n": n,
                "kps": kps,
                "ans": ans,
                "fig": fig,
                "gap_fields": gap_fields,
                "complete": complete,
            }
        )

        items.append(f"## {qid}")
        items.append("")
        items.append(f"> question_id: {qid}")
        items.append(f"> exam_year: {year}")
        items.append("> question_type: choice")
        items.append("> score: 2")
        items.append("> part: 一、单项选择题")
        items.append("> source_type: third_party")
        items.append("> credibility: high")
        items.append(f"> explanation_status: {exp_status}")
        items.append(f"> subject: {subj}")
        items.append(f"> kp_ids: [{', '.join(kps)}]")
        items.append(f"> answer_key: {ans or 'null'}")
        items.append("> reference_answer: null")
        items.append(f"> has_figure: {'true' if fig else 'false'}")
        if fig:
            items.append("> figure_status: missing")
        else:
            items.append("> figure_status: null")
        items.append(f"> completeness: {complete}")
        items.append(f"> gap_status: {gap_status}")
        items.append(f"> gap_fields: [{', '.join(gap_fields)}]")
        items.append("")
        items.append(f"**题干**：{q['stem']}")
        items.append("")
        for letter, otext in q["opts"]:
            items.append(f"- {letter}. {otext}")
        items.append("")
        items.append("---")
        items.append("")

        answer.append(f"## {qid}")
        answer.append("")
        answer.append(f"> question_id: {qid}")
        answer.append(f"> explanation_status: {exp_status}")
        answer.append(f"> answer_key: {ans or 'null'}")
        answer.append("")
        # 带 qid 前缀，防止占位文本被 content_hash 去重合并
        if exp_text:
            answer.append(f"[{qid}]")
            answer.append(exp_text)
        else:
            answer.append(f"[{qid}] （无文字解析。）")
        answer.append("")

    # paper：溯源 + 年卷级缺口
    paper = [
        f"# {year} 年 408 · paper（溯源资产）",
        "",
        f"> document_id: exam-{year}-paper",
        f"> exam_year: {year}",
        "> kb_depth: exams",
        "> doc_role: exam_paper",
        "> source_type: third_party",
        "> credibility: medium",
        f"> source_file: knowledge/papers-rebuild/{year}.md",
        "",
        "整卷原始语境见 papers-rebuild；**默认不进主 RAG**。",
        "题干/选项以 items.md 为准。",
        "",
    ]
    if year_gaps:
        paper.append("## 年卷级缺口（gap 记录，不臆补）")
        paper.append("")
        for g in year_gaps:
            paper.append(f"- {g}")
        paper.append("")

    (out_dir / "items.md").write_text("\n".join(items) + "\n", encoding="utf-8")
    (out_dir / "answer.md").write_text("\n".join(answer) + "\n", encoding="utf-8")
    (out_dir / "paper.md").write_text("\n".join(paper) + "\n", encoding="utf-8")

    # ★ gap inventory：正式产物（非失败）；append 合并，保留已 filled 记录
    inv_path = OUT / "gap_inventory.jsonl"
    existing: list[dict] = []
    if inv_path.exists():
        for line in inv_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                existing.append(json.loads(line))
    # 本年重建：丢掉该年旧 open 记录（filled 的保留）
    keep = [e for e in existing if not (e.get("year") == year and e.get("status") == "open")]
    gaps: list[dict] = []
    for c in computed:
        qid = c["qid"]
        gap_fields = c["gap_fields"]
        for gf in gap_fields:
            gtype = "question_body" if gf in {"stem", "options", "sub_questions"} else gf
            gaps.append(
                {
                    "asset": f"question:{qid}",
                    "year": year,
                    "gap_type": gtype,
                    "gap_fields": [gf],
                    "completeness": c["complete"],
                    "source": f"knowledge/exams/{year}/items.md",
                    "note": "",
                    "status": "open",
                }
            )
        if not c["kps"]:
            gaps.append(
                {
                    "asset": f"question:{qid}",
                    "year": year,
                    "gap_type": "knowledge_points",
                    "gap_fields": ["kp_ids"],
                    "completeness": c["complete"],
                    "source": f"knowledge/exams/{year}/items.md",
                    "note": "无法锚定到 KP 骨架，禁止硬贴",
                    "status": "open",
                }
            )
    for g in year_gaps:
        gaps.append(
            {
                "asset": f"paper:{year}",
                "year": year,
                "gap_type": "comprehensive",
                "gap_fields": ["question_body"],
                "completeness": "incomplete",
                "source": f"knowledge/exams/{year}/paper.md",
                "note": g,
                "status": "open",
            }
        )
    keep.extend(gaps)
    inv_path.write_text(
        "\n".join(json.dumps(e, ensure_ascii=False) for e in keep) + "\n",
        encoding="utf-8",
    )

    n_exp = sum(1 for q in qs if (q.get("inline_exp") or booklet_exp.get(q["num"])))
    missing_ans = [q["num"] for q in qs if not q["answer_key"]]
    print(f"wrote {out_dir} items={len(qs)} with_exp={n_exp} gaps={len(gaps)}")
    if missing_ans:
        print("WARN missing answer_key:", missing_ans)
    if year not in KP_MAP:
        print("WARN no KP_MAP for year", year)


if __name__ == "__main__":
    y = int(sys.argv[1]) if len(sys.argv) > 1 else 2020
    build_year(y)
