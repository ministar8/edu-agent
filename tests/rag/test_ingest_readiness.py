"""入库就绪屏障与预热告警的测试。

背景：Chroma 的 PersistentClient 在 ``add_documents`` 返回后，某个集合的 HNSW 段文件
可能**从未落盘**，此时查询会抛 ``Error creating hnsw segment reader: Nothing found on disk``。
间歇性 —— 每次命中的集合不同，命中后该集合整轮不可查询（检索结果全错但不报错）。

它有两个后果，本文件各覆盖一个：

1. ``VectorStoreManager.wait_until_ready``：把"静默返回错误检索结果"变成"入库期显式失败"。
   **注意它是检测器而非修复器** —— 实测「丢弃缓存句柄」「重开 client」都无效，
   只有「删除集合并重建」能修。所以测试重点有两处：
   - 失败路径必须抛错，且**错误信息里带可执行的补救命令**；
   - 重试期间必须丢弃缓存句柄（对"真的只是慢"的情况有效），
     这一点从"最终成功了"看不出来，必须断言副作用。
2. ``rag.ingest.evaluate_warmup``：预热失败必须被判为不可接受并给出原因，而不是只打印一行
   INFO 让它滑过去。
"""

from __future__ import annotations

import pytest

from rag import vectorstore as vs
from rag.ingest import evaluate_warmup

# ══════════════════════════════════════════════════════
# 1. wait_until_ready
# ══════════════════════════════════════════════════════


class _FakeSearch:
    """记录调用并把前 N 次变成失败，之后成功。"""

    def __init__(self, fail_times: int) -> None:
        self.fail_times = fail_times
        self.calls: list[tuple[str, str, int]] = []

    def __call__(self, collection_name, query, k, filter=None):
        self.calls.append((collection_name, query, k))
        if len(self.calls) <= self.fail_times:
            raise RuntimeError(
                "Error executing plan: Internal error: "
                "Error creating hnsw segment reader: Nothing found on disk"
            )
        return []


def _manager(fail_times: int) -> tuple[vs.VectorStoreManager, _FakeSearch]:
    """构造一个不碰真实 Chroma 的 manager（跳过 __init__，手工装字段）。"""
    manager = object.__new__(vs.VectorStoreManager)
    manager._stores = {"os": object()}  # 预置一个"坏句柄"，用于验证是否被丢弃
    fake = _FakeSearch(fail_times)
    manager.similarity_search_with_score = fake  # type: ignore[method-assign]
    return manager, fake


class TestWaitUntilReady:
    def test_first_attempt_success_returns_zero(self):
        manager, fake = _manager(fail_times=0)
        assert manager.wait_until_ready("os", retries=5, delay=0) == 0
        assert len(fake.calls) == 1

    def test_probe_uses_readiness_query_and_k_one(self):
        manager, fake = _manager(fail_times=0)
        manager.wait_until_ready("os", retries=5, delay=0)
        assert fake.calls[0] == ("os", vs._READINESS_PROBE_QUERY, 1)

    def test_retries_then_succeeds_returns_failure_count(self):
        manager, fake = _manager(fail_times=2)
        assert manager.wait_until_ready("os", retries=5, delay=0) == 2
        assert len(fake.calls) == 3

    def test_cached_store_handle_is_discarded_between_attempts(self):
        """核心断言：只重试不丢句柄是无效的，所以必须验证句柄真的被丢弃。

        这一点无法从"最终成功了"这个结果反推出来 —— 必须断言副作用。
        """
        manager, _fake = _manager(fail_times=1)
        assert "os" in manager._stores
        manager.wait_until_ready("os", retries=5, delay=0)
        # 失败过一次 → 句柄被丢弃（get_store 之后会重新构造）
        assert "os" not in manager._stores

    def test_success_without_failure_keeps_handle(self):
        manager, _fake = _manager(fail_times=0)
        manager.wait_until_ready("os", retries=5, delay=0)
        assert "os" in manager._stores

    def test_exhausted_retries_raises_with_last_error(self):
        manager, fake = _manager(fail_times=99)
        with pytest.raises(RuntimeError) as excinfo:
            manager.wait_until_ready("os", retries=3, delay=0)
        message = str(excinfo.value)
        assert "os" in message
        assert "3 次重试" in message
        assert "Nothing found on disk" in message  # 保留底层原因，便于定位
        assert len(fake.calls) == 3

    def test_error_message_contains_actionable_remedy(self):
        """错误信息必须能直接照做 —— 这是"检测器"唯一的价值所在。

        实测重试与重开 client 都无效，只有重建集合能修，
        所以补救命令必须出现在信息里，否则值班的人只会反复重跑入库。
        """
        manager, _fake = _manager(fail_times=99)
        with pytest.raises(RuntimeError) as excinfo:
            manager.wait_until_ready("os", retries=2, delay=0)
        message = str(excinfo.value)
        assert "rebuild=True" in message
        assert "无法恢复" in message

    def test_exhausted_retries_still_discards_handle(self):
        manager, _fake = _manager(fail_times=99)
        with pytest.raises(RuntimeError):
            manager.wait_until_ready("os", retries=2, delay=0)
        assert "os" not in manager._stores

    def test_single_retry_budget_does_not_sleep(self):
        manager, fake = _manager(fail_times=99)
        with pytest.raises(RuntimeError):
            manager.wait_until_ready("os", retries=1, delay=10.0)
        assert len(fake.calls) == 1

    def test_non_chroma_exception_is_also_retried(self):
        manager, _fake = _manager(fail_times=0)

        def boom(collection_name, query, k, filter=None):
            raise ValueError("unexpected")

        manager.similarity_search_with_score = boom  # type: ignore[method-assign]
        with pytest.raises(RuntimeError) as excinfo:
            manager.wait_until_ready("os", retries=2, delay=0)
        assert "ValueError" in str(excinfo.value)


