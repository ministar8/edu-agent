from __future__ import annotations

import logging
from collections import Counter, defaultdict

from langchain_core.documents import Document

from core.settings import settings
from rag.evidence import (
    FusedEvidence,
    TextEvidence,
    format_text_evidence,
    text_evidence_from_document,
)
from rag.rag_utils import estimate_tokens

logger = logging.getLogger(__name__)
_MAX_PER_SOURCE = 3
_PARENT_WINDOW_BONUS = 1.08
_HYDE_PENALTY = 0.95
_NOISE_DOWNGRADE_PENALTY = 0.5  # window 噪声降级惩罚（排到 context 末尾）


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
    return text[: max(0, char_budget)] + "\n[...truncated]"


def _score_text_evidence(ev: TextEvidence) -> float:
    if "rerank_score" in ev.metadata:
        score = float(ev.rerank_score or 0.0)
    elif "recall_score" in ev.metadata:
        score = float(ev.recall_score or 0.0)
    else:
        score = float(ev.score or 0.0)
    if score == 0.0:
        score = 0.01
    if (
        ev.metadata.get("_parent_expanded")
        or ev.metadata.get("section.chunk_role") == "parent_window"
    ):
        score *= _PARENT_WINDOW_BONUS
    if ev.metadata.get("_hyde_fallback"):
        score *= _HYDE_PENALTY
    if ev.metadata.get("_noise_downgraded"):
        score *= ev.metadata.get("_noise_downgrade_factor", _NOISE_DOWNGRADE_PENALTY)
    return score


def fuse_evidence(
    text_evidences: list[TextEvidence] | None = None,
    query: str = "",
    max_tokens: int = settings.CONTEXT_TOKEN_BUDGET,
    depth: str = "standard",
) -> FusedEvidence:
    """把逐条文本证据融合成 `FusedEvidence`。

    ★ 这里**曾经**还有三条输入：`kg_evidences`（知识图谱证据）、`agent_evidences`、
    `student_profile`。三者在生产链路里**恒为空**，已于 2026-09-23 随 KG 遗留一起移除：

    - `kg_evidences` / `agent_evidences`：`retriever.aretrieve_evidence` 从不传值，
      且 KG 本体早已下线（原 `KGEvidence` 的 docstring 自己写着「KG 已移除」）；
    - `student_profile`：三个调用方（`agents/tools.py`、`evaluation/adapters.py`、
      `evaluation/retrieval_gate.py`）都没传，恒为 `""`。

    **移除是行为等价的**，逐项核对过：
    · `_extract_kg_terms([])` 恒返回空集 → `_score_text_evidence` 里的 KG 加权分支
      （`if kg_terms:`）从不执行 → 删掉不影响任何排序；
    · `kg_tokens` / `profile_tokens` 恒为 0 → `doc_budget` 由
      `max(1000, max_tokens - 0 - 0)` 化简为 `max(1000, max_tokens)`，逐字等价；
    · `parts` 里的 `if kg_text:` / `if profile:` 恒为假 → 最终 `final_context` 不变；
    · `sources` 的 KG 兜底 `if not sources: for ev in kg_evidences` 对空列表是空转。
    """
    text_evidences = text_evidences or []
    if not max_tokens:
        max_tokens = settings.CONTEXT_TOKEN_BUDGET

    deduped: dict[str, TextEvidence] = {}
    for ev in text_evidences:
        key = _content_key(ev)
        existing = deduped.get(key)
        if existing is None:
            deduped[key] = ev
            continue
        if _score_text_evidence(ev) > _score_text_evidence(existing):
            deduped[key] = ev

    ranked = sorted(
        deduped.values(),
        key=lambda ev: _score_text_evidence(ev),
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

    # 文档预算。原式为 `max(1000, max_tokens - kg_tokens - profile_tokens)`，
    # 而 kg_tokens / profile_tokens 恒为 0（KG 与 student_profile 都已移除）→ 逐字等价。
    doc_budget = max(1000, max_tokens)

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
            even_idx = list(range(0, n, 2))  # [0, 2, 4, ...]
            odd_idx = list(range(1, n, 2))  # [1, 3, 5, ...]
            odd_idx.reverse()  # [5, 3, 1, ...]
            interleaved_indices = even_idx + odd_idx
            interleaved = [selected_texts[i] for i in interleaved_indices]
        else:
            interleaved = selected_texts

        parts.append(interleaved[0][1])
        parts.extend(text for _, text in interleaved[1:])

    sources = []
    seen_sources = set()
    for ev, _ in selected_texts:
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
            query[:30],
            used_token_budget,
            max_tokens,
        )
    elif used_token_budget > max_tokens * 0.9:
        logger.info(
            "Evidence fusion budget query=%s text=%d/%d tokens=%d/%d diversity=%.3f",
            query[:30],
            len(selected_texts),
            len(text_evidences),
            used_token_budget,
            max_tokens,
            diversity_score,
        )

    fused = FusedEvidence(
        text_evidences=[ev for ev, _ in selected_texts],
        final_context=final_context,
        sources=sources,
        used_token_budget=used_token_budget,
        diversity_score=round(diversity_score, 6),
        metadata={
            "input_text_evidence_count": len(text_evidences),
            "deduped_text_evidence_count": len(deduped),
            "selected_text_evidence_count": len(selected_texts),
            "doc_token_budget": doc_budget,
            "max_tokens": max_tokens,
            "retrieval_depth": depth,
        },
    )

    return fused


def fuse_documents(
    docs: list[Document],
    query: str = "",
    max_tokens: int = settings.CONTEXT_TOKEN_BUDGET,
    depth: str = "standard",
) -> FusedEvidence:
    """把检索到的 Document 融合成 `FusedEvidence`（同步版）。"""
    return fuse_evidence(
        text_evidences=[text_evidence_from_document(doc) for doc in docs],
        query=query,
        max_tokens=max_tokens,
        depth=depth,
    )


async def afuse_documents(
    docs: list[Document],
    query: str = "",
    max_tokens: int = settings.CONTEXT_TOKEN_BUDGET,
    depth: str = "standard",
) -> FusedEvidence:
    """`fuse_documents` 的异步版（当前实现同步完成，签名保持异步以适配调用方）。"""
    return fuse_evidence(
        text_evidences=[text_evidence_from_document(doc) for doc in docs],
        query=query,
        max_tokens=max_tokens,
        depth=depth,
    )
