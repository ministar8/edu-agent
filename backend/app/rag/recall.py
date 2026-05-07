"""多路召回构建模块

职责：查询归一化、同义词扩展、关键词提取、召回路由构建、元数据路由、集合路由

由 retriever.py 调用，不直接暴露给外部。
"""

from __future__ import annotations

import logging
import re

from app.rag.query_classifier import classify_query, QueryCategory
from app.rag.synonyms import expand_query_with_synonyms

logger = logging.getLogger(__name__)

_MAX_QUERY_TERMS = 6
_QUERY_STOP_WORDS = frozenset({
    "什么", "怎么", "如何", "为什么", "请问", "一下", "一下子", "有关", "关于", "这个", "那个",
    "哪些", "是否", "可以", "一下吧", "帮我", "讲解", "解释", "说明", "作用", "使用", "方法",
})


def normalize_query_text(query: str) -> str:
    return re.sub(r"\s+", " ", str(query).strip())


def extract_query_terms(query: str, max_terms: int = _MAX_QUERY_TERMS) -> list[str]:
    normalized = normalize_query_text(query)
    if not normalized:
        return []

    candidates = re.findall(r"[A-Za-z_][A-Za-z0-9_\.]{1,}|[\u4e00-\u9fff]{2,12}", normalized)
    terms: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        term = candidate.strip()
        if not term or term.lower() in _QUERY_STOP_WORDS or term in _QUERY_STOP_WORDS:
            continue
        lowered = term.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        terms.append(term)
        if len(terms) >= max_terms:
            break
    return terms


def _kg_expand_terms(query: str, max_terms: int = 4) -> str:
    """从知识图谱获取关联知识点名称，构建扩展召回查询

    防泛化约束：
    - 最多取 max_terms 个关联节点名
    - 仅取与 query 直接相邻的节点（1跳），不做深度遍历
    - KG 查询失败时静默降级
    """
    try:
        from app.rag.knowledge_graph import get_kg_manager
        kg_manager = get_kg_manager()
        resolved = kg_manager.resolve_topic(query)
        if not resolved:
            return ""
        related_names: list[str] = []
        prerequisites = kg_manager.get_prerequisites(resolved)
        for p in prerequisites:
            name = p.get("name", "")
            if name and name not in related_names:
                related_names.append(name)
        next_topics = kg_manager.get_next_topics(resolved)
        for n in next_topics:
            name = n.get("name", "")
            if name and name not in related_names:
                related_names.append(name)
        if not related_names:
            return ""
        related_names = related_names[:max_terms]
        return " ".join(related_names)
    except Exception as e:
        logger.debug("KG expand failed (non-fatal): %s", e)
        return ""


def combine_filters(base_filter: dict | None, extra_filter: dict | None) -> dict | None:
    if not base_filter:
        return extra_filter
    if not extra_filter:
        return base_filter
    return {"$and": [base_filter, extra_filter]}


def build_recall_queries(query: str) -> list[tuple[str, str]]:
    """构建多路召回查询

    路由策略：
    - semantic: 完整 query 走向量语义检索
    - keyword_bm25: 关键词走 BM25 全文检索
    - focus: 核心关键词走向量检索（短词组语义聚焦）
    - expanded: 同义词扩展 query 走向量检索
    - kg_expand: 知识图谱关联扩展
    """
    normalized = normalize_query_text(query)
    routes: list[tuple[str, str]] = []
    if normalized:
        routes.append(("semantic", normalized))

    keyword_terms = extract_query_terms(normalized)
    if keyword_terms:
        routes.append(("keyword_bm25", " ".join(keyword_terms)))
    if len(keyword_terms) >= 2:
        routes.append(("focus", " ".join(keyword_terms[:2])))

    expanded = expand_query_with_synonyms(normalized)
    if expanded != normalized:
        routes.append(("expanded", expanded))

    kg_terms = _kg_expand_terms(normalized)
    if kg_terms:
        routes.append(("kg_expand", kg_terms))

    deduped: list[tuple[str, str]] = []
    seen_queries: set[str] = set()
    for route_name, route_query in routes:
        route_key = route_query.lower()
        if not route_query or route_key in seen_queries:
            continue
        seen_queries.add(route_key)
        deduped.append((route_name, route_query))
    return deduped


def build_metadata_routes(
    query: str,
    base_filter: dict | None = None,
    cat: QueryCategory | None = None,
) -> list[tuple[str, str, dict | None]]:
    normalized = normalize_query_text(query)
    terms = extract_query_terms(normalized)
    focus_query = " ".join(terms[:2]) if len(terms) >= 2 else (terms[0] if terms else normalized)
    metadata_routes: list[tuple[str, str, dict | None]] = []

    if cat is None:
        cat = classify_query(query, terms)

    if cat.is_code:
        metadata_routes.append(
            ("code_meta", focus_query, combine_filters(base_filter, {"content_type": "code_mixed"}))
        )
        metadata_routes.append(
            ("code_source_meta", focus_query, combine_filters(base_filter, {"source_type": "md"}))
        )

    if cat.is_exercise:
        metadata_routes.append(
            ("exercise_meta", normalized, combine_filters(base_filter, {"content_type": "exercise"}))
        )

    if cat.is_answer:
        metadata_routes.append(
            ("answer_meta", normalized, combine_filters(base_filter, {"content_type": "answer"}))
        )

    if cat.is_structured:
        metadata_routes.append(
            ("structured_meta", focus_query, combine_filters(base_filter, {"is_structured": True}))
        )
        metadata_routes.append(
            ("structured_source_meta", focus_query, combine_filters(base_filter, {"source_type": "md"}))
        )

    if cat.is_concept:
        metadata_routes.append(
            ("concept_meta", focus_query, combine_filters(base_filter, {"content_type": "section"}))
        )

    if cat.is_comparison:
        metadata_routes.append(
            ("comparison_meta", focus_query, combine_filters(base_filter, {"content_type": "section"}))
        )

    if terms and not cat.is_exercise and not cat.is_answer:
        metadata_routes.append(
            ("section_meta", focus_query, combine_filters(base_filter, {"content_type": "section"}))
        )

    deduped: list[tuple[str, str, dict | None]] = []
    seen_specs: set[str] = set()
    for route_name, route_query, route_filter in metadata_routes:
        filter_key = str(route_filter)
        spec_key = f"{route_query.lower()}::{filter_key}"
        if not route_query or spec_key in seen_specs:
            continue
        seen_specs.add(spec_key)
        deduped.append((route_name, route_query, route_filter))
    return deduped


SUBJECT_COLLECTIONS = ["data_structure", "computer_organization", "operating_system", "computer_network"]


def resolve_collection_routes(query: str, collection_name: str,
                             cat: QueryCategory | None = None) -> list[str]:
    if collection_name:
        return [collection_name]

    # 默认：搜索所有学科集合 + 辅助集合
    normalized = normalize_query_text(query)
    terms = extract_query_terms(normalized)
    if cat is None:
        cat = classify_query(query, terms)
    collections = list(SUBJECT_COLLECTIONS)

    if cat.is_answer:
        collections.append("answers")
    if cat.is_exercise:
        collections.append("questions")
    if cat.is_structured and any(marker in normalized for marker in ("路径", "路线", "怎么学", "学习计划", "学习路径")):
        collections.append("learning_paths")
    if cat.is_code:
        collections.append("answers")

    deduped: list[str] = []
    seen: set[str] = set()
    for name in collections:
        if name in seen:
            continue
        seen.add(name)
        deduped.append(name)
    return deduped
