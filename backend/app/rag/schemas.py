"""LLM 结构化输出 Pydantic Schema 定义

用于 with_structured_output()，替代裸 Prompt + 正则/手动 JSON 解析。
DeepSeek / qwen 系列均支持 Function Calling，with_structured_output 内部优先使用 tool_call，
模型不支持时自动回退到 JSON Schema 注入（= PydanticOutputParser 行为）。
"""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator


# ── 批改结果 ──────────────────────────────────────────


class GradingResult(BaseModel):
    """单题批改结构化输出"""
    score: int = Field(ge=0, le=100, description="0-100 的整数得分")
    feedback: str = Field(max_length=800, description="不超过200字的批改反馈，指出对错和关键点")
    is_wrong: bool = Field(description="学生答案是否错误（score < 60 视为错误）")


# ── 出题结果 ──────────────────────────────────────────


class QuestionItem(BaseModel):
    """单道题目"""
    question_type: str = Field(description="题目类型：选择/填空/简答/综合")
    difficulty: float = Field(ge=1.0, le=2.0, description="难度：1.0基础 1.3中等 1.6较难 2.0困难")
    stem: str = Field(description="题干全文")
    answer: str = Field(description="标准答案")
    explanation: str = Field(description="解析，不超过80字")


class QuestionList(BaseModel):
    """出题结果结构化输出"""
    questions: list[QuestionItem] = Field(description="生成的题目列表")


# ── 查询分解结果 ──────────────────────────────────────


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


# ── KG 抽取结果 ──────────────────────────────────────


class KGNode(BaseModel):
    """知识点节点"""
    name: str = Field(description="知识点名称")
    description: str = Field(description="简短描述")


class KGEdge(BaseModel):
    """知识点关系"""
    source: str = Field(description="前置/来源知识点名称")
    target: str = Field(description="后续/目标知识点名称")
    relation: str = Field(description="关系类型：PREREQUISITE_OF 或 RELATED_TO")


class KGExtractResult(BaseModel):
    """KG 抽取结构化输出"""
    nodes: list[KGNode] = Field(description="知识点节点列表")
    edges: list[KGEdge] = Field(description="知识点关系列表")


# ── 查询分类结果 ──────────────────────────────────────


class QueryClassifyResult(BaseModel):
    """查询分类结构化输出"""
    model_config = {"populate_by_name": True}

    categories: list[str] = Field(
        alias="intent",
        min_length=1,
        max_length=7,
        description="命中的分类标签，可选值：code, exercise, answer, structured, concept, comparison, learning_path, uncategorized",
    )
