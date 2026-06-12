import logging

from app.config import settings
from app.agents.agent_factory import ReactAgentSpec, create_react_tool_agent
from app.agents.kg_tools import aquery_knowledge_graph
from app.agents.prompts import QUESTION_AGENT_SYSTEM_PROMPT as QUESTION_AGENT_PROMPT
from app.agents.question_tools import asearch_question_templates, get_cached_evidences
from app.services.question_generation_service import (
    compute_quality_scores,
    extract_topic,
    generate_questions_from_prompt,
    generate_questions_with_retrieval,
    parse_questions_from_raw,
)

logger = logging.getLogger(__name__)


async def generate_and_persist_questions(
    prompt: str,
    user_id: int,
    conversation_id: int | None = None,
    topic: str = "",
) -> list[dict]:
    """兼容入口：旧调用方仍可请求出题并持久化。"""
    from app.services.question_service import persist_generated_questions_with_managed_session

    questions = await generate_questions_from_prompt(prompt)
    if not questions or questions[0].get("error") or questions[0].get("raw_text"):
        return questions

    try:
        persist_generated_questions_with_managed_session(
            questions,
            user_id=user_id,
            conversation_id=conversation_id,
            topic=topic or extract_topic(prompt),
            evidences=get_cached_evidences(),
        )
    except Exception as e:
        logger.warning("Failed to persist questions: %s", e)
    return questions


# ── Agent 定义 ──────────────────────────────────────────────────


def create_question_agent():
    """创建题目生成Agent（ReAct 模式，供 Supervisor 路由使用）"""
    return create_react_tool_agent(
        ReactAgentSpec(
            name="question_agent",
            prompt=QUESTION_AGENT_PROMPT,
            tools=[
                asearch_question_templates,
                aquery_knowledge_graph,
            ],
            temperature=settings.TEMP_CREATIVE,
        )
    )


__all__ = [
    "asearch_question_templates",
    "compute_quality_scores",
    "create_question_agent",
    "generate_and_persist_questions",
    "generate_questions_from_prompt",
    "generate_questions_with_retrieval",
    "get_cached_evidences",
    "parse_questions_from_raw",
]
