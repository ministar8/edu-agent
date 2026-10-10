"""切分主入口：`split_documents`（把文档切成 chunk）。

原为单函数 285 行，按三个阶段抽出子函数（行为等价，见 commit 的差分验证）：
  _build_section_hierarchy → _build_section_chunks（逐 section）→ _emit_split_metrics
"""

from __future__ import annotations

from typing import NamedTuple

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


class _Hierarchy(NamedTuple):
    """一个文档内各 section 的层级关系（索引对齐 `sections`）。"""

    doc_id: str
    ids: list[str]
    parent_ids: list[str | None]
    child_ids: list[list[str]]
    ancestor_ids: list[list[str]]
    sibling_indices: list[int]
    sibling_counts: list[int]
    is_leaf: list[bool]


def _build_section_hierarchy(sections: list[dict], source: str) -> _Hierarchy:
    """用栈构建 section 的 parent/child/ancestor/sibling/is_leaf 关系。"""
    doc_id = _make_doc_id(source)
    ids: list[str] = []
    parent_ids: list[str | None] = []
    child_ids: list[list[str]] = []
    ancestor_ids: list[list[str]] = []
    active_stack: list[int] = []  # indices into ids

    for i, section in enumerate(sections):
        sid = _make_section_id(source, section["section_index"])
        ids.append(sid)

        # 找 parent：栈中最后一个 heading_level < 当前的
        parent_idx = None
        while active_stack:
            candidate = active_stack[-1]
            if sections[candidate]["heading_level"] < section["heading_level"]:
                parent_idx = candidate
                break
            active_stack.pop()

        parent_ids.append(ids[parent_idx] if parent_idx is not None else None)
        child_ids.append([])  # 先初始化空，后面填充
        # 祖先链 = parent 的祖先链 + parent
        if parent_idx is not None:
            ancestor_ids.append(ancestor_ids[parent_idx] + [ids[parent_idx]])
            child_ids[parent_idx].append(sid)
        else:
            ancestor_ids.append([])
        active_stack.append(i)

    is_leaf = [len(child_ids[i]) == 0 for i in range(len(sections))]

    # 按 parent 分组计算 sibling_index/sibling_count（保持 section 索引顺序）
    sibling_indices: list[int] = []
    sibling_counts: list[int] = []
    parent_groups: dict[str | None, list[int]] = {}
    for i in range(len(sections)):
        parent_groups.setdefault(parent_ids[i], []).append(i)
    for i in range(len(sections)):
        siblings = parent_groups[parent_ids[i]]
        sibling_indices.append(siblings.index(i))
        sibling_counts.append(len(siblings))

    return _Hierarchy(
        doc_id, ids, parent_ids, child_ids, ancestor_ids, sibling_indices, sibling_counts, is_leaf
    )


def _resolve_content_type(section: dict) -> tuple[str, bool, bool]:
    """按内容推断 content_type，并做「练习题 Q&A」检测。

    Returns:
        ``(content_type, has_answer_marker, heading_is_exercise)``。
    """
    from rag.common.rag_utils import detect_content_type as _detect_content_type

    # 根据 section 内容推断 content_type（需要一段文字来检测）
    content_type = _detect_content_type(
        section["text"][:200], {"heading_title": section["heading"]}
    )
    # ── 练习题 Q&A 检测 ──
    # section 内含「答案：」类标记，且 heading 含 "题"/"例题"（或 content_type 已是
    # exercise/answer），则整个 section 视为 merged_qa。
    section_text = section["text"]
    has_answer_marker = bool(_ANSWER_RE.search(section_text))
    heading_is_exercise = any(kw in section["heading"] for kw in ("题", "例题", "习题", "练习"))
    if has_answer_marker and (heading_is_exercise or content_type in ("exercise", "answer")):
        content_type = "merged_qa"
    return content_type, has_answer_marker, heading_is_exercise


