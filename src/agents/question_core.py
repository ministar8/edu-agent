"""出题结构化真源：专用 API 与聊天工具共用。

`question_gen_agent` 是唯一 `response_format` 实例；聊天路径通过
`agents.tools.generate_practice_questions` 调用本模块，再做对话修饰。
"""

from typing import Any

from langchain.agents import create_agent

from agents.temperature import TEMPERATURE_QUESTION
from agents.tools import asearch_question_templates
from core import get_model, settings
from prompts import QUESTION_GEN_PROMPT, QUESTION_GEN_STRUCTURED_SYSTEM_PROMPT
from schema.questions import GeneratedQuestionSet

question_gen_agent: Any = create_agent(
    model=get_model(settings.DEFAULT_MODEL, temperature=TEMPERATURE_QUESTION),
    tools=[asearch_question_templates],
    name="question_gen_agent",
    system_prompt=QUESTION_GEN_STRUCTURED_SYSTEM_PROMPT,
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
    """生成结构化练习题；失败抛 RuntimeError（由调用方决定 HTTP/对话语义）。"""
    messages = QUESTION_GEN_PROMPT.format_messages(count=count, topic=topic, difficulty=difficulty)
    state = await question_gen_agent.ainvoke({"messages": messages})
    result: GeneratedQuestionSet | None = state.get("structured_response")
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
