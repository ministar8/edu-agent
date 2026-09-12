"""由 episodes 派生 weak_topics（阈值 + 时间窗 + 次数防抖）。

episodes 是事实源；profile.weak_topics 只是缓存摘要，禁止业务手改列表。
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from langgraph.store.base import BaseStore

from core.settings import settings
from memory.episodes import arecent_episodes
from memory.profile import aget_profile, aupsert_profile
from memory.schemas import Episode, parse_iso
from memory.topics import normalize_topic

logger = logging.getLogger(__name__)


def _in_window(ep: Episode, now: datetime, days: int) -> bool:
    at = parse_iso(ep.at)
    if at is None:
        return False
    return at >= now - timedelta(days=days)


def compute_weak_topics(
    grade_episodes: list[Episode],
    *,
    weak_score: float | None = None,
    good_score: float | None = None,
    window_days: int | None = None,
    min_weak_hits: int | None = None,
    min_good_hits: int | None = None,
) -> list[str]:
    """纯函数：从批改 episodes 计算薄弱知识点列表。"""
    weak_score = settings.MEMORY_WEAK_SCORE if weak_score is None else weak_score
    good_score = settings.MEMORY_GOOD_SCORE if good_score is None else good_score
    window_days = settings.MEMORY_WEAK_WINDOW_DAYS if window_days is None else window_days
    min_weak_hits = settings.MEMORY_WEAK_MIN_HITS if min_weak_hits is None else min_weak_hits
    min_good_hits = (
        settings.MEMORY_WEAK_CLEAR_MIN_GOOD_HITS if min_good_hits is None else min_good_hits
    )

    now = datetime.now(UTC)
    windowed = [
        e for e in grade_episodes if e.score is not None and _in_window(e, now, window_days)
    ]

    # 按规范化 topic 聚合；topic 空则用 stem 摘录兜底
    stats: dict[str, dict[str, int]] = {}
    for e in windowed:
        topic = normalize_topic(e.topic or e.stem_excerpt)
        if not topic:
            continue
        bucket = stats.setdefault(topic, {"weak": 0, "good": 0})
        score = float(e.score or 0)
        if score < weak_score:
            bucket["weak"] += 1
        elif score >= good_score:
            bucket["good"] += 1

    weak: list[str] = []
    for topic, bucket in stats.items():
        # 连续足够多的好成绩 → 移出薄弱（用 good 次数近似，避免依赖顺序）
        if bucket["good"] >= min_good_hits and bucket["weak"] < min_weak_hits:
            continue
        if bucket["weak"] >= min_weak_hits:
            weak.append(topic)
    return weak


async def a_recompute_weak_topics(store: BaseStore, user_id: int | str) -> list[str]:
    """重算并写回 profile.weak_topics。"""
    episodes = await arecent_episodes(store, user_id, limit=settings.MEMORY_EPISODE_SCAN_LIMIT)
    grades = [e for e in episodes if e.type == "grade"]
    weak = compute_weak_topics(grades)
    profile = await aget_profile(store, user_id)
    if profile.weak_topics != weak:
        profile = await aupsert_profile(store, user_id, weak_topics=weak)
        logger.info("weak_topics 已更新 user=%s → %s", user_id, weak)
    return weak
