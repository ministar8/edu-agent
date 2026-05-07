"""检索后处理模块

职责：RRF 合并、同 section 去重、层级上下文展开、连续补齐
"""

from __future__ import annotations

import logging

from langchain_core.documents import Document

logger = logging.getLogger(__name__)

# RRF 常数 k
_RRF_K = 60

# 层级展开字符预算
_EXPAND_MAX_CHARS = 3000


# ── RRF 合并 ──────────────────────────────────────────

def merge_route_results(
    route_results: list[tuple[str, list[tuple[Document, float]]]],
) -> list[tuple[Document, float]]:
    """RRF (Reciprocal Rank Fusion) 合并多路检索结果

    各路由结果按排名贡献 1/(k+rank) 分数，同一文档跨路由累加。
    优点：
    - 对异常高分不敏感（排名 1 和 2 的差距是 1/(k+1)-1/(k+2)）
    - 跨路由重复文档自然获得更高分数
    """
    merged: dict[str, tuple[Document, float, set[str], dict[str, float]]] = {}
    raw_count = sum(len(results) for _, results in route_results)

    for route_name, results in route_results:
        for rank, (doc, original_score) in enumerate(results, 1):
            key = str(doc.metadata.get("content_hash") or f"{doc.metadata.get('source_file', '')}:{doc.page_content}")
            rrf_contribution = 1.0 / (_RRF_K + rank)

            existing = merged.get(key)
            if existing is None:
                copied = Document(page_content=doc.page_content, metadata=dict(doc.metadata))
                merged[key] = (copied, rrf_contribution, {route_name}, {route_name: original_score})
            else:
                doc_obj, prev_score, routes, route_scores = existing
                merged[key] = (doc_obj, prev_score + rrf_contribution, routes | {route_name}, {**route_scores, route_name: original_score})

    ranked: list[tuple[Document, float]] = []
    for doc, rrf_score, routes, route_scores in merged.values():
        doc.metadata["recall_score"] = round(rrf_score, 6)
        doc.metadata["recall_routes"] = ", ".join(sorted(routes))
        doc.metadata["recall_route_count"] = len(routes)
        for rn, rs in route_scores.items():
            doc.metadata[f"recall_{rn}_score"] = round(float(rs), 6)
        ranked.append((doc, rrf_score))

    ranked.sort(key=lambda item: item[1], reverse=True)
    logger.info(
        "RRF merge k=%d raw_hits=%d merged_hits=%d top_scores=%s multi_route=%d",
        _RRF_K,
        raw_count,
        len(ranked),
        [round(score, 6) for _, score in ranked[:5]],
        sum(1 for _, _, routes, _ in merged.values() if len(routes) >= 2),
    )
    return ranked


# ── 同 section 去重 ────────────────────────────────────

