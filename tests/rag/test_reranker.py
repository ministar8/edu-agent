"""`rag/reranker.py` 单元测试。

**为什么这个文件之前不存在**：该模块覆盖率长期停在 26%，未覆盖的正是**整条重排主路径**
（76~166 行）。原因是测试里 `RERANK_ENABLED=False`，所有调用都在第 73 行就早退返回了 ——
也就是说**从来没人在测试里真正执行过一次重排**。它又依赖本地 TEI（`localhost`），
CI 里起不来，于是长期无人触碰。

用 `RERANK_ENABLED=True` + 假的 `httpx.Client` 就能把这条路径完整跑起来。
这很重要，因为重排是**静默降级的高危区**：TEI 超时、返回空、索引越界时，
代码都是"悄悄回退到原始顺序"而不报错 —— 检索质量掉了但没人知道。
本文件把每一条回退路径都钉住。
"""

from __future__ import annotations

import httpx
import pytest
from langchain_core.documents import Document

from rag import reranker as R


@pytest.fixture(autouse=True)
def _clear_rerank_cache():
    """重排结果有进程内缓存，跨用例必须清，否则"缓存命中"会掩盖真实路径。"""
    R._rerank_cache.clear()
    yield
    R._rerank_cache.clear()


@pytest.fixture
def enabled(monkeypatch):
    monkeypatch.setattr(R.settings, "RERANK_ENABLED", True)
    monkeypatch.setattr(R.settings, "RERANK_LOCAL_URL", "http://localhost:9999")
    monkeypatch.setattr(R.settings, "RERANK_TIMEOUT", 5)


class _FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code
        self.text = str(payload)[:200]

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("boom", request=None, response=self)

    def json(self):
        return self._payload


def _install_client(monkeypatch, *, payload=None, exc=None, status_code=200):
    """装一个假的 httpx.Client，记录调用参数。"""
    calls = {}

    class _FakeClient:
        def __init__(self, timeout=None):
            calls["timeout"] = timeout

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def post(self, url, json=None):
            calls["url"] = url
            calls["json"] = json
            if exc is not None:
                raise exc
            return _FakeResponse(payload, status_code)

    monkeypatch.setattr(R.httpx, "Client", _FakeClient)
    return calls


def _docs(n, *, prefix="doc", metadata=None):
    return [
        Document(page_content=f"{prefix}{i}", metadata=dict(metadata or {"chunk_id": f"c{i}"}))
        for i in range(n)
    ]


# ── 缓存键 ──────────────────────────────────────────────


class TestDocumentCacheId:
    def test_prefers_content_hash(self):
        doc = Document(page_content="x", metadata={"content_hash": "H", "chunk_id": "C"})
        assert R._document_cache_id(doc) == "H"

    def test_falls_back_to_chunk_id(self):
        doc = Document(page_content="x", metadata={"chunk_id": "C"})
        assert R._document_cache_id(doc) == "C"

    def test_falls_back_to_source_and_prefix(self):
        doc = Document(page_content="正文", metadata={"source": "s.md", "chunk_index": 3})
        assert R._document_cache_id(doc) == "s.md:3:正文"

    def test_tolerates_empty_metadata(self):
        doc = Document(page_content="x", metadata={})
        assert R._document_cache_id(doc) == "::x"


class TestRerankCacheKey:
    def test_same_input_same_key(self):
        docs = _docs(3)
        assert R._rerank_cache_key("q", docs, 5) == R._rerank_cache_key("q", docs, 5)

    def test_query_and_top_k_participate(self):
        docs = _docs(3)
        base = R._rerank_cache_key("q", docs, 5)
        assert base != R._rerank_cache_key("q2", docs, 5)
        assert base != R._rerank_cache_key("q", docs, 6)

    def test_document_order_participates(self):
        """顺序不同 → 键不同。缓存不能把"换个顺序的同一批文档"当成同一结果。"""
        docs = _docs(3)
        assert R._rerank_cache_key("q", docs, 5) != R._rerank_cache_key(
            "q", list(reversed(docs)), 5
        )


# ── 早退路径 ────────────────────────────────────────────


