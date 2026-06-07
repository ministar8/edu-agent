from __future__ import annotations

import json
import re
import time
from typing import Any

from langchain_core.messages import AIMessage, ToolMessage

_SOURCE_RE = re.compile(r"\[(?:来源|Source)\s*\d*\s*:\s*([^\]\n]+)\]", re.IGNORECASE)
_SOURCES_LINE_RE = re.compile(r"^Sources:\s*(.+)$", re.IGNORECASE | re.MULTILINE)


def _to_text(value: Any, limit: int = 1200) -> str:
    if isinstance(value, str):
        text = value
    else:
        try:
            text = json.dumps(value, ensure_ascii=False)
        except TypeError:
            text = str(value)
    return text[:limit]


def extract_sources_from_text(text: str) -> list[str]:
    sources: list[str] = []
    seen: set[str] = set()
    for match in _SOURCE_RE.finditer(text or ""):
        raw = match.group(1).strip()
        source = re.split(r"\s+\(|\s+\[", raw, maxsplit=1)[0].strip()
        if source and source != "未知来源" and source not in seen:
            seen.add(source)
            sources.append(source)
    for match in _SOURCES_LINE_RE.finditer(text or ""):
        for raw in re.split(r"[,，;；]", match.group(1)):
            source = re.split(r"\s+\(|\s+\[", raw.strip(), maxsplit=1)[0].strip()
            if source and source != "未知来源" and source not in seen:
                seen.add(source)
                sources.append(source)
    text = text or ""
    if (
        "【知识图谱关联信息】" in text
        or "[KG Related Info]" in text
        or "Related topics" in text
        or "Dependency edges" in text
        or "Learning paths" in text
    ) and "知识图谱" not in seen:
        seen.add("知识图谱")
        sources.append("知识图谱")
    return sources


def collect_sources_from_steps(steps: list[dict]) -> list[str]:
    sources: list[str] = []
    seen: set[str] = set()
    for step in steps:
        for source in step.get("sources", []) or []:
            if source and source not in seen:
                seen.add(source)
                sources.append(source)
    return sources


def extract_agent_steps_from_messages(messages: list, agent_name: str) -> list[dict]:
    tool_calls: dict[str, dict] = {}
    steps: list[dict] = []

    for msg in messages:
        if isinstance(msg, AIMessage):
            for call in getattr(msg, "tool_calls", []) or []:
                call_id = call.get("id") or call.get("tool_call_id") or f"call_{len(tool_calls) + 1}"
                tool_calls[call_id] = call
        elif isinstance(msg, ToolMessage):
            tool_call_id = getattr(msg, "tool_call_id", "") or ""
            call = tool_calls.get(tool_call_id, {})
            tool_name = getattr(msg, "name", None) or call.get("name") or "unknown_tool"
            content = msg.content if isinstance(msg.content, str) else str(msg.content)
            steps.append({
                "agent_name": agent_name,
                "action": "tool_call",
                "tool_name": tool_name,
                "input_data": _to_text(call.get("args", {}), limit=600),
                "output_data": _to_text(content),
                "sources": extract_sources_from_text(content),
                "timestamp": time.time(),
            })

    return steps
