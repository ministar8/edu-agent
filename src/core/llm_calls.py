"""统一的 LLM 调用入口（全局模型基建，2026-11-07 从 ``rag.retrieval.llm_calls`` 迁出）。

此前 7 处调用各写一遍「取客户端 → 调用 → 解析 → 失败兜底」，导致两个问题：
超时只有 decomposer 显式施加，失败语义有三种（返回空串 / 返回原顺序 / 抛 500）。

本模块把骨架收敛到一处，并统一约定：

- **失败（含超时、解析失败）一律返回 ``None``**，由调用方显式决定降级方向，
  不再由被调方替调用方决定"失败就该给空串"。
- 异步版本统一用 ``asyncio.wait_for`` 施加超时；同步版本供同步上下文（如 ingest
  后的缓存预热）使用，超时由客户端级 ``request_timeout`` 兜底。
- **提示词集版本由调用方注入**（``prompt_set_version``）：本模块身处 ``core``，
  不得反向依赖 ``prompts``（``prompts`` 自己依赖 ``core.kp_vocab``）。
  未传版本时 trace metadata 省略该键，功能不受影响。
- **业务专用兜底走 ``salvage`` 钩子**：通用 JSON 清洗在本模块完成；批改专用的
  ``score: ...`` 裸文本解析在 ``agents.specialists.grading_salvage``，
  由调用方显式传入，避免把领域字段名写进通用基建（历史缺陷：``_KV_*``
  与 ``GradingResult`` 逐字段耦合）。
"""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Callable

from langchain_core.messages import BaseMessage
from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel, ValidationError

from core.llm import get_llm
from core.settings import settings

logger = logging.getLogger(__name__)

__all__ = [
    "PromptInput",
    "SalvageFn",
    "call_structured",
    "call_text",
    "call_text_sync",
    "salvage_json_from_raw",
    "strip_tool_markup",
]

# 既接受裸字符串（会被包成单条 HumanMessage），也接受 ChatPromptTemplate
# 产出的消息列表（指令进 SystemMessage、数据进 HumanMessage）。
type PromptInput = str | list[BaseMessage]

# 业务侧兜底钩子：拿「最后一次原始输出 + 目标 schema」，能救回就返回实例。
type SalvageFn[T: BaseModel] = Callable[[str, type[T]], T | None]

# ★ 2026-10-06（Step 5 实测）：模型在 function_calling 模式下**格式飘移**时，会把
#   工具调用的参数标记直接吐进自然语言文本，实测见过三种形态：
#
#       "结构描述基本正确……\n<parameter=score>\n95"
#       "……<parameter=feedback>平衡性判断有误</parameter>"
#       "……AVL树\n\n\n<tool_call>"
#
#   这些标记**不是**批改内容，却占了长度、污染了字段语义。清洗掉再交给 Pydantic，
#   能把「格式飘移」与「真错误答案」区分开 —— 前者不该让整条链路判失败。
#   只匹配工具调用相关的成对/自闭合标签，不碰正文里正常的尖括号（如泛型 <T>）。
_TOOL_MARKUP_RE = re.compile(
    r"</?(?:parameter|tool_call|tool_calls|function_call|function|invoke)"
    r"(?:\s*=\s*[^>]*)?>",
    re.IGNORECASE,
)


def strip_tool_markup(text: str) -> str:
    """剥掉泄漏进自然语言输出里的工具调用标记（含其后的孤立闭合标记）。"""
    if not text or "<" not in text:
        return text
    return _TOOL_MARKUP_RE.sub("", text).strip()


def _as_text(raw: object) -> str:
    content = getattr(raw, "content", raw)
    return str(content).strip()


def _trace_config(stage: str, prompt_set_version: str) -> RunnableConfig:
    """把提示词阶段与提示词集版本写进 run metadata。

    LangSmith 据此按提示词分组 —— 改过提示词后输出质量变化可直接归因。
    ``prompt_set_version`` 由调用方注入（本模块不 import ``prompts``，见模块头）。
    """
    metadata = {"prompt_stage": stage}
    if prompt_set_version:
        metadata["prompt_set_version"] = prompt_set_version
    return {"metadata": metadata}


