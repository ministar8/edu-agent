"""rag/query_classifier.py 纯函数测试（规则层，不触发 LLM）。"""

from rag.query_classifier import (
    CODE_DEPTH,
    DEEP_DEPTH,
    SHALLOW_DEPTH,
    STANDARD_DEPTH,
    QueryCategory,
    classify_query,
    resolve_retrieval_depth,
)


class TestResolveRetrievalDepth:
    def test_uncategorized_is_standard(self):
        assert resolve_retrieval_depth(QueryCategory()) is STANDARD_DEPTH

    def test_short_is_shallow(self):
        assert resolve_retrieval_depth(QueryCategory(is_short=True)) is SHALLOW_DEPTH

    def test_short_wins_over_code(self):
        # 规则优先级：is_short 在 is_code 之前
        assert resolve_retrieval_depth(QueryCategory(is_short=True, is_code=True)) is SHALLOW_DEPTH

    def test_comparison_is_standard(self):
        assert resolve_retrieval_depth(QueryCategory(is_comparison=True)) is STANDARD_DEPTH

    def test_code_is_code_depth(self):
        assert resolve_retrieval_depth(QueryCategory(is_code=True)) is CODE_DEPTH

    def test_exercise_is_standard(self):
        assert resolve_retrieval_depth(QueryCategory(is_exercise=True)) is STANDARD_DEPTH

    def test_answer_is_standard(self):
        assert resolve_retrieval_depth(QueryCategory(is_answer=True)) is STANDARD_DEPTH

    def test_long_structured_is_deep(self):
        assert (
            resolve_retrieval_depth(QueryCategory(is_long=True, is_structured=True)) is DEEP_DEPTH
        )

    def test_long_but_unstructured_is_standard(self):
        assert resolve_retrieval_depth(QueryCategory(is_long=True)) is STANDARD_DEPTH

    def test_learning_path_long_is_deep(self):
        assert (
            resolve_retrieval_depth(QueryCategory(is_learning_path=True, is_long=True))
            is DEEP_DEPTH
        )

    def test_learning_path_non_long_is_standard(self):
        assert resolve_retrieval_depth(QueryCategory(is_learning_path=True)) is STANDARD_DEPTH


class TestQueryCategory:
    def test_to_dict(self):
        data = QueryCategory(is_code=True, is_long=True, source="llm").to_dict()
        assert data["is_code"] is True
        assert data["is_long"] is True
        assert data["is_short"] is False
        assert data["source"] == "llm"

    def test_repr(self):
        assert "code" in repr(QueryCategory(is_code=True))
        assert "uncategorized" in repr(QueryCategory())


class TestClassifyQuery:
    def test_blank_is_uncategorized(self):
        cat = classify_query("   ")
        assert isinstance(cat, QueryCategory)
        assert cat.source == "rule"
        assert not any(
            [
                cat.is_code,
                cat.is_exercise,
                cat.is_answer,
                cat.is_concept,
                cat.is_short,
                cat.is_long,
            ]
        )

    def test_sync_entry_is_rule_only(self):
        # 同步入口保证不调用 LLM（避免 asyncio.run 嵌套）
        assert classify_query("进程调度算法").source == "rule"

    def test_deterministic_across_calls(self):
        first = classify_query("死锁产生的四个必要条件是什么").to_dict()
        second = classify_query("死锁产生的四个必要条件是什么").to_dict()
        assert first == second


class TestRetrievalDepthPresets:
    def test_depth_levels_are_distinct(self):
        depths = {SHALLOW_DEPTH.depth, STANDARD_DEPTH.depth, DEEP_DEPTH.depth, CODE_DEPTH.depth}
        assert depths == {"shallow", "standard", "deep", "code"}

    def test_k_increases_with_depth(self):
        assert SHALLOW_DEPTH.k < STANDARD_DEPTH.k < DEEP_DEPTH.k

    def test_shallow_skips_expensive_stages(self):
        assert SHALLOW_DEPTH.skip_decompose
        assert SHALLOW_DEPTH.skip_hyde
        assert SHALLOW_DEPTH.skip_metadata_routes

    def test_deep_enables_everything(self):
        assert not DEEP_DEPTH.skip_bm25
        assert not DEEP_DEPTH.skip_decompose
        assert not DEEP_DEPTH.skip_hyde

    def test_code_depth_skips_hyde_only(self):
        assert CODE_DEPTH.skip_hyde
        assert not CODE_DEPTH.skip_decompose
