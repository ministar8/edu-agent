"""memory.schemas 的契约单测：时间解析/截断/画像与情节模型的字段纪律。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from memory.schemas import SCHEMA_VERSION, Episode, StudentProfile, excerpt, parse_iso, utc_now_iso


def test_utc_now_iso_is_parsed_roundtrip() -> None:
    before = datetime.now(UTC)
    s = utc_now_iso()
    dt = parse_iso(s)
    after = datetime.now(UTC)
    assert dt is not None
    assert dt.tzinfo is not None
    assert before - timedelta(seconds=1) <= dt <= after + timedelta(seconds=1)


def test_parse_iso_keeps_explicit_offset() -> None:
    dt = parse_iso("2026-01-02T03:04:05+08:00")
    assert dt is not None
    assert dt.utcoffset() == timedelta(hours=8)


def test_parse_iso_naive_becomes_utc() -> None:
    dt = parse_iso("2026-01-02T03:04:05")
    assert dt is not None
    assert dt.tzinfo is UTC


def test_parse_iso_invalid_or_empty_returns_none() -> None:
    assert parse_iso("") is None
    assert parse_iso("不是时间") is None
    assert parse_iso("2026-13-99T00:00:00") is None


def test_excerpt_short_text_unchanged() -> None:
    assert excerpt("avl树") == "avl树"


def test_excerpt_long_text_hits_limit_with_ellipsis() -> None:
    text = "字" * 300
    out = excerpt(text)
    assert len(out) == 120
    assert out.endswith("…")
    assert out[:-1] == "字" * 119


def test_excerpt_respects_custom_limit() -> None:
    out = excerpt("字" * 300, 40)
    assert len(out) == 40
    assert out.endswith("…")


def test_profile_with_updates_rewrites_metadata() -> None:
    p = StudentProfile(level="unknown", weak_topics=["图"])
    updated = p.with_updates(level="beginner", weak_topics=["图", "堆"])
    assert updated.level == "beginner"
    assert updated.weak_topics == ["图", "堆"]
    assert updated.schema_version == SCHEMA_VERSION
    old_at, new_at = parse_iso(p.updated_at), parse_iso(updated.updated_at)
    assert old_at is not None and new_at is not None and new_at >= old_at


def test_profile_rejects_unknown_level() -> None:
    with pytest.raises(ValidationError):
        StudentProfile(level="master")


def test_episode_requires_type() -> None:
    with pytest.raises(ValidationError):
        Episode()  # type: ignore[call-arg]


def test_question_episode_allows_score_none() -> None:
    ep = Episode(type="question", topic="图")
    assert ep.score is None
    assert ep.knowledge_points == []
    assert ep.schema_version == SCHEMA_VERSION


def test_episode_topic_max_length_enforced() -> None:
    with pytest.raises(ValidationError):
        Episode(type="grade", score=1.0, topic="字" * 201)
