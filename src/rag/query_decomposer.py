"""查询分解模块

将跨知识点综合查询拆分为 2-4 个子查询，每个聚焦单一知识点。
仅在查询长度 > 30 字或 query_classifier 判定为"综合/对比"类型时触发。

设计要点：
  - async decompose()：LLM 调用天然 async
  - sync decompose_sync()：**仅供同步上下文**（ingest 后的缓存预热）
  - 原始查询本身也作为一条子查询，decompose 返回单元素列表时等价于不分解
  - 缓存用 md5(query) 做键，减少 LLM 抖动和成本
  - JSON 解析前剥 markdown 代码块标记
"""

from __future__ import annotations

import hashlib
import logging
import re

from core.cache import BoundedCache
from core.settings import settings
from prompts import DECOMPOSE_PROMPT
from rag.llm_calls import (
    PromptInput,
    call_structured,
    call_structured_sync,
    call_text,
    call_text_sync,
)
from rag.parse_utils import parse_llm_json
from rag.query_classifier import QueryCategory
from rag.schemas import DecomposeResult

logger = logging.getLogger(__name__)

# ── 常量 ──────────────────────────────────────────────────

_CACHE_TTL = 3600  # 1 小时
_CACHE_MAX = 128
_DECOMPOSE_CACHE: BoundedCache[str, list[str]] = BoundedCache(
    max_size=_CACHE_MAX, ttl=_CACHE_TTL, name="decompose"
)

_MAX_SUB_QUERIES = 3


# ── 触发判断 ──────────────────────────────────────────────


def should_decompose(query: str, cat: QueryCategory) -> bool:
    """判断是否需要查询分解

    触发条件（满足任一）：
      - 查询长度 > 30 字
      - is_comparison（对比/异同类）
      - is_long（长查询）

    不触发：
      - is_short（短查询）
      - 纯概念/定义查询（is_concept 且非 comparison）
    """
    if cat.is_short:
        return False
    if cat.is_comparison or cat.is_long:
        return True
    if len(query) > 30:
        return True
    return False


# ── JSON 解析 ──────────────────────────────────────────────


def _parse_sub_queries(raw: str) -> list[str]:
    """解析 LLM 返回的子查询列表（兜底用，主路径用 with_structured_output）"""
    parsed = parse_llm_json(raw, fallback_default=None)
    if not isinstance(parsed, list):
        return []
    result = [str(q).strip() for q in parsed if str(q).strip()]
    return result[:_MAX_SUB_QUERIES]


# ── 缓存 ──────────────────────────────────────────────────


def _cache_key(query: str) -> str:
    return hashlib.md5(query.encode()).hexdigest()


def _get_cached(query: str) -> list[str] | None:
    return _DECOMPOSE_CACHE.get(_cache_key(query))


def _set_cached(query: str, sub_queries: list[str]) -> None:
    _DECOMPOSE_CACHE.set(_cache_key(query), sub_queries)


# ── 共享核心逻辑 ──────────────────────────────────────────


def _ensure_cat(query: str, cat: QueryCategory | None = None) -> QueryCategory:
    if cat is None:
        from rag.query_classifier import classify_query
        from rag.rag_utils import extract_query_terms, normalize_query_text

        _norm = normalize_query_text(query)
        _terms = extract_query_terms(_norm)
        return classify_query(query, _terms)
    return cat


def _postprocess_subs(query: str, sub_queries: list[str]) -> list[str]:
    if not sub_queries:
        return [query]
    if query not in sub_queries:
        sub_queries = [*sub_queries, query]
    return sub_queries[: _MAX_SUB_QUERIES + 1]


def _clean_rule_part(text: str) -> str:
    text = re.sub(r"^(请|帮我|解释|说明|比较|对比|分析|讲解|一下)+", "", text.strip())
    text = re.sub(r"(的)?(区别|差异|不同|异同|关系|联系|对比|比较)$", "", text.strip())
    return text.strip("：:，,。？? ")


