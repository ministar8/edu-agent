"""Agent 注册表：对外暴露可用的 agent 图与元信息。"""

from dataclasses import dataclass

from langgraph.graph.state import CompiledStateGraph

from agents.teaching_graph import edu_supervisor
from schema import AgentInfo

DEFAULT_AGENT = "edu-assistant"


@dataclass
class Agent:
    description: str
    graph_like: CompiledStateGraph


agents: dict[str, Agent] = {
    DEFAULT_AGENT: Agent(
        description="408 考研智能辅导助手：知识讲解、出题练习、答案批改。",
        graph_like=edu_supervisor,
    ),
}


def get_agent(agent_id: str) -> CompiledStateGraph:
    return agents[agent_id].graph_like


def get_all_agent_info() -> list[AgentInfo]:
    return [
        AgentInfo(key=agent_id, description=agent.description) for agent_id, agent in agents.items()
    ]