def _build_merged_qa_chunks(doc: Document, section_text: str) -> list[tuple[Document, str]]:
    """merged_qa section（无可用 is_qa 块）→ 按题号拆或整体输出。

    超长走 `_split_qa_oversized`；否则整段一个 chunk。两者都带 `_qa_fields`。
    """
    out: list[tuple[Document, str]] = []
    if len(section_text) > _QA_CHUNK_SOFT_LIMIT:
        for sub in _split_qa_oversized(section_text, _QA_CHUNK_SOFT_LIMIT):
            sub = sub.strip()
            if len(sub) < MIN_CHUNK_LENGTH:
                continue
            chunk = _make_chunk(doc.metadata, sub)
            # heading_path 不拼入 page_content，避免干扰 embedding/reranker；
            # section 上下文已通过 metadata (section.path) 传递给 LLM。
            chunk.metadata["_qa_fields"] = _extract_qa_fields(sub)
            out.append((chunk, "merged_qa"))
    else:
        chunk = _make_chunk(doc.metadata, section_text.strip())
        chunk.metadata["_qa_fields"] = _extract_qa_fields(section_text)
        out.append((chunk, "merged_qa"))
    return out


def _attach_code_anchor(chunk_text: str, section: dict, sc: dict | None) -> str:
    """含代码围栏的 chunk：把 heading_path 拼回 page_content 作语义锚点。

    纯代码正文没有中文语义，bge-m3 无法把中文 query 映射到纯 C 代码上。判据用
    `_looks_like_code_chunk`（围栏 / `is_code` 单元 / 无围栏代码碎片），不能只看 chunk
    内是否残留 ```。其余类型仍守「heading 不进 page_content」；merged_qa 本身是中文题干，
    加锚点反而稀释。只保留**考点级父标题**（去掉文件级标题与当前标题）作为锚点。
    """
    is_qa = bool(sc.get("is_qa", False)) if isinstance(sc, dict) else False
    _is_code_like = (not is_qa) and _looks_like_code_chunk(
        chunk_text, is_code_unit=bool(sc.get("is_code")) if isinstance(sc, dict) else False
    )
    if not (_is_code_like and section.get("heading_path")):
        return chunk_text
    _hp = section["heading_path"].strip("[]")
    _parts = [p.strip() for p in _hp.split(">") if p.strip()]
    if len(_parts) >= 3:
        _anchor = " > ".join(_parts[1:-1])
    elif len(_parts) == 2:
        _anchor = _parts[-1]
    else:
        _anchor = _hp
    return f"[{_anchor}]\n{chunk_text}" if _anchor else chunk_text


def _build_detail_chunks(
    doc: Document, section: dict, section_text: str, section_chunks: list
) -> list[tuple[Document, str]]:
    """普通 section → detail / merged_qa chunk（每个都过 MIN_CHUNK_LENGTH）。"""
    out: list[tuple[Document, str]] = []
    for sc in section_chunks:
        chunk_text = sc["text"].strip() if isinstance(sc, dict) else sc.strip()
        if len(chunk_text) < MIN_CHUNK_LENGTH:
            continue
        is_qa = sc.get("is_qa", False) if isinstance(sc, dict) else False
        qa_fields = sc.get("qa_fields") if isinstance(sc, dict) else None
        chunk_text = _attach_code_anchor(chunk_text, section, sc)
        chunk = _make_chunk(doc.metadata, chunk_text)
        # 临时存储 qa_fields，后续 _append_chunk_metadata 会消费
        if is_qa and qa_fields:
            chunk.metadata["_qa_fields"] = qa_fields
        out.append((chunk, "merged_qa" if is_qa else "detail"))
    return out


