from __future__ import annotations

import hashlib
import logging

from core.cache import BoundedCache
from core.settings import settings
from prompts import HYDE_PROMPT
from rag.llm_calls import call_text_sync
from rag.query_classifier import QueryCategory

logger = logging.getLogger(__name__)

_HYDE_CACHE_MAX = 128
_hyde_cache: BoundedCache[str, str] = BoundedCache(max_size=_HYDE_CACHE_MAX, name="hyde")


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
    short_concept = (
        docs_count == 0 and cat.is_concept and (cat.is_short or len(query.strip()) <= 18)
    )
    return low_docs or low_score or short_concept


def _build_hyde_text(normalized_query: str) -> str:
    messages = HYDE_PROMPT.format_messages(
        query=normalized_query, max_chars=settings.HYDE_MAX_CHARS
    )
    # 失败降级为"不使用 HyDE"（空串），由调用方跳过 HyDE 分支
    text = call_text_sync(messages, temperature=settings.TEMP_DEFAULT, stage="hyde") or ""
    if len(text) > settings.HYDE_MAX_CHARS:
        text = text[: settings.HYDE_MAX_CHARS]
    return text


def generate_hyde_query(query: str) -> str:
    normalized = query.strip()
    if not normalized:
        return ""
    # 带 LLM 调用（IO），用 get_or_compute：允许竞态重复生成，但不持锁等待
    return _hyde_cache.get_or_compute(_cache_key(normalized), lambda: _build_hyde_text(normalized))
