"""记忆写入前隐私扫描：脱敏手机号/身份证等，避免原样进 Store。

只做确定性正则，不调用 LLM；命中则替换为占位符，不阻断写入。
"""

from __future__ import annotations

import re

# 大陆手机号（宽松：1 开头 11 位，允许空格/横线）
_PHONE = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
_PHONE_SEP = re.compile(r"(?<!\d)1[3-9]\d[-\s]\d{4}[-\s]\d{4}(?!\d)")

# 身份证 18 位（末位可为 X）
_ID_CARD = re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)")

# 邮箱（简单）
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")

_REDACT_PHONE = "[手机已脱敏]"
_REDACT_ID = "[身份证已脱敏]"
_REDACT_EMAIL = "[邮箱已脱敏]"


def redact_pii(text: str) -> tuple[str, int]:
    """脱敏常见 PII；返回 (脱敏后文本, 替换次数)。"""
    if not text:
        return "", 0
    hits = 0
    out = text

    def _sub(pattern: re.Pattern[str], repl: str, s: str) -> tuple[str, int]:
        nonlocal hits
        new, n = pattern.subn(repl, s)
        hits += n
        return new, n

    out, _ = _sub(_PHONE_SEP, _REDACT_PHONE, out)
    out, _ = _sub(_PHONE, _REDACT_PHONE, out)
    out, _ = _sub(_ID_CARD, _REDACT_ID, out)
    out, _ = _sub(_EMAIL, _REDACT_EMAIL, out)
    return out, hits
