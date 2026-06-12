"""RAG 共享工具函数

消除各模块间的重复代码：token 估算、查询归一化、关键词提取、内容类型检测。
统一维护点，所有模块从此导入。
"""

from __future__ import annotations

import logging
import re

import jieba

logger = logging.getLogger(__name__)

# ── 常量 ──────────────────────────────────────────────

_MAX_QUERY_TERMS = 6

_QUERY_STOP_WORDS = frozenset({
    "什么", "怎么", "如何", "为什么", "请问", "一下", "一下子", "有关", "关于", "这个", "那个",
    "哪些", "是否", "可以", "一下吧", "帮我", "讲解", "解释", "说明", "作用", "使用", "方法",
    "解释一下", "说明一下", "介绍一下", "讲一下", "讲讲", "简述", "阐述",
    "是", "的", "了", "在", "有", "和", "与", "及", "或", "等", "都", "也", "还", "又",
    "那", "这", "被", "把", "从", "到", "对", "向", "给", "让", "用", "以",
})


# ── Token 估算 ───────────────────────────────────────

def estimate_tokens(text: str) -> int:
    """粗估 token 数：中文 1 字符 ≈ 1.5 tokens，ASCII 1 字符 ≈ 0.25 tokens"""
    cn = sum(1 for c in text if '一' <= c <= '鿿')
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

    if metadata.get("chunk_role") == "merged_qa" or metadata.get("section.chunk_role") == "merged_qa":
        return "merged_qa"

    if "```" in stripped or "~~~" in stripped:
        return "code_mixed"
    if re.search(r"(^|\n)\s{4,}\S", text):
        return "code_mixed"
    if re.search(r"(^|\n)\|.+\|(\n|$)", stripped) and re.search(r"(^|\n)\|[-:| ]+\|(\n|$)", stripped):
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


# ── LLM getter（已迁移至 llm_provider.py） ────────

from app.rag.llm_provider import (    # noqa: F401 — 向后兼容导出
    get_llm,
    create_llm,
    detect_provider,
    build_llm_kwargs,
    ProviderConfig,
)
