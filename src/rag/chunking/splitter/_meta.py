"""自动拆分自 splitter.py（行为等价）。"""

from __future__ import annotations

import json

from langchain_core.documents import Document

from rag.chunking.splitter._params import _PARENT_WINDOW_CHAR_BUDGET


def _make_chunk(base_metadata: dict, text: str) -> Document:
    return Document(page_content=text, metadata=dict(base_metadata))


def _build_parent_window_text(
    detail_chunks: list[tuple[Document, str]],
    anchor_index: int,
    budget: int = _PARENT_WINDOW_CHAR_BUDGET,
) -> str:
    if not detail_chunks:
        return ""

    anchor_text = detail_chunks[anchor_index][0].page_content.strip()
    if len(anchor_text) >= budget:
        return anchor_text[:budget]

    selected: dict[int, str] = {anchor_index: anchor_text}
    total = len(anchor_text)
    left = anchor_index - 1
    right = anchor_index + 1

    while (left >= 0 or right < len(detail_chunks)) and total < budget:
        added = False
        if left >= 0:
            text = detail_chunks[left][0].page_content.strip()
            extra = len(text) + 2
            if total + extra <= budget:
                selected[left] = text
                total += extra
                added = True
            left -= 1
        if right < len(detail_chunks):
            text = detail_chunks[right][0].page_content.strip()
            extra = len(text) + 2
            if total + extra <= budget:
                selected[right] = text
                total += extra
                added = True
            right += 1
        if not added and left < 0 and right >= len(detail_chunks):
            break
        if not added and total >= budget:
            break

    return "\n\n".join(selected[idx] for idx in sorted(selected))


def _make_doc_id(source: str) -> str:
    """生成文档级唯一标识"""
    return f"doc::{source}"


def _make_section_id(source: str, section_index: int) -> str:
    """生成 section 唯一标识"""
    return f"sec::{source}::{section_index}"


def _make_chunk_id(source: str, section_index: int, chunk_index: int) -> str:
    """生成 chunk 唯一标识"""
    return f"chk::{source}::{section_index}::{chunk_index}"


def _compute_section_depth(heading_level: int) -> int:
    """将 Markdown heading level 映射为层级深度

    heading_level 0 (无标题) → depth 0 (文档级)
    heading_level 1 (#)      → depth 1 (章)
    heading_level 2 (##)     → depth 2 (节)
    heading_level 3-4        → depth 3 (小节)
    """
    if heading_level == 0:
        return 0
    if heading_level == 1:
        return 1
    if heading_level == 2:
        return 2
    return 3


def _write_section_level_metadata(
    chunk: Document,
    section: dict,
    section_id: str,
    parent_section_id: str | None,
    child_section_ids: list[str],
    *,
    ancestor_ids: list[str] | None,
    sibling_index: int,
    sibling_count: int,
    is_leaf: bool,
    doc_id: str,
    depth: int,
    heading_level: int,
) -> None:
    """写入文档级 + section 级元数据。"""
    # ── 文档级 ──
    chunk.metadata["section.doc_id"] = doc_id

    # ── section 级 ──
    chunk.metadata["section.id"] = section_id
    chunk.metadata["section.parent_id"] = parent_section_id
    chunk.metadata["section.child_ids"] = json.dumps(child_section_ids)
    chunk.metadata["section.ancestor_ids"] = json.dumps(ancestor_ids or [])
    chunk.metadata["section.depth"] = depth
    chunk.metadata["section.path"] = section["heading_path"]
    chunk.metadata["section.title"] = section["heading"]
    chunk.metadata["section.heading_level"] = heading_level
    chunk.metadata["section.index"] = section["section_index"]
    chunk.metadata["section.sibling_index"] = sibling_index
    chunk.metadata["section.sibling_count"] = sibling_count
    chunk.metadata["section.is_leaf"] = is_leaf
    chunk.metadata["section.char_count"] = len(section["text"])


