"""出题与批改的请求/响应模型。

请求字段全部来自客户端，属于**不可信输入**，因此都在这里设长度上限 ——
在**入口**拦下，而不是在提示词里静默截断（后者会让 LLM 收到被悄悄改过的数据，
是更差的失败模式）。`difficulty` 用 Literal 而不是 str：它会被拼进提示词，
穷举校验比长度校验更准。

出题返回**结构化题目**（而非一整页 Markdown），目的是让前端能把「单题的题干 + 该题
标准答案」原样交给批改端点 —— 否则批改只能拿到含答案的整页文本，见 GRADE_PROMPT。
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
    standard_answer: str = Field(description="标准答案。")
    explanation: str = Field(description="简明解析。")


class GeneratedQuestionSet(BaseModel):
    """LLM 结构化输出的外层包装：一次出题产出的题目集合。"""

    questions: list[GeneratedQuestion] = Field(description="生成的题目列表。")


class QuestionRequest(BaseModel):
    topic: str = Field(max_length=200, description="知识点，如「进程死锁」。")
    count: int = Field(default=1, ge=1, le=5)
    difficulty: Literal["basic", "medium", "hard", "mixed"] = "mixed"


class QuestionResponse(BaseModel):
    questions: list[GeneratedQuestion] = Field(description="结构化题目列表。")
    batch_id: str | None = None


class GradeRequest(BaseModel):
    stem: str = Field(max_length=2000, description="题干（只含题干，不含答案）。")
    standard_answer: str = Field(default="", max_length=2000, description="标准答案，可为空。")
    user_answer: str = Field(max_length=5000, description="学生作答（不可信输入）。")
    batch_id: str = Field(default="", max_length=64, description="出题 batch_id（显式外键，可选）")
    question_id: str = Field(default="", max_length=64, description="单题 id（可选）")


class GradeResponse(BaseModel):
    score: float
    feedback: str
    error_analysis: str = ""
