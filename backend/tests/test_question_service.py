from __future__ import annotations

from unittest import TestCase

from app.services.question_service import (
    build_generation_prompt,
    format_question_response,
    persist_generated_questions,
)


class _FakeQuestionRepository:
    def __init__(self) -> None:
        self.created = None

    def create_questions(self, questions, *, user_id, conversation_id, batch_id, topic, evidences):
        self.created = {
            "questions": questions,
            "user_id": user_id,
            "conversation_id": conversation_id,
            "batch_id": batch_id,
            "topic": topic,
            "evidences": evidences,
        }
        for index, question in enumerate(questions, start=1):
            question["id"] = index


class QuestionServiceTests(TestCase):
    def test_build_generation_prompt_maps_requested_difficulty(self) -> None:
        prompt = build_generation_prompt("线性表", 2, "hard")

        self.assertIn("线性表", prompt)
        self.assertIn("生成 2 道", prompt)
        self.assertIn("难度要求：困难", prompt)
        self.assertIn("不要兜底生成题目", prompt)

    def test_format_question_response_preserves_structured_questions(self) -> None:
        response = format_question_response(
            [
                {
                    "question_type": "选择题",
                    "difficulty": 1.3,
                    "stem": "栈的特点是什么？",
                    "answer": "后进先出",
                    "explanation": "栈只允许在一端操作。",
                    "batch_id": "batch-1",
                }
            ],
            batch_id="batch-1",
        )

        self.assertEqual(response.batch_id, "batch-1")
        self.assertEqual(len(response.questions), 1)
        self.assertIn("题目1", response.raw)
        self.assertIn("后进先出", response.raw)

    def test_format_question_response_returns_raw_text_on_parse_fallback(self) -> None:
        response = format_question_response(
            [{"raw_text": "原始题目文本"}],
            batch_id=None,
        )

        self.assertEqual(response.raw, "原始题目文本")
        self.assertEqual(response.questions, [])

    def test_persist_generated_questions_attaches_batch_id_and_record_ids(self) -> None:
        repository = _FakeQuestionRepository()
        questions = [{"stem": "题干", "answer": "答案"}]

        batch_id = persist_generated_questions(
            repository,
            questions,
            user_id=7,
            conversation_id=None,
            topic="线性表",
            evidences=[],
        )

        self.assertIsNotNone(batch_id)
        self.assertEqual(repository.created["user_id"], 7)
        self.assertEqual(repository.created["topic"], "线性表")
        self.assertEqual(questions[0]["batch_id"], batch_id)
        self.assertEqual(questions[0]["id"], 1)
