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
# L2_STANDARD_DEPTH，与真源只有 `skip_kg` 相反，造成同一 "standard" 两种行为；
# 该副本与 `skip_kg` 字段已随 KG 遗留一并移除（2026-09-23）。
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
    # 以下是**自定义 depth**（depth 字段不属于上面 5 个命名档）的兜底。
    # 生产链路不会走到这里 —— `resolve_retrieval_depth` 只返回命名档。
    #
    # ★ 2026-09-23：原第一条兜底是 `if depth.skip_kg and not depth.skip_bm25: → l2_custom`，
    # 随 `skip_kg` 字段移除而删掉。影响：只有「自定义 depth + skip_kg=True + skip_bm25=False」
    # 这一种（现已无法表达）的组合从 l2_custom 变为 l3_custom，无生产路径受影响。
    if depth.skip_bm25 and depth.skip_rerank:
        return RetrievalStrategy(layer="L1", route_type="l1_custom", depth=depth)
    return RetrievalStrategy(layer="L3", route_type="l3_custom", depth=depth)


def resolve_retrieval_strategy(
    cat: QueryCategory, depth: RetrievalDepth | None = None
) -> RetrievalStrategy:
    return strategy_from_depth(depth or resolve_retrieval_depth(cat))
