"""rag/retriever.py 纯函数测试：不依赖 TEI / ChromaDB / 网络。

`retriever.py` 是全项目最大的模块（近 1900 行），此前覆盖率仅 7%，且其中
`retrieve_documents` / `aretrieve_documents` 各 400+ 行。本文件先把**无外部依赖的
决策逻辑**（阈值、检索策略、路由 k、超时、缓存拷贝语义）锁进回归网：

1. 这些逻辑是"调参"的实际落点（SCORE_THRESHOLD、RERANK_MIN_SCORE、各类倍率），
   此前改动它们无法被任何自动化手段验证；
2. 它们同时是后续拆分巨型函数的安全网 —— 拆分前后这些断言必须保持全绿。

**关于钉死校准值**：`TestResolveRetrievalPolicyCalibration` 直接断言当前阈值/候选池
取值。这不是脆弱测试，而是把"隐式校准结果"变成"显式契约"：任何改动阈值表或
`recall._ROUTE_WEIGHTS` 权重表的行为，都会在此处产生 diff，迫使改动者确认这是
有意的调参而非误伤。
"""

from __future__ import annotations

import threading

import pytest
from langchain_core.documents import Document

from core.settings import settings
from rag.query_classifier import QueryCategory
from rag.retriever import (
    _apply_rerank_threshold,
    _cache_stats_fields,
    _copy_results,
    _emit_evidence_metric,
    _resolve_retrieval_policy,
    _route_adaptive_k,
    _route_timeout_seconds,
    _safe_to_thread,
    _summarize_document,
)


def _doc(score: float | None = None, **metadata) -> Document:
    """构造带 rerank_score 的 Document（其余 metadata 由调用方指定）。"""
    md: dict = dict(metadata)
    if score is not None:
        md["rerank_score"] = score
    return Document(page_content="内容", metadata=md)


def _scores(docs: list[Document]) -> list[float]:
    return [d.metadata["rerank_score"] for d in docs]


# ── Rerank 双重阈值过滤 ─────────────────────────────────


class TestApplyRerankThreshold:
    """相对阈值（top × RERANK_MIN_SCORE）与绝对阈值取高者，不足 min_keep 时兜底。"""

    def test_empty_input_returns_empty(self):
        assert _apply_rerank_threshold([]) == []

    def test_keeps_docs_above_relative_threshold(self):
        # top=1.0 → rel=0.3；abs=0.15 → final=0.3；0.2 被滤掉
        docs = [_doc(1.0), _doc(0.5), _doc(0.2)]
        assert _scores(_apply_rerank_threshold(docs)) == [1.0, 0.5]

    def test_absolute_threshold_dominates_when_top_score_is_low(self):
        # top=0.2 → rel=0.06；abs=0.15 → final=0.15。
        # 0.08 高于 rel 但低于 abs —— 正是绝对阈值的鉴别点：
        # 若绝对阈值失效（abs=0），0.08 会进入结果集（3 篇）而非走兜底（2 篇）。
        docs = [_doc(0.2), _doc(0.1), _doc(0.08)]
        assert _scores(_apply_rerank_threshold(docs)) == [0.2, 0.1]

    def test_zero_top_score_falls_back_to_absolute_threshold(self):
        # top=0 → rel 分支不生效（top_score > 0 为假）→ final=abs=0.15 → 全不达标 → 兜底保留 top-2。
        # 若绝对阈值失效（abs=0），三篇都会"达标"（0.0 >= 0.0）而不走兜底。
        docs = [_doc(0.0), _doc(0.0), _doc(0.0)]
        assert len(_apply_rerank_threshold(docs)) == 2

    def test_missing_rerank_score_treated_as_zero(self):
        docs = [Document(page_content="无分数", metadata={}), _doc(1.0)]
        # top 取第一项的 0 → final=abs=0.15；1.0 达标但仅 1 篇 → 兜底保留 top-2（原顺序）
        assert len(_apply_rerank_threshold(docs)) == 2

    def test_all_above_threshold_are_kept(self):
        docs = [_doc(1.0), _doc(0.9), _doc(0.8)]
        assert _scores(_apply_rerank_threshold(docs)) == [1.0, 0.9, 0.8]

    def test_min_keep_is_honoured_when_lowering_threshold_scope(self):
        # 显式放宽 min_keep=1 时，只有 1 篇达标也无需兜底
        docs = [_doc(1.0), _doc(0.1)]
        assert _scores(_apply_rerank_threshold(docs, min_keep=1)) == [1.0]

    def test_relative_threshold_scales_with_top_score(self):
        # top=2.0 → rel=0.6 → final=0.6；0.5 被滤掉（证明是比例而非固定值）
        docs = [_doc(2.0), _doc(1.0), _doc(0.5)]
        assert _scores(_apply_rerank_threshold(docs)) == [2.0, 1.0]

    def test_order_is_preserved(self):
        docs = [_doc(0.9), _doc(1.0), _doc(0.8)]
        # 函数不改排序（排序由上游 rerank 负责），仅做过滤
        assert _scores(_apply_rerank_threshold(docs)) == [0.9, 1.0, 0.8]


