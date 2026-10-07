"""批改 LLM 结构化输出模型。

属于**业务领域**契约，不放在 `rag/schemas.py` —— 后者只保留检索链内部
（分类/分解等）的 LLM 输出 schema。
"""

from pydantic import BaseModel, Field, field_validator

# ★ 2026-10-06（Step 5 实测）：`feedback` 是**展示字段**（渲染进对话体给用户看），
#   不是事实源 —— 事实源是 `score` / `knowledge_points`。
#   实测模型在 function_calling 模式下偶发把**解体过程**（"等等，重新计算……"、
#   英文的 "Let's output."）一起塞进 feedback，长度可达 2000+ 字符。
#   此时若因超长而**整体判失败**，等于为一句话的长度丢掉整次批改 + Memory 写入，
#   代价与收益严重不匹配。故：**软约束 + 截断**，而非硬拒绝。
_FEEDBACK_SOFT_LIMIT = 800
_ERROR_ANALYSIS_SOFT_LIMIT = 500


class GradingResult(BaseModel):
    """单题批改结构化输出（`call_structured` / grading_core 使用）。"""

    score: int = Field(ge=0, le=100, description="0-100 的整数得分")
    feedback: str = Field(
        default="",
        description="不超过200字的批改反馈，指出对错和关键点（过长会被截断）",
    )
    is_wrong: bool = Field(description="学生答案是否错误（score < 60 视为错误）")
    error_analysis: str = Field(
        default="",
        description="当is_wrong=True时，分析学生答错的原因：是概念混淆、遗漏要点、还是推理错误，给出具体错因分类和改进建议",
    )
    # ★ 2026-10-06 Phase 1.5「Memory」修复新增。
    #   此前 Memory 写入用 `topic=stem[:80]`（题干前 80 字符）⇒ 记忆里存的是
    #   「某道题的开头」而不是「用户在哪个知识点上薄弱」，`weak_topics` 语义失真。
    #   这里让批改 LLM 顺带输出**本题考查的标准知识点名**，作为 Memory 聚合的
    #   **唯一事实源**（`Episode.knowledge_points`）。
    knowledge_points: list[str] = Field(
        default_factory=list,
        description=(
            "本题考查的**标准知识点名称**（1–3 个），须用教材/考纲的规范考点名，"
            "例如「平衡二叉树」「图」「TCP 流量控制」「进程同步」。"
            "**不是题干摘要、不是题目内容、不是学科名**；"
            "不确定时给最贴切的一个，宁可少给也不要编造。"
        ),
    )

    @field_validator("feedback", "error_analysis", mode="before")
    @classmethod
    def _truncate_long_text(cls, value: object, info) -> object:
        """超长文本**截断**而非拒绝 —— 见模块顶部说明。

        用 `mode="before"` 在长度校验之前动手，这样既能收口，又能让 pydantic
        继续做类型检查（非 str 输入交给它报错）。
        """
        if not isinstance(value, str):
            return value
        limit = (
            _FEEDBACK_SOFT_LIMIT if info.field_name == "feedback" else _ERROR_ANALYSIS_SOFT_LIMIT
        )
        if len(value) <= limit:
            return value
        return value[: limit - 1] + "…"
