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
_MD_TABLE_RE = re.compile(r"(?m)(?:^\|.+\|$\n?)+")
_LATEX_BLOCK_RE = re.compile(r"(?ms)\$\$.+?\$\$")


def _unit(
    text: str,
    *,
    code: bool = False,
    qa: bool = False,
    table: bool = False,
    formula: bool = False,
) -> dict:
    """构造语义单元 dict（键顺序与拆分前逐字一致）。"""
    return {"text": text, "is_code": code, "is_qa": qa, "is_table": table, "is_formula": formula}


def _stash_blocks(pattern: re.Pattern, text: str, tag: str) -> tuple[str, list[str]]:
    """把 pattern 命中的块抽成占位符 `__<tag>_BLOCK_N__`，返回 (替换后文本, 块列表)。"""
    blocks: list[str] = []

    def _repl(m: re.Match) -> str:
        blocks.append(m.group(0).strip())
        return f"\n__{tag}_BLOCK_{len(blocks) - 1}__\n"

    return pattern.sub(_repl, text), blocks


def _restore_placeholder_unit(block: str, prefix: str, blocks: list[str], flag: str) -> dict | None:
    """block 为 `<prefix>N__` 且下标可解析 → 还原为标 `flag` 的原子 unit；否则 None。"""
    if not (block.startswith(prefix) and block.endswith("__")):
        return None
    m = re.search(re.escape(prefix) + r"(\d+)__", block)
    if not m:
        return None
    return {
        "text": blocks[int(m.group(1))],
        "is_code": flag == "code",
        "is_qa": flag == "qa",
        "is_table": flag == "table",
        "is_formula": flag == "formula",
    }


def _add_line_group_units(units: list[dict], block: str) -> None:
    """列表项组：连续列表行合并为一个 unit；散文行交给 `_add_prose_unit`。"""
    list_lines: list[str] = []
    prose_lines: list[str] = []
    for line in block.splitlines():
        if _LIST_ITEM_RE.match(line):
            if prose_lines:
                _add_prose_unit(units, "\n".join(prose_lines))
                prose_lines = []
            list_lines.append(line)
        else:
            if list_lines:
                units.append(_unit("\n".join(list_lines)))
                list_lines = []
            prose_lines.append(line)
    if list_lines:
        units.append(_unit("\n".join(list_lines)))
    if prose_lines:
        _add_prose_unit(units, "\n".join(prose_lines))


def _parse_semantic_units(text: str) -> list[dict]:
    """将文本解析为语义单元（段落 / 列表项组 / 代码块 / Q&A 对 / 表格 / 公式块）

    代码块、表格、公式、Q&A 对为原子单元**不可拆分**；连续列表行合并为一个单元；
    空行分隔的段落为一个单元，单个过长段落按句子边界再拆。

    Returns:
        [{"text": str, "is_code": bool, "is_qa": bool, "is_table": bool, "is_formula": bool}, ...]
    """
    # 1-3. 提取代码块 / 表格 / 公式为占位符（原子单元，逐块整块还原）
    text_no_code, code_blocks = _stash_blocks(_FENCED_CODE_BLOCK_RE, text, "CODE")
    text_no_table, table_blocks = _stash_blocks(_MD_TABLE_RE, text_no_code, "TABLE")
    text_no_formula, formula_blocks = _stash_blocks(_LATEX_BLOCK_RE, text_no_table, "FORMULA")

    # 4. 预扫描：把 Q&A 合并为原子块
    text_with_qa = _merge_qa_blockquotes(text_no_formula)

    # 5. 按空行切分为文本块，逐块还原
    units: list[dict] = []
    for block in re.split(r"\n{2,}", text_with_qa.strip()):
        block = block.strip()
        if not block:
            continue

        restored = (
            _restore_placeholder_unit(block, "__CODE_BLOCK_", code_blocks, "code")
            or _restore_placeholder_unit(block, "__TABLE_BLOCK_", table_blocks, "table")
            or _restore_placeholder_unit(block, "__FORMULA_BLOCK_", formula_blocks, "formula")
        )
        if restored is not None:
            units.append(restored)
        elif block.startswith("__QA_PAIR_START__"):
            # Q&A 原子单元（已被 _merge_qa_blockquotes 标记）
            inner = block[len("__QA_PAIR_START__") :].strip()
            units.append(_unit(_restore_code_placeholders(inner, code_blocks), qa=True))
        else:
            _add_line_group_units(units, block)

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
