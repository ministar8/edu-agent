from __future__ import annotations

import logging
from collections import defaultdict

from langchain_core.documents import Document

from core.settings import settings
from rag.common.rag_utils import estimate_tokens
from rag.retrieval.evidence import (
    FusedEvidence,
    TextEvidence,
    format_text_evidence,
    text_evidence_from_document,
)

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


def _dedup_keep_best(evs: list[TextEvidence]) -> dict[str, TextEvidence]:
    """按内容键去重，同一键保留 `_score_text_evidence` 更高的一条。"""
    deduped: dict[str, TextEvidence] = {}
    for ev in evs:
        key = _content_key(ev)
        existing = deduped.get(key)
        if existing is None or _score_text_evidence(ev) > _score_text_evidence(existing):
            deduped[key] = ev
    return deduped


def _diversify_by_source(ranked: list[TextEvidence]) -> list[TextEvidence]:
    """单一来源最多保留 `_MAX_PER_SOURCE` 条，溢出的按原序排到末尾。"""
    source_counts: defaultdict[str, int] = defaultdict(int)
    diversified: list[TextEvidence] = []
    overflow: list[TextEvidence] = []
    for ev in ranked:
        if source_counts[ev.source] < _MAX_PER_SOURCE:
            diversified.append(ev)
            source_counts[ev.source] += 1
        else:
            overflow.append(ev)
    return diversified + overflow


def _select_within_budget(
    ranked: list[TextEvidence], doc_budget: int
) -> list[tuple[TextEvidence, str]]:
    """在 `doc_budget` token 内自顶向下选证据，末条可按剩余额度截断。"""
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
    return selected_texts


def _interleave_head_tail(
    selected: list[tuple[TextEvidence, str]],
) -> list[tuple[TextEvidence, str]]:
    """首尾效应优化：最高相关证据放首尾、次相关放中间。

    原序 [1,2,3,4,5] → [1,3,5,4,2]；不足 4 条时保持原序。
    """
    n = len(selected)
    if n < 4:
        return selected
    even_idx = list(range(0, n, 2))  # [0, 2, 4, ...]
    odd_idx = list(range(1, n, 2))  # [1, 3, 5, ...]
    odd_idx.reverse()  # [5, 3, 1, ...]
    return [selected[i] for i in even_idx + odd_idx]


def _collect_sources(selected: list[tuple[TextEvidence, str]]) -> list[str]:
    """按选中顺序收集去重后的来源名。"""
    sources: list[str] = []
    seen: set[str] = set()
    for ev, _ in selected:
        if ev.source and ev.source not in seen:
            sources.append(ev.source)
            seen.add(ev.source)
    return sources


def _source_diversity(selected: list[tuple[TextEvidence, str]]) -> float:
    """多样性 = 去重来源数 / 选中证据数（无证据时为 0）。"""
    if not selected:
        return 0.0
    return len({ev.source for ev, _ in selected if ev.source}) / len(selected)


def _apply_final_budget(
    final_context: str,
    query: str,
    selected_count: int,
    input_count: int,
    max_tokens: int,
    diversity_score: float,
) -> tuple[str, int]:
    """最终上下文超预算时截断并记录；返回 (上下文, 实际 token 数)。

    if/elif 只对**截断前**的 token 数判定一次 —— 与拆分前逐字一致（不能把判定挪到截断后）。
    """
    used = estimate_tokens(final_context)
    if used > max_tokens:
        final_context = _truncate_to_tokens(final_context, max_tokens)
        used = estimate_tokens(final_context)
        logger.info("Evidence fusion truncated query=%s tokens=%d/%d", query[:30], used, max_tokens)
    elif used > max_tokens * 0.9:
        logger.info(
            "Evidence fusion budget query=%s text=%d/%d tokens=%d/%d diversity=%.3f",
            query[:30],
            selected_count,
            input_count,
            used,
            max_tokens,
            diversity_score,
        )
    return final_context, used


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
    - `student_profile`：三个调用方（`agents/tools.py`、`evaluation/ragas/adapters.py`、
      `evaluation/gates/retrieval_gate/`）都没传，恒为 `""`。

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

    deduped = _dedup_keep_best(text_evidences)
    ranked = _diversify_by_source(sorted(deduped.values(), key=_score_text_evidence, reverse=True))

    # 文档预算。原式为 `max(1000, max_tokens - kg_tokens - profile_tokens)`，
    # 而 kg_tokens / profile_tokens 恒为 0（KG 与 student_profile 都已移除）→ 逐字等价。
    doc_budget = max(1000, max_tokens)

    selected_texts = _select_within_budget(ranked, doc_budget)
    ordered = _interleave_head_tail(selected_texts)
    final_context = "\n\n".join(text for _, text in ordered)
    sources = _collect_sources(selected_texts)
    diversity_score = _source_diversity(selected_texts)

    final_context, used_token_budget = _apply_final_budget(
        final_context, query, len(selected_texts), len(text_evidences), max_tokens, diversity_score
    )

    return FusedEvidence(
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


async def afuse_documents(
    docs: list[Document],
    query: str = "",
    max_tokens: int = settings.CONTEXT_TOKEN_BUDGET,
    depth: str = "standard",
) -> FusedEvidence:
    """把检索到的 Document 融合成 `FusedEvidence`（异步签名，实现同步完成）。"""
    return fuse_evidence(
        text_evidences=[text_evidence_from_document(doc) for doc in docs],
        query=query,
        max_tokens=max_tokens,
        depth=depth,
    )
