from contextlib import AbstractAsyncContextManager

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from memory.sqlite import get_sqlite_saver, get_sqlite_store


def initialize_database() -> AbstractAsyncContextManager[AsyncSqliteSaver]:
    """初始化 checkpointer，返回异步上下文管理器。"""
    return get_sqlite_saver()


def initialize_store():
    """初始化长期记忆 store（SQLite 场景用 InMemoryStore）。"""
    return get_sqlite_store()


__all__ = ["initialize_database", "initialize_store"]
