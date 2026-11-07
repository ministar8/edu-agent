"""memory.remember 纯逻辑与写入口契约单测（不依赖真实 Store / LangGraph 运行时）。

关键契约（remember.py 内 docstring 定稿）：
- `_resolve_config` 是**整块替换**：显式 configurable 非空时只信它，
  缺 user_id 时不得回落运行时上下文补；
- 非 LangGraph 运行时（直接单测）一切回落函数静默降级，不抛错；
- Store 未初始化 → 写入安全跳过（返回 None），绝不拖垮主流程。
"""

from __future__ import annotations

import pytest

import memory.runtime as runtime
from core.settings import settings
from memory.remember import (
    _sanitize_episode,
    batch_id_from_config,
    record_grade,
    record_question,
    thread_id_from_config,
    user_id_from_config,
)
from memory.schemas import Episode

PII_STEM = "手机15812345678"
PII_ANALYSIS = "邮箱x@y.com"
PII_META = {"note": "身份证11010119900307457X"}


def pii_episode() -> Episode:
    return Episode(
        type="grade",
        topic="死锁",
        score=40.0,
        stem_excerpt=PII_STEM,
        error_analysis=PII_ANALYSIS,
        meta=dict(PII_META),
    )


def test_sanitize_episode_redacts_when_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "MEMORY_PRIVACY_REDACT", True)
    cleaned = _sanitize_episode(pii_episode())
    assert "[手机已脱敏]" in cleaned.stem_excerpt
    assert "[邮箱已脱敏]" in cleaned.error_analysis
    assert "[身份证已脱敏]" in cleaned.meta["note"]
    # 非自由文本字段不得被误改
    assert cleaned.topic == "死锁"
    assert cleaned.score == 40.0
    # 整数值 / 非字符串 meta 不受影响
    assert cleaned.type == "grade"


def test_sanitize_episode_passthrough_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "MEMORY_PRIVACY_REDACT", False)
    out = _sanitize_episode(pii_episode())
    assert out.stem_excerpt == PII_STEM
    assert out.error_analysis == PII_ANALYSIS
    assert out.meta["note"] == PII_META["note"]


def test_config_explicit_full_block_wins() -> None:
    conf = {"configurable": {"user_id": 7, "thread_id": "t1", "question_batch_id": "B1"}}
    assert user_id_from_config(conf) == "7"
    assert thread_id_from_config(conf) == "t1"
    assert batch_id_from_config(conf) == "B1"


def test_config_partial_block_is_whole_replacement_no_fallback() -> None:
    # 整块替换契约：显式 configurable 只带 thread_id ⇒ user_id 是 None，
    # **不得**去运行时上下文补——补了反而更难归因（docstring 明文禁止）。
    conf = {"configurable": {"thread_id": "t1"}}
    assert thread_id_from_config(conf) == "t1"
    assert user_id_from_config(conf) is None
    assert batch_id_from_config(conf) == ""


def test_config_none_outside_runtime_degrades_silently() -> None:
    assert user_id_from_config(None) is None
    assert thread_id_from_config(None) == ""
    assert batch_id_from_config(None) == ""


@pytest.mark.asyncio
async def test_record_grade_without_store_skips_safely(monkeypatch: pytest.MonkeyPatch) -> None:
    runtime.set_store(None)
    monkeypatch.setattr(settings, "MEMORY_PRIVACY_REDACT", True)
    eid = await record_grade(user_id=1, topic="死锁", score=40.0)
    assert eid is None


@pytest.mark.asyncio
async def test_record_question_returns_batch_id_even_without_store(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime.set_store(None)
    monkeypatch.setattr(settings, "MEMORY_PRIVACY_REDACT", True)
    eid, bid = await record_question(user_id=1, topic="图")
    assert eid is None
    assert bid and len(bid) == 32 and all(c in "0123456789abcdef" for c in bid)

    eid2, same_bid = await record_question(user_id=1, topic="图", batch_id="B123")
    assert eid2 is None
    assert same_bid == "B123"
