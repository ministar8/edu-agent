"""run_supervisor 异常分段与 stage_of 映射（§4.5 / §5.4）。

锁定三件事：
1. UnclosedSpecialistOutput → SpecialistRunError（stage=specialist）；
2. 其余内层失败 → SupervisorRunError（stage=supervisor），且已打标不二次包装；
3. 服务层 stage_of 只认包装类型，未包装兜底 supervisor。
"""

from __future__ import annotations

import pytest
from langchain_core.messages import HumanMessage

from agents.orchestration.state import (
    SpecialistRunError,
    SupervisorRunError,
    stage_of,
)
from agents.orchestration.supervisor import UnclosedSpecialistOutput
from agents.orchestration.teaching_graph import run_supervisor


def _state():
    return {"messages": [HumanMessage(content="出题")]}


class _RaisingSupervisor:
    def __init__(self, exc: Exception) -> None:
        self.exc = exc
        self.payload = None

    async def ainvoke(self, payload, config=None):
        self.payload = payload
        raise self.exc


class _PassThroughSupervisor:
    """成功路径替身：返回固定 dict，不推断真实专家。"""

    def __init__(self, result: dict) -> None:
        self.result = result

    async def ainvoke(self, payload, config=None):
        return self.result


@pytest.mark.asyncio
async def test_unclosed_specialist_wrapped_as_specialist(monkeypatch) -> None:
    stub = _RaisingSupervisor(
        UnclosedSpecialistOutput("专家 'question_agent' 以未闭环 tool_calls 收尾")
    )
    monkeypatch.setattr("agents.orchestration.teaching_graph.inner_supervisor", stub)

    with pytest.raises(SpecialistRunError) as exc_info:
        await run_supervisor(_state(), {"configurable": {}})

    assert exc_info.value.stage == "specialist"
    # 原因链保留原始异常，日志/调试仍能看到真凶
    assert isinstance(exc_info.value.__cause__, UnclosedSpecialistOutput)
    assert "question_agent" in str(exc_info.value)


@pytest.mark.asyncio
async def test_generic_inner_failure_wrapped_as_supervisor(monkeypatch) -> None:
    stub = _RaisingSupervisor(RuntimeError("LLM gateway 500"))
    monkeypatch.setattr("agents.orchestration.teaching_graph.inner_supervisor", stub)

    with pytest.raises(SupervisorRunError) as exc_info:
        await run_supervisor(_state(), {"configurable": {}})

    assert exc_info.value.stage == "supervisor"
    assert isinstance(exc_info.value.__cause__, RuntimeError)
    assert "LLM gateway 500" in str(exc_info.value)


@pytest.mark.asyncio
async def test_already_tagged_errors_are_not_double_wrapped(monkeypatch) -> None:
    original = SpecialistRunError("already tagged")
    stub = _RaisingSupervisor(original)
    monkeypatch.setattr("agents.orchestration.teaching_graph.inner_supervisor", stub)

    with pytest.raises(SpecialistRunError) as exc_info:
        await run_supervisor(_state(), {"configurable": {}})

    assert exc_info.value is original
    assert exc_info.value.stage == "specialist"


@pytest.mark.asyncio
async def test_success_path_still_returns_inferred_fields(monkeypatch) -> None:
    from langchain_core.messages import AIMessage

    stub = _PassThroughSupervisor(
        {
            "messages": [
                HumanMessage(content="你好"),
                AIMessage(content="答", name="knowledge_agent"),
            ]
        }
    )
    monkeypatch.setattr("agents.orchestration.teaching_graph.inner_supervisor", stub)

    out = await run_supervisor(_state(), {"configurable": {}})
    assert out["active_agent"] == "knowledge_agent"
    assert out["task_mode"] == "knowledge"


def test_stage_of_specialist_and_supervisor() -> None:
    assert stage_of(SpecialistRunError("x")) == "specialist"
    assert stage_of(SupervisorRunError("x")) == "supervisor"


def test_stage_of_unwrapped_defaults_to_supervisor() -> None:
    # 未包装的图异常（例如未来绕过 run_supervisor 的路径）保持旧行为
    assert stage_of(RuntimeError("boom")) == "supervisor"
    assert stage_of(ValueError("boom")) == "supervisor"
    # UnclosedSpecialistOutput 未经 run_supervisor 包装时也兜底 supervisor
    # （正常链路一定会先被包装成 SpecialistRunError）
    assert stage_of(UnclosedSpecialistOutput("raw")) == "supervisor"
