"""检索后处理模块

职责：RRF 合并、同 section 去重、Sentence Window 上下文展开
"""

from __future__ import annotations

import logging

from langchain_core.documents import Document

from app.rag.query_classifier import QueryCategory
from app.rag.rag_utils import (
    estimate_tokens as _estimate_tokens,
    extract_query_terms as _extract_query_terms,
)

logger = logging.getLogger(__name__)

# RRF 常数 k 基准值（RAG 场景每路 5-20 条结果，k=20 平衡排名区分度与多路融合）
_RRF_K_BASE = 20


def _dynamic_rrf_k(route_count: int) -> int:
    """按路由数动态调整 RRF k 值

    路由多时 k 需更大（降低排名区分度，让多路融合更平滑），
    路由少时 k 更小（增强区分度，让 top-1 信号更强）。
    经验值：k ≈ 10 × sqrt(route_count)
    """
    import math
    return max(10, min(60, int(_RRF_K_BASE * math.sqrt(route_count) / math.sqrt(4))))


def _base_route_name(route_name: str) -> str:
    return route_name.rsplit(":", 1)[-1].strip()


def _dedup_key(doc: Document) -> str:
    """Build a dedup key from collection + content_hash for cross-collection dedup."""
    collection = doc.metadata.get("_collection", "")
    content_hash = doc.metadata.get("content_hash")
    if not content_hash:
        import hashlib
        content_hash = hashlib.sha256(doc.page_content[:200].encode()).hexdigest()[:16]
    else:
        content_hash = str(content_hash)
    return f"{collection}::{content_hash}"


# ── RRF 合并 ──────────────────────────────────────────

def merge_route_results(
    route_results: list[tuple[str, list[tuple[Document, float]]]],
    cat: QueryCategory | None = None,
) -> list[tuple[Document, float]]:
    """RRF (Reciprocal Rank Fusion) 合并多路检索结果

    加权 RRF：不同路由按查询类型赋予不同权重。
    公式：score(d) = Σ w(route, cat) / (k + rank_i(d))
    优点：
    - 对异常高分不敏感（排名 1 和 2 的差距是 1/(k+1)-1/(k+2)）
    - 跨路由重复文档自然获得更高分数
    - 精准路由（metadata 过滤）权重高于宽泛路由（semantic）
    """
    from app.rag.recall import get_route_weight
    # 动态 k：路由多时 k 更大，让多路融合更平滑
    k = _dynamic_rrf_k(len(route_results))
    merged: dict[str, tuple[Document, float, set[str], dict[str, float]]] = {}
    raw_count = sum(len(results) for _, results in route_results)

    for route_name, results in route_results:
        w = get_route_weight(_base_route_name(route_name), cat)
        for rank, (doc, original_score) in enumerate(results, 1):
            # 去重 key 加入集合来源，防止跨集合同名文档被误合并
            # 例如 "栈的定义" 在 data_structure 和 computer_organization 都出现
            key = _dedup_key(doc)
            rrf_contribution = w / (k + rank)

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
    logger.debug(
        "RRF k=%d routes=%d raw=%d merged=%d top=%.4f multi=%d",
        k, len(route_results), raw_count, len(ranked),
        ranked[0][1] if ranked else 0,
        sum(1 for _, _, routes, _ in merged.values() if len(routes) >= 2),
    )
    return ranked


# ── 加权 RRF 合并（查询分解用） ──────────────────────────────


