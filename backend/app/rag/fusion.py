from __future__ import annotations

import logging
from collections import Counter, defaultdict
from typing import Iterable

from langchain_core.documents import Document

from app.rag.evidence import (
    AgentEvidence,
    FusedEvidence,
    KGEvidence,
    TextEvidence,
    format_kg_evidence,
    format_text_evidence,
    kg_evidence_from_text,
    text_evidence_from_document,
)
from app.config import settings
from app.rag.rag_utils import estimate_tokens

logger = logging.getLogger(__name__)
_MAX_PER_SOURCE = 3
_KG_TEXT_BOOST = 1.2
_PARENT_WINDOW_BONUS = 1.08
_HYDE_PENALTY = 0.95
_NOISE_DOWNGRADE_PENALTY = 0.5   # window 噪声降级惩罚（排到 context 末尾）


def _content_key(ev: TextEvidence) -> str:
    key = str(ev.metadata.get("content_hash") or "").strip()
    if key:
        return f"{ev.collection}:{key}"
    return f"{ev.collection}:{ev.source}:{ev.content[:120]}"


def _truncate_to_tokens(text: str, max_tokens: int) -> str:
    if estimate_tokens(text) <= max_tokens:
        return text
    if max_tokens <= 0:
        return ""
    char_budget = int(len(text) * max_tokens / max(estimate_tokens(text), 1))
    return text[:max(0, char_budget)] + "\n[...truncated]"


def _truncate_profile(student_profile: str) -> str:
    if not student_profile:
        return ""
    if estimate_tokens(student_profile) <= settings.MAX_STUDENT_PROFILE_TOKENS:
        return student_profile
    return _truncate_to_tokens(student_profile, settings.MAX_STUDENT_PROFILE_TOKENS)


def _extract_kg_terms(kg_evidences: Iterable[KGEvidence]) -> set[str]:
    terms: set[str] = set()
    for ev in kg_evidences:
        for node in ev.nodes:
            node = str(node).strip()
            if node:
                terms.add(node)
        for path in ev.paths:
            for item in path:
                item = str(item).strip()
                if item:
                    terms.add(item)
        for edge in ev.edges:
            for key in ("source", "target", "name"):
                val = str(edge.get(key) or "").strip()
                if val:
                    terms.add(val)
    return terms


def _score_text_evidence(ev: TextEvidence, kg_terms: set[str]) -> float:
    if "rerank_score" in ev.metadata:
        score = float(ev.rerank_score or 0.0)
    elif "recall_score" in ev.metadata:
        score = float(ev.recall_score or 0.0)
    else:
        score = float(ev.score or 0.0)
    if score == 0.0:
        score = 0.01
    if ev.metadata.get("_parent_expanded") or ev.metadata.get("section.chunk_role") == "parent_window":
        score *= _PARENT_WINDOW_BONUS
    if ev.metadata.get("_hyde_fallback"):
        score *= _HYDE_PENALTY
    if ev.metadata.get("_noise_downgraded"):
        score *= ev.metadata.get("_noise_downgrade_factor", _NOISE_DOWNGRADE_PENALTY)
    if kg_terms:
        kp = set(ev.knowledge_points)
        if kp & kg_terms:
            score *= _KG_TEXT_BOOST
        elif any(len(term) >= 2 and term in ev.content for term in kg_terms):
            score *= _KG_TEXT_BOOST
    return score


