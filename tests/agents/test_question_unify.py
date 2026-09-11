"""聊天出题：结构化真源 + 对话修饰。"""

import pytest
from langchain_core.messages import AIMessage

from agents.question_core import (
    agenerate_question_set,
    format_questions_for_chat,
    question_gen_agent,
)
from agents.tools import agenerate_practice_questions
from schema.questions import GeneratedQuestion, GeneratedQuestionSet

_QUESTION = GeneratedQuestion(
    question_type="choice",
    difficulty="medium",
    stem="死锁的必要条件不包括？",
    standard_answer="D",
    explanation="互斥、占有并等待、不可抢占、循环等待。",
)


def test_format_questions_for_chat_renders_fields():
    text = format_questions_for_chat(GeneratedQuestionSet(questions=[_QUESTION]))
    assert "题目1" in text
    assert "选择" in text
    assert "死锁的必要条件不包括？" in text
    assert "标准答案：D" in text
    assert "解析：" in text


def test_format_empty_set():
    assert "未能生成" in format_questions_for_chat(GeneratedQuestionSet(questions=[]))


@pytest.mark.asyncio
async def test_agenerate_question_set_uses_core(monkeypatch):
    async def fake_ainvoke(payload, **_kwargs):
        return {
            "messages": [AIMessage(content="")],
            "structured_response": GeneratedQuestionSet(questions=[_QUESTION]),
        }

    monkeypatch.setattr(question_gen_agent, "ainvoke", fake_ainvoke)
    result = await agenerate_question_set(topic="死锁", count=1, difficulty="medium")
    assert result.questions[0].standard_answer == "D"


@pytest.mark.asyncio
async def test_chat_tool_formats_same_core(monkeypatch):
    async def fake_ainvoke(payload, **_kwargs):
        return {
            "messages": [AIMessage(content="")],
            "structured_response": GeneratedQuestionSet(questions=[_QUESTION]),
        }

    monkeypatch.setattr(question_gen_agent, "ainvoke", fake_ainvoke)
    text = await agenerate_practice_questions.ainvoke(
        {"topic": "死锁", "count": 1, "difficulty": "medium"}
    )
    assert "题目1" in text
    assert "标准答案：D" in text


def test_chat_tool_name():
    assert agenerate_practice_questions.name == "generate_practice_questions"
