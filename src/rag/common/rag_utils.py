"""RAG 共享工具函数

消除各模块间的重复代码：token 估算、查询归一化、关键词提取、内容类型检测。
统一维护点，所有模块从此导入。
"""

from __future__ import annotations

import logging
import re

import jieba
from langchain_core.documents import Document

logger = logging.getLogger(__name__)

# ── 领域词典（防止 jieba 把专业词切坏）─────────────────
# ★ 为什么必须有：jieba 默认词典不含这些词组，会把相邻字误并成一个不存在的词。
#   实测（2026-10-01）：「单链表逆置」被切成 `['单链', '表逆置']`、「单链表就地逆置」
#   切成 `['单链', '表就', '地逆置']` —— **「逆置」根本不成词**。后果是
#   `extract_query_terms` 给出坏词 → `focus` 路由按坏词召回 → 目标 chunk（L2 方法层
#   「逆置：三指针 pre/cur/nxt 逐个头插」）召回不到，整池退化为 legacy 讲义。
#   加入词典后切分为 `['单链表', '逆置']`，同一 query 目标 chunk 直接进包。
#
# ⚠️ 只影响**查询侧**分词（`extract_query_terms` / BM25 `cut_for_search` / topic 判分）；
#   入库切分（`splitter` / `cleaner`）不依赖 jieba，故**改这里不需要重建索引**。
#   但会改变召回结果 —— 改动后必须跑 `evaluation.retrieval_gate`。
_DOMAIN_WORDS: tuple[str, ...] = (
    # 线性表 / 链表
    "单链表",
    "双链表",
    "循环链表",
    "静态链表",
    "头结点",
    "逆置",
    "就地逆置",
    "头插法",
    "尾插法",
)

_jieba_words_registered = False


def ensure_jieba_domain_words() -> None:
    """把领域词注册进 jieba 全局词典（幂等，进程内一次）。

    jieba 的词典是**进程级全局**，注册一次对所有调用点生效。
    """
    global _jieba_words_registered
    if _jieba_words_registered:
        return
    for word in _DOMAIN_WORDS:
        jieba.add_word(word, freq=20000)
    _jieba_words_registered = True
    logger.debug("已注册 %d 个领域词到 jieba 词典", len(_DOMAIN_WORDS))


ensure_jieba_domain_words()

# ── 常量 ──────────────────────────────────────────────

_MAX_QUERY_TERMS = 6

_QUERY_STOP_WORDS = frozenset(
    {
        "什么",
        "怎么",
        "如何",
        "为什么",
        "请问",
        "一下",
        "一下子",
        "有关",
        "关于",
        "这个",
        "那个",
        "哪些",
        "是否",
        "可以",
        "一下吧",
        "帮我",
        "讲解",
        "解释",
        "说明",
        "作用",
        "使用",
        "方法",
        "解释一下",
        "说明一下",
        "介绍一下",
        "讲一下",
        "讲讲",
        "简述",
        "阐述",
        "是",
        "的",
        "了",
        "在",
        "有",
        "和",
        "与",
        "及",
        "或",
        "等",
        "都",
        "也",
        "还",
        "又",
        "那",
        "这",
        "被",
        "把",
        "从",
        "到",
        "对",
        "向",
        "给",
        "让",
        "用",
        "以",
        # ── code 类查询的功能词：不携带内容语义，混入 focus_query 会挤掉真实内容词 ──
        # 例：「用信号量写出生产者—消费者问题的伪代码」若不过滤「写出/伪代码」，
        #     _rank_terms_by_specificity 会把「写出」(0 集合匹配, specificity=0.5) 与
        #     「生产者」同分，又因原顺序靠前而排进 focus_query → 变成「信号量 写出」。
        "写出",
        "编写",
        "编写出",
        "实现",
        "伪代码",
        "写一段",
        "编写一段",
        "给出",
        "输出",
        "打印",
        "求解",
        "计算",
    }
)


# ── Token 估算 ───────────────────────────────────────


def estimate_tokens(text: str) -> int:
    """粗估 token 数：中文 1 字符 ≈ 1.5 tokens，ASCII 1 字符 ≈ 0.25 tokens"""
    cn = sum(1 for c in text if "一" <= c <= "鿿")
    en = len(text) - cn
    return int(cn * 1.5 + en * 0.25)


