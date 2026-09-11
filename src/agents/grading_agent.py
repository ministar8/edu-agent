"""批改 Agent：基于标准答案与知识库内容批改 408 学生答案。"""

from typing import Any

from langchain.agents import create_agent

from agents.tools import asearch_standard_answer
from core import get_model, settings
from prompts import GRADING_AGENT_SYSTEM_PROMPT

grading_agent: Any = create_agent(
    model=get_model(settings.DEFAULT_MODEL, temperature=settings.TEMP_PRECISE),
    tools=[asearch_standard_answer],
    name="grading_agent",
    system_prompt=GRADING_AGENT_SYSTEM_PROMPT,
)
