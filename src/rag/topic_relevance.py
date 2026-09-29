"""主题相关性：防止 top-up 错域（哈夫曼→CSMA）。

规则（与层召回正交）：
- 层保证「进池」
- 主题保证「进池的像样」
- 仅约束 top-up / 补齐，不改主召回分数公式
"""

from __future__ import annotations

import re

# 中文/英文技术词：长度≥2 的汉字串，或 ≥3 的英文词
_TOKEN_RE = re.compile(r"[一-鿿]{2,}|[A-Za-z]{3,}")

# 弱词：几乎所有 408 文都会出现
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
    "stem",
    "the",
    "and",
    "for",
    "with",
    "that",
    "this",
}


def tokenize(text: str) -> set[str]:
    if not text:
        return set()
    import jieba

    toks: set[str] = set()
    for raw in jieba.lcut(text or ""):
        t = raw.strip().lower()
        if t and t not in _STOP and (len(t) >= 2 or re.fullmatch(r"[a-z]{3,}", t)):
            # 过滤纯符号/单字
            if re.search(r"[一-鿿A-Za-z0-9]", t):
                toks.add(t)
    # 英文技术词
    for en in re.findall(r"[A-Za-z]{3,}", text or ""):
        e = en.lower()
        if e not in _STOP:
            toks.add(e)
    return toks


def topic_relevance_score(query: str, doc_text: str, meta: dict | None = None) -> float:
    """0~1：query 词在文档/元数据中的覆盖度。"""
    q = tokenize(query)
    if not q:
        return 1.0
    meta = meta or {}
    blob = " ".join(
        [
            doc_text or "",
            str(meta.get("section_id") or ""),
            str(meta.get("heading") or ""),
            str(meta.get("knowledge_points") or ""),
            str(meta.get("source") or ""),
        ]
    )
    d = tokenize(blob)
    if not d:
        return 0.0
    hit = q & d
    return len(hit) / len(q)


def is_topic_relevant(
    query: str,
    doc_text: str,
    meta: dict | None = None,
    *,
    min_score: float = 0.25,
) -> bool:
    return topic_relevance_score(query, doc_text, meta) >= min_score
