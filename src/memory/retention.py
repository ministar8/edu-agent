"""情节记忆保留策略：TTL + 每用户条数上限。

启动时全量扫一遍学生 episodes 命名空间并删除超限/过期项；
失败由调用方 safe_remember 吞掉，不影响服务启动。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from langgraph.store.base import BaseStore

from core.settings import settings
from memory.episodes import _coerce_episode
from memory.namespaces import student_episodes_ns
from memory.schemas import Episode

logger = logging.getLogger(__name__)


@dataclass
class CleanupStats:
    users: int = 0
    scanned: int = 0
    deleted_expired: int = 0
    deleted_over_cap: int = 0

    @property
    def deleted_total(self) -> int:
        return self.deleted_expired + self.deleted_over_cap


def _parse_iso(value: str) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


async def alist_episode_items(
    store: BaseStore, user_id: int | str, *, limit: int | None = None
) -> list[tuple[str, Episode]]:
    """列出 (store_key, Episode)。"""
    cap = limit if limit is not None else max(settings.MEMORY_EPISODE_MAX_PER_USER, 1) * 2
    cap = max(cap, 50)
    items = await store.asearch(student_episodes_ns(user_id), limit=cap)
    out: list[tuple[str, Episode]] = []
    for item in items:
        ep = _coerce_episode(item.value)
        if ep is not None:
            out.append((item.key, ep))
    return out


async def acleanup_user_episodes(
    store: BaseStore,
    user_id: int | str,
    *,
    ttl_days: int | None = None,
    max_per_user: int | None = None,
    now: datetime | None = None,
) -> CleanupStats:
    """按 TTL 与条数上限删除该用户的 episodes。"""
    ttl_days = settings.MEMORY_EPISODE_TTL_DAYS if ttl_days is None else ttl_days
    max_per_user = settings.MEMORY_EPISODE_MAX_PER_USER if max_per_user is None else max_per_user
    now = now or datetime.now(UTC)
    stats = CleanupStats(users=1)

    pairs = await alist_episode_items(store, user_id)
    stats.scanned = len(pairs)
    if not pairs:
        return stats

    # 按时间新→旧
    pairs.sort(key=lambda kv: kv[1].at, reverse=True)
    cutoff = now - timedelta(days=ttl_days) if ttl_days > 0 else None

    keep: list[tuple[str, Episode]] = []
    for key, ep in pairs:
        at = _parse_iso(ep.at)
        if cutoff is not None and at is not None and at < cutoff:
            await store.adelete(student_episodes_ns(user_id), key)
            stats.deleted_expired += 1
            continue
        keep.append((key, ep))

    if max_per_user > 0 and len(keep) > max_per_user:
        for key, _ep in keep[max_per_user:]:
            await store.adelete(student_episodes_ns(user_id), key)
            stats.deleted_over_cap += 1

    return stats


async def acleanup_all_student_episodes(
    store: BaseStore,
    *,
    namespace_limit: int = 500,
) -> CleanupStats:
    """遍历 student/*/episodes 并清理。"""
    total = CleanupStats()
    try:
        namespaces = await store.alist_namespaces(
            prefix=("student",),
            suffix=("episodes",),
            limit=namespace_limit,
        )
    except Exception:
        logger.warning("列出 episodes 命名空间失败", exc_info=True)
        return total

    for ns in namespaces:
        if len(ns) < 2:
            continue
        user_id = ns[1]
        try:
            part = await acleanup_user_episodes(store, user_id)
        except Exception:
            logger.warning("清理 user=%s episodes 失败", user_id, exc_info=True)
            continue
        total.users += part.users
        total.scanned += part.scanned
        total.deleted_expired += part.deleted_expired
        total.deleted_over_cap += part.deleted_over_cap

    if total.deleted_total:
        logger.info(
            "episodes 清理完成 users=%s scanned=%s expired=%s over_cap=%s",
            total.users,
            total.scanned,
            total.deleted_expired,
            total.deleted_over_cap,
        )
    return total
