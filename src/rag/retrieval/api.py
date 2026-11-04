"""产品检索门面：检索 + 层排序 + 安全裁剪的唯一入口。

与 `aretrieve_evidence_raw` 的分工（两条显式路径，勿混）：

- **本模块** = 产品路径：返回**已裁剪**的证据包，给 Agent 用。
- **`aretrieve_evidence_raw`** = 测量路径：返回**未裁剪**的检索包，
  给检索门禁 / RAGAS / 诊断 / 消融实验用（它们测的是检索质量，不是披露）。

★ 为什么 release 放在这里、而不下移进 `aretrieve_evidence`：
  `_semantic_cache_codec` 的缓存发生在 `aretrieve_evidence` 内部；若把
  `finalize_with_layer_ranking` / `apply_evidence_policy` 下移，缓存就会存**裁剪后**
  的包 —— 策略变更后旧缓存继续命中，等于真泄露。本门面因此位于缓存**之上**。
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from rag.retrieval.evidence import FusedEvidence
from rag.retrieval.evidence_policy import apply_evidence_policy, finalize_with_layer_ranking
from rag.retrieval.query_classifier import RetrievalDepth
from rag.retrieval.retriever import StageSink, aretrieve_evidence_raw
from rag.retrieval.task_policy import resolve_task_policy
from rag.retrieval.verifier import VerificationResult
from schema.task_policy import TaskMode


class EvidenceBundle(BaseModel):
    """产品路径的检索结果：已裁剪的证据包 + release flags + 规则校验。"""

    pack: FusedEvidence
    release: dict[str, Any] = Field(default_factory=dict)
    verdict: VerificationResult


async def retrieve_for_task(
    query: str,
    *,
    task_mode: TaskMode | None = None,
    depth: RetrievalDepth | None = None,
    k: int = 5,
    context_mode: TaskMode | None = None,
    agent_prior: str = "",
    on_stage: StageSink | None = None,
) -> EvidenceBundle:
    """产品路径：策略解析 → 检索 → 层排序 → 安全裁剪。

    异常**不在这里吞**：调用方（`agents/tools.py`）负责把异常映射成
    `status=error` 的对外载荷，并区分 `unavailable` / `internal`。
    """
    policy = resolve_task_policy(
        query,
        task_mode=task_mode,  # type: ignore[arg-type]
        context_mode=context_mode,  # type: ignore[arg-type]
        agent_prior=agent_prior,
    )

    from schema.task_policy import merge_where_filters

    recall_filter = merge_where_filters(None, policy.eligibility_where())
    # 多取候选 → layer 软加权 → 再截 top-k（否则 preferred 层进不了池）
    candidate_k = max(k * 3, 15)
    fused, verdict = await aretrieve_evidence_raw(
        query=query,
        k=candidate_k,
        use_rerank=True,
        depth=depth,
        filter=recall_filter,
        on_stage=on_stage,
        preferred_layers=list(policy.preferred_layers),
        eligible_layers=policy.eligible_semantic_layers(),
    )
    fused = finalize_with_layer_ranking(fused, policy, keep=k)
    fused, release = apply_evidence_policy(fused, policy)
    return EvidenceBundle(pack=fused, release=release, verdict=verdict)