def _log_failure(stage: str, exc: BaseException) -> None:
    logger.warning("LLM call failed [%s]: %s: %s", stage, type(exc).__name__, exc)


async def call_text(
    prompt: PromptInput,
    *,
    temperature: float,
    timeout: float,
    stage: str,
    prompt_set_version: str = "",
) -> str | None:
    """调用 LLM 取纯文本。超时或异常返回 None。"""
    llm = get_llm(streaming=False, temperature=temperature)
    try:
        raw = await asyncio.wait_for(
            llm.ainvoke(prompt, config=_trace_config(stage, prompt_set_version)), timeout=timeout
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
    prompt_set_version: str = "",
) -> str | None:
    """``call_text`` 的同步版本，**仅供同步上下文使用**（如 ingest 的缓存预热）。

    注意：在 ``async def`` 里直接调用它会阻塞事件循环整个 LLM 调用时长；
    async 上下文请用 ``await call_text(...)``。
    """
    llm = get_llm(streaming=False, temperature=temperature)
    try:
        raw = llm.invoke(prompt, config=_trace_config(stage, prompt_set_version))
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


async def _await_structured(
    llm,
    prompt: PromptInput,
    schema: type,
    timeout: float,
    stage: str,
    prompt_set_version: str,
):
    """单次结构化调用：成功返回 ``(result, None)``，异常返回 ``(None, exc)``。"""
    try:
        structured = _bind_structured(llm, schema)
        result = await asyncio.wait_for(
            structured.ainvoke(prompt, config=_trace_config(stage, prompt_set_version)),
            timeout=timeout,
        )
        return result, None
    except Exception as exc:
        return None, exc


async def _structured_attempts[T: BaseModel](
    llm,
    prompt: PromptInput,
    schema: type[T],
    timeout: float,
    stage: str,
    attempts: int,
    prompt_set_version: str,
) -> tuple[T | None, BaseException | None, str]:
    """重试循环：成功即返回 ``(result, None, last_raw)``，耗尽则 ``(None, last_exc, last_raw)``。

    ★ 超时**不重试**（重试只会再等一个 timeout，成倍放大延迟而不提升成功率）。
    ★ ``last_raw`` 是最后一次拿到、可能含工具标记污染的原始文本，供兜底清洗。
    """
    last_exc: BaseException | None = None
    last_raw: str = ""
    for attempt in range(attempts):
        result, exc = await _await_structured(
            llm, prompt, schema, timeout, stage, prompt_set_version
        )
        if exc is not None:
            last_exc = exc
            # 格式飘移时异常里带的是「原始文本」，取回留作兜底素材。
            raw_text = _raw_from_validation_error(exc)
            if raw_text:
                last_raw = raw_text
            if isinstance(exc, TimeoutError):
                break
            if attempt + 1 < attempts:
                logger.info(
                    "结构化输出失败 [%s]，重试 %s/%s：%s: %s",
                    stage,
                    attempt + 1,
                    attempts - 1,
                    type(exc).__name__,
                    exc,
                )
        elif isinstance(result, schema):
            if attempt:
                logger.info("结构化输出重试成功 [%s]（第 %s 次尝试）", stage, attempt + 1)
            return result, None, last_raw
        else:
            last_exc = None  # 未抛错但类型不符，同样值得重试
            if attempt + 1 < attempts:
                logger.info(
                    "结构化输出类型不符 [%s]（%s），重试 %s/%s",
                    stage,
                    type(result).__name__,
                    attempt + 1,
                    attempts - 1,
                )
    return None, last_exc, last_raw


