"""rag/retrieval_strategy.py 直接测试。

覆盖检索链**第二跳**：分类 / 深度 → 策略（`layer` + `route_type`）。

这个模块是**纯映射、无 IO**，所以下面的断言大多是「契约」而不是「观察」：
它们固定的是调用方（`retriever.py` 的 841/844/1637/1640 四处）依赖的形状。

此前它没有任何直接测试，只有被上层检索用例顺带覆盖到的 50.0%。
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from rag.query_classifier import (
    CODE_DEPTH,
    DEEP_DEPTH,
    SHALLOW_DEPTH,
    STANDARD_DEPTH,
    TEXT_ONLY_DEPTH,
    QueryCategory,
    RetrievalDepth,
    resolve_retrieval_depth,
)
from rag.retrieval_strategy import (
    L1_FAST,
    L2_STANDARD,
    L2_TEXT_ONLY,
    L3_CODE,
    L3_DEEP,
    resolve_retrieval_strategy,
    strategy_from_depth,
)

ALL_PRESETS = (L1_FAST, L2_STANDARD, L2_TEXT_ONLY, L3_DEEP, L3_CODE)


class TestNamedDepthMapping:
    @pytest.mark.parametrize(
        ("depth", "expected"),
        [
            (SHALLOW_DEPTH, L1_FAST),
            (STANDARD_DEPTH, L2_STANDARD),
            (TEXT_ONLY_DEPTH, L2_TEXT_ONLY),
            (CODE_DEPTH, L3_CODE),
            (DEEP_DEPTH, L3_DEEP),
        ],
    )
    def test_known_depth_name_maps_to_its_preset(self, depth, expected):
        assert strategy_from_depth(depth) is expected

    def test_name_takes_precedence_over_skip_flags(self):
        """命名匹配在前 —— 即使 skip 标志看起来该走 custom 兜底，名字也优先。

        顺带固定一个容易误解的点：此时调用方传进来的 depth 对象被**整个丢弃**，
        返回的是预设自己的 depth。
        """
        passed = RetrievalDepth(depth="deep", skip_kg=True, skip_bm25=False)
        strat = strategy_from_depth(passed)

        assert strat is L3_DEEP
        assert strat.depth is DEEP_DEPTH
        assert strat.depth is not passed


class TestCustomFallback:
    """三个没有名字的深度走兜底分支 —— 只有手工构造 RetrievalDepth 才会命中。"""

    def test_skip_kg_with_bm25_is_l2_custom(self):
        depth = RetrievalDepth(depth="weird", skip_kg=True, skip_bm25=False)
        strat = strategy_from_depth(depth)
        assert (strat.layer, strat.route_type) == ("L2", "l2_custom")
        # 兜底分支会**原样保留**调用方的 depth（与命名分支相反）
        assert strat.depth is depth

    def test_skip_bm25_and_rerank_is_l1_custom(self):
        depth = RetrievalDepth(depth="weird", skip_bm25=True, skip_rerank=True)
        strat = strategy_from_depth(depth)
        assert (strat.layer, strat.route_type) == ("L1", "l1_custom")
        assert strat.depth is depth

    def test_everything_else_is_l3_custom(self):
        depth = RetrievalDepth(depth="weird")
        strat = strategy_from_depth(depth)
        assert (strat.layer, strat.route_type) == ("L3", "l3_custom")
        assert strat.depth is depth

    def test_skip_kg_without_bm25_skipped_does_not_match_l1(self):
        # l1_custom 要求 skip_bm25 **和** skip_rerank 同时为真，缺一不可
        depth = RetrievalDepth(depth="weird", skip_kg=True, skip_bm25=True, skip_rerank=False)
        assert strategy_from_depth(depth).route_type == "l3_custom"


class TestResolveRetrievalStrategy:
    def test_explicit_depth_overrides_category(self):
        """显式传 depth 时完全绕过分类 —— 这是调用方覆盖分类结果的唯一入口。"""
        cat = QueryCategory(is_code=True)  # 按分类会指向 CODE_DEPTH
        assert resolve_retrieval_strategy(cat, STANDARD_DEPTH) is L2_STANDARD

    def test_no_depth_falls_back_to_category(self):
        assert resolve_retrieval_strategy(QueryCategory(is_short=True)) is L1_FAST
        assert resolve_retrieval_strategy(QueryCategory(is_code=True)) is L3_CODE

    @pytest.mark.parametrize(
        "cat",
        [
            QueryCategory(),
            QueryCategory(is_short=True),
            QueryCategory(is_code=True),
            QueryCategory(is_comparison=True),
            QueryCategory(is_exercise=True),
            QueryCategory(is_answer=True),
            QueryCategory(is_long=True, is_structured=True),
            QueryCategory(is_learning_path=True),
            QueryCategory(is_learning_path=True, is_long=True),
        ],
    )
    def test_equivalent_to_the_two_step_composition(self, cat):
        """`resolve_retrieval_strategy(cat)` 等价于两步手工组合。

        这条断言是防止有人改动其中一步却忘了另一条路径。
        """
        assert resolve_retrieval_strategy(cat) == strategy_from_depth(resolve_retrieval_depth(cat))

    def test_empty_category_is_l2_standard(self):
        assert resolve_retrieval_strategy(QueryCategory()) is L2_STANDARD


class TestPresetShape:
    def test_route_type_prefix_matches_layer(self):
        """`route_type` 的前缀必须与 `layer` 一致 —— 下游按 route_type 做指标分组。"""
        for strat in ALL_PRESETS:
            assert strat.route_type.startswith(strat.layer.lower() + "_"), strat

    def test_layers_cover_all_three_levels(self):
        assert {s.layer for s in ALL_PRESETS} == {"L1", "L2", "L3"}

    def test_route_types_are_unique(self):
        assert len({s.route_type for s in ALL_PRESETS}) == len(ALL_PRESETS)

    def test_deeper_layer_returns_at_least_as_many_docs(self):
        assert L1_FAST.depth.k < L2_STANDARD.depth.k <= L3_DEEP.depth.k

    def test_presets_are_immutable(self):
        """预设是模块级单例、被所有请求共享 —— 必须 frozen，否则一处改动污染全局。"""
        with pytest.raises(FrozenInstanceError):
            L1_FAST.layer = "L3"

    def test_presets_are_returned_as_shared_singletons(self):
        assert strategy_from_depth(SHALLOW_DEPTH) is strategy_from_depth(SHALLOW_DEPTH)


class TestDepthObjectReuse:
    def test_all_presets_reuse_the_classifier_depth_objects(self):
        assert L1_FAST.depth is SHALLOW_DEPTH
        assert L2_STANDARD.depth is STANDARD_DEPTH
        assert L2_TEXT_ONLY.depth is TEXT_ONLY_DEPTH
        assert L3_DEEP.depth is DEEP_DEPTH
        assert L3_CODE.depth is CODE_DEPTH

    def test_standard_has_one_canonical_depth_on_both_paths(self):
        """分类路径与显式 depth 路径必须得到同一对象，不能再分叉成两种 standard。"""
        cat = QueryCategory()
        assert resolve_retrieval_strategy(cat).depth is STANDARD_DEPTH
        assert resolve_retrieval_strategy(cat, STANDARD_DEPTH).depth is STANDARD_DEPTH
        assert strategy_from_depth(STANDARD_DEPTH).depth is STANDARD_DEPTH

    def test_standard_skips_kg_but_keeps_lightweight_rerank_and_metadata_cap(self):
        # 这是既有生产默认的 L2 行为；本次只把它收回唯一真源 STANDARD_DEPTH。
        assert STANDARD_DEPTH.skip_kg is True
        assert STANDARD_DEPTH.max_metadata_routes == 2
        assert STANDARD_DEPTH.lightweight_rerank is True
