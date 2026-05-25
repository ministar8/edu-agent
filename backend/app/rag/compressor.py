"""CRAG 风格上下文压缩器

对 Fusion 后的证据做相关性评估与压缩：
1. LLM 批量判定每条证据与查询的相关性（relevant / partial / irrelevant）
2. 剔除 irrelevant，截断 partial 为仅相关片段
3. LLM 不可用时回退到规则评分（score + 关键词重叠）

配置项：CRAG_COMPRESS_ENABLED, CRAG_SCORE_THRESHOLD, CRAG_MAX_EVAL_BATCH
"""

from __future__ import annotations

import logging
import re
from enum import IntEnum

from app.rag.evidence import FusedEvidence, TextEvidence
from app.rag.rag_utils import estimate_tokens, get_llm

logger = logging.getLogger(__name__)


class Relevance(IntEnum):
    IRRELEVANT = 0
    PARTIAL = 1
    RELEVANT = 2


# ── 规则回退 ──────────────────────────────────────────

def _keyword_overlap(query: str, content: str) -> float:
    """计算查询关键词在内容中的命中比例（0~1）"""
    q_chars = set(query) - {" ", "？", "？", "的", "了", "是", "在", "和", "与", "有", "不"}
    if not q_chars:
        return 0.0
    c_chars = set(content)
    hit = q_chars & c_chars
    return len(hit) / len(q_chars)


def _primary_score(ev: TextEvidence) -> float:
    if "rerank_score" in ev.metadata:
        return float(ev.rerank_score or 0.0)
    if "recall_score" in ev.metadata:
        return float(ev.recall_score or 0.0)
    return float(ev.score or 0.0)


def _rule_relevance(ev: TextEvidence, query: str) -> Relevance:
    """纯规则判定相关性（LLM 不可用时的回退）"""
    score = _primary_score(ev)
    overlap = _keyword_overlap(query, ev.content)

    if score >= 0.5 and overlap >= 0.4:
        return Relevance.RELEVANT
    if score >= 0.3 or overlap >= 0.5:
        return Relevance.PARTIAL
    if score < 0.1 and overlap < 0.2:
        return Relevance.IRRELEVANT
    return Relevance.PARTIAL


# ── LLM 批量评估 ──────────────────────────────────────

_EVAL_PROMPT = """请判断以下每条检索内容与学生问题的相关性。
对每条内容输出一个标签：relevant（高度相关）、partial（部分相关）、irrelevant（不相关）。

学生问题：{query}

{evidence_list}

请严格按照以下格式输出，每行一条，不要添加其他内容：
1: relevant
2: partial
3: irrelevant
..."""

_LABEL_MAP = {
    "relevant": Relevance.RELEVANT,
    "partial": Relevance.PARTIAL,
    "irrelevant": Relevance.IRRELEVANT,
}

_EVAL_RESULT_RE = re.compile(r"(\d+)\s*[:：.）)]\s*(relevant|partial|irrelevant)", re.IGNORECASE)


def _llm_batch_evaluate(
    evidences: list[TextEvidence],
    query: str,
    max_batch: int = 8,
) -> list[Relevance]:
    """LLM 批量评估证据相关性

    Returns:
        与 evidences 等长的 Relevance 列表；LLM 失败时回退到规则
    """
    n = len(evidences)
    results: list[Relevance | None] = [None] * n

    for batch_start in range(0, n, max_batch):
        batch = evidences[batch_start:batch_start + max_batch]
        batch_n = len(batch)

        lines = []
        for i, ev in enumerate(batch, 1):
            snippet = ev.content[:300].replace("\n", " ")
            lines.append(f"{i}. [{ev.source}] {snippet}")

        evidence_list = "\n".join(lines)
        prompt = _EVAL_PROMPT.format(query=query, evidence_list=evidence_list)

        try:
            llm = get_llm(streaming=False, temperature=0.0)
            raw = llm.invoke(prompt)
            text = raw.content if hasattr(raw, "content") else str(raw)
            text = str(text or "")

            parsed: dict[int, Relevance] = {}
            for m in _EVAL_RESULT_RE.finditer(text):
                idx = int(m.group(1))
                label = m.group(2).lower()
                if 1 <= idx <= batch_n and label in _LABEL_MAP:
                    parsed[idx] = _LABEL_MAP[label]

            for i in range(batch_n):
                local_idx = i + 1
                if local_idx in parsed:
                    results[batch_start + i] = parsed[local_idx]

        except Exception as e:
            logger.warning("CRAG LLM evaluate batch failed: %s", e)

    # 未被 LLM 判定的位置用规则回退
    for i in range(n):
        if results[i] is None:
            results[i] = _rule_relevance(evidences[i], query)

    return results  # type: ignore[return-value]


