from __future__ import annotations

from sqlalchemy.orm import Session

from app.db.models import QuestionRecord
from app.repositories.knowledge_registry_repository import KnowledgeRegistryRepository


class QuestionRepository:
    def __init__(self, db: Session):
        self.db = db
        self.knowledge_registry = KnowledgeRegistryRepository(db)

    def list_wrong_questions(self, user_id: int, limit: int) -> list[QuestionRecord]:
        return (
            self.db.query(QuestionRecord)
            .filter(
                QuestionRecord.user_id == user_id,
                QuestionRecord.is_wrong == True,  # noqa: E712
            )
            .order_by(QuestionRecord.created_at.desc())
            .limit(limit)
            .all()
        )

    def get_for_user(self, question_id: int, user_id: int) -> QuestionRecord | None:
        return (
            self.db.query(QuestionRecord)
            .filter(
                QuestionRecord.id == question_id,
                QuestionRecord.user_id == user_id,
            )
            .first()
        )

    def create_questions(
        self,
        questions: list[dict],
        *,
        user_id: int,
        conversation_id: int | None,
        batch_id: str,
        topic: str,
        evidences: list[object],
    ) -> None:
        knowledge_point_id = self.knowledge_registry.resolve_knowledge_point_id(
            evidences=evidences,
            topic=topic,
        )

        for question in questions:
            record = QuestionRecord(
                user_id=user_id,
                conversation_id=conversation_id,
                batch_id=batch_id,
                knowledge_point_id=knowledge_point_id,
                question_type=question.get("question_type", "简答"),
                difficulty=question.get("difficulty", 1.0),
                stem=question.get("stem", ""),
                standard_answer=question.get("answer", ""),
                explanation=question.get("explanation", ""),
                quality_score=question.get("quality_score"),
            )
            self.db.add(record)
            self.db.flush()
            question["id"] = record.id

        self.db.commit()

    def update_grading(
        self,
        record: QuestionRecord,
        *,
        user_answer: str,
        score: float,
        is_wrong: bool,
        error_analysis: str,
    ) -> None:
        was_wrong = bool(record.is_wrong)
        record.user_answer = user_answer
        record.grading_score = score
        record.is_wrong = is_wrong
        record.error_analysis = error_analysis
        if was_wrong and not is_wrong:
            record.redo_count = (record.redo_count or 0) + 1
        self.db.commit()
