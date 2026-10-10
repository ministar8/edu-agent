from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from langchain_core.documents import Document
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class TextEvidence(BaseModel):
    evidence_id: str = Field(description="evidence unique ID")
    content: str = Field(description="evidence body text")
    source: str = Field(default="unknown", description="source file or data source")
    score: float = Field(
        default=0.0,
        description=(
            "★ B1（§1.5 R4）契约：相似度语义，**数值越高越相似**（距离→相似度只在唯一换算点 "
            "`embeddings.similarity_from_distance`）。top-up 路径由 `layer_recall._doc_to_evidence` "
            "直接落向量相似度；主路径取 rerank/recall(RRF)——均「越高越好」，排序一律 reverse=True。"
        ),
    )
    rerank_score: float = Field(default=0.0)
    recall_score: float = Field(default=0.0)
    collection: str = Field(default="")
    section_path: str = Field(default="")
    chunk_id: str = Field(default="")
    parent_id: str = Field(default="")
    knowledge_points: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class FusedEvidence(BaseModel):
    text_evidences: list[TextEvidence] = Field(default_factory=list)
    final_context: str = Field(default="")
    sources: list[str] = Field(default_factory=list)
    used_token_budget: int = Field(default=0)
    diversity_score: float = Field(default=0.0)
    metadata: dict[str, Any] = Field(default_factory=dict)


def _stable_id(prefix: str, text: str) -> str:
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}_{digest}"


def parse_knowledge_points(value: Any) -> list[str]:
    """把 metadata 里的 `knowledge_points` 解析成名字列表（JSON 字符串 / list / 逗号分隔都吃）。

    ★ 公开名（2026-10-08 D12 选 (B) 之后）：评测侧 `task_eval.retrieval_probe` 需要在
      `EvidenceDoc.knowledge_points` 为空时**从 metadata 兜底解析**（#27：layer top-up 那条
      路径写死成 `[]`，索引里明明带着标签）。原先这是 `_` 私有函数，跨模块调用就是耦合
      —— 而「唯一正确的解析方式」正是必须共享的那一份，私有名只会诱导读的人另写一套。
    """
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
    recall_score = (
        float(meta["recall_score"]) if "recall_score" in meta else (fallback_score or 0.0)
    )
    rerank_score = float(meta["rerank_score"]) if "rerank_score" in meta else 0.0
    score = (
        rerank_score
        if rerank_score
        else (recall_score if recall_score else (fallback_score or 0.0))
    )
    source = str(
        meta.get("source_file") or meta.get("source") or meta.get("source_name") or "unknown"
    )
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
        # 唯一写入方是 `knowledge_tagger`（写扁平名 `knowledge_points`，JSON 字符串）。
        # 此处曾回退读 `section.knowledge_points` —— 那是**幽灵字段**（无任何写入方），
        # 2026-09-24 移除，避免"看起来有两条来源"的错觉。
        knowledge_points=parse_knowledge_points(meta.get("knowledge_points")),
        metadata=meta,
    )


# -- Formatting utilities (shared by fusion.py) --


def format_text_evidence(index: int, ev: TextEvidence) -> str:
    path_info = f" [{ev.section_path}]" if ev.section_path else ""
    return f"[Source {index}: {ev.source}{path_info}]\n{ev.content}"
