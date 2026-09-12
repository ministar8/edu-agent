"""业务侧记忆写入口：append episode + 重算 weak_topics。"""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.runnables import RunnableConfig
from langgraph.store.base import BaseStore

from memory.episodes import aappend_episode
from memory.runtime import get_store
from memory.safe import safe_remember
from memory.schemas import AgentPath, Episode, excerpt
from memory.weak_topics import a_recompute_weak_topics

logger = logging.getLogger(__name__)


async def _record_episode(payload: Episode, *, user_id: int | str, label: str) -> None:
    store: BaseStore | None = get_store()
    if store is None:
        logger.debug("Store 未初始化，跳过记忆写入")
        return

    async def _write() -> None:
        await aappend_episode(store, user_id, payload)
        if payload.type == "grade":
            await a_recompute_weak_topics(store, user_id)

    await safe_remember(_write, label=label)


async def record_grade(
    *,
    user_id: int | str,
    topic: str,
    score: float,
    error_analysis: str = "",
    stem: str = "",
    thread_id: str = "",
    run_id: str = "",
    knowledge_points: list[str] | None = None,
    agent_path: AgentPath = "api_grade",
) -> None:
    await _record_episode(
        Episode(
            type="grade",
            topic=topic[:200],
            score=score,
            error_analysis=error_analysis[:500],
            thread_id=thread_id,
            run_id=run_id,
            stem_excerpt=excerpt(stem),
            knowledge_points=list(knowledge_points or []),
            agent_path=agent_path,
        ),
        user_id=user_id,
        label="grade",
    )


async def record_question(
    *,
    user_id: int | str,
    topic: str,
    thread_id: str = "",
    knowledge_points: list[str] | None = None,
    agent_path: AgentPath = "api_question",
    count: int | None = None,
) -> None:
    await _record_episode(
        Episode(
            type="question",
            topic=topic[:200],
            thread_id=thread_id,
            knowledge_points=list(knowledge_points or []),
            agent_path=agent_path,
            meta={"count": count} if count is not None else {},
        ),
        user_id=user_id,
        label="question",
    )


def user_id_from_config(config: RunnableConfig | None) -> str | None:
    """从 RunnableConfig 取 user_id（聊天工具用）。"""
    if not config:
        return None
    configurable: dict[str, Any] = dict(config.get("configurable") or {})
    uid = configurable.get("user_id")
    return str(uid) if uid is not None else None


def thread_id_from_config(config: RunnableConfig | None) -> str:
    if not config:
        return ""
    configurable: dict[str, Any] = dict(config.get("configurable") or {})
    tid = configurable.get("thread_id")
    return str(tid) if tid is not None else ""
