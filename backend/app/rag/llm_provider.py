"""结构化模型接口层

统一管理 LLM Provider 检测、参数构建、实例缓存。
所有 LLM 创建逻辑集中于此，修改 provider 适配只需改本文件。

公共 API：
  - detect_provider()  → ProviderConfig
  - build_llm_kwargs() → dict
  - get_llm()          → ChatOpenAI  (基于 settings，带缓存)
  - create_llm()       → ChatOpenAI  (显式参数，无缓存，评估等场景)
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from langchain_openai import ChatOpenAI

logger = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════════
# Provider 检测
# ════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class ProviderConfig:
    """一次 provider 检测的结果，所有 provider 信息集中在此"""
    provider: str               # "deepseek" | "dashscope" | "generic"
    api_base: str
    model: str
    needs_thinking_disabled: bool   # DeepSeek / Qwen3.x: 禁用思考模式
    needs_enable_thinking: bool     # Qwen3.x-max: 启用思考模式
    is_dashscope: bool              # DashScope 百炼 API（不支持 instructor）


def detect_provider(api_base: str, model: str) -> ProviderConfig:
    """统一 provider 检测，一处维护

    检测逻辑：
    1. api_base 含 "deepseek" → DeepSeek 官方 API
    2. model 含 "deepseek" → 通过第三方代理（如 DashScope）调用的 DeepSeek
    3. api_base 含 "dashscope" → 阿里云百炼 DashScope
    4. 其他 → generic OpenAI 兼容
    """
    b = (api_base or "").lower()
    m = (model or "").lower()

    is_deepseek = "deepseek" in b or "deepseek" in m
    is_dashscope = "dashscope" in b
    is_qwen3 = "qwen3" in m
    is_qwen3_max = bool(re.search(r"qwen[\d.]+-max", m))

    if is_deepseek:
        provider = "deepseek"
    elif is_dashscope:
        provider = "dashscope"
    else:
        provider = "generic"

    # DeepSeek: 禁用思考模式（reasoning token 暴增输出费用）
    # Qwen3.x: 禁用思考模式（RAGAS judge 需要结构化输出）
    needs_thinking_disabled = is_deepseek or is_qwen3

    # Qwen3.x-max 思考模型通过 DashScope 必须 enable_thinking=True
    # 非思考模型不传该参数（传 False 会导致 400 错误）
    needs_enable_thinking = is_qwen3_max and is_dashscope

    return ProviderConfig(
        provider=provider,
        api_base=api_base,
        model=model,
        needs_thinking_disabled=needs_thinking_disabled,
        needs_enable_thinking=needs_enable_thinking,
        is_dashscope=is_dashscope,
    )


# ════════════════════════════════════════════════════════════════
# 参数构建
# ════════════════════════════════════════════════════════════════

def build_llm_kwargs(
    api_key: str,
    api_base: str,
    model: str,
    *,
    streaming: bool = True,
    temperature: float = 0.3,
    timeout: int = 90,
    max_retries: int = 2,
) -> dict:
    """构建 ChatOpenAI 参数，provider 专有参数在此注入

    Returns:
        kwargs dict，可直接传 ChatOpenAI(**kwargs)
    """
    pc = detect_provider(api_base, model)

    kwargs: dict = dict(
        api_key=api_key,
        base_url=api_base,
        model=model,
        temperature=temperature,
        streaming=streaming,
        request_timeout=timeout,
        max_retries=max_retries,
    )

    extra_body: dict = {}

    # DeepSeek v4: 禁用思考模式
    # 官方参数: extra_body={"thinking": {"type": "disabled"}}
    if pc.needs_thinking_disabled and not pc.needs_enable_thinking:
        if pc.provider == "deepseek":
            extra_body["thinking"] = {"type": "disabled"}
        else:
            # Qwen3.x: enable_thinking=False 禁用思考
            extra_body["enable_thinking"] = False

    # Qwen3.x-max 思考模型: 必须 enable_thinking=True
    if pc.needs_enable_thinking:
        extra_body["enable_thinking"] = True

    if extra_body:
        kwargs["extra_body"] = extra_body

    return kwargs


# ════════════════════════════════════════════════════════════════
# 实例缓存 + 入口函数
# ════════════════════════════════════════════════════════════════

_LLM_INSTANCES: dict[str, ChatOpenAI] = {}


def get_llm(
    streaming: bool = True,
    temperature: float = 0.3,
    use_fast: bool = False,
) -> ChatOpenAI:
    """获取 LLM 实例（基于 settings 全局配置，单例缓存）

    用于 Agent / 检索 / HyDE 等常规场景。

    Args:
        streaming: 是否启用流式输出（默认 True，用于 Agent 对话）
        temperature: 生成温度（0.0=确定性评估，0.3=创造性生成）
        use_fast: 是否使用轻量模型（settings.LLM_MODEL_FAST）
    """
    from app.config import settings

    if not settings.LLM_API_KEY:
        raise RuntimeError("LLM_API_KEY must be set in .env or environment variables")

    model = settings.LLM_MODEL_FAST if use_fast and settings.LLM_MODEL_FAST else settings.LLM_MODEL

    cache_key = "|".join([
        settings.LLM_API_BASE,
        model,
        settings.LLM_API_KEY[-8:],
        "stream" if streaming else "no_stream",
        f"temp={temperature}",
        f"timeout={settings.LLM_TIMEOUT}|fast={use_fast}",
        detect_provider(settings.LLM_API_BASE, model).provider,
    ])

    if cache_key not in _LLM_INSTANCES:
        logger.debug(
            "Creating LLM client: base=%s model=%s streaming=%s fast=%s",
            settings.LLM_API_BASE, model, streaming, use_fast,
        )
        kwargs = build_llm_kwargs(
            api_key=settings.LLM_API_KEY,
            api_base=settings.LLM_API_BASE,
            model=model,
            streaming=streaming,
            temperature=temperature,
            timeout=settings.LLM_TIMEOUT,
            max_retries=2,
        )
        _LLM_INSTANCES[cache_key] = ChatOpenAI(**kwargs)

    return _LLM_INSTANCES[cache_key]


def create_llm(
    model: str,
    api_base: str,
    api_key: str,
    *,
    temperature: float = 0.0,
    streaming: bool = False,
    timeout: int = 120,
    max_retries: int = 3,
) -> ChatOpenAI:
    """创建 LLM 实例（显式参数，无缓存，评估等场景使用）

    不依赖 settings 全局配置，参数由调用方显式传入。
    """
    kwargs = build_llm_kwargs(
        api_key=api_key,
        api_base=api_base,
        model=model,
        streaming=streaming,
        temperature=temperature,
        timeout=timeout,
        max_retries=max_retries,
    )
    return ChatOpenAI(**kwargs)
