from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import Any

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.store.sqlite.aio import AsyncSqliteStore

from core.settings import settings


def get_sqlite_saver() -> AbstractAsyncContextManager[AsyncSqliteSaver]:
    """初始化并返回 SQLite checkpointer。"""
    return AsyncSqliteSaver.from_conn_string(settings.SQLITE_DB_PATH)


def _store_index_config() -> Any | None:
    """向量索引配置：复用 RAG TEI embedding；未启用时返回 None。"""
    if not settings.MEMORY_STORE_VECTOR_ENABLED:
        return None
    from rag.embeddings import get_embeddings

    return {
        "dims": int(settings.EMBEDDING_DIM),
        "embed": get_embeddings(),
        "fields": ["search_text"],
    }


@asynccontextmanager
async def get_sqlite_store():
    """长期记忆 store：独立 SQLite 文件（SQLITE_STORE_PATH），重启不丢。

    向量索引启用时写入会多一次 TEI embed（失败由 safe_remember 吞掉）。
    注意：已有无索引 store.db 再开索引可能需删库重建。
    """
    index = _store_index_config()
    async with AsyncSqliteStore.from_conn_string(settings.SQLITE_STORE_PATH, index=index) as store:
        await store.setup()
        yield store
