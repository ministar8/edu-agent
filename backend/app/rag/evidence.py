from __future__ import annotations

import hashlib
import json
from typing import Any

from langchain_core.documents import Document
from pydantic import BaseModel, Field


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
            return [p.strip() for p in text.replace("，", ",").split(",") if p.strip()]
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
    import logging
    logger = logging.getLogger(__name__)
    try:
        from app.rag.knowledge_graph import get_kg_manager

        kg = get_kg_manager()

        # 1. Resolve topic (with optional category disambiguation)
        resolved = kg.resolve_topic(query, category=category)
        if not resolved:
            return None

        nodes: list[str] = [resolved]
        edges: list[dict[str, Any]] = []
        path_list: list[list[str]] = []

        # 2. Prerequisites (n-hop, incoming: pre -> resolved)
        prereqs = kg.get_prerequisites(resolved, depth=max_depth)
        for p in prereqs:
            name = str(p.get("name", "")).strip()
            if name and name not in nodes:
                nodes.append(name)
            if name:
                edges.append({
                    "source": name,
                    "target": resolved,
                    "relation": "PREREQUISITE_OF",
                })

        # 3. Next topics (n-hop, outgoing: resolved -> next)
        next_topics = kg.get_next_topics(resolved, depth=max_depth)
        for n in next_topics:
            name = str(n.get("name", "")).strip()
            if name and name not in nodes:
                nodes.append(name)
            if name:
                edges.append({
                    "source": resolved,
                    "target": name,
                    "relation": "PREREQUISITE_OF",
                })

        # 4. Learning paths (multi-hop reverse traversal)
        raw_paths = kg.get_learning_path(resolved, max_depth=max_depth)
        for path in raw_paths:
            names = [
                str(step.get("name", "")).strip()
                for step in path
                if str(step.get("name", "")).strip()
            ]
            if names:
                path_list.append(names)
                for name in names:
                    if name not in nodes:
                        nodes.append(name)

        # 5. Serialize for LLM context
        parts = [f"Topic: {resolved}"]
        if prereqs:
            pre_names = [
                str(p.get("name", "")) for p in prereqs if p.get("name")
            ]
            if pre_names:
                parts.append(
                    f"Prerequisites: {' -> '.join(pre_names)} -> [{resolved}]"
                )
        if next_topics:
            next_names = [
                str(n.get("name", "")) for n in next_topics if n.get("name")
            ]
            if next_names:
                parts.append(
                    f"Next topics: [{resolved}] -> {' -> '.join(next_names)}"
                )
        if path_list:
            for p in path_list:
                parts.append(f"Learning path: {' -> '.join(p)}")

        serialized = "[KG Related Info]\n" + "\n".join(parts)

        confidence = 0.7

        return KGEvidence(
            evidence_id=_stable_id("kg", resolved),
            serialized=serialized,
            nodes=nodes,
            edges=edges,
            paths=path_list,
            confidence=confidence,
            source="knowledge_graph",
        )
    except Exception as e:
        logger.debug("kg_evidence_from_query failed (non-fatal): %s", e)
        return None


# -- Formatting utilities (shared by fusion.py / compressor.py) --

def format_text_evidence(index: int, ev: TextEvidence) -> str:
    path_info = f" [{ev.section_path}]" if ev.section_path else ""
    return f"[Source {index}: {ev.source}{path_info}]\n{ev.content}"


def format_kg_evidence(ev: KGEvidence) -> str:
    return ev.serialized
