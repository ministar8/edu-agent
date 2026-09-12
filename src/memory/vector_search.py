"""情节记忆语义检索：复用 Store 向量索引（RAG TEI embedding）。

向量未启用或 embed 失败时回退到时间序 `arecent_episodes`。
"""

from __future__ import annotations

import logging

from langgraph.store.base import BaseStore

from core.settings import settings
from memory.episodes import _coerce_episode, arecent_episodes
from memory.namespaces import student_episodes_ns
from memory.schemas import Episode

logger = logging.getLogger(__name__)


async def asearch_episodes(
    store: BaseStore,
    user_id: int | str,
    query: str,
    *,
    limit: int = 5,
) -> list[Episode]:
    """按语义相似检索 episodes；失败/未启用向量时回退最近列表。"""
    if limit <= 0:
        return []
    if not settings.MEMORY_STORE_VECTOR_ENABLED or not (query or "").strip():
        return await arecent_episodes(store, user_id, limit=limit)
    try:
        items = await store.asearch(student_episodes_ns(user_id), query=query, limit=limit)
    except Exception:
        logger.warning("episodes 向量检索失败，回退最近列表", exc_info=True)
        return await arecent_episodes(store, user_id, limit=limit)

    episodes: list[Episode] = []
    for item in items:
        ep = _coerce_episode(item.value)
        if ep is not None:
            episodes.append(ep)
    # 有 score 时可再按 score 排；SQLite store 一般已按相似度返回
    return episodes[:limit]