def _build_section_chunks(
    doc: Document, section: dict, i: int, h: _Hierarchy, base_index: int
) -> list[Document]:
    """切分单个 section → 该 section 的 chunk 列表（已补全全部元数据）。"""
    sid = h.ids[i]
    section_text = section["text"]
    content_type, has_answer_marker, heading_is_exercise = _resolve_content_type(section)
    adaptive_size, adaptive_overlap = _resolve_chunk_params(content_type)

    # adaptive_size=0 表示原子结构不在通用切分器中拆分；真题整卷的拆分由 merged_qa fallback 处理
    effective_size = min(adaptive_size, _CHUNK_HARD_LIMIT) if adaptive_size > 0 else 999999
    section_chunks = _split_section_text(section_text, effective_size, adaptive_overlap)

    # 判据必须是「可用」而不是「存在」：真题 section 首行 `### 第N题(…)` 会被切成一个
    # 17 字的 is_qa 块，随即被 MIN_CHUNK_LENGTH 过滤掉 —— 只看 is_qa 标志是假信号。
    usable_qa_chunk = any(
        isinstance(sc, dict)
        and sc.get("is_qa", False)
        and len(str(sc.get("text", "")).strip()) >= MIN_CHUNK_LENGTH
        for sc in section_chunks
    )
    if content_type == "merged_qa" and not usable_qa_chunk and section_text.strip():
        detail_chunks = _build_merged_qa_chunks(doc, section_text)
    else:
        detail_chunks = _build_detail_chunks(doc, section, section_text, section_chunks)

    chunk_count = len(detail_chunks)
    parent_windows = [_build_parent_window_text(detail_chunks, ci) for ci in range(chunk_count)]

    chunks: list[Document] = []
    for ci, (chunk, chunk_role) in enumerate(detail_chunks):
        _append_chunk_metadata(
            chunk,
            section,
            sid,
            h.parent_ids[i],
            h.child_ids[i],
            base_index + ci,
            ci,
            chunk_role=chunk_role,
            parent_chunk_id=None,
            ancestor_ids=h.ancestor_ids[i],
            sibling_index=h.sibling_indices[i],
            sibling_count=h.sibling_counts[i],
            is_leaf=h.is_leaf[i],
            doc_id=h.doc_id,
        )
        chunk.metadata["section.chunk_count"] = chunk_count
        chunk.metadata["section.adaptive_size"] = adaptive_size
        chunk.metadata["section.adaptive_overlap"] = adaptive_overlap
        # merged_qa 的 content_type 固定
        chunk.metadata["section.content_type"] = (
            "merged_qa" if chunk_role == "merged_qa" else content_type
        )
        # ── 内容语义标志（供 recall 的 exercise_meta / answer_meta 路由过滤）──
        # 不复用 content_type：它是单值形状分类器，一个 chunk 可既是「列表」又是「习题」。
        chunk.metadata["is_exercise_content"] = heading_is_exercise
        chunk.metadata["has_answer_marker"] = has_answer_marker
        chunk.metadata["section.parent_id_index"] = sid
        chunk.metadata["section.parent_text"] = parent_windows[ci]
        chunk.metadata["section.parent_char_count"] = len(parent_windows[ci])
        chunk.metadata["section.parent_window_index"] = ci
        chunk.metadata["section.parent_window_budget"] = _PARENT_WINDOW_CHAR_BUDGET
        chunks.append(chunk)
    return chunks


def _emit_split_metrics(documents: list[Document], valid_chunks: list[Document]) -> None:
    """切分统计埋点（不影响返回结果）。"""
    chunk_lengths = [
        int(c.metadata.get("char_count") or len(c.page_content or "")) for c in valid_chunks
    ]
    incomplete_detail_count = sum(
        1 for c in valid_chunks if not _is_sentence_complete(c.page_content)
    )
    merged_qa_count = sum(
        1 for c in valid_chunks if c.metadata.get("section.chunk_role") == "merged_qa"
    )

    def _ratio(num: int, den: int) -> float:
        return round(num / den, 6) if den else 0.0

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
            "short_chunk_ratio": _ratio(
                sum(1 for n in chunk_lengths if n < max(MIN_CHUNK_LENGTH * 3, 60)),
                len(chunk_lengths),
            ),
            "long_chunk_ratio": _ratio(
                sum(1 for n in chunk_lengths if n > 1600), len(chunk_lengths)
            ),
            "mid_sentence_cut_rate": _ratio(incomplete_detail_count, len(valid_chunks)),
        },
    )
    logger.info("Split %d documents into %d chunks", len(documents), len(valid_chunks))


def split_documents(documents: list[Document]) -> list[Document]:
    """把文档切成 chunk。

    签名里没有 `chunk_size` / `chunk_overlap`：切分尺寸完全由 `_ADAPTIVE_CHUNK_SIZE` /
    `_ADAPTIVE_CHUNK_OVERLAP` 按 content_type 决定（正文 800 / 代码 400 / 表格与公式不拆），
    单个全局尺寸无法同时满足这些约束，加参数只会让人误以为调得动。

    若要调整切分尺寸，请改那两个映射，并**重跑检索质量门禁**确认没有退化。
    """
    valid_chunks: list[Document] = []
    for doc in documents:
        source = str(doc.metadata.get("source_file") or doc.metadata.get("source") or "unknown")
        sections = _split_into_sections(doc.page_content, _extract_headings(doc.page_content))
        h = _build_section_hierarchy(sections, source)
        for i, section in enumerate(sections):
            valid_chunks.extend(_build_section_chunks(doc, section, i, h, len(valid_chunks)))
    _emit_split_metrics(documents, valid_chunks)
    return valid_chunks
