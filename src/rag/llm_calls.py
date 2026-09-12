"""RAG 层统一的 LLM 调用入口。

此前 7 处调用各写一遍「取客户端 → 调用 → 解析 → 失败兜底」，导致两个问题：
超时只有 decomposer 显式施加，失败语义有三种（返回空串 / 返回原顺序 / 抛 500）。

本模块把骨架收敛到一处，并统一约定：

- **失败（含超时、解析失败）一律返回 ``None``**，由调用方显式决定降级方向，
  不再由被调方替调用方决定"失败就该给空串"。
- 异步版本统一用 ``asyncio.wait_for`` 施加超时；同步版本供同步上下文（如 ingest
  后的缓存预热）使用，超时由客户端级 ``request_timeout`` 兜底。
"""

from __future__ import annotations

import asyncio
import logging

from langchain_core.messages import BaseMessage
from pydantic import BaseModel

from core.llm import get_llm
from core.settings import settings
from prompts import PROMPT_SET_VERSION

logger = logging.getLogger(__name__)

# 既接受裸字符串（会被包成单条 HumanMessage），也接受 ChatPromptTemplate
# 产出的消息列表（指令进 SystemMessage、数据进 HumanMessage）。
type PromptInput = str | list[BaseMessage]


def _as_text(raw: object) -> str:
    content = getattr(raw, "content", raw)
    return str(content).strip()


def _trace_config(stage: str) -> dict:
    """把提示词阶段与提示词集版本写进 run metadata。

    LangSmith 据此按提示词分组 —— 改过提示词后输出质量变化可直接归因。
    """
    return {"metadata": {"prompt_stage": stage, "prompt_set_version": PROMPT_SET_VERSION}}


def _log_failure(stage: str, exc: BaseException) -> None:
    logger.warning("LLM call failed [%s]: %s: %s", stage, type(exc).__name__, exc)


async def call_text(
    prompt: PromptInput,
    *,
    temperature: float,
    timeout: float,
    stage: str,
) -> str | None:
    """调用 LLM 取纯文本。超时或异常返回 None。"""
    llm = get_llm(streaming=False, temperature=temperature)
    try:
        raw = await asyncio.wait_for(
            llm.ainvoke(prompt, config=_trace_config(stage)), timeout=timeout
        )
    except Exception as exc:
        _log_failure(stage, exc)
        return None
    return _as_text(raw)


def call_text_sync(
    prompt: PromptInput,
    *,
    temperature: float,
    stage: str,
) -> str | None:
    """``call_text`` 的同步版本，**仅供同步上下文使用**（如 ingest 的缓存预热）。

    注意：在 ``async def`` 里直接调用它会阻塞事件循环整个 LLM 调用时长；
    async 上下文请用 ``await call_text(...)``。
    """
    llm = get_llm(streaming=False, temperature=temperature)
    try:
        raw = llm.invoke(prompt, config=_trace_config(stage))
    except Exception as exc:
        _log_failure(stage, exc)
        return None
    return _as_text(raw)


def _bind_structured(llm, schema: type):
    """按配置绑定 with_structured_output；失败时回退不带 method 的默认实现。"""
    method = settings.STRUCTURED_OUTPUT_METHOD
    try:
        return llm.with_structured_output(schema, method=method)
    except Exception as exc:
        logger.warning("with_structured_output(method=%s) 失败，回退默认: %s", method, exc)
        return llm.with_structured_output(schema)


async def call_structured[T: BaseModel](
    prompt: PromptInput,
    schema: type[T],
    *,
    temperature: float,
    timeout: float,
    stage: str,
) -> T | None:
    """调用 LLM 并解析为结构化结果。超时、异常或结构不符均返回 None。"""
    llm = get_llm(streaming=False, temperature=temperature)
    try:
        structured = _bind_structured(llm, schema)
        result = await asyncio.wait_for(
            structured.ainvoke(prompt, config=_trace_config(stage)), timeout=timeout
        )
    except Exception as exc:
        _log_failure(stage, exc)
        return None
    return result if isinstance(result, schema) else None


def call_structured_sync[T: BaseModel](
    prompt: PromptInput,
    schema: type[T],
    *,
    temperature: float,
    stage: str,
) -> T | None:
    """``call_structured`` 的同步版本，**仅供同步上下文使用**。"""
    llm = get_llm(streaming=False, temperature=temperature)
    try:
        structured = _bind_structured(llm, schema)
        result = structured.invoke(prompt, config=_trace_config(stage))
    except Exception as exc:
        _log_failure(stage, exc)
        return None
    return result if isinstance(result, schema) else None
