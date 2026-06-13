from __future__ import annotations

import asyncio
import json
import re
import time
from collections.abc import AsyncIterator
from typing import Protocol, runtime_checkable

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


def build_evidence_metadata(fused) -> dict:
    return {
        **(fused.metadata or {}),
        "text_evidence_count": len(fused.text_evidences),
        "context_tokens": fused.used_token_budget,
    }


def build_partial_final_payload(
    *,
    agent_name: str,
    final_answer: str,
    sources: list[str],
    agent_steps: list[dict],
    streaming_mode: str,
) -> dict:
    return {
        "agent_name": agent_name,
        "final_answer": final_answer,
        "sources": sources,
        "agent_steps": agent_steps,
        "streaming_mode": streaming_mode,
    }


def build_done_payload(
    *,
    agent_name: str,
    sources: list[str],
    user_msg_id: int,
    partial: bool = False,
) -> dict:
    payload = {
        "agent_name": agent_name,
        "sources": sources,
        "user_msg_id": user_msg_id,
    }
    if partial:
        payload["partial"] = True
    return payload


def sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def deadline_remaining(deadline_at: float) -> float:
    return max(0.0, deadline_at - time.perf_counter())


@runtime_checkable
class AsyncClosable(Protocol):
    async def aclose(self) -> None:
        ...


async def close_async_stream(stream: object) -> None:
    if isinstance(stream, AsyncClosable):
        await stream.aclose()


async def stream_text_chunks(text: str, chunk_size: int = 20, delay: float = 0.01) -> AsyncIterator[str]:
    for index in range(0, len(text), chunk_size):
        yield text[index:index + chunk_size]
        if delay > 0:
            await asyncio.sleep(delay)


def chunk_text(chunk) -> str:
    content = chunk.content if hasattr(chunk, "content") else str(chunk)
    if isinstance(content, list):
        return "".join(
            item.get("text", "") if isinstance(item, dict) else str(item)
            for item in content
        )
    return str(content or "")
