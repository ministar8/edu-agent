"""metrics 的共享低层 helper（从 metrics.py 拆出，行为等价）。"""

from __future__ import annotations

# 难度字符串 → 1–5 档（文档口径是 1–5；demo 集允许写 basic/medium/hard 便于人工标）
_DIFFICULTY_MAP: dict[str, int] = {
    "basic": 2,
    "easy": 1,
    "medium": 3,
    "mid": 3,
    "hard": 4,
    "difficult": 5,
}


def _norm(text: object) -> str:
    return str(text or "").strip().casefold()


def _as_difficulty(value: object) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        level = int(value)
        return level if 1 <= level <= 5 else None
    return _DIFFICULTY_MAP.get(str(value).strip().lower())
