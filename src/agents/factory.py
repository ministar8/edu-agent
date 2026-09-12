"""Agent 构建工厂：统一 create_agent 装配并登记元信息供测试/调试。

图对象仍直接传给 create_supervisor；工厂额外记录 tool 名与温度槽，
避免改工具或漏挂时只能靠聊天肉眼发现。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from langchain.agents import create_agent


@dataclass(frozen=True)
class AgentAssembly:
    """一次 build_agent 的装配快照（不含运行时状态）。"""

    name: str
    tool_names: tuple[str, ...]
    temperature: float
    has_response_format: bool = False


_ASSEMBLIES: dict[str, AgentAssembly] = {}


def build_agent(
    *,
    name: str,
    tools: list[Any],
    system_prompt: str,
    temperature: float,
    model_ref: str | None = None,
    response_format: Any | None = None,
) -> Any:
    """创建 LangChain agent 图，并登记 AgentAssembly。"""
    from core import get_model, settings

    resolved_model = model_ref if model_ref is not None else settings.DEFAULT_MODEL
    kwargs: dict[str, Any] = {
        "model": get_model(resolved_model, temperature=temperature),
        "tools": tools,
        "name": name,
        "system_prompt": system_prompt,
    }
    if response_format is not None:
        kwargs["response_format"] = response_format
    graph = create_agent(**kwargs)
    _ASSEMBLIES[name] = AgentAssembly(
        name=name,
        tool_names=tuple(str(t.name) for t in tools),
        temperature=temperature,
        has_response_format=response_format is not None,
    )
    return graph


def get_assembly(name: str) -> AgentAssembly:
    if name not in _ASSEMBLIES:
        raise KeyError(f"Unknown agent assembly: {name}")
    return _ASSEMBLIES[name]


def all_assemblies() -> dict[str, AgentAssembly]:
    return dict(_ASSEMBLIES)
