"""隐私脱敏与记忆计量。"""

import pytest

from memory.metering import approx_tokens, meter_text
from memory.privacy import redact_pii
from memory.remember import _sanitize_episode
from memory.runtime import set_store
from memory.schemas import Episode
from memory.sqlite import get_sqlite_store


def test_redact_phone_id_email():
    text = "联系我 13812345678，身份证 110101199001011234，邮箱 a@b.com"
    out, hits = redact_pii(text)
    assert "13812345678" not in out
    assert "110101199001011234" not in out
    assert "a@b.com" not in out
    assert hits >= 3
    assert "[手机已脱敏]" in out


def test_redact_no_pii():
    out, hits = redact_pii("进程死锁的四个必要条件")
    assert out == "进程死锁的四个必要条件"
    assert hits == 0


def test_approx_tokens():
    assert approx_tokens("") == 0
    assert approx_tokens("死锁") == 2
    assert approx_tokens("abcd") == 1


def test_sanitize_episode_stem():
    ep = Episode(
        type="grade",
        topic="进程死锁",
        score=50,
        stem_excerpt="我的手机 13900001111",
        error_analysis="无",
    )
    out = _sanitize_episode(ep)
    assert "13900001111" not in out.stem_excerpt
    assert "手机已脱敏" in out.stem_excerpt


def test_meter_text_fields():
    m = meter_text("grade", "题干", "反馈")
    assert m.chars == 4
    assert m.approx_tokens >= 1


@pytest.mark.asyncio
async def test_record_grade_redacts_before_store(tmp_path, monkeypatch):
    from core import settings as settings_singleton

    monkeypatch.setattr(settings_singleton, "SQLITE_STORE_PATH", str(tmp_path / "store.db"))
    async with get_sqlite_store() as store:
        set_store(store)
        try:
            from memory.episodes import arecent_episodes
            from memory.remember import record_grade

            await record_grade(
                user_id=1,
                topic="进程死锁",
                score=40,
                stem="手机 13800002222",
                agent_path="api_grade",
            )
            eps = await arecent_episodes(store, 1, limit=5)
            assert "13800002222" not in eps[0].stem_excerpt
        finally:
            set_store(None)
