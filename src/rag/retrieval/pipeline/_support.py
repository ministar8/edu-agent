"""检索策略解析与状态判定辅助（从 pipeline.py 拆出，行为等价）。"""

from __future__ import annotations

import logging

from core.settings import settings
from rag.common.rag_utils import extract_query_terms, normalize_query_text
from rag.retrieval.query_classifier import QueryCategory, classify_query
from rag.retrieval.recall import ALL_ROUTES

from ._constants import _RERANK_EXPAND_FACTOR, StageSink

logger = logging.getLogger(__name__)


def _emit_stage(on_stage: StageSink | None, stage: str) -> None:
    """上报「即将进入某检索阶段」。

    **回调抛错绝不能影响检索结果** —— 进度是锦上添花，失败就跳过。
    所以这里吞异常只记 debug（有日志，不是静默 pass）。
    """
    if on_stage is None:
        return
    try:
        on_stage(stage)
    except Exception:
        logger.debug("阶段进度回调失败（已忽略）: stage=%s", stage, exc_info=True)


def _resolve_cat(query: str, cat: QueryCategory | None) -> tuple[str, QueryCategory]:
    """确定查询类别；未提供时走「归一 → 抽词 → 规则/LLM 分类」。"""
    normalized = normalize_query_text(query)
    if cat is None:
        terms = extract_query_terms(normalized)
        cat = classify_query(query, terms)
    return normalized, cat


def _calibrated_threshold(score_threshold: float, cat: QueryCategory) -> float:
    """阈值校准：按最活跃路由权重缩放，再按查询类型微调。

    原理：w/(k+rank) < threshold 等价于 rank > w/threshold - k
    高权重路由(w=2.5)的 rank-20 噪声分数 = 2.5/40 = 0.0625 > 0.05，直接通过
    缩放后 threshold × (max_w / baseline_w) 让高权重路由的噪声也被过滤
    """
    from rag.retrieval.recall import get_route_weight

    _BASELINE_WEIGHT = settings.RRF_BASELINE_WEIGHT  # semantic default 权重作为基准
    # 路由名单来自 `recall.ALL_ROUTES`（单一真源）——
    # 这里曾内联抄了一份 13 个路由名的元组，与 `recall.py` 的权重表各自维护。
    # 抄漏/抄多**都不会报错**，只会让 `_max_w` 静默偏掉、进而让阈值偏掉。
    _active_routes = ALL_ROUTES
    _max_w = max(get_route_weight(r, cat) for r in _active_routes)
    effective_threshold = score_threshold * _max_w / _BASELINE_WEIGHT

    # 阈值自适应：在权重校准基础上，按查询类型微调
    # 注意：权重校准已收紧高权重路由，此处只需小幅调整
    if cat.is_exercise or cat.is_answer:
        effective_threshold *= 1.2  # 习题/答案适度收紧
    elif cat.is_short:
        effective_threshold *= 0.75  # 短查询结果少，放宽阈值保召回
    elif cat.is_long or cat.is_comparison:
        effective_threshold *= 1.1  # 长查询/对比查询适度收紧
    return effective_threshold


def _resolve_coarse_k(k: int, cat: QueryCategory, use_rerank: bool) -> int:
    """候选池大小 coarse_k：启用重排时按 expand_factor 放大，否则小幅加宽并封顶 20。"""
    if use_rerank:
        expand_factor = _RERANK_EXPAND_FACTOR
        if cat.is_short:
            expand_factor = 6  # 短查询检索命中少，需要更大候选池
        elif cat.is_code or cat.is_long:
            expand_factor = 6
        elif cat.is_answer or cat.is_exercise:
            expand_factor = 5  # 答案/习题适度扩大
        return max(k, min(k * expand_factor, 50))

    if cat.is_short:
        coarse_k = max(k + 4, k * 2)
    elif cat.is_code or cat.is_long:
        coarse_k = max(k + 3, k * 2)
    elif cat.is_answer or cat.is_exercise:
        coarse_k = max(k + 1, k)
    else:
        coarse_k = k
    return min(coarse_k, 20)


def _resolve_thresholds(
    query: str,
    k: int,
    score_threshold: float,
    use_rerank: bool,
    cat: QueryCategory | None = None,
) -> tuple[float, int]:
    normalized, cat = _resolve_cat(query, cat)
    effective_threshold = _calibrated_threshold(score_threshold, cat)
    coarse_k = _resolve_coarse_k(k, cat, use_rerank)

    logger.info(
        "Retrieval policy query=%s threshold=%.2f coarse_k=%d rerank=%s cat=%s",
        normalized[:50],
        effective_threshold,
        coarse_k,
        use_rerank,
        cat,
    )
    return effective_threshold, coarse_k


def _derive_rerank_status(docs: list, *, active: bool, raised: bool, empty_result: bool) -> str:
    """重排阶段状态的**唯一真源**（tier-0 枚举：off / success / degraded / failed）。

    ★ 判「有没有 `rerank_score` 这个**键**」而不是「分数是否 > 0」：
      `reranker.py:246` 有合法写 `0.0` 的补齐路径，用真值会把假重排 `on` 路由的自报值
      误翻成 False —— 等于借修诚实度偷偷换基线。
    ★ 先挡空 docs 再 `all(...)`：Python 的 `all([])` 是 True，不先守卫就会把
      `docs=[]` 判成 success（四态判据不能依赖「调用方保证 docs 非空」这种口头前提）。
    """
    if not active:
        return "off"
    if raised or empty_result:
        return "failed"
    if not docs:
        return "degraded"
    if all("rerank_score" in (d.metadata or {}) for d in docs):
        return "success"
    return "degraded"