class TestEarlyReturns:
    def test_empty_documents_returns_empty(self):
        assert R.rerank("q", []) == []

    def test_disabled_truncates_without_calling_tei(self, monkeypatch):
        monkeypatch.setattr(R.settings, "RERANK_ENABLED", False)
        docs = _docs(10)
        assert R.rerank("q", docs, top_k=3) == docs[:3]

    def test_disabled_does_not_touch_cache(self, monkeypatch):
        monkeypatch.setattr(R.settings, "RERANK_ENABLED", False)
        R.rerank("q", _docs(3), top_k=2)
        assert len(R._rerank_cache) == 0


# ── 预筛选 ──────────────────────────────────────────────


class TestPreFilter:
    @pytest.mark.parametrize(("lightweight", "cap"), [(True, 10), (False, 30)])
    def test_candidate_cap_follows_mode(self, monkeypatch, enabled, lightweight, cap):
        """lightweight(L2) 候选池 10，deep(L3) 30 —— 写反会静默改变精度/延迟。"""
        calls = _install_client(monkeypatch, payload=[])
        docs = _docs(cap + 5)

        R.rerank("q", docs, top_k=3, lightweight=lightweight)

        assert len(calls["json"]["texts"]) == cap

    def test_pre_filter_keeps_highest_scored(self, monkeypatch, enabled):
        """预筛选必须**按分数保留**，而不是按原顺序截断 —— 写反会丢掉最好的候选。

        断言方式：看哪些正文被送进了 TEI（`texts` 就是候选池）。
        """
        calls = _install_client(monkeypatch, payload=[])
        docs = _docs(12, prefix="pad")
        docs[11].metadata["recall_score"] = 0.99  # 最后一条分数最高

        R.rerank("q", docs, top_k=3, lightweight=True)

        assert "pad11" in calls["json"]["texts"], "最高分候选必须进入候选池"
        assert len(calls["json"]["texts"]) == 10

    def test_recall_score_beats_rerank_score(self, monkeypatch, enabled):
        """`recall_score` 优先于 `rerank_score`：两者都有时以前者排序。"""
        calls = _install_client(monkeypatch, payload=[])
        docs = _docs(12, prefix="pad")
        docs[11].metadata.update({"recall_score": 0.9, "rerank_score": 0.1})  # 只有 recall 高
        docs[10].metadata.update({"rerank_score": 0.95})  # 只有 rerank 高

        R.rerank("q", docs, top_k=3, lightweight=True)

        texts = calls["json"]["texts"]
        assert "pad11" in texts, "recall_score 高的应入选"
        assert "pad10" in texts, "仅有 rerank_score 的也应参与排序"

    def test_zero_scores_are_treated_as_missing(self, monkeypatch, enabled):
        """分数为 0 视为"没有分数"，不应把候选顶到前面。"""
        calls = _install_client(monkeypatch, payload=[])
        docs = _docs(12, prefix="pad")
        docs[0].metadata["recall_score"] = 0.0  # 显式 0 不该算高分
        docs[11].metadata["recall_score"] = 0.99

        R.rerank("q", docs, top_k=3, lightweight=True)

        assert calls["json"]["texts"][0] == "pad11", "0.99 应排在 0.0 之前"


# ── 缓存 ────────────────────────────────────────────────


