"""元数据增强模块

在分块后、入库前执行，为 chunk 自动提取关键词并写入 metadata：
- 基于 TextRank 算法提取关键词（jieba，无需 API 调用）
- 从标题路径中提取结构化关键词
- 合并去重后写入 metadata["keywords"]
- 支持后续按关键词过滤检索
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import List

from langchain_core.documents import Document

from app.rag.rag_utils import detect_content_type as _detect_content_type

logger = logging.getLogger(__name__)

# 关键词提取数量
_TOP_KEYWORDS = 8

# 中文停用词（高频但无意义的词）
_STOP_WORDS = frozenset({
    "的", "了", "在", "是", "我", "有", "和", "就", "不", "人", "都", "一",
    "一个", "上", "也", "很", "到", "说", "要", "去", "你", "会", "着",
    "没有", "看", "好", "自己", "这", "他", "她", "它", "们", "那", "些",
    "什么", "如何", "怎么", "哪些", "为什么", "可以", "因为", "所以",
    "但是", "而且", "或者", "如果", "虽然", "不过", "然后", "那么",
    "这个", "那个", "这些", "那些", "其", "此", "该", "每", "各",
    "即", "等", "等等", "之", "与", "及", "以", "为", "于", "从",
    "被", "把", "让", "给", "向", "比", "用", "通过", "进行",
})


def _extract_with_jieba(text: str, top_k: int = _TOP_KEYWORDS) -> List[str]:
    """使用 jieba TextRank 提取关键词"""
    try:
        import jieba
        import jieba.analyse
        return jieba.analyse.textrank(text, topK=top_k, withWeight=False)
    except ImportError:
        logger.debug("jieba not installed, falling back to simple extraction")
        return []


def _extract_simple(text: str, top_k: int = _TOP_KEYWORDS) -> List[str]:
    """简单关键词提取（无第三方依赖的降级方案）

    策略：提取中文词组（2-4字）和英文单词，按词频排序
    """
    # 提取中文词组（2-4字连续中文）
    cn_words = re.findall(r"[\u4e00-\u9fff]{2,4}", text)
    # 提取英文单词（3+字母）
    en_words = re.findall(r"[a-zA-Z]{3,}", text)

    all_words = cn_words + [w.lower() for w in en_words]

    # 过滤停用词
    all_words = [w for w in all_words if w not in _STOP_WORDS and len(w) >= 2]

    # 按词频排序
    from collections import Counter
    counter = Counter(all_words)
    return [w for w, _ in counter.most_common(top_k)]


def _extract_heading_keywords(heading: str) -> List[str]:
    """从标题路径中提取结构化关键词

    输入: "[操作系统 > 进程管理 > 死锁]"
    输出: ["操作系统", "进程管理", "死锁"]
    """
    if not heading:
        return []

    # 去除方括号，按 > 分割
    heading = heading.strip("[]")
    parts = [p.strip() for p in heading.split(">") if p.strip()]
    return parts


def _normalize_keyword_list(values: List[str]) -> List[str]:
    normalized: List[str] = []
    seen: set[str] = set()
    for value in values:
        keyword = value.strip()
        if not keyword:
            continue
        lowered = keyword.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        normalized.append(keyword)
    return normalized


def _build_heading_slug(heading_path: str) -> str:
    parts = _extract_heading_keywords(heading_path)
    if not parts:
        return ""
    slug = "/".join(part.strip().lower().replace(" ", "-") for part in parts if part.strip())
    return slug


def _estimate_token_count(text: str) -> int:
    ascii_chars = sum(1 for char in text if ord(char) < 128)
    non_ascii_chars = len(text) - ascii_chars
    return max(1, ascii_chars // 4 + non_ascii_chars)


def extract_keywords(text: str, heading: str = "", top_k: int = _TOP_KEYWORDS) -> List[str]:
    """提取关键词，合并标题关键词和正文关键词

    优先级：标题关键词 > TextRank关键词 > 简单词频关键词
    """
    keywords: List[str] = []

    # 1. 标题关键词（优先级最高）
    heading_kw = _extract_heading_keywords(heading)
    keywords.extend(heading_kw)

    # 2. 正文关键词
    body_kw = _extract_with_jieba(text, top_k=top_k)
    if not body_kw:
        body_kw = _extract_simple(text, top_k=top_k)

    # 合并去重，保持顺序
    seen = set(keywords)
    for kw in body_kw:
        if kw not in seen:
            keywords.append(kw)
            seen.add(kw)

    return keywords[:top_k]


def enhance_documents(documents: List[Document]) -> List[Document]:
    for doc in documents:
        heading = doc.metadata.get("heading", "") or doc.metadata.get("section.path", "")
        heading_keywords = _extract_heading_keywords(heading)
        keywords = _normalize_keyword_list(extract_keywords(doc.page_content, heading=heading))
        source_path = str(doc.metadata.get("source_path") or doc.metadata.get("source_file") or "")
        source_name = Path(source_path).stem if source_path else ""
        source_ext = str(doc.metadata.get("source_ext") or Path(source_path).suffix.lower())
        content_type = _detect_content_type(doc.page_content, doc.metadata)

        # ── 新规范字段 (content.*, source.*) ──
        doc.metadata["source_name"] = source_name
        doc.metadata["source_ext"] = source_ext
        doc.metadata["source_type"] = doc.metadata.get("source_type") or source_ext.lstrip(".") or "unknown"
        doc.metadata["content_type"] = content_type
        doc.metadata["keywords"] = ", ".join(keywords)
        doc.metadata["heading_keywords"] = ", ".join(heading_keywords) if heading_keywords else ""
        doc.metadata["heading_slug"] = _build_heading_slug(str(doc.metadata.get("heading_path") or heading))
        doc.metadata["has_heading"] = bool(heading)
        doc.metadata["has_code_block"] = "```" in doc.page_content or "~~~" in doc.page_content or bool(re.search(r"(^|\n)\s{4,}\S", doc.page_content))
        doc.metadata["line_count"] = len(doc.page_content.splitlines())
        doc.metadata["estimated_tokens"] = _estimate_token_count(doc.page_content)
        doc.metadata["is_structured"] = content_type in {"section", "list", "exercise", "answer", "code_mixed", "merged_qa"}

        # ── Chroma 仅支持 str/int/float/bool，无 list 类型 ──

    logger.info("Enhanced %d documents with keywords", len(documents))
    return documents
