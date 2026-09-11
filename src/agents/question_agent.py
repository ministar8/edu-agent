"""出题 Agent（聊天路径）：经共享工具调用结构化真源，只做对话修饰。

专用出题 API 见 `agents.question_core` / `service.generate_questions`。
"""

from typing import Any

from langchain.agents import create_agent

from agents.tools import agenerate_practice_questions
from core import get_model, settings
from prompts import QUESTION_AGENT_SYSTEM_PROMPT

# supervisor 子 agent：出题一律走 generate_practice_questions（内部共用结构化真源）。
question_agent: Any = create_agent(
    model=get_model(settings.DEFAULT_MODEL, temperature=settings.TEMP_CREATIVE),
    tools=[agenerate_practice_questions],
    name="question_agent",
    system_prompt=QUESTION_AGENT_SYSTEM_PROMPT,
)
