from __future__ import annotations

import hashlib
import json
import logging
import re
import socket
import time
from typing import Any
from urllib.parse import urlparse

from langchain_core.documents import Document
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

_MAX_KG_TOPICS = 3
_MAX_KG_NODES = 24
_MAX_KG_EDGES = 32
_MAX_KG_PATHS = 6
_KG_EVIDENCE_CACHE_TTL = 300
_KG_EVIDENCE_CACHE_MAX = 128
_KG_EVIDENCE_CACHE: dict[tuple[str, str, int], tuple[float, KGEvidence | None]] = {}
_KG_FAILURE_COOLDOWN = 60
_KG_FAILURE_UNTIL = 0.0
_KG_TOPIC_STOP_WORDS = {
    "什么", "是什么", "怎么", "如何", "为什么", "解释", "说明", "介绍",
    "解释一下", "说明一下", "关系", "联系", "区别", "差异", "不同", "异同",
    "核心", "概念", "核心概念", "作用", "应用", "特点", "对比", "比较",
    "控制",
}


class TextEvidence(BaseModel):
    evidence_id: str = Field(description="evidence unique ID")
    content: str = Field(description="evidence body text")
    source: str = Field(default="unknown", description="source file or data source")
    score: float = Field(default=0.0)
    rerank_score: float = Field(default=0.0)
    recall_score: float = Field(default=0.0)
    collection: str = Field(default="")
    section_path: str = Field(default="")
    chunk_id: str = Field(default="")
    parent_id: str = Field(default="")
    knowledge_points: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class KGEvidence(BaseModel):
    evidence_id: str = Field(description="KG evidence unique ID")
    serialized: str = Field(description="serialized graph evidence text")
    nodes: list[str] = Field(default_factory=list, description="related nodes")
    edges: list[dict[str, Any]] = Field(default_factory=list, description="related edges")
    paths: list[list[str]] = Field(default_factory=list, description="path evidence")
    confidence: float = Field(default=0.5, ge=0.0, le=1.0, description="KG evidence confidence")
    source: str = Field(default="knowledge_graph", description="evidence source")
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentEvidence(BaseModel):
    evidence_id: str = Field(description="Agent evidence unique ID")
    agent_name: str = Field(description="agent that produced the evidence")
    content: str = Field(description="agent output content")
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class FusedEvidence(BaseModel):
    text_evidences: list[TextEvidence] = Field(default_factory=list)
    kg_evidences: list[KGEvidence] = Field(default_factory=list)
    agent_evidences: list[AgentEvidence] = Field(default_factory=list)
    final_context: str = Field(default="")
    sources: list[str] = Field(default_factory=list)
    used_token_budget: int = Field(default=0)
    diversity_score: float = Field(default=0.0)
    metadata: dict[str, Any] = Field(default_factory=dict)


def _stable_id(prefix: str, text: str) -> str:
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}_{digest}"


def _parse_knowledge_points(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v) for v in value if str(v).strip()]
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        try:
            parsed = json.loads(text)
            if isinstance(parsed, list):
                return [str(v) for v in parsed if str(v).strip()]
        except json.JSONDecodeError:
            pass
        return [p.strip() for p in text.replace("，", ",").split(",") if p.strip()]
    return []


def text_evidence_from_document(doc: Document, fallback_score: float = 0.0) -> TextEvidence:
    meta = dict(doc.metadata or {})
    content = doc.page_content or ""
    recall_score = float(meta["recall_score"]) if "recall_score" in meta else (fallback_score or 0.0)
    rerank_score = float(meta["rerank_score"]) if "rerank_score" in meta else 0.0
    score = rerank_score if rerank_score else (recall_score if recall_score else (fallback_score or 0.0))
    source = str(meta.get("source_file") or meta.get("source") or meta.get("source_name") or "unknown")
    chunk_id = str(meta.get("section.chunk_id") or meta.get("chunk_id") or "")
    evidence_seed = chunk_id or f"{source}:{content[:120]}"
    return TextEvidence(
        evidence_id=_stable_id("txt", evidence_seed),
        content=content,
        source=source,
        score=score,
        rerank_score=rerank_score,
        recall_score=recall_score,
        collection=str(meta.get("_collection") or ""),
        section_path=str(meta.get("section.path") or meta.get("heading_path") or ""),
        chunk_id=chunk_id,
        parent_id=str(meta.get("section.parent_id_index") or meta.get("section.id") or ""),
        knowledge_points=_parse_knowledge_points(meta.get("knowledge_points") or meta.get("section.knowledge_points")),
        metadata=meta,
    )


def kg_evidence_from_text(text: str, confidence: float = 0.7) -> KGEvidence | None:
    stripped = (text or "").strip()
    if not stripped:
        return None
    return KGEvidence(
        evidence_id=_stable_id("kg", stripped[:300]),
        serialized=stripped,
        confidence=confidence,
    )


