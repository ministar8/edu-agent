"""Candidate Pool Recall：preferred 层 top-up（修复 A1：目标层进不了池）。

问题：融合后 legacy（无 kb_depth 旧讲义/真题）挤满 top-k，
L1/L2/L3 单独 `where kb_depth=…` 能命中，但进不了最终候选池。

策略（非权重）：
对 preferred_layers 各做一次定向召回，合并进 FusedEvidence，
保证目标层**至少进入候选池**，再由 layer ranking / Evidence Policy 决策。
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

from rag.evidence import FusedEvidence, TextEvidence
from rag.topic_relevance import is_topic_relevant, topic_relevance_score

logger = logging.getLogger(__name__)

SUBJECT_COLLECTIONS = (
    "data_structure",
    "computer_organization",
    "operating_system",
    "computer_network",
    "questions",
)


def _doc_to_evidence(doc, score: float, collection: str) -> TextEvidence:
    meta = dict(getattr(doc, "metadata", None) or {})
    meta.setdefault("kb_depth", meta.get("kb_depth") or "")
    chunk_id = str(meta.get("chunk_id") or meta.get("section.chunk_id") or "")
    content = getattr(doc, "page_content", "") or ""
    return TextEvidence(
        evidence_id=f"topup_{collection}_{chunk_id or hash(content) % 10**8}",
        content=content,
        source=str(meta.get("source") or meta.get("source_file") or collection),
        score=float(score),
        collection=collection,
        chunk_id=chunk_id,
        section_path=str(meta.get("section_path") or meta.get("heading") or ""),
        knowledge_points=[],
        metadata=meta,
    )


async def topup_preferred_layers(
    query: str,
    preferred_layers: Sequence[str],
    fused: FusedEvidence,
    *,
    per_layer: int = 2,
    max_add: int = 4,
    eligibility_where: dict | None = None,
) -> FusedEvidence:
    """preferred 层缺口补齐（不是无条件灌池）。

    - 仅当候选池**缺少**某 preferred 层时 top-up 该层
    - 每层每集合最多 per_layer，总新增 ≤ max_add
    - 按 score 截断，避免无关 advanced 灌满 pack

    ★ **资格边界**：本函数只决定「从哪些层补」，**不重写 eligibility**。
      调用方必须把 policy 的 `eligibility_where()` 传入 `eligibility_where`
      （与主检索同一条 where），避免 top-up 绕过 doc_role 约束
      —— 例如 verify 禁 `exam_answer`，但 top-up 只按 `kb_depth=exams`
      会把 answer.md 拉进池，随后被 Evidence Policy 裁掉，形成空 L3。
    """
    from schema.task_policy import merge_where_filters

    preferred = list(preferred_layers or [])
    if not preferred:
        return fused

    # 语义层集合（空串 = legacy 资产，不是层）
    pool_layers = {
        str((e.metadata or {}).get("kb_depth") or "")
        for e in (fused.text_evidences or [])
        if str((e.metadata or {}).get("kb_depth") or "") in ("basic", "advanced", "exams")
    }
    missing = [ly for ly in preferred if ly not in pool_layers]
    if not missing:
        return fused

    from rag.vectorstore import get_vector_store_manager

    mgr = get_vector_store_manager()
    existing_ids = {
        str((e.metadata or {}).get("chunk_id") or e.evidence_id)
        for e in (fused.text_evidences or [])
    }
    candidates: list[TextEvidence] = []
    for layer in missing:
        # 层约束 + 资格约束（policy 真源）；layer_recall 不实现资格规则
        filt = merge_where_filters({"kb_depth": layer}, eligibility_where)
        for coll in SUBJECT_COLLECTIONS:
            try:
                hits = await mgr.asimilarity_search_with_score(coll, query, per_layer, filter=filt)
            except Exception:
                logger.debug("layer topup %s/%s failed", layer, coll, exc_info=True)
                continue
            for doc, score in hits:
                ev = _doc_to_evidence(doc, score, coll)
                key = str((ev.metadata or {}).get("chunk_id") or ev.evidence_id)
                if key in existing_ids:
                    continue
                # ★ 主题门：错域 top-up 直接丢弃（哈夫曼≠CSMA）
                rel = topic_relevance_score(query, ev.content, ev.metadata)
                if not is_topic_relevant(query, ev.content, ev.metadata, min_score=0.25):
                    logger.debug(
                        "topup reject off-topic %s rel=%.2f %s",
                        key,
                        rel,
                        (ev.metadata or {}).get("section_id"),
                    )
                    continue
                existing_ids.add(key)
                ev.metadata = {
                    **(ev.metadata or {}),
                    "layer_topup": True,
                    "topic_relevance": round(rel, 3),
                }
                candidates.append(ev)

    if not candidates:
        return fused

    candidates.sort(
        key=lambda e: (float((e.metadata or {}).get("topic_relevance") or 0.0), e.score),
        reverse=True,
    )
    added = candidates[:max_add]

    out = fused.model_copy(deep=True)
    out.text_evidences = list(fused.text_evidences or []) + added
    out.metadata = {
        **(fused.metadata or {}),
        "layer_topup_added": len(added),
        "layer_topup_layers": missing,
    }
    return out
