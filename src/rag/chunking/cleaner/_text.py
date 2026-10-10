"""自动拆分自 cleaner.py（行为等价）。"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path

from langchain_core.documents import Document

# ── 正则预编译 ──────────────────────────────────

# PDF 页码：单独一行的 "第X页" / "Page X" / "- X -" / 纯数字行
_PAGE_NUM_RE = re.compile(
    r"^\s*(?:第\s*\d+\s*页|page\s*\d+|-?\s*\d+\s*-?)\s*$",
    re.IGNORECASE | re.MULTILINE,
)

# 连续3个以上换行 → 2个换行
_MULTI_NEWLINE_RE = re.compile(r"\n{3,}")

# 连续3个以上空格 → 1个空格
_MULTI_SPACE_RE = re.compile(r"(?<=\S)[ \t]{3,}(?=\S)")

# 行尾空白（空格/制表符）
_LINE_TRIM_RE = re.compile(r"[ \t]+$", re.MULTILINE)

# 乱码：控制字符（\t \n \r 除外）
_CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

_FENCE_RE = re.compile(r"^\s*(```+|~~~+)")


def _get_source_ext(doc: Document) -> str:
    return Path(_get_source_path(doc)).suffix.lower()


def _get_source_path(doc: Document) -> str:
    return str(
        doc.metadata.get("source_path")
        or doc.metadata.get("source_file")
        or doc.metadata.get("source")
        or ""
    )


def _normalize_text(text: str) -> str:
    if not text or not text.strip():
        return ""
    return unicodedata.normalize("NFKC", _CONTROL_CHARS_RE.sub("", text))


def _collapse_blank_lines(lines: list[str]) -> list[str]:
    collapsed: list[str] = []
    blank_run = 0
    for line in lines:
        if line.strip():
            blank_run = 0
            collapsed.append(line)
            continue
        blank_run += 1
        if blank_run <= 2:
            collapsed.append("")
    return collapsed


def _finalize_whitespace(cleaned: str) -> str:
    """收尾空白清理：压缩多余换行/空格并去除首尾空白"""
    cleaned = _MULTI_NEWLINE_RE.sub("\n\n", cleaned)
    cleaned = _MULTI_SPACE_RE.sub(" ", cleaned)
    return cleaned.strip()


def _clean_plain_text(text: str) -> str:
    normalized = _normalize_text(text)
    if not normalized:
        return ""
    cleaned_lines = [_LINE_TRIM_RE.sub("", line) for line in normalized.splitlines()]
    cleaned = "\n".join(cleaned_lines)
    cleaned = _PAGE_NUM_RE.sub("", cleaned)
    return _finalize_whitespace(cleaned)