def _dedupe_keep_order(items: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for item in items:
        cleaned = str(item).strip()
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            result.append(cleaned)
    return result


def _extract_kg_topic_candidates(query: str) -> list[str]:
    from app.rag.rag_utils import extract_query_terms, normalize_query_text
    from app.rag.synonyms import SYNONYM_MAP, SYNONYM_MAP_CASEFOLD

    normalized = normalize_query_text(query)
    candidates: list[str] = []

    def _add_candidate(term: str) -> None:
        cleaned = str(term).strip("：:，,。？? ")
        mapped = SYNONYM_MAP.get(cleaned) or SYNONYM_MAP_CASEFOLD.get(cleaned.casefold())
        if len(cleaned) < 2 or cleaned in _KG_TOPIC_STOP_WORDS:
            return
        if not re.search(r"[\u4e00-\u9fff]", cleaned) and cleaned.casefold() == cleaned and not mapped:
            return
        if re.fullmatch(r"[a-z][a-z0-9_./+-]*", cleaned) and not mapped:
            return
        candidates.append(cleaned)
        if mapped and mapped not in _KG_TOPIC_STOP_WORDS:
            candidates.append(mapped)

    relation_parts = re.split(r"(?:和|与|及|以及|、|，|,|\s+vs\s+|\s+VS\s+)", normalized)
    if 2 <= len(relation_parts) <= 4:
        for part in relation_parts:
            cleaned = re.sub(r"^(请|帮我|解释|说明|比较|对比|分析|讲解|一下)+", "", part.strip())
            cleaned = re.sub(r"(的)?(区别|差异|不同|异同|关系|联系|对比|比较)$", "", cleaned.strip())
            _add_candidate(cleaned)

    for term in extract_query_terms(normalized):
        _add_candidate(term)

    for matched in re.findall(r"[\u4e00-\u9fffA-Za-z0-9_+./-]{2,}", normalized):
        if matched == normalized and re.search(r"(区别|差异|不同|异同|关系|联系|对比|比较)", normalized):
            continue
        if matched not in candidates:
            _add_candidate(matched)

    if len(normalized) <= 24 and not re.search(r"(区别|差异|不同|异同|关系|联系|对比|比较)", normalized):
        _add_candidate(normalized)

    return _dedupe_keep_order(candidates)[:8]


def _resolve_kg_topics(kg: Any, query: str, category: str) -> tuple[list[str], list[str]]:
    resolved_topics: list[str] = []
    matched_candidates: list[str] = []
    for candidate in _extract_kg_topic_candidates(query):
        resolved = kg.resolve_topic(candidate, category=category)
        if not resolved and category:
            resolved = kg.resolve_topic(candidate, category="")
        if resolved and resolved not in resolved_topics:
            resolved_topics.append(resolved)
            matched_candidates.append(candidate)
        if len(resolved_topics) >= _MAX_KG_TOPICS:
            break
    return resolved_topics, matched_candidates


def _append_unique_edge(edges: list[dict[str, Any]], source: str, target: str,
                        relation: str = "PREREQUISITE_OF") -> None:
    if not source or not target:
        return
    edge = {"source": source, "target": target, "relation": relation}
    if edge not in edges:
        edges.append(edge)


def _get_cached_kg_evidence(query: str, category: str, max_depth: int) -> KGEvidence | None | bool:
    key = (query, category, max_depth)
    cached = _KG_EVIDENCE_CACHE.get(key)
    if cached is None:
        return False
    ts, value = cached
    if time.time() - ts > _KG_EVIDENCE_CACHE_TTL:
        del _KG_EVIDENCE_CACHE[key]
        return False
    return value


def _set_cached_kg_evidence(query: str, category: str, max_depth: int,
                            value: KGEvidence | None) -> None:
    if len(_KG_EVIDENCE_CACHE) >= _KG_EVIDENCE_CACHE_MAX:
        oldest = min(_KG_EVIDENCE_CACHE, key=lambda k: _KG_EVIDENCE_CACHE[k][0])
        del _KG_EVIDENCE_CACHE[oldest]
    _KG_EVIDENCE_CACHE[(query, category, max_depth)] = (time.time(), value)


def _kg_endpoint_available(timeout: float = 0.25) -> bool:
    try:
        from app.config import settings
        parsed = urlparse(settings.NEO4J_URI)
        host = parsed.hostname
        port = parsed.port or 7687
        if not host:
            return True
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False
    except Exception:
        return True


def kg_evidence_from_query(
    query: str,
    category: str = "",
    max_depth: int = 2,
) -> KGEvidence | None:
    """Query KG for structured evidence (nodes / edges / paths).

    Unlike kg_evidence_from_text(), this function queries the KG Manager directly:
    - Prerequisite topics (incoming PREREQUISITE_OF edges)
    - Next topics (outgoing PREREQUISITE_OF edges)
    - Learning paths (n-hop reverse traversal, default 2-hop)

    Also generates serialized text for LLM context compatibility.

    Args:
        query: Topic name (auto fuzzy-matched via tiered resolver)
        category: Optional category filter for cross-discipline disambiguation
        max_depth: Max hops for learning path (default 2)

    Returns:
        KGEvidence with structured nodes/edges/paths; None if no KG match.
    """
    cached = _get_cached_kg_evidence(query, category, max_depth)
    if cached is not False:
        return cached
    global _KG_FAILURE_UNTIL
    if time.time() < _KG_FAILURE_UNTIL:
        return None
    if not _kg_endpoint_available():
        _KG_FAILURE_UNTIL = time.time() + _KG_FAILURE_COOLDOWN
        _set_cached_kg_evidence(query, category, max_depth, None)
        return None
    try:
        from app.rag.knowledge_graph import get_kg_manager

        kg = get_kg_manager()

        resolved_topics, matched_candidates = _resolve_kg_topics(kg, query, category)
        if not resolved_topics:
            _set_cached_kg_evidence(query, category, max_depth, None)
            return None

        nodes: list[str] = []
        edges: list[dict[str, Any]] = []
        path_list: list[list[str]] = []

        parts = ["[KG Related Info]"]
        for resolved in resolved_topics:
            if resolved not in nodes:
                nodes.append(resolved)

            topic_parts = [f"Topic: {resolved}"]
            prereqs = kg.get_prerequisites(resolved, depth=max_depth)
            pre_names = [str(p.get("name", "")).strip() for p in prereqs if p.get("name")]
            if pre_names:
                topic_parts.append(f"Prerequisites: {' -> '.join(pre_names[:8])} -> [{resolved}]")
            for name in pre_names:
                if name and name not in nodes and len(nodes) < _MAX_KG_NODES:
                    nodes.append(name)
                _append_unique_edge(edges, name, resolved)

            next_topics = kg.get_next_topics(resolved, depth=max_depth)
            next_names = [str(n.get("name", "")).strip() for n in next_topics if n.get("name")]
            if next_names:
                topic_parts.append(f"Next topics: [{resolved}] -> {' -> '.join(next_names[:8])}")
            for name in next_names:
                if name and name not in nodes and len(nodes) < _MAX_KG_NODES:
                    nodes.append(name)
                _append_unique_edge(edges, resolved, name)

            raw_paths = kg.get_learning_path(resolved, max_depth=max_depth)
            for path in raw_paths:
                names = [
                    str(step.get("name", "")).strip()
                    for step in path
                    if str(step.get("name", "")).strip()
                ]
                if names and names not in path_list:
                    path_list.append(names)
                    topic_parts.append(f"Learning path: {' -> '.join(names)}")
                    for name in names:
                        if name not in nodes and len(nodes) < _MAX_KG_NODES:
                            nodes.append(name)

            parts.extend(topic_parts)
            if len(nodes) >= _MAX_KG_NODES:
                break

        nodes = nodes[:_MAX_KG_NODES]
        edges = edges[:_MAX_KG_EDGES]
        path_list = path_list[:_MAX_KG_PATHS]

        if len(resolved_topics) >= 2:
            parts.append("Resolved topics: " + " | ".join(resolved_topics))

        serialized = "\n".join(parts)
        confidence = min(0.95, 0.65 + 0.08 * len(resolved_topics))

        result = KGEvidence(
            evidence_id=_stable_id("kg", "|".join(resolved_topics)),
            serialized=serialized,
            nodes=nodes,
            edges=edges,
            paths=path_list,
            confidence=confidence,
            source="knowledge_graph",
            metadata={
                "resolved_topics": resolved_topics,
                "matched_candidates": matched_candidates,
                "category": category,
                "max_depth": max_depth,
            },
        )
        _set_cached_kg_evidence(query, category, max_depth, result)
        return result
    except Exception as e:
        logger.debug("kg_evidence_from_query failed (non-fatal): %s", e)
        _KG_FAILURE_UNTIL = time.time() + _KG_FAILURE_COOLDOWN
        _set_cached_kg_evidence(query, category, max_depth, None)
        return None


# -- Formatting utilities (shared by fusion.py) --

def format_text_evidence(index: int, ev: TextEvidence) -> str:
    path_info = f" [{ev.section_path}]" if ev.section_path else ""
    return f"[Source {index}: {ev.source}{path_info}]\n{ev.content}"


def format_kg_evidence(ev: KGEvidence) -> str:
    return ev.serialized
