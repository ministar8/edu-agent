from __future__ import annotations

import asyncio
import logging
import random
import uuid

from sqlalchemy.orm import Session

from app.config import settings
from app.events import TrackingEvent, emit
from app.repositories.question_repository import QuestionRepository
from app.schemas.questions import (
    GradeRequest,
    GradeResponse,
    QuestionRequest,
    QuestionResponse,
    WeakPointPracticeRequest,
    WrongQuestionItem,
)

logger = logging.getLogger(__name__)


class QuestionNotFoundError(Exception):
    pass


class QuestionGenerationError(Exception):
    pass


_DIFFICULTY_LABELS = {
    "basic": "基础",
    "medium": "中等",
    "hard": "困难",
    "mixed": "基础/中等/困难混合",
}

_FALLBACK_TOPICS = [
    ("线性表", "数据结构"),
    ("进程同步", "操作系统"),
    ("Cache映射", "计算机组成原理"),
    ("TCP协议", "计算机网络"),
    ("二叉树", "数据结构"),
    ("死锁", "操作系统"),
    ("指令流水线", "计算机组成原理"),
    ("IP地址", "计算机网络"),
]


class QuestionService:
    def __init__(self, db: Session):
        self.repository = QuestionRepository(db)

    async def generate_questions(self, req: QuestionRequest, user_id: int) -> QuestionResponse:
        count = max(1, min(req.count, 5))
        prompt = build_generation_prompt(req.topic, count, req.difficulty)
        questions, evidences = await self._generate_question_dicts(prompt)
        self._raise_if_generation_error(questions)

        batch_id = persist_generated_questions(
            self.repository,
            questions,
            user_id=user_id,
            conversation_id=None,
            topic=req.topic,
            evidences=evidences,
        )
        return format_question_response(questions, batch_id=batch_id)

    def list_wrong_questions(self, user_id: int, limit: int) -> list[WrongQuestionItem]:
        records = self.repository.list_wrong_questions(user_id, limit)
        return [
            WrongQuestionItem(
                id=record.id,
                question_type=record.question_type,
                difficulty=record.difficulty,
                stem=record.stem,
                standard_answer=record.standard_answer,
                explanation=record.explanation,
                user_answer=record.user_answer,
                grading_score=record.grading_score,
                error_analysis=record.error_analysis or "",
                redo_count=record.redo_count or 0,
                created_at=record.created_at.isoformat() if record.created_at else "",
            )
            for record in records
            if record.quality_score is None or record.quality_score >= 0.5
        ]

    async def generate_weak_point_practice(
        self,
        req: WeakPointPracticeRequest,
        user_id: int,
    ) -> QuestionResponse:
        prompt, topic_label = build_weak_point_prompt(req, user_id)
        questions, evidences = await self._generate_question_dicts(prompt)
        self._raise_if_generation_error(questions)
        batch_id = persist_generated_questions(
            self.repository,
            questions,
            user_id=user_id,
            conversation_id=None,
            topic=topic_label,
            evidences=evidences,
        )
        return format_question_response(questions, batch_id=batch_id, empty_text="无法生成练习题。")

    async def grade_question(
        self,
        question_id: int,
        req: GradeRequest,
        user_id: int,
    ) -> GradeResponse:
        record = self.repository.get_for_user(question_id, user_id)
        if not record:
            raise QuestionNotFoundError("题目不存在")

        from app.agents.grading_agent import grade_single_question

        result = await asyncio.wait_for(
            grade_single_question(
                stem=record.stem,
                standard_answer=record.standard_answer or "",
                user_answer=req.user_answer,
            ),
            timeout=settings.AGENT_RETRY_TIMEOUT,
        )
        score = float(result["score"])
        feedback = result["feedback"]
        is_wrong = bool(result["is_wrong"])
        error_analysis = result.get("error_analysis", "")

        self.repository.update_grading(
            record,
            user_answer=req.user_answer,
            score=score,
            is_wrong=is_wrong,
            error_analysis=error_analysis,
        )
        await self._emit_grading_event(record, user_id, score)

        return GradeResponse(
            score=score,
            feedback=feedback,
            is_wrong=is_wrong,
            error_analysis=error_analysis,
        )

    async def _generate_question_dicts(self, prompt: str) -> tuple[list[dict], list[object]]:
        from app.agents.question_tools import get_cached_evidences
        from app.services.question_generation_service import generate_questions_from_prompt

        questions = await asyncio.wait_for(
            generate_questions_from_prompt(prompt),
            timeout=settings.QUESTION_GEN_TIMEOUT,
        )
        return questions, get_cached_evidences()

    @staticmethod
    def _raise_if_generation_error(questions: list[dict]) -> None:
        if questions and questions[0].get("error"):
            raise QuestionGenerationError(questions[0]["error"])

    async def _emit_grading_event(self, record, user_id: int, score: float) -> None:
        try:
            if not record.knowledge_point_id:
                return

            knowledge_point = self.repository.knowledge_registry.get_by_id(record.knowledge_point_id)
            category = knowledge_point.category if knowledge_point else "unknown"
            if score >= 80:
                event_type = "grading_excellent"
                outcome = 1.0
            elif score >= 60:
                event_type = "grading_pass"
                outcome = 0.5
            else:
                event_type = "grading_fail"
                outcome = 0.0
            await emit(
                TrackingEvent(
                    user_id=user_id,
                    knowledge_point_ids=[record.knowledge_point_id],
                    event_type=event_type,
                    category=category,
                    difficulty=record.difficulty,
                    outcome=outcome,
                )
            )
        except Exception as event_error:
            logger.warning("Failed to publish grading event: %s", event_error)


