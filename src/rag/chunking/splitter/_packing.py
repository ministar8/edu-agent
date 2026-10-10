"""自动拆分自 splitter.py（行为等价）。"""

from __future__ import annotations

import re

from rag.chunking.splitter._params import _CHUNK_HARD_LIMIT, _CHUNK_MIN_EFFECTIVE, MIN_CHUNK_LENGTH
from rag.chunking.splitter._qa import _extract_qa_fields
from rag.chunking.splitter._text import _is_sentence_complete
from rag.chunking.splitter._units import (
    _build_overlap_units,
    _parse_semantic_units,
    _render_units,
    _split_sentences,
)


def _split_section_text(
    text: str,
    chunk_size: int = 800,
    chunk_overlap: int = 200,
) -> list[dict]:
    """结构化分块：按语义单元贪心合并，强制句子完整边界

    Q&A / 表格 / 公式为原子单元**不被拆分**（过短的原子单元仍会与邻居整体拼接，
    见 _merge_short_chunks）；超长单元按句子拆分，上限 _CHUNK_HARD_LIMIT；
    overlap 回溯优先取同 section 的尾部单元。

    Returns:
        [{"text": str, "is_qa": bool, "qa_fields": dict|None}, ...]
    """
    units = _parse_semantic_units(text)
    if not units:
        return []

    chunks: list[dict] = []
    current_units: list[dict] = []

    for unit in units:
        unit_text = unit["text"].strip()
        if not unit_text:
            continue

        is_qa = unit.get("is_qa", False)
        is_table = unit.get("is_table", False)
        is_formula = unit.get("is_formula", False)
        is_atomic = is_qa or is_table or is_formula

        # 原子单元：始终单独输出，不与其它单元合并
        if is_atomic:
            # 先输出当前累积的非原子单元
            if current_units:
                _flush_chunk(chunks, current_units, chunk_size)
                current_units = []
            if is_qa:
                qa_fields = _extract_qa_fields(unit_text)
                chunks.append({"text": unit_text, "is_qa": True, "qa_fields": qa_fields})
            else:
                chunks.append({"text": unit_text, "is_qa": False, "qa_fields": None})
            continue

        if len(unit_text) > _CHUNK_HARD_LIMIT:
            if current_units:
                _flush_chunk(chunks, current_units, chunk_size)
                current_units = []
            for sub in _split_oversized(unit_text, _CHUNK_HARD_LIMIT):
                chunks.append({"text": sub, "is_qa": False, "qa_fields": None})
            continue

        candidate = [*current_units, unit]
        candidate_text = _render_units(candidate)

        if len(candidate_text) <= chunk_size:
            current_units.append(unit)
            continue

        # 超出：先输出当前 chunk，再用它的尾部单元做 overlap 回溯
        # _flush_chunk / _build_overlap_units 都不改动传入的列表，故无需先拷贝一份
        if current_units:
            _flush_chunk(chunks, current_units, chunk_size)
        overlap_units = _build_overlap_units(current_units, chunk_overlap)
        if overlap_units and len(_render_units([*overlap_units, unit])) > chunk_size:
            overlap_units = []

        current_units = [*overlap_units, unit]

    if current_units:
        _flush_chunk(chunks, current_units, chunk_size)

    chunks = _merge_short_chunks(chunks, _CHUNK_MIN_EFFECTIVE, chunk_size)

    return chunks


def _flush_chunk(chunks: list[dict], units: list[dict], chunk_size: int) -> None:
    """输出当前 chunk：末尾若不在句子完整处结束，从后向前回退到上一个完整边界，避免句中截断。"""
    if not units:
        return
    text = _render_units(units)
    if not text.strip():
        return

    if _is_sentence_complete(text):
        chunks.append({"text": text, "is_qa": False, "qa_fields": None})
        return

    remaining = list(units)
    tail_units: list[dict] = []
    while remaining and not _is_sentence_complete(_render_units(remaining)):
        tail_units.insert(0, remaining.pop())

    if remaining:
        chunks.append({"text": _render_units(remaining), "is_qa": False, "qa_fields": None})
        if tail_units:
            tail_text = _render_units(tail_units)
            if len(tail_text.strip()) >= MIN_CHUNK_LENGTH:
                chunks.append({"text": tail_text, "is_qa": False, "qa_fields": None})
    else:
        # 找不到任何完整边界时整体输出，宁可长也不丢内容
        chunks.append({"text": text, "is_qa": False, "qa_fields": None})


