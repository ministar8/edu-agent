"""自动拆分自 postprocess.py（行为等价）。"""

from __future__ import annotations

from langchain_core.documents import Document

from rag.common.rag_utils import estimate_tokens as _estimate_tokens
from rag.common.rag_utils import extract_query_terms as _extract_query_terms
from rag.retrieval.postprocess._log import logger

# ── Sentence Window 上下文展开 ──────────────────────────


_WINDOW_SIZE = 2  # 命中 chunk 左右各展开的 chunk 数
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
            doc.metadata.get("section.parent_id_index") or doc.metadata.get("section.id") or ""
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
        logger.debug(
            "Parent window +%d total=%d tokens≈%d",
            len(result) - len(docs),
            len(result),
            total_tokens,
        )
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
        doc for doc in docs if str(doc.metadata.get("section.id") or "") not in sw_expanded_sections
    ]

    if needs_parent:
        parent_added = _parent_window_expand(needs_parent, global_budget)
        if len(parent_added) > len(needs_parent):
            existing_keys = {
                str(d.metadata.get("section.chunk_id") or d.page_content[:80]) for d in result
            }
            current_tokens = sum(_estimate_tokens(d.page_content) for d in result)
            for doc in parent_added:
                if doc.metadata.get("_parent_expanded"):
                    # 去重键必须**区分父文档与它的锚点**。
                    # 父文档的 metadata 是从锚点复制来的，因此它带着**锚点的
                    # `section.chunk_id`**。若直接用 chunk_id 做键，父文档必然与锚点撞键
                    # 而被永远挡掉 —— 实测确认这就是原本的行为：**只要锚点有 chunk_id
                    # （生产环境的正常情况），父窗口兜底就从未真正生效过**，
                    # 只有锚点恰好没有 chunk_id 时才会被加进去。
                    key = "parent:" + str(
                        doc.metadata.get("_parent_anchor_chunk_id") or doc.page_content[:80]
                    )
                    if key not in existing_keys:
                        doc_tokens = _estimate_tokens(doc.page_content)
                        if current_tokens + doc_tokens <= global_budget:
                            result.append(doc)
                            existing_keys.add(key)
                            current_tokens += doc_tokens

    return result


def _group_hits_by_section(docs: list[Document]) -> dict[str, Document]:
    """按 `section.id` 分组，每 section 取**首个**命中 chunk 作锚点（无 section.id 的丢弃）。"""
    hits: dict[str, Document] = {}
    for doc in docs:
        sec_id = str(doc.metadata.get("section.id") or "")
        if sec_id and sec_id not in hits:
            hits[sec_id] = doc
    return hits


def _fetch_section_details(
    collection_name: str, sec_ids: list[str]
) -> dict[str, list[tuple[int, Document]]]:
    """批量取各 section 的 detail chunk（每 50 个 section 一次 `$or` 查询，避免 N 次串行）。

    返回 ``{section_id: [(chunk_index, Document), ...]}``；查询失败时返回全空表（不抛）。
    """
    from rag.common.vectorstore import get_vector_store_manager

    details: dict[str, list[tuple[int, Document]]] = {sid: [] for sid in sec_ids}
    try:
        raw_collection = get_vector_store_manager().client.get_collection(collection_name)
        for batch_start in range(0, len(sec_ids), 50):
            batch_ids = sec_ids[batch_start : batch_start + 50]
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
                if sid in details and isinstance(idx, int) and idx >= 0:
                    d = Document(page_content=text or "", metadata=dict(meta))
                    details[sid].append((idx, d))
    except Exception as e:
        logger.warning("Sentence window ChromaDB query failed: %s", e)
    return details


def _window_bounds(
    all_details: list[tuple[int, Document]],
    anchor_idx: int,
    window_size: int,
    budget: int,
) -> tuple[int, int, int]:
    """锚点左右各 window_size 的 `[lo, hi]`，再按 token 预算从两端裁到 ≤ budget。

    **锚点始终保留**。返回 ``(lo, hi, 裁剪后窗口的 token 数)``。

    ★ 锚点定位用一个 `next(...)` 生成器（等价于原「for + if + break」循环，少了 2 个判定点，
    backlog #36 第三步）；找不到（理论上不会）时退回 0。
    """
    anchor_pos = next((pos for pos, (idx, _d) in enumerate(all_details) if idx == anchor_idx), 0)
    lo = max(0, anchor_pos - window_size)
    hi = min(len(all_details) - 1, anchor_pos + window_size)
    window_tokens = sum(_estimate_tokens(all_details[i][1].page_content) for i in range(lo, hi + 1))
    while window_tokens > budget and (hi - lo) > 0:
        if lo < anchor_pos:
            window_tokens -= _estimate_tokens(all_details[lo][1].page_content)
            lo += 1
        elif hi > anchor_pos:
            window_tokens -= _estimate_tokens(all_details[hi][1].page_content)
            hi -= 1
        else:
            break  # lo == anchor_pos == hi：只剩锚点，停止裁剪
    return lo, hi, window_tokens


