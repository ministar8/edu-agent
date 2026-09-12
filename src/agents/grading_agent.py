"""批改 Agent（聊天路径）：经 grading_core 真源打分，只做对话修饰。

专用批改 API 见 `agents.grading_core` / `service.grade_question`。
"""

from typing import Any

from langchain.agents import create_agent

from agents.temperature import TEMPERATURE_GRADING
from agents.tools import agrade_student_answer, asearch_standard_answer
from core import get_model, settings
from prompts import GRADING_AGENT_SYSTEM_PROMPT

# supervisor 子 agent：打分一律走 grade_student_answer（内部共用 grading_core）。
grading_agent: Any = create_agent(
    model=get_model(settings.DEFAULT_MODEL, temperature=TEMPERATURE_GRADING),
    tools=[agrade_student_answer, asearch_standard_answer],
    name="grading_agent",
    system_prompt=GRADING_AGENT_SYSTEM_PROMPT,
)