# ── 查询归一化 ───────────────────────────────────────


def normalize_query_text(query: str) -> str:
    """统一查询归一化：去除多余空白"""
    return re.sub(r"\s+", " ", str(query).strip())


# ── 关键词提取 ───────────────────────────────────────


def extract_query_terms(query: str, max_terms: int = _MAX_QUERY_TERMS) -> list[str]:
    """用 jieba 精准分词提取查询关键词

    jieba.cut() 对中文精准分词，过滤停用词后保留有意义的术语词。
    英文 token 通过 regex 补充提取，避免 jieba 将英文缩写误切。
    """
    normalized = normalize_query_text(query)
    if not normalized:
        return []

    terms: list[str] = []
    seen: set[str] = set()

    # jieba 精准分词
    for word in jieba.cut(normalized):
        word = word.strip()
        if not word or word in _QUERY_STOP_WORDS or word.lower() in _QUERY_STOP_WORDS:
            continue
        if len(word) == 1 and not word.isascii():
            continue
        lowered = word.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        terms.append(word)
        if len(terms) >= max_terms:
            break

    # 补充：regex 提取英文缩写/术语
    en_tokens = re.findall(r"[A-Za-z_][A-Za-z0-9_\.]{1,}", normalized)
    for token in en_tokens:
        lowered = token.lower()
        if lowered not in seen and lowered not in _QUERY_STOP_WORDS:
            seen.add(lowered)
            terms.append(token)
            if len(terms) >= max_terms:
                break

    return terms


def get_bm25_stop_words() -> frozenset[str]:
    return _QUERY_STOP_WORDS


# ── 内容键（去重 / 确定性排序） ──────────────────────


def content_key(doc: Document) -> str:
    """去重与确定性排序键：优先内容哈希，缺失时退回「来源 + 正文前 80 字」。

    供 pipeline（HyDE 追加去重）与 routes（top-k 平票定序）共用。
    实现只能有这一份 —— 改动会同时影响召回边界与去重集合。
    """
    return str(
        doc.metadata.get("content_hash")
        or f"{doc.metadata.get('source', '') or doc.metadata.get('source_file', '')}:"
        f"{doc.page_content[:80]}"
    )


# ── 内容类型检测 ─────────────────────────────────────


def detect_content_type(text: str, metadata: dict) -> str:
    """检测 chunk 内容类型

    供 enhancer.py 和 splitter.py 共用，避免跨模块循环依赖。
    """
    stripped = text.strip()
    if not stripped:
        return "empty"

    heading_title = str(metadata.get("heading_title") or "").lower()
    source_ext = str(metadata.get("source_ext") or "").lower()

    if (
        metadata.get("chunk_role") == "merged_qa"
        or metadata.get("section.chunk_role") == "merged_qa"
    ):
        return "merged_qa"

    if "```" in stripped or "~~~" in stripped:
        return "code_mixed"
    if re.search(r"(^|\n)\s{4,}\S", text):
        return "code_mixed"
    if re.search(r"(^|\n)\|.+\|(\n|$)", stripped) and re.search(
        r"(^|\n)\|[-:| ]+\|(\n|$)", stripped
    ):
        return "table"
    if re.search(r"\$\$.+?\$\$", stripped, re.DOTALL):
        return "formula"
    if re.search(r"(^|\n)#{1,4}\s+", text):
        return "section"
    if re.search(r"(^|\n)\s*[-*+]\s+", text) or re.search(r"(^|\n)\s*\d+[.)、]\s+", text):
        return "list"
    if source_ext == ".md" and "题" in heading_title:
        return "exercise"
    if source_ext == ".md" and any(token in heading_title for token in ["答案", "解析"]):
        return "answer"
    if re.search(r"def |class |import |from .* import |if __name__ == ['\"]__main__['\"]", text):
        return "code_mixed"
    return "text"


# ── LLM getter（已迁移至 core.llm） ────────

from core.llm import get_llm  # noqa: E402, F401 — 向后兼容导出
