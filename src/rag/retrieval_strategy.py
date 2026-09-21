from __future__ import annotations

from dataclasses import dataclass

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


@dataclass(frozen=True)
class RetrievalStrategy:
    layer: str
    route_type: str
    depth: RetrievalDepth


L1_FAST = RetrievalStrategy(layer="L1", route_type="l1_fast", depth=SHALLOW_DEPTH)
# ★ standard 的唯一真源在 query_classifier.STANDARD_DEPTH。历史上这里复制了一份
# L2_STANDARD_DEPTH，只有 skip_kg 与唯一真源相反：默认生产路径（depth=None）会走
# 这份副本，显式传 STANDARD_DEPTH 则走另一份，造成同一 "standard" 两种行为。
L2_STANDARD = RetrievalStrategy(layer="L2", route_type="l2_standard", depth=STANDARD_DEPTH)
L2_TEXT_ONLY = RetrievalStrategy(layer="L2", route_type="l2_text_only", depth=TEXT_ONLY_DEPTH)
L3_DEEP = RetrievalStrategy(layer="L3", route_type="l3_deep", depth=DEEP_DEPTH)
L3_CODE = RetrievalStrategy(layer="L3", route_type="l3_code", depth=CODE_DEPTH)


def strategy_from_depth(depth: RetrievalDepth) -> RetrievalStrategy:
    if depth.depth == "shallow":
        return L1_FAST
    if depth.depth == "standard":
        return L2_STANDARD
    if depth.depth == "text_only":
        return L2_TEXT_ONLY
    if depth.depth == "code":
        return L3_CODE
    if depth.depth == "deep":
        return L3_DEEP
    if depth.skip_kg and not depth.skip_bm25:
        return RetrievalStrategy(layer="L2", route_type="l2_custom", depth=depth)
    if depth.skip_bm25 and depth.skip_rerank:
        return RetrievalStrategy(layer="L1", route_type="l1_custom", depth=depth)
    return RetrievalStrategy(layer="L3", route_type="l3_custom", depth=depth)


def resolve_retrieval_strategy(
    cat: QueryCategory, depth: RetrievalDepth | None = None
) -> RetrievalStrategy:
    return strategy_from_depth(depth or resolve_retrieval_depth(cat))
