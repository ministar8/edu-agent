from dataclasses import dataclass
from collections.abc import Sequence

from langchain_core.tools import BaseTool
from langgraph.prebuilt import create_react_agent

from app.config import settings
from app.rag.rag_utils import get_llm


@dataclass(frozen=True)
class ReactAgentSpec:
    name: str
    prompt: str
    tools: Sequence[BaseTool]
    temperature: float = settings.TEMP_PRECISE
    use_fast: bool = True


def create_react_tool_agent(spec: ReactAgentSpec) -> object:
    llm = get_llm(temperature=spec.temperature, use_fast=spec.use_fast)
    return create_react_agent(
        model=llm,
        tools=list(spec.tools),
        prompt=spec.prompt,
    )
