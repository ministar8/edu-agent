"""出题 Agent（聊天路径）：经共享工具调用结构化真源，只做对话修饰。

专用出题 API 见 `agents.question_core` / `service.generate_questions`。
"""

from typing import Any

from agents.factory import build_agent
from agents.temperature import TEMPERATURE_QUESTION
from agents.tools import agenerate_practice_questions
from prompts import QUESTION_AGENT_SYSTEM_PROMPT

question_agent: Any = build_agent(
    name="question_agent",
    tools=[agenerate_practice_questions],
    system_prompt=QUESTION_AGENT_SYSTEM_PROMPT,
    temperature=TEMPERATURE_QUESTION,
)
