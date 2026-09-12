"""topic 规范化：闭环（episode 关联 / weak_topics / 记忆卡）的唯一入口。

自由文本 topic 不能直接当关联键：空格、全半角、同义词会导致同一知识点裂成多条。
所有写入与派生计算必须先 `normalize_topic`。
"""

from __future__ import annotations

import re
import unicodedata

# 教学场景常见同义/别名 → 规范名（可继续扩充，改这里即可全局生效）
_TOPIC_ALIASES: dict[str, str] = {
    "死锁": "进程死锁",
    "进程死锁": "进程死锁",
    "deadlock": "进程死锁",
    "页面置换": "页面置换",
    "页面置换算法": "页面置换",
    "belady": "页面置换",
    "虚拟内存": "虚拟内存",
    "虚存": "虚拟内存",
    "进程同步": "进程同步",
    "信号量": "进程同步",
}

_WS = re.compile(r"\s+")


def normalize_topic(raw: str) -> str:
    """规范化知识点名；无法识别时返回去空白后的原文（仍保证稳定）。"""
    text = unicodedata.normalize("NFKC", raw or "").strip()
    text = _WS.sub("", text)
    if not text:
        return ""
    key = text.lower()
    if key in _TOPIC_ALIASES:
        return _TOPIC_ALIASES[key]
    # 中文别名表按原文再查一次（无大小写）
    if text in _TOPIC_ALIASES:
        return _TOPIC_ALIASES[text]
    return text


def normalize_topics(raws: list[str] | None) -> list[str]:
    """去重且保序规范化。"""
    seen: set[str] = set()
    out: list[str] = []
    for raw in raws or []:
        t = normalize_topic(raw)
        if t and t not in seen:
            seen.add(t)
            out.append(t)
    return out
