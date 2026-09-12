"""工作记忆卡：从 profile + 最近 grade episodes 程序侧聚合（非 LLM 总结）。

带语义锚点、长度硬切、空画像不产出 —— 避免无效 token 与注意力污染。
"""

from __future__ import annotations

import logging

from langgraph.store.base import BaseStore

from core.settings import settings
from memory.episodes import arecent_episodes
from memory.profile import aget_profile
from memory.schemas import excerpt
from memory.topics import normalize_topic

logger = logging.getLogger(__name__)

_MAX_CARD_CHARS = 200
_MAX_WEAK = 3


def format_memory_card(
    *,
    weak_lines: list[str],
    preferred_style: str = "",
) -> str:
    """拼装记忆卡；无内容时返回空串（调用方不得注入）。"""
    parts: list[str] = []
    if weak_lines:
        shown = weak_lines[:_MAX_WEAK]
        parts.append("薄弱：" + "；".join(shown))
    if preferred_style.strip():
        parts.append(f"风格：{preferred_style.strip()}")
    if not parts:
        return ""
    card = "【学生记忆】\n" + "\n".join(parts)
    if len(card) > _MAX_CARD_CHARS:
        card = card[: _MAX_CARD_CHARS - 1] + "…"
    return card


def build_weak_lines_from_grades(
    grade_topics: list[str], grades_by_topic: dict[str, list]
) -> list[str]:
    """weak topic → 「名称（最近分/题干锚点）」。grades 为该 topic 的 grade episodes。"""
    lines: list[str] = []
    for topic in grade_topics:
        eps = grades_by_topic.get(topic) or []
        if not eps:
            lines.append(topic)
            continue
        last = eps[0]  # 调用方保证按时间新→旧
        score = int(last.score) if last.score is not None else "?"
        anchor = excerpt(last.stem_excerpt or last.topic, 40)
        lines.append(f"{topic}（最近{score}分，「{anchor}」）")
    return lines


async def abuild_memory_card(store: BaseStore | None, user_id: int | str) -> str:
    """读 profile + 最近 grade，生成记忆卡；任何失败返回空串。"""
    if store is None or user_id is None or user_id == "":
        return ""
    try:
        profile = await aget_profile(store, user_id)
        weak: list[str] = []
        for t in profile.weak_topics:
            nt = normalize_topic(t)
            if nt:
                weak.append(nt)
        if not weak and not profile.preferred_style.strip():
            return ""
        grades_by_topic: dict[str, list] = {}
        if weak:
            episodes = await arecent_episodes(
                store, user_id, limit=settings.MEMORY_EPISODE_SCAN_LIMIT
            )
            grades = [e for e in episodes if e.type == "grade" and e.score is not None]
            grades.sort(key=lambda e: e.at, reverse=True)
            for e in grades:
                t = normalize_topic(e.topic or e.stem_excerpt)
                if t:
                    grades_by_topic.setdefault(t, []).append(e)
        lines = build_weak_lines_from_grades(weak, grades_by_topic)
        return format_memory_card(weak_lines=lines, preferred_style=profile.preferred_style)
    except Exception:
        logger.warning("构建记忆卡失败，本轮不注入", exc_info=True)
        return ""
