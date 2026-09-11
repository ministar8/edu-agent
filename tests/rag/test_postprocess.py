"""rag/postprocess.py 纯函数测试：RRF 融合与同 section 去重（不依赖 TEI / Chroma）。"""

import hashlib

from langchain_core.documents import Document

from rag.postprocess import (
    _base_route_name,
    _dedup_key,
    _dynamic_rrf_k,
    dedup_same_section,
    merge_route_results,
    weighted_rrf_merge,
)


def _doc(content: str, collection: str = "os", content_hash: str | None = None) -> Document:
    metadata: dict = {"_collection": collection}
    if content_hash is not None:
        metadata["content_hash"] = content_hash
    return Document(page_content=content, metadata=metadata)


class TestDynamicRrfK:
    def test_lower_bound(self):
        assert _dynamic_rrf_k(1) == 10
        assert _dynamic_rrf_k(0) == 10

    def test_midpoint(self):
        assert _dynamic_rrf_k(4) == 20

    def test_upper_bound(self):
        assert _dynamic_rrf_k(100) == 60

    def test_monotonic_non_decreasing(self):
        values = [_dynamic_rrf_k(n) for n in range(1, 40)]
        assert values == sorted(values)


class TestBaseRouteName:
    def test_strips_collection_prefix(self):
        assert _base_route_name("os:concept_meta") == "concept_meta"

    def test_passthrough_without_prefix(self):
        assert _base_route_name("semantic") == "semantic"

    def test_takes_last_segment(self):
        assert _base_route_name("  a:b:c  ") == "c"


class TestDedupKey:
    def test_prefers_content_hash(self):
        assert _dedup_key(_doc("x", collection="os", content_hash="abc")) == "os::abc"

    def test_falls_back_to_content_digest(self):
        expected = hashlib.sha256("同一段内容".encode()).hexdigest()[:16]
        assert _dedup_key(_doc("同一段内容", collection="os")) == f"os::{expected}"

    def test_stable_for_same_content_and_collection(self):
        assert _dedup_key(_doc("内容", collection="ds")) == _dedup_key(
            _doc("内容", collection="ds")
        )

    def test_differs_across_collections(self):
        # 同名文档出现在不同集合时不能被误合并
        assert _dedup_key(_doc("内容", collection="ds")) != _dedup_key(
            _doc("内容", collection="os")
        )


class TestMergeRouteResults:
    def test_empty(self):
        assert merge_route_results([]) == []

    def test_single_route_keeps_rank_order(self):
        results = [
            ("semantic", [(_doc("a", content_hash="ha"), 0.9), (_doc("b", content_hash="hb"), 0.8)])
        ]
        merged = merge_route_results(results)
        assert [d.page_content for d, _ in merged] == ["a", "b"]

    def test_cross_route_hit_is_boosted(self):
        shared = _doc("shared", content_hash="h-shared")
        results = [
            ("semantic", [(_doc("other", content_hash="h-other"), 0.99), (shared, 0.5)]),
            ("bm25", [(shared, 0.4)]),
        ]
        merged = merge_route_results(results)

        assert merged[0][0].page_content == "shared"
        assert merged[0][0].metadata["recall_route_count"] == 2
        assert "bm25" in merged[0][0].metadata["recall_routes"]

    def test_writes_recall_metadata(self):
        doc, score = merge_route_results([("semantic", [(_doc("a", content_hash="h"), 0.9)])])[0]
        assert doc.metadata["recall_score"] == round(score, 6)
        assert doc.metadata["recall_route_count"] == 1
        assert doc.metadata["recall_semantic_score"] == 0.9

    def test_scores_descending(self):
        results = [
            ("semantic", [(_doc("a", content_hash="ha"), 0.9)]),
            ("bm25", [(_doc("b", content_hash="hb"), 0.1)]),
        ]
        scores = [s for _, s in merge_route_results(results)]
        assert scores == sorted(scores, reverse=True)


class TestWeightedRrfMerge:
    def test_source_weight_orders_results(self):
        grouped = [
            ("orig", [(_doc("orig", content_hash="h1"), 0.5)]),
            ("sub", [(_doc("sub", content_hash="h2"), 0.5)]),
        ]
        merged = weighted_rrf_merge(grouped, weights={"orig": 1.5, "sub": 1.0})

        assert [d.page_content for d, _ in merged] == ["orig", "sub"]
        assert merged[0][0].metadata["_decompose_labels"] == "orig"

    def test_unknown_label_defaults_to_unit_weight(self):
        grouped = [("mystery", [(_doc("a", content_hash="h1"), 0.5)])]
        merged = weighted_rrf_merge(grouped, weights={})
        assert len(merged) == 1

    def test_dedups_by_content_hash(self):
        grouped = [
            ("orig", [(_doc("same", content_hash="h"), 0.5)]),
            ("sub", [(_doc("same", content_hash="h"), 0.4)]),
        ]
        merged = weighted_rrf_merge(grouped, weights={"orig": 1.5, "sub": 1.0})
        assert len(merged) == 1
        assert merged[0][0].metadata["_decompose_labels"] == "orig, sub"


def _sec_doc(content: str, section_id: str, score: float) -> tuple[Document, float]:
    return Document(page_content=content, metadata={"section.id": section_id}), score


class TestDedupSameSection:
    def test_under_cap_keeps_all(self):
        results = [_sec_doc(f"c{i}", "s1", 1.0 - i * 0.1) for i in range(3)]
        assert len(dedup_same_section(results, max_per_section=3)) == 3

    def test_over_cap_keeps_top_n_by_score(self):
        results = [
            _sec_doc(f"c{i}", "s1", score) for i, score in enumerate([0.1, 0.9, 0.5, 0.7, 0.3])
        ]
        kept = dedup_same_section(results, max_per_section=2)
        assert len(kept) == 2
        assert sorted(s for _, s in kept) == [0.7, 0.9]

    def test_docs_without_section_are_all_kept(self):
        results = [_sec_doc(f"c{i}", "", 1.0 - i * 0.1) for i in range(5)]
        assert len(dedup_same_section(results, max_per_section=2)) == 5

    def test_output_sorted_desc(self):
        results = [_sec_doc("a", "s1", 0.2), _sec_doc("b", "s2", 0.9), _sec_doc("c", "s3", 0.5)]
        scores = [s for _, s in dedup_same_section(results)]
        assert scores == sorted(scores, reverse=True)

    def test_empty(self):
        assert dedup_same_section([]) == []
