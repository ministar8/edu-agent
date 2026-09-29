"""Legacy Coverage Gap：legacy vs L1/L2/L3 的知识覆盖分析。

不只比 chunk 数，要比「知识主题」：
- 用 jieba 主题词簇 + 学科域 对齐
- 产出：legacy 独有 / 新层独有 / 交集 / 未覆盖主题

用法：
    uv run python scripts/legacy_coverage_gap.py
"""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path

import chromadb
import jieba

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "evals" / "legacy_coverage_gap.json"
COLLECTIONS = [
    "data_structure",
    "computer_organization",
    "operating_system",
    "computer_network",
    "questions",
]

_STOP = {
    "的",
    "是",
    "了",
    "在",
    "和",
    "与",
    "或",
    "对",
    "中",
    "算法",
    "方法",
    "问题",
    "过程",
    "计算",
    "分析",
    "选择",
    "结构",
    "系统",
    "操作",
    "实现",
    "方式",
    "情况",
    "叙述",
    "正确",
    "错误",
    "下列",
    "如何",
    "什么",
    "怎么",
    "步骤",
    "识别",
    "信号",
    "易错",
    "变式",
    "综合",
    "拆解",
    "本章",
    "解决",
    "一个",
    "可以",
    "进行",
    "具有",
    "下列",
    "有关",
    "关于",
    "主要",
    "特点",
    "概念",
    "定义",
    "基本",
    "原理",
    "作用",
    "表示",
    "存储",
    "使用",
}

# 主题锚点：锚定到 KP 域（用于粗聚类，不替代 KP 标注）
TOPIC_ANCHORS = {
    "线性表/链表": ["线性表", "链表", "顺序表", "单链表", "双链表", "循环链表"],
    "栈队列": ["栈", "队列", "循环队列", "括号匹配", "出栈"],
    "数组矩阵": ["数组", "矩阵", "稀疏矩阵", "压缩存储", "特殊矩阵"],
    "串/KMP": ["串", "模式匹配", "KMP", "next"],
    "树/二叉树": ["二叉树", "树", "遍历", "先序", "中序", "后序", "线索"],
    "BST/AVL": ["二叉排序", "BST", "平衡二叉", "AVL"],
    "哈夫曼": ["哈夫曼", "Huffman", "WPL"],
    "图": ["图", "邻接", "遍历", "DFS", "BFS", "最小生成", "最短路径", "拓扑", "关键路径", "AOE"],
    "查找": ["查找", "折半", "分块", "B树", "B 树", "散列", "哈希", "顺序查找"],
    "排序": ["排序", "快速排序", "堆排序", "归并", "插入排序", "选择排序", "希尔", "基数", "冒泡"],
    "表示与运算": ["补码", "原码", "浮点", "IEEE", "溢出", "移码", "定点"],
    "存储/Cache": ["Cache", "高速缓存", "主存", "DRAM", "SRAM", "存储器", "映射", "替换"],
    "指令/寻址": ["指令", "寻址", "操作码", "RISC", "CISC"],
    "流水线": ["流水线", "冒险", "停顿", "转发", "CPI"],
    "中断/DMA": ["中断", "异常", "DMA", "通道", "自陷"],
    "总线/IO": ["总线", "带宽", "仲裁", "I/O", "接口"],
    "进程/线程": ["进程", "线程", "PCB", "状态"],
    "调度": ["调度", "时间片", "优先级", "周转"],
    "同步/死锁": ["同步", "信号量", "PV", "互斥", "死锁", "银行家", "管程", "临界"],
    "内存管理": ["分页", "分段", "虚拟内存", "缺页", "页面置换", "TLB", "页表", "分区"],
    "文件系统": ["文件", "目录", "inode", "FAT", "分配", "磁盘", "空闲"],
    "设备/IO": ["缓冲", "设备", "SPOOLing", "驱动"],
    "体系结构": ["体系结构", "OSI", "协议", "分层"],
    "物理层": ["物理层", "信道", "波特", "调制", "介质", "带宽"],
    "数据链路": ["数据链路", "帧", "CRC", "海明", "CSMA", "以太网", "滑动窗口", "停等"],
    "网络层/IP": ["IP", "子网", "路由", "分片", "ARP", "ICMP", "虚电路"],
    "传输层": ["TCP", "UDP", "握手", "拥塞", "流量控制", "端口"],
    "应用层": ["DNS", "HTTP", "FTP", "SMTP", "邮件", "应用层"],
}


def tokens(text: str) -> set[str]:
    out = set()
    for t in jieba.lcut(text or ""):
        t = t.strip().lower()
        if len(t) >= 2 and t not in _STOP and re.search(r"[一-鿿a-z0-9]", t):
            out.add(t)
    return out


def topic_hits(text: str) -> Counter:
    toks = tokens(text)
    raw = text or ""
    c: Counter = Counter()
    for name, keys in TOPIC_ANCHORS.items():
        score = 0
        for k in keys:
            if k.lower() in raw.lower() or k.lower() in toks:
                score += 1
        if score:
            c[name] = score
    return c


