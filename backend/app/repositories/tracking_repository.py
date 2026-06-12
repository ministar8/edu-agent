from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.db.models import KnowledgePointRegistry, MasteryHistory, StudentKnowledgeState


class TrackingRepository:
    def __init__(self, db: Session):
        self.db = db

    def list_category_knowledge_points(self, category: str) -> list[KnowledgePointRegistry]:
        return (
            self.db.query(KnowledgePointRegistry)
            .filter(
                KnowledgePointRegistry.category == category,
                KnowledgePointRegistry.chapter != "",
            )
            .all()
        )

    def list_states_for_user_category(self, user_id: int, category: str) -> list[StudentKnowledgeState]:
        return (
            self.db.query(StudentKnowledgeState)
            .filter(
                StudentKnowledgeState.user_id == user_id,
                StudentKnowledgeState.category == category,
            )
            .all()
        )

    def list_states_for_user(self, user_id: int) -> list[StudentKnowledgeState]:
        return (
            self.db.query(StudentKnowledgeState)
            .filter(StudentKnowledgeState.user_id == user_id)
            .all()
        )

    def list_recent_states(self, user_id: int, limit: int) -> list[StudentKnowledgeState]:
        return (
            self.db.query(StudentKnowledgeState)
            .filter(StudentKnowledgeState.user_id == user_id)
            .order_by(StudentKnowledgeState.last_interaction_at.desc())
            .limit(limit)
            .all()
        )

    def get_knowledge_point(self, knowledge_point_id: int) -> KnowledgePointRegistry | None:
        return self.db.get(KnowledgePointRegistry, knowledge_point_id)

    def list_knowledge_points_by_ids(self, knowledge_point_ids: list[int]) -> list[KnowledgePointRegistry]:
        if not knowledge_point_ids:
            return []
        return (
            self.db.query(KnowledgePointRegistry)
            .filter(KnowledgePointRegistry.id.in_(knowledge_point_ids))
            .all()
        )

    def list_knowledge_point_ids_by_category(self, category: str) -> list[int]:
        return [
            knowledge_point.id
            for knowledge_point in (
                self.db.query(KnowledgePointRegistry)
                .filter(KnowledgePointRegistry.category == category)
                .all()
            )
        ]

    def list_mastery_history(
        self,
        *,
        user_id: int,
        since: datetime,
        knowledge_point_id: int | None = None,
        knowledge_point_ids: list[int] | None = None,
    ) -> list[MasteryHistory]:
        query = self.db.query(MasteryHistory).filter(
            MasteryHistory.user_id == user_id,
            MasteryHistory.created_at >= since,
        )

        if knowledge_point_id:
            query = query.filter(MasteryHistory.knowledge_point_id == knowledge_point_id)
        elif knowledge_point_ids:
            query = query.filter(MasteryHistory.knowledge_point_id.in_(knowledge_point_ids))

        return query.order_by(MasteryHistory.created_at).all()
