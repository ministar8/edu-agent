"""service._mark_failed 的两道守卫：task_id 与终态。

图内节点抛异常时 update 不会提交，所以只能由图外写 failed；
但图外写入必须防两件事：同 thread 的另一个请求、以及已经 completed 的任务。
stage 按 stage_of(exc) 分段（specialist / supervisor），不写死。
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from agents.orchestration.state import SpecialistRunError, SupervisorRunError
from service.service import _mark_failed


class _StubAgent:
    def __init__(self, values):
        self.values = values
        self.updated = None

    async def aget_state(self, config=None):
        return SimpleNamespace(values=self.values)

    async def aupdate_state(self, config, update):
        self.updated = update


@pytest.mark.asyncio
async def test_mark_failed_skips_when_task_id_mismatch() -> None:
    agent = _StubAgent({"task_id": "other:r", "task_status": "pending"})
    await _mark_failed(agent, {}, "mine:r", RuntimeError("boom"))
    assert agent.updated is None


@pytest.mark.parametrize("status", ["completed", "failed"])
@pytest.mark.asyncio
async def test_mark_failed_skips_terminal_task(status: str) -> None:
    agent = _StubAgent({"task_id": "mine:r", "task_status": status})
    await _mark_failed(agent, {}, "mine:r", RuntimeError("boom"))
    assert agent.updated is None


@pytest.mark.asyncio
async def test_mark_failed_writes_pending_task() -> None:
    agent = _StubAgent({"task_id": "mine:r", "task_status": "pending"})
    await _mark_failed(agent, {}, "mine:r", SupervisorRunError("boom"))
    assert agent.updated["task_status"] == "failed"
    assert agent.updated["error"]["code"] == "GRAPH_RUN_FAILED"
    assert agent.updated["error"]["stage"] == "supervisor"


@pytest.mark.asyncio
async def test_mark_failed_maps_specialist_stage() -> None:
    agent = _StubAgent({"task_id": "mine:r", "task_status": "pending"})
    await _mark_failed(agent, {}, "mine:r", SpecialistRunError("专家未闭环"))
    assert agent.updated["error"]["stage"] == "specialist"


@pytest.mark.asyncio
async def test_mark_failed_unwrapped_exception_stays_supervisor() -> None:
    # 未包装异常：stage_of 兜底 supervisor（与 P1 前行为一致）
    agent = _StubAgent({"task_id": "mine:r", "task_status": "pending"})
    await _mark_failed(agent, {}, "mine:r", RuntimeError("boom"))
    assert agent.updated["error"]["stage"] == "supervisor"
