"""检索流水线的阶段产出/请求结构（从 pipeline.py 拆出，行为等价）。"""

from __future__ import annotations

from dataclasses import dataclass, field

from langchain_core.documents import Document

from rag.retrieval.query_classifier import QueryCategory, RetrievalDepth


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
