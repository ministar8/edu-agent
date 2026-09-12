"""episodes 保留策略：TTL + 每用户上限。"""

from datetime import UTC, datetime, timedelta

import pytest

from memory.episodes import aappend_episode, arecent_episodes
from memory.retention import (
    acleanup_all_student_episodes,
    acleanup_user_episodes,
    alist_episode_items,
)
from memory.schemas import Episode
from memory.sqlite import get_sqlite_store


def _ep(at: datetime, score: float = 80) -> Episode:
    return Episode(type="grade", topic="进程死锁", score=score, at=at.isoformat())


@pytest.mark.asyncio
async def test_ttl_deletes_old(tmp_path, monkeypatch):
    from core import settings as settings_singleton

    monkeypatch.setattr(settings_singleton, "SQLITE_STORE_PATH", str(tmp_path / "store.db"))
    now = datetime.now(UTC)
    async with get_sqlite_store() as store:
        uid = 1
        await aappend_episode(store, uid, _ep(now - timedelta(days=100)))
        await aappend_episode(store, uid, _ep(now - timedelta(days=1)))
        stats = await acleanup_user_episodes(store, uid, ttl_days=90, max_per_user=0, now=now)
        assert stats.deleted_expired == 1
        left = await alist_episode_items(store, uid)
        assert len(left) == 1
        assert left[0][1].at.startswith((now - timedelta(days=1)).strftime("%Y-%m-%d")[:10])


@pytest.mark.asyncio
async def test_max_per_user_keeps_newest(tmp_path, monkeypatch):
    from core import settings as settings_singleton

    monkeypatch.setattr(settings_singleton, "SQLITE_STORE_PATH", str(tmp_path / "store.db"))
    now = datetime.now(UTC)
    async with get_sqlite_store() as store:
        uid = 2
        for i in range(5):
            await aappend_episode(store, uid, _ep(now - timedelta(hours=i), score=50 + i))
        stats = await acleanup_user_episodes(store, uid, ttl_days=0, max_per_user=2, now=now)
        assert stats.deleted_over_cap == 3
        left = await arecent_episodes(store, uid, limit=10)
        assert len(left) == 2
        # 保留最新两条
        assert left[0].score == 50
        assert left[1].score == 51


@pytest.mark.asyncio
async def test_cleanup_all_students(tmp_path, monkeypatch):
    from core import settings as settings_singleton

    monkeypatch.setattr(settings_singleton, "SQLITE_STORE_PATH", str(tmp_path / "store.db"))
    now = datetime.now(UTC)
    async with get_sqlite_store() as store:
        for uid in (10, 11):
            await aappend_episode(store, uid, _ep(now - timedelta(days=200)))
            await aappend_episode(store, uid, _ep(now))
        stats = await acleanup_all_student_episodes(store)
        assert stats.users >= 2
        assert stats.deleted_expired >= 2


@pytest.mark.asyncio
async def test_disabled_when_zero(tmp_path, monkeypatch):
    from core import settings as settings_singleton

    monkeypatch.setattr(settings_singleton, "SQLITE_STORE_PATH", str(tmp_path / "store.db"))
    now = datetime.now(UTC)
    async with get_sqlite_store() as store:
        uid = 3
        await aappend_episode(store, uid, _ep(now - timedelta(days=400)))
        stats = await acleanup_user_episodes(store, uid, ttl_days=0, max_per_user=0, now=now)
        assert stats.deleted_total == 0
        assert len(await alist_episode_items(store, uid)) == 1
