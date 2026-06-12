from collections.abc import Callable

from langgraph.graph import END, START, StateGraph

from app.agents.chain_runners import wrap_agent
from app.agents.grading_agent import create_grading_agent
from app.agents.graph_router import route_question
from app.agents.graph_state import AGENT_NODE_NAMES, AgentState
from app.agents.knowledge_agent import create_knowledge_agent
from app.agents.path_agent import create_path_agent
from app.agents.question_agent import create_question_agent


AGENT_NODE_FACTORIES: tuple[tuple[str, Callable[[], object]], ...] = (
    ("knowledge_agent", create_knowledge_agent),
    ("question_agent", create_question_agent),
    ("grading_agent", create_grading_agent),
    ("path_agent", create_path_agent),
)


def build_multi_agent_graph() -> object:
    builder = StateGraph(AgentState)
    builder.add_node("supervisor", route_question)

    for node_name, create_agent in AGENT_NODE_FACTORIES:
        builder.add_node(node_name, wrap_agent(create_agent(), node_name))

    builder.add_edge(START, "supervisor")
    for node_name in AGENT_NODE_NAMES:
        builder.add_edge(node_name, END)

    return builder.compile()


_graph: object | None = None


def get_graph() -> object:
    global _graph
    if _graph is None:
        _graph = build_multi_agent_graph()
    return _graph