def fuse_evidence(
    text_evidences: list[TextEvidence] | None = None,
    kg_evidences: list[KGEvidence] | None = None,
    agent_evidences: list[AgentEvidence] | None = None,
    query: str = "",
    student_profile: str = "",
    max_tokens: int = settings.CONTEXT_TOKEN_BUDGET,
    depth: str = "standard",
) -> FusedEvidence:
    text_evidences = text_evidences or []
    kg_evidences = kg_evidences or []
    agent_evidences = agent_evidences or []
    if not max_tokens:
        max_tokens = settings.CONTEXT_TOKEN_BUDGET

    kg_terms = _extract_kg_terms(kg_evidences)

    deduped: dict[str, TextEvidence] = {}
    for ev in text_evidences:
        key = _content_key(ev)
        existing = deduped.get(key)
        if existing is None:
            deduped[key] = ev
            continue
        if _score_text_evidence(ev, kg_terms) > _score_text_evidence(existing, kg_terms):
            deduped[key] = ev

    ranked = sorted(
        deduped.values(),
        key=lambda ev: _score_text_evidence(ev, kg_terms),
        reverse=True,
    )

    source_counts: defaultdict[str, int] = defaultdict(int)
    diversified: list[TextEvidence] = []
    overflow: list[TextEvidence] = []
    for ev in ranked:
        if source_counts[ev.source] < _MAX_PER_SOURCE:
            diversified.append(ev)
            source_counts[ev.source] += 1
        else:
            overflow.append(ev)
    ranked = diversified + overflow

    profile = _truncate_profile(student_profile)
    kg_parts = [format_kg_evidence(ev) for ev in kg_evidences if ev.serialized.strip()]
    kg_text = "\n".join(kg_parts).strip()
    kg_tokens = estimate_tokens(kg_text) if kg_text else 0
    kg_nodes_count = sum(len(ev.nodes) for ev in kg_evidences)
    kg_edges_count = sum(len(ev.edges) for ev in kg_evidences)
    kg_paths_count = sum(len(ev.paths) for ev in kg_evidences)
    kg_resolved_topics = sorted({
        str(topic)
        for ev in kg_evidences
        for topic in ev.metadata.get("resolved_topics", [])
        if str(topic).strip()
    })
    kg_matched_candidates = sorted({
        str(candidate)
        for ev in kg_evidences
        for candidate in ev.metadata.get("matched_candidates", [])
        if str(candidate).strip()
    })
    profile_tokens = estimate_tokens(profile) if profile else 0
    doc_budget = max(1000, max_tokens - kg_tokens - profile_tokens)

    selected_texts: list[tuple[TextEvidence, str]] = []
    used_doc_tokens = 0
    for i, ev in enumerate(ranked, 1):
        formatted = format_text_evidence(i, ev)
        tokens = estimate_tokens(formatted)
        if used_doc_tokens + tokens <= doc_budget:
            selected_texts.append((ev, formatted))
            used_doc_tokens += tokens
            continue
        remaining = doc_budget - used_doc_tokens
        if remaining > 200:
            selected_texts.append((ev, _truncate_to_tokens(formatted, remaining)))
            used_doc_tokens += remaining
        break

    parts: list[str] = []
    if selected_texts:
        # 策略 B：交叉排列（首尾效应优化）
        # LLM 对 Context 首尾位置关注度更高，中间位置容易被忽略
        # 将最高相关度的证据放在首尾，次相关的放在中间
        # 原序 [1,2,3,4,5] → 交叉排列 [1,3,5,4,2]
        n = len(selected_texts)
        if n >= 4:
            even_idx = list(range(0, n, 2))   # [0, 2, 4, ...]
            odd_idx = list(range(1, n, 2))    # [1, 3, 5, ...]
            odd_idx.reverse()                   # [5, 3, 1, ...]
            interleaved_indices = even_idx + odd_idx
            interleaved = [selected_texts[i] for i in interleaved_indices]
        else:
            interleaved = selected_texts

        parts.append(interleaved[0][1])
        if kg_text:
            parts.append(kg_text)
        parts.extend(text for _, text in interleaved[1:])
    elif kg_text:
        parts.append(kg_text)
    if profile:
        parts.append(profile)

    sources = []
    seen_sources = set()
    for ev, _ in selected_texts:
        if ev.source and ev.source not in seen_sources:
            sources.append(ev.source)
            seen_sources.add(ev.source)
    if not sources:
        for ev in kg_evidences:
            if ev.source and ev.source not in seen_sources:
                sources.append(ev.source)
                seen_sources.add(ev.source)

    selected_source_counts = Counter(ev.source for ev, _ in selected_texts if ev.source)
    diversity_score = 0.0
    if selected_texts:
        diversity_score = len(selected_source_counts) / len(selected_texts)

    final_context = "\n\n".join(parts)
    used_token_budget = estimate_tokens(final_context)
    if used_token_budget > max_tokens:
        final_context = _truncate_to_tokens(final_context, max_tokens)
        used_token_budget = estimate_tokens(final_context)
        logger.info(
            "Evidence fusion truncated query=%s tokens=%d/%d",
            query[:30], used_token_budget, max_tokens,
        )
    elif used_token_budget > max_tokens * 0.9:
        logger.info(
            "Evidence fusion budget query=%s text=%d/%d kg=%d tokens=%d/%d diversity=%.3f",
            query[:30], len(selected_texts), len(text_evidences), len(kg_evidences),
            used_token_budget, max_tokens, diversity_score,
        )

    fused = FusedEvidence(
        text_evidences=[ev for ev, _ in selected_texts],
        kg_evidences=kg_evidences,
        agent_evidences=agent_evidences,
        final_context=final_context,
        sources=sources,
        used_token_budget=used_token_budget,
        diversity_score=round(diversity_score, 6),
        metadata={
            "input_text_evidence_count": len(text_evidences),
            "deduped_text_evidence_count": len(deduped),
            "selected_text_evidence_count": len(selected_texts),
            "kg_used": bool(kg_evidences),
            "kg_evidence_count": len(kg_evidences),
            "kg_nodes_count": kg_nodes_count,
            "kg_edges_count": kg_edges_count,
            "kg_paths_count": kg_paths_count,
            "kg_tokens": kg_tokens,
            "kg_resolved_topics": kg_resolved_topics,
            "kg_matched_candidates": kg_matched_candidates,
            "kg_text_boost_terms": sorted(kg_terms),
            "profile_tokens": profile_tokens,
            "doc_token_budget": doc_budget,
            "max_tokens": max_tokens,
            "retrieval_depth": depth,
        },
    )

    return fused


