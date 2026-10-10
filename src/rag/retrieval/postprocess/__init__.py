"""检索后处理：RRF 融合 / 同 section 去重 / 窗口展开 —— 由原单文件拆分为子包，对外 API 不变。"""

from rag.retrieval.postprocess._dedup import dedup_same_section
from rag.retrieval.postprocess._rrf import merge_route_results, weighted_rrf_merge
from rag.retrieval.postprocess._window import (
    downgrade_window_noise,
    merge_window_into_anchors,
    sentence_window_expand,
)

__all__ = [
    "merge_route_results",
    "weighted_rrf_merge",
    "dedup_same_section",
    "sentence_window_expand",
    "merge_window_into_anchors",
    "downgrade_window_noise",
]
