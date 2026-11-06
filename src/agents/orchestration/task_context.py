"""多轮 task_mode 上下文（检索策略词表）。

读取优先级：
1. ContextVar
2. RunnableConfig.configurable.context_mode
3. LangGraph get_config（工具内部读取）

★ **ContextVar 只在一个节点的执行上下文内向后传播**（已实测）：
在 ``prepare_task`` 里设置，后续节点看不到；必须在 ``run_supervisor`` 里、
紧挨着 ``inner_supervisor.ainvoke`` 之前设置，内层图与其中工具才能读到。
节点之间的传递靠 ``TeachingState.context_mode``，不靠 ContextVar。

**跨 invoke 的持久值也不在这里**：它由 ``TeachingState.context_mode`` 承载
（线程生命周期，随 checkpoint 持久），由 ``prepare_task`` 写入。
本模块刻意**不再持有进程级字典** —— 旧实现 ``_THREAD_MODE`` 无界增长、
多 worker 各一份、重启即丢，且与 Store 双读。
"""

from __future__ import annotations

import logging
from contextvars import ContextVar

from langchain_core.runnables import RunnableConfig

logger = logging.getLogger(__name__)

_CONTEXT_VAR: ContextVar[str | None] = ContextVar("edu_task_context_mode", default=None)

_VALID = {"learn", "method", "practice", "grade", "explain", "verify"}


def set_context_mode(mode: str | None) -> None:
    if mode in _VALID:
        _CONTEXT_VAR.set(mode)


def get_context_mode(config: RunnableConfig | None = None) -> str | None:
    """读取多轮上下文 mode（供 Classifier / 检索工具用）。

    只读三条来源，不写任何缓存；线程级持久值在 ``TeachingState.context_mode``。
    """
    # 1) ContextVar（同任务内最优先）
    mode = _CONTEXT_VAR.get()
    if mode in _VALID:
        return mode

    # 2) RunnableConfig
    if config:
        conf = dict(config.get("configurable") or {})
        configured = conf.get("context_mode")
        if isinstance(configured, str) and configured in _VALID:
            return configured

    # 3) LangGraph get_config（工具内部无法拿到显式 config 时）
    try:
        from langgraph.config import get_config

        conf = dict((get_config() or {}).get("configurable") or {})
        configured = conf.get("context_mode")
        if isinstance(configured, str) and configured in _VALID:
            return configured
    except Exception:
        logger.debug("get_config for context_mode failed", exc_info=True)
    return None
