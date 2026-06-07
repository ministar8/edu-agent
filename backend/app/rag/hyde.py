from __future__ import annotations

import hashlib
import logging

from app.config import settings
from app.rag.query_classifier import QueryCategory
from app.rag.rag_utils import get_llm

logger = logging.getLogger(__name__)

_hyde_cache: dict[str, str] = {}
_HYDE_CACHE_MAX = 128

_HYDE_PROMPT = """你是408考研教材知识库检索增强器。
请根据学生问题生成一段可能出现在教材中的、用于向量检索的假设性知识片段。
要求：
- 只写客观教材风格内容，不要回答用户
- 不要编造章节、页码、题号或来源
- 保留关键术语和同义表达
- 控制在 {max_chars} 字以内

学生问题：{query}

假设性知识片段："""


def _cache_key(query: str) -> str:
    return hashlib.sha256(query.strip().encode("utf-8")).hexdigest()[:16]


def should_trigger_hyde(
    query: str,
    docs_count: int,
    top_rerank_score: float,
    cat: QueryCategory,
) -> bool:
    if not settings.HYDE_ENABLED:
        return False
    if cat.is_answer or cat.is_exercise or cat.is_code:
        return False
    if not query.strip():
        return False
    low_docs = docs_count < settings.HYDE_MIN_DOCS
    low_score = docs_count == 0 and top_rerank_score < settings.HYDE_RERANK_SCORE_THRESHOLD
    short_concept = docs_count == 0 and cat.is_concept and (cat.is_short or len(query.strip()) <= 18)
    return low_docs or low_score or short_concept


def generate_hyde_query(query: str) -> str:
    normalized = query.strip()
    if not normalized:
        return ""
    key = _cache_key(normalized)
    cached = _hyde_cache.get(key)
    if cached is not None:
        return cached
    try:
        llm = get_llm(streaming=False)
        prompt = _HYDE_PROMPT.format(query=normalized, max_chars=settings.HYDE_MAX_CHARS)
        raw = llm.invoke(prompt)
        text = raw.content if hasattr(raw, "content") else str(raw)
        text = str(text or "").strip()
        if len(text) > settings.HYDE_MAX_CHARS:
            text = text[:settings.HYDE_MAX_CHARS]
    except Exception as e:
        logger.warning("HyDE generation failed: %s", e)
        text = ""
    if len(_hyde_cache) > _HYDE_CACHE_MAX:
        # Partial eviction: delete oldest 25% to avoid cache stampede
        _evict_count = max(1, len(_hyde_cache) // 4)
        for _key in list(_hyde_cache.keys())[:_evict_count]:
            del _hyde_cache[_key]
    _hyde_cache[key] = text
    return text
