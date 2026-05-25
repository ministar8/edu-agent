"""上下文构建模块

职责：KG 关联知识补充、RAG 上下文拼接（含全局 token 预算控制）
"""

from __future__ import annotations

import logging

from langchain_core.documents import Document

from app.config import settings
from app.rag.rag_utils import estimate_tokens as _estimate_tokens

logger = logging.getLogger(__name__)


def kg_context_supplement(query: str, max_related: int = 5, category: str = "") -> str:
    """从知识图谱获取关联知识点，构建上下文补充段落

    查询 KG 获取 query 对应节点的学习路径和前置知识，
    格式化为结构化文本附加到 RAG context 末尾。

    拓扑保留：输出 前置->当前->后续 的有向链路，而非扁平名称列表，
    让 LLM 能理解知识点之间的依赖/递进关系。

    防泛化约束：
    - 仅取直接相邻节点（1跳），不做深度遍历
    - 最多 max_related 个关联知识点
    - 每个知识点描述截断 100 字
    - KG 查询失败时静默降级

    Args:
        query: 查询文本
        max_related: 最大关联知识点数
        category: KG 分类限定（用于跨学科消歧，空=不限）
    """
    try:
        from app.rag.knowledge_graph import get_kg_manager
        kg_manager = get_kg_manager()
        resolved = kg_manager.resolve_topic(query, category=category)
        if not resolved:
            return ""

        parts: list[str] = []
        count = 0

        # 当前知识点名称
        current_name = resolved

        # 前置知识（保留依赖关系：前置 → 当前）
        prerequisites = kg_manager.get_prerequisites(resolved)
        if prerequisites:
            pre_names = [p.get("name", "") for p in prerequisites if p.get("name")]
            if pre_names:
                # 用箭头表达依赖方向
                chain = " → ".join(pre_names[:max_related]) + f" → 【{current_name}】"
                parts.append(f"前置知识链: {chain}")
                count += len(pre_names[:max_related])

        # 后续知识（保留递进关系：当前 → 后续）
        next_topics = kg_manager.get_next_topics(resolved)
        if next_topics and count < max_related:
            next_names = [n.get("name", "") for n in next_topics if n.get("name")]
            remaining = max_related - count
            if next_names:
                chain = f"【{current_name}】 → " + " → ".join(next_names[:remaining])
                parts.append(f"后续知识链: {chain}")
                count += len(next_names[:remaining])

        # 学习路径（保留完整路径拓扑）
        if count < max_related:
            learning_path = kg_manager.get_learning_path(resolved)
            if learning_path:
                first_path = learning_path[0] if isinstance(learning_path[0], list) else learning_path
                path_names = [step.get("name", "") for step in first_path if step.get("name")]
                remaining = max_related - count
                if path_names:
                    parts.append(f"学习路径: {' → '.join(path_names[:remaining + 1])}")

        if not parts:
            return ""

        return "【知识图谱关联信息】\n" + "\n".join(parts)
    except Exception as e:
        logger.debug("KG context supplement failed (non-fatal): %s", e)
        return ""


def build_rag_context(
    docs: list[Document],
    query: str = "",
    kg_supplement: str = "",
    student_profile: str = "",
    max_tokens: int = 0,
) -> str:
    """将检索结果构建为上下文（含全局 token 预算 + 相关性截断）

    策略：
    1. 按 rerank_score 降序排列文档（高相关优先保留）
    2. 精简元数据头（仅来源+路径，不含 rerank_score 等内部标记）
    3. KG 补充插入到首个文档之后（避免末尾被截断丢弃）
    4. student_profile 截断到 500 token
    5. 全局 token 预算控制：超出时从最低相关文档开始丢弃

    Args:
        docs: 检索结果文档列表
        query: 原始查询（仅用于日志）
        kg_supplement: KG 关联知识补充文本
        student_profile: 学生画像摘要
        max_tokens: 全局 token 预算上限（0 = 使用默认 6000）
    """
    if not max_tokens:
        max_tokens = settings.CONTEXT_TOKEN_BUDGET

    try:
        from app.rag.fusion import fuse_documents
        fused = fuse_documents(
            docs,
            query=query,
            kg_supplement=kg_supplement,
            student_profile=student_profile,
            max_tokens=max_tokens,
        )
        return fused.final_context
    except Exception as e:
        if isinstance(e, (TypeError, ValueError, KeyError, AttributeError)):
            logger.error("Evidence fusion logic error, falling back to legacy: %s", e, exc_info=True)
        else:
            logger.warning("Evidence fusion failed, falling back to legacy context builder: %s", e)
        return _build_rag_context_legacy(docs, query, kg_supplement, student_profile, max_tokens)


def _build_rag_context_legacy(
    docs: list[Document],
    query: str,
    kg_supplement: str,
    student_profile: str,
    max_tokens: int,
) -> str:
    """Legacy fallback: token budget truncation without structured fusion"""
    scored_docs = sorted(
        docs,
        key=lambda d: float(d.metadata.get("rerank_score") or d.metadata.get("recall_score") or 0),
        reverse=True,
    )
    doc_entries: list[tuple[float, str]] = []
    for i, doc in enumerate(scored_docs, 1):
        source = doc.metadata.get("source_file") or doc.metadata.get("source") or doc.metadata.get("source_name") or "未知来源"
        section_path = doc.metadata.get("section.path") or doc.metadata.get("heading_path") or ""
        path_info = f" [{section_path}]" if section_path else ""
        header = f"[来源{i}: {source}{path_info}]"
        doc_entries.append((
            float(doc.metadata.get("rerank_score") or doc.metadata.get("recall_score") or 0),
            f"{header}\n{doc.page_content}",
        ))
    kg_tokens = _estimate_tokens(kg_supplement) if kg_supplement else 0
    if student_profile and _estimate_tokens(student_profile) > settings.MAX_STUDENT_PROFILE_TOKENS:
        char_budget = int(len(student_profile) * settings.MAX_STUDENT_PROFILE_TOKENS / max(_estimate_tokens(student_profile), 1))
        student_profile = student_profile[:char_budget] + "..."
    profile_tokens = _estimate_tokens(student_profile) if student_profile else 0
    doc_budget = max(1000, max_tokens - kg_tokens - profile_tokens)
    selected: list[str] = []
    used_tokens = 0
    for _score, text in doc_entries:
        t = _estimate_tokens(text)
        if used_tokens + t <= doc_budget:
            selected.append(text)
            used_tokens += t
        else:
            remaining = doc_budget - used_tokens
            if remaining > 200:
                selected.append(text[:int(len(text) * remaining / max(t, 1))] + "\n[...已截断]")
            break
    parts: list[str] = []
    if selected:
        if kg_supplement and len(selected) >= 1:
            parts.append(selected[0])
            parts.append(kg_supplement)
            parts.extend(selected[1:])
        else:
            parts.extend(selected)
            if kg_supplement:
                parts.append(kg_supplement)
    elif kg_supplement:
        parts.append(kg_supplement)
    if student_profile:
        parts.append(student_profile)
    return "\n\n".join(parts)