def _write_chunk_level_metadata(
    chunk: Document,
    chunk_id: str,
    section_id: str,
    local_index: int,
    chunk_role: str,
    *,
    child_chunk_ids: list[str] | None,
    parent_chunk_id: str | None,
) -> None:
    """写入 chunk 级元数据 + chunk 间层级关系。"""
    # ── chunk 级 ──
    chunk.metadata["section.chunk_id"] = chunk_id
    chunk.metadata["section.chunk_parent_id"] = section_id
    chunk.metadata["section.chunk_index"] = local_index
    chunk.metadata["section.chunk_role"] = chunk_role

    # ── chunk 间层级关系 ──
    if chunk_role in ("summary", "qa", "merged_qa") and child_chunk_ids is not None:
        chunk.metadata["section.child_chunk_ids"] = json.dumps(child_chunk_ids)
    if parent_chunk_id is not None:
        chunk.metadata["section.parent_chunk_id"] = parent_chunk_id


def _write_legacy_metadata(
    chunk: Document, chunk_id: str, section: dict, global_index: int, local_index: int
) -> None:
    """写入旧字段（不删除，保证下游代码不 break）。"""
    chunk.metadata["chunk_id"] = chunk_id
    chunk.metadata["heading"] = section["heading_path"]
    chunk.metadata["heading_title"] = section["heading"]
    chunk.metadata["heading_level"] = section["heading_level"]
    chunk.metadata["heading_path"] = section["heading_path"]
    chunk.metadata["section_index"] = section["section_index"]
    chunk.metadata["chunk_index"] = global_index
    chunk.metadata["chunk_index_in_section"] = local_index
    chunk.metadata["char_count"] = len(chunk.page_content)


def _write_qa_fields(chunk: Document, chunk_role: str) -> None:
    """merged_qa 角色：把临时 `_qa_fields` 展开成 `qa.*` 字段（存储合并、检索分离）。"""
    if chunk_role != "merged_qa":
        return
    qa_fields = chunk.metadata.pop("_qa_fields", None)
    if qa_fields:
        chunk.metadata["qa.question"] = qa_fields.get("question", "")
        chunk.metadata["qa.answer"] = qa_fields.get("answer", "")
        chunk.metadata["qa.answer_key"] = qa_fields.get("answer_key", "")


def _append_chunk_metadata(
    chunk: Document,
    section: dict,
    section_id: str,
    parent_section_id: str | None,
    child_section_ids: list[str],
    global_index: int,
    local_index: int,
    chunk_role: str = "detail",
    *,
    child_chunk_ids: list[str] | None = None,
    parent_chunk_id: str | None = None,
    ancestor_ids: list[str] | None = None,
    sibling_index: int = 0,
    sibling_count: int = 1,
    is_leaf: bool = True,
    doc_id: str = "",
) -> None:
    """写入层级化元数据（新规范 + 旧字段兼容）

    Args:
        child_chunk_ids: 父 chunk 引用的子 chunk ID 列表（summary/qa 角色使用）
        parent_chunk_id: 子 chunk 引用的父 chunk ID（detail 角色使用）
        ancestor_ids: 从根到当前 section 的祖先 ID 链（不含自身）
        sibling_index: 在同级兄弟中的序号（0-based）
        sibling_count: 同级兄弟总数
        is_leaf: 是否为叶子 section（无子 section）
        doc_id: 文档级唯一标识
    """
    source = chunk.metadata.get("source_file") or chunk.metadata.get("source", "unknown")
    chunk_id = _make_chunk_id(source, section["section_index"], local_index)
    heading_level = section["heading_level"]
    _write_section_level_metadata(
        chunk,
        section,
        section_id,
        parent_section_id,
        child_section_ids,
        ancestor_ids=ancestor_ids,
        sibling_index=sibling_index,
        sibling_count=sibling_count,
        is_leaf=is_leaf,
        doc_id=doc_id,
        depth=_compute_section_depth(heading_level),
        heading_level=heading_level,
    )
    _write_chunk_level_metadata(
        chunk,
        chunk_id,
        section_id,
        local_index,
        chunk_role,
        child_chunk_ids=child_chunk_ids,
        parent_chunk_id=parent_chunk_id,
    )
    _write_qa_fields(chunk, chunk_role)
    _write_legacy_metadata(chunk, chunk_id, section, global_index, local_index)
