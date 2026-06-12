from __future__ import annotations

import logging
import threading

from langchain_core.tools import tool

from app.rag.evidence import TextEvidence
from app.repositories.knowledge_registry_repository import KnowledgeRegistryRepository

logger = logging.getLogger(__name__)

_DIFFICULTY_KEYWORDS = {
    1.0: ["基础", "入门", "概述", "概念", "基本", "初识"],
    1.3: ["理解", "掌握", "原理", "特征", "性质", "定义"],
    1.6: ["综合", "应用", "分析", "设计", "实现", "计算"],
    2.0: ["创新", "优化", "拓展", "高级", "深入", "探究"],
}

_local = threading.local()


def subject_collection(query: str) -> str:
    if "数据结构" in query:
        return "data_structure"
    if "组成原理" in query or "计算机组成" in query:
        return "computer_organization"
    if "操作系统" in query:
        return "operating_system"
    if "计算机网络" in query or "网络" in query:
        return "computer_network"
    return ""


def get_cached_evidences() -> list[TextEvidence]:
    return getattr(_local, "last_evidences", [])


def set_cached_evidences(evidences: list[TextEvidence]) -> None:
    _local.last_evidences = evidences


def extract_difficulty_annotations(evidences: list[TextEvidence], subject: str) -> str:
    annotations: dict[str, str] = {}

    for evidence in evidences:
        knowledge_point = evidence.metadata.get("knowledge_point") or evidence.metadata.get("heading", "")
        if not knowledge_point or knowledge_point in annotations:
            continue

        difficulty = evidence.metadata.get("difficulty")
        difficulty_source = evidence.metadata.get("difficulty_source", "auto")

        if difficulty is not None:
            value = float(difficulty)
            if difficulty_source == "auto" and value == 1.0:
                heading_path = evidence.metadata.get("heading_path", "")
                if not _has_difficulty_keyword(heading_path):
                    annotations[knowledge_point] = "未知"
                    continue
            annotations[knowledge_point] = f"{_difficulty_label(value)}({value:.1f})"
        else:
            registry_difficulty = KnowledgeRegistryRepository.lookup_difficulty_with_managed_session(knowledge_point)
            if registry_difficulty is not None:
                annotations[knowledge_point] = f"{_difficulty_label(registry_difficulty)}({registry_difficulty:.1f})"
            else:
                annotations[knowledge_point] = "未知"

    if not annotations:
        return "难度信息未知，请按混合难度出题。"

    lines = [f"  - {name}：{annotation}" for name, annotation in annotations.items()]
    return "【知识点难度标注】\n" + "\n".join(lines) + "\n请按标注难度生成对应题目；标注「未知」的按中等难度出题。"


def _has_difficulty_keyword(heading_path: str) -> bool:
    return any(keyword in heading_path for keywords in _DIFFICULTY_KEYWORDS.values() for keyword in keywords)


def _difficulty_label(difficulty: float) -> str:
    if difficulty <= 1.1:
        return "基础"
    if difficulty <= 1.4:
        return "理解"
    if difficulty <= 1.7:
        return "综合"
    return "高级"


@tool("search_question_templates")
async def asearch_question_templates(query: str) -> str:
    """异步搜索题库和教材中与指定知识点相关的题目模板、例题和知识点内容（多路召回+Reranker+KG扩展完整管线）。"""
    try:
        subject = subject_collection(query)
        all_evidences: list[TextEvidence] = []
        context_parts: list[str] = []

        if subject:
            from app.rag.retriever import aretrieve_evidence

            subject_fused = await aretrieve_evidence(
                query=query, collection_name=subject, k=5, use_rerank=True
            )
            if subject_fused.final_context:
                context_parts.append(subject_fused.final_context)
            all_evidences.extend(subject_fused.text_evidences)

        from app.rag.retriever import aretrieve_evidence as _aretrieve_evidence

        question_fused = await _aretrieve_evidence(
            query=query, collection_name="questions", k=3, use_rerank=True
        )
        if question_fused.final_context:
            context_parts.append(question_fused.final_context)
        all_evidences.extend(question_fused.text_evidences)

        set_cached_evidences(all_evidences)
        logger.debug("Cached %s evidences for question generation", len(all_evidences))
        for index, evidence in enumerate(all_evidences[:3]):
            logger.debug(
                "  Evidence %s: kp=%s, section_path=%s, collection=%s",
                index,
                evidence.knowledge_points,
                evidence.section_path,
                evidence.collection,
            )

        if not context_parts:
            return "题库和教材中暂无相关内容。"

        context = "\n\n".join(context_parts)
        difficulty_annotation = extract_difficulty_annotations(all_evidences, subject)
        if difficulty_annotation and not difficulty_annotation.startswith("难度信息未知"):
            context = difficulty_annotation + "\n\n" + context

        max_context_chars = 4500
        if len(context) > max_context_chars:
            context = context[:max_context_chars] + "\n\n[上下文已截断：仅保留最相关的题库模板与知识依据。]"
        return context
    except Exception as exc:
        logger.error("Question template search failed: %s", exc, exc_info=True)
        return f"题库检索失败: {exc}"
