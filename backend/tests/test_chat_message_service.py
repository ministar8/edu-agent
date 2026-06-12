from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest import TestCase

from app.services.chat_message_service import message_to_item


class ChatMessageServiceTests(TestCase):
    def test_message_to_item_decodes_sources_and_governance(self) -> None:
        message = SimpleNamespace(
            id=1,
            role="assistant",
            content="答案",
            agent_name="knowledge_agent",
            sources='["教材A"]',
            governance='{"passed": true}',
            parent_id=7,
            siblings_order=2,
            created_at=datetime.now(timezone.utc),
        )

        item = message_to_item(message, child_count=3)

        self.assertEqual(item.sources, ["教材A"])
        self.assertEqual(item.governance, {"passed": True})
        self.assertEqual(item.child_count, 3)
        self.assertEqual(item.parent_id, 7)
