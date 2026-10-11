"""检索流水线编排（论文架构图「Plan → Execute」对应模块）。

阶段顺序（与论文图一致）：
  classify → plan → decompose → 多路召回 → 去重/阈值 → rerank → HyDE → window → finalize

只做编排与阶段函数；路由细节见 `routes.py`，重排实现见 `reranker.py`。

子模块：
- `_constants`：模块级常量与 `StageSink` 类型别名
- `_types`：阶段产出/请求结构 + 编排状态 `_RunState`
- `_support`：策略解析（阈值/coarse_k）与重排状态判定
- `_stages`：各阶段函数（★ 猴子补丁目标模块，见其模块文档串）
- `_orchestrator`：`aretrieve_documents` + 收尾指标

★ 阶段函数（`_stage_*`）**不**在本包顶层再导出：它们住在 `_stages`，且 `aretrieve_documents`
  经由 `_stages` 命名空间调用 —— 若要打猴子补丁，请打在 `rag.retrieval.pipeline._stages` 上，
  打在包顶层是**静默无效**的。
"""

from ._constants import SCORE_THRESHOLD, StageSink
from ._orchestrator import aretrieve_documents
from ._support import _derive_rerank_status, _resolve_thresholds
from ._types import (
    _HydeOutcome,
    _RecallRequest,
    _RetrievalContext,
    _RetrievalCounters,
    _RetrievalPlan,
    _RunState,
    _WindowOutcome,
)

__all__ = [
    "SCORE_THRESHOLD",
    "StageSink",
    "_HydeOutcome",
    "_RecallRequest",
    "_RetrievalContext",
    "_RetrievalCounters",
    "_RetrievalPlan",
    "_RunState",
    "_WindowOutcome",
    "_derive_rerank_status",
    "_resolve_thresholds",
    "aretrieve_documents",
]
