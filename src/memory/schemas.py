"""长期记忆文档模型：带 schema_version、UTC 时间戳与上下文锚点。

Store 里是 JSON；改字段时保持向后兼容（新字段给默认）。
topic 一律经 `memory.topics.normalize_topic` 后再写入。
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

SCHEMA_VERSION = 1

EpisodeType = Literal["grade", "question", "chat_topic"]
AgentPath = Literal[
    "chat_grade",
    "api_grade",
    "chat_question",
    "api_question",
    "chat_topic",
    "other",
]


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def parse_iso(value: str) -> datetime | None:
    """解析 ISO 时间；非法或空返回 None；naive 按 UTC。"""
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


def excerpt(text: str, limit: int = 120) -> str:
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


class StudentProfile(BaseModel):
    """跨会话学生画像（语义记忆，单文档持续更新）。"""

    schema_version: int = Field(default=SCHEMA_VERSION)
    updated_at: str = Field(default_factory=utc_now_iso)
    level: Literal["unknown", "beginner", "intermediate", "advanced"] = "unknown"
    weak_topics: list[str] = Field(default_factory=list)
    preferred_style: str = Field(default="", description="如「极简要点」")
    notes: str = Field(default="", description="自由备注，勿塞敏感凭证")

    def with_updates(self, **fields: Any) -> StudentProfile:
        data = self.model_dump()
        data.update(fields)
        data["schema_version"] = SCHEMA_VERSION
        data["updated_at"] = utc_now_iso()
        return StudentProfile.model_validate(data)


class Episode(BaseModel):
    """单条情节记忆；question ↔ grade 靠显式外键关联，禁止只靠 topic+时间邻近。"""

    schema_version: int = Field(default=SCHEMA_VERSION)
    at: str = Field(default_factory=utc_now_iso)
    type: EpisodeType
    topic: str = Field(default="", max_length=200, description="须为 normalize_topic 结果")
    score: float | None = Field(default=None, description="批改得分 0-100，非批改为 None")
    error_analysis: str = Field(default="", max_length=500)
    thread_id: str = Field(default="")
    run_id: str = Field(default="")
    stem_excerpt: str = Field(default="", max_length=200, description="题干截断，便于回溯")
    knowledge_points: list[str] = Field(default_factory=list)
    agent_path: AgentPath = "other"
    # ── 显式外键（闭环关联）────────────────────────
    batch_id: str = Field(
        default="", description="出题批次 ID（与 API QuestionResponse.batch_id 对齐）"
    )
    question_id: str = Field(default="", description="单题 ID（可选）")
    ref_episode_id: str = Field(
        default="",
        description="grade episode → 所批改的 question episode id（显式外键）",
    )
    meta: dict[str, Any] = Field(default_factory=dict)
