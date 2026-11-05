"""出题结构化输出模型（LLM response_format 用）。

聊天路径经 `question_core` 产出 `GeneratedQuestionSet`，再由工具渲染成对话文本。
"""

from typing import Literal

from pydantic import BaseModel, Field

QuestionType = Literal["choice", "fill", "short_answer", "comprehensive"]
QuestionDifficulty = Literal["basic", "medium", "hard"]


class GeneratedQuestion(BaseModel):
    """单道结构化题目（同时用作 LLM 的结构化输出 schema）。"""

    question_type: QuestionType = Field(description="题型：选择/填空/简答/综合应用。")
    difficulty: QuestionDifficulty = Field(description="难度。")
    stem: str = Field(description="题干。**只含题干，不要包含答案或解析**。")
    # ★ 实测缺陷（2026-10-08 §6 整轮，`gen-003`/`007`/`009`/`010`）：模型把这两个字段
    #   **各写各的** —— 标准答案给「能聚合为 /22」而解析说「三者不能合并为单个 CIDR 块」，
    #   或答案里留着「=602？」「→实际为 8」这类自我改口。约束写在字段描述上，
    #   是因为模型正是在填这两个字段的瞬间看得到它（与上方 `stem` 同一手法）。
    standard_answer: str = Field(
        description="标准答案。**必须与 explanation 同结论** —— 解析推出的数值/选项就是这里的答案，两者不得互相矛盾。"
    )
    explanation: str = Field(
        description=(
            "简明解析。**不得自我改口、也不得并列两种口径**（禁止「=602？」「→实际为 8」"
            "「若按另一口径则为 X」这类写法）；先定口径算清楚，再写解析。"
        )
    )


class GeneratedQuestionSet(BaseModel):
    """LLM 结构化输出的外层包装：一次出题产出的题目集合。"""

    questions: list[GeneratedQuestion] = Field(description="生成的题目列表。")
