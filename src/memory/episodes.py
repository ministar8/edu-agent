"""情节记忆读写：错题/练习轨迹（collection 型）。"""

from __future__ import annotations

import logging
import uuid

from langgraph.store.base import BaseStore

from memory.namespaces import episode_key, student_episodes_ns
from memory.schemas import Episode

logger = logging.getLogger(__name__)


def _coerce_episode(raw: object) -> Episode | None:
    if isinstance(raw, Episode):
        return raw
    try:
        return Episode.model_validate(raw)
    except Exception:
        logger.warning("跳过无法解析的 Episode 文档", exc_info=True)
        return None


async def aappend_episode(
    store: BaseStore,
    user_id: int | str,
    episode: Episode,
    *,
    episode_id: str | None = None,
) -> str:
    """追加一条情节记忆，返回使用的 episode_id。"""
    eid = episode_id or uuid.uuid4().hex
    await store.aput(student_episodes_ns(user_id), episode_key(eid), episode.model_dump())
    return eid


async def arecent_episodes(
    store: BaseStore,
    user_id: int | str,
    limit: int = 10,
) -> list[Episode]:
    """最近的情节记忆（按 at 降序，最多 limit 条）。

    未配置向量索引时 store.search 按插入序返回；这里再按时间排序兜底。
    """
    if limit <= 0:
        return []
    items = await store.asearch(student_episodes_ns(user_id), limit=limit)
    episodes: list[Episode] = []
    for item in items:
        ep = _coerce_episode(item.value)
        if ep is not None:
            episodes.append(ep)
    episodes.sort(key=lambda e: e.at, reverse=True)
    return episodes[:limit]