# ── 检索策略：阈值自适应 + 候选池扩缩 ─────────────────────


class TestResolveRetrievalPolicyRelations:
    """跨查询类型的关系断言：不依赖权重表的具体数值，抗调参。"""

    def test_default_category_leaves_threshold_untouched(self):
        # 无任何类型标记时，最活跃路由权重恰好等于基准权重 1.5 → 不缩放
        threshold, _ = _resolve_retrieval_policy("进程同步", 5, 0.06, True, cat=QueryCategory())
        assert threshold == pytest.approx(0.06)

    def test_precise_categories_tighten_threshold(self):
        baseline, _ = _resolve_retrieval_policy("x", 5, 0.06, True, cat=QueryCategory())
        for cat in (
            QueryCategory(is_code=True),
            QueryCategory(is_exercise=True),
            QueryCategory(is_answer=True),
            QueryCategory(is_comparison=True),
        ):
            tightened, _ = _resolve_retrieval_policy("x", 5, 0.06, True, cat=cat)
            assert tightened > baseline, f"{cat!r} 应收紧阈值"

    def test_short_query_loosens_threshold(self):
        # 短查询结果少，放宽阈值保召回
        baseline, _ = _resolve_retrieval_policy("x", 5, 0.06, True, cat=QueryCategory())
        short, _ = _resolve_retrieval_policy("x", 5, 0.06, True, cat=QueryCategory(is_short=True))
        assert short < baseline

    def test_threshold_scales_with_input_threshold(self):
        # 输入阈值翻倍 → 输出阈值同步翻倍（线性关系）
        low, _ = _resolve_retrieval_policy("x", 5, 0.05, True, cat=QueryCategory(is_code=True))
        high, _ = _resolve_retrieval_policy("x", 5, 0.10, True, cat=QueryCategory(is_code=True))
        assert high == pytest.approx(low * 2)

    def test_none_category_is_classified_internally(self):
        threshold, coarse_k = _resolve_retrieval_policy("什么是虚拟内存", 5, 0.06, True, cat=None)
        assert threshold > 0
        assert coarse_k >= 5


