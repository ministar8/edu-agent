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

from core import settings
from memory.episodes import aappend_episode
from memory.metering import meter_text
from memory.privacy import redact_pii
from memory.runtime import get_store
from memory.safe import safe_remember
from memory.schemas import AgentPath, Episode, excerpt
from memory.topics import normalize_topic, normalize_topics
from memory.weak_topics import a_recompute_weak_topics

logger = logging.getLogger(__name__)


def _sanitize_episode(payload: Episode) -> Episode:
    """写入前脱敏自由文本字段；topic/知识点走规范化，一般不含 PII。"""
    if not settings.MEMORY_PRIVACY_REDACT:
        return payload
    data = payload.model_dump()
    hits = 0
    for field in ("stem_excerpt", "error_analysis"):
        if field not in data:
            continue
        text, n = redact_pii(str(data.get(field) or ""))
        data[field] = text
        hits += n
    # meta 中的自由文本（若有）
    meta = dict(data.get("meta") or {})
    for k, v in list(meta.items()):
        if isinstance(v, str):
            nv, n = redact_pii(v)
            meta[k] = nv
            hits += n
    data["meta"] = meta
    if hits:
        logger.info("记忆写入前脱敏 %s 处 PII（%s）", hits, payload.type)
    return Episode.model_validate(data)


async def _record_episode(payload: Episode, *, user_id: int | str, label: str) -> str | None:
    store: BaseStore | None = get_store()
    if store is None:
        logger.debug("Store 未初始化，跳过记忆写入")
        return None

    cleaned = _sanitize_episode(payload)
    meter_text(label, cleaned.stem_excerpt, cleaned.error_analysis, cleaned.topic)

    result: dict[str, str] = {}

    async def _write() -> None:
        result["id"] = await aappend_episode(store, user_id, cleaned)
        if cleaned.type == "grade":
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


def _resolve_config(config: RunnableConfig | None) -> dict[str, Any]:
    """取 `configurable` 字典：**显式传入优先，缺失时回落到运行时上下文**。

    ★ 2026-10-06（Step 5 实测缺陷）：LangChain **不会**把运行时 ``RunnableConfig``
    注入到工具函数的 ``config`` 参数（实测：参数恒为 ``None``，而
    ``langgraph.config.get_config()`` 能拿到真值）。此前工具内只读参数，导致
    ``user_id`` 恒为 ``None`` ⇒ ``record_grade`` 的 ``if uid:`` 分支被**静默跳过**，
    批改成功却**一条 episode 都不写** ⇒ ``weak_topics`` 永远为空 ⇒ B 段永不召回。

    这类"成功但没落库"最难查：工具输出看着正常（``评分：40/100``），只有 Agent
    自己知道 `EPISODES: 0`。故此处把「参数 → 上下文」的回落**收敛到一处**，
    所有 ``*_from_config`` 共用，避免再次漏改。

    ★ 契约（2026-10-07 与并发实测一并定稿，改动前请先读）：
    - **整块替换，不做键级合并**：只要 ``config`` 带了非空 ``configurable``，
      就只信它 —— 显式 config 只写 ``thread_id`` 时，``user_id`` 结果是 ``None``
      （不会去运行时上下文里补）。仓内所有调用方都**同时**给两把键
      （``service.py:218`` 的 ``configurable`` / gate 的 ⑩a），故今天没有踩到这条；
      新增调用方若只传其一，请**显式传全**，不要指望回落帮你补 —— 补了反而更难归因。
    - **回落是安全的**：``get_config()`` 读的是 contextvar，asyncio 每个 Task 持有
      自己的 context 副本 ⇒ 并发请求各取各自的用户。实测：4 个 ``RunnableLambda``
      分别注入 U0~U3、内部 ``sleep`` 交错，两次阅读仍各自返回自己的 uid
      （护栏 ⑩e 固化这一点）。所以「参数为 None ⇒ 用上下文」不是「算到谁头上算谁的」，
      而是**当前那次 graph 调用的** config。
    """
    explicit = dict(config.get("configurable") or {}) if config else {}
    if explicit:
        return explicit
    try:
        from langgraph.config import get_config

        return dict((get_config() or {}).get("configurable") or {})
    except Exception:  # 非 LangGraph 运行时（如直接单测）时静默降级
        return {}


def user_id_from_config(config: RunnableConfig | None) -> str | None:
    """从 RunnableConfig 取 user_id（聊天工具用）。"""
    uid = _resolve_config(config).get("user_id")
    return str(uid) if uid is not None else None


def thread_id_from_config(config: RunnableConfig | None) -> str:
    conf = _resolve_config(config)
    tid = conf.get("thread_id")
    return str(tid) if tid is not None else ""


def batch_id_from_config(config: RunnableConfig | None) -> str:
    conf = _resolve_config(config)
    bid = conf.get("question_batch_id")
    return str(bid) if bid is not None else ""
