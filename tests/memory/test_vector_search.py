"""向量检索回退行为（测试环境 MEMORY_STORE_VECTOR_ENABLED=false）。"""

import pytest

from memory.episodes import aappend_episode
from memory.schemas import Episode
from memory.sqlite import get_sqlite_store
from memory.vector_search import asearch_episodes


@pytest.mark.asyncio
async def test_vector_disabled_falls_back_to_recent(tmp_path, monkeypatch):
    from core import settings as settings_singleton

    monkeypatch.setattr(settings_singleton, "SQLITE_STORE_PATH", str(tmp_path / "store.db"))
    monkeypatch.setattr(settings_singleton, "MEMORY_STORE_VECTOR_ENABLED", False)
    async with get_sqlite_store() as store:
        uid = 1
        await aappend_episode(store, uid, Episode(type="grade", topic="进程死锁", score=40))
        await aappend_episode(store, uid, Episode(type="grade", topic="页面置换", score=50))
        eps = await asearch_episodes(store, uid, "死锁", limit=5)
        assert len(eps) == 2


@pytest.mark.asyncio
async def test_search_text_written(tmp_path, monkeypatch):
    from core import settings as settings_singleton
    from memory.episodes import episode_search_text

    monkeypatch.setattr(settings_singleton, "SQLITE_STORE_PATH", str(tmp_path / "store.db"))
    ep = Episode(type="grade", topic="进程死锁", score=40, stem_excerpt="必要条件")
    assert "进程死锁" in episode_search_text(ep)
    assert "必要条件" in episode_search_text(ep)
