"""长期记忆 Store 命名空间工厂。

约定：`namespace = (域, 主体 id, 用途)`，id 一律 `str`（DB 里是 int，API/JWT 侧是 str）。
业务侧禁止手写元组，统一走本工厂，避免结构漂移。
"""

from __future__ import annotations

_NS_STUDENT = "student"
_KEY_PROFILE = "profile"
_KEY_EPISODES = "episodes"


def student_profile_ns(user_id: int | str) -> tuple[str, str, str]:
    """学生画像命名空间。"""
    return (_NS_STUDENT, str(user_id), _KEY_PROFILE)


def student_episodes_ns(user_id: int | str) -> tuple[str, str, str]:
    """学生情节记忆（错题/练习轨迹）命名空间。"""
    return (_NS_STUDENT, str(user_id), _KEY_EPISODES)


PROFILE_DOC_KEY = "profile"


def episode_key(episode_id: str) -> str:
    """单条 episode 的 store key。"""
    return f"ep-{episode_id}"
