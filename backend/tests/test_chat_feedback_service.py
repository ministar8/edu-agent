from __future__ import annotations

from unittest import TestCase
from unittest.mock import patch

from app.services.chat_feedback_service import ChatFeedbackService


class ChatFeedbackServiceTests(TestCase):
    def test_submit_feedback_adds_user_and_thread_metadata(self) -> None:
        with patch("app.services.chat_feedback_service.log_feedback") as log_feedback:
            result = ChatFeedbackService.submit_feedback(
                user_id=7,
                thread_id="thread-1",
                rating=-1,
                query="问题",
                answer="回答",
                metadata={"source": "ui"},
            )

        self.assertEqual(result, {"status": "ok", "rating": -1})
        log_feedback.assert_called_once_with(
            query="问题",
            answer="回答",
            rating=-1,
            metadata={"thread_id": "thread-1", "user_id": 7, "source": "ui"},
        )

    def test_get_feedback_summary_adds_bad_case_clusters(self) -> None:
        with (
            patch("app.services.chat_feedback_service.get_feedback_stats", return_value={"total": 1}),
            patch("app.services.chat_feedback_service.cluster_bad_cases", return_value=[{"cluster": "bad"}]),
        ):
            summary = ChatFeedbackService.get_feedback_summary(days=14)

        self.assertEqual(summary, {"total": 1, "bad_case_clusters": [{"cluster": "bad"}]})
