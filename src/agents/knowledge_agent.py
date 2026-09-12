"""知识讲解 Agent：基于 RAG 检索回答 408 考研概念与原理问题。"""

from typing import Any

from langchain.agents import create_agent

from agents.temperature import TEMPERATURE_KNOWLEDGE
from agents.tools import aknowledge_search, atext_search
from core import get_model, settings
from prompts import KNOWLEDGE_AGENT_SYSTEM_PROMPT

knowledge_agent: Any = create_agent(
    model=get_model(settings.DEFAULT_MODEL, temperature=TEMPERATURE_KNOWLEDGE),
    tools=[aknowledge_search, atext_search],
    name="knowledge_agent",
    system_prompt=KNOWLEDGE_AGENT_SYSTEM_PROMPT,
)