def weighted_rrf_merge(
    grouped_results: list[tuple[str, list[tuple[Document, float]]]],
    weights: dict[str, float],
    k: int = 0,
    cat: QueryCategory | None = None,
) -> list[tuple[Document, float]]:
    """加权 RRF 合并：不同来源（原始查询/子查询）可赋予不同权重

    标准 RRF: score(d) = Σ 1/(k + rank_i(d))
    加权 RRF: score(d) = Σ w_source × w_route / (k + rank_i(d))

    w_source: 原始查询 1.5，子查询 1.0，确保原始语境信号更强。
    w_route: 从 recall_routes metadata 提取路由名，按 get_route_weight 加权，
             使分解路径与非分解路径的 RRF 分数分布归一化到同一尺度。
    去重 key 使用 content_hash + collection（与 merge_route_results 一致，避免同前缀误合并）。
    """
    from app.rag.recall import get_route_weight
    # 动态 k：k=0 时按路由数自动计算
    if k <= 0:
        total_routes = sum(len(results) for _, results in grouped_results)
        k = _dynamic_rrf_k(max(1, total_routes // max(1, len(grouped_results))))
    merged: dict[str, tuple[Document, float, set[str]]] = {}
    raw_count = sum(len(results) for _, results in grouped_results)

    for label, results in grouped_results:
        w_source = weights.get(label, 1.0)
        for rank, (doc, _original_score) in enumerate(results, 1):
            # 路由级加权：从 recall_routes metadata 提取路由名
            route_str = doc.metadata.get("recall_routes", "")
            route_names = [r.strip() for r in route_str.split(",") if r.strip()]
            if route_names and cat is not None:
                w_route = max(get_route_weight(_base_route_name(r), cat) for r in route_names)
            else:
                w_route = 1.0
            # 去重 key 用 content_hash + collection，避免同 section 不同 chunk 前100字相同被误合并
            key = _dedup_key(doc)
            rrf_contribution = w_source * w_route / (k + rank)

            existing = merged.get(key)
            if existing is None:
                copied = Document(page_content=doc.page_content, metadata=dict(doc.metadata))
                copied.metadata["_decompose_weight"] = w_source
                merged[key] = (copied, rrf_contribution, {label})
            else:
                doc_obj, prev_score, labels = existing
                merged[key] = (doc_obj, prev_score + rrf_contribution, labels | {label})

    ranked: list[tuple[Document, float]] = []
    for doc, rrf_score, labels in merged.values():
        doc.metadata["recall_score"] = round(rrf_score, 6)
        doc.metadata["_decompose_labels"] = ", ".join(sorted(labels))
        ranked.append((doc, rrf_score))

    ranked.sort(key=lambda item: item[1], reverse=True)
    logger.debug(
        "Weighted RRF k=%d raw=%d merged=%d top=%.4f",
        k, raw_count, len(ranked),
        ranked[0][1] if ranked else 0,
    )
    return ranked


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


# ── Sentence Window 上下文展开 ──────────────────────────


_WINDOW_SIZE = 2            # 命中 chunk 左右各展开的 chunk 数
_WINDOW_TOKEN_BUDGET = 6000  # 每 section token 预算（≈4000 中文字 / 24000 英文词）
_GLOBAL_WINDOW_TOKEN_BUDGET = 12000  # 全局 token 预算上限（多 section 叠加后总量可控）


def _parent_window_expand(docs: list[Document], global_budget: int) -> list[Document]:
    if not docs:
        return docs

    result: list[Document] = list(docs)
    seen_parent_ids: set[str] = set()
    seen_texts: set[str] = {d.page_content for d in docs}
    total_tokens = sum(_estimate_tokens(d.page_content) for d in result)

    for doc in docs:
        parent_text = str(doc.metadata.get("section.parent_text") or "").strip()
        if not parent_text:
            continue

        parent_id = str(
            doc.metadata.get("section.parent_id_index")
            or doc.metadata.get("section.id")
            or ""
        )
        if parent_id and parent_id in seen_parent_ids:
            continue
        if parent_text in seen_texts:
            continue
        if len(parent_text) <= len(doc.page_content.strip()) + 40:
            continue

        parent_tokens = _estimate_tokens(parent_text)
        if total_tokens + parent_tokens > global_budget:
            continue

        parent_meta = dict(doc.metadata)
        parent_meta["_parent_expanded"] = True
        parent_meta["_parent_anchor_chunk_id"] = str(doc.metadata.get("section.chunk_id") or "")
        parent_meta["section.chunk_role"] = "parent_window"
        parent_doc = Document(page_content=parent_text, metadata=parent_meta)
        result.append(parent_doc)
        seen_texts.add(parent_text)
        if parent_id:
            seen_parent_ids.add(parent_id)
        total_tokens += parent_tokens

    if len(result) > len(docs):
        logger.debug("Parent window +%d total=%d tokens≈%d", len(result) - len(docs), len(result), total_tokens)
    return result


def sentence_window_expand(
    docs: list[Document],
    collection_name: str = "data_structure",
    window_size: int = _WINDOW_SIZE,
    budget: int = _WINDOW_TOKEN_BUDGET,
    global_budget: int = _GLOBAL_WINDOW_TOKEN_BUDGET,
) -> list[Document]:
    """Sentence Window: 对命中的 detail chunk 展开上下文窗口

    策略（window_size 控制扩展量）:
    - window_size=0: 不扩展，直接返回原文档
    - window_size>0: 先走 ChromaDB sentence window（主路径，受 window_size 控制），
      再对 sentence window 无法展开的 section 走 parent window 兜底

    执行顺序:
    1. sentence window (primary): 从 ChromaDB 查同 section 相邻 detail chunk，
       以锚点为中心取 window_size 窗口，标记 _window_expanded
    2. parent window (fallback): 对 sentence window 未覆盖的 section，
       用 section.parent_text 补充完整 section 上下文，标记 _parent_expanded

    Args:
        docs: 检索命中的文档列表（已排序）
        collection_name: 向量集合名
        window_size: 左右窗口大小（0=不扩展）
        budget: 每 section token 预算上限
        global_budget: 全局 token 预算上限

    Returns:
        展开后的文档列表（原始命中 + 窗口上下文）
    """
    if not docs or window_size <= 0:
        return docs

    # ── Stage 1: Sentence window expand（主路径，受 window_size 控制）──
    if not collection_name:
        result = list(docs)
    else:
        result = _chroma_window_expand(docs, collection_name, window_size, budget, global_budget)

    # ── Stage 2: Parent window fallback（对 sentence window 未覆盖的 section）──
    # 收集已被 sentence window 展开的 section.id
    sw_expanded_sections: set[str] = set()
    for doc in result:
        if doc.metadata.get("_window_expanded"):
            sid = str(doc.metadata.get("section.id") or "")
            if sid:
                sw_expanded_sections.add(sid)

    # 找出未被 sentence window 覆盖的锚点文档
    needs_parent = [
        doc for doc in docs
        if str(doc.metadata.get("section.id") or "") not in sw_expanded_sections
    ]

    if needs_parent:
        parent_added = _parent_window_expand(needs_parent, global_budget)
        if len(parent_added) > len(needs_parent):
            existing_keys = {
                str(d.metadata.get("section.chunk_id") or d.page_content[:80])
                for d in result
            }
            current_tokens = sum(_estimate_tokens(d.page_content) for d in result)
            for doc in parent_added:
                if doc.metadata.get("_parent_expanded"):
                    key = str(doc.metadata.get("section.chunk_id") or doc.page_content[:80])
                    if key not in existing_keys:
                        doc_tokens = _estimate_tokens(doc.page_content)
                        if current_tokens + doc_tokens <= global_budget:
                            result.append(doc)
                            existing_keys.add(key)
                            current_tokens += doc_tokens

    return result


def _chroma_window_expand(
    docs: list[Document],
    collection_name: str,
    window_size: int = _WINDOW_SIZE,
    budget: int = _WINDOW_TOKEN_BUDGET,
    global_budget: int = _GLOBAL_WINDOW_TOKEN_BUDGET,
) -> list[Document]:
    """ChromaDB Sentence Window 扩展：从向量库查询同 section 相邻 chunk"""
    from app.rag.vectorstore import get_vector_store_manager

    # 按 section.id 分组原始命中
    section_hits: dict[str, Document] = {}
    for doc in docs:
        sec_id = str(doc.metadata.get("section.id") or "")
        if not sec_id:
            continue
        if sec_id not in section_hits:
            section_hits[sec_id] = doc

    if not section_hits:
        return docs

    result: list[Document] = []
    seen_chunk_ids: set[str] = set()
    for doc in docs:
        cid = str(doc.metadata.get("section.chunk_id") or "")
        if cid:
            seen_chunk_ids.add(cid)
        result.append(doc)

    # 批量查询：合并所有 section 为单次 $or 查询，避免 N 次串行调用
    sec_ids = list(section_hits.keys())
    all_section_details: dict[str, list[tuple[int, Document]]] = {sid: [] for sid in sec_ids}
    try:
        raw_collection = get_vector_store_manager().client.get_collection(collection_name)
        for batch_start in range(0, len(sec_ids), 50):
            batch_ids = sec_ids[batch_start:batch_start + 50]
            or_conditions = [
                {"$and": [{"section.id": sid}, {"section.chunk_role": "detail"}]}
                for sid in batch_ids
            ]
            batch_result = raw_collection.get(
                where={"$or": or_conditions} if len(or_conditions) > 1 else or_conditions[0],
                include=["documents", "metadatas"],
            )
            texts = batch_result.get("documents", []) or []
            metas = batch_result.get("metadatas", []) or []
            for text, meta in zip(texts, metas):
                if meta is None:
                    continue
                sid = str(meta.get("section.id", ""))
                idx = meta.get("section.chunk_index")
                if sid in all_section_details and idx is not None and isinstance(idx, int) and idx >= 0:
                    d = Document(page_content=text or "", metadata=dict(meta))
                    all_section_details[sid].append((idx, d))
    except Exception as e:
        logger.warning("Sentence window ChromaDB query failed: %s", e)

    for sec_id, anchor_doc in section_hits.items():
        all_details = all_section_details.get(sec_id, [])
        if not all_details:
            continue
        all_details.sort(key=lambda x: x[0])

        anchor_idx = anchor_doc.metadata.get("section.chunk_index")
        if anchor_idx is None or not isinstance(anchor_idx, int) or anchor_idx < 0:
            anchor_idx = 0

        anchor_pos = 0
        for pos, (idx, _) in enumerate(all_details):
            if idx == anchor_idx:
                anchor_pos = pos
                break

        lo = max(0, anchor_pos - window_size)
        hi = min(len(all_details) - 1, anchor_pos + window_size)

        window_tokens = 0
        for idx, d in all_details[lo:hi + 1]:
            window_tokens += _estimate_tokens(d.page_content)

        while window_tokens > budget and (hi - lo) > 0:
            # Always keep the anchor chunk in the window
            if lo < anchor_pos:
                window_tokens -= _estimate_tokens(all_details[lo][1].page_content)
                lo += 1
            elif hi > anchor_pos:
                window_tokens -= _estimate_tokens(all_details[hi][1].page_content)
                hi -= 1
            else:
                # lo == anchor_pos == hi: only anchor remains, stop trimming
                break

        added = 0
        for idx, d in all_details[lo:hi + 1]:
            chunk_id = str(d.metadata.get("section.chunk_id") or "")
            if chunk_id in seen_chunk_ids:
                continue
            d.metadata["_window_expanded"] = True
            d.metadata["_window_anchor_chunk_id"] = str(anchor_doc.metadata.get("section.chunk_id") or "")
            result.append(d)
            seen_chunk_ids.add(chunk_id)
            added += 1

        if added > 0:
            logger.debug("Window expand +%d sec=%s tokens≈%d", added, sec_id, window_tokens)

    # 全局 token 预算控制：从尾部（低优先级 window chunk）开始裁剪
    total_tokens = sum(_estimate_tokens(d.page_content) for d in result)
    if total_tokens > global_budget:
        while total_tokens > global_budget and len(result) > len(docs):
            removed_doc = result.pop()
            total_tokens -= _estimate_tokens(removed_doc.page_content)
        logger.debug("Window budget trim: %d tokens > %d budget, → %d docs", total_tokens, global_budget, len(result))

    return result


# ── Negative Sampling: Window 噪声软降级 ──────────────────

_NOISE_MIN_COVERAGE = 0.15   # chunk 中至少 15% 的 query 关键词被命中才视为相关
_NOISE_PENALTY_FACTOR = 0.5  # fusion 评分惩罚系数（越低排越后）


def downgrade_window_noise(
    docs: list[Document],
    query: str,
    *,
    is_comparison: bool = False,
    min_coverage: float = _NOISE_MIN_COVERAGE,
) -> list[Document]:
    """对 sentence_window_expand 展开的噪声 chunk 做软降级标记。

    策略 1: 只过滤 window 展开的 chunk（原始检索结果保留）
    策略 3: 不删除，只标记 _noise_downgraded=True + 降权系数，
            fusion.py 排序时将其排到末尾，保证 Recall 不丢。

    对比查询豁免：is_comparison=True 时跳过降级，
    因为对比查询需要两侧 context，误删任一侧都会丢失关键信息。

    Args:
        docs: sentence_window_expand 后的文档列表
        query: 原始查询
        is_comparison: 是否为对比查询（豁免降级）
        min_coverage: 关键词覆盖率阈值（低于此值视为噪声）

    Returns:
        标记了 _noise_downgrade_factor 的文档列表（顺序不变）
    """
    if not docs or not query or is_comparison:
        return docs

    terms = _extract_query_terms(query)
    if not terms:
        return docs

    # 构建小写关键词集合
    term_set = {t.lower() for t in terms if len(t) >= 2}
    if not term_set:
        return docs

    downgraded = 0
    for doc in docs:
        # 只处理 window 展开的 chunk（策略 1: 原始检索结果保留）
        if not doc.metadata.get("_window_expanded") and not doc.metadata.get("_parent_expanded"):
            continue

        content_lower = doc.page_content.lower()

        # 计算关键词覆盖率
        hit = sum(1 for t in term_set if t in content_lower)
        coverage = hit / len(term_set) if term_set else 0.0

        if coverage < min_coverage:
            doc.metadata["_noise_downgraded"] = True
            doc.metadata["_noise_downgrade_factor"] = _NOISE_PENALTY_FACTOR
            doc.metadata["_noise_coverage"] = round(coverage, 3)
            downgraded += 1
        else:
            # 相关的 window chunk，保留并标记覆盖率供诊断
            doc.metadata["_noise_coverage"] = round(coverage, 3)

    if downgraded > 0:
        logger.debug(
            "Window noise downgrade: query='%s' terms=%s downgraded=%d/%d threshold=%.2f",
            query[:40], term_set, downgraded,
            sum(1 for d in docs if d.metadata.get("_window_expanded") or d.metadata.get("_parent_expanded")),
            min_coverage,
        )

    return docs