class TestResolveRetrievalPolicyCalibration:
    """把当前校准结果钉成显式契约（改权重表/倍率时必须同步更新这里）。"""

    @pytest.mark.parametrize(
        ("label", "cat", "expected_threshold", "expected_coarse_k"),
        [
            ("default", QueryCategory(), 0.060, 25),
            ("code", QueryCategory(is_code=True), 0.100, 30),
            ("exercise", QueryCategory(is_exercise=True), 0.120, 25),
            ("answer", QueryCategory(is_answer=True), 0.120, 25),
            ("short", QueryCategory(is_short=True), 0.045, 30),
            ("long", QueryCategory(is_long=True), 0.066, 30),
            ("comparison", QueryCategory(is_comparison=True), 0.088, 25),
            ("concept", QueryCategory(is_concept=True), 0.080, 25),
            ("structured", QueryCategory(is_structured=True), 0.080, 25),
        ],
    )
    def test_calibration_table(self, label, cat, expected_threshold, expected_coarse_k):
        threshold, coarse_k = _resolve_retrieval_policy("测试查询", 5, 0.06, True, cat=cat)
        assert threshold == pytest.approx(expected_threshold), f"{label} 阈值漂移"
        assert coarse_k == expected_coarse_k, f"{label} 候选池漂移"

    @pytest.mark.parametrize(
        ("k", "expected_coarse_k"),
        [(1, 5), (5, 25), (8, 40), (10, 50), (20, 50)],
    )
    def test_rerank_candidate_pool_expansion_and_cap(self, k, expected_coarse_k):
        # 扩展倍数 5，但硬上限 50
        _, coarse_k = _resolve_retrieval_policy("x", k, 0.06, True, cat=QueryCategory())
        assert coarse_k == expected_coarse_k

    @pytest.mark.parametrize(
        ("k", "expected_coarse_k"),
        [(5, 5), (20, 20), (30, 20)],
    )
    def test_no_rerank_path_caps_candidate_pool_at_20(self, k, expected_coarse_k):
        _, coarse_k = _resolve_retrieval_policy("x", k, 0.06, False, cat=QueryCategory())
        assert coarse_k == expected_coarse_k

    def test_no_rerank_short_query_gets_small_boost(self):
        _, coarse_k = _resolve_retrieval_policy(
            "x", 3, 0.06, False, cat=QueryCategory(is_short=True)
        )
        assert coarse_k == 7  # max(k + 4, k * 2) = 7

    def test_no_rerank_long_query_hits_cap(self):
        _, coarse_k = _resolve_retrieval_policy(
            "x", 10, 0.06, False, cat=QueryCategory(is_long=True)
        )
        assert coarse_k == 20  # max(k + 3, k * 2) = 20，再被 min(..., 20) 截断


# ── 按路由调整候选数 ────────────────────────────────────


class TestRouteAdaptiveK:
    """BM25 放大候选、expanded 收缩、*_meta 精准过滤收紧且封顶 10。"""

    @pytest.mark.parametrize(
        ("k", "route", "expected"),
        [
            (10, "semantic", 10),  # 语义路由不缩放
            (10, "keyword_bm25", 12),  # ×1.2
            (10, "expanded", 8),  # ×0.8
            (10, "concept_meta", 6),  # ×0.6
            (30, "concept_meta", 10),  # 封顶 10
            (20, "keyword_bm25", 24),
        ],
    )
    def test_rerank_enabled(self, k, route, expected):
        assert _route_adaptive_k(k, True, route) == expected

    @pytest.mark.parametrize("route", ["expanded", "concept_meta", "code_meta"])
    def test_small_k_has_lower_bound_of_3(self, route):
        # int(1 * 0.8) = 0 / int(1 * 0.6) = 0 → 由 max(3, ...) 兜底
        assert _route_adaptive_k(1, True, route) == 3

    def test_bm25_small_k_has_no_lower_bound(self):
        assert _route_adaptive_k(1, True, "keyword_bm25") == 1

    def test_meta_routes_recognised_by_suffix(self):
        for route in ("concept_meta", "code_meta", "merged_qa_meta", "section_meta"):
            assert _route_adaptive_k(20, True, route) == 10

    @pytest.mark.parametrize(
        ("use_rerank", "expected"),
        [(True, 40), (False, 20)],
    )
    def test_hard_cap_depends_on_rerank(self, use_rerank, expected):
        assert _route_adaptive_k(50, use_rerank, "semantic") == expected

    def test_unknown_route_passes_through(self):
        assert _route_adaptive_k(10, True, "") == 10
        assert _route_adaptive_k(10, True, "focus") == 10


