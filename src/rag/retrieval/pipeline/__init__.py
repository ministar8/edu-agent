"""检索流水线编排（主路径 ①–④ 的阶段执行；论文「Plan → Execute」中的 Execute）。

阶段顺序（与主路径一致，见 `src/rag/README.md`）：
  classify → plan → decompose → 多路召回 → 去重/阈值 → rerank → HyDE → window → finalize

只做编排与阶段函数：
- 路由**拼装** → `recall.py`；路由**执行** → `routes.py`
- RRF/去重/窗口 → `postprocess/`；重排实现 → `reranker.py`
- 出包与权限 → `evidence_policy.py`（本包 finalize 后仍经门面/策略出口）

子模块：
- `_internals`：常量、策略解析（阈值/coarse_k）、状态/请求结构
- `_helpers`：单阶段辅助（HyDE / 窗口 / 阈值）
- `_stages`：各阶段函数（★ 猴子补丁目标模块，见其模块文档串）
- `_orchestrator`：`aretrieve_documents` + 收尾指标

★ 阶段函数（`_stage_*`）**不**在本包顶层再导出：它们住在 `_stages`，且 `aretrieve_documents`
  经由 `_stages` 命名空间调用 —— 若要打猴子补丁，请打在 `rag.retrieval.pipeline._stages` 上，
  打在包顶层是**静默无效**的。
"""

from ._internals import (
    SCORE_THRESHOLD,
    StageSink,
    _derive_rerank_status,
    _HydeOutcome,
    _PlanSink,
    _RecallRequest,
    _resolve_thresholds,
    _RetrievalContext,
    _RetrievalCounters,
    _RetrievalPlan,
    _RunState,
    _WindowOutcome,
)
from ._orchestrator import aretrieve_documents

__all__ = [
    "SCORE_THRESHOLD",
    "StageSink",
    "_HydeOutcome",
    "_PlanSink",
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
