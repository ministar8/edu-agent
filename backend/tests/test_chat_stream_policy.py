from __future__ import annotations

from types import SimpleNamespace
from unittest import TestCase

from app.services.chat_stream_policy import is_simple_knowledge_candidate


def _category(**overrides):
    values = {
        "is_code": False,
        "is_exercise": False,
        "is_answer": False,
        "is_comparison": False,
        "is_learning_path": False,
        "is_long": False,
        "is_concept": True,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class ChatStreamPolicyTests(TestCase):
    def test_simple_concept_allows_fast_stream(self) -> None:
        self.assertTrue(
            is_simple_knowledge_candidate(
                "knowledge_agent",
                _category(),
                SimpleNamespace(layer="L1"),
            )
        )

    def test_non_knowledge_route_skips_fast_stream(self) -> None:
        self.assertFalse(
            is_simple_knowledge_candidate(
                "question_agent",
                _category(),
                SimpleNamespace(layer="L1"),
            )
        )

    def test_exercise_query_skips_fast_stream(self) -> None:
        self.assertFalse(
            is_simple_knowledge_candidate(
                "knowledge_agent",
                _category(is_exercise=True),
                SimpleNamespace(layer="L1"),
            )
        )

    def test_l2_non_concept_skips_fast_stream(self) -> None:
        self.assertFalse(
            is_simple_knowledge_candidate(
                "knowledge_agent",
                _category(is_concept=False),
                SimpleNamespace(layer="L2"),
            )
        )
