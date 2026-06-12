from __future__ import annotations

from app.rag.feedback import cluster_bad_cases, get_feedback_stats, log_feedback


class ChatFeedbackService:
    @staticmethod
    def submit_feedback(
        *,
        user_id: int,
        thread_id: str,
        rating: int,
        query: str = "",
        answer: str = "",
        metadata: dict | None = None,
    ) -> dict:
        log_feedback(
            query=query or "",
            answer=answer or "",
            rating=rating,
            metadata={
                "thread_id": thread_id,
                "user_id": user_id,
                **(metadata or {}),
            },
        )
        return {"status": "ok", "rating": rating}

    @staticmethod
    def get_feedback_summary(days: int = 7) -> dict:
        stats = get_feedback_stats(days=days)
        stats["bad_case_clusters"] = cluster_bad_cases(days=days)
        return stats
