from typing_extensions import TypedDict


class AgentState(TypedDict, total=False):
    messages: list
    current_agent: str
    agent_steps: list[dict]
    final_answer: str
    guard_result: dict
    governance: dict
    pre_retrieval_result: str | None
    retrieval_layer: str
    route_type: str
    route_source: str


AGENT_NODE_NAMES = ("knowledge_agent", "question_agent", "grading_agent", "path_agent")