class TestGateDelegatesToManager:
    """门禁的批量封装必须复用生产实现，否则两份逻辑会漂移。"""

    def test_wait_for_index_ready_uses_manager_method(self, monkeypatch):
        from evaluation import retrieval_gate as gate
        from rag import vectorstore

        seen: list[tuple[str, int, float]] = []

        class _SpyManager:
            def wait_until_ready(self, name, *, retries, delay):
                seen.append((name, retries, delay))
                return 1 if name == "b" else 0

        monkeypatch.setattr(vectorstore, "get_vector_store_manager", lambda: _SpyManager())
        result = gate.wait_for_index_ready(["a", "b"], retries=4, delay=0.25)

        assert result == {"a": 0, "b": 1}
        assert seen == [("a", 4, 0.25), ("b", 4, 0.25)]

    def test_repairs_unqueryable_collection_then_retries(self, monkeypatch):
        """门禁的索引是一次性的，所以可以自动重建 —— 生产路径不能这么做。

        这条测试同时钉住"只重建出问题的那个集合"：顺手重建全部会让每次故障
        都把整库重跑一遍，白白放大故障影响面。
        """
        from evaluation import retrieval_gate as gate
        from rag import vectorstore

        events: list[tuple] = []
        attempts: dict[str, int] = {}

        class _SpyManager:
            def wait_until_ready(self, name, *, retries, delay):
                attempts[name] = attempts.get(name, 0) + 1
                events.append(("wait", name, attempts[name]))
                if name == "bad" and attempts[name] == 1:
                    raise RuntimeError("Nothing found on disk")
                return 0

            def delete_collection(self, name):
                events.append(("delete", name))

        def _fake_build(categories=None):
            events.append(("build", tuple(categories or [])))
            return {}

        monkeypatch.setattr(vectorstore, "get_vector_store_manager", lambda: _SpyManager())
        monkeypatch.setattr(gate, "build_index", _fake_build)

        result = gate.wait_for_index_ready(["good", "bad"], retries=1, delay=0)

        assert result == {"good": 0, "bad": 0}
        assert ("delete", "bad") in events
        assert ("build", ("bad",)) in events
        assert ("delete", "good") not in events

    def test_repair_disabled_propagates_error(self, monkeypatch):
        """生产路径语义：不可查询就必须显式失败，绝不自动删集合。"""
        from evaluation import retrieval_gate as gate
        from rag import vectorstore

        deleted: list[str] = []

        class _SpyManager:
            def wait_until_ready(self, name, *, retries, delay):
                raise RuntimeError("Nothing found on disk")

            def delete_collection(self, name):
                deleted.append(name)

        monkeypatch.setattr(vectorstore, "get_vector_store_manager", lambda: _SpyManager())

        with pytest.raises(RuntimeError):
            gate.wait_for_index_ready(["bad"], retries=1, delay=0, repair=False)
        assert deleted == []


# ══════════════════════════════════════════════════════
# 2. evaluate_warmup
# ══════════════════════════════════════════════════════