def _rule_decompose(query: str, cat: QueryCategory) -> list[str]:
    if not cat.is_comparison:
        return []
    if len(query) > 80:
        return []
    if not re.search(r"(区别|差异|不同|异同|关系|联系|对比|比较)", query):
        return []
    parts = [
        _clean_rule_part(part)
        for part in re.split(r"\s*(?:和|与|及|以及|、|，|,|\s+vs\s+|\s+VS\s+)\s*", query)
    ]
    parts = [part for part in parts if len(part) >= 2]
    if len(parts) < 2 or len(parts) > 3:
        return []
    subs = [f"{part}的核心概念" for part in parts[:2]]
    return [query, *subs]


def _llm_decompose_fallback(prompt: PromptInput) -> list[str]:
    text = call_text_sync(prompt, temperature=settings.TEMP_DEFAULT, stage="decompose_fallback")
    return _parse_sub_queries(text or "")


# ── async 分解 ────────────────────────────────────────────


async def decompose(query: str, cat: QueryCategory | None = None) -> list[str]:
    """异步查询分解。返回子查询列表，单元素时等价于不分解。"""
    cached = _get_cached(query)
    if cached is not None:
        return cached

    cat = _ensure_cat(query, cat)
    if not should_decompose(query, cat):
        return [query]
    rule_subs = _rule_decompose(query, cat)
    if rule_subs:
        result = _postprocess_subs(query, rule_subs)
        _set_cached(query, result)
        return result

    prompt = DECOMPOSE_PROMPT.format_messages(query=query, max_subs=_MAX_SUB_QUERIES)

    # 结构化输出优先；失败则退化为纯文本解析；两者都失败则视为不分解
    structured = await call_structured(
        prompt,
        DecomposeResult,
        temperature=settings.TEMP_DEFAULT,
        timeout=settings.PRE_RETRIEVAL_TIMEOUT,
        stage="decompose",
    )
    if structured is not None:
        sub_queries = structured.sub_queries
    else:
        text = await call_text(
            prompt,
            temperature=settings.TEMP_DEFAULT,
            timeout=settings.PRE_RETRIEVAL_TIMEOUT,
            stage="decompose_fallback",
        )
        sub_queries = _parse_sub_queries(text or "")

    result = _postprocess_subs(query, sub_queries)
    _set_cached(query, result)
    return result


# ── sync 桥接（LEGACY：供非 async 上下文使用，async 上下文请用 decompose()） ──


def decompose_sync(query: str, cat: QueryCategory | None = None) -> list[str]:
    """同步查询分解（LEGACY，**当前仓库内无调用方**）。

    历史：曾由同步版 ``retriever.retrieve_documents`` 调用。该函数已改为委托
    ``aretrieve_documents``（消除 448 行双份流水线），因此本函数不再被引用。

    保留原因：它是公开的同步桥接工具，直接删除属于对外 API 变更，交由仓库负责人决定
    （见 ENGINEERING.md 附录 A）。若要清理，请连同 ``llm_calls.call_structured_sync``
    一起评估。

    **不要在 `async def` 里直接调用** —— `llm.invoke()` 不会抛错，但会**阻塞事件循环
    整个 LLM 调用时长**（客户端超时 90 秒）。async 上下文请用 `await decompose()`。
    """
    cached = _get_cached(query)
    if cached is not None:
        return cached

    cat = _ensure_cat(query, cat)
    if not should_decompose(query, cat):
        return [query]
    rule_subs = _rule_decompose(query, cat)
    if rule_subs:
        result = _postprocess_subs(query, rule_subs)
        _set_cached(query, result)
        return result

    prompt = DECOMPOSE_PROMPT.format_messages(query=query, max_subs=_MAX_SUB_QUERIES)
    structured = call_structured_sync(
        prompt,
        DecomposeResult,
        temperature=settings.TEMP_DEFAULT,
        stage="decompose_sync",
    )
    sub_queries = (
        structured.sub_queries if structured is not None else _llm_decompose_fallback(prompt)
    )

    result = _postprocess_subs(query, sub_queries)
    _set_cached(query, result)
    return result
