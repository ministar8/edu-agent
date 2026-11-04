"""检索流水线的内部共享件：常量、策略解析、状态/请求结构。

原先拆在 `_constants` / `_types` / `_support` 三个文件；它们都是 pipeline 的
内部实现细节，没有独立对外语义，合并后减少文件碎片。行为与原拆分版等价。
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field

from langchain_core.documents import Document

from core.settings import settings
from rag.common.rag_utils import extract_query_terms, normalize_query_text
from rag.retrieval.query_classifier import QueryCategory, RetrievalDepth, classify_query
from rag.retrieval.recall import ALL_ROUTES

logger = logging.getLogger(__name__)

# ── 常量 ──────────────────────────────────────────────

# 阶段进度回调类型：上报「即将进入某检索阶段」
StageSink = Callable[[str], None]

# 重排候选扩展系数（与门禁/实验的 coarse_k 口径一致）
_RERANK_EXPAND_FACTOR = settings.RERANK_EXPAND_FACTOR

# RRF 融合分数阈值（基于采样校准，非余弦距离）
# RRF(k=20): 排名1≈0.048, 排名5≈0.040（权重 1.0 时）
# 权重 1.5 的路由第 10 名 = 1.5/(20+10) = 0.05 → 刚好过旧阈值
# 0.06 ≈ "至少1路前7" 或 "2路前15"，过滤掉排名#8+的单路噪声
# 数值来自 `settings.RETRIEVAL_SCORE_THRESHOLD`（可经 .env 覆盖，backlog #14）。
# 保留模块级别名是为了不动下游函数签名的默认值。
SCORE_THRESHOLD = settings.RETRIEVAL_SCORE_THRESHOLD

# 对比类查询的子查询精简路由集（避免子查询把召回面摊得过宽）
_COMPACT_SUBQUERY_ROUTES = {"keyword_bm25", "concept_meta", "structured_meta", "section_meta"}

# `_safe_to_thread` 在超时/异常时**原样返回 default**；用一个可辨识哨兵当 default，
# 调用点就能区分「rerank 真的返回了列表」与「rerank 坏了走兜底」⇒ 四态里的 `failed`
# 有实测依据，而不是把降级猜成失败。（reranker 自捕 HTTP 错误会返回**不含 rerank_score**
# 的正常列表 ⇒ raised=False、无键 ⇒ degraded，与「超时/抛错走 default=failed」天然分开。）
_RERANK_UNSET = object()


# ── 策略解析与状态判定 ────────────────────────────────


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


# ── 状态 / 请求 / 产出结构 ────────────────────────────


@dataclass
class _RunState:
    """一次检索的编排状态（**可变**，随阶段推进就地更新）。

    承载原 `aretrieve_documents` 里靠局部变量逐阶段传递的全部事实 —— 拆开后显式化，
    且让**异常路径**也能读到「已走到哪、计数到多少」（错误指标要报告部分计数）。
    """

    depth: RetrievalDepth | None
    k: int
    use_rerank: bool
    effective_threshold: float
    coarse_k: int
    cat: QueryCategory | None = None
    retrieval_layer: str = ""
    route_type: str = ""
    decomposed: bool = False
    sub_queries: list[str] = field(default_factory=list)
    raw_results_count: int = 0
    post_dedup_count: int = 0
    post_threshold_count: int = 0
    post_rerank_count: int = 0
    post_window_count: int = 0
    window_added_count: int = 0
    rerank_status: str = ""
    hyde_triggered: bool = False
    hyde_added_count: int = 0
    hyde_error: str = ""


@dataclass
class _PlanSink:
    """旁路出参：把阶段 1-3 解析出的计划带回门面。

    与 `rerank_status_out` 同款 —— 空包/异常时没有 doc 可挂溯源字段，所以由调用方
    传入一个可变对象，pipeline 在 `finally` 填充。这样 classify/plan/decompose
    只由 pipeline 执行一次，门面不再自己算一遍。
    """

    depth: RetrievalDepth | None = None
    k: int = 0
    coarse_k: int = 0
    effective_threshold: float = 0.0
    retrieval_layer: str = ""
    route_type: str = ""
    cat: QueryCategory | None = None
    sub_queries: list[str] = field(default_factory=list)
    decomposed: bool = False
    decompose_ms: float = 0.0


@dataclass(frozen=True)
class _RetrievalPlan:
    """阶段 2 的产物：一次检索实际采用的策略与阈值。

    把 `depth` / `k` / `use_rerank` 也放进返回值，是因为阶段 2 会**就地调整**它们
    （`depth=None` 时由分类推导；策略要求时覆盖 `k`、关掉重排）。
    原实现靠闭包变量隐式传递，拆开后显式化，避免调用方漏用调整后的值。
    """

    depth: RetrievalDepth
    k: int
    use_rerank: bool
    effective_threshold: float
    coarse_k: int
    retrieval_layer: str
    route_type: str


@dataclass(frozen=True)
class _RecallRequest:
    """阶段 4 的全部输入。

    参数有 11 个，且明显分成两类（检索配置 / 查询状态）—— 直接铺成位置参数
    在调用处极易错位，故打包成一个不可变请求对象，顺带把契约写清楚。
    """

    query: str
    collection_name: str
    coarse_k: int
    filter: dict | None
    cat: QueryCategory
    terms: list[str]
    use_rerank: bool
    depth: RetrievalDepth
    sub_queries: list[str]
    decomposed: bool
    effective_threshold: float


@dataclass(frozen=True)
class _HydeContext:
    """HyDE 阶段的检索上下文（避免 8 个参数在调用处错位）。"""

    collection_name: str
    coarse_k: int
    filter: dict | None
    cat: QueryCategory
    use_rerank: bool
    depth: RetrievalDepth
    k: int
    effective_threshold: float


@dataclass(frozen=True)
class _HydeOutcome:
    """HyDE 阶段的产出。

    `rerank_status` 也在返回值里：HyDE 召回后若走了重排并把状态拉回 success，
    会把整条链路的重排状态更新 —— 这是原实现「用过重排 ⇒ 标记翻 True」行为的
    状态枚举化。拆开后显式返回，避免调用方漏掉这次翻转。
    """

    docs: list[Document]
    triggered: bool
    added_count: int
    error: str
    rerank_status: str
    elapsed_ms: float


@dataclass(frozen=True)
class _WindowOutcome:
    docs: list[Document]
    elapsed_ms: float
    window_merged_count: int = 0  # 合并进锚点的窗口 chunk 数


@dataclass(frozen=True)
class _RetrievalCounters:
    """一次检索各阶段的计数，供收尾写指标。"""

    raw_results: int
    after_dedup: int
    after_threshold: int
    after_rerank: int
    after_window: int
    window_added: int


@dataclass(frozen=True)
class _RetrievalContext:
    """收尾阶段需要的检索上下文（调用方请求 + 实际采用的策略）。

    参数很多，但都是"这一次检索的事实"—— 打包成一个不可变对象，
    避免 19 个关键字参数在调用处错位。
    """

    query: str
    collection_name: str
    k: int
    coarse_k: int
    effective_threshold: float
    depth: RetrievalDepth | None
    retrieval_layer: str
    route_type: str
    cat: QueryCategory
    decomposed: bool
    sub_queries: list[str]
    use_rerank: bool
    rerank_status: str
    hyde_triggered: bool
    hyde_added_count: int
    hyde_error: str
    counters: _RetrievalCounters
