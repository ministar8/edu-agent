"""检索证据的**对外契约**（tools / 未来 API / 前端引用）。

`rag.evidence.FusedEvidence` 是检索链内部模型，字段与演进绑定 Chroma/融合逻辑；
本模块只描述「工具与调用方看得见的证据」，**禁止 import rag**。

约定：
- LLM 优先读 `context`（已拼好的可引用正文）
- 机器/前端读 `docs`（含 chunk_id、路径、分数）
- `status` 显式区分 empty/error，避免只靠自然语言句子
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

# 工具结果里给模型看的正文最多保留的单文档字符数（完整正文仍在检索链内部）
DOC_EXCERPT_MAX_CHARS = 400


class EvidenceDoc(BaseModel):
    """单条可引用证据（对外精简字段）。"""

    evidence_id: str = Field(default="", description="证据 ID")
    source: str = Field(default="unknown", description="来源文件名")
    section_path: str = Field(default="", description="章节路径")
    chunk_id: str = Field(default="", description="chunk ID（引用定位）")
    score: float = Field(default=0.0, description="综合得分")
    rerank_score: float = Field(default=0.0, description="重排得分")
    knowledge_points: list[str] = Field(default_factory=list)
    excerpt: str = Field(default="", description="正文摘录（可能截断）")


class RetrievalResult(BaseModel):
    """一次检索工具调用的结构化结果。"""

    status: Literal["ok", "empty", "error"] = Field(description="检索结局")
    query: str = Field(default="", description="实际用于检索的查询")
    context: str = Field(
        default="",
        description="给 LLM 的正文（含来源/质量注记）；empty/error 时为说明句",
    )
    sources: list[str] = Field(default_factory=list, description="去重后的来源文件名")
    docs: list[EvidenceDoc] = Field(default_factory=list)
    verification: str = Field(default="", description="证据校验 verdict，如 pass/warn/fail")
    verification_reasons: list[str] = Field(default_factory=list)
    error: str | None = Field(default=None, description="status=error 时的错误摘要")
    error_kind: Literal["unavailable", "internal"] | None = Field(
        default=None,
        description=(
            "status=error 时的**机器可读**分类："
            "unavailable=外部依赖暂时不可用（可重试，别当故障上报）；"
            "internal=检索链内部缺陷（重试无用，需排查）。"
            "只有 status=error 时非空；empty 是正常结局，不属于错误。"
        ),
    )

    def as_tool_payload(self) -> dict[str, Any]:
        """工具返回值：模型读 context，程序读 docs/status。"""
        return self.model_dump()


def excerpt(text: str, limit: int = DOC_EXCERPT_MAX_CHARS) -> str:
    """截断正文摘录（超长加省略号）。"""
    text = text or ""
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"
