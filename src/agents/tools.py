"""共享 RAG 检索工具：供 knowledge / question / grading agent 复用。

检索类工具统一返回 `schema.evidence.RetrievalResult` 的 dict 载荷
（`as_tool_payload`），不再只给一截字符串 —— 引用 UI 与调试依赖 docs 中的
chunk_id / 路径 / 分数。
"""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.tools import tool

from rag.evidence import FusedEvidence
from rag.query_classifier import TEXT_ONLY_DEPTH
from rag.retriever import aretrieve_evidence_with_retry
from rag.verifier import VerificationResult
from schema.evidence import EvidenceDoc, RetrievalResult, _excerpt

logger = logging.getLogger(__name__)

# 工具失败文案统一用「动作失败：原因」全角冒号，便于模型与日志对齐
_ERR_RETRIEVE = "检索失败"
_ERR_GENERATE = "出题失败"
_ERR_GRADE = "批改失败"


def build_retrieval_result(
    *,
    query: str,
    fused: FusedEvidence,
    verification: VerificationResult | None,
) -> RetrievalResult:
    """把检索链内部的 FusedEvidence 映射为对外契约。"""
    docs = [
        EvidenceDoc(
            evidence_id=ev.evidence_id,
            source=ev.source,
            section_path=ev.section_path,
            chunk_id=ev.chunk_id,
            score=ev.score,
            rerank_score=ev.rerank_score,
            knowledge_points=list(ev.knowledge_points),
            excerpt=_excerpt(ev.content),
        )
        for ev in fused.text_evidences
    ]
    sources = [str(s) for s in (fused.sources or [])]
    verdict = str(verification.verdict.value) if verification else ""
    reasons = [str(r) for r in (verification.reasons if verification else [])]

    if not fused.final_context.strip():
        return RetrievalResult(
            status="empty",
            query=query,
            context="知识库中未找到相关内容。",
            sources=sources,
            docs=docs,
            verification=verdict,
            verification_reasons=reasons,
        )

    context = fused.final_context
    if sources:
        context += f"\n\n来源: {', '.join(sources[:5])}"
    if verification and verification.verdict.value != "pass" and reasons:
        context += f"\n\n证据质量: {verdict}; {'; '.join(reasons[:2])}"

    return RetrievalResult(
        status="ok",
        query=query,
        context=context,
        sources=sources,
        docs=docs,
        verification=verdict,
        verification_reasons=reasons,
    )


async def _retrieve_payload(query: str, *, depth=None, k: int = 5) -> dict[str, Any]:
    """统一的「检索 → 对外载荷」封装。"""
    try:
        fused, verification = await aretrieve_evidence_with_retry(
            query=query,
            k=k,
            use_rerank=True,
            depth=depth,
            max_retries=1,
            use_llm_verify=False,
        )
    except Exception as e:
        logger.error("Retrieval failed: %s", e, exc_info=True)
        return RetrievalResult(
            status="error",
            query=query,
            context=f"{_ERR_RETRIEVE}：{e}",
            error=str(e),
        ).as_tool_payload()

    return build_retrieval_result(
        query=query, fused=fused, verification=verification
    ).as_tool_payload()


# 检索工具共用契约说明（拼进各工具 docstring，供模型理解返回值）
_EVIDENCE_PAYLOAD_NOTE = (
    "\n返回 JSON：优先读 `context` 作答；`docs` 含来源/chunk/分数供引用；"
    "`status=empty` 表示知识库无相关内容，`status=error` 表示检索失败"
    " —— 两者都不得编造内容。"
)


def _make_search_tool(name: str, doc: str, *, depth: Any = None):
    """生成检索类 @tool（同一 _retrieve_payload 封装）。"""
    full_doc = doc + _EVIDENCE_PAYLOAD_NOTE

    async def _search(query: str) -> dict[str, Any]:
        return await _retrieve_payload(query, depth=depth)

    # 先写 __doc__ 再包 @tool，否则 description 在装饰时已被捕获
    _search.__doc__ = full_doc
    _search.__name__ = f"a{name}"
    return tool(name)(_search)


aknowledge_search = _make_search_tool(
    "knowledge_search",
    "知识库综合检索（多路召回+BM25+Reranker）。适合大多数概念讲解与原理理解问题。",
)
atext_search = _make_search_tool(
    "text_search",
    "纯教材文本检索（更快的浅层检索）。适合快速查询概念定义、原理说明。",
    depth=TEXT_ONLY_DEPTH,
)
asearch_standard_answer = _make_search_tool(
    "search_standard_answer",
    "检索教材知识库中的标准答案与评分依据。批改学生答案时使用。",
)
asearch_question_templates = _make_search_tool(
    "search_question_templates",
    "检索题库与教材中与知识点相关的题目模板、例题与知识依据。出题时使用。",
)


@tool("generate_practice_questions")
async def agenerate_practice_questions(
    topic: str, count: int = 1, difficulty: str = "mixed"
) -> str:
    """按知识点生成练习题（选择/填空/简答/综合）。返回已排版的题目文本。

    与专用出题 API 共用同一结构化生成核心；本工具只负责对话展示。
    difficulty: basic | medium | hard | mixed
    """
    # 延迟导入：question_core 依赖本模块的 asearch_question_templates
    from agents.question_core import agenerate_question_set, format_questions_for_chat

    try:
        result = await agenerate_question_set(topic=topic, count=count, difficulty=difficulty)
    except Exception as e:
        return f"{_ERR_GENERATE}：{e}"
    return format_questions_for_chat(result)


@tool("grade_student_answer")
async def agrade_student_answer(stem: str, user_answer: str, standard_answer: str = "") -> str:
    """对单题学生作答打分（与专用批改 API 共用 grading_core）。

    stem 必须是**题干本身**，不要包含标准答案或解析。
    standard_answer 可空：为空时会先用题干检索知识库作为评分依据。
    返回已排版的评分/反馈文本，不要自行编造分数。
    """
    from agents.grading_core import agrade_answer, format_grading_for_chat

    std = standard_answer
    if not std.strip():
        payload = await _retrieve_payload(stem)
        if payload.get("status") == "ok":
            std = str(payload.get("context") or "")
        elif payload.get("status") == "error":
            return f"{_ERR_GRADE}：检索标准答案失败（{payload.get('error') or '未知错误'}）"
    try:
        result = await agrade_answer(stem=stem, user_answer=user_answer, standard_answer=std)
    except Exception as e:
        return f"{_ERR_GRADE}：{e}"
    return format_grading_for_chat(result)