def dedup_same_section(
    results: list[tuple[Document, float]],
    max_per_section: int = 2,
) -> list[tuple[Document, float]]:
    """同 section 去重：避免 QA/Detail/Summary 同 section 多个 chunk 全部送给 LLM

    策略：
    1. 按 section.id 分组
    2. 同 section 内按角色优先级选最佳 chunk：qa > detail > summary
    3. 同角色多 chunk 保留得分最高的
    4. 每个 section 最多保留 max_per_section 个 chunk
    5. 跨 section 保留全局排序
    """
    _ROLE_PRIORITY = {"qa": 0, "detail": 1, "summary": 2}

    section_groups: dict[str, list[tuple[Document, float]]] = {}
    for doc, score in results:
        sec_id = str(doc.metadata.get("section.id") or "")
        if not sec_id:
            section_groups.setdefault("__no_section__", []).append((doc, score))
            continue
        section_groups.setdefault(sec_id, []).append((doc, score))

    deduped: list[tuple[Document, float]] = []
    for sec_id, group in section_groups.items():
        if sec_id == "__no_section__" or len(group) <= max_per_section:
            deduped.extend(group)
            continue

        def _sort_key(item: tuple[Document, float]) -> tuple:
            doc, score = item
            role = str(doc.metadata.get("section.chunk_role") or "detail")
            priority = _ROLE_PRIORITY.get(role, 3)
            return (priority, -score)

        sorted_group = sorted(group, key=_sort_key)

        seen_roles: set[str] = set()
        selected: list[tuple[Document, float]] = []
        for doc, score in sorted_group:
            if len(selected) >= max_per_section:
                break
            role = str(doc.metadata.get("section.chunk_role") or "detail")
            if role in seen_roles:
                continue
            seen_roles.add(role)
            selected.append((doc, score))

        # 如果角色去重后不足 max_per_section，补充剩余最高分
        if len(selected) < max_per_section:
            remaining = [(doc, score) for doc, score in sorted_group
                         if not any(doc is s_doc for s_doc, _ in selected)]
            selected.extend(remaining[:max_per_section - len(selected)])

        deduped.extend(selected)

    deduped.sort(key=lambda item: item[1], reverse=True)

    removed = len(results) - len(deduped)
    if removed > 0:
        logger.info("Section dedup removed=%d before=%d after=%d", removed, len(results), len(deduped))
    return deduped


# ── 层级上下文展开 ────────────────────────────────────

def expand_hierarchical_context(
    docs: list[Document],
    collection_name: str = "data_structure",
    max_expand: int = 3,
) -> list[Document]:
    """层级上下文展开：QA/Summary 命中时，全量展开同 section 的 detail chunk

    核心原则：**连续优先，预算控制**

    策略：
    1. 全量查询该 section 所有 detail chunk
    2. 按 chunk_index 排序（保证原文顺序）
    3. 滑动窗口选择：以命中 chunk 为锚点，向前后扩展
       构建最长的连续窗口，总字符数 ≤ _EXPAND_MAX_CHARS
    4. 如果原始结果中已有同 section 的 detail chunk，合并后统一处理
    """
    if not docs:
        return docs

    expanded: list[Document] = []
    seen_chunk_ids: set[str] = set()
    for doc in docs:
        cid = str(doc.metadata.get("section.chunk_id") or "")
        if cid:
            seen_chunk_ids.add(cid)

    from app.rag.vectorstore import get_vector_store_manager
    store = get_vector_store_manager().get_store(collection_name)

    for doc in docs:
        expanded.append(doc)
        role = str(doc.metadata.get("section.chunk_role") or "detail")

        if role not in ("qa", "summary"):
            continue

        sec_id = str(doc.metadata.get("section.id") or "")
        if not sec_id:
            continue

        try:
            detail_results = store.similarity_search_with_score(
                "",
                k=50,
                filter={
                    "$and": [
                        {"section.id": sec_id},
                        {"section.chunk_role": "detail"},
                    ]
                },
            )
        except Exception:
            continue

        all_details: list[tuple[int, Document]] = []
        for detail_doc, _ in detail_results:
            idx = detail_doc.metadata.get("section.chunk_index")
            if idx is not None and isinstance(idx, int) and idx >= 0:
                all_details.append((idx, detail_doc))
        all_details.sort(key=lambda x: x[0])

        if not all_details:
            continue

        existing_indices: set[int] = set()
        for d in docs:
            if (str(d.metadata.get("section.id") or "") == sec_id
                    and str(d.metadata.get("section.chunk_role") or "detail") == "detail"):
                idx = d.metadata.get("section.chunk_index")
                if idx is not None and isinstance(idx, int) and idx >= 0:
                    existing_indices.add(idx)

        anchor_indices = sorted(existing_indices) if existing_indices else [0]

        detail_chars = {idx: len(d.page_content) for idx, d in all_details}
        idx_to_doc = {idx: d for idx, d in all_details}
        all_indices = [idx for idx, _ in all_details]

        best_window: list[int] = []
        for anchor in anchor_indices:
            if anchor not in idx_to_doc:
                continue
            window = _build_contiguous_window(anchor, all_indices, detail_chars, _EXPAND_MAX_CHARS)
            if len(window) > len(best_window):
                best_window = window

        if not best_window and all_indices:
            best_window = _build_contiguous_window(all_indices[0], all_indices, detail_chars, _EXPAND_MAX_CHARS)

        added = 0
        for idx in best_window:
            detail_doc = idx_to_doc[idx]
            detail_cid = str(detail_doc.metadata.get("section.chunk_id") or "")
            if detail_cid in seen_chunk_ids:
                continue
            detail_doc.metadata["_expanded_from"] = str(doc.metadata.get("section.chunk_id") or "")
            expanded.append(detail_doc)
            seen_chunk_ids.add(detail_cid)
            added += 1

        if added > 0:
            logger.info(
                "Hierarchical expand sec=%s added=%d window=%s total_chars=%d",
                sec_id, added, best_window,
                sum(detail_chars.get(i, 0) for i in best_window),
            )

    if len(expanded) > len(docs):
        logger.info("Hierarchical expand total: before=%d after=%d", len(docs), len(expanded))
    return expanded


