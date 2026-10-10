"""LLM 输出解析工具函数

统一处理 LLM 返回的 JSON 文本：
1. 剥离 markdown 代码块包裹
2. json.loads 解析
3. 正则兜底提取

替代各模块中重复的 _strip_markdown_codeblock + json.loads 实现。
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)


def strip_markdown_codeblock(text: str) -> str:
    """剥 markdown 代码块标记，如 ```json ... ```

    处理格式：
    - ```json\\n{...}\\n```
    - ```\\n{...}\\n```
    - 无代码块的纯 JSON
    """
    m = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
    if m:
        return m.group(1).strip()
    return text.strip()


def parse_llm_json(raw: str, fallback_default: Any = None) -> Any:
    """解析 LLM 输出的 JSON，容错处理

    策略：
    1. 剥 markdown 代码块
    2. json.loads
    3. 正则提取方括号/花括号内容再 json.loads
    4. 返回 fallback_default

    Args:
        raw: LLM 原始输出文本
        fallback_default: 解析失败时的默认返回值（默认 None）

    Returns:
        解析后的 Python 对象，或 fallback_default
    """
    cleaned = strip_markdown_codeblock(raw)

    # 尝试直接解析
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # 尝试提取方括号内容（列表）
    m = re.search(r"\[.*\]", cleaned, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass

    # 尝试提取花括号内容（对象）
    m = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass

    logger.warning("Failed to parse LLM output as JSON: %s", raw[:200])
    return fallback_default