def load_side(col, kb_filter: list[str] | None) -> list[dict]:
    got = col.get(include=["documents", "metadatas"])
    docs = got.get("documents") or []
    metas = got.get("metadatas") or []
    ids = got.get("ids") or []
    rows = []
    for i, m in enumerate(metas):
        m = m or {}
        kb = str(m.get("kb_depth") or "")
        if kb_filter is not None and kb not in kb_filter:
            continue
        if kb_filter is None and kb:
            continue  # legacy only
        rows.append(
            {
                "id": ids[i] if i < len(ids) else "",
                "kb_depth": kb or "legacy",
                "doc_role": str(m.get("doc_role") or ""),
                "text": docs[i] if i < len(docs) else "",
                "chunk_id": str(m.get("chunk_id") or ""),
            }
        )
    return rows


def coverage(rows: list[dict]) -> dict:
    topic_docs: dict[str, int] = defaultdict(int)
    topic_tokens: dict[str, set[str]] = defaultdict(set)
    all_tokens: set[str] = set()
    for r in rows:
        t = topic_hits(r["text"] + " " + r["chunk_id"])
        blob = tokens(r["text"])
        all_tokens |= blob
        for name, sc in t.items():
            topic_docs[name] += 1
            topic_tokens[name] |= blob
    return {
        "n_chunks": len(rows),
        "topic_chunk_counts": dict(sorted(topic_docs.items(), key=lambda x: -x[1])),
        "topics_present": sorted(topic_docs.keys()),
        "token_count": len(all_tokens),
        "top_tokens": [w for w, _ in Counter().update(all_tokens) or []] if False else [],
    }


def main() -> int:
    client = chromadb.PersistentClient(path=str(ROOT / "chroma_db"))
    legacy_all = []
    new_all = {"basic": [], "advanced": [], "exams": []}

    for coll in COLLECTIONS:
        try:
            col = client.get_collection(coll)
        except Exception:
            continue
        legacy_all.extend(load_side(col, None))
        new_all["basic"].extend(load_side(col, ["basic"]))
        new_all["advanced"].extend(load_side(col, ["advanced"]))
        new_all["exams"].extend(load_side(col, ["exams"]))

    cov_legacy = coverage(legacy_all)
    cov_basic = coverage(new_all["basic"])
    cov_adv = coverage(new_all["advanced"])
    cov_exams = coverage(new_all["exams"])

    new_topics = (
        set(cov_basic["topics_present"])
        | set(cov_adv["topics_present"])
        | set(cov_exams["topics_present"])
    )
    legacy_topics = set(cov_legacy["topics_present"])

    only_legacy = sorted(legacy_topics - new_topics)
    only_new = sorted(new_topics - legacy_topics)
    both = sorted(legacy_topics & new_topics)

    # 主题文档量对比（覆盖厚度）
    thickness = []
    for name in sorted(set(legacy_topics) | set(new_topics)):
        thickness.append(
            {
                "topic": name,
                "legacy_chunks": cov_legacy["topic_chunk_counts"].get(name, 0),
                "basic_chunks": cov_basic["topic_chunk_counts"].get(name, 0),
                "advanced_chunks": cov_adv["topic_chunk_counts"].get(name, 0),
                "exams_chunks": cov_exams["topic_chunk_counts"].get(name, 0),
                "new_total": cov_basic["topic_chunk_counts"].get(name, 0)
                + cov_adv["topic_chunk_counts"].get(name, 0)
                + cov_exams["topic_chunk_counts"].get(name, 0),
            }
        )
    thickness.sort(key=lambda x: -x["legacy_chunks"])

    # 薄弱：legacy 很多、新层很少
    thin = [
        t
        for t in thickness
        if t["legacy_chunks"] >= 10 and t["new_total"] <= max(3, t["legacy_chunks"] * 0.15)
    ]
    # 未锚主题：legacy 有内容但无 topic 命中（抽样 token）
    legacy_unanchored = 0
    unanchored_tokens: Counter = Counter()
    for r in legacy_all:
        if not topic_hits(r["text"]):
            legacy_unanchored += 1
            for w in tokens(r["text"]):
                unanchored_tokens[w] += 1

    report = {
        "_meta": {
            "note": "Legacy Coverage Gap：知识主题对照，非纯 chunk 计数",
            "legacy_chunks": cov_legacy["n_chunks"],
            "new_chunks": {
                "basic": cov_basic["n_chunks"],
                "advanced": cov_adv["n_chunks"],
                "exams": cov_exams["n_chunks"],
            },
        },
        "topics_only_in_legacy": only_legacy,
        "topics_only_in_new_layers": only_new,
        "topics_in_both": both,
        "topic_thickness": thickness,
        "thin_coverage": thin,
        "legacy_unanchored_chunks": legacy_unanchored,
        "legacy_unanchored_top_tokens": unanchored_tokens.most_common(30),
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print("==== Legacy Coverage Gap ====")
    print(
        f"legacy={cov_legacy['n_chunks']} basic={cov_basic['n_chunks']} "
        f"advanced={cov_adv['n_chunks']} exams={cov_exams['n_chunks']}"
    )
    print(f"topics only_legacy={only_legacy}")
    print(f"topics only_new={only_new}")
    print(f"topics both={len(both)}")
    print("thin (legacy≥10 且 new 很薄):")
    for t in thin[:15]:
        print(
            f"  {t['topic']}: legacy={t['legacy_chunks']} "
            f"new(L1+L2+L3)={t['new_total']} "
            f"(b{t['basic_chunks']}+a{t['advanced_chunks']}+e{t['exams_chunks']})"
        )
    print(f"legacy unanchored chunks={legacy_unanchored}")
    print("top unanchored tokens", unanchored_tokens.most_common(15))
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