# ── 压缩：提取相关片段 ────────────────────────────────

_EXTRACT_PROMPT = """从以下检索内容中，仅提取与学生问题直接相关的句子或段落。
不要添加任何解释，只输出相关原文片段。如果没有任何相关内容，输出空行。

学生问题：{query}

检索内容：
{content}

相关片段："""


def _llm_extract_relevant(content: str, query: str) -> str:
    """LLM 提取内容中与查询相关的片段"""
    try:
        llm = get_llm(streaming=False, temperature=0.0)
        prompt = _EXTRACT_PROMPT.format(query=query, content=content[:1500])
        raw = llm.invoke(prompt)
        text = raw.content if hasattr(raw, "content") else str(raw)
        text = str(text or "").strip()
        if text and len(text) < len(content):
            return text
        return content
    except Exception as e:
        logger.warning("CRAG LLM extract failed: %s", e)
        return content


def _rule_extract_relevant(content: str, query: str) -> str:
    """规则提取：保留包含查询关键词的句子"""
    q_terms = set(re.findall(r"[\u4e00-\u9fffA-Za-z0-9]{2,}", query))
    if not q_terms:
        return content

    sentences = re.split(r"(?<=[。！？；\n])", content)
    kept = []
    for s in sentences:
        s = s.strip()
        if not s:
            continue
        s_terms = set(re.findall(r"[\u4e00-\u9fffA-Za-z0-9]{2,}", s))
        if q_terms & s_terms:
            kept.append(s)

    if not kept:
        return content
    return "".join(kept)


# ── 主入口 ─────────────────────────────────────────────

