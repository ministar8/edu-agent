"""运行时按 RunnableConfig 选择模型的中间件。

服务层会把用户指定的 ``<gateway>:<model_id>`` 写入
``config["configurable"]["model"]``。本中间件在每次真正调用模型前读取该值并
``request.override(model=...)``，使 API 传入的 model 生效；未指定时保持
create_agent 装配的默认模型。
"""

from __future__ import annotations

from typing import Any

from langchain.agents.middleware import AgentMiddleware
from langchain_core.language_models.chat_models import BaseChatModel
from langgraph.config import get_config

from core.llm import get_model
from core.settings import settings


def _config_model_ref() -> str | None:
    """从当前 LangGraph RunnableConfig 读取用户指定的 model_ref。"""
    try:
        config = get_config() or {}
    except Exception:
        return None
    configurable = config.get("configurable") or {}
    model_ref = configurable.get("model")
    return model_ref if isinstance(model_ref, str) and model_ref else None


def _temperature_of(model: BaseChatModel) -> float:
    """沿用当前装配模型的温度，避免覆盖 grading 等分级温度。"""
    raw = getattr(model, "temperature", None)
    if isinstance(raw, (int, float)):
        return float(raw)
    return settings.TEMP_DEFAULT


def _resolve_override(request_model: BaseChatModel) -> BaseChatModel | None:
    model_ref = _config_model_ref()
    if not model_ref:
        return None
    return get_model(model_ref, temperature=_temperature_of(request_model))


class RuntimeModelMiddleware(AgentMiddleware):
    """若 config 指定了 model，则在调用前换成对应客户端。"""

    @property
    def name(self) -> str:
        return "runtime_model"

    def wrap_model_call(self, request: Any, handler: Any) -> Any:
        override = _resolve_override(request.model)
        if override is not None:
            request = request.override(model=override)
        return handler(request)

    async def awrap_model_call(self, request: Any, handler: Any) -> Any:
        override = _resolve_override(request.model)
        if override is not None:
            request = request.override(model=override)
        return await handler(request)


runtime_model_middleware = RuntimeModelMiddleware()
