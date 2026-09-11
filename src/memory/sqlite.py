from contextlib import AbstractAsyncContextManager, asynccontextmanager

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.store.memory import InMemoryStore

from core.settings import settings


def get_sqlite_saver() -> AbstractAsyncContextManager[AsyncSqliteSaver]:
    """初始化并返回 SQLite checkpointer。"""
    return AsyncSqliteSaver.from_conn_string(settings.SQLITE_DB_PATH)


class AsyncInMemoryStore:
    """InMemoryStore 的异步上下文管理器包装。"""

    def __init__(self):
        self.store = InMemoryStore()

    async def __aenter__(self):
        return self.store

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass

    async def setup(self):
        pass


@asynccontextmanager
async def get_sqlite_store():
    """长期记忆 store：SQLite 场景使用 InMemoryStore（对齐参考项目）。"""
    store_manager = AsyncInMemoryStore()
    yield await store_manager.__aenter__()
