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
    # 只保留子 agent 最后一条回答，避免 full_history 把中间检索/重复内容透传给前端
    output_mode="last_message",
    # 子 agent 完成后不再回插 "Transferring back to supervisor" 这类控制消息
    add_handoff_back_messages=False,
)

# 内层 supervisor（仅分派）。对外图见 teaching_graph.edu_supervisor（含 load_memory）
inner_supervisor = workflow.compile()
