"""批改 domain 入口：专用 API 与后续复用共用。

service 层只做 HTTP 映射，不再直接依赖 `rag.llm_calls` / `GRADE_PROMPT`。
"""

from core import settings
from prompts import GRADE_PROMPT
from rag.llm_calls import call_structured
from schema.grading import GradingResult

_NO_STANDARD_ANSWER = "（无标准答案，请基于学科知识判断）"


async def agrade_answer(stem: str, user_answer: str, standard_answer: str = "") -> GradingResult:
    """对单题作答打分；失败抛 RuntimeError（由调用方决定 HTTP/对话语义）。"""
    messages = GRADE_PROMPT.format_messages(
        stem=stem,
        standard_answer=standard_answer or _NO_STANDARD_ANSWER,
        user_answer=user_answer,
    )
    result = await call_structured(
        messages,
        GradingResult,
        temperature=settings.TEMP_PRECISE,
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
