"""出题专家：结构化真源 + 聊天路径薄壳（同一模块、职责分离）。

- **真源**（业务函数，不塞进 Agent 构建）：
  ``agenerate_question_set`` / ``format_questions_for_chat`` /
  ``question_gen_agent``（唯一 ``response_format`` 实例）。
- **薄壳**：``question_agent`` 只接线聊天工具与 system prompt。

两层可在同文件，但业务逻辑保持独立函数；core 增长到数百行时再拆
``question/{agent,core}.py``，现在不必。
"""

from typing import Any

from agents.runtime.factory import build_agent
from agents.runtime.temperature import TEMPERATURE_QUESTION
from agents.runtime.tools import agenerate_practice_questions, asearch_question_templates
from prompts.agents.question import (
    QUESTION_AGENT_SYSTEM_PROMPT,
    QUESTION_GEN_STRUCTURED_SYSTEM_PROMPT,
)
from prompts.service import build_question_gen_messages
from schema.questions import GeneratedQuestionSet

# ── 业务真源 ──────────────────────────────────────────────────────────

question_gen_agent: Any = build_agent(
    name="question_gen_agent",
    tools=[asearch_question_templates],
    system_prompt=QUESTION_GEN_STRUCTURED_SYSTEM_PROMPT,
    temperature=TEMPERATURE_QUESTION,
    response_format=GeneratedQuestionSet,
)

_TYPE_LABEL = {
    "choice": "选择",
    "fill": "填空",
    "short_answer": "简答",
    "comprehensive": "综合应用",
}
_DIFFICULTY_LABEL = {
    "basic": "基础",
    "medium": "理解",
    "hard": "综合",
}


async def agenerate_question_set(
    topic: str, count: int = 1, difficulty: str = "mixed"
) -> GeneratedQuestionSet:
    """生成结构化练习题；失败抛 RuntimeError（由调用方决定 HTTP/对话语义）。

    structured output 偶发失败（模型输出不满足 schema）时重试一次，再失败才抛错。
    """
    messages = build_question_gen_messages(topic=topic, count=count, difficulty=difficulty)
    state = await question_gen_agent.ainvoke({"messages": messages})
    result: GeneratedQuestionSet | None = state.get("structured_response")
    if result is None:
        retry_state = await question_gen_agent.ainvoke({"messages": messages})
        result = retry_state.get("structured_response")
        if result is None:
            raise RuntimeError("出题失败：未返回结构化结果")
    return result


def format_questions_for_chat(result: GeneratedQuestionSet) -> str:
    """把结构化题目渲染成对话体 Markdown（题干/答案/解析字段不合并）。"""
    blocks: list[str] = []
    for i, q in enumerate(result.questions, 1):
        type_label = _TYPE_LABEL.get(q.question_type, q.question_type)
        diff_label = _DIFFICULTY_LABEL.get(q.difficulty, q.difficulty)
        blocks.append(
            f"**题目{i}**\n"
            f"类型：{type_label}\n"
            f"难度：{diff_label}\n"
            f"题干：{q.stem}\n"
            f"标准答案：{q.standard_answer}\n"
            f"解析：{q.explanation}"
        )
    return "\n\n".join(blocks) if blocks else "本次未能生成题目，请换一个知识点或稍后再试。"


# ── 聊天路径薄壳 ──────────────────────────────────────────────────────

question_agent: Any = build_agent(
    name="question_agent",
    tools=[agenerate_practice_questions],
    system_prompt=QUESTION_AGENT_SYSTEM_PROMPT,
    temperature=TEMPERATURE_QUESTION,
)
