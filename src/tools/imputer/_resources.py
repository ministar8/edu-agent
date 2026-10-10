"""资源配额控制：跟踪昂贵操作调用次数，超限时自动降级。

从 imputer.py 拆出，供各子模块共享同一个全局监控器 `_resource_guard`。
"""

from __future__ import annotations

import logging
import time
from functools import wraps

logger = logging.getLogger(__name__)


# ── 资源控制配置 ────────────────────────────────────

_QUOTA_CONFIG = {
    "jieba_keyword": {"max_calls": 200, "timeout": 5.0},  # jieba 关键词提取
    "jieba_stopword": {"max_calls": 500, "timeout": 2.0},  # jieba 停用词过滤
    "semantic_segment": {"max_calls": 100, "timeout": 10.0},  # 语义连贯分段
    "pdf_feature": {"max_calls": 300, "timeout": 3.0},  # PDF 特征检测
    "llm_call": {"max_calls": 50, "timeout": 30.0, "retries": 2},  # LLM 调用（预留）
}


class _ResourceGuard:
    """资源配额监控器：跟踪昂贵操作调用次数，超限时自动降级"""

    def __init__(self, config: dict | None = None):
        self._config = config or _QUOTA_CONFIG
        self._counters: dict[str, int] = {}
        self._degraded: set[str] = set()  # 已降级的操作集合

    def is_available(self, operation: str) -> bool:
        """检查操作是否仍在配额内"""
        if operation in self._degraded:
            return False
        max_calls = self._config.get(operation, {}).get("max_calls", float("inf"))
        current = self._counters.get(operation, 0)
        return current < max_calls

    def record(self, operation: str) -> None:
        """记录一次操作调用"""
        self._counters[operation] = self._counters.get(operation, 0) + 1

    def degrade(self, operation: str) -> None:
        """标记操作为已降级"""
        if operation not in self._degraded:
            self._degraded.add(operation)
            logger.warning(
                "ResourceGuard: '%s' degraded (calls=%d, limit=%d)",
                operation,
                self._counters.get(operation, 0),
                self._config.get(operation, {}).get("max_calls", 0),
            )

    def check_and_record(self, operation: str) -> bool:
        """检查配额并记录调用，返回是否可用"""
        if not self.is_available(operation):
            if operation not in self._degraded:
                self.degrade(operation)
            return False
        self.record(operation)
        return True

    def reset(self) -> None:
        """重置所有计数器和降级状态"""
        self._counters.clear()
        self._degraded.clear()

    def summary(self) -> str:
        parts = [f"{op}:{cnt}" for op, cnt in sorted(self._counters.items())]
        degraded = ", ".join(sorted(self._degraded)) if self._degraded else "none"
        return f"calls({', '.join(parts)}) degraded({degraded})"


# 全局资源监控器实例
_resource_guard = _ResourceGuard()


def _with_timeout(timeout: float):
    """超时装饰器：超时则返回 None 并降级"""

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            start = time.perf_counter()
            try:
                result = func(*args, **kwargs)
            except Exception as e:
                logger.warning("Timeout wrapper: %s raised %s", func.__name__, e)
                return None
            elapsed = time.perf_counter() - start
            if elapsed > timeout:
                logger.warning(
                    "Timeout: %s took %.1fs (limit=%.1fs)", func.__name__, elapsed, timeout
                )
                return None
            return result

        return wrapper

    return decorator
