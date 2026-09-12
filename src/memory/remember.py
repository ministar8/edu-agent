"""业务侧记忆写入口：append episode + 重算 weak_topics。

topic / knowledge_points 一律先 normalize_topic；question↔grade 用 batch_id /
question_id / ref_episode_id 显式外键。
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from langchain_core.runnables import RunnableConfig
from langgraph.store.base import BaseStore

from memory.episodes import aappend_episode
from memory.runtime import get_store
from memory.safe import safe_remember
from memory.schemas import AgentPath, Episode, excerpt
from memory.topics import normalize_topic, normalize_topics
from memory.weak_topics import a_recompute_weak_topics

logger = logging.getLogger(__name__)


async def _record_episode(payload: Episode, *, user_id: int | str, label: str) -> str | None:
    store: BaseStore | None = get_store()
    if store is None:
        logger.debug("Store 未初始化，跳过记忆写入")
        return None

    result: dict[str, str] = {}

    async def _write() -> None:
        result["id"] = await aappend_episode(store, user_id, payload)
        if payload.type == "grade":
            await a_recompute_weak_topics(store, user_id)

    await safe_remember(_write, label=label)
    return result.get("id")


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
    batch_id: str = "",
    question_id: str = "",
    ref_episode_id: str = "",
) -> str | None:
    """写入批改 episode，返回 episode_id（失败为 None）。"""
    return await _record_episode(
        Episode(
            type="grade",
            topic=normalize_topic(topic)[:200],
            score=score,
            error_analysis=error_analysis[:500],
            thread_id=thread_id,
            run_id=run_id,
            stem_excerpt=excerpt(stem),
            knowledge_points=normalize_topics(knowledge_points),
            agent_path=agent_path,
            batch_id=batch_id,
            question_id=question_id,
            ref_episode_id=ref_episode_id,
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
    batch_id: str | None = None,
) -> tuple[str | None, str]:
    """写入出题 episode；返回 (episode_id, batch_id)。

    batch_id 未传则生成，应与 QuestionResponse.batch_id 一致，供后续 grade 外键引用。
    """
    bid = batch_id or uuid.uuid4().hex
    eid = await _record_episode(
        Episode(
            type="question",
            topic=normalize_topic(topic)[:200],
            thread_id=thread_id,
            knowledge_points=normalize_topics(knowledge_points),
            agent_path=agent_path,
            batch_id=bid,
            meta={"count": count} if count is not None else {},
        ),
        user_id=user_id,
        label="question",
    )
    return eid, bid


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


def batch_id_from_config(config: RunnableConfig | None) -> str:
    if not config:
        return ""
    configurable: dict[str, Any] = dict(config.get("configurable") or {})
    bid = configurable.get("question_batch_id")
    return str(bid) if bid is not None else ""
