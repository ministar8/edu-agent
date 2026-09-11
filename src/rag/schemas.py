"""检索链内部的 LLM 结构化输出 Schema。

领域模型（如批改 `GradingResult`）见 `schema/grading.py`，不要放这里。
出题 HTTP/LLM 模型见 `schema/questions.py`。
"""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator


class DecomposeResult(BaseModel):
    """查询分解结构化输出"""

    model_config = {"populate_by_name": True}

    sub_queries: list[str] = Field(
        alias="sub_questions",
        min_length=1,
        max_length=4,
        description="拆分后的子问题列表，每个聚焦单一知识点。如果无需分解，返回原始查询。",
    )

    @model_validator(mode="before")
    @classmethod
    def _wrap_bare_list(cls, data):
        """LLM 有时直接返回 list 而非 {"sub_queries": list}，自动包装"""
        if isinstance(data, list):
            return {"sub_queries": data}
        return data


class QueryClassifyResult(BaseModel):
    """查询分类结构化输出"""

    model_config = {"populate_by_name": True}

    categories: list[str] = Field(
        alias="intent",
        min_length=1,
        max_length=7,
        description="命中的分类标签，可选值：code, exercise, answer, structured, concept, comparison, learning_path, uncategorized",
    )