def compress_evidence(
    fused: FusedEvidence,
    query: str = "",
    use_llm: bool = True,
    max_eval_batch: int = 8,
    score_threshold: float = 0.15,
    student_profile: str = "",
    max_tokens: int = 0,
    depth: str = "standard",
) -> FusedEvidence:
    """对 FusedEvidence 做相关性压缩

    流程：
    1. 评估每条 text_evidence 的相关性
    2. 剔除 irrelevant
    3. 对 partial 做内容提取压缩
    4. 重新计算 final_context 和 sources

    Args:
        fused: Fusion 层输出的 FusedEvidence
        query: 原始查询
        use_llm: 是否使用 LLM 评估（False 时纯规则）
        max_eval_batch: LLM 批量评估每批最大条数
        score_threshold: 规则回退时低于此分数直接判 irrelevant

    Returns:
        压缩后的 FusedEvidence
    """
    from app.config import settings
    from app.rag.fusion import fuse_evidence

    if not settings.CRAG_COMPRESS_ENABLED:
        return fused
    if not max_tokens:
        max_tokens = settings.CONTEXT_TOKEN_BUDGET

    text_evs = fused.text_evidences
    if not text_evs:
        return fused

    # ── Depth-gated compression ──
    # shallow: skip LLM, rule-filter only
    # standard: lightweight CRAG (top-5 LLM eval + rule extraction for partial)
    # deep/code: full CRAG (current behavior)

    if depth == "shallow":
        # Rule-only: drop low-score evidence, no LLM calls
        kept = [ev for ev in text_evs if _primary_score(ev) >= 0.1]
        if len(kept) < max(3, len(text_evs) // 3):
            kept = text_evs  # safety floor
        compressed = fuse_evidence(
            text_evidences=kept,
            kg_evidences=fused.kg_evidences,
            agent_evidences=fused.agent_evidences,
            query="", student_profile=student_profile, max_tokens=max_tokens,
        )
        logger.info("CRAG shallow: %d -> %d evidence (rule-filter only)", len(text_evs), len(kept))
        return FusedEvidence(
            text_evidences=compressed.text_evidences,
            kg_evidences=compressed.kg_evidences,
            agent_evidences=compressed.agent_evidences,
            final_context=compressed.final_context,
            sources=compressed.sources,
            used_token_budget=compressed.used_token_budget,
            diversity_score=compressed.diversity_score,
            metadata={**fused.metadata, "crag_stats": {"shallow_kept": len(kept), "shallow_dropped": len(text_evs) - len(kept)}},
        )

    # Step 1: Evaluate relevance
    if depth == "standard":
        # Lightweight: only evaluate top-5 by score, rest keep as-is
        top_n = min(5, len(text_evs))
        sorted_evs = sorted(text_evs, key=lambda ev: _primary_score(ev), reverse=True)
        candidates = sorted_evs[:top_n]
        rest = sorted_evs[top_n:]
        relevances = _llm_batch_evaluate(candidates, query, max_batch=4)
        # pad relevances for rest (treat as RELEVANT = keep)
        relevances += [Relevance.RELEVANT] * len(rest)
        # rebuild text_evs in original order for zip
        eval_map = {}
        for i, ev in enumerate(candidates):
            eval_map[id(ev)] = relevances[i]
        n = len(text_evs)
        relevances_ordered = [eval_map.get(id(ev), Relevance.RELEVANT) for ev in text_evs]
        use_llm_extract = False  # standard: rule extraction for partial (save token)
    elif use_llm:
        relevances_ordered = _llm_batch_evaluate(text_evs, query, max_eval_batch)
        use_llm_extract = True
    else:
        relevances_ordered = [_rule_relevance(ev, query) for ev in text_evs]
        use_llm_extract = False

    relevances = relevances_ordered

    # Step 2: 过滤 + 压缩
    compressed_evs: list[TextEvidence] = []
    stats = {"relevant": 0, "partial": 0, "irrelevant_removed": 0, "partial_compressed": 0}

    for i, (ev, rel) in enumerate(zip(text_evs, relevances)):
        if rel != Relevance.RELEVANT and _primary_score(ev) < score_threshold:
            rel = Relevance.IRRELEVANT
            relevances[i] = rel
        if rel == Relevance.RELEVANT:
            compressed_evs.append(ev)
            stats["relevant"] += 1
        elif rel == Relevance.PARTIAL:
            # 对 partial 证据做内容提取
            original_content = ev.content
            if use_llm_extract and estimate_tokens(original_content) > 200:
                compressed_content = _llm_extract_relevant(original_content, query)
            else:
                compressed_content = _rule_extract_relevant(original_content, query)

            if compressed_content and compressed_content != original_content:
                ev = ev.model_copy(update={"content": compressed_content})
                stats["partial_compressed"] += 1
            compressed_evs.append(ev)
            stats["partial"] += 1
        else:
            # irrelevant → 剔除
            stats["irrelevant_removed"] += 1

    # 安全兜底：至少保留 MIN_KEEP 条证据，避免过度压缩导致上下文不足
    _MIN_KEEP = max(3, len(text_evs) // 3)
    if len(compressed_evs) < _MIN_KEEP and text_evs:
        # 按分数排序被剔除的 irrelevant，回补最高分的
        removed_evs = [(ev, rel) for ev, rel in zip(text_evs, relevances) if rel == Relevance.IRRELEVANT]
        removed_evs.sort(key=lambda x: _primary_score(x[0]), reverse=True)
        for ev, _ in removed_evs:
            if len(compressed_evs) >= _MIN_KEEP:
                break
            compressed_evs.append(ev)
            stats["irrelevant_removed"] -= 1

    compressed = fuse_evidence(
        text_evidences=compressed_evs,
        kg_evidences=fused.kg_evidences,
        agent_evidences=fused.agent_evidences,
        query="",
        student_profile=student_profile,
        max_tokens=max_tokens,
    )

    logger.info(
        "CRAG compress query=%s relevant=%d partial=%d removed=%d compressed=%d",
        query[:30], stats["relevant"], stats["partial"],
        stats["irrelevant_removed"], stats["partial_compressed"],
    )

    return FusedEvidence(
        text_evidences=compressed.text_evidences,
        kg_evidences=compressed.kg_evidences,
        agent_evidences=compressed.agent_evidences,
        final_context=compressed.final_context,
        sources=compressed.sources,
        used_token_budget=compressed.used_token_budget,
        diversity_score=compressed.diversity_score,
        metadata={
            **fused.metadata,
            "crag_stats": stats,
            "crag_relevances": [r.name for r in relevances],
        },
    )