def _append_window_chunks(
    result: list[Document],
    seen_chunk_ids: set[str],
    all_details: list[tuple[int, Document]],
    lo: int,
    hi: int,
    anchor_doc: Document,
) -> int:
    """把窗口内**尚未出现过**的 chunk 追加进 result（标 `_window_expanded`），返回新增数。"""
    added = 0
    for _idx, d in all_details[lo : hi + 1]:
        chunk_id = str(d.metadata.get("section.chunk_id") or "")
        if chunk_id in seen_chunk_ids:
            continue
        d.metadata["_window_expanded"] = True
        d.metadata["_window_anchor_chunk_id"] = str(
            anchor_doc.metadata.get("section.chunk_id") or ""
        )
        result.append(d)
        seen_chunk_ids.add(chunk_id)
        added += 1
    return added


def _trim_global_budget(result: list[Document], base_len: int, global_budget: int) -> None:
    """全局 token 超预算时，从尾部（低优先级 window chunk）裁到 ≤ 预算。

    `base_len` = 原始命中数 —— 保证不裁掉原始证据本身（`len(result) > base_len`）。
    """
    total_tokens = sum(_estimate_tokens(d.page_content) for d in result)
    if total_tokens <= global_budget:
        return
    while total_tokens > global_budget and len(result) > base_len:
        total_tokens -= _estimate_tokens(result.pop().page_content)
    logger.debug(
        "Window budget trim: %d tokens > %d budget, → %d docs",
        total_tokens,
        global_budget,
        len(result),
    )


def _chroma_window_expand(
    docs: list[Document],
    collection_name: str,
    window_size: int = _WINDOW_SIZE,
    budget: int = _WINDOW_TOKEN_BUDGET,
    global_budget: int = _GLOBAL_WINDOW_TOKEN_BUDGET,
) -> list[Document]:
    """ChromaDB Sentence Window 扩展：从向量库查询同 section 相邻 chunk"""
    section_hits = _group_hits_by_section(docs)
    if not section_hits:
        return docs

    result = list(docs)
    seen_chunk_ids = {str(d.metadata.get("section.chunk_id") or "") for d in docs} - {""}

    all_section_details = _fetch_section_details(collection_name, list(section_hits.keys()))

    for sec_id, anchor_doc in section_hits.items():
        all_details = all_section_details.get(sec_id, [])
        if not all_details:
            continue
        all_details.sort(key=lambda x: x[0])

        anchor_idx = anchor_doc.metadata.get("section.chunk_index")
        if not isinstance(anchor_idx, int) or anchor_idx < 0:
            anchor_idx = 0

        lo, hi, window_tokens = _window_bounds(all_details, anchor_idx, window_size, budget)
        added = _append_window_chunks(result, seen_chunk_ids, all_details, lo, hi, anchor_doc)
        if added > 0:
            logger.debug("Window expand +%d sec=%s tokens≈%d", added, sec_id, window_tokens)

    _trim_global_budget(result, len(docs), global_budget)
    return result


# ── Negative Sampling: Window 噪声软降级 ──────────────────

_NOISE_MIN_COVERAGE = 0.15  # chunk 中至少 15% 的 query 关键词被命中才视为相关
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
            query[:40],
            term_set,
            downgraded,
            sum(
                1
                for d in docs
                if d.metadata.get("_window_expanded") or d.metadata.get("_parent_expanded")
            ),
            min_coverage,
        )

    return docs


def merge_window_into_anchors(docs: list[Document]) -> list[Document]:
    """把窗口扩展 chunk 的内容合并回其锚点，窗口 chunk 本身不再作为独立证据返回。

    背景：`sentence_window_expand` 会把同 section 相邻 chunk 以 score=0 的独立条目
    追加到结果尾部。这些「窗口 chunk」未经 rerank、collection 为空，混入最终证据
    列表会被 RAGAS 当作独立 top-k context 计分，稀释 context_precision。

    处理规则：
    - 被 `downgrade_window_noise` 判为噪声的窗口 chunk（_noise_downgraded=True）直接丢弃；
    - 其余窗口 chunk 的内容追加到其锚点 chunk 的 page_content 末尾（锚点由
      _window_anchor_chunk_id / _parent_anchor_chunk_id 指向），窗口 chunk 本身移除；
    - 找不到锚点（锚点已在前序阶段被过滤）的孤儿窗口 chunk 直接丢弃。
    """
    # 只索引非窗口 chunk 作为锚点。窗口 chunk 的 section.chunk_id 可能复制自锚点
    # （parent window 尤甚），若一并索引会与锚点撞 key。
    anchor_by_chunk_id: dict[str, Document] = {}
    for d in docs:
        if d.metadata.get("_window_expanded") or d.metadata.get("_parent_expanded"):
            continue
        cid = str(d.metadata.get("section.chunk_id") or "")
        if cid:
            anchor_by_chunk_id[cid] = d

    result: list[Document] = []
    for d in docs:
        is_window = d.metadata.get("_window_expanded") or d.metadata.get("_parent_expanded")
        if not is_window:
            result.append(d)
            continue
        if d.metadata.get("_noise_downgraded"):
            continue  # 噪声窗口直接丢弃
        anchor_id = str(
            d.metadata.get("_window_anchor_chunk_id")
            or d.metadata.get("_parent_anchor_chunk_id")
            or ""
        )
        anchor = anchor_by_chunk_id.get(anchor_id)
        if anchor is None:
            continue  # 孤儿窗口丢弃
        anchor.page_content = anchor.page_content + "\n\n" + d.page_content
        anchor.metadata["_window_merged"] = True

    return result
