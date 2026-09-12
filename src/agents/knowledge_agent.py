"""知识讲解 Agent：基于 RAG 检索回答 408 考研概念与原理问题。"""

from typing import Any

from agents.factory import build_agent
from agents.temperature import TEMPERATURE_KNOWLEDGE
from agents.tools import aknowledge_search, atext_search
from prompts import KNOWLEDGE_AGENT_SYSTEM_PROMPT

knowledge_agent: Any = build_agent(
    name="knowledge_agent",
    tools=[aknowledge_search, atext_search],
    system_prompt=KNOWLEDGE_AGENT_SYSTEM_PROMPT,
    temperature=TEMPERATURE_KNOWLEDGE,
)
