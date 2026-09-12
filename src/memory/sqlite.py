from contextlib import AbstractAsyncContextManager, asynccontextmanager

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.store.sqlite.aio import AsyncSqliteStore

from core.settings import settings


def get_sqlite_saver() -> AbstractAsyncContextManager[AsyncSqliteSaver]:
    """初始化并返回 SQLite checkpointer。"""
    return AsyncSqliteSaver.from_conn_string(settings.SQLITE_DB_PATH)


@asynccontextmanager
async def get_sqlite_store():
    """长期记忆 store：独立 SQLite 文件（SQLITE_STORE_PATH），重启不丢。"""
    async with AsyncSqliteStore.from_conn_string(settings.SQLITE_STORE_PATH) as store:
        await store.setup()
        yield store
