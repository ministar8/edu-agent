"""共享 RAG 检索工具：供 knowledge / question / grading agent 复用。

检索类工具统一返回 `schema.evidence.RetrievalResult` 的 dict 载荷
（`as_tool_payload`），不再只给一截字符串 —— 引用 UI 与调试依赖 docs 中的
chunk_id / 路径 / 分数。
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from langgraph.config import get_stream_writer

from agents.utils import CustomData
from rag.errors import RetrievalUnavailable, classify_retrieval_error
from rag.evidence import FusedEvidence
from rag.query_classifier import TEXT_ONLY_DEPTH
from rag.retriever import StageSink, aretrieve_evidence_with_retry
from rag.verifier import VerificationResult
from schema.evidence import EvidenceDoc, RetrievalResult, excerpt

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
            excerpt=excerpt(ev.content),
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


def _stage_sink() -> StageSink | None:
    """把「检索阶段进度」接到 SSE 的回调；拿不到 writer 时返回 None。

    为什么放在这里而不是 `rag/`：检索链是纯计算层，不该知道 SSE 的存在。
    由这一层（已经依赖 `agents.utils`）把回调注入进去，UI 关注点就留在上层。

    ⚠️ **必须守卫 `get_stream_writer()`** —— 它内部读的是 runnable 上下文，
    在没有 graph 上下文时（直接调用工具、离线评测、脚本）会抛
    `RuntimeError: Called get_config outside of a runnable context`。
    不守卫的话检索链会崩在「进度上报」这种锦上添花的事情上。
    返回 None 时 `rag/` 走 no-op 分支，**检索行为与加这个功能之前完全一致**。
    """
    try:
        writer = get_stream_writer()
    except Exception:
        # 拿不到 writer 是正常情况（非流式调用），绝不能影响检索
        logger.debug("无 stream writer，跳过检索阶段进度上报", exc_info=True)
        return None

    def emit(stage: str) -> None:
        CustomData(data={"kind": "retrieval_stage", "stage": stage}).dispatch(writer)

    return emit


def _docs_sink() -> Callable[[RetrievalResult], None] | None:
    """把「检索到的来源文档」接到 SSE 的回调；拿不到 writer 时返回 None。

    引用溯源 UI 的数据源：前端在 `custom` 流上按 ``kind == "retrieval_docs"`` 收集，
    回答渲染完成后折叠展示（文件名 + 章节路径 + 分数 + 摘录）。
    发端在这里、收端在 ``static/app.js``。

    守卫理由与 ``_stage_sink`` 完全相同 —— 非流式调用（直接调工具、离线评测、脚本）
    下 ``get_stream_writer()`` 会抛 ``RuntimeError``。拿不到 writer 就静默跳过，
    **绝不影响检索本身**：引用 UI 是锦上添花，不该让检索为它崩掉。
    """
    try:
        writer = get_stream_writer()
    except Exception:
        logger.debug("无 stream writer，跳过引用来源下发", exc_info=True)
        return None

    def emit(result: RetrievalResult) -> None:
        # 没有 docs（empty / error）就不发 —— 前端据此不必处理空列表
        if not result.docs:
            return
        CustomData(
            data={
                "kind": "retrieval_docs",
                "query": result.query,
                # mode="json" 保证可 JSON 序列化（前端按普通对象消费）
                "docs": [doc.model_dump(mode="json") for doc in result.docs],
            }
        ).dispatch(writer)

    return emit


def _retrieval_error_payload(query: str, exc: BaseException) -> dict[str, Any]:
    """把检索异常映射为对外载荷，**按类别**决定日志级别与文案。

    这是「三类失败被抹平成同一类」的修复点：
    在此之前一律 `logger.error` + `检索失败：{e}`，于是日志里的 ERROR
    既可能是 TEI 抖了一下，也可能是真代码缺陷，值班的人无从判断。

    - `RetrievalUnavailable` → WARNING（**不触发告警**）+ 可重试文案
    - 其余 → ERROR + 完整堆栈（**必须有人看**）

    两种情况的 `status` 仍是 `"error"`（对外契约不变），但 `error_kind`
    让程序可以区分 —— 空结果则走 `status="empty"` 的正常路径，不经此处。
    """
    err = classify_retrieval_error(exc)
    if isinstance(err, RetrievalUnavailable):
        logger.warning("检索依赖不可用（可重试）：%s", err, exc_info=True)
        kind = "unavailable"
        context = f"{_ERR_RETRIEVE}：知识库服务暂时不可用，请稍后重试"
    else:
        logger.exception("检索内部错误（需排查）：%s", err)
        kind = "internal"
        context = f"{_ERR_RETRIEVE}：{err}"

    return RetrievalResult(
        status="error",
        query=query,
        context=context,
        error=str(err),
        error_kind=kind,
    ).as_tool_payload()


async def _retrieve_payload(query: str, *, depth=None, k: int = 5) -> dict[str, Any]:
    """统一的「检索 → 对外载荷」封装。

    catch-all 只允许出现在这类**最外层边界**（见 §2.2 规范 2），
    且必须分级处理 —— 具体分级见 `_retrieval_error_payload`。
    """
    try:
        fused, verification = await aretrieve_evidence_with_retry(
            query=query,
            k=k,
            # True = 「这条路径按重排口径准备候选池」，**不是**开关 ——
            # 实际是否重排由 .env 的 RERANK_ENABLED 决定（见 retriever 模块的「重排判定链」）。
            use_rerank=True,
            depth=depth,
            max_retries=1,
            use_llm_verify=False,
            on_stage=_stage_sink(),
        )
    except Exception as e:
        return _retrieval_error_payload(query, e)

    result = build_retrieval_result(query=query, fused=fused, verification=verification)
    # 引用溯源：把来源文档下发到前端（拿不到 stream writer 时是 no-op）
    emit_docs = _docs_sink()
    if emit_docs is not None:
        emit_docs(result)
    return result.as_tool_payload()


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
    topic: str,
    count: int = 1,
    difficulty: str = "mixed",
    config: RunnableConfig | None = None,
) -> str:
    """按知识点生成练习题（选择/填空/简答/综合）。返回已排版的题目文本。

    与专用出题 API 共用同一结构化生成核心；本工具只负责对话展示。
    difficulty: basic | medium | hard | mixed
    """
    # 延迟导入：question_core 依赖本模块的 asearch_question_templates
    from agents.question_core import agenerate_question_set, format_questions_for_chat
    from memory.remember import record_question, thread_id_from_config, user_id_from_config

    try:
        result = await agenerate_question_set(topic=topic, count=count, difficulty=difficulty)
    except Exception as e:
        return f"{_ERR_GENERATE}：{e}"
    uid = user_id_from_config(config)
    batch_id = ""
    if uid:
        _, batch_id = await record_question(
            user_id=uid,
            topic=topic,
            thread_id=thread_id_from_config(config),
            agent_path="chat_question",
            count=count,
        )
    body = format_questions_for_chat(result)
    if batch_id:
        body += f"\n\n（练习批次 batch_id: `{batch_id}`，批改时可带上以便关联）"
    return body


@tool("grade_student_answer")
async def agrade_student_answer(
    stem: str,
    user_answer: str,
    standard_answer: str = "",
    config: RunnableConfig | None = None,
) -> str:
    """对单题学生作答打分（与专用批改 API 共用 grading_core）。

    stem 必须是**题干本身**，不要包含标准答案或解析。
    standard_answer 可空：为空时会先用题干检索知识库作为评分依据。
    返回已排版的评分/反馈文本，不要自行编造分数。
    """
    from agents.grading_core import agrade_answer, format_grading_for_chat
    from memory.remember import (
        batch_id_from_config,
        record_grade,
        thread_id_from_config,
        user_id_from_config,
    )

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
    uid = user_id_from_config(config)
    if uid:
        await record_grade(
            user_id=uid,
            topic=stem[:80],
            score=float(result.score),
            error_analysis=result.error_analysis or "",
            stem=stem,
            thread_id=thread_id_from_config(config),
            agent_path="chat_grade",
            batch_id=batch_id_from_config(config),
        )
    return format_grading_for_chat(result)
