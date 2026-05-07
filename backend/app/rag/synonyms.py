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
    "二叉搜索树": "二叉搜索树",
    "二叉排序树": "二叉搜索树",
    "AVL": "平衡二叉树",
    "平衡二叉树": "平衡二叉树",
    "B树": "B树",
    "B+树": "B+树",
    "哈希表": "散列表",
    "散列表": "散列表",
    "Hash": "散列表",
    "DFS": "深度优先搜索",
    "深度优先搜索": "深度优先搜索",
    "BFS": "广度优先搜索",
    "广度优先搜索": "广度优先搜索",
    # ── 计算机组成原理 ──
    "CO": "计算机组成原理",
    "计组": "计算机组成原理",
    "计算机组成原理": "计算机组成原理",
    "CPU": "中央处理器",
    "中央处理器": "中央处理器",
    "ALU": "算术逻辑单元",
    "算术逻辑单元": "算术逻辑单元",
    "Cache": "高速缓存",
    "高速缓存": "高速缓存",
    "DMA": "直接存储器存取",
    "直接存储器存取": "直接存储器存取",
    "PCB": "进程控制块",
    "进程控制块": "进程控制块",
    # ── 操作系统 ──
    "OS": "操作系统",
    "操作系统": "操作系统",
    "进程": "进程",
    "线程": "线程",
    "PV操作": "信号量操作",
    "信号量操作": "信号量操作",
    "死锁": "死锁",
    "虚拟内存": "虚拟存储器",
    "虚拟存储器": "虚拟存储器",
    "分页": "分页存储",
    "分段": "分段存储",
    # ── 计算机网络 ──
    "CN": "计算机网络",
    "计网": "计算机网络",
    "计算机网络": "计算机网络",
    "TCP": "传输控制协议",
    "传输控制协议": "传输控制协议",
    "UDP": "用户数据报协议",
    "用户数据报协议": "用户数据报协议",
    "IP": "网际协议",
    "MAC": "介质访问控制",
    "ARP": "地址解析协议",
    "地址解析协议": "地址解析协议",
    "DNS": "域名系统",
    "域名系统": "域名系统",
    "HTTP": "超文本传输协议",
    "HTTPS": "安全超文本传输协议",
    # ── 通用 ──
    "KG": "知识图谱",
    "知识图谱": "知识图谱",
    "RAG": "检索增强生成",
    "检索增强生成": "检索增强生成",
}

# ── 派生映射 ──────────────────────────────────────────

# cleaner 用：含自映射的完整映射
SYNONYM_MAP: dict[str, str] = dict(_SYNONYM_RAW)

# recall / kg 用：正向映射（不含自映射）
SYNONYM_FORWARD: dict[str, str] = {k: v for k, v in _SYNONYM_RAW.items() if k != v}

# recall 用：反向映射（标准词 → 所有变体列表）
SYNONYM_REVERSE: dict[str, list[str]] = {}
for _k, _v in _SYNONYM_RAW.items():
    if _k != _v:
        SYNONYM_REVERSE.setdefault(_v, [])
        if _k not in SYNONYM_REVERSE[_v]:
            SYNONYM_REVERSE[_v].append(_k)

# recall 用：预编译正则（按长度降序，避免短词先匹配）
_SYNONYM_EXPAND_KEYS = sorted(SYNONYM_FORWARD.keys(), key=len, reverse=True)
SYNONYM_EXPAND_RE: re.Pattern[str] = re.compile(
    "|".join(re.escape(k) for k in _SYNONYM_EXPAND_KEYS)
) if _SYNONYM_EXPAND_KEYS else re.compile(r"(?!)")


def expand_query_with_synonyms(query: str) -> str:
    """同义词查询扩展：将用户查询中的术语扩展为所有同义表述

    例："什么是OS" → "什么是OS 操作系统"
    """
    expansions: list[str] = []
    seen: set[str] = set()

    def _add_expansion(term: str) -> None:
        if term.lower() not in seen:
            seen.add(term.lower())
            expansions.append(term)

    for m in SYNONYM_EXPAND_RE.finditer(query):
        matched = m.group(0)
        standard = SYNONYM_FORWARD[matched]
        _add_expansion(standard)
        for variant in SYNONYM_REVERSE.get(standard, []):
            _add_expansion(variant)

    if not expansions:
        return query

    return query + " " + " ".join(expansions)


def normalize_synonyms(text: str) -> tuple[str, int]:
    """同义词归一：将文本中的同义表述替换为标准术语

    Args:
        text: 待处理文本

    Returns:
        (归一后文本, 替换次数)
    """
    # cleaner 用：含自映射的完整映射 + 按长度降序正则
    _keys_sorted = sorted(SYNONYM_MAP.keys(), key=len, reverse=True)
    _pattern = re.compile("|".join(re.escape(k) for k in _keys_sorted))

    count = 0

    def _replace(m: re.Match) -> str:
        nonlocal count
        count += 1
        return SYNONYM_MAP[m.group(0)]

    result = _pattern.sub(_replace, text)
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
