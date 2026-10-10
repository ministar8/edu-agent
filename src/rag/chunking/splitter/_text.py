"""自动拆分自 splitter.py（行为等价）。"""

from __future__ import annotations

import re


def _percentile(values: list[int], ratio: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int(round((len(ordered) - 1) * ratio))))
    return float(ordered[index])


def _is_sentence_complete(text: str) -> bool:
    """判断文本是否在语义完整的位置结束。

    完整结束：句末标点、Markdown 列表项/标题行、代码块或加粗闭合、右括号右引号、表格行、引用块。
    """
    stripped = text.rstrip()
    if not stripped:
        return True
    if stripped.endswith(
        ("。", "！", "？", ".", "!", "?", ":", "：", "；", ";", "…", "”", "'", '"')
    ):
        return True
    if stripped.endswith("```"):
        return True
    last_line = stripped.splitlines()[-1].strip() if stripped.splitlines() else ""
    if re.match(r"^(?:[-*+]|\d+[.．])\s+", last_line):
        return True
    if re.match(r"^#{1,4}\s+", last_line):
        return True
    if stripped.endswith(("）", ")", "】", "]", "》", "}", ">")):
        return True
    if stripped.endswith("|"):
        return True
    if stripped.endswith(">"):
        return True
    if stripped.endswith(("**", "__")):
        return True
    return False
