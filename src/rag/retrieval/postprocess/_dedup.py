"""自动拆分自 postprocess.py（行为等价）。"""

from __future__ import annotations

from langchain_core.documents import Document

from rag.retrieval.postprocess._log import logger

# ── 同 section 去重 ────────────────────────────────────


def dedup_same_section(
    results: list[tuple[Document, float]],
    max_per_section: int = 3,
) -> list[tuple[Document, float]]:
    """同 section 去重：所有 chunk 均为 detail 角色，按分数取 Top-N

    改造后所有 chunk 同为 detail 角色，无需角色优先级逻辑，
    简化为基础的分组 + 高分选取。
    """
    section_groups: dict[str, list[tuple[Document, float]]] = {}
    for doc, score in results:
        sec_id = str(doc.metadata.get("section.id") or "")
        if not sec_id:
            sec_id = "__no_section__"
        section_groups.setdefault(sec_id, []).append((doc, score))

    deduped: list[tuple[Document, float]] = []
    for sec_id, group in section_groups.items():
        if sec_id == "__no_section__" or len(group) <= max_per_section:
            deduped.extend(group)
            continue
        sorted_group = sorted(group, key=lambda x: x[1], reverse=True)
        deduped.extend(sorted_group[:max_per_section])

    deduped.sort(key=lambda x: x[1], reverse=True)

    removed = len(results) - len(deduped)
    if removed > 0:
        logger.debug("Section dedup -%d %d→%d", removed, len(results), len(deduped))
    return deduped
