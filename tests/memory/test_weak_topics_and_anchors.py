"""weak_topics 防抖、safe_remember、记忆锚点字段。"""

import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from memory.episodes import aappend_episode
from memory.profile import aget_profile
from memory.remember import record_grade
from memory.runtime import set_store
from memory.safe import safe_remember
from memory.schemas import Episode, excerpt
from memory.sqlite import get_sqlite_store
from memory.weak_topics import a_recompute_weak_topics, compute_weak_topics


def _ep(score: float, topic: str = "死锁", days_ago: int = 0) -> Episode:
    at = (datetime.now(UTC) - timedelta(days=days_ago)).isoformat()
    return Episode(type="grade", topic=topic, score=score, at=at)


def test_compute_weak_requires_min_hits():
    assert compute_weak_topics([_ep(40)], min_weak_hits=2) == []
    assert compute_weak_topics([_ep(40), _ep(50)], min_weak_hits=2) == ["进程死锁"]


def test_compute_weak_ignores_old_and_good():
    old = _ep(40, days_ago=90)
    good = _ep(90)
    assert compute_weak_topics([old, good], min_weak_hits=1) == []


def test_compute_weak_clears_after_good_hits():
    eps = [_ep(40), _ep(50), _ep(90), _ep(95)]
    # 2 good + 2 weak → 仍算 weak（weak >= min）
    assert "进程死锁" in compute_weak_topics(eps, min_weak_hits=2, min_good_hits=2)
    # 只有 good 达标、weak 不足 → 不进列表
    only_good = [_ep(90), _ep(95), _ep(40)]
    assert compute_weak_topics(only_good, min_weak_hits=2, min_good_hits=2) == []


def test_excerpt():
    assert excerpt("短") == "短"
    assert excerpt("x" * 200).endswith("…")
    assert len(excerpt("x" * 200)) == 120


@pytest.mark.asyncio
async def test_safe_remember_timeout_returns_none(monkeypatch):
    from core import settings as settings_singleton

    monkeypatch.setattr(settings_singleton, "MEMORY_WRITE_TIMEOUT", 0.05)

    async def slow():
        await asyncio.sleep(1)
        return "x"

    assert await safe_remember(slow, label="t") is None


@pytest.mark.asyncio
async def test_safe_remember_swallows_errors():
    async def boom():
        raise RuntimeError("db down")

    assert await safe_remember(boom) is None


@pytest.mark.asyncio
async def test_record_grade_updates_weak_topics(tmp_path, monkeypatch):
    from core import settings as settings_singleton

    monkeypatch.setattr(settings_singleton, "SQLITE_STORE_PATH", str(tmp_path / "store.db"))
    async with get_sqlite_store() as store:
        set_store(store)
        try:
            await record_grade(
                user_id=1,
                topic="死锁",
                score=40,
                stem="死锁的必要条件不包括？",
                thread_id="t-1",
                agent_path="api_grade",
            )
            # 一次低分未达 min_hits=2
            profile = await aget_profile(store, 1)
            assert profile.weak_topics == []

            await record_grade(
                user_id=1,
                topic="死锁",
                score=30,
                stem="死锁的必要条件不包括？",
                thread_id="t-2",
                agent_path="api_grade",
            )
            profile = await aget_profile(store, 1)
            assert "进程死锁" in profile.weak_topics
        finally:
            set_store(None)


@pytest.mark.asyncio
async def test_episode_has_anchors(tmp_path, monkeypatch):
    from core import settings as settings_singleton

    monkeypatch.setattr(settings_singleton, "SQLITE_STORE_PATH", str(tmp_path / "store.db"))
    async with get_sqlite_store() as store:
        set_store(store)
        try:
            await record_grade(
                user_id=2,
                topic="页面置换",
                score=50,
                stem="Belady 异常说明了什么？",
                thread_id="th",
                run_id="run-1",
                agent_path="chat_grade",
            )
            from memory.episodes import arecent_episodes

            eps = await arecent_episodes(store, 2, limit=5)
            assert eps[0].stem_excerpt.startswith("Belady")
            assert eps[0].thread_id == "th"
            assert eps[0].run_id == "run-1"
            assert eps[0].agent_path == "chat_grade"
        finally:
            set_store(None)


@pytest.mark.asyncio
async def test_recompute_idempotent(tmp_path, monkeypatch):
    from core import settings as settings_singleton

    monkeypatch.setattr(settings_singleton, "SQLITE_STORE_PATH", str(tmp_path / "store.db"))
    async with get_sqlite_store() as store:
        uid = 3
        await aappend_episode(store, uid, _ep(50))
        await aappend_episode(store, uid, _ep(55))
        w1 = await a_recompute_weak_topics(store, uid)
        w2 = await a_recompute_weak_topics(store, uid)
        assert w1 == w2 == ["进程死锁"]