# ── 路由超时预算 ────────────────────────────────────────


class TestRouteTimeoutSeconds:
    """各路由超时不得超过 TOOL_CALL_TIMEOUT；BM25 与元数据路由更紧。"""

    def test_default_values(self):
        assert _route_timeout_seconds("semantic") == 20.0
        assert _route_timeout_seconds("keyword_bm25") == 15.0
        assert _route_timeout_seconds("concept_meta") == 15.0
        assert _route_timeout_seconds("code_meta") == 15.0

    def test_never_exceeds_configured_budget(self, monkeypatch):
        monkeypatch.setattr(settings, "TOOL_CALL_TIMEOUT", 10)
        for route in ("semantic", "keyword_bm25", "concept_meta"):
            assert _route_timeout_seconds(route) == 10.0

    def test_zero_budget_falls_back_to_30(self, monkeypatch):
        # `getattr(...) or 30` 的兜底：0 是假值，不应导致超时为 0（等于必然失败）
        monkeypatch.setattr(settings, "TOOL_CALL_TIMEOUT", 0)
        assert _route_timeout_seconds("semantic") == 20.0

    def test_missing_setting_falls_back_to_30(self, monkeypatch):
        monkeypatch.delattr(settings, "TOOL_CALL_TIMEOUT", raising=False)
        assert _route_timeout_seconds("keyword_bm25") == 15.0


# ── 缓存拷贝语义（防止下游写入污染缓存）─────────────────


class TestCopyResults:
    """缓存命中必须返回深一层的副本：下游会往 metadata 写 _collection / 窗口展开等。"""

    def test_preserves_content_and_scores(self):
        original = [(Document(page_content="甲", metadata={"a": 1}), 0.9)]
        copied = _copy_results(original)
        assert copied[0][0].page_content == "甲"
        assert copied[0][0].metadata == {"a": 1}
        assert copied[0][1] == 0.9

    def test_returns_new_list_and_documents(self):
        original = [(Document(page_content="甲", metadata={"a": 1}), 0.9)]
        copied = _copy_results(original)
        assert copied is not original
        assert copied[0][0] is not original[0][0]

    def test_metadata_mutation_does_not_leak_into_source(self):
        # 这是本函数存在的唯一理由：下游写 metadata 不得污染缓存原对象
        source_doc = Document(page_content="甲", metadata={"a": 1})
        copied = _copy_results([(source_doc, 0.9)])
        copied[0][0].metadata["_collection"] = "os"
        copied[0][0].metadata["a"] = 999
        assert source_doc.metadata == {"a": 1}

    def test_empty_input(self):
        assert _copy_results([]) == []

    def test_order_preserved(self):
        original = [
            (Document(page_content="一", metadata={}), 0.3),
            (Document(page_content="二", metadata={}), 0.2),
        ]
        assert [d.page_content for d, _ in _copy_results(original)] == ["一", "二"]


class TestCacheStatsFields:
    def test_exposes_expected_keys_and_types(self):
        stats = _cache_stats_fields()
        assert set(stats) == {"cache_hits", "cache_misses", "cache_hit_rate"}
        assert isinstance(stats["cache_hits"], int)
        assert isinstance(stats["cache_misses"], int)
        assert isinstance(stats["cache_hit_rate"], int | float)


# ── 诊断摘要 ────────────────────────────────────────────


