"""进程内缓存：有界 + 可选 TTL + 线程安全。

两条构造语义，按场景选：

- ``get_or_create``：**构造在锁内**执行，同一 key 恰好构造一次。仅适用于「构造罕见、
  廉价且无 IO」的对象（如 LLM 客户端：整个进程生命周期只构造十几次）。
- ``get_or_compute``：**构造在锁外**执行，竞态下可能重复计算一次。用于「key 空间大、
  计算慢或带 IO」的场景（如 rerank 的 HTTP 调用）。**绝不能持锁等 IO** ——
  一次 30 秒的超时会把所有并发请求一起拖住。

命中时更新访问时间，淘汰按 LRU（最久未访问的先出）。计数与淘汰都在锁内完成。

**有状态对象禁止缓存。** 判据不是「构造是否昂贵」，而是「值是否有状态」。
反例：FakeToolModel 内部维护响应队列，被多个调用方共享后响应会互相穿插
（且耗尽后是静默循环复用、不报错）—— 这类对象必须每次新建。
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable

logger = logging.getLogger(__name__)


class BoundedCache[K, V]:
    """有界 + 可选 TTL 的进程内缓存。"""

    def __init__(
        self,
        max_size: int,
        ttl: float | None = None,
        *,
        name: str = "cache",
        evict_ratio: float = 0.25,
        on_evict: Callable[[V], None] | None = None,
    ) -> None:
        if max_size <= 0:
            raise ValueError("max_size 必须为正整数")
        if not 0 < evict_ratio <= 1:
            raise ValueError("evict_ratio 必须落在 (0, 1]")
        self._name = name
        self._data: dict[K, tuple[V, float]] = {}
        self._max_size = max_size
        self._ttl = ttl
        self._evict_ratio = evict_ratio
        self._on_evict = on_evict
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0

    def get(self, key: K) -> V | None:
        with self._lock:
            return self._get_locked(key)

    def get_or_create(self, key: K, factory: Callable[[], V]) -> V:
        """同一 key 恰好构造一次，杜绝重复构造有副作用的资源（如连接池）。

        前置条件：factory 必须是廉价、无 IO 的纯对象构造 —— 它在持锁期间执行。
        """
        with self._lock:
            value = self._get_locked(key)
            if value is not None:
                return value
            value = factory()
            self._insert_locked(key, value)
            return value

    def get_or_compute(self, key: K, factory: Callable[[], V]) -> V:
        """构造在锁外执行。竞态下最多重复计算一次，但绝不阻塞其他线程。"""
        value = self.get(key)
        if value is not None:
            return value
        value = factory()
        self.set(key, value)
        return value

    def set(self, key: K, value: V) -> None:
        with self._lock:
            self._insert_locked(key, value)

    def clear(self, *, notify: bool = True) -> None:
        """清空缓存并重置计数。notify=False 时不触发 on_evict。"""
        with self._lock:
            values = [v for v, _ in self._data.values()]
            self._data.clear()
            self._hits = 0
            self._misses = 0
        if notify:
            for value in values:
                self._notify_evict(value)

    @property
    def stats(self) -> dict[str, int | float]:
        with self._lock:
            hits, misses, size = self._hits, self._misses, len(self._data)
        total = hits + misses
        return {
            "size": size,
            "hits": hits,
            "misses": misses,
            "hit_rate": round(100 * hits / total, 1) if total else 0.0,
        }

    def __len__(self) -> int:
        with self._lock:
            return len(self._data)

    # ── 内部：以下方法都要求调用方已持有 self._lock ──────────
    def _get_locked(self, key: K) -> V | None:
        entry = self._data.get(key)
        if entry is None:
            self._misses += 1
            return None
        value, ts = entry
        if self._ttl is not None and time.monotonic() - ts >= self._ttl:
            self._data.pop(key, None)  # pop 而非 del：并发路径下也不会 KeyError
            self._misses += 1
            return None
        self._data[key] = (value, time.monotonic())  # LRU 触达
        self._hits += 1
        return value

    def _insert_locked(self, key: K, value: V) -> None:
        if len(self._data) >= self._max_size and key not in self._data:
            self._evict_locked()
        self._data[key] = (value, time.monotonic())

    def _evict_locked(self) -> None:
        """LRU 淘汰：按最后访问时间丢掉最旧的一批。"""
        if len(self._data) <= self._max_size:
            return
        evict_count = max(1, int(len(self._data) * self._evict_ratio))
        oldest = sorted(self._data.items(), key=lambda item: item[1][1])[:evict_count]
        victims = []
        for key, (value, _ts) in oldest:
            self._data.pop(key, None)  # pop 而非 del：并发路径下也不会 KeyError
            victims.append(value)
        if victims:
            logger.debug("%s: 淘汰 %d 项（当前 %d）", self._name, len(victims), len(self._data))
        for value in victims:
            self._notify_evict(value)

    def _notify_evict(self, value: V) -> None:
        if self._on_evict is None:
            return
        try:
            self._on_evict(value)
        except Exception:
            logger.debug("%s: on_evict 回调失败", self._name, exc_info=True)
