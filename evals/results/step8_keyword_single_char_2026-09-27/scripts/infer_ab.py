"""单字关键词收窄的 A/B：改动前后的学科推断对比（纯函数，不需要索引）。

用法：PYTHONPATH=src .venv/Scripts/python.exe infer_ab.py
"""

from __future__ import annotations

import rag.recall as R

# 本次新增/替换的词（用于把词表还原成「改动前」）
NEW_DS = ("主串", "子串", "字符串匹配", "图的", "图论", "无向图", "有向图", "邻接表")
NEW_OS = ("位示图",)

CASES: list[tuple[str, str, str]] = [
    ("#19 位示图（不含磁盘）", "位示图法是怎么工作的？", "operating_system"),
    ("位示图+磁盘（对照）", "位示图法是怎么管理磁盘空闲空间的？", "operating_system"),
    ("黄金集·资源分配图", "写出死锁检测算法（资源分配图化简）的伪代码。", "operating_system"),
    (
        "黄金集·IPv4 字符串",
        "写一段代码把 IPv4 点分十进制字符串转换为 32 位整数，并处理非法输入。",
        "computer_network",
    ),
    ("黄金集·KMP 主串", "学生的答案是：KMP 算法比朴素匹配快，是因为它对主串做了预处理。请批改。", "data_structure"),
    ("黄金集·图的遍历", "图的深度优先遍历和广度优先遍历有什么不同？", "data_structure"),
    ("黄金集·邻接表", "写出用邻接表存储图的深度优先遍历代码。", "data_structure"),
    ("黄金集·邻接矩阵", "邻接矩阵和邻接表各适合什么样的图？", "data_structure"),
    ("黄金集·二叉树", "什么是二叉搜索树？", "data_structure"),
    ("黄金集·栈", "栈和队列的主要区别是什么？", "data_structure"),
    ("#9 磁盘空闲空间", "请出一道考查磁盘空闲空间管理的题。", "operating_system"),
    ("#18 生产者-消费者", "用信号量写出生产者—消费者问题的伪代码。", "operating_system"),
]


def old_keywords() -> dict[str, tuple[str, ...]]:
    """把词表还原成「改动前」：去掉新词，加回两个单字项。"""
    out: dict[str, tuple[str, ...]] = {}
    for col, kws in R._COLLECTION_KEYWORDS.items():
        kept = tuple(k for k in kws if k not in NEW_DS and k not in NEW_OS)
        out[col] = kept
    out["data_structure"] = out["data_structure"] + ("串", "图")
    return out


def main() -> None:
    current = R._COLLECTION_KEYWORDS
    try:
        R._COLLECTION_KEYWORDS = old_keywords()
        before = {q: R._infer_subject_collections(q) for _, q, _ in CASES}
    finally:
        R._COLLECTION_KEYWORDS = current
    after = {q: R._infer_subject_collections(q) for _, q, _ in CASES}

    print(f"{'情形':22s} {'期望集合在范围内':^16s} {'多余的集合（噪声）':^24s}")
    print(f"{'':22s} {'改动前':>8s} {'改动后':>8s}   {'改动前':<12s} {'改动后':<12s}")
    for label, q, expect in CASES:
        b = before[q] or []
        a = after[q] or []
        ok_b = "✓" if expect in b else "✗"
        ok_a = "✓" if expect in a else "✗"
        extra_b = [c for c in b if c != expect]
        extra_a = [c for c in a if c != expect]
        print(
            f"{label:22s} {ok_b:>8s} {ok_a:>8s}   {str(extra_b):<12s} {str(extra_a):<12s}"
        )
    print()
    print("两个判据：① 期望集合**是否在检索范围内**（✗→✓ = 修好可达性）；")
    print("          ② 多余的集合是否被剔除（噪声↓ ⇒ category_precision↑）。")


if __name__ == "__main__":
    main()