class TestCache:
    def test_second_call_hits_cache(self, monkeypatch, enabled):
        calls = _install_client(monkeypatch, payload=[{"index": 0, "score": 0.9}])
        docs = _docs(3)

        first = R.rerank("q", docs, top_k=2)
        assert calls["json"] is not None

        # 第二次不应再发请求
        calls["json"] = None
        second = R.rerank("q", docs, top_k=2)
        assert calls["json"] is None, "第二次应命中缓存，不再调用 TEI"
        assert [d.page_content for d in first] == [d.page_content for d in second]

    def test_first_caller_does_not_poison_the_cache(self, monkeypatch, enabled):
        """**回归测试**：第一个调用方写 metadata，不得污染后续命中缓存的调用。

        原实现是 `_rerank_cache.set(key, result)` 后 `return result` ——
        **同一个对象既进缓存又返回**，于是调用方 1 的写入直接落进缓存，
        调用方 2 命中时会看到它。`_copy_ranked` 只在**读时**拷贝，防不住从写时进去的污染。

        `_rerank_cache` 是进程级、TTL 300s，所以这是**跨请求污染**：
        例如调用方 1 的窗口展开标记会出现在调用方 2 的结果里。
        """
        _install_client(monkeypatch, payload=[{"index": 0, "score": 0.9}])
        docs = _docs(2)

        first = R.rerank("q", docs, top_k=1)
        first[0].metadata["下游写入"] = "污染标记"

        second = R.rerank("q", docs, top_k=1)
        assert "下游写入" not in second[0].metadata, "调用方 1 的写入污染了缓存"

    def test_cache_hit_returns_independent_objects(self, monkeypatch, enabled):
        """缓存命中要返回新对象，避免调用方之间共享同一份 metadata。"""
        _install_client(monkeypatch, payload=[{"index": 0, "score": 0.9}])
        docs = _docs(2)

        first = R.rerank("q", docs, top_k=1)
        second = R.rerank("q", docs, top_k=1)

        assert second[0] is not first[0]
        second[0].metadata["调用方2写入"] = True
        third = R.rerank("q", docs, top_k=1)
        assert "调用方2写入" not in third[0].metadata

    def test_successful_result_is_cached(self, monkeypatch, enabled):
        _install_client(monkeypatch, payload=[{"index": 1, "score": 0.7}])
        R.rerank("q", _docs(3), top_k=1)
        assert len(R._rerank_cache) == 1


# ── 降级路径（静默回退的高危区）────────────────────────


class TestFallbacks:
    def test_http_status_error_falls_back(self, monkeypatch, enabled):
        _install_client(monkeypatch, payload={"err": "x"}, status_code=503)
        docs = _docs(5)

        out = R.rerank("q", docs, top_k=3)

        assert [d.page_content for d in out] == ["doc0", "doc1", "doc2"], "应回退到原始顺序"

    def test_generic_exception_falls_back(self, monkeypatch, enabled):
        _install_client(monkeypatch, exc=RuntimeError("connection refused"))
        docs = _docs(5)

        out = R.rerank("q", docs, top_k=2)

        assert [d.page_content for d in out] == ["doc0", "doc1"]

    def test_timeout_falls_back(self, monkeypatch, enabled):
        _install_client(monkeypatch, exc=httpx.ConnectTimeout("timeout"))
        out = R.rerank("q", _docs(4), top_k=1)
        assert [d.page_content for d in out] == ["doc0"]

    def test_empty_tei_results_fall_back(self, monkeypatch, enabled):
        _install_client(monkeypatch, payload=[])
        out = R.rerank("q", _docs(4), top_k=2)
        assert [d.page_content for d in out] == ["doc0", "doc1"]

    def test_fallback_result_is_not_cached(self, monkeypatch, enabled):
        """降级结果不该进缓存 —— 否则 TEI 恢复后仍会拿到旧的回退结果。"""
        _install_client(monkeypatch, payload=[])
        R.rerank("q", _docs(3), top_k=2)
        assert len(R._rerank_cache) == 0


# ── 正常路径 ────────────────────────────────────────────


