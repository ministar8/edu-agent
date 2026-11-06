"""批改专家：结构化真源 + 聊天路径薄壳（同一模块、职责分离）。

- **真源**（业务函数）：``agrade_answer`` / ``format_grading_for_chat``。
  模块级**不**建 LLM 实例（与 question 不同）；service 只依赖本真源。
- **薄壳**：``grading_agent`` 只接线聊天工具与 system prompt。
"""

from typing import Any

from agents.runtime.factory import build_agent
from agents.runtime.temperature import TEMPERATURE_GRADING
from agents.runtime.tools import agrade_student_answer, asearch_standard_answer
from core import settings
from prompts.agents.grading import GRADING_AGENT_SYSTEM_PROMPT
from prompts.service import build_grade_messages
from rag.retrieval.llm_calls import call_structured
from schema.grading import GradingResult

# ── 业务真源 ──────────────────────────────────────────────────────────


async def agrade_answer(stem: str, user_answer: str, standard_answer: str = "") -> GradingResult:
    """对单题作答打分；失败抛 RuntimeError（由调用方决定 HTTP/对话语义）。"""
    messages = build_grade_messages(
        stem=stem,
        user_answer=user_answer,
        standard_answer=standard_answer,
    )
    result = await call_structured(
        messages,
        GradingResult,
        temperature=TEMPERATURE_GRADING,
        timeout=settings.LLM_TIMEOUT,
        stage="grading",
    )
    if result is None:
        raise RuntimeError("批改失败")
    return result


def format_grading_for_chat(result: GradingResult) -> str:
    """把结构化批改结果渲染成对话体（与专用 API 同一真源）。"""
    lines = [
        f"评分：{result.score}/100",
        f"结论：{result.feedback}",
    ]
    if result.is_wrong and result.error_analysis:
        lines.append(f"错因与建议：{result.error_analysis}")
    return "\n".join(lines)


# ── 聊天路径薄壳 ──────────────────────────────────────────────────────

grading_agent: Any = build_agent(
    name="grading_agent",
    tools=[agrade_student_answer, asearch_standard_answer],
    system_prompt=GRADING_AGENT_SYSTEM_PROMPT,
    temperature=TEMPERATURE_GRADING,
)
