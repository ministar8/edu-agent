"""出题 Agent：基于题库模板与知识库内容生成 408 练习题。"""

from typing import Any

from langchain.agents import create_agent

from agents.tools import asearch_question_templates
from core import get_model, settings
from prompts import QUESTION_AGENT_SYSTEM_PROMPT, QUESTION_GEN_STRUCTURED_SYSTEM_PROMPT
from schema.questions import GeneratedQuestionSet

question_agent: Any = create_agent(
    model=get_model(settings.DEFAULT_MODEL, temperature=settings.TEMP_CREATIVE),
    tools=[asearch_question_templates],
    name="question_agent",
    system_prompt=QUESTION_AGENT_SYSTEM_PROMPT,
)


# 出题端点专用：同样的 tools / 规则，但要求结构化输出。
# 单独一个实例是因为 question_agent 同时是 supervisor 的子 agent —— 给它加 response_format
# 会改变 chat 路径的产出形态，而这一点无法离线验证。
question_gen_agent: Any = create_agent(
    model=get_model(settings.DEFAULT_MODEL, temperature=settings.TEMP_CREATIVE),
    tools=[asearch_question_templates],
    name="question_gen_agent",
    system_prompt=QUESTION_GEN_STRUCTURED_SYSTEM_PROMPT,
    response_format=GeneratedQuestionSet,
)
