"""自动拆分自 splitter.py（行为等价）。"""

from __future__ import annotations

import re

from rag.chunking.splitter._params import _PROSE_UNIT_MAX_CHARS
from rag.chunking.splitter._qa import (
    _LIST_ITEM_RE,
    _merge_qa_blockquotes,
    _restore_code_placeholders,
)

_FENCED_CODE_BLOCK_RE = re.compile(r"(?ms)^[ \t]{0,3}(```+|~~~+)[^\n]*\n.*?^[ \t]{0,3}\1[ \t]*$")


def _parse_semantic_units(text: str) -> list[dict]:
    """将文本解析为语义单元（段落 / 列表项组 / 代码块 / Q&A 对 / 表格 / 公式块）

    代码块、表格、公式、Q&A 对为原子单元**不可拆分**；连续列表行合并为一个单元；
    空行分隔的段落为一个单元，单个过长段落按句子边界再拆。

    Returns:
        [{"text": str, "is_code": bool, "is_qa": bool, "is_table": bool, "is_formula": bool}, ...]
    """
    units: list[dict] = []

    # 1. 提取代码块，替换为占位符
    code_blocks: list[str] = []

    def _code_placeholder(m: re.Match) -> str:
        code_blocks.append(m.group(0).strip())
        return f"\n__CODE_BLOCK_{len(code_blocks) - 1}__\n"

    text_no_code = _FENCED_CODE_BLOCK_RE.sub(_code_placeholder, text)

    # 2. 提取 Markdown 表格，替换为占位符
    _MD_TABLE_RE = re.compile(r"(?m)(?:^\|.+\|$\n?)+")
    table_blocks: list[str] = []

    def _table_placeholder(m: re.Match) -> str:
        table_blocks.append(m.group(0).strip())
        return f"\n__TABLE_BLOCK_{len(table_blocks) - 1}__\n"

    text_no_table = _MD_TABLE_RE.sub(_table_placeholder, text_no_code)

    # 3. 提取 LaTeX 公式块，替换为占位符
    _LATEX_BLOCK_RE = re.compile(r"(?ms)\$\$.+?\$\$")
    formula_blocks: list[str] = []

    def _formula_placeholder(m: re.Match) -> str:
        formula_blocks.append(m.group(0).strip())
        return f"\n__FORMULA_BLOCK_{len(formula_blocks) - 1}__\n"

    text_no_formula = _LATEX_BLOCK_RE.sub(_formula_placeholder, text_no_table)

    # 4. 预扫描：把 Q&A 合并为原子块
    text_with_qa = _merge_qa_blockquotes(text_no_formula)

    # 5. 按空行切分为文本块
    blocks = re.split(r"\n{2,}", text_with_qa.strip())

    for block in blocks:
        block = block.strip()
        if not block:
            continue

        # 代码块占位符还原
        if block.startswith("__CODE_BLOCK_") and block.endswith("__"):
            idx_match = re.search(r"__CODE_BLOCK_(\d+)__", block)
            if idx_match:
                units.append(
                    {
                        "text": code_blocks[int(idx_match.group(1))],
                        "is_code": True,
                        "is_qa": False,
                        "is_table": False,
                        "is_formula": False,
                    }
                )
                continue

        # 表格占位符还原
        if block.startswith("__TABLE_BLOCK_") and block.endswith("__"):
            idx_match = re.search(r"__TABLE_BLOCK_(\d+)__", block)
            if idx_match:
                units.append(
                    {
                        "text": table_blocks[int(idx_match.group(1))],
                        "is_code": False,
                        "is_qa": False,
                        "is_table": True,
                        "is_formula": False,
                    }
                )
                continue

        # 公式块占位符还原
        if block.startswith("__FORMULA_BLOCK_") and block.endswith("__"):
            idx_match = re.search(r"__FORMULA_BLOCK_(\d+)__", block)
            if idx_match:
                units.append(
                    {
                        "text": formula_blocks[int(idx_match.group(1))],
                        "is_code": False,
                        "is_qa": False,
                        "is_table": False,
                        "is_formula": True,
                    }
                )
                continue

        # Q&A 原子单元（已被 _merge_qa_blockquotes 标记）
        if block.startswith("__QA_PAIR_START__"):
            inner = block[len("__QA_PAIR_START__") :].strip()
            inner = _restore_code_placeholders(inner, code_blocks)
            units.append(
                {
                    "text": inner,
                    "is_code": False,
                    "is_qa": True,
                    "is_table": False,
                    "is_formula": False,
                }
            )
            continue

        # 列表项组：连续的列表行合并为一个单元
        lines = block.splitlines()
        list_lines: list[str] = []
        prose_lines: list[str] = []

        for line in lines:
            if _LIST_ITEM_RE.match(line):
                if prose_lines:
                    _add_prose_unit(units, "\n".join(prose_lines))
                    prose_lines = []
                list_lines.append(line)
            else:
                if list_lines:
                    units.append(
                        {
                            "text": "\n".join(list_lines),
                            "is_code": False,
                            "is_qa": False,
                            "is_table": False,
                            "is_formula": False,
                        }
                    )
                    list_lines = []
                prose_lines.append(line)

        # 收尾：把缓冲区里剩下的行落进 units
        if list_lines:
            units.append(
                {
                    "text": "\n".join(list_lines),
                    "is_code": False,
                    "is_qa": False,
                    "is_table": False,
                    "is_formula": False,
                }
            )
        if prose_lines:
            _add_prose_unit(units, "\n".join(prose_lines))

    return units


