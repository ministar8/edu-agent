"""自动拆分自 splitter.py（行为等价）。"""

from __future__ import annotations

import re

_HEADING_RE = re.compile(r"^(#{1,4})\s+(.+)$", re.MULTILINE)


def _extract_headings(text: str) -> list[dict]:
    return [
        {
            "level": len(match.group(1)),
            "title": match.group(2).strip(),
            "start": match.start(),
            "end": match.end(),
        }
        for match in _HEADING_RE.finditer(text)
    ]


def _build_heading_context(headings: list[dict], position: int) -> str:
    active: dict[int, str] = {}
    for item in headings[: position + 1]:
        level = item["level"]
        title = item["title"]
        if level <= 4:
            active = {k: v for k, v in active.items() if k < level}
            active[level] = title

    if not active:
        return ""

    path = " > ".join(active[k] for k in sorted(active.keys()))
    return f"[{path}]"


def _split_into_sections(text: str, headings: list[dict]) -> list[dict]:
    if not headings:
        return [
            {
                "text": text,
                "heading": "",
                "heading_level": 0,
                "heading_path": "",
                "section_index": 0,
            }
        ]

    sections: list[dict] = []
    first_heading_start = headings[0]["start"]
    if text[:first_heading_start].strip():
        sections.append(
            {
                "text": text[:first_heading_start].strip(),
                "heading": "",
                "heading_level": 0,
                "heading_path": "",
                "section_index": 0,
            }
        )

    for index, heading in enumerate(headings):
        next_start = headings[index + 1]["start"] if index + 1 < len(headings) else len(text)
        section_text = text[heading["start"] : next_start].strip()
        if not section_text:
            continue
        sections.append(
            {
                "text": section_text,
                "heading": heading["title"],
                "heading_level": heading["level"],
                "heading_path": _build_heading_context(headings, index),
                "section_index": len(sections),
            }
        )
    return sections