def _pack_qa_parts(parts: list[str], limit: int) -> list[str]:
    """把题目片段按顺序累加成段：加入下一题会超 limit 就先切一段，题内绝不拆。"""
    result: list[str] = []
    buf: list[str] = []
    buf_len = 0
    for part in parts:
        part = part.strip()
        if not part:
            continue
        if buf and buf_len + len(part) > limit:
            result.append("\n\n".join(buf))
            buf = []
            buf_len = 0
        buf.append(part)
        buf_len += len(part)
    if buf:
        result.append("\n\n".join(buf))
    return [r for r in result if r.strip()]


def _split_qa_oversized(text: str, limit: int) -> list[str]:
    """将超长 QA 块按题目边界拆分，每段不超过 limit

    题目边界有两种：真题的 `##### N` / `### 第N题` 标题行，例题的 `> 例题/例N` 开头。
    每个题目+答案保持原子性，不跨题拆分。
    """
    # 按真题标题拆分（支持旧格式 ##### N 和新格式 ### 第N题）
    parts = re.split(r"(?=^#{2,5}\s*(?:\d+\s*$|第\d+题))", text, flags=re.MULTILINE)
    if len(parts) > 1:
        return _pack_qa_parts(parts, limit)

    # 按例题标记拆分
    parts = re.split(r"(?=>\s*例[题\d])", text)
    if len(parts) > 1:
        return _pack_qa_parts(parts, limit)

    # 无法按题目边界拆分，整体保留，避免破坏题干-答案-解析原子性
    return [text.strip()] if text.strip() else []


def _split_oversized(text: str, limit: int) -> list[str]:
    """将超长文本按句子边界拆分，保证每段不超过 limit

    单句本身就超 limit 时（无标点的长列表项、被压成一行的表格）**必须硬切**，
    否则 limit 形同虚设：一个 500 字的单句在 limit=100 下仍会整块落进一个 chunk。
    """
    sentences = _split_sentences(text)
    result: list[str] = []
    buf: list[str] = []
    buf_len = 0
    for sent in sentences:
        if len(sent) > limit:
            # 先把缓冲区冲掉，再对这一句做定长硬切，避免与后面的句子混拼
            if buf:
                result.append(" ".join(buf))
                buf = []
                buf_len = 0
            result.extend(sent[i : i + limit] for i in range(0, len(sent), limit))
            continue
        if buf and buf_len + len(sent) > limit:
            result.append(" ".join(buf))
            buf = []
            buf_len = 0
        buf.append(sent)
        buf_len += len(sent)
    if buf:
        result.append(" ".join(buf))
    return [r for r in result if r.strip()]


def _merge_short_chunks(chunks: list[dict], min_len: int, max_len: int) -> list[dict]:
    """后处理：将过短 chunk 与邻居合并，避免它们被 MIN_CHUNK_LENGTH 过滤掉

    只有 QA 不参与合并 —— 题干与答案必须留在同一个 chunk 里。

    表格/公式允许合并：本函数的合并是**整体拼接**，不会把它们拆开，内部结构始终完整。
    反过来禁止合并，过短的原子 chunk 会连同它的过短邻居一起落到 MIN_CHUNK_LENGTH
    之下被丢弃（实测全库留存率 97.6% → 96.5%）。
    所以这里「原子性」的准确含义是**不被拆分**，而不是「不参与合并」。
    """
    if not chunks:
        return chunks
    merged: list[dict] = [dict(chunks[0])]
    for chunk in chunks[1:]:
        prev = merged[-1]
        prev_text = prev["text"]
        cur_text = chunk["text"]
        if (
            len(prev_text) < min_len
            and len(prev_text) + len(cur_text) + 2 <= max_len
            and not prev.get("is_qa")
            and not chunk.get("is_qa")
        ):
            prev["text"] = prev_text + "\n\n" + cur_text
        else:
            merged.append(dict(chunk))
    return merged
