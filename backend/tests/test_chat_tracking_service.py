from __future__ import annotations

from types import SimpleNamespace
from unittest import TestCase

from app.services.chat_tracking_service import ChatTrackingService


class ChatTrackingServiceTests(TestCase):
    def test_build_document_qa_event_uses_governance_confidence(self) -> None:
        docs = [
            SimpleNamespace(
                metadata={"knowledge_point_ids": "[7]", "category": "数据结构"},
                collection="data_structure",
            )
        ]

        event = ChatTrackingService.build_document_qa_event(
            user_id=3,
            docs=docs,
            governance={"confidence": "high"},
        )

        self.assertIsNotNone(event)
        self.assertEqual(event.event_type, "qa_high_confidence")
        self.assertEqual(event.knowledge_point_ids, [7])
        self.assertEqual(event.category, "数据结构")
        self.assertEqual(event.outcome, 1.0)

    def test_build_multi_agent_event_maps_grading_score(self) -> None:
        event = ChatTrackingService.build_multi_agent_event(
            user_id=3,
            current_agent="grading_agent",
            agent_steps=[{"output_data": '{"knowledge_point_ids": [8]}'}],
            governance={"confidence": "low"},
            final_answer="评分：45/100\n难度：综合",
        )

        self.assertIsNotNone(event)
        self.assertEqual(event.event_type, "grading_fail")
        self.assertEqual(event.knowledge_point_ids, [8])
        self.assertEqual(event.difficulty, 1.6)
        self.assertEqual(event.outcome, 0.45)

    def test_build_multi_agent_event_ignores_question_agent(self) -> None:
        event = ChatTrackingService.build_multi_agent_event(
            user_id=3,
            current_agent="question_agent",
            agent_steps=[{"output_data": '{"knowledge_point_ids": [8]}'}],
            governance={"confidence": "high"},
            final_answer="",
        )

        self.assertIsNone(event)
