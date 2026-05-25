"""Q&A 字段提取工具

供 Agent 检索时按需取用 merged_qa chunk 的结构化字段：
- question_agent：只需题干（qa.question）
- grading_agent：只需答案+解析（qa.answer）
- knowledge_agent：使用完整 page_content

设计原则：存储合并，检索分离。
"""

from __future__ import annotations

from langchain_core.documents import Document


def extract_question(doc: Document) -> str:
    """从 merged_qa chunk 中提取题干部分

    若 chunk 不是 merged_qa 角色，返回完整 page_content。
    """
    if doc.metadata.get("section.chunk_role") != "merged_qa":
        return doc.page_content

    question = doc.metadata.get("qa.question", "")
    answer_key = doc.metadata.get("qa.answer_key", "")
    if question:
        result = question
        if answer_key:
            result += f"\n正确答案：{answer_key}"
        return result
    return doc.page_content


def extract_answer(doc: Document) -> str:
    """从 merged_qa chunk 中提取答案+解析部分

    若 chunk 不是 merged_qa 角色，返回完整 page_content。
    """
    if doc.metadata.get("section.chunk_role") != "merged_qa":
        return doc.page_content

    answer = doc.metadata.get("qa.answer", "")
    answer_key = doc.metadata.get("qa.answer_key", "")
    if answer:
        result = answer
        if answer_key and not result.startswith(answer_key):
            result = f"正确答案：{answer_key}\n{result}"
        return result
    return doc.page_content


def extract_answer_key(doc: Document) -> str:
    """从 merged_qa chunk 中提取正确答案字母（A/B/C/D/E）"""
    return doc.metadata.get("qa.answer_key", "")


def is_merged_qa(doc: Document) -> bool:
    """判断 chunk 是否为 merged_qa 角色"""
    return doc.metadata.get("section.chunk_role") == "merged_qa"


def build_question_only_context(docs: list[Document]) -> str:
    """构建只含题干的上下文（供 question_agent 使用，避免答案泄露）"""
    parts: list[str] = []
    for i, doc in enumerate(docs, 1):
        source = doc.metadata.get("source_file", "unknown")
        heading = doc.metadata.get("section.path", "")
        question = extract_question(doc)
        header = f"[来源{i}: {source}"
        if heading:
            header += f" | {heading}"
        header += "]"
        parts.append(f"{header}\n{question}")
    return "\n\n".join(parts)


def build_answer_only_context(docs: list[Document]) -> str:
    """构建只含答案+解析的上下文（供 grading_agent 使用）"""
    parts: list[str] = []
    for i, doc in enumerate(docs, 1):
        source = doc.metadata.get("source_file", "unknown")
        heading = doc.metadata.get("section.path", "")
        answer = extract_answer(doc)
        header = f"[来源{i}: {source}"
        if heading:
            header += f" | {heading}"
        header += "]"
        parts.append(f"{header}\n{answer}")
    return "\n\n".join(parts)
