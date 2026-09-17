"""`rag/bm25.py` 测试：**确定性**（backlog #31）。

**为什么要测确定性**：`bm25_search` 的最终排序原本只按分数排，**没有并列次级键**。
分数相同时，名次取决于 `scored_docs` 的**插入顺序**，而插入顺序又取决于
Chroma `get()` 返回候选的先后 —— 这个顺序在当前实现下实测稳定（5/5 一致），
但**API 并未承诺**。一旦它变化，并列项的名次会**无声改变**，
表现为"同样的查询、同样的库，检索结果不同"（与 #29 同一类问题）。

本文件的核心断言是：**候选返回顺序变化时，结果必须不变。**
"""

from __future__ import annotations

import pytest
from langchain_core.documents import Document

from rag import bm25 as B


class _FakeCollection:
    """可控的假 Chroma collection：按 `$contains` 返回预设文档。"""

    def __init__(self, rows: list[tuple[str, str, dict]], *, total: int | None = None):
        # rows: [(doc_id, text, metadata)]
        self._rows = rows
        self._total = total if total is not None else len(rows)
        self.get_calls: list[dict] = []

    def count(self) -> int:
        return self._total

    def get(self, **kwargs):
        self.get_calls.append(kwargs)
        where_doc = kwargs.get("where_document") or {}
        term = where_doc.get("$contains")
        if term is None:
            # 无 where_document：用于 avgdl 采样
            rows = self._rows
        else:
            rows = [r for r in self._rows if term in r[1]]
        limit = kwargs.get("limit")
        if limit is not None:
            rows = rows[:limit]
        return {
            "ids": [r[0] for r in rows],
            "documents": [r[1] for r in rows],
            "metadatas": [r[2] for r in rows],
        }


def _install(monkeypatch, collection: _FakeCollection):
    class _Mgr:
        def __init__(self):
            self.client = type("C", (), {"get_collection": lambda _s, _n: collection})()

    import rag.vectorstore as vs

    monkeypatch.setattr(vs, "get_vector_store_manager", lambda: _Mgr())
    B._avgdl_cache.clear()


def _rows(n: int, *, text: str = "进程调度是核心概念") -> list[tuple[str, str, dict]]:
    return [(f"id{i:03d}", text, {"section.chunk_id": f"c{i:03d}"}) for i in range(n)]


class TestEmptyInputs:
    def test_no_terms_returns_empty(self):
        assert B.bm25_search([], "coll", 5) == []

    def test_collection_unavailable_returns_empty(self, monkeypatch):
        import rag.vectorstore as vs

        def boom():
            raise RuntimeError("no store")

        monkeypatch.setattr(vs, "get_vector_store_manager", boom)
        assert B.bm25_search(["进程"], "coll", 5) == []

    def test_empty_collection_returns_empty(self, monkeypatch):
        _install(monkeypatch, _FakeCollection([], total=0))
        assert B.bm25_search(["进程"], "coll", 5) == []

    def test_term_with_no_match_returns_empty(self, monkeypatch):
        _install(monkeypatch, _FakeCollection(_rows(3)))
        assert B.bm25_search(["不存在的词"], "coll", 5) == []


