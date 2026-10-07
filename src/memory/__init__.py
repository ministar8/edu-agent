"""记忆层：checkpointer（短期）+ Store 业务封装（长期）。

- 连接与 lifespan 挂载：`initialize_database` / `initialize_store`
- 业务读写：经 `memory.profile` / `memory.episodes` / `memory.remember`，
  不要在 agents 里裸调 store
"""

from contextlib import AbstractAsyncContextManager

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from memory.episodes import aappend_episode, arecent_episodes
from memory.metering import approx_tokens, meter_text
from memory.namespaces import (
    episode_key,
    student_episodes_ns,
    student_profile_ns,
)
from memory.privacy import redact_pii
from memory.profile import aget_profile, aupsert_profile
from memory.remember import record_grade, record_question
from memory.retention import acleanup_all_student_episodes, acleanup_user_episodes
from memory.runtime import get_store, set_store
from memory.safe import safe_remember
from memory.schemas import SCHEMA_VERSION, Episode, StudentProfile, utc_now_iso
from memory.sqlite import get_sqlite_saver, get_sqlite_store
from memory.topics import normalize_topic, normalize_topics
from memory.weak_topics import a_recompute_weak_topics, compute_weak_topics
from memory.window import trim_conversation
from memory.working import abuild_memory_card, format_memory_card


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
    "a_recompute_weak_topics",
    "aappend_episode",
    "abuild_memory_card",
    "acleanup_all_student_episodes",
    "acleanup_user_episodes",
    "aget_profile",
    "arecent_episodes",
    "aupsert_profile",
    "approx_tokens",
    "compute_weak_topics",
    "episode_key",
    "format_memory_card",
    "get_store",
    "initialize_database",
    "initialize_store",
    "meter_text",
    "normalize_topic",
    "normalize_topics",
    "record_grade",
    "record_question",
    "redact_pii",
    "safe_remember",
    "set_store",
    "student_episodes_ns",
    "student_profile_ns",
    "trim_conversation",
    "utc_now_iso",
]
