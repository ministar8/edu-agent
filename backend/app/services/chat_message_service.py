from __future__ import annotations

import json
import logging

from sqlalchemy.orm import Session

from app.repositories.conversation_repository import ConversationRepository
from app.schemas import ConversationDetail, ConversationItem, MessageItem

logger = logging.getLogger(__name__)


class ChatMessageService:
    def __init__(self, db: Session):
        self.repository = ConversationRepository(db)

    def ensure_conversation(self, user_id: int, base_thread: str, first_message: str):
        return self.repository.ensure_conversation(user_id, base_thread, first_message)

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
    ):
        return self.repository.save_message(
            conversation_id,
            role,
            content,
            agent_name=agent_name,
            sources=sources,
            governance=governance,
            parent_id=parent_id,
        )

    def build_input_messages(
        self,
        *,
        user_message: str,
        conversation_id: int,
        conversation_summary: str,
        leaf_message_id: int | None = None,
    ) -> list:
        from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

        messages: list = [
            SystemMessage(
                content=(
                    "请用简洁、规范、整洁的中文分点回答。"
                    "除非用户明确要求表格、长文或完整试卷，否则不要使用表格和大段说明；"
                    "优先使用有序编号或短横线列表，每一点控制在1到2句话；"
                    "必要时只保留少量二级标题，不要输出三级标题；"
                    "不要使用 Markdown 加粗符号 **，需要强调时使用空格或普通文字表达；"
                    "408题目或解析必须包含题干、答案、解析三个部分；"
                    "不要输出原始JSON、调试信息或无意义前缀。"
                )
            ),
        ]

        if conversation_summary:
            messages.append(SystemMessage(content=f"【会话早期摘要】\n{conversation_summary}\n---"))

        history_messages = (
            self.repository.get_parent_chain(leaf_message_id, 12)
            if leaf_message_id is not None
            else self.repository.list_recent_messages(conversation_id, 12)
        )
        for message in history_messages:
            if message.role == "user":
                messages.append(HumanMessage(content=message.content))
            elif message.role == "assistant":
                content = message.content[:500] + "..." if len(message.content) > 500 else message.content
                messages.append(AIMessage(content=content))

        messages.append(HumanMessage(content=user_message))
        return messages

    async def maybe_summarize_conversation(self, conversation_id: int) -> None:
        from app.agents.memory_manager import summarize_messages, should_trigger_summary

        try:
            message_count = self.repository.count_messages(conversation_id)
            if not should_trigger_summary(message_count):
                return

            conversation = self.repository.get_conversation_by_id(conversation_id)
            if not conversation:
                return

            early_messages = self.repository.list_early_messages(conversation_id, 12)
            if not early_messages:
                return

            new_messages = [{"role": message.role, "content": message.content} for message in early_messages]
            summary = await summarize_messages(
                new_messages,
                existing_summary=conversation.summary or "",
            )
            if summary:
                self.repository.update_summary(conversation_id, summary)
                logger.info("Conversation summary updated conv_id=%s", conversation_id)
        except Exception as exc:
            logger.warning("Summary generation failed (non-fatal): %s", exc)

    def list_conversations(self, user_id: int) -> list[ConversationItem]:
        conversations = self.repository.list_conversations_for_user(user_id)
        return [
            ConversationItem(
                id=conversation.id,
                thread_id=conversation.thread_id,
                title=conversation.title,
                summary=conversation.summary or "",
                created_at=conversation.created_at,
                updated_at=conversation.updated_at,
                message_count=self.repository.count_messages(conversation.id),
            )
            for conversation in conversations
        ]

    def get_conversation_detail(self, conversation_id: int, user_id: int) -> ConversationDetail | None:
        conversation = self.repository.get_conversation_for_user(conversation_id, user_id)
        if not conversation:
            return None

        messages = self.repository.list_messages(conversation.id)
        child_counts: dict[int, int] = {}
        for message in messages:
            if message.parent_id is not None:
                child_counts[message.parent_id] = child_counts.get(message.parent_id, 0) + 1

        return ConversationDetail(
            id=conversation.id,
            thread_id=conversation.thread_id,
            title=conversation.title,
            summary=conversation.summary or "",
            created_at=conversation.created_at,
            updated_at=conversation.updated_at,
            messages=[
                message_to_item(message, child_count=child_counts.get(message.id, 0))
                for message in messages
            ],
        )

    def delete_conversation(self, conversation_id: int, user_id: int) -> bool:
        conversation = self.repository.get_conversation_for_user(conversation_id, user_id)
        if not conversation:
            return False
        self.repository.delete_conversation(conversation)
        return True

    @staticmethod
    def persist_message_with_managed_session(
        conversation_id: int,
        role: str,
        content: str,
        *,
        agent_name: str | None = None,
        sources: list[str] | None = None,
        governance: dict | None = None,
        parent_id: int | None = None,
    ) -> int:
        from app.db.session import SessionLocal

        with SessionLocal() as db:
            message = ChatMessageService(db).save_message(
                conversation_id,
                role,
                content,
                agent_name=agent_name,
                sources=sources,
                governance=governance,
                parent_id=parent_id,
            )
            return message.id

    @staticmethod
    async def summarize_with_managed_session(conversation_id: int) -> None:
        from app.db.session import SessionLocal

        with SessionLocal() as db:
            await ChatMessageService(db).maybe_summarize_conversation(conversation_id)


def message_to_item(message, *, child_count: int = 0) -> MessageItem:
    sources = json.loads(message.sources) if message.sources else []
    governance = json.loads(message.governance) if message.governance else None
    return MessageItem(
        id=message.id,
        role=message.role,
        content=message.content,
        agent_name=message.agent_name,
        sources=sources,
        governance=governance,
        parent_id=message.parent_id,
        siblings_order=message.siblings_order,
        child_count=child_count,
        created_at=message.created_at,
    )
