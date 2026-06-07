"""查询分解模块

将跨知识点综合查询拆分为 2-4 个子查询，每个聚焦单一知识点。
仅在查询长度 > 30 字或 query_classifier 判定为"综合/对比"类型时触发。

设计要点：
  - async decompose()：LLM 调用天然 async
  - sync decompose_sync()：供 retrieve_documents 同步调用，自动检测 async 上下文桥接
  - 原始查询本身也作为一条子查询，decompose 返回单元素列表时等价于不分解
  - 缓存用 md5(query) 做键，减少 LLM 抖动和成本
  - JSON 解析前剥 markdown 代码块标记
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
import time

from app.rag.query_classifier import QueryCategory
from app.rag.schemas import DecomposeResult
from app.rag.parse_utils import parse_llm_json

logger = logging.getLogger(__name__)

# ── 常量 ──────────────────────────────────────────────────

_DECOMPOSE_CACHE: dict[str, tuple[float, list[str]]] = {}  # md5 → (timestamp, sub_queries)
_CACHE_TTL = 3600  # 1 小时
_CACHE_MAX = 128

_MAX_SUB_QUERIES = 3
_DECOMPOSE_TIMEOUT = 10.0  # 单次 LLM 调用超时


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


# ── Prompt ────────────────────────────────────────────────

_DECOMPOSE_PROMPT = """\
将以下408考研问题拆分为独立的子问题，每个子问题聚焦单一知识点。

规则：
- 拆分为 2-{max_subs} 个子问题
- 每个子问题只涉及一个学科/知识点
- 如果问题本身已聚焦单一知识点，返回单元素数组
- 子问题应保留原问题中的关键术语

示例：
问题：比较Cache写回法与虚拟存储器的写回策略的异同
子问题：["Cache写回法的工作原理", "虚拟存储器写回策略的工作原理", "两者异同对比"]

问题：{query}

请以JSON格式输出。"""


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
    key = _cache_key(query)
    entry = _DECOMPOSE_CACHE.get(key)
    if entry is None:
        return None
    ts, sub_queries = entry
    if time.time() - ts > _CACHE_TTL:
        del _DECOMPOSE_CACHE[key]
        return None
    return sub_queries


def _set_cached(query: str, sub_queries: list[str]) -> None:
    key = _cache_key(query)
    if len(_DECOMPOSE_CACHE) >= _CACHE_MAX:
        # 淘汰最旧的
        oldest_key = min(_DECOMPOSE_CACHE, key=lambda k: _DECOMPOSE_CACHE[k][0])
        del _DECOMPOSE_CACHE[oldest_key]
    _DECOMPOSE_CACHE[key] = (time.time(), sub_queries)


# ── 共享核心逻辑 ──────────────────────────────────────────

def _ensure_cat(query: str, cat: QueryCategory | None = None) -> QueryCategory:
    if cat is None:
        from app.rag.query_classifier import classify_query
        from app.rag.rag_utils import extract_query_terms, normalize_query_text
        _norm = normalize_query_text(query)
        _terms = extract_query_terms(_norm)
        return classify_query(query, _terms)
    return cat


def _postprocess_subs(query: str, sub_queries: list[str]) -> list[str]:
    if not sub_queries:
        return [query]
    if query not in sub_queries:
        sub_queries = [*sub_queries, query]
    return sub_queries[:_MAX_SUB_QUERIES + 1]


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
    parts = [_clean_rule_part(part) for part in re.split(r"\s*(?:和|与|及|以及|、|，|,|\s+vs\s+|\s+VS\s+)\s*", query)]
    parts = [part for part in parts if len(part) >= 2]
    if len(parts) < 2 or len(parts) > 3:
        return []
    subs = [f"{part}的核心概念" for part in parts[:2]]
    return [query, *subs]


def _llm_decompose_fallback(llm, prompt: str) -> list[str]:
    try:
        raw = llm.invoke(prompt)
        text = raw.content if hasattr(raw, "content") else str(raw)
        return _parse_sub_queries(text)
    except Exception:
        return []


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

    from app.rag.rag_utils import get_llm
    llm = get_llm(streaming=False)
    prompt = _DECOMPOSE_PROMPT.format(query=query, max_subs=_MAX_SUB_QUERIES)
    try:
        structured_llm = llm.with_structured_output(DecomposeResult)
        result = await asyncio.wait_for(structured_llm.ainvoke(prompt), timeout=_DECOMPOSE_TIMEOUT)
        sub_queries = result.sub_queries
    except asyncio.TimeoutError:
        logger.warning("Decompose timeout: %s", query[:50])
        sub_queries = []
    except Exception as e:
        logger.warning("Decompose structured output failed: %s", e)
        try:
            raw = await asyncio.wait_for(llm.ainvoke(prompt), timeout=_DECOMPOSE_TIMEOUT)
            sub_queries = _parse_sub_queries(raw.content if hasattr(raw, "content") else str(raw))
        except Exception:
            sub_queries = []

    result = _postprocess_subs(query, sub_queries)
    _set_cached(query, result)
    return result


# ── sync 桥接（LEGACY：供非 async 上下文使用，async 上下文请用 decompose()） ──


def decompose_sync(query: str, cat: QueryCategory | None = None) -> list[str]:
    """同步查询分解（LEGACY：在 async 上下文中请使用 await decompose()）。

    此函数使用 llm.invoke() 同步调用 LLM，仅适用于：
    - 纯 sync 上下文（如 evaluation/adapters.py）
    - asyncio.to_thread() 包裹的线程池中

    在 async def 内部直接调用此函数是安全的（因为 llm.invoke 是 sync，
    不涉及 asyncio.run），但推荐使用 await decompose() 以获得真正的异步 I/O。
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

    from app.rag.rag_utils import get_llm
    llm = get_llm(streaming=False)
    prompt = _DECOMPOSE_PROMPT.format(query=query, max_subs=_MAX_SUB_QUERIES)
    try:
        structured_llm = llm.with_structured_output(DecomposeResult)
        sub_queries = structured_llm.invoke(prompt).sub_queries
    except Exception as e:
        logger.warning("Decompose structured output failed: %s", e)
        sub_queries = _llm_decompose_fallback(llm, prompt)

    result = _postprocess_subs(query, sub_queries)
    _set_cached(query, result)
    return result
