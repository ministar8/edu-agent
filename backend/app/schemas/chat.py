from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str
    thread_id: str | None = "default"


class ChatResponse(BaseModel):
    answer: str
    agent_name: str
    sources: list[str] = Field(default_factory=list)
    agent_steps: list[dict] = Field(default_factory=list)


class AgentStep(BaseModel):
    agent_name: str
    action: str
    input_data: str
    output_data: str
    timestamp: float


# ── 对话历史 schemas ──────────────────────────


class MessageItem(BaseModel):
    id: int
    role: str
    content: str
    agent_name: str | None = None
    sources: list[str] = Field(default_factory=list)
    governance: dict | None = None
    created_at: datetime


class ConversationItem(BaseModel):
    id: int
    thread_id: str
    title: str
    summary: str = ""
    created_at: datetime
    updated_at: datetime | None = None
    message_count: int = 0


class ConversationDetail(BaseModel):
    id: int
    thread_id: str
    title: str
    summary: str = ""
    created_at: datetime
    updated_at: datetime | None = None
    messages: list[MessageItem] = Field(default_factory=list)