def _add_prose_unit(units: list[dict], text: str) -> None:
    """添加散文单元，过长时按句子边界拆分"""
    text = text.strip()
    if not text:
        return
    # 上限以内整块保留，只有极端长段落才按句子拆分
    if len(text) <= _PROSE_UNIT_MAX_CHARS:
        units.append({"text": text, "is_code": False, "is_qa": False})
    else:
        # 按句子边界拆分
        sentences = _split_sentences(text)
        buf: list[str] = []
        buf_len = 0
        for sent in sentences:
            if buf and buf_len + len(sent) > _PROSE_UNIT_MAX_CHARS:
                units.append({"text": " ".join(buf), "is_code": False, "is_qa": False})
                buf = []
                buf_len = 0
            buf.append(sent)
            buf_len += len(sent)
        if buf:
            units.append({"text": " ".join(buf), "is_code": False, "is_qa": False})


def _split_sentences(text: str) -> list[str]:
    """按中英文句子终结标点切分，保留标点"""
    parts = re.split(r"([。！？；.!?;])", text)
    sentences: list[str] = []
    buf = ""
    for part in parts:
        buf += part
        if part in ("。", "！", "？", "；", ".", "!", "?", ";"):
            sentences.append(buf)
            buf = ""
    if buf.strip():
        sentences.append(buf)
    return sentences


def _render_units(units: list[dict]) -> str:
    return "\n\n".join(unit["text"] for unit in units if unit["text"].strip())


def _build_overlap_units(units: list[dict], chunk_overlap: int) -> list[dict]:
    """从 chunk 尾部选取最多 chunk_overlap 字符作为 overlap。
    按原始顺序返回（尾部在前），供下一个 chunk 前置拼接。"""
    if chunk_overlap <= 0:
        return []
    overlap: list[dict] = []
    total = 0
    for unit in reversed(units):
        if (
            unit.get("is_code")
            or unit.get("is_qa")
            or unit.get("is_table")
            or unit.get("is_formula")
        ):
            break
        unit_len = len(unit["text"])
        if total + unit_len > chunk_overlap:
            break
        overlap.insert(0, unit)
        total += unit_len
    return [
        {"text": u["text"], "is_code": u.get("is_code", False), "is_qa": u.get("is_qa", False)}
        for u in overlap
    ]