class TestEvaluateWarmup:
    def test_full_success_is_acceptable(self):
        ok, message = evaluate_warmup({"total": 10, "succeeded": 10, "failed": 0}, 0.8)
        assert ok is True
        assert "100.0%" in message

    def test_rate_above_threshold_is_acceptable(self):
        ok, _ = evaluate_warmup({"total": 10, "succeeded": 9, "failed": 1}, 0.8)
        assert ok is True

    def test_rate_exactly_at_threshold_is_acceptable(self):
        # 边界取 >=：恰好达标不应报警
        ok, _ = evaluate_warmup({"total": 10, "succeeded": 8, "failed": 2}, 0.8)
        assert ok is True

    def test_rate_below_threshold_is_rejected_with_reason(self):
        ok, message = evaluate_warmup({"total": 10, "succeeded": 7, "failed": 3}, 0.8)
        assert ok is False
        assert "70.0%" in message
        assert "80%" in message
        assert "7/10" in message

    def test_total_failure_is_rejected(self):
        """预热全落空是最典型的失败形态（索引未就绪），必须被判为不可接受。"""
        ok, message = evaluate_warmup({"total": 20, "succeeded": 0, "failed": 20}, 0.8)
        assert ok is False
        assert "0.0%" in message

    def test_empty_warmup_set_is_rejected(self):
        ok, message = evaluate_warmup({"total": 0, "succeeded": 0, "failed": 0}, 0.8)
        assert ok is False
        assert "为空" in message

    def test_missing_keys_treated_as_zero(self):
        ok, message = evaluate_warmup({}, 0.8)
        assert ok is False
        assert "为空" in message

    def test_none_values_treated_as_zero(self):
        ok, _ = evaluate_warmup({"total": None, "succeeded": None}, 0.8)
        assert ok is False

    def test_string_counts_are_coerced(self):
        # warmup_query_cache 返回的是 int，但从指标/JSON 回读时可能是字符串
        ok, _ = evaluate_warmup({"total": "10", "succeeded": "9"}, 0.8)
        assert ok is True

    def test_threshold_zero_accepts_any_non_empty_run(self):
        ok, _ = evaluate_warmup({"total": 10, "succeeded": 1}, 0.0)
        assert ok is True