async def call_structured[T: BaseModel](
    prompt: PromptInput,
    schema: type[T],
    *,
    temperature: float,
    timeout: float,
    stage: str,
    prompt_set_version: str = "",
    salvage: SalvageFn[T] | None = None,
) -> T | None:
    """调用 LLM 并解析为结构化结果。超时、异常或结构不符均返回 None。

    ★ 2026-10-06（Step 5 实测）：**对可重试的结构化失败做同 prompt 重试**。

    背景：实测 DashScope 兼容端即使强制 ``tool_choice``，仍**偶发**返回裸文本
    （形如 ``score: 40\\nfeedback: ...``）而非 tool call 参数。这类输出的长度不受
    schema 约束，一旦超过 ``max_length``，Pydantic 校验即抛 ``ValidationError``。
    此前该异常被本函数的 ``except Exception`` 吞成 ``None``，调用方（如
    ``grading_core.agrade_answer``）无法区分「上游超时」与「只是这一次格式飘了」，
    只能整体判失败 —— 批改链路因此**随机整体崩塌**。

    因此：**第一次失败后按 ``STRUCTURED_OUTPUT_RETRIES`` 重试**（同 prompt、
    同 temperature）。重试是安全的 —— 失败不产生副作用（纯读），而实测同 prompt
    重试的成功率提升显著（第一次裸文本、第二次常回正常 tool call）。

    ``timeout`` 语义：**单次尝试**的上限，不是总时长。总耗时上界为
    ``(1 + STRUCTURED_OUTPUT_RETRIES) * timeout``；调用方如需严格总预算，
    应在外层再包一层 ``asyncio.wait_for``。

    ★ 兜底清洗：若重试耗尽仍失败，且**最后一次的原始输出可拿到**，则先做
      通用清洗（``strip_tool_markup`` + JSON 重解析，§ ``salvage_json_from_raw``）；
      若调用方传了 ``salvage`` 钩子，再交给它做领域专用解析（如批改的
      ``score: 40`` 裸文本）。仅当该次失败确实是「工具标记污染文本」时才可能救回；
      救不回仍返回 ``None``。
    """
    llm = get_llm(streaming=False, temperature=temperature)
    attempts = max(1, 1 + int(settings.STRUCTURED_OUTPUT_RETRIES))
    result, last_exc, last_raw = await _structured_attempts(
        llm, prompt, schema, timeout, stage, attempts, prompt_set_version
    )
    if result is not None:
        return result

    # ── 兜底：清洗工具标记后重新解析 ──────────────────────────────
    if last_raw:
        salvaged = salvage_json_from_raw(last_raw, schema, stage=stage)
        if salvaged is not None:
            return salvaged
        if salvage is not None:
            custom = salvage(last_raw, schema)
            if custom is not None:
                logger.info("领域专用兜底解析成功 [%s]", stage)
                return custom

    if last_exc is not None:
        _log_failure(stage, last_exc)
    else:
        logger.warning("结构化输出类型不符 [%s]，重试 %s 次后仍失败", stage, attempts - 1)
    return None


def _raw_from_validation_error(exc: BaseException) -> str:
    """从 ValidationError 中取回触发失败的原始字符串（模型输出）。

    Pydantic 把原始输入放在每个 error 的 ``input``；批量结构化输出失败时通常
    整条 payload 都在。取其中最长的那个字符串字段 —— 即被撑爆的 ``feedback``。
    """
    if not isinstance(exc, ValidationError):
        return ""
    best = ""
    for e in exc.errors():
        val = e.get("input")
        if isinstance(val, str) and len(val) > len(best):
            best = val
    return best


def salvage_json_from_raw[T: BaseModel](raw: str, schema: type[T], *, stage: str = "") -> T | None:
    """清洗工具标记后，把原始文本按 **JSON** 重建为结构化对象。

    只在**清洗确实改变了内容**时才尝试；且必须解析成 **dict** 再走 schema 校验，
    避免把自然语言散文硬塞进字段。

    ★ 只处理 JSON 形态。领域专用的裸文本解析（如批改的 ``score: 40``）
      由调用方通过 ``call_structured(..., salvage=...)`` 钩子提供。
    """
    cleaned = strip_tool_markup(raw)
    if cleaned == raw:
        return None  # 没有标记污染，不属于本兜底能治的情形

    payload = _try_json_dict(cleaned)
    if not payload:
        return None
    try:
        candidate = schema.model_validate(payload)
    except ValidationError:
        return None
    logger.info("结构化输出兜底清洗成功 [%s]：字段 %s", stage, sorted(payload))
    return candidate


def _try_json_dict(text: str) -> dict | None:
    import orjson

    for candidate in (text, _extract_json_object(text)):
        if not candidate:
            continue
        try:
            parsed = orjson.loads(candidate)
        except Exception:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


def _extract_json_object(text: str) -> str | None:
    """从文本里截出最外层 ``{...}`` 片段。"""
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        return None
    return text[start : end + 1]
