"""自动拆分自 cleaner.py（行为等价）。"""

from __future__ import annotations

import re
from collections import Counter

from langchain_core.documents import Document

from rag.chunking.cleaner._log import logger
from rag.chunking.cleaner._text import (
    _LINE_TRIM_RE,
    _MULTI_NEWLINE_RE,
    _PAGE_NUM_RE,
    _finalize_whitespace,
    _normalize_text,
)

# PDF 页眉页脚：短行（<40字）且出现在文档开头/结尾的重复行
_SHORT_LINE_RE = re.compile(r"^[^\n]{1,40}$", re.MULTILINE)

# ── PDF 断行修复 ──────────────────────────────────
# 句子终结标点（行尾出现这些说明是自然断行，不需要合并）
_SENT_END_PUNCTS = set("。！？；：…—.!?;:")

# 行首大写/章节标记（说明是新段落开头，不与前一行合并）
_LINE_START_NEW_PARA_RE = re.compile(
    r"^(?:"
    r"[A-Z]"  # 英文大写开头
    r"|第[一二三四五六七八九十百千零\d]+[章节篇部]"  # 章节标记
    r"|[一二三四五六七八九十]+[、.]"  # 中文序号
    r"|[\d]+[.)）]"  # 数字编号
    r"|[#\-*>·•◆]"  # Markdown/列表标记
    r")"
)

# 行尾连字符（英文断行 "xxx-\nyyy"）
_HYPHEN_BREAK_RE = re.compile(r"(\w)-\s*\n\s*(\w)")

# ── PDF 多栏检测 ──────────────────────────────────
# 多栏特征：大量短行（行宽 < 阈值）连续出现
# 假设正常单栏行宽 > 40 字符，双栏行宽通常 20-40 字符
_COLUMN_LINE_MAX_WIDTH = 40
# 连续短行数 ≥ 此阈值才判定为多栏区域
_COLUMN_MIN_CONSECUTIVE = 6


def _edge_lines(text: str) -> list[str]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return []
    candidates = lines[:2] + lines[-2:]
    # _SHORT_LINE_RE 的 {1,40} + match 锚定已限死长度，无需再判 len<=40
    return [
        line for line in candidates if _SHORT_LINE_RE.match(line) and not _PAGE_NUM_RE.match(line)
    ]


def _dedupe_pdf_edges(documents: list[Document]) -> dict[str, set[str]]:
    grouped: dict[str, list[Document]] = {}
    for doc in documents:
        grouped.setdefault(_pdf_source_key(doc), []).append(doc)

    repeated: dict[str, set[str]] = {}
    for key, group_docs in grouped.items():
        if len(group_docs) < 2:
            repeated[key] = set()
            continue
        counter = Counter()
        for doc in group_docs:
            counter.update(_edge_lines(_normalize_text(doc.page_content)))
        repeated[key] = {line for line, count in counter.items() if count >= 2}
    return repeated


def _is_cjk_char(char: str) -> bool:
    """单字符是否落在 CJK 统一表意文字区（基本区 + 扩展A）"""
    return "\u4e00" <= char <= "\u9fff" or "\u3400" <= char <= "\u4dbf"


def _can_merge_pdf_lines(current: str, next_stripped: str) -> bool:
    """判断断行的下一行能否并入当前行（判断顺序即优先级，勿调换）"""
    if _LINE_START_NEW_PARA_RE.match(next_stripped):
        return False

    if current and current[-1] in _SENT_END_PUNCTS:
        return False

    # 右括号/引号结尾 → 可能本就是自然断行
    if current and current[-1] in "）)」』\"'":
        return False

    # 左括号/引号开头 → 可能是新内容块
    if next_stripped and next_stripped[0] in "（(「『\"'":
        return False

    return True


def _join_pdf_lines(current: str, next_stripped: str) -> str:
    """合并断行：CJK 相邻直接拼接，否则用空格连接"""
    cur_last_cjk = bool(current) and _is_cjk_char(current[-1])
    next_first_cjk = bool(next_stripped) and _is_cjk_char(next_stripped[0])
    if cur_last_cjk or next_first_cjk:
        return current + next_stripped
    return current + " " + next_stripped


def _repair_pdf_line_breaks(text: str) -> str:
    """修复 PDF 提取导致的断行

    PDF 提取常在句子中间断行，例如：
      "这是一"  →  "这是一个例子。"
      "个例子。"

    合并规则：当前行不以终结标点结尾、且下一行不以新段落标记开头 → 合并；
    英文连字符断行 "word-\\nword" → "wordword"；空行（段落边界）不跨越。
    """
    if not text or not text.strip():
        return text

    text = _HYPHEN_BREAK_RE.sub(r"\1\2", text)

    lines = text.splitlines()
    if len(lines) <= 1:
        return text

    merged: list[str] = []
    i = 0

    while i < len(lines):
        line = lines[i]
        i += 1

        # 空行 → 段落边界，不合并
        if not line.strip():
            merged.append(line)
            continue

        current = line.rstrip()

        while i < len(lines):
            next_line = lines[i]

            # 下一行为空 → 段落边界，停止合并
            if not next_line.strip():
                break

            next_stripped = next_line.strip()
            if not _can_merge_pdf_lines(current, next_stripped):
                break

            current = _join_pdf_lines(current, next_stripped)
            i += 1

        merged.append(current)

    return "\n".join(merged)


