"""记忆 P0：命名空间工厂、版本化 schema、profile/episodes 读写。"""

from pathlib import Path

import pytest

from memory.episodes import aappend_episode, arecent_episodes
from memory.namespaces import episode_key, student_episodes_ns, student_profile_ns
from memory.profile import aget_profile, aupsert_profile
from memory.schemas import SCHEMA_VERSION, Episode, StudentProfile
from memory.sqlite import get_sqlite_store


def test_namespace_factory_stringifies_user_id():
    assert student_profile_ns(7) == ("student", "7", "profile")
    assert student_profile_ns("7") == ("student", "7", "profile")
    assert student_episodes_ns(7) == ("student", "7", "episodes")
    assert episode_key("abc") == "ep-abc"


def test_profile_defaults_and_version():
    p = StudentProfile()
    assert p.schema_version == SCHEMA_VERSION
    assert p.weak_topics == []
    assert p.updated_at


def test_profile_with_updates_stamps_time():
    p1 = StudentProfile()
    p2 = p1.with_updates(weak_topics=["死锁"])
    assert p2.weak_topics == ["死锁"]
    assert p2.updated_at >= p1.updated_at
    assert p2.schema_version == SCHEMA_VERSION


@pytest.mark.asyncio
async def test_profile_roundtrip(tmp_path, monkeypatch):
    from core import settings as settings_singleton

    monkeypatch.setattr(settings_singleton, "SQLITE_STORE_PATH", str(tmp_path / "store.db"))
    async with get_sqlite_store() as store:
        empty = await aget_profile(store, 42)
        assert empty.weak_topics == []

        saved = await aupsert_profile(store, 42, weak_topics=["页面置换"], level="beginner")
        assert "页面置换" in saved.weak_topics
        assert saved.level == "beginner"

        again = await aget_profile(store, 42)
        assert again.weak_topics == ["页面置换"]
        # merge：只改 level，weak_topics 保留
        merged = await aupsert_profile(store, "42", level="intermediate")
        assert merged.weak_topics == ["页面置换"]
        assert merged.level == "intermediate"

    assert Path(tmp_path / "store.db").exists()


@pytest.mark.asyncio
async def test_episodes_append_and_recent(tmp_path, monkeypatch):
    from core import settings as settings_singleton

    monkeypatch.setattr(settings_singleton, "SQLITE_STORE_PATH", str(tmp_path / "store.db"))
    uid = 9
    async with get_sqlite_store() as store:
        eid = await aappend_episode(
            store,
            uid,
            Episode(type="grade", topic="死锁", score=40, error_analysis="漏条件", thread_id="t1"),
        )
        assert eid
        await aappend_episode(
            store,
            uid,
            Episode(type="question", topic="页面置换", thread_id="t1"),
        )
        recent = await arecent_episodes(store, uid, limit=5)
        assert len(recent) == 2
        assert {e.type for e in recent} == {"grade", "question"}
        grade = next(e for e in recent if e.type == "grade")
        assert grade.score == 40
        assert grade.schema_version == SCHEMA_VERSION


@pytest.mark.asyncio
async def test_corrupt_profile_falls_back(tmp_path, monkeypatch):
    from core import settings as settings_singleton

    monkeypatch.setattr(settings_singleton, "SQLITE_STORE_PATH", str(tmp_path / "store.db"))
    async with get_sqlite_store() as store:
        await store.aput(student_profile_ns(1), "profile", {"weak_topics": "not-a-list"})
        profile = await aget_profile(store, 1)
        assert profile.weak_topics == []


@pytest.mark.asyncio
async def test_unknown_schema_version_still_reads(tmp_path, monkeypatch):
    from core import settings as settings_singleton

    monkeypatch.setattr(settings_singleton, "SQLITE_STORE_PATH", str(tmp_path / "store.db"))
    async with get_sqlite_store() as store:
        await store.aput(
            student_profile_ns(2),
            "profile",
            {"schema_version": 99, "weak_topics": ["x"], "updated_at": "t"},
        )
        profile = await aget_profile(store, 2)
        assert profile.weak_topics == ["x"]
        assert profile.schema_version == SCHEMA_VERSION
