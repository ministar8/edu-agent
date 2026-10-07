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
    allow_legacy_fallback: bool = True,
) -> list[str]:
    """纯函数：从批改 episodes 计算薄弱知识点列表。

    ★ 2026-10-06 Phase 1.5 修复：**聚合单位从「单值 topic」改为「knowledge_points 列表」**。

    此前只消费 `e.topic`（写入时是 `stem[:80]` 题干截断）⇒ 记忆里存的是
    「某道题的开头」而不是「用户在哪个知识点上薄弱」，且**一道题命中多个考点时只能记一个**。

    现在：**一条 episode 的每个 KP 各累计一次 hit**：

        一道题 → knowledge_points = ["AVL树", "二叉搜索树"]
                 ⇒ AVL树 weak+=1、二叉搜索树 weak+=1（而不是只记第一个）

    ``allow_legacy_fallback``：
      - ``True``（默认）→ `knowledge_points` 为空时**回落到 `e.topic`**，兼容旧数据；
      - ``False`` → **完全忽略旧 topic**。**Phase 1.5 评测必须传 False**，
        否则旧数据会重新产生 `weak_topics = ["已知一棵二叉排序树……"]` 这类
        **题干片段**，把历史错误语义带进新指标（评测污染）。
    """
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

    # 按规范化 KP 聚合：**每条 episode 的每个 KP 各计一次**
    stats: dict[str, dict[str, int]] = {}
    for e in windowed:
        topics = [t for t in (normalize_topic(k) for k in (e.knowledge_points or [])) if t]
        if not topics:
            # 新路径无 KP：仅当允许时才回落旧 topic（题干截断）
            if not allow_legacy_fallback:
                continue
            legacy = normalize_topic(e.topic or e.stem_excerpt)
            topics = [legacy] if legacy else []
        score = float(e.score or 0)
        for topic in topics:
            bucket = stats.setdefault(topic, {"weak": 0, "good": 0})
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
