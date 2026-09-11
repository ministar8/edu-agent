"""BoundedCache 的语义与并发安全测试。

并发用例针对的是重构前真实存在的崩溃路径：淘汰循环用 `del` 删已被其他线程删掉的键
会抛 KeyError（RAG 同步逻辑通过 asyncio.to_thread 跑在线程池里，是真并发）。
"""

import threading
import time

import pytest

from core.cache import BoundedCache


class TestBasicSemantics:
    def test_miss_returns_none(self):
        cache: BoundedCache[str, int] = BoundedCache(max_size=4)
        assert cache.get("k") is None

    def test_get_or_create_builds_once(self):
        cache: BoundedCache[str, int] = BoundedCache(max_size=4)
        calls: list[int] = []

        def factory() -> int:
            calls.append(1)
            return 42

        assert cache.get_or_create("k", factory) == 42
        assert cache.get_or_create("k", factory) == 42
        assert len(calls) == 1

    def test_get_or_compute_caches_result(self):
        cache: BoundedCache[str, int] = BoundedCache(max_size=4)
        calls: list[int] = []

        def factory() -> int:
            calls.append(1)
            return 7

        assert cache.get_or_compute("k", factory) == 7
        assert cache.get_or_compute("k", factory) == 7
        assert len(calls) == 1

    def test_set_then_get(self):
        cache: BoundedCache[str, int] = BoundedCache(max_size=4)
        cache.set("k", 5)
        assert cache.get("k") == 5

    def test_ttl_expiry(self, monkeypatch):
        """TTL 过期。

        用**受控时钟**而不是真实 sleep：Windows 的 `time.monotonic()` 粒度约 15.6ms，
        靠 `sleep(0.06)` 去跨过 `ttl=0.05` 只有 10ms 余量，负载下会偶发失败（实测出现过）。
        """
        now = {"t": 1000.0}
        monkeypatch.setattr("core.cache.time.monotonic", lambda: now["t"])

        cache: BoundedCache[str, int] = BoundedCache(max_size=4, ttl=0.05)
        cache.set("k", 1)
        assert cache.get("k") == 1

        now["t"] += 0.1  # 推进受控时钟，跨过 TTL
        assert cache.get("k") is None

    def test_lru_touch_extends_lifetime(self, monkeypatch):
        """命中会刷新访问时间（LRU 触达）—— 所以刚访问过的项不会因 TTL 立即过期。"""
        now = {"t": 1000.0}
        monkeypatch.setattr("core.cache.time.monotonic", lambda: now["t"])

        cache: BoundedCache[str, int] = BoundedCache(max_size=4, ttl=0.05)
        cache.set("k", 1)

        now["t"] += 0.04
        assert cache.get("k") == 1  # 触达，刷新时间戳

        now["t"] += 0.04  # 距上一次访问仅 0.04 < ttl
        assert cache.get("k") == 1

        now["t"] += 0.1  # 真正超过 TTL
        assert cache.get("k") is None

    def test_size_stays_bounded(self):
        cache: BoundedCache[int, int] = BoundedCache(max_size=10)
        for i in range(200):
            cache.set(i, i)
        assert len(cache) <= 10

    def test_stats_and_clear(self):
        cache: BoundedCache[str, int] = BoundedCache(max_size=4)
        cache.set("k", 1)
        cache.get("k")
        cache.get("missing")
        assert cache.stats["hits"] == 1
        assert cache.stats["misses"] == 1
        cache.clear()
        assert len(cache) == 0
        assert cache.stats["hits"] == 0

    def test_on_evict_called_by_clear(self):
        victims: list[int] = []
        cache: BoundedCache[str, int] = BoundedCache(max_size=4, on_evict=victims.append)
        cache.set("k", 1)
        cache.clear()
        assert victims == [1]

    def test_on_evict_skipped_when_notify_false(self):
        victims: list[int] = []
        cache: BoundedCache[str, int] = BoundedCache(max_size=4, on_evict=victims.append)
        cache.set("k", 1)
        cache.clear(notify=False)
        assert victims == []

    def test_on_evict_error_does_not_propagate(self):
        def boom(_value: int) -> None:
            raise RuntimeError("boom")

        cache: BoundedCache[str, int] = BoundedCache(max_size=4, on_evict=boom)
        cache.set("k", 1)
        cache.clear()  # 不应抛出

    @pytest.mark.parametrize("bad", [0, -1])
    def test_rejects_non_positive_max_size(self, bad: int):
        with pytest.raises(ValueError):
            BoundedCache(max_size=bad)

    @pytest.mark.parametrize("bad", [0, -0.5, 1.5])
    def test_rejects_invalid_evict_ratio(self, bad: float):
        with pytest.raises(ValueError):
            BoundedCache(max_size=10, evict_ratio=bad)


class TestConcurrency:
    def test_get_or_create_builds_exactly_once(self):
        """单飞：8 个线程同时请求同一 key，只应构造一次且拿到同一实例。"""
        cache: BoundedCache[str, object] = BoundedCache(max_size=8)
        barrier = threading.Barrier(8)
        build_lock = threading.Lock()
        built: list[object] = []
        results: list[object] = []
        result_lock = threading.Lock()

        def factory() -> object:
            with build_lock:
                built.append(object())
                return built[-1]

        def worker() -> None:
            barrier.wait(timeout=5)
            value = cache.get_or_create("same-key", factory)
            with result_lock:
                results.append(value)

        threads = [threading.Thread(target=worker) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert len(built) == 1
        assert len(results) == 8
        assert len({id(r) for r in results}) == 1

    def test_get_or_compute_survives_eviction_contention(self):
        """高并发写入 + 频繁淘汰不应抛异常（旧实现在这里会 KeyError）。"""
        cache: BoundedCache[int, int] = BoundedCache(max_size=8, evict_ratio=0.5)
        errors: list[BaseException] = []

        def worker(seed: int) -> None:
            try:
                for i in range(600):
                    key = (seed * 601 + i) % 64
                    cache.get_or_compute(key, lambda: i)
                    cache.get(key)
            except BaseException as exc:  # pragma: no cover - 失败时用于报告
                errors.append(exc)

        threads = [threading.Thread(target=worker, args=(s,)) for s in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        assert errors == []
        assert len(cache) <= 8

    def test_set_under_contention_stays_bounded(self):
        cache: BoundedCache[int, int] = BoundedCache(max_size=4, evict_ratio=0.5)
        errors: list[BaseException] = []

        def worker() -> None:
            try:
                for i in range(800):
                    cache.set(i % 32, i)
                    cache.get(i % 32)
            except BaseException as exc:  # pragma: no cover
                errors.append(exc)

        threads = [threading.Thread(target=worker) for _ in range(6)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        assert errors == []
        assert len(cache) <= 4

    def test_slow_factory_does_not_block_other_keys(self):
        """慢 factory 不得阻塞其他 key —— 这是 get_or_compute 与 get_or_create 的核心差别。"""
        cache: BoundedCache[str, str] = BoundedCache(max_size=8)
        started = threading.Event()
        release = threading.Event()

        def slow() -> str:
            started.set()
            release.wait(timeout=5)
            return "slow"

        thread = threading.Thread(target=lambda: cache.get_or_compute("slow", slow))
        thread.start()
        assert started.wait(timeout=5)

        begin = time.monotonic()
        assert cache.get_or_compute("fast", lambda: "fast") == "fast"
        assert time.monotonic() - begin < 0.5

        release.set()
        thread.join(timeout=5)
        assert cache.get("slow") == "slow"
