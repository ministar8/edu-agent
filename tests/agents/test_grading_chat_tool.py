"""聊天批改收口：grading_core 真源 + 工具。"""

from unittest.mock import AsyncMock, patch

import pytest

from agents.grading_core import format_grading_for_chat
from agents.tools import agrade_student_answer
from schema.grading import GradingResult


def test_format_grading_for_chat():
    text = format_grading_for_chat(
        GradingResult(
            score=72, feedback="基本正确，漏了循环等待", is_wrong=True, error_analysis="概念不全"
        )
    )
    assert "72/100" in text
    assert "循环等待" in text
    assert "概念不全" in text


def test_format_grading_ok_no_error_analysis():
    text = format_grading_for_chat(GradingResult(score=95, feedback="很好", is_wrong=False))
    assert "95/100" in text
    assert "错因" not in text


@pytest.mark.asyncio
async def test_grade_tool_uses_provided_standard_answer():
    async def fake_agrade(stem, user_answer, standard_answer=""):
        assert stem == "死锁条件"
        assert user_answer == "互斥"
        assert standard_answer == "互斥、占有并等待、不可抢占、循环等待"
        return GradingResult(score=40, feedback="不完整", is_wrong=True, error_analysis="漏点")

    with patch("agents.grading_core.agrade_answer", AsyncMock(side_effect=fake_agrade)):
        text = await agrade_student_answer.ainvoke(
            {
                "stem": "死锁条件",
                "user_answer": "互斥",
                "standard_answer": "互斥、占有并等待、不可抢占、循环等待",
            }
        )
    assert "40/100" in text
    assert "漏点" in text


@pytest.mark.asyncio
async def test_grade_tool_retrieves_when_no_standard():
    retrieve_payload = {
        "status": "ok",
        "context": "标准：A、B、C",
        "docs": [],
        "sources": [],
    }
    captured: dict = {}

    async def fake_agrade(stem, user_answer, standard_answer=""):
        captured["standard_answer"] = standard_answer
        return GradingResult(score=80, feedback="尚可", is_wrong=False)

    with (
        patch("agents.tools._retrieve_payload", AsyncMock(return_value=retrieve_payload)),
        patch("agents.grading_core.agrade_answer", AsyncMock(side_effect=fake_agrade)),
    ):
        text = await agrade_student_answer.ainvoke(
            {"stem": "题干", "user_answer": "作答", "standard_answer": ""}
        )

    assert captured["standard_answer"] == "标准：A、B、C"
    assert "80/100" in text


@pytest.mark.asyncio
async def test_grade_tool_retrieve_error():
    payload = {"status": "error", "error": "TEI down", "context": "检索失败", "docs": []}
    with patch("agents.tools._retrieve_payload", AsyncMock(return_value=payload)):
        text = await agrade_student_answer.ainvoke(
            {"stem": "s", "user_answer": "u", "standard_answer": ""}
        )
    assert "批改失败" in text
    assert "TEI down" in text
