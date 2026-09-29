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


def _patch_tool_choice_safe(model: Any) -> Any:
    """把 `tool_choice=any/required` 降为 `auto`（DashScope thinking 兼容）。

    ★ 根因：create_agent 在 ToolStrategy（结构化输出走工具）下会
    `bind_tools(tool_choice="any")`，而 DashScope 的 thinking 模式
    （qwen3-max 必开 enable_thinking=true）直接拒绝
    「tool_choice = required / object」→ `invalid_parameter_error`。

    实测 `tool_choice="auto"` 两步链（检索工具 → 结构化工具）在 DashScope 上
    稳定可用；强制 any 反而把整条出题链路打死。

    只改「强制」档位；默认 `tool_choice=None` 原样透传，不影响其它 agent 的正常绑定。
    注意 `get_model` 按 (网关,模型,温度,streaming) 缓存，同一实例可能被多 agent 共享 ——
    本补丁对共享实例是安全的：仅当调用方传 `tool_choice=any/required` 时才改写。
    """
    original = model.bind_tools

    def bind_tools(tools: Any, *, tool_choice: Any = None, **kwargs: Any) -> Any:
        if tool_choice in ("any", "required") or isinstance(tool_choice, dict):
            tool_choice = "auto"
        return original(tools, tool_choice=tool_choice, **kwargs)

    # ChatOpenAI 是 pydantic 模型，普通赋值会被拒；用 object.__setattr__ 打实例补丁
    object.__setattr__(model, "bind_tools", bind_tools)
    return model


def build_agent(
    *,
    name: str,
    tools: list[Any],
    system_prompt: str,
    temperature: float,
    model_ref: str | None = None,
    response_format: Any | None = None,
) -> Any:
    """创建 LangChain agent 图，并登记 AgentAssembly。

    默认挂 RuntimeModelMiddleware：API 层写入的 configurable.model 在调用时生效。
    """
    from agents.runtime_model import runtime_model_middleware
    from core import get_model, settings

    resolved_model = model_ref if model_ref is not None else settings.DEFAULT_MODEL
    model = get_model(resolved_model, temperature=temperature)
    if response_format is not None:
        # 结构化输出会触发 create_agent 的 tool_choice="any"，须先降级为 auto
        model = _patch_tool_choice_safe(model)
    kwargs: dict[str, Any] = {
        "model": model,
        "tools": tools,
        "name": name,
        "system_prompt": system_prompt,
        "middleware": [runtime_model_middleware],
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
