from __future__ import annotations

from pydantic import BaseModel, Field


class KnowledgeInfo(BaseModel):
    id: str
    name: str
    category: str
    chunk_count: int
    doc_count: int


class RAGProcessInfo(BaseModel):
    query: str
    rewritten_query: str | None = None
    retrieved_chunks: list[dict] = Field(default_factory=list)
    reranked_chunks: list[dict] = Field(default_factory=list)
    final_context: str = ""


class KGNode(BaseModel):
    name: str
    category: str = "data_structure"
    description: str = ""


class KGEdge(BaseModel):
    source: str
    target: str
    relation: str = "RELATED_TO"


class KGImportRequest(BaseModel):
    nodes: list[KGNode]
    edges: list[KGEdge]
