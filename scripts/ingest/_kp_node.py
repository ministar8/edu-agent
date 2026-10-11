"""KP 骨架的构造原语（`n` + 题型常量）；数据按科分在 `_kp_<科>.py`。"""

from __future__ import annotations


def n(
    id: str,
    name: str,
    parent: str | None,
    level: int,
    kind: str,
    typ: str,
    imp: str = "major",
    qtypes: list[str] | None = None,
    aliases: list[str] | None = None,
    tags: list[str] | None = None,
) -> dict:
    return {
        "id": id,
        "name": name,
        "subject": id.split(".", 1)[0],
        "parent_id": parent,
        "level": level,
        "node_kind": kind,
        "type": typ,
        "importance": imp,
        "typical_question_types": qtypes or ["choice"],
        "aliases": aliases or [],
        "tags": tags or [],
        "status": "active",
    }


ALL = ["choice", "calculation", "comprehensive", "code"]
CHOICE = ["choice"]
CHOICE_CALC = ["choice", "calculation"]
CHOICE_CODE = ["choice", "code"]