class TestSummarizeDocument:
    def test_prefers_source_file_over_source(self):
        doc = Document(
            page_content="x",
            metadata={"source_file": "os.md", "source": "legacy.md", "heading_title": "分页"},
        )
        assert "source=os.md" in _summarize_document(doc)

    def test_falls_back_to_unknown_source(self):
        assert "source=unknown" in _summarize_document(Document(page_content="x", metadata={}))

    def test_truncates_heading_and_routes(self):
        doc = Document(
            page_content="x",
            metadata={
                "source_file": "os.md",
                "heading": "很长的标题" * 10,
                "recall_routes": "route" * 50,
            },
        )
        summary = _summarize_document(doc)
        assert "heading=" in summary
        assert len(summary) < 250  # 标题与路由均被截断


# ── 指标埋点（防御性：字段缺失不得抛异常）────────────────


class TestEmitEvidenceMetric:
    def test_tolerates_none_fused(self):
        # fused 为 None 时全部走 getattr 兜底，不得抛异常
        _emit_evidence_metric(query="q", collection_name="os", start=0.0, fused=None)

    def test_tolerates_object_missing_all_attributes(self):
        class Bare:
            pass

        _emit_evidence_metric(query="q", collection_name="os", start=0.0, fused=Bare())

    def test_emits_expected_values(self, monkeypatch):
        captured: dict = {}

        def fake_emit(**kwargs):
            captured.update(kwargs)

        monkeypatch.setattr("rag.retriever.metrics.emit_evidence_summary", fake_emit, raising=True)
        fused = type(
            "Fused",
            (),
            {
                "metadata": {"k": 5, "route_type": "semantic"},
                "text_evidences": [1, 2, 3],
                "kg_evidences": [],
                "final_context": "上下文",
                "sources": ["os.md"],
                "used_token_budget": 42,
            },
        )()
        _emit_evidence_metric(
            query="虚拟内存", collection_name="os", start=0.0, fused=fused, status="ok"
        )
        assert captured["status"] == "ok"
        assert captured["collection"] == "os"
        assert captured["values"]["text_evidence_count"] == 3
        assert captured["values"]["context_chars"] == len("上下文")
        assert captured["values"]["k"] == 5
        assert captured["values"]["source_count"] == 1
        assert captured["values"]["context_tokens"] == 42


# ── 异步分支隔离 ────────────────────────────────────────


class TestSafeToThread:
    """单路失败/超时不得拖垮整体检索 —— 由 _safe_to_thread 兜底成 default。"""

    @pytest.mark.asyncio
    async def test_returns_result_on_success(self):
        result = await _safe_to_thread("t", lambda a, b: a + b, 1, 2, timeout=1.0)
        assert result == 3

    @pytest.mark.asyncio
    async def test_passes_keyword_arguments(self):
        result = await _safe_to_thread("t", lambda **kw: kw["value"], timeout=1.0, value=7)
        assert result == 7

    @pytest.mark.asyncio
    async def test_returns_default_on_timeout(self):
        # 必须传**阻塞函数**：to_thread 在线程里跑，传协程函数只会立刻拿到未 await 的协程对象
        release = threading.Event()

        def _blocking():
            release.wait(timeout=5.0)
            return "too late"

        try:
            assert await _safe_to_thread("blocking", _blocking, timeout=0.05) is None
        finally:
            release.set()  # 立即放行线程，避免测试残留 5 秒

    @pytest.mark.asyncio
    async def test_returns_custom_default_on_timeout(self):
        release = threading.Event()

        def _blocking():
            release.wait(timeout=5.0)

        try:
            result = await _safe_to_thread("blocking", _blocking, timeout=0.05, default=[])
            assert result == []
        finally:
            release.set()

    @pytest.mark.asyncio
    async def test_returns_default_on_exception(self):
        def _boom():
            raise ValueError("路由炸了")

        # 异常被隔离成 default，不向上传播（保证多路并发不被单路拖垮）
        assert await _safe_to_thread("boom", _boom, timeout=1.0, default="fallback") == "fallback"

    @pytest.mark.asyncio
    async def test_default_is_none_when_not_specified(self):
        def _boom():
            raise RuntimeError("x")

        assert await _safe_to_thread("boom", _boom, timeout=1.0) is None
