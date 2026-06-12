from __future__ import annotations

from pydantic import BaseModel, Field


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