class TestSettingsWiring:
    """参数必须真的来自 settings —— 否则"可配置"是假的。

    这里刻意用**行为验证**而不是扫描源码文本。原因：文本扫描只要目标字符串在文件别处
    出现就会假绿。反向验证当场戳穿过这一点 —— 把 ``evaluate_warmup`` 的实参换成常量
    ``0.0`` 后，文本断言仍然通过（因为 ``settings.WARMUP_MIN_SUCCESS_RATE``
    在指标载荷里又出现了一次）。
    """

    def test_ingest_ready_settings_exist_and_are_sane(self):
        from core.settings import settings

        assert settings.INGEST_READY_RETRIES >= 1
        assert settings.INGEST_READY_DELAY >= 0
        assert 0.0 <= settings.WARMUP_MIN_SUCCESS_RATE <= 1.0

    def _stub_pipeline(self, monkeypatch, tmp_path, manager):
        """把 ingest 的文件处理链路整体替换掉，只保留被验证的接线。"""
        from langchain_core.documents import Document

        from core.settings import settings
        from rag import ingest

        (tmp_path / "cat").mkdir()
        (tmp_path / "cat" / "a.md").write_text("内容", encoding="utf-8")
        monkeypatch.setattr(settings, "KNOWLEDGE_DIR", str(tmp_path))
        monkeypatch.setattr(ingest, "get_vector_store_manager", lambda: manager)
        monkeypatch.setattr(
            ingest,
            "load_single_file",
            lambda _p: [Document(page_content="内容" * 60, metadata={"source_file": "a.md"})],
        )
        monkeypatch.setattr(ingest, "clean_documents", lambda docs, **kw: docs)
        monkeypatch.setattr(ingest, "split_documents", lambda docs: list(docs))
        monkeypatch.setattr(ingest, "enhance_documents", lambda chunks: chunks)
        monkeypatch.setattr(
            ingest,
            "tag_chunks_with_knowledge_points",
            lambda chunks, fallback_category: chunks,
        )
        return ingest

    def test_ingest_category_passes_settings_ready_params(self, monkeypatch, tmp_path):
        from core.settings import settings

        monkeypatch.setattr(settings, "INGEST_READY_RETRIES", 3)
        monkeypatch.setattr(settings, "INGEST_READY_DELAY", 0.75)

        class _Mgr:
            def __init__(self):
                self.ready_calls = []

            def add_documents(self, chunks, collection_name):
                return ["id"] * len(chunks)

            def wait_until_ready(self, name, *, retries, delay):
                self.ready_calls.append((name, retries, delay))
                return 0

        manager = _Mgr()
        ingest = self._stub_pipeline(monkeypatch, tmp_path, manager)
        result = ingest.ingest_category("cat")

        assert manager.ready_calls == [("cat", 3, 0.75)]
        assert result["chunks"] == 1
        assert result["not_ready"] is False
        assert result["ready_retries"] == 0

    def test_ingest_category_records_retry_count(self, monkeypatch, tmp_path):
        class _Mgr:
            def add_documents(self, chunks, collection_name):
                return ["id"] * len(chunks)

            def wait_until_ready(self, name, *, retries, delay):
                return 2

        ingest = self._stub_pipeline(monkeypatch, tmp_path, _Mgr())
        result = ingest.ingest_category("cat")
        assert result["ready_retries"] == 2
        assert result["not_ready"] is False

    def test_ingest_category_marks_not_ready_when_barrier_fails(self, monkeypatch, tmp_path):
        class _Mgr:
            def add_documents(self, chunks, collection_name):
                return ["id"] * len(chunks)

            def wait_until_ready(self, name, *, retries, delay):
                raise RuntimeError("索引不可查询")

        ingest = self._stub_pipeline(monkeypatch, tmp_path, _Mgr())
        result = ingest.ingest_category("cat")
        # 不能抛出去中断整轮入库，但必须把失败状态记录下来
        assert result["not_ready"] is True

    def test_ingest_category_skips_barrier_when_nothing_was_split(self, monkeypatch, tmp_path):
        """没有产出任何 chunk 时不该做就绪探测（空集合探测无意义）。

        注意 ``total_chunks`` 统计的是切分产物数而非入库 id 数 ——
        即使 ``add_documents`` 因去重返回 0 个 id，只要切分有产物就会做探测。
        """

        class _Mgr:
            def __init__(self):
                self.ready_calls = []

            def add_documents(self, chunks, collection_name):
                return ["id"] * len(chunks)

            def wait_until_ready(self, name, *, retries, delay):
                self.ready_calls.append(name)
                return 0

        manager = _Mgr()
        ingest = self._stub_pipeline(monkeypatch, tmp_path, manager)
        monkeypatch.setattr(ingest, "split_documents", lambda docs: [])
        result = ingest.ingest_category("cat")

        assert manager.ready_calls == []
        assert result["chunks"] == 0

    def test_ingest_all_passes_settings_threshold_to_evaluate_warmup(self, monkeypatch):
        from core.settings import settings
        from rag import ingest

        received: list[float] = []
        real_evaluate = ingest.evaluate_warmup

        class _Mgr:
            def list_collections(self):
                return []

        monkeypatch.setattr(settings, "WARMUP_MIN_SUCCESS_RATE", 0.55)
        monkeypatch.setattr(
            ingest,
            "ingest_category",
            lambda *a, **k: {"category": "cat", "files": 0, "chunks": 0, "errors": 0},
        )
        monkeypatch.setattr(ingest, "get_vector_store_manager", lambda: _Mgr())
        monkeypatch.setattr(
            "rag.retriever.warmup_query_cache",
            lambda quiet=True: {"total": 10, "succeeded": 10, "failed": 0, "elapsed_ms": 1.0},
        )

        def _spy(result, rate):
            received.append(rate)
            return real_evaluate(result, rate)

        monkeypatch.setattr(ingest, "evaluate_warmup", _spy)
        ingest.ingest_all(categories=["cat"])

        assert received == [0.55]

    def test_ingest_all_reports_not_ready_categories(self, monkeypatch):
        from rag import ingest

        emitted: list[dict] = []

        class _Mgr:
            def list_collections(self):
                return []

        monkeypatch.setattr(
            ingest,
            "ingest_category",
            lambda *a, **k: {
                "category": "cat",
                "files": 0,
                "chunks": 0,
                "errors": 0,
                "not_ready": True,
            },
        )
        monkeypatch.setattr(ingest, "get_vector_store_manager", lambda: _Mgr())
        monkeypatch.setattr(
            "rag.retriever.warmup_query_cache",
            lambda quiet=True: {"total": 10, "succeeded": 10, "failed": 0, "elapsed_ms": 1.0},
        )
        monkeypatch.setattr(ingest.metrics, "emit", lambda **kw: emitted.append(kw))

        ingest.ingest_all(categories=["cat"])

        assert emitted, "预热结果必须进指标"
        assert emitted[-1]["values"]["not_ready_categories"] == ["cat"]
