"""记忆写入计量：粗粒度字符/伪 token 估算，便于观测而非精确计费。

不绑定具体 tokenizer；默认按「中文≈1字/1token、英文≈4字符/1token」粗估。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MemoryMeter:
    label: str
    chars: int
    approx_tokens: int


def approx_tokens(text: str) -> int:
    if not text:
        return 0
    # 粗估：CJK 与非 CJK 分开
    cjk = sum(1 for ch in text if "一" <= ch <= "鿿")
    other = len(text) - cjk
    return cjk + max(other // 4, 1 if other else 0)


def meter_text(label: str, *parts: str) -> MemoryMeter:
    joined = "".join(p or "" for p in parts)
    m = MemoryMeter(label=label, chars=len(joined), approx_tokens=approx_tokens(joined))
    if m.chars:
        logger.debug("memory meter %s chars=%s tokens~%s", label, m.chars, m.approx_tokens)
    return m