def _build_contiguous_window(
    anchor: int,
    all_indices: list[int],
    char_lengths: dict[int, int],
    budget: int,
) -> list[int]:
    """从锚点出发，贪心构建连续窗口，字符预算内最大化覆盖"""
    if anchor not in char_lengths:
        return []

    used = char_lengths[anchor]
    lo = anchor
    hi = anchor

    try:
        anchor_pos = all_indices.index(anchor)
    except ValueError:
        return [anchor]

    left_pos = anchor_pos - 1
    right_pos = anchor_pos + 1

    while left_pos >= 0 or right_pos < len(all_indices):
        if right_pos < len(all_indices):
            next_idx = all_indices[right_pos]
            cost = char_lengths.get(next_idx, 0)
            if used + cost <= budget:
                hi = next_idx
                used += cost
                right_pos += 1
            else:
                right_pos = len(all_indices)

        if left_pos >= 0:
            prev_idx = all_indices[left_pos]
            cost = char_lengths.get(prev_idx, 0)
            if used + cost <= budget:
                lo = prev_idx
                used += cost
                left_pos -= 1
            else:
                left_pos = -1

        if right_pos >= len(all_indices) and left_pos < 0:
            break
        if left_pos < 0 and right_pos >= len(all_indices):
            break

    return [i for i in all_indices if lo <= i <= hi]


# ── 连续补齐 ──────────────────────────────────────────

