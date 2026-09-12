"""批改 Agent（聊天路径）：经 grading_core 真源打分，只做对话修饰。

专用批改 API 见 `agents.grading_core` / `service.grade_question`。
"""

from typing import Any

from agents.factory import build_agent
from agents.temperature import TEMPERATURE_GRADING
from agents.tools import agrade_student_answer, asearch_standard_answer
from prompts import GRADING_AGENT_SYSTEM_PROMPT

grading_agent: Any = build_agent(
    name="grading_agent",
    tools=[agrade_student_answer, asearch_standard_answer],
    system_prompt=GRADING_AGENT_SYSTEM_PROMPT,
    temperature=TEMPERATURE_GRADING,
)
