"""提示词服务层：变量准备 + 模板调用。

职责边界：
- Prompt 内容**不在这里定义**：静态 System Prompt 见 `prompts.agents`，
  ChatPromptTemplate 见 `prompts.templates`。
- 本层只做「调用前的变量准备」：清洗输入、补默认值、约束取值范围，
  再调用模板的 `format_messages()`，返回可直接发给模型的消息列表。

调用点：
  - build_grade_messages        → agents/specialists/grading.py
  - build_question_gen_messages → agents/specialists/question.py
"""

from __future__ import annotations

from langchain_core.messages import BaseMessage

from prompts.templates.grading import GRADE_PROMPT
from prompts.templates.question import QUESTION_GEN_PROMPT

# 无标准答案时的占位：提示模型基于学科知识判断，而不是拒绝批改
NO_STANDARD_ANSWER = "（无标准答案，请基于学科知识判断）"

# 出题数量允许区间：防止模型传 0、负数或超大值
MIN_QUESTION_COUNT = 1
MAX_QUESTION_COUNT = 10

# 难度白名单：非法值统一回落为 mixed
VALID_DIFFICULTIES = ("basic", "medium", "hard", "mixed")


def _clean_text(value: str, *, field: str, required: bool) -> str:
    """去掉首尾空白；required=True 时拒绝空值。"""
    text = (value or "").strip()
    if required and not text:
        raise ValueError(f"{field}不能为空")
    return text


def build_grade_messages(
    *,
    stem: str,
    user_answer: str,
    standard_answer: str = "",
) -> list[BaseMessage]:
    """准备批改变量并组装消息。

    变量约定：
    - stem / user_answer 必填，去掉首尾空白；
    - standard_answer 为空时用 NO_STANDARD_ANSWER 兜底，
      保证模板变量永远有值，模型不会因缺字段而拒答。
    """
    return GRADE_PROMPT.format_messages(
        stem=_clean_text(stem, field="题干", required=True),
        standard_answer=(
            _clean_text(standard_answer, field="标准答案", required=False)
            or NO_STANDARD_ANSWER
        ),
        user_answer=_clean_text(user_answer, field="学生答案", required=True),
    )


def build_question_gen_messages(
    *,
    topic: str,
    count: int = MIN_QUESTION_COUNT,
    difficulty: str = "mixed",
) -> list[BaseMessage]:
    """准备出题变量并组装消息。

    变量约定：
    - topic 必填，去掉首尾空白；
    - count 收口到 [MIN_QUESTION_COUNT, MAX_QUESTION_COUNT]，非整数按 1 处理；
    - difficulty 只接受 VALID_DIFFICULTIES，非法值回落 mixed。
    """
    try:
        parsed_count = int(count)
    except (TypeError, ValueError):
        parsed_count = MIN_QUESTION_COUNT

    return QUESTION_GEN_PROMPT.format_messages(
        count=max(MIN_QUESTION_COUNT, min(parsed_count, MAX_QUESTION_COUNT)),
        topic=_clean_text(topic, field="主题", required=True),
        difficulty=difficulty if difficulty in VALID_DIFFICULTIES else "mixed",
    )
