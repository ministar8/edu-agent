"""记忆层：checkpointer（短期）+ Store 业务封装（长期）。

- 连接与 lifespan 挂载：`initialize_database` / `initialize_store`
- 业务读写长期记忆：经 `memory.profile` / `memory.episodes`，不要在 agents 里裸调 store
"""

from contextlib import AbstractAsyncContextManager

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from memory.episodes import aappend_episode, arecent_episodes
from memory.namespaces import (
    episode_key,
    student_episodes_ns,
    student_profile_ns,
)
from memory.profile import aget_profile, aupsert_profile
from memory.schemas import SCHEMA_VERSION, Episode, StudentProfile, utc_now_iso
from memory.sqlite import get_sqlite_saver, get_sqlite_store


def initialize_database() -> AbstractAsyncContextManager[AsyncSqliteSaver]:
    """初始化 checkpointer，返回异步上下文管理器。"""
    return get_sqlite_saver()


def initialize_store():
    """初始化长期记忆 store（SQLite 文件持久化）。"""
    return get_sqlite_store()


__all__ = [
    "SCHEMA_VERSION",
    "Episode",
    "StudentProfile",
    "aappend_episode",
    "aget_profile",
    "arecent_episodes",
    "aupsert_profile",
    "episode_key",
    "initialize_database",
    "initialize_store",
    "student_episodes_ns",
    "student_profile_ns",
    "utc_now_iso",
]
