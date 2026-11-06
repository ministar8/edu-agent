"""Agent 包公开 API（稳定、窄）。

外部应只依赖本层导出；内部实现模块路径（orchestration / specialists / runtime）
不承诺跨版本稳定。
"""

from agents.registry import DEFAULT_AGENT, Agent, agents, get_agent, get_all_agent_info

__all__ = ["DEFAULT_AGENT", "Agent", "agents", "get_agent", "get_all_agent_info"]
