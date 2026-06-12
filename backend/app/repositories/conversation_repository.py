from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.models import Conversation, Message


class ConversationRepository:
    def __init__(self, db: Session):
        self.db = db

    def ensure_conversation(self, user_id: int, base_thread: str, first_message: str) -> Conversation:
        thread_id = f"{user_id}:{base_thread}"
        conversation = (
            self.db.query(Conversation)
            .filter(Conversation.thread_id == thread_id)
            .first()
        )
        if conversation:
            return conversation

        title = first_message[:50] if first_message else "新对话"
        conversation = Conversation(user_id=user_id, thread_id=thread_id, title=title)
        self.db.add(conversation)
        self.db.commit()
        self.db.refresh(conversation)
        return conversation

    def save_message(
        self,
        conversation_id: int,
        role: str,
        content: str,
        *,
        agent_name: str | None = None,
        sources: list[str] | None = None,
        governance: dict | None = None,
        parent_id: int | None = None,
    ) -> Message:
        conversation = self.get_conversation_by_id(conversation_id)
        if conversation is not None:
            conversation.updated_at = datetime.now(timezone.utc)

        parent_filter = Message.parent_id == parent_id if parent_id is not None else Message.parent_id.is_(None)
        max_order = (
            self.db.query(func.max(Message.siblings_order))
            .filter(parent_filter, Message.conversation_id == conversation_id)
            .scalar()
        )
        message = Message(
            conversation_id=conversation_id,
            role=role,
            content=content,
            agent_name=agent_name,
            sources=json.dumps(sources or [], ensure_ascii=False),
            governance=json.dumps(governance, ensure_ascii=False) if governance else None,
            parent_id=parent_id,
            siblings_order=(max_order or 0) + 1,
        )
        self.db.add(message)
        self.db.commit()
        self.db.refresh(message)
        return message

    def get_conversation_by_id(self, conversation_id: int) -> Conversation | None:
        return (
            self.db.query(Conversation)
            .filter(Conversation.id == conversation_id)
            .first()
        )

    def get_conversation_for_user(self, conversation_id: int, user_id: int) -> Conversation | None:
        return (
            self.db.query(Conversation)
            .filter(
                Conversation.id == conversation_id,
                Conversation.user_id == user_id,
            )
            .first()
        )

    def list_conversations_for_user(self, user_id: int) -> list[Conversation]:
        return (
            self.db.query(Conversation)
            .filter(Conversation.user_id == user_id)
            .order_by(Conversation.updated_at.desc())
            .all()
        )

    def list_messages(self, conversation_id: int) -> list[Message]:
        return (
            self.db.query(Message)
            .filter(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.asc())
            .all()
        )

    def list_recent_messages(self, conversation_id: int, limit: int) -> list[Message]:
        messages = (
            self.db.query(Message)
            .filter(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.desc())
            .limit(limit)
            .all()
        )
        messages.reverse()
        return messages

    def list_early_messages(self, conversation_id: int, limit: int) -> list[Message]:
        return (
            self.db.query(Message)
            .filter(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.asc())
            .limit(limit)
            .all()
        )

    def count_messages(self, conversation_id: int) -> int:
        return (
            self.db.query(Message)
            .filter(Message.conversation_id == conversation_id)
            .count()
        )

    def get_message(self, message_id: int) -> Message | None:
        return (
            self.db.query(Message)
            .filter(Message.id == message_id)
            .first()
        )

    def get_parent_chain(self, leaf_message_id: int, limit: int) -> list[Message]:
        chain: list[Message] = []
        current = self.get_message(leaf_message_id)
        while current is not None:
            chain.append(current)
            if current.parent_id is None:
                break
            current = self.get_message(current.parent_id)
        chain.reverse()
        return chain[-limit:]

    def update_summary(self, conversation_id: int, summary: str) -> None:
        conversation = self.get_conversation_by_id(conversation_id)
        if not conversation:
            return
        conversation.summary = summary
        self.db.commit()

    def delete_conversation(self, conversation: Conversation) -> None:
        self.db.query(Message).filter(Message.conversation_id == conversation.id).delete()
        self.db.delete(conversation)
        self.db.commit()
