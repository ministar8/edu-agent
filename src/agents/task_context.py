"""多轮 task_mode 上下文（LangGraph 贯通）。

存储优先级：
1. ContextVar（同轮内 tools 可见）
2. Store（thread 级，跨轮）
3. RunnableConfig.configurable.context_mode（服务层注入）

RETRIEVAL_POLICY §4.0：conversation context → explicit query → agent_prior → learn
"""

from __future__ import annotations

import logging
from contextvars import ContextVar

from langchain_core.runnables import RunnableConfig

logger = logging.getLogger(__name__)

_CONTEXT_VAR: ContextVar[str | None] = ContextVar("edu_task_context_mode", default=None)

_VALID = {"learn", "method", "practice", "grade", "explain", "verify"}


def _thread_id_from_config(config: RunnableConfig | None) -> str:
    if not config:
        return ""
    conf = dict(config.get("configurable") or {})
    return str(conf.get("thread_id") or "")


def set_context_mode(mode: str | None) -> None:
    if mode in _VALID:
        _CONTEXT_VAR.set(mode)


def get_context_mode(
    config: RunnableConfig | None = None,
    *,
    thread_id: str = "",
) -> str | None:
    """读取多轮上下文 mode（供 Classifier 用）。

    ⚠️ ContextVar 在 ainvoke 子任务里设置后**不一定**回传到调用方；
    跨调用请传 `thread_id`（或靠 Store/字典）。
    """
    # 1) ContextVar（同任务内最优先）
    m = _CONTEXT_VAR.get()
    if m in _VALID:
        return m
    # 2) 线程缓存
    tid = thread_id or _thread_id_from_config(config)
    if tid:
        tm = _store_get(tid)
        if tm in _VALID:
            return tm
    # 3) RunnableConfig
    if config:
        conf = dict(config.get("configurable") or {})
        cm = conf.get("context_mode")
        if isinstance(cm, str) and cm in _VALID:
            return cm
    # 4) LangGraph get_config
    try:
        from langgraph.config import get_config

        conf = dict((get_config() or {}).get("configurable") or {})
        cm = conf.get("context_mode")
        if isinstance(cm, str) and cm in _VALID:
            return cm
    except Exception:
        logger.debug("get_config for context_mode failed", exc_info=True)
    return None


# 线程级进程内缓存（Store 为异步 API，V1 用 dict + ContextVar 贯通）
_THREAD_MODE: dict[str, str] = {}


def _store_put(thread_id: str, mode: str) -> None:
    if thread_id and mode in _VALID:
        _THREAD_MODE[thread_id] = mode


def _store_get(thread_id: str) -> str | None:
    m = _THREAD_MODE.get(thread_id or "")
    return m if m in _VALID else None


def remember_query_mode(
    query: str,
    *,
    thread_id: str = "",
    config: RunnableConfig | None = None,
    context_mode: str | None = None,
) -> str:
    """对本轮 user query 分类并记住，返回当前 mode。

    ⚠️ 有 thread_id 时以**该线程 Store** 为准，避免把上一线程的 ContextVar 带进新线程。
    """
    from rag.task_policy import classify_task_mode

    tid = thread_id or _thread_id_from_config(config)
    if context_mode:
        prev = context_mode
    elif tid:
        prev = _store_get(tid) or (get_context_mode() if not thread_id else None)
    else:
        prev = get_context_mode(config) or _store_get(tid)
    mode = classify_task_mode(query, context_mode=prev)  # type: ignore[arg-type]
    set_context_mode(mode)
    _store_put(tid, mode)
    return mode


def load_thread_context(thread_id: str, config: RunnableConfig | None = None) -> str | None:
    """线程启动时把 Store 里的 mode 载入 ContextVar。"""
    tid = thread_id or _thread_id_from_config(config)
    m = _store_get(tid) or get_context_mode(config)
    if m in _VALID:
        set_context_mode(m)
        return m
    return None
