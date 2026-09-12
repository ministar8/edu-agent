"""P2：topic 规范化、记忆卡、显式外键、教学图节点。"""

from datetime import UTC, datetime

import pytest
from langchain_core.messages import HumanMessage, SystemMessage

from memory.episodes import aappend_episode, arecent_episodes
from memory.remember import record_grade, record_question
from memory.runtime import set_store
from memory.schemas import Episode
from memory.sqlite import get_sqlite_store
from memory.topics import normalize_topic, normalize_topics
from memory.weak_topics import a_recompute_weak_topics
from memory.working import abuild_memory_card, format_memory_card


def test_normalize_topic_aliases():
    assert normalize_topic("死锁") == "进程死锁"
    assert normalize_topic("  进程死锁 ") == "进程死锁"
    assert normalize_topic("页面置换算法") == "页面置换"
    assert normalize_topic("未知主题") == "未知主题"
    assert normalize_topics(["死锁", "进程死锁", "页面置换"]) == ["进程死锁", "页面置换"]


def test_format_memory_card_empty_and_cap():
    assert format_memory_card(weak_lines=[], preferred_style="") == ""
    card = format_memory_card(weak_lines=["a" * 50, "b", "c", "d"], preferred_style="极简")
    assert card.startswith("【学生记忆】")
    assert "薄弱：" in card
    assert len(card) <= 200


@pytest.mark.asyncio
async def test_memory_card_has_anchors(tmp_path, monkeypatch):
    from core import settings as settings_singleton

    monkeypatch.setattr(settings_singleton, "SQLITE_STORE_PATH", str(tmp_path / "store.db"))
    async with get_sqlite_store() as store:
        set_store(store)
        try:
            await record_grade(
                user_id=1,
                topic="死锁",
                score=40,
                stem="死锁的必要条件不包括下列哪一项？",
                agent_path="api_grade",
            )
            await record_grade(
                user_id=1,
                topic="死锁",
                score=35,
                stem="死锁的必要条件不包括下列哪一项？",
                agent_path="api_grade",
            )
            card = await abuild_memory_card(store, 1)
            assert "进程死锁" in card
            assert "分" in card
        finally:
            set_store(None)


@pytest.mark.asyncio
async def test_question_grade_explicit_fk(tmp_path, monkeypatch):
    from core import settings as settings_singleton

    monkeypatch.setattr(settings_singleton, "SQLITE_STORE_PATH", str(tmp_path / "store.db"))
    async with get_sqlite_store() as store:
        set_store(store)
        try:
            eid, batch_id = await record_question(
                user_id=2,
                topic="死锁",
                agent_path="api_question",
                count=1,
            )
            assert eid and batch_id
            await record_grade(
                user_id=2,
                topic="死锁",
                score=50,
                stem="题干",
                batch_id=batch_id,
                ref_episode_id=eid,
                agent_path="api_grade",
            )
            eps = await arecent_episodes(store, 2, limit=10)
            grade = next(e for e in eps if e.type == "grade")
            question = next(e for e in eps if e.type == "question")
            assert grade.batch_id == question.batch_id == batch_id
            assert grade.ref_episode_id == eid
            assert grade.topic == question.topic == "进程死锁"
        finally:
            set_store(None)


@pytest.mark.asyncio
async def test_weak_topics_use_normalized_topic(tmp_path, monkeypatch):
    from core import settings as settings_singleton

    monkeypatch.setattr(settings_singleton, "SQLITE_STORE_PATH", str(tmp_path / "store.db"))
    async with get_sqlite_store() as store:
        uid = 5
        now = datetime.now(UTC).isoformat()
        await aappend_episode(store, uid, Episode(type="grade", topic="死锁", score=40, at=now))
        await aappend_episode(store, uid, Episode(type="grade", topic="进程死锁", score=50, at=now))
        weak = await a_recompute_weak_topics(store, uid)
        assert weak == ["进程死锁"]


@pytest.mark.asyncio
async def test_load_memory_node_writes_state():
    from agents.teaching_graph import load_memory

    updates = await load_memory({"messages": []}, config=None)
    assert updates.get("memory_card") == ""
    assert "messages" not in updates


@pytest.mark.asyncio
async def test_load_memory_injects_system_message(tmp_path, monkeypatch):
    from core import settings as settings_singleton

    monkeypatch.setattr(settings_singleton, "SQLITE_STORE_PATH", str(tmp_path / "store.db"))
    async with get_sqlite_store() as store:
        set_store(store)
        try:
            await record_grade(user_id=9, topic="死锁", score=40, stem="s1", agent_path="api_grade")
            await record_grade(user_id=9, topic="死锁", score=45, stem="s2", agent_path="api_grade")
            from agents.teaching_graph import load_memory

            config = {"configurable": {"user_id": "9", "thread_id": "t"}}
            updates = await load_memory({"messages": [HumanMessage("hi")]}, config=config)
            assert updates["memory_card"]
            msgs = updates.get("messages") or []
            assert any(isinstance(m, SystemMessage) for m in msgs)
        finally:
            set_store(None)