def fuse_documents(
    docs: list[Document],
    query: str = "",
    kg_supplement: str = "",
    student_profile: str = "",
    max_tokens: int = settings.CONTEXT_TOKEN_BUDGET,
    kg_evidences: list[KGEvidence] | None = None,
    depth: str = "standard",
) -> FusedEvidence:
    """Fuse retrieved documents into FusedEvidence.

    Args:
        docs: Retrieved document list
        query: Original query
        kg_supplement: KG supplement text (legacy, used only when kg_evidences=None)
        student_profile: Student profile summary
        max_tokens: Token budget cap
        kg_evidences: Structured KG evidence list (priority over kg_supplement).
                      When provided, used directly; when None, converted from kg_supplement text.
    """
    text_evidences = [text_evidence_from_document(doc) for doc in docs]

    if kg_evidences is not None:
        # Use caller-provided structured KG evidence (with nodes/edges/paths)
        kg_evs = kg_evidences
    else:
        # Backward compat: convert from plain text (nodes/edges/paths stay empty)
        kg_ev = kg_evidence_from_text(kg_supplement)
        kg_evs = [kg_ev] if kg_ev else []

    return fuse_evidence(
        text_evidences=text_evidences,
        kg_evidences=kg_evs,
        query=query,
        student_profile=student_profile,
        max_tokens=max_tokens,
        depth=depth,
    )


async def afuse_documents(
    docs: list[Document],
    query: str = "",
    kg_supplement: str = "",
    student_profile: str = "",
    max_tokens: int = settings.CONTEXT_TOKEN_BUDGET,
    kg_evidences: list[KGEvidence] | None = None,
    depth: str = "standard",
) -> FusedEvidence:
    text_evidences = [text_evidence_from_document(doc) for doc in docs]
    if kg_evidences is not None:
        kg_evs = kg_evidences
    else:
        kg_ev = kg_evidence_from_text(kg_supplement)
        kg_evs = [kg_ev] if kg_ev else []

    fused = fuse_evidence(
        text_evidences=text_evidences,
        kg_evidences=kg_evs,
        query=query,
        student_profile=student_profile,
        max_tokens=max_tokens,
        depth=depth,
    )
    return fused
