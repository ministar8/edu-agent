"""任务生命周期节点：prepare_task / finalize。

只依赖状态类型与 task_context，不 import supervisor 或模型客户端，便于单测。
"""

from __future__ import annotations

import uuid

from langchain_core.messages import AnyMessage, HumanMessage

from agents.state import TeachingState, has_final_answer
from schema.task_policy import TaskMode as RetrievalMode


def _last_human_text(messages: list[AnyMessage]) -> str:
    for message in reversed(messages):
        if isinstance(message, HumanMessage):
            return str(message.content or "")
    return ""


def _classify(query: str, previous: RetrievalMode | None) -> RetrievalMode | None:
    """从用户 query 识别检索策略模式；失败或无 query 时沿用上一轮。"""
    if not query:
        return previous
    try:
        from rag.retrieval.task_policy import classify_task_mode

        return classify_task_mode(query, context_mode=previous)
    except Exception:
        return previous


async def prepare_task(state: TeachingState, config=None) -> dict:
    """每次 invoke 开一个新任务：生成 task_id，重置任务字段；messages 不动。

    ``context_mode`` 是线程级字段：从恢复的 state 读上一轮值，分类后写回，不随任务重置。
    """
    conf = dict((config or {}).get("configurable") or {})
    thread_id = str(conf.get("thread_id") or "")
    request_id = str(conf.get("request_id") or "") or str(uuid.uuid4())

    ctx_mode = _classify(
        _last_human_text(state.get("messages") or []),
        state.get("context_mode"),
    )
    # 不在这里 set_context_mode：实测 ContextVar 不跨节点传播，
    # 真正生效的位置是 run_supervisor 里紧挨着 ainvoke 之前（见 teaching_graph.py）。

    return {
        "task_id": f"{thread_id}:{request_id}",
        "task_mode": "unknown",
        "task_context": {},
        "context_mode": ctx_mode,
        "active_agent": None,
        "task_status": "pending",
        "task_result": None,
        "error": None,
    }


async def finalize(state: TeachingState, config=None) -> dict:
    """正常路径收尾：有终答才算 completed，否则记 EMPTY_RESULT。"""
    if has_final_answer(state.get("messages") or []):
        return {"task_status": "completed"}
    return {
        "task_status": "failed",
        "error": {
            "code": "EMPTY_RESULT",
            "message": "本轮没有产出可返回的结果",
            "stage": "finalize",
            "recoverable": True,
        },
    }