def build_generation_prompt(topic: str, count: int, difficulty: str) -> str:
    diff_label = _DIFFICULTY_LABELS.get(difficulty, "混合")
    return "\n".join([
        f"请围绕「{topic}」生成 {count} 道 408 练习题，难度要求：{diff_label}。",
        "必须先检索题库模板或教材知识依据，再基于检索结果生成。",
        "如果检索不到相关依据或工具调用失败，不要兜底生成题目，直接说明无法生成的具体原因。",
        "题型只能从选择题、填空题、简答题、综合应用题中选择，不要生成编程题。",
        "每题按以下格式输出：题目X、类型、难度、题干、标准答案、解析。",
        "题干和解析必须简洁，每题解析不超过80字。",
        "不要输出寒暄、背景介绍、额外总结或 Markdown 加粗符号。",
    ])


def build_weak_point_prompt(req: WeakPointPracticeRequest, user_id: int) -> tuple[str, str]:
    from app.services.knowledge_tracker import get_knowledge_tracker

    tracker = get_knowledge_tracker()
    weak_points = tracker.get_weak_points(user_id, threshold=0.4, limit=5)

    if not weak_points:
        chosen = random.sample(_FALLBACK_TOPICS, min(req.count, len(_FALLBACK_TOPICS)))
        topics = [f"{topic}（{category}）" for topic, category in chosen]
        prompt_parts = [
            f"请围绕以下知识点生成 {req.count} 道 408 练习题，混合难度：",
            "、".join(topics),
            "必须先检索题库模板或教材知识依据，再基于检索结果生成。",
            "题型只能从选择题、填空题、简答题、综合应用题中选择。",
            "每题按以下格式输出：题目X、类型、难度、题干、标准答案、解析。",
            "题干和解析必须简洁，每题解析不超过80字。",
        ]
        return "\n".join(prompt_parts), ", ".join(topics)

    topics = [weak_point["name"] for weak_point in weak_points]
    difficulties = []
    for weak_point in weak_points:
        pct = max(0, min(100, round(weak_point["effective_score"] * 100)))
        if pct < 30:
            difficulties.append("基础")
        elif pct < 50:
            difficulties.append("中等")
        else:
            difficulties.append("较难")

    prompt_parts = [
        f"请围绕以下薄弱知识点生成 {req.count} 道 408 练习题：",
        "、".join(topics),
        f"难度要求：{'/'.join(difficulties)}。",
        "必须先检索题库模板或教材知识依据，再基于检索结果生成。",
        "题型只能从选择题、填空题、简答题、综合应用题中选择。",
        "每题按以下格式输出：题目X、类型、难度、题干、标准答案、解析。",
        "题干和解析必须简洁，每题解析不超过80字。",
    ]
    return "\n".join(prompt_parts), ", ".join(topics)


def persist_generated_questions(
    repository: QuestionRepository,
    questions: list[dict],
    *,
    user_id: int,
    conversation_id: int | None,
    topic: str,
    evidences: list[object],
) -> str | None:
    if not questions or questions[0].get("raw_text"):
        return None

    batch_id = str(uuid.uuid4())
    repository.create_questions(
        questions,
        user_id=user_id,
        conversation_id=conversation_id,
        batch_id=batch_id,
        topic=topic,
        evidences=evidences,
    )
    for question in questions:
        question["batch_id"] = batch_id
    return batch_id


def persist_generated_questions_with_managed_session(
    questions: list[dict],
    *,
    user_id: int,
    conversation_id: int | None,
    topic: str,
    evidences: list[object],
) -> str | None:
    from app.db.session import SessionLocal

    with SessionLocal() as db:
        return persist_generated_questions(
            QuestionRepository(db),
            questions,
            user_id=user_id,
            conversation_id=conversation_id,
            topic=topic,
            evidences=evidences,
        )


def format_question_response(
    questions: list[dict],
    *,
    batch_id: str | None,
    empty_text: str = "",
) -> QuestionResponse:
    raw_text = ""
    if questions and questions[0].get("raw_text"):
        raw_text = questions[0]["raw_text"]
    else:
        parts = []
        for index, question in enumerate(questions, 1):
            parts.append(
                "题目{index}：\n类型：{question_type}\n难度：{difficulty}\n题干：{stem}\n标准答案：{answer}\n解析：{explanation}".format(
                    index=index,
                    question_type=question.get("question_type", ""),
                    difficulty=question.get("difficulty", ""),
                    stem=question.get("stem", ""),
                    answer=question.get("answer", ""),
                    explanation=question.get("explanation", ""),
                )
            )
        raw_text = "\n\n".join(parts)

    return QuestionResponse(
        raw=raw_text or empty_text,
        questions=[
            question
            for question in questions
            if not question.get("error") and not question.get("raw_text")
        ],
        batch_id=batch_id,
    )
