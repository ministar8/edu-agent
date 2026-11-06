"""专业 Agent Prompt 统一导出。"""

from prompts.agents.knowledge import KNOWLEDGE_AGENT_SYSTEM_PROMPT
from prompts.agents.question import QUESTION_AGENT_SYSTEM_PROMPT
from prompts.agents.grading import GRADING_AGENT_SYSTEM_PROMPT

__all__ = [
    "KNOWLEDGE_AGENT_SYSTEM_PROMPT",
    "QUESTION_AGENT_SYSTEM_PROMPT",
    "GRADING_AGENT_SYSTEM_PROMPT",
]
