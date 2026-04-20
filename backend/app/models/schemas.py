from __future__ import annotations

from pydantic import BaseModel


class ChatRequest(BaseModel):
    message: str
    thread_id: str | None = "default"


class ChatResponse(BaseModel):
    answer: str
    agent_name: str
    sources: list[str] = []
    agent_steps: list[dict] = []


class KnowledgeInfo(BaseModel):
    id: str
    name: str
    category: str
    chunk_count: int
    doc_count: int


class AgentStep(BaseModel):
    agent_name: str
    action: str
    input_data: str
    output_data: str
    timestamp: float


class RAGProcessInfo(BaseModel):
    query: str
    rewritten_query: str | None = None
    retrieved_chunks: list[dict] = []
    reranked_chunks: list[dict] = []
    final_context: str = ""


class KGNode(BaseModel):
    name: str
    category: str = "general"
    description: str = ""


class KGEdge(BaseModel):
    source: str
    target: str
    relation: str = "RELATED_TO"


class KGImportRequest(BaseModel):
    nodes: list[KGNode]
    edges: list[KGEdge]
