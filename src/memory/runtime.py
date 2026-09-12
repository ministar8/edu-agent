"""进程内 Store 引用：lifespan 注入，业务侧经 get_store() 取用。

避免在 agents/tools 里各自持有连接；未初始化时返回 None，调用方跳过记忆。
"""

from __future__ import annotations

from typing import Any

_store: Any | None = None


def set_store(store: Any | None) -> None:
    global _store
    _store = store


def get_store() -> Any | None:
    return _store
