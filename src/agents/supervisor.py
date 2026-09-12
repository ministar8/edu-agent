"""多 Agent 编排：supervisor 路由到 knowledge / question / grading 三个专业 agent。"""

from langgraph_supervisor import create_supervisor

from agents.grading_agent import grading_agent
from agents.knowledge_agent import knowledge_agent
from agents.question_agent import question_agent
from agents.temperature import TEMPERATURE_SUPERVISOR
from core import get_model, settings
from prompts import SUPERVISOR_PROMPT

workflow = create_supervisor(
    [knowledge_agent, question_agent, grading_agent],
    model=get_model(settings.DEFAULT_MODEL, temperature=TEMPERATURE_SUPERVISOR),
    prompt=SUPERVISOR_PROMPT,
    add_handoff_back_messages=True,
    output_mode="full_history",
)

edu_supervisor = workflow.compile()
