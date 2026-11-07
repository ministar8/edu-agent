"""memory.weak_topics 的派生逻辑单测（纯函数域，全量显式阈值，不依赖 settings 数值）。

核心语义（Phase 1.5）：
- 聚合单位是 knowledge_points 列表，**一条 episode 的每个 KP 各计一次**；
- allow_legacy_fallback=False 时旧 topic（题干截断）必须完全不进 weak_topics；
- 连续好成绩（good ≥ min_good_hits 且 weak < min_weak_hits）→ 移出薄弱池。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from memory.schemas import Episode, utc_now_iso
from memory.weak_topics import (
    _aggregate_kp_stats,
    _in_window,
    _resolve_weak_thresholds,
    compute_weak_topics,
)

# 显式阈值，让测试与 settings 调参解耦
P = {"weak_score": 40.0, "good_score": 80.0, "window_days": 30, "min_weak_hits": 1, "min_good_hits": 2}


def ep(  # noqa: PLR0913 — 测试构造器
    *,
    score: float | None,
    kps: list[str] | None = None,
    topic: str = "",
    at: str | None = None,
) -> Episode:
    return Episode(
        type="grade",
        score=score,
        knowledge_points=kps or [],
        topic=topic,
        at=at or utc_now_iso(),
    )


def old_at(days: int) -> str:
    return (datetime.now(UTC) - timedelta(days=days)).isoformat()


def test_in_window_inclusive_boundary() -> None:
    now = datetime.now(UTC)
    e = ep(score=10, at=(now - timedelta(days=30)).isoformat())
    assert _in_window(e, now, 30) is True  # 恰好等于窗口边界：含入
    assert _in_window(e, now, 29) is False


def test_in_window_rejects_unparseable_at() -> None:
    e = ep(score=10, at="不是时间")
    assert _in_window(e, datetime.now(UTC), 30) is False


def test_resolve_weak_thresholds_falls_back_to_settings() -> None:
    from core.settings import settings

    weak, good, days, min_weak, min_good = _resolve_weak_thresholds(
        None, None, None, None, None
    )
    # 单一真源断言：回落值必须逐项等于 settings，而 settings 本身是文档化的缺省
    assert weak == settings.MEMORY_WEAK_SCORE == 60.0
    assert good == settings.MEMORY_GOOD_SCORE == 85.0
    assert days == settings.MEMORY_WEAK_WINDOW_DAYS == 30
    assert min_weak == settings.MEMORY_WEAK_MIN_HITS == 2
    assert min_good == settings.MEMORY_WEAK_CLEAR_MIN_GOOD_HITS == 2


def test_resolve_weak_thresholds_explicit_wins() -> None:
    assert _resolve_weak_thresholds(20.0, 70.0, 7, 3, 4) == (20.0, 70.0, 7, 3, 4)


def test_each_kp_of_one_episode_counts_once() -> None:
    eps = [ep(score=20, kps=["AVL树", "Hash表"])]
    weak = compute_weak_topics(eps, **P)
    # 两个 KP 经归一化分别成桶（平衡二叉树/散列表），各 +1 weak ⇒ 都进薄弱
    assert sorted(weak) == ["平衡二叉树", "散列表"]


def test_aggregate_kp_stats_buckets_are_independent() -> None:
    windowed = [
        ep(score=90, kps=["AVL树"]),   # good +1
        ep(score=20, kps=["AVL树"]),   # weak +1
        ep(score=60, kps=["AVL树"]),   # 中间分：两桶都不计
    ]
    stats = _aggregate_kp_stats(windowed, weak_score=40.0, good_score=80.0, allow_legacy_fallback=False)
    assert stats == {"平衡二叉树": {"weak": 1, "good": 1}}


def test_legacy_fallback_true_uses_topic_when_no_kp() -> None:
    eps = [ep(score=20, topic="题干片段abc")]
    weak = compute_weak_topics(eps, **P)
    assert weak == ["题干片段abc"]


def test_legacy_fallback_false_ignores_old_topic() -> None:
    # Phase 1.5 评测污染防线：旧数据的题干片段不得以 KP 语义进新指标
    eps = [ep(score=20, topic="已知一棵二叉排序树……")]
    weak = compute_weak_topics(eps, **{**P, "allow_legacy_fallback": False})
    assert weak == []


def test_good_streak_clears_weak_topic() -> None:
    eps = [ep(score=90, kps=["AVL树"]), ep(score=85, kps=["AVL树"])]
    weak = compute_weak_topics(eps, **P)
    assert weak == []


def test_good_hits_do_not_clear_when_weak_hits_still_meet_threshold() -> None:
    # weak=2 ≥ min_weak_hits ⇒ 即使 good=2 也仍在薄弱池（原则：weak 优先）
    eps = [
        ep(score=20, kps=["AVL树"]),
        ep(score=10, kps=["AVL树"]),
        ep(score=90, kps=["AVL树"]),
        ep(score=85, kps=["AVL树"]),
    ]
    weak = compute_weak_topics(eps, **P)
    assert weak == ["平衡二叉树"]


def test_score_none_and_mid_band_episodes_count_nowhere() -> None:
    eps = [ep(score=None, kps=["AVL树"]), ep(score=60, kps=["AVL树"])]
    assert compute_weak_topics(eps, **P) == []


def test_out_of_window_episodes_excluded() -> None:
    eps = [ep(score=10, kps=["AVL树"], at=old_at(31))]
    assert compute_weak_topics(eps, **P) == []


def test_kp_alias_normalized_before_aggregation() -> None:
    eps = [ep(score=10, kps=["deadlock"]), ep(score=15, kps=["死锁"])]
    stats = _aggregate_kp_stats(eps, weak_score=40.0, good_score=80.0, allow_legacy_fallback=False)
    # 别名 episode 与 canonical episode 必须汇入同一桶，而不是裂成两条
    assert list(stats) == ["死锁"]


def test_min_weak_hits_gates_entry() -> None:
    eps = [ep(score=10, kps=["AVL树"])]  # weak=1 < min_weak_hits=1? 恰等 1 ≥ 1 ⇒ 进
    assert compute_weak_topics(eps, **P) == ["平衡二叉树"]
    eps2 = [ep(score=10, kps=["AVL树"]), ep(score=90, kps=["AVL树"])]  # weak=1, good=1
    # good=1 < min_good_hits=2 ⇒ 不满足"移出"条件；weak=1 ≥ 1 ⇒ 进薄弱
    assert compute_weak_topics(eps2, **P) == ["平衡二叉树"]
