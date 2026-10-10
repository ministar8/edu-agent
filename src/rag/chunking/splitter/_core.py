"""自动拆分自 splitter.py（行为等价）。"""

from __future__ import annotations

from langchain_core.documents import Document

from rag.chunking.splitter._code import _looks_like_code_chunk
from rag.chunking.splitter._heading import _extract_headings, _split_into_sections
from rag.chunking.splitter._log import logger
from rag.chunking.splitter._meta import (
    _append_chunk_metadata,
    _build_parent_window_text,
    _make_chunk,
    _make_doc_id,
    _make_section_id,
)
from rag.chunking.splitter._packing import _split_qa_oversized, _split_section_text
from rag.chunking.splitter._params import (
    _CHUNK_HARD_LIMIT,
    _PARENT_WINDOW_CHAR_BUDGET,
    _QA_CHUNK_SOFT_LIMIT,
    MIN_CHUNK_LENGTH,
    _resolve_chunk_params,
)
from rag.chunking.splitter._qa import _ANSWER_RE, _extract_qa_fields
from rag.chunking.splitter._text import _is_sentence_complete, _percentile
from rag.common.metrics import metrics


def split_documents(documents: list[Document]) -> list[Document]:
    """把文档切成 chunk。

    签名里没有 `chunk_size` / `chunk_overlap`：切分尺寸完全由 `_ADAPTIVE_CHUNK_SIZE` /
    `_ADAPTIVE_CHUNK_OVERLAP` 按 content_type 决定（正文 800 / 代码 400 / 表格与公式不拆），
    单个全局尺寸无法同时满足这些约束，加参数只会让人误以为调得动。

    若要调整切分尺寸，请改那两个映射，并**重跑检索质量门禁**确认没有退化。
    """
    valid_chunks: list[Document] = []

    for doc in documents:
        original_text = doc.page_content
        source = str(doc.metadata.get("source_file") or doc.metadata.get("source") or "unknown")
        headings = _extract_headings(original_text)
        sections = _split_into_sections(original_text, headings)

        # ── 构建 section 层级关系 ──
        # 每个 section 记录其 parent, children, ancestors, siblings, is_leaf
        doc_id = _make_doc_id(source)
        section_ids: list[str] = []
        section_parent_ids: list[str | None] = []
        section_child_ids: list[list[str]] = []
        section_ancestor_ids: list[list[str]] = []
        section_sibling_indices: list[int] = []
        section_sibling_counts: list[int] = []

        # 用栈追踪当前活跃的各级 section
        active_stack: list[int] = []  # indices into section_ids

        for i, section in enumerate(sections):
            sid = _make_section_id(source, section["section_index"])
            section_ids.append(sid)

            # 找 parent：栈中最后一个 heading_level < 当前的
            parent_idx = None
            while active_stack:
                candidate = active_stack[-1]
                if sections[candidate]["heading_level"] < section["heading_level"]:
                    parent_idx = candidate
                    break
                active_stack.pop()

            parent_id = section_ids[parent_idx] if parent_idx is not None else None
            section_parent_ids.append(parent_id)
            section_child_ids.append([])  # 先初始化空，后面填充

            # 祖先链 = parent 的祖先链 + parent
            if parent_idx is not None:
                ancestors = section_ancestor_ids[parent_idx] + [section_ids[parent_idx]]
            else:
                ancestors = []
            section_ancestor_ids.append(ancestors)

            # 将自己加入 parent 的 child_ids
            if parent_idx is not None:
                section_child_ids[parent_idx].append(sid)

            active_stack.append(i)

        # 计算兄弟信息和 is_leaf
        section_is_leaf: list[bool] = []
        for i in range(len(sections)):
            section_is_leaf.append(len(section_child_ids[i]) == 0)

        # 按 parent 分组计算 sibling_index/sibling_count
        parent_groups: dict[str | None, list[int]] = {}
        for i in range(len(sections)):
            pid = section_parent_ids[i]
            parent_groups.setdefault(pid, []).append(i)

        # 预计算每个 section 的兄弟信息（保持 section 索引顺序）
        for i in range(len(sections)):
            pid = section_parent_ids[i]
            siblings = parent_groups[pid]
            rank = siblings.index(i)
            section_sibling_indices.append(rank)
            section_sibling_counts.append(len(siblings))

        # ── 切分 chunk ──
        from rag.common.rag_utils import detect_content_type as _detect_content_type

        for i, section in enumerate(sections):
            sid = section_ids[i]
            parent_id = section_parent_ids[i]
            child_ids = section_child_ids[i]
            ancestors = section_ancestor_ids[i]
            sib_idx = section_sibling_indices[i]
            sib_count = section_sibling_counts[i]
            is_leaf = section_is_leaf[i]

            # 根据 section 内容推断 content_type（需要一段文字来检测）
            sample_text = section["text"][:200]
            content_type = _detect_content_type(sample_text, {"heading_title": section["heading"]})

            # ── 练习题 Q&A 检测 ──
            # section 内含「答案：」类标记，且 heading 含 "题"/"例题"（或 content_type 已是
            # exercise/answer），则整个 section 视为 merged_qa。
            section_text = section["text"]
            has_answer_marker = bool(_ANSWER_RE.search(section_text))
            heading_is_exercise = any(
                kw in section["heading"] for kw in ("题", "例题", "习题", "练习")
            )
            if has_answer_marker and (
                heading_is_exercise or content_type in ("exercise", "answer")
            ):
                content_type = "merged_qa"

            adaptive_size, adaptive_overlap = _resolve_chunk_params(content_type)

            # 生成 detail / merged_qa chunk
            # adaptive_size=0 表示原子结构不在通用切分器中拆分；
            # 真题整卷的拆分由下方 merged_qa fallback 按题号处理。
            effective_size = min(adaptive_size, _CHUNK_HARD_LIMIT) if adaptive_size > 0 else 999999
            section_chunks = _split_section_text(section["text"], effective_size, adaptive_overlap)
            detail_chunks: list[tuple[Document, str]] = []

            # 若 content_type 是 merged_qa 但 _split_section_text 未产出**可用**的 is_qa 块
            # （真题模式：无 blockquote，整个 section 就是一个 Q&A 对），强制整体输出。
            # 判据必须是「可用」而不是「存在」：真题 section 首行 `### 第N题(…)` 会被切成
            # 一个 17 字的 is_qa 块，随即被 MIN_CHUNK_LENGTH 过滤掉 —— 只看 is_qa 标志是假信号，
            # 兜底不触发，正文退回 detail 分支，qa.question / qa.answer 全为空。
            usable_qa_chunk = any(
                isinstance(sc, dict)
                and sc.get("is_qa", False)
                and len(str(sc.get("text", "")).strip()) >= MIN_CHUNK_LENGTH
                for sc in section_chunks
            )
            if content_type == "merged_qa" and not usable_qa_chunk and section_text.strip():
                # 超长 merged_qa section：按题目边界拆分，但不拆单题内部题干/答案/解析
                if len(section_text) > _QA_CHUNK_SOFT_LIMIT:
                    for sub in _split_qa_oversized(section_text, _QA_CHUNK_SOFT_LIMIT):
                        sub = sub.strip()
                        if len(sub) < MIN_CHUNK_LENGTH:
                            continue
                        qa_fields = _extract_qa_fields(sub)
                        chunk = _make_chunk(doc.metadata, sub)
                        # heading_path 不拼入 page_content，避免干扰 embedding/reranker
                        # section 上下文已通过 metadata (section.path) 传递给 LLM
                        chunk.metadata["_qa_fields"] = qa_fields
                        detail_chunks.append((chunk, "merged_qa"))
                else:
                    qa_fields = _extract_qa_fields(section_text)
                    chunk = _make_chunk(doc.metadata, section_text.strip())
                    chunk.metadata["_qa_fields"] = qa_fields
                    detail_chunks.append((chunk, "merged_qa"))
            else:
                for sc in section_chunks:
                    chunk_text = sc["text"].strip() if isinstance(sc, dict) else sc.strip()
                    if len(chunk_text) < MIN_CHUNK_LENGTH:
                        continue
                    is_qa = sc.get("is_qa", False) if isinstance(sc, dict) else False
                    qa_fields = sc.get("qa_fields") if isinstance(sc, dict) else None
                    # 含代码围栏的 chunk：把 heading_path 拼回 page_content 作为语义锚点。
                    # 纯代码正文没有中文语义，bge-m3 无法把中文 query 映射到纯 C 代码上。
                    # 判据用 `_looks_like_code_chunk`（围栏、`is_code` 单元、无围栏代码碎片），
                    # 不能只看 chunk 内是否残留 ```。其余类型仍守「heading 不进 page_content」。
                    # merged_qa（真题）本身是中文题干，加锚点反而稀释。
                    _is_code_like = (not is_qa) and _looks_like_code_chunk(
                        chunk_text,
                        is_code_unit=bool(sc.get("is_code")) if isinstance(sc, dict) else False,
                    )
                    if _is_code_like and section.get("heading_path"):
                        # 只保留考点级父标题（去掉文件级标题与当前标题）作为锚点，
                        # 避免「操作系统代码实现」这类文件级泛词稀释 embedding 区分度。
                        _hp = section["heading_path"].strip("[]")
                        _parts = [p.strip() for p in _hp.split(">") if p.strip()]
                        if len(_parts) >= 3:
                            _anchor = " > ".join(_parts[1:-1])
                        elif len(_parts) == 2:
                            _anchor = _parts[-1]
                        else:
                            _anchor = _hp
                        if _anchor:
                            chunk_text = f"[{_anchor}]\n{chunk_text}"
                    chunk = _make_chunk(doc.metadata, chunk_text)
                    # 临时存储 qa_fields，后续 _append_chunk_metadata 会消费
                    if is_qa and qa_fields:
                        chunk.metadata["_qa_fields"] = qa_fields
                    chunk_role = "merged_qa" if is_qa else "detail"
                    detail_chunks.append((chunk, chunk_role))

            chunk_count = len(detail_chunks)
            parent_windows = [
                _build_parent_window_text(detail_chunks, ci) for ci in range(chunk_count)
            ]

            for ci, (chunk, chunk_role) in enumerate(detail_chunks):
                _append_chunk_metadata(
                    chunk,
                    section,
                    sid,
                    parent_id,
                    child_ids,
                    len(valid_chunks),
                    ci,
                    chunk_role=chunk_role,
                    parent_chunk_id=None,
                    ancestor_ids=ancestors,
                    sibling_index=sib_idx,
                    sibling_count=sib_count,
                    is_leaf=is_leaf,
                    doc_id=doc_id,
                )
                chunk.metadata["section.chunk_count"] = chunk_count
                chunk.metadata["section.adaptive_size"] = adaptive_size
                chunk.metadata["section.adaptive_overlap"] = adaptive_overlap
                # merged_qa 的 content_type 固定
                chunk.metadata["section.content_type"] = (
                    "merged_qa" if chunk_role == "merged_qa" else content_type
                )
                # ── 内容语义标志（供 recall 的 exercise_meta / answer_meta 路由过滤）──
                # 不复用 content_type：它是**单值形状分类器**，一个 chunk 可以既是「列表」（形状）
                # 又是「习题」（语义），挤在一个字段里会互相挤掉；且 content_type 还经
                # `_resolve_chunk_params` 决定切分尺寸，改它的判定顺序会连带**重切索引**。
                chunk.metadata["is_exercise_content"] = heading_is_exercise
                chunk.metadata["has_answer_marker"] = has_answer_marker
                chunk.metadata["section.parent_id_index"] = sid
                chunk.metadata["section.parent_text"] = parent_windows[ci]
                chunk.metadata["section.parent_char_count"] = len(parent_windows[ci])
                chunk.metadata["section.parent_window_index"] = ci
                chunk.metadata["section.parent_window_budget"] = _PARENT_WINDOW_CHAR_BUDGET
                valid_chunks.append(chunk)

    # ── 统计 ──
    chunk_lengths = [
        int(c.metadata.get("char_count") or len(c.page_content or "")) for c in valid_chunks
    ]
    incomplete_detail_count = sum(
        1 for c in valid_chunks if not _is_sentence_complete(c.page_content)
    )
    merged_qa_count = sum(
        1 for c in valid_chunks if c.metadata.get("section.chunk_role") == "merged_qa"
    )
    metrics.emit(
        event="split_documents",
        stage="splitter",
        values={
            "input_docs": len(documents),
            "total_chunks": len(valid_chunks),
            "detail_chunks": len(valid_chunks) - merged_qa_count,
            "merged_qa_chunks": merged_qa_count,
            "avg_chunk_chars": round(sum(chunk_lengths) / len(chunk_lengths), 3)
            if chunk_lengths
            else 0.0,
            "p50_chunk_chars": _percentile(chunk_lengths, 0.5),
            "p90_chunk_chars": _percentile(chunk_lengths, 0.9),
            "short_chunk_ratio": round(
                sum(1 for n in chunk_lengths if n < max(MIN_CHUNK_LENGTH * 3, 60))
                / len(chunk_lengths),
                6,
            )
            if chunk_lengths
            else 0.0,
            "long_chunk_ratio": round(
                sum(1 for n in chunk_lengths if n > 1600) / len(chunk_lengths), 6
            )
            if chunk_lengths
            else 0.0,
            "mid_sentence_cut_rate": round(incomplete_detail_count / len(valid_chunks), 6)
            if valid_chunks
            else 0.0,
        },
    )
    logger.info("Split %d documents into %d chunks", len(documents), len(valid_chunks))
    return valid_chunks
