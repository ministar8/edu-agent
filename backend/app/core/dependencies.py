from __future__ import annotations

from fastapi import Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.services.chat_message_service import ChatMessageService
from app.services.knowledge_base_service import KnowledgeBaseService
from app.services.question_service import QuestionService
from app.services.tracking_query_service import TrackingQueryService


def get_question_service(db: Session = Depends(get_db)) -> QuestionService:
    return QuestionService(db)


def get_chat_message_service(db: Session = Depends(get_db)) -> ChatMessageService:
    return ChatMessageService(db)


def get_tracking_query_service(db: Session = Depends(get_db)) -> TrackingQueryService:
    return TrackingQueryService(db)


def get_knowledge_base_service() -> KnowledgeBaseService:
    return KnowledgeBaseService()
