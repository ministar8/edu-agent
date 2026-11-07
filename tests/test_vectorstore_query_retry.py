"""单路向量查询的重试与可观测性（L1 + L3）。

背景：`asimilarity_search_with_score` 失败时返回 `[]`，上游无法区分
「知识库确实没有」与「索引坏了」。L1 对瞬时故障重试一次；L3 把进程内
失败计数暴露到 `/health`，让产品路径也能发现降级。

反向验证：把 `_QUERY_ATTEMPTS` 改回 1，`test_retries_transient_failure_then_succeeds`
立刻失败；把 `/health` 里的 `query_failures` 去掉，第三条测试失败。
"""

from __future__ import annotations

import asyncio

import pytest

from infra._vectorstore_query import _retry_async


def test_retries_transient_failure_then_succeeds() -> None:
    calls: list[int] = []

    async def fn() -> list[str]:
        calls.append(1)
        if len(calls) == 1:
            raise ConnectionResetError("transient")
        return ["ok"]

    assert asyncio.run(_retry_async(fn, attempts=2, backoff_s=0)) == ["ok"]
    assert len(calls) == 2


def test_raises_last_error_after_all_attempts() -> None:
    errors: list[tuple[int, str]] = []

    async def fn() -> None:
        raise RuntimeError("permanent")

    with pytest.raises(RuntimeError):
        asyncio.run(
            _retry_async(
                fn,
                attempts=2,
                backoff_s=0,
                on_error=lambda attempt, exc: errors.append((attempt, str(exc))),
            )
        )
    assert errors == [(1, "permanent"), (2, "permanent")]


def test_health_exposes_query_failure_snapshot(monkeypatch: pytest.MonkeyPatch) -> None:
    from infra import vectorstore as vs
    from service import health

    class _Manager:
        query_failures = ["data_structure: TimeoutError", "exams: RuntimeError"]

    monkeypatch.setattr(vs, "_vector_store_manager", _Manager(), raising=False)
    assert health._query_failure_snapshot() == {
        "total": 2,
        "recent": ["data_structure: TimeoutError", "exams: RuntimeError"],
    }

    monkeypatch.setattr(vs, "_vector_store_manager", None, raising=False)
    assert health._query_failure_snapshot() == {"total": 0, "recent": []}
