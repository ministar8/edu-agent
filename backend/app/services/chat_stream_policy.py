from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def is_simple_knowledge_candidate(route: str, category, strategy) -> bool:
    if route != "knowledge_agent":
        return False
    if strategy.layer not in {"L1", "L2"}:
        return False
    if (
        category.is_code
        or category.is_exercise
        or category.is_answer
        or category.is_comparison
        or category.is_learning_path
    ):
        return False
    if strategy.layer == "L2" and (category.is_long or not category.is_concept):
        return False
    return True


def should_fast_stream_simple_knowledge(query: str) -> bool:
    try:
        from app.agents.supervisor import _rule_based_route
        from app.rag.query_classifier import classify_query
        from app.rag.rag_utils import extract_query_terms, normalize_query_text
        from app.rag.retrieval_strategy import resolve_retrieval_strategy

        normalized = normalize_query_text(query)
        terms = extract_query_terms(normalized)
        category = classify_query(query, terms)
        strategy = resolve_retrieval_strategy(category)
        return is_simple_knowledge_candidate(_rule_based_route(query), category, strategy)
    except Exception as exc:
        logger.debug("Fast-stream eligibility check skipped: %s", exc)
        return False
