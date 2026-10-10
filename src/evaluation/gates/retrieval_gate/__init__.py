"""检索质量黄金集回归门禁（包）。

原 `retrieval_gate.py` 已拆为子模块，公开 API 由本 `__init__` 原样重导出 ——
`from evaluation.gates.retrieval_gate import X` 与 `python -m evaluation.gates.retrieval_gate`
两种用法都保持不变。
"""

from __future__ import annotations

from ._baseline import (
    build_baseline_payload,
    check_baseline_sanity,
    compare_to_baseline,
    default_baseline_path,
    load_baseline,
)
from ._constants import (
    DEFAULT_BASELINE_PATH,
    DEFAULT_GOLDEN_PATH,
    GATE_K,
    QUESTIONS_CATEGORY,
    REAL_EMBED_BASELINE_PATH,
    REAL_EMBED_RERANK_BASELINE_PATH,
    REAL_EMBED_RERANK_DISABLED_BASELINE_PATH,
    RERANK_BASELINE_PATH,
    RERANK_DISABLED_BASELINE_PATH,
    SUBJECT_TO_CATEGORY,
)
from ._data import (
    MetricSpec,
    QueryOutcome,
    RerankObservation,
    RetrievalMetrics,
    compute_metrics,
)
from ._gate import (
    main,
    report_retrieval_anomalies,
    run_gate,
    unexpected_query_failures,
)
from ._golden import (
    chapter_of_source,
    load_golden_queries,
)
from ._index import (
    build_index,
    configure_for_gate,
    wait_for_index_ready,
)
from ._modes import (
    GATE_RERANK_MODE,
    GATE_RERANK_MODE_ERROR,
    GATE_USE_REAL_EMBEDDING,
    GATE_USE_REAL_RERANK,
    RERANK_MODES,
    SUPPORTED_ROUTES,
    embedding_mode,
    rerank_backend,
    rerank_mode,
    rerank_requested,
)

__all__ = [
    "DEFAULT_BASELINE_PATH",
    "DEFAULT_GOLDEN_PATH",
    "GATE_K",
    "QUESTIONS_CATEGORY",
    "REAL_EMBED_BASELINE_PATH",
    "REAL_EMBED_RERANK_BASELINE_PATH",
    "REAL_EMBED_RERANK_DISABLED_BASELINE_PATH",
    "RERANK_BASELINE_PATH",
    "RERANK_DISABLED_BASELINE_PATH",
    "SUBJECT_TO_CATEGORY",
    "GATE_RERANK_MODE",
    "GATE_RERANK_MODE_ERROR",
    "GATE_USE_REAL_EMBEDDING",
    "GATE_USE_REAL_RERANK",
    "RERANK_MODES",
    "SUPPORTED_ROUTES",
    "embedding_mode",
    "rerank_backend",
    "rerank_mode",
    "rerank_requested",
    "chapter_of_source",
    "load_golden_queries",
    "MetricSpec",
    "QueryOutcome",
    "RerankObservation",
    "RetrievalMetrics",
    "compute_metrics",
    "build_index",
    "configure_for_gate",
    "wait_for_index_ready",
    "build_baseline_payload",
    "check_baseline_sanity",
    "compare_to_baseline",
    "default_baseline_path",
    "load_baseline",
    "main",
    "report_retrieval_anomalies",
    "run_gate",
    "unexpected_query_failures",
]
