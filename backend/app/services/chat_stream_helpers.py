from __future__ import annotations

import json
import re
import time

SOURCE_MARKER_RE = re.compile(
    r"(\[(?:来源|Source)\s*\d*\s*:)|(^|\n)\s*(?:来源依据|来源|Sources?|参考来源)\s*[:：]",
    re.IGNORECASE,
)


def append_source_line_if_missing(answer: str, sources: list[str]) -> str:
    if not answer or not sources:
        return answer
    if SOURCE_MARKER_RE.search(answer):
        return answer
    return answer.rstrip() + "\n\n来源依据：" + "，".join(sources[:5])


def build_governance_from_agent(governance: dict, guard: dict | None) -> dict:
    return {
        "confidence": governance.get("confidence", "unknown"),
        "has_source": governance.get("has_source", False),
        "passed": governance.get("passed", True),
        "flags": governance.get("flags", []),
        "has_sufficient_evidence": guard.get("has_sufficient_evidence", True) if guard else True,
    }


def build_timeout_governance(sources: list[str], **extra) -> dict:
    return {
        "confidence": "low",
        "has_source": bool(sources),
        "passed": False,
        "flags": ["timeout_partial"],
        **extra,
    }


def sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def deadline_remaining(deadline_at: float) -> float:
    return max(0.0, deadline_at - time.perf_counter())


def chunk_text(chunk) -> str:
    content = chunk.content if hasattr(chunk, "content") else str(chunk)
    if isinstance(content, list):
        return "".join(
            item.get("text", "") if isinstance(item, dict) else str(item)
            for item in content
        )
    return str(content or "")
