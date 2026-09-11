"""批改 LLM 结构化输出模型。

属于**业务领域**契约，不放在 `rag/schemas.py` —— 后者只保留检索链内部
（分类/分解等）的 LLM 输出 schema。
"""

from pydantic import BaseModel, Field


class GradingResult(BaseModel):
    """单题批改结构化输出（`call_structured` / grading_core 使用）。"""

    score: int = Field(ge=0, le=100, description="0-100 的整数得分")
    feedback: str = Field(max_length=800, description="不超过200字的批改反馈，指出对错和关键点")
    is_wrong: bool = Field(description="学生答案是否错误（score < 60 视为错误）")
    error_analysis: str = Field(
        default="",
        max_length=500,
        description="当is_wrong=True时，分析学生答错的原因：是概念混淆、遗漏要点、还是推理错误，给出具体错因分类和改进建议",
    )
