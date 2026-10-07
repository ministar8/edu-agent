"""检索侧探针：对一条 case 跑**与产品同策略**的检索，抽出可归因的原始指标。

为什么单独一个模块、而不是从 agent 的 tool payload 取
----------------------------------------------------
`agents/tools.py` 下发的 `EvidenceDoc` 只暴露
`source / section_path / chunk_id / score / knowledge_points / excerpt`
—— **不含 `kb_depth` / `doc_role` / `category`**（见 `schema/evidence.py`）。
而 Phase 0 要判「真题有没有进包」（`exam_hit@5`）与「学科对不对」（`category_hit`），
这两者恰恰依赖上述元数据。故这里直接调用检索链拿 `FusedEvidence`（元数据完整），
并**镜像 `tools._retrieve_payload` 的策略与后处理顺序**，保证口径与产品一致：

    resolve_task_policy → aretrieve_evidence_with_retry
        → finalize_with_layer_ranking → apply_evidence_policy

★ 本模块**只读**，不修改产品行为；Phase 0 纪律：只测量、不修。
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# 与 retrieval_gate 同源（那里是学科→类目的单一真源）
try:  # 延迟导入失败也不致命：退化为不做 category_hit
    from evaluation.retrieval_gate import SUBJECT_TO_CATEGORY
except Exception:  # noqa: BLE001
    SUBJECT_TO_CATEGORY = {
        "ds": "data_structure",
        "co": "computer_organization",
        "os": "operating_system",
        "network": "computer_network",
    }

_EXAM_ROLES = ("exam_item", "exam_answer", "exam_paper")


@dataclass
class RetrievedItem:
    """包内单条证据的可归因快照。"""

    source: str = ""
    chunk_id: str = ""
    kb_depth: str = ""
    doc_role: str = ""
    category: str = ""
    knowledge_points: list[str] = field(default_factory=list)
    score: float = 0.0

    @property
    def is_exam(self) -> bool:
        """是否 L3 真题资产（用于 `exam_hit@k`）。"""
        if self.kb_depth == "exams" or self.doc_role in _EXAM_ROLES:
            return True
        if self.category == "questions":
            return True
        src = self.source.replace("\\", "/").lower()
        return "/exams/" in src or src.startswith("exams/")


@dataclass
class RetrievalProbe:
    ok: bool = False
    status: str = "error"
    items: list[RetrievedItem] = field(default_factory=list)
    pack_len: int = 0
    evidence_count: int = 0
    error: str = ""
    latency_ms: float = 0.0

    def top_k(self, k: int) -> list[RetrievedItem]:
        return self.items[:k]


def _to_item(ev) -> RetrievedItem:
    meta = ev.metadata or {}
    return RetrievedItem(
        source=str(ev.source or meta.get("source_file") or ""),
        chunk_id=str(ev.chunk_id or ""),
        kb_depth=str(meta.get("kb_depth") or ""),
        doc_role=str(meta.get("doc_role") or ""),
        category=str(meta.get("category") or ev.collection or ""),
        knowledge_points=list(ev.knowledge_points or []),
        score=float(ev.score or 0.0),
    )


async def probe_retrieval(
    query: str,
    *,
    task_mode: str | None = None,
    k: int = 5,
    use_rerank: bool = True,
) -> RetrievalProbe:
    """跑一次与产品同策略的检索，返回可归因探针结果。

    `task_mode` 为空时由 query 信号自行分类（与产品一致）。
    任何异常都收敛为 `ok=False, status="error"`，**不抛出** ——
    单条 case 的检索失败不该中断整轮 Phase 0。
    """
    from rag.evidence_policy import apply_evidence_policy, finalize_with_layer_ranking
    from rag.retriever import aretrieve_evidence_with_retry
    from rag.task_policy import resolve_task_policy
    from schema.task_policy import merge_where_filters

    started = time.perf_counter()
    try:
        policy = resolve_task_policy(query, task_mode=task_mode)  # type: ignore[arg-type]
        recall_filter = merge_where_filters(None, policy.eligibility_where())
        candidate_k = max(k * 3, 15)  # 与 tools._retrieve_payload 同口径
        fused, _ver = await aretrieve_evidence_with_retry(
            query=query,
            k=candidate_k,
            use_rerank=use_rerank,
            filter=recall_filter,
            max_retries=0,
            use_llm_verify=False,
            preferred_layers=list(policy.preferred_layers),
            eligible_layers=policy.eligible_semantic_layers(),
        )
        fused = finalize_with_layer_ranking(fused, policy, keep=k)
        fused, _flags = apply_evidence_policy(fused, policy)
    except Exception as e:  # noqa: BLE001
        logger.warning("检索探针失败 query=%s: %s", query[:40], e)
        return RetrievalProbe(
            ok=False,
            status="error",
            error=f"{type(e).__name__}: {e}",
            latency_ms=round((time.perf_counter() - started) * 1000, 3),
        )

    items = [_to_item(ev) for ev in fused.text_evidences]
    context = fused.final_context or ""
    return RetrievalProbe(
        ok=bool(context.strip()),
        status="ok" if context.strip() else "empty",
        items=items,
        pack_len=len(context),
        evidence_count=len(items),
        latency_ms=round((time.perf_counter() - started) * 1000, 3),
    )