def _find_short_line_regions(lines: list[str], is_short: list[bool]) -> list[tuple[int, int]]:
    """找出连续短行区域，返回 (start, end) 闭区间列表"""
    regions: list[tuple[int, int]] = []
    start: int | None = None
    for i, short in enumerate(is_short):
        if short and not lines[i].strip() == "":
            if start is None:
                start = i
            continue
        if start is not None and i - start >= _COLUMN_MIN_CONSECUTIVE:
            regions.append((start, i - 1))
        start = None
    # 处理末尾区域
    if start is not None and len(lines) - start >= _COLUMN_MIN_CONSECUTIVE:
        regions.append((start, len(lines) - 1))
    return regions


def _reorder_pdf_columns(text: str) -> str:
    """检测并修复 PDF 多栏混排导致的文本交叉

    PDF 提取双栏文档时，经常出现左右栏文本交叉：
      左栏第1行  右栏第1行  ← 实际提取为连续行
      左栏第2行  右栏第2行

    做法：找出连续短行区域（行宽 ≤ _COLUMN_LINE_MAX_WIDTH、行数 ≥ _COLUMN_MIN_CONSECUTIVE），
    按奇偶分成左右栏重排，且只在 `_check_column_coherence` 判定栏内连贯性显著更高时才采用。

    启发式方法，可能误判 ⇒ 保守策略：只在高置信度时重排。
    """
    if not text or not text.strip():
        return text

    lines = text.splitlines()
    if len(lines) < _COLUMN_MIN_CONSECUTIVE:
        return text

    is_short = [
        bool(line.strip()) and len(line.strip()) <= _COLUMN_LINE_MAX_WIDTH for line in lines
    ]

    regions = _find_short_line_regions(lines, is_short)
    if not regions:
        return text

    result_lines = list(lines)

    for region_start, region_end in regions:
        region_lines = [lines[i] for i in range(region_start, region_end + 1) if lines[i].strip()]

        if len(region_lines) < _COLUMN_MIN_CONSECUTIVE:
            continue

        left_col = [region_lines[i] for i in range(0, len(region_lines), 2)]
        right_col = [region_lines[i] for i in range(1, len(region_lines), 2)]

        if not _check_column_coherence(left_col, right_col, region_lines):
            continue

        reordered = left_col + [""] + right_col  # 用空行分隔左右栏
        result_lines[region_start : region_end + 1] = reordered + [""] * (
            (region_end - region_start + 1) - len(reordered)
        )
        logger.debug(
            "PDF column reorder: region lines %d-%d (%d lines → L%d + R%d)",
            region_start,
            region_end,
            len(region_lines),
            len(left_col),
            len(right_col),
        )

    result = "\n".join(result_lines)
    result = _MULTI_NEWLINE_RE.sub("\n\n", result)
    return result


def _check_column_coherence(
    left_col: list[str],
    right_col: list[str],
    original: list[str],
) -> bool:
    """验证奇偶重排是否比原始顺序更连贯

    用字符级 bigram 重叠率比较「栏内相邻行」与「原始交替相邻行」，前者显著更高才重排。
    """

    def _adjacent_coherence(lines: list[str]) -> float:
        """计算相邻行对（lines[i] 与 lines[i+1]）的平均字符重叠率"""
        if len(lines) < 2:
            return 0.0
        overlaps = []
        for a, b in zip(lines, lines[1:]):
            if not a or not b:
                overlaps.append(0.0)
                continue
            # 用字符级 bigram 集合计算重叠
            bigrams_a = {a[i : i + 2] for i in range(len(a) - 1)}
            bigrams_b = {b[i : i + 2] for i in range(len(b) - 1)}
            if not bigrams_a or not bigrams_b:
                overlaps.append(0.0)
                continue
            overlap = len(bigrams_a & bigrams_b) / min(len(bigrams_a), len(bigrams_b))
            overlaps.append(overlap)
        return sum(overlaps) / len(overlaps) if overlaps else 0.0

    original_coherence = _adjacent_coherence(original)
    left_coherence = _adjacent_coherence(left_col)
    right_coherence = _adjacent_coherence(right_col)
    column_coherence = (left_coherence + right_coherence) / 2

    # 重排有效条件：分栏连贯性显著高于原始（1.5x 阈值，避免误判）
    return column_coherence > original_coherence * 1.5 and column_coherence > 0.05


def _clean_pdf_text(text: str, repeated_edges: set[str]) -> str:
    normalized = _normalize_text(text)
    if not normalized:
        return ""
    # 页眉页脚移除
    lines = normalized.splitlines()
    while lines and lines[0].strip() in repeated_edges:
        lines.pop(0)
    while lines and lines[-1].strip() in repeated_edges:
        lines.pop()
    cleaned_lines = [_LINE_TRIM_RE.sub("", line) for line in lines]
    cleaned = "\n".join(cleaned_lines)
    cleaned = _PAGE_NUM_RE.sub("", cleaned)
    # 多栏重排必须排在断行修复之前：断行修复会改变行结构
    cleaned = _reorder_pdf_columns(cleaned)
    cleaned = _repair_pdf_line_breaks(cleaned)
    return _finalize_whitespace(cleaned)


def _pdf_source_key(doc: Document) -> str:
    """PDF 页边重复行去重的分组键（_dedupe_pdf_edges 与 pdf 分派共用这一份规则）"""
    return str(doc.metadata.get("source_path") or doc.metadata.get("source_file") or id(doc))