def contiguous_fill(
    docs: list[Document],
    collection_name: str = "data_structure",
    max_gap_fill: int = 5,
) -> list[Document]:
    """滑动窗口拼接：补充同 section 内 detail chunk 之间的空缺，保证文本连续

    问题：命中 Detail_5 和 Detail_8，中间缺 Detail_6、Detail_7
          → LLM 看到断章取义的内容

    策略：
    1. 按 section.id 分组，仅处理 detail 角色
    2. 按 section.chunk_index 排序，检测缺口
    3. 从向量库按 section.id + chunk_role="detail" 查询全量 detail
    4. 填补缺口中的 chunk，标记 _filled_gap=True
    5. 非 detail chunk（QA/Summary）保持原位不动
    6. 最终按 section.id 分组输出：每组内 detail 连续，非 detail 插回原位
    """
    if not docs:
        return docs

    detail_map: dict[str, dict[int, Document]] = {}
    non_detail: list[tuple[int, Document]] = []

    for i, doc in enumerate(docs):
        role = str(doc.metadata.get("section.chunk_role") or "detail")
        sec_id = str(doc.metadata.get("section.id") or "")
        chunk_idx = doc.metadata.get("section.chunk_index")

        if role == "detail" and sec_id and chunk_idx is not None and isinstance(chunk_idx, int) and chunk_idx >= 0:
            detail_map.setdefault(sec_id, {})[chunk_idx] = doc
        else:
            non_detail.append((i, doc))

    gaps_to_fill: dict[str, list[int]] = {}

    for sec_id, idx_map in detail_map.items():
        indices = sorted(idx_map.keys())
        if len(indices) < 2:
            continue
        for j in range(len(indices) - 1):
            for missing in range(indices[j] + 1, indices[j + 1]):
                gaps_to_fill.setdefault(sec_id, []).append(missing)

    if not gaps_to_fill:
        return docs

    total_gaps = sum(len(v) for v in gaps_to_fill.values())
    if total_gaps > max_gap_fill:
        sorted_sections = sorted(
            gaps_to_fill.keys(),
            key=lambda s: len(detail_map.get(s, {})),
            reverse=True,
        )
        capped_gaps: dict[str, list[int]] = {}
        remaining = max_gap_fill
        for sec_id in sorted_sections:
            if remaining <= 0:
                break
            take = min(len(gaps_to_fill[sec_id]), remaining)
            capped_gaps[sec_id] = gaps_to_fill[sec_id][:take]
            remaining -= take
        gaps_to_fill = capped_gaps

    from app.rag.vectorstore import get_vector_store_manager
    store = get_vector_store_manager().get_store(collection_name)
    filled: dict[str, dict[int, Document]] = {}

    for sec_id, missing_indices in gaps_to_fill.items():
        try:
            section_details = store.similarity_search_with_score(
                "",
                k=50,
                filter={
                    "$and": [
                        {"section.id": sec_id},
                        {"section.chunk_role": "detail"},
                    ]
                },
            )
        except Exception:
            continue

        for detail_doc, _ in section_details:
            doc_idx = detail_doc.metadata.get("section.chunk_index")
            if doc_idx is not None and isinstance(doc_idx, int) and doc_idx in missing_indices:
                doc_cid = str(detail_doc.metadata.get("section.chunk_id") or "")
                already_present = any(
                    str(d.metadata.get("section.chunk_id") or "") == doc_cid
                    for d in docs
                )
                if not already_present:
                    detail_doc.metadata["_filled_gap"] = True
                    filled.setdefault(sec_id, {})[doc_idx] = detail_doc

    # 重组结果列表
    section_ordered: dict[str, list[Document]] = {}
    for sec_id in detail_map:
        merged = {**detail_map[sec_id], **filled.get(sec_id, {})}
        for idx in sorted(merged.keys()):
            section_ordered.setdefault(sec_id, []).append(merged[idx])

    section_first_pos: dict[str, int] = {}
    for i, doc in enumerate(docs):
        sec_id = str(doc.metadata.get("section.id") or "")
        if sec_id and sec_id not in section_first_pos:
            section_first_pos[sec_id] = i

    result: list[Document] = []
    placed_sections: set[str] = set()

    all_items: list[tuple[int, str, Document | None]] = []

    for sec_id, ordered_docs in section_ordered.items():
        pos = section_first_pos.get(sec_id, 0)
        all_items.append((pos, "section", ordered_docs))

    for pos, doc in non_detail:
        all_items.append((pos, "non_section", doc))

    all_items.sort(key=lambda x: x[0])

    for pos, item_type, item_data in all_items:
        if item_type == "section":
            sec_id = str(item_data[0].metadata.get("section.id") or "") if item_data else ""
            if sec_id not in placed_sections:
                result.extend(item_data)
                placed_sections.add(sec_id)
        else:
            result.append(item_data)

    filled_count = sum(len(v) for v in filled.values())
    if filled_count > 0:
        logger.info(
            "Contiguous fill added=%d gaps=%d before=%d after=%d",
            filled_count, total_gaps, len(docs), len(result),
        )
    return result
