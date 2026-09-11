"""批改 domain 入口。"""

import pytest
from langchain_core.messages import HumanMessage, SystemMessage

from agents.grading_core import agrade_answer
from rag.schemas import GradingResult


@pytest.mark.asyncio
async def test_agrade_answer_builds_prompt_and_returns_result(monkeypatch):
    import agents.grading_core as grading_core

    captured: dict = {}

    async def fake_call_structured(prompt, _schema, **kwargs):
        captured["messages"] = prompt
        captured["kwargs"] = kwargs
        return GradingResult(score=80, feedback="ok", is_wrong=False)

    monkeypatch.setattr(grading_core, "call_structured", fake_call_structured)

    result = await agrade_answer(
        stem="题干A",
        user_answer="我的作答",
        standard_answer="标答B",
    )

    assert result.score == 80
    text = "\n".join(m.content for m in captured["messages"])
    assert "题干A" in text
    assert "标答B" in text
    assert "我的作答" in text
    assert captured["kwargs"]["stage"] == "grading"
    assert isinstance(captured["messages"][0], SystemMessage)
    assert any(isinstance(m, HumanMessage) for m in captured["messages"])


@pytest.mark.asyncio
async def test_agrade_answer_fallback_when_no_standard(monkeypatch):
    import agents.grading_core as grading_core

    captured: dict = {}

    async def fake_call_structured(prompt, _schema, **kwargs):
        captured["text"] = "\n".join(m.content for m in prompt)
        return GradingResult(score=50, feedback="差", is_wrong=True, error_analysis="概念不清")

    monkeypatch.setattr(grading_core, "call_structured", fake_call_structured)
    await agrade_answer(stem="s", user_answer="u", standard_answer="")
    assert "（无标准答案，请基于学科知识判断）" in captured["text"]


@pytest.mark.asyncio
async def test_agrade_answer_none_raises(monkeypatch):
    import agents.grading_core as grading_core

    async def fake_call_structured(prompt, _schema, **kwargs):
        return None

    monkeypatch.setattr(grading_core, "call_structured", fake_call_structured)
    with pytest.raises(RuntimeError, match="批改失败"):
        await agrade_answer(stem="s", user_answer="u")