class TestHappyPath:
    def test_scores_and_method_written_to_metadata(self, monkeypatch, enabled):
        _install_client(
            monkeypatch,
            payload=[{"index": 2, "score": 0.98765}, {"index": 0, "score": 0.5}],
        )
        docs = _docs(3)

        out = R.rerank("q", docs, top_k=2)

        assert [d.page_content for d in out] == ["doc2", "doc0"], "应按 TEI 返回的次序"
        assert out[0].metadata["rerank_score"] == 0.9877, "分数应四舍五入到 4 位"
        assert out[0].metadata["rerank_method"] == "bge-reranker-v2-m3"

    def test_out_of_range_index_is_skipped(self, monkeypatch, enabled):
        """TEI 返回越界索引时必须跳过，不能 IndexError 崩掉整条检索。

        越界项被丢弃后，剩下的名额由补位逻辑填上（标记为 fallback）。
        """
        _install_client(
            monkeypatch,
            payload=[{"index": 99, "score": 0.9}, {"index": 0, "score": 0.5}],
        )
        out = R.rerank("q", _docs(3), top_k=2)

        assert out[0].page_content == "doc0"
        assert out[0].metadata["rerank_score"] == 0.5, "只有合法索引的分数应被写入"
        assert out[1].metadata["rerank_method"] == "bge-reranker-v2-m3-fallback"

    def test_negative_index_is_skipped(self, monkeypatch, enabled):
        """负索引必须被丢弃，**不能**被 Python 的负下标语义当成"最后一条"。"""
        _install_client(monkeypatch, payload=[{"index": -1, "score": 0.9}])
        out = R.rerank("q", _docs(3), top_k=2)

        assert all(d.metadata["rerank_method"] != "bge-reranker-v2-m3" for d in out), (
            "没有任何文档应被标记为 TEI 排序结果"
        )
        assert [d.page_content for d in out] == ["doc0", "doc1"], "应由补位逻辑填满"

    def test_backfills_unranked_docs_to_reach_top_k(self, monkeypatch, enabled):
        """TEI 只返回 1 条但 top_k=3 时，要补足到 3 条并标记 fallback。"""
        _install_client(monkeypatch, payload=[{"index": 1, "score": 0.9}])
        docs = _docs(3)

        out = R.rerank("q", docs, top_k=3)

        assert len(out) == 3
        assert out[0].page_content == "doc1"
        assert out[0].metadata["rerank_method"] == "bge-reranker-v2-m3"
        assert out[1].metadata["rerank_score"] == 0.0
        assert out[1].metadata["rerank_method"] == "bge-reranker-v2-m3-fallback"

    def test_backfill_does_not_duplicate_ranked_docs(self, monkeypatch, enabled):
        _install_client(monkeypatch, payload=[{"index": 0, "score": 0.9}])
        out = R.rerank("q", _docs(3), top_k=3)
        contents = [d.page_content for d in out]
        assert len(contents) == len(set(contents)), "补位不应重复已排序的文档"

    def test_does_not_exceed_top_k_when_tei_returns_more(self, monkeypatch, enabled):
        """TEI 不遵守 top_n 多返回时，必须自己截断 —— 否则违反"返回前 top_k 个"的契约。"""
        _install_client(
            monkeypatch,
            payload=[{"index": i, "score": 1.0 - i / 10} for i in range(5)],
        )
        out = R.rerank("q", _docs(5), top_k=2)
        assert len(out) == 2

    def test_heading_path_prefix_stripped_before_sending(self, monkeypatch, enabled):
        """heading_path 前缀要剥掉再送 TEI —— 它会干扰相关性判断。"""
        calls = _install_client(monkeypatch, payload=[])
        docs = [
            Document(page_content="[进程管理] > [PV操作]\n正文内容", metadata={"chunk_id": "c"})
        ]

        R.rerank("q", docs, top_k=1)

        assert calls["json"]["texts"] == ["正文内容"]

    def test_long_document_truncated_before_sending(self, monkeypatch, enabled):
        calls = _install_client(monkeypatch, payload=[])
        docs = [Document(page_content="甲" * 5000, metadata={"chunk_id": "c"})]

        R.rerank("q", docs, top_k=1)

        assert len(calls["json"]["texts"][0]) == R._MAX_DOC_CHARS

    def test_request_shape(self, monkeypatch, enabled):
        calls = _install_client(monkeypatch, payload=[])
        R.rerank("查询", _docs(4), top_k=2)

        assert calls["url"] == "http://localhost:9999/rerank"
        assert calls["json"]["query"] == "查询"
        assert calls["json"]["top_n"] == 2, "top_n 应为 min(top_k, 候选数)"
        assert calls["timeout"] == 5

    def test_top_n_never_exceeds_candidate_count(self, monkeypatch, enabled):
        calls = _install_client(monkeypatch, payload=[])
        R.rerank("q", _docs(2), top_k=10)
        assert calls["json"]["top_n"] == 2
