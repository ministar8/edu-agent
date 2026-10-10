"""自动拆分自 cleaner.py（行为等价）。"""

from __future__ import annotations

import re

from rag.chunking.cleaner._text import (
    _FENCE_RE,
    _LINE_TRIM_RE,
    _collapse_blank_lines,
    _normalize_text,
)

_WEB_NOISE_MARKERS = (
    ".choice-container",
    ".choice-option",
    ".choice-inline",
    ".choice-text",
    ".explanation",
    ".feedback-area",
    ".multiple-choice-hint",
    "@media(",
    "@keyframes",
    "document.addEventListener",
    "querySelector",
    "localStorage",
    "window.quizChoiceFlag",
    "setupChoiceEventListeners",
    "restoreChoices()",
    "saveChoiceToLocalStorage",
)

_WEB_NOISE_LINE_RE = re.compile(
    r"(?:querySelector|addEventListener|localStorage|document\.|window\.|"
    r"choice-container|choice-option|feedback-area|multiple-choice-hint|"
    r"@media|@keyframes)"
)

_INLINE_EXAM_HEADING_RE = re.compile(r"(?<!\n)(#{4,5}\s*\d+\s*)")


def _clean_markdown_text(text: str) -> str:
    normalized = _normalize_text(text)
    if not normalized:
        return ""
    # 逐行去行尾空白；代码围栏内外的处理目前相同（历史上曾按 in_fence 分叉，
    # 现三分支体一致，故不再维护 in_fence —— 若将来要保护围栏内空白，在此处补回）
    cleaned_lines = [_LINE_TRIM_RE.sub("", line) for line in normalized.splitlines()]
    return "\n".join(_collapse_blank_lines(cleaned_lines)).strip()


def _is_exam_markdown_source(source: str) -> bool:
    # L3 真题源目录：`knowledge/exams/YYYY/{items,answer}.md`
    # （旧 `questions/*_408_exam.md` 已退役，不再作为入库源）
    normalized = source.replace("\\", "/").lower()
    return "/exams/" in normalized


def _remove_exam_web_noise(text: str) -> tuple[str, int]:
    if not text or not text.strip():
        return text, 0

    removed = 0
    cleaned_lines: list[str] = []
    in_fence = False

    for line in text.splitlines():
        stripped = line.strip()
        if _FENCE_RE.match(stripped):
            in_fence = not in_fence
            cleaned_lines.append(line)
            continue
        if in_fence:
            cleaned_lines.append(line)
            continue

        cut_pos = -1
        for marker in _WEB_NOISE_MARKERS:
            pos = line.find(marker)
            if pos >= 0 and (cut_pos < 0 or pos < cut_pos):
                cut_pos = pos

        if cut_pos >= 0:
            prefix = line[:cut_pos].rstrip(" -`},;")
            if prefix:
                cleaned_lines.append(prefix)
            removed += len(line) - len(prefix)
            continue

        if len(stripped) > 160 and _WEB_NOISE_LINE_RE.search(stripped):
            removed += len(line)
            continue

        if len(stripped) > 300 and (
            stripped.count("{") + stripped.count("}") >= 4
            or stripped.count("=>") >= 2
            or stripped.count("`") >= 4
        ):
            removed += len(line)
            continue

        cleaned_lines.append(line)

    cleaned = "\n".join(_collapse_blank_lines(cleaned_lines)).strip()
    return cleaned, removed


def _normalize_exam_question_headings(text: str) -> str:
    if not text or not text.strip():
        return text
    normalized = _INLINE_EXAM_HEADING_RE.sub(r"\n\1\n", text)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    return normalized.strip()
