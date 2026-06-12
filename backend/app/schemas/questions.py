from __future__ import annotations

from pydantic import BaseModel, Field


class QuestionRequest(BaseModel):
    topic: str
    count: int = Field(default=1, ge=1, le=5)
    difficulty: str = "mixed"  # basic / medium / hard / mixed


class QuestionResponse(BaseModel):
    raw: str
    questions: list[dict] = Field(default_factory=list)
    batch_id: str | None = None


class GradeRequest(BaseModel):
    user_answer: str


class GradeResponse(BaseModel):
    score: float
    feedback: str
    is_wrong: bool
    error_analysis: str = ""


class WrongQuestionItem(BaseModel):
    id: int
    question_type: str | None
    difficulty: float
    stem: str
    standard_answer: str | None
    explanation: str | None
    user_answer: str | None
    grading_score: float | None
    error_analysis: str = ""
    redo_count: int = 0
    created_at: str


class WeakPointPracticeRequest(BaseModel):
    count: int = Field(default=3, ge=1, le=5)
