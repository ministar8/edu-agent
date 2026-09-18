"""`/api/metrics` 与 `service.metrics` 的测试（backlog #20）。

**为什么给这个端点写测试**：它的价值全在「**数据是对的、且取不到时不会装死**」。
- 字段名写错 → 运维看到的永远是 0，不会报错；
- 某个缓存读取抛异常 → 若整体 500，另一个缓存的健康状况就完全看不到了。

两条都不容易在人工点一次端点时发现，所以钉住。
"""

from __future__ import annotations

import pytest

from service import metrics as M


class TestCollectCacheStats:
    def test_returns_both_caches(self):
        """两个缓存都要出现 —— 少一个就是"看得见的那个掩盖了看不见的那个"。"""
        result = M.collect_cache_stats()
        assert set(result) == {"query", "semantic"}

    def test_query_cache_fields(self):
        query = M.collect_cache_stats()["query"]
        assert {"hits", "misses", "hit_rate"} <= set(query)
        assert query["hits"] >= 0
        assert query["misses"] >= 0

    def test_semantic_cache_fields(self):
        sem = M.collect_cache_stats()["semantic"]
        assert {"hits", "misses", "hit_rate", "entries", "max_entries"} <= set(sem)

    def test_key_names_are_aligned_across_caches(self):
        """两个缓存的公共键名必须一致，否则并排展示时要做映射、容易写错。"""
        result = M.collect_cache_stats()
        common = {"hits", "misses", "hit_rate"}
        assert common <= set(result["query"])
        assert common <= set(result["semantic"])


class TestFailureIsolation:
    """**核心**：一个缓存坏了，不能连累另一个的可见性。"""

    def test_one_failure_does_not_break_the_other(self, monkeypatch):
        def boom() -> dict:
            raise RuntimeError("缓存炸了")

        monkeypatch.setattr(
            M, "_CACHE_PROBES", (("query", boom), ("semantic", M._semantic_cache_stats))
        )
        result = M.collect_cache_stats()
        assert "error" in result["query"], "坏掉的那个要如实标记"
        assert "error" not in result["semantic"], "另一个必须照常返回"

    def test_failure_records_exception_type(self, monkeypatch):
        def boom() -> dict:
            raise ValueError("x")

        monkeypatch.setattr(M, "_CACHE_PROBES", (("query", boom),))
        assert M.collect_cache_stats()["query"] == {"error": "ValueError"}

    def test_failure_is_logged(self, monkeypatch, caplog):
        """静默吞异常是本项目刚清理过的问题（backlog #11），这里不能再犯。"""

        def boom() -> dict:
            raise RuntimeError("x")

        monkeypatch.setattr(M, "_CACHE_PROBES", (("query", boom),))
        with caplog.at_level("WARNING"):
            M.collect_cache_stats()
        assert any("缓存统计失败" in r.message for r in caplog.records)

    def test_all_failures_still_return_shape(self, monkeypatch):
        def boom() -> dict:
            raise RuntimeError("x")

        monkeypatch.setattr(M, "_CACHE_PROBES", (("query", boom), ("semantic", boom)))
        result = M.collect_cache_stats()
        assert set(result) == {"query", "semantic"}


class TestCollectMetrics:
    def test_shape(self):
        assert set(M.collect_metrics()) == {"cache"}

    def test_cache_section_matches_collect_cache_stats(self):
        assert M.collect_metrics()["cache"] == M.collect_cache_stats()


class TestMetricsEndpoint:
    def test_returns_200(self, test_client):
        resp = test_client.get("/api/metrics")
        assert resp.status_code == 200

    def test_body_has_cache_hit_rates(self, test_client):
        body = test_client.get("/api/metrics").json()
        assert "cache" in body
        assert "hit_rate" in body["cache"]["query"]
        assert "hit_rate" in body["cache"]["semantic"]

    def test_is_under_api_prefix(self, test_client):
        """挂在 `/api` 下，与其它业务路由一致；根路径留给静态前端。"""
        assert test_client.get("/metrics").status_code == 404

    def test_does_not_require_auth(self, test_client):
        """观测端点不应要求登录 —— 否则健康采集方拿不到数据。"""
        assert test_client.get("/api/metrics").status_code == 200


class TestHealthIsNotPolluted:
    """`/health` 与 `/metrics` 的职责必须分开。"""

    def test_health_does_not_contain_cache_stats(self, test_client):
        """`/health` 被 Docker healthcheck 使用，混入运行统计会让语义变模糊。"""
        body = test_client.get("/health").json()
        assert "cache" not in body

    def test_health_still_has_status(self, test_client):
        assert "status" in test_client.get("/health").json()


class TestRetrieverCacheStats:
    """`retriever.cache_stats()` 是公开访问器，`_cache_stats_fields()` 供日志复用。"""

    def test_public_accessor_keys(self):
        from rag.retriever import cache_stats

        assert set(cache_stats()) == {"hits", "misses", "hit_rate"}

    def test_log_fields_are_prefixed_versions(self):
        """日志键名带 `cache_` 前缀 —— 历史指标日志用的是这套名字，不能改。"""
        from rag.retriever import _cache_stats_fields, cache_stats

        assert _cache_stats_fields() == {f"cache_{k}": v for k, v in cache_stats().items()}

    def test_both_share_one_source_of_truth(self):
        """两者必须同源 —— 否则日志与端点会各报一个数。"""
        from rag.retriever import _cache_stats_fields, cache_stats

        public = cache_stats()
        logged = _cache_stats_fields()
        assert logged["cache_hits"] == public["hits"]
        assert logged["cache_misses"] == public["misses"]
        assert logged["cache_hit_rate"] == public["hit_rate"]


@pytest.mark.parametrize("key", ["hits", "misses", "hit_rate"])
def test_query_cache_keys_present(key):
    assert key in M.collect_cache_stats()["query"]
