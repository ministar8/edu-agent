"""运行时观测指标聚合（供 `/api/metrics` 使用）。

**为什么单独一个模块**：`service/` 与 `rag/` 是解耦的 —— `service.py` 不 import rag。
这里用**惰性导入**聚合 rag 的缓存统计，与 `service/health.py` 探测外部依赖同一模式。

**为什么放 `/api/metrics` 而不是塞进 `/health`**：`/health` 被 Docker healthcheck 使用，
它要并发探测 embedding / reranker / chromadb 三个外部依赖 —— **必须快**，
且它的语义是「依赖是否健康」。缓存命中率是**运行统计**，不是依赖健康；
混进去会让 healthcheck 语义变模糊、payload 变重，还可能让采集方误判。
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)


def _query_cache_stats() -> dict[str, int | float]:
    """检索结果缓存的命中统计。"""
    from rag.retriever import cache_stats

    return cache_stats()


def _semantic_cache_stats() -> dict[str, Any]:
    """语义缓存的命中统计（含条目数与上限）。"""
    from rag.semantic_cache import get_semantic_cache

    return get_semantic_cache().stats()


# 缓存名 -> 取值函数。新增缓存只需在此登记一行。
_CACHE_PROBES: tuple[tuple[str, Callable[[], dict[str, Any]]], ...] = (
    ("query", _query_cache_stats),
    ("semantic", _semantic_cache_stats),
)


def collect_cache_stats() -> dict[str, Any]:
    """聚合各缓存的命中统计。

    **单个缓存读取失败不应让整个端点失败** —— 每项独立捕获并记录，
    失败项返回 `{"error": <异常类名>}`，其余照常返回。
    否则一个缓存初始化异常会让运维完全看不到另一个缓存的健康状况。
    """
    result: dict[str, Any] = {}
    for name, probe in _CACHE_PROBES:
        try:
            result[name] = probe()
        except Exception as exc:
            logger.warning("读取 %s 缓存统计失败: %s", name, exc, exc_info=True)
            result[name] = {"error": type(exc).__name__}
    return result


def collect_metrics() -> dict[str, Any]:
    """`/api/metrics` 的响应体。"""
    return {"cache": collect_cache_stats()}