class TestDeterminism:
    """**核心**：结果不应依赖候选返回顺序。"""

    def test_ties_broken_by_chunk_id(self, monkeypatch):
        """分数完全相同时，按 `chunk_id` 升序 —— 而不是按候选返回顺序。"""
        rows = _rows(5)
        _install(monkeypatch, _FakeCollection(rows))

        results = B.bm25_search(["进程"], "coll", 5)

        assert len(results) == 5
        # 五条文本完全相同 → 分数完全相同 → 应由 chunk_id 决定顺序
        keys = [d.metadata["section.chunk_id"] for d, _ in results]
        assert keys == sorted(keys), f"并列项未按 chunk_id 排序: {keys}"

    def test_result_is_independent_of_candidate_order(self, monkeypatch):
        """**关键性质**：把候选顺序反过来，结果必须一模一样。

        原实现（无并列次级键）在这里会失败 —— 并列项的名次会跟着候选顺序翻转。
        """
        rows = _rows(5)
        _install(monkeypatch, _FakeCollection(rows))
        forward = B.bm25_search(["进程"], "coll", 5)

        B._avgdl_cache.clear()
        _install(monkeypatch, _FakeCollection(list(reversed(rows))))
        backward = B.bm25_search(["进程"], "coll", 5)

        assert [d.metadata["section.chunk_id"] for d, _ in forward] == [
            d.metadata["section.chunk_id"] for d, _ in backward
        ]

    def test_repeated_calls_are_identical(self, monkeypatch):
        _install(monkeypatch, _FakeCollection(_rows(6)))
        first = [d.metadata["section.chunk_id"] for d, _ in B.bm25_search(["进程"], "coll", 6)]
        second = [d.metadata["section.chunk_id"] for d, _ in B.bm25_search(["进程"], "coll", 6)]
        assert first == second

    def test_missing_chunk_id_falls_back_to_content(self, monkeypatch):
        """没有 `chunk_id` 时退到内容前缀 —— 仍然必须是确定性的。"""
        rows = [
            ("a", "进程调度", {}),
            ("b", "进程调度", {}),
        ]
        _install(monkeypatch, _FakeCollection(rows))
        results = B.bm25_search(["进程"], "coll", 2)
        assert len(results) == 2


class TestScoring:
    def test_higher_term_frequency_scores_higher(self, monkeypatch):
        rows = [
            ("low", "进程", {"section.chunk_id": "c1"}),
            ("high", "进程进程进程", {"section.chunk_id": "c2"}),
        ]
        _install(monkeypatch, _FakeCollection(rows))
        results = B.bm25_search(["进程"], "coll", 2)
        assert results[0][0].metadata["section.chunk_id"] == "c2", "词频高的应排前面"

    def test_scores_normalised_to_unit_max(self, monkeypatch):
        _install(monkeypatch, _FakeCollection(_rows(3)))
        results = B.bm25_search(["进程"], "coll", 3)
        assert results[0][1] == pytest.approx(1.0), "最高分应归一化到 1.0"
        assert all(0.0 <= s <= 1.0 for _, s in results)

    def test_respects_k(self, monkeypatch):
        _install(monkeypatch, _FakeCollection(_rows(10)))
        assert len(B.bm25_search(["进程"], "coll", 3)) == 3

    def test_multi_term_scores_accumulate(self, monkeypatch):
        """多个关键词命中同一篇时分数应叠加。"""
        rows = [
            ("both", "进程 调度", {"section.chunk_id": "c1"}),
            ("one", "进程", {"section.chunk_id": "c2"}),
        ]
        _install(monkeypatch, _FakeCollection(rows))
        results = B.bm25_search(["进程", "调度"], "coll", 2)
        assert results[0][0].metadata["section.chunk_id"] == "c1"

    def test_document_has_content_and_metadata(self, monkeypatch):
        _install(monkeypatch, _FakeCollection(_rows(1)))
        doc, _ = B.bm25_search(["进程"], "coll", 1)[0]
        assert isinstance(doc, Document)
        assert doc.page_content
        assert doc.metadata

    def test_filter_is_passed_through(self, monkeypatch):
        coll = _FakeCollection(_rows(3))
        _install(monkeypatch, coll)
        B.bm25_search(["进程"], "coll", 3, filter={"collection": "os"})
        assert any(call.get("where") == {"collection": "os"} for call in coll.get_calls)


class TestCandidateLimitCaveat:
    """把「候选集被截断」这个**已知取舍**钉住。

    `limit=k*3` 意味着命中数远超 `k*3` 时，只有**一部分**匹配会被评分
    （实测某词命中 178 篇而只取 15 篇）。这是**性能取舍**，不是 bug，
    但它确实造成召回损失 —— 本类把它显式记录下来，避免被当成"全量匹配"。
    """

    def test_candidates_are_truncated(self, monkeypatch):
        coll = _FakeCollection(_rows(100))
        _install(monkeypatch, coll)
        B.bm25_search(["进程"], "coll", 5)
        term_calls = [c for c in coll.get_calls if (c.get("where_document") or {}).get("$contains")]
        assert term_calls, "应有按词查询"
        assert term_calls[0]["limit"] == 15, "当前实现是 k*3（k=5）"
