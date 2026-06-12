from __future__ import annotations

from unittest import TestCase

from app.services.question_generation_service import (
    compute_quality_scores,
    extract_topic,
    parse_questions_from_raw,
)


class QuestionGenerationServiceTests(TestCase):
    def test_extract_topic_prefers_quoted_topic(self) -> None:
        self.assertEqual(extract_topic("请围绕「线性表」出题"), "线性表")

    def test_parse_questions_from_raw_uses_regex_path(self) -> None:
        questions = parse_questions_from_raw(
            "题目1：\n"
            "类型：简答\n"
            "难度：基础\n"
            "题干：什么是栈？\n"
            "答案：后进先出。\n"
            "解析：栈只允许在一端插入和删除元素。"
        )

        self.assertEqual(len(questions), 1)
        self.assertEqual(questions[0]["question_type"], "简答")
        self.assertEqual(questions[0]["difficulty"], 1.0)
        self.assertEqual(questions[0]["stem"], "什么是栈？")

    def test_compute_quality_scores_penalizes_duplicate_short_items(self) -> None:
        questions = [
            {"question_type": "简答", "stem": f"题干{i}", "explanation": "短"}
            for i in range(5)
        ]

        scored = compute_quality_scores(questions, ["完全不同的模板"])

        self.assertAlmostEqual(scored[0]["quality_score"], 0.5)
