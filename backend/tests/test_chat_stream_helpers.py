from __future__ import annotations

from types import SimpleNamespace
from unittest import TestCase

from app.services.chat_stream_helpers import (
    append_source_line_if_missing,
    build_governance_from_agent,
    build_timeout_governance,
    chunk_text,
    sse,
)


class ChatStreamHelpersTests(TestCase):
    def test_append_source_line_if_missing_preserves_existing_source(self) -> None:
        answer = "答案\n\n来源：教材A"

        self.assertEqual(append_source_line_if_missing(answer, ["教材B"]), answer)

    def test_append_source_line_if_missing_appends_sources(self) -> None:
        self.assertEqual(
            append_source_line_if_missing("答案", ["教材A", "教材B"]),
            "答案\n\n来源依据：教材A，教材B",
        )

    def test_build_governance_from_agent_merges_guard(self) -> None:
        result = build_governance_from_agent(
            {"confidence": "high", "has_source": True, "passed": True, "flags": ["ok"]},
            {"has_sufficient_evidence": False},
        )

        self.assertEqual(result["confidence"], "high")
        self.assertFalse(result["has_sufficient_evidence"])

    def test_build_timeout_governance_marks_partial(self) -> None:
        self.assertEqual(
            build_timeout_governance(["教材A"], reason="deadline"),
            {
                "confidence": "low",
                "has_source": True,
                "passed": False,
                "flags": ["timeout_partial"],
                "reason": "deadline",
            },
        )

    def test_sse_serializes_utf8_json(self) -> None:
        self.assertEqual(sse("token", {"text": "你好"}), 'event: token\ndata: {"text": "你好"}\n\n')

    def test_chunk_text_handles_text_parts(self) -> None:
        chunk = SimpleNamespace(content=[{"text": "你"}, {"text": "好"}])

        self.assertEqual(chunk_text(chunk), "你好")
