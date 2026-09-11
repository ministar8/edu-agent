"""Thread 枚举：会话线程信息由 checkpointer 派生，不单独建表。"""

import logging
from typing import Any

from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig

from schema import ThreadSummary
from service.utils import convert_message_content_to_string, messages_from_checkpoint

logger = logging.getLogger(__name__)

# LangGraph 在每个 thread 首次写入时于 step -1 写 input checkpoint。
THREAD_HEAD_STEP = -1

MAX_THREAD_HEADS = 200
HEAD_PAGE_SIZE = 200
MAX_HEAD_ROWS = 1000

TITLE_MAX_LENGTH = 60


async def _list_thread_heads(checkpointer: Any, user_id: str, agent_id: str) -> list[Any]:
    """返回每个 thread 的 head checkpoint（新线程在前）。"""
    heads: list[Any] = []
    seen: set[str] = set()
    rows_scanned = 0
    before = None
    while len(seen) < MAX_THREAD_HEADS and rows_scanned < MAX_HEAD_ROWS:
        page = [
            c
            async for c in checkpointer.alist(
                None,
                filter={"user_id": user_id, "agent_id": agent_id, "step": THREAD_HEAD_STEP},
                before=before,
                limit=HEAD_PAGE_SIZE,
            )
        ]
        if not page:
            break
        rows_scanned += len(page)
        short_page = len(page) < HEAD_PAGE_SIZE
        for row in page:
            thread_id = row.config["configurable"]["thread_id"]
            if thread_id in seen:
                continue
            seen.add(thread_id)
            heads.append(row)
        if short_page:
            break
        before = RunnableConfig(
            configurable={"checkpoint_id": page[-1].config["configurable"]["checkpoint_id"]}
        )
    return heads


async def list_user_threads(
    checkpointer: Any, user_id: str, agent_id: str, limit: int
) -> list[ThreadSummary]:
    """列出某用户的会话线程（最近更新在前）。"""
    summaries: list[tuple[str, ThreadSummary]] = []
    for head in await _list_thread_heads(checkpointer, user_id, agent_id):
        thread_id = head.config["configurable"]["thread_id"]
        stored_user_id = head.metadata.get("user_id")
        stored_agent_id = head.metadata.get("agent_id")
        if stored_user_id != user_id or stored_agent_id != agent_id:
            logger.warning(
                "Checkpointer returned thread %s with user_id=%r/agent_id=%r, expected "
                "%r/%r — skipping to avoid cross-user leak.",
                thread_id,
                stored_user_id,
                stored_agent_id,
                user_id,
                agent_id,
            )
            continue

        tip = await checkpointer.aget_tuple(RunnableConfig(configurable={"thread_id": thread_id}))
        if tip is None:
            continue
        messages = messages_from_checkpoint(tip.checkpoint)
        first_human = next((m for m in messages if isinstance(m, HumanMessage)), None)
        summaries.append(
            (
                tip.config["configurable"]["checkpoint_id"],
                ThreadSummary(
                    thread_id=thread_id,
                    agent_id=agent_id,
                    updated_at=tip.checkpoint.get("ts"),
                    title=convert_message_content_to_string(first_human.content)[:TITLE_MAX_LENGTH]
                    if first_human
                    else None,
                ),
            )
        )

    summaries.sort(key=lambda item: item[0], reverse=True)
    return [summary for _, summary in summaries[:limit]]
