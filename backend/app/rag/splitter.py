import json
import logging
import re

from langchain_core.documents import Document
from app.rag.metrics import metrics

logger = logging.getLogger(__name__)

MIN_CHUNK_LENGTH = 80

# ── Adaptive chunk_size 映射 ──
# 根据 content_type 选择 chunk_size，0 表示不拆分（整块保留）
_ADAPTIVE_CHUNK_SIZE: dict[str, int] = {
    "section": 800,
    "text": 800,
    "list": 0,        # 不拆
    "code_mixed": 400,
    "exercise": 600,
    "answer": 600,
    "merged_qa": 0,   # 不拆（题+答原子单元）
    "table": 0,       # 不拆（表格原子保留）
    "formula": 0,     # 不拆（公式块原子保留）
}
_ADAPTIVE_CHUNK_OVERLAP: dict[str, int] = {
    "section": 150,
    "text": 150,
    "list": 0,
    "code_mixed": 100,
    "exercise": 100,
    "answer": 100,
    "merged_qa": 0,
    "table": 0,
    "formula": 0,
}

# 硬上限：任何 chunk 不超过此长度（超长单元按句子拆分）
_CHUNK_HARD_LIMIT = 1600
# QA 软上限：只用于多题合并时的题目边界分组，不拆单题
_QA_CHUNK_SOFT_LIMIT = 3000
# 过短阈值：低于此长度的 chunk 尝试与邻居合并
_CHUNK_MIN_EFFECTIVE = 80
_PARENT_WINDOW_CHAR_BUDGET = 4200


def _resolve_chunk_params(content_type: str) -> tuple[int, int]:
    """根据内容类型返回 (chunk_size, chunk_overlap)"""
    size = _ADAPTIVE_CHUNK_SIZE.get(content_type, 800)
    overlap = _ADAPTIVE_CHUNK_OVERLAP.get(content_type, 150)
    return size, overlap


# Markdown 标题正则：# 标题 / ## 标题 / ### 标题
_HEADING_RE = re.compile(r"^(#{1,4})\s+(.+)$", re.MULTILINE)
_FENCED_CODE_BLOCK_RE = re.compile(r"(?ms)^[ \t]{0,3}(```+|~~~+)[^\n]*\n.*?^[ \t]{0,3}\1[ \t]*$")


def _percentile(values: list[int], ratio: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int(round((len(ordered) - 1) * ratio))))
    return float(ordered[index])


def _is_sentence_complete(text: str) -> bool:
    """判断文本是否在语义完整的位置结束

    完整结束包括：
    - 句末标点（。！？.!?;：…）
    - Markdown 列表项（- 或 数字. 开头的行）
    - Markdown 标题行（# 开头的行）
    - 加粗/强调结尾（**）
    - 代码块结尾（```）
    - 右括号/右引号结尾
    """
    stripped = text.rstrip()
    if not stripped:
        return True
    # 句末标点
    if stripped.endswith(("。", "！", "？", ".", "!", "?", ":", "：", "；", ";", "…", "”", "'", "\"")):
        return True
    # Markdown 结构
    if stripped.endswith("```"):
        return True
    if stripped.endswith("**"):
        return True
    # 列表项行（最后一行是列表项）
    last_line = stripped.splitlines()[-1].strip() if stripped.splitlines() else ""
    if re.match(r"^(?:[-*+]|\d+[.．])\s+", last_line):
        return True
    # 标题行
    if re.match(r"^#{1,4}\s+", last_line):
        return True
    # 右括号结尾
    if stripped.endswith(("）", ")", "】", "]", "》", "}", ">")):
        return True
    # Markdown 表格行
    if stripped.endswith("|"):
        return True
    # Markdown 引用块
    if stripped.endswith(">"):
        return True
    # 加粗文本结尾
    if stripped.endswith(("**", "__")):
        return True
    return False


def _extract_headings(text: str) -> list[dict]:
    return [
        {
            "level": len(match.group(1)),
            "title": match.group(2).strip(),
            "start": match.start(),
            "end": match.end(),
        }
        for match in _HEADING_RE.finditer(text)
    ]


def _build_heading_context(headings: list[dict], position: int) -> str:
    active: dict[int, str] = {}
    for item in headings[: position + 1]:
        level = item["level"]
        title = item["title"]
        if level <= 4:
            active = {k: v for k, v in active.items() if k < level}
            active[level] = title

    if not active:
        return ""

    path = " > ".join(active[k] for k in sorted(active.keys()))
    return f"[{path}]"


def _split_into_sections(text: str, headings: list[dict]) -> list[dict]:
    if not headings:
        return [{"text": text, "heading": "", "heading_level": 0, "heading_path": "", "section_index": 0}]

    sections: list[dict] = []
    first_heading_start = headings[0]["start"]
    if text[:first_heading_start].strip():
        sections.append(
            {
                "text": text[:first_heading_start].strip(),
                "heading": "",
                "heading_level": 0,
                "heading_path": "",
                "section_index": 0,
            }
        )

    for index, heading in enumerate(headings):
        next_start = headings[index + 1]["start"] if index + 1 < len(headings) else len(text)
        section_text = text[heading["start"]:next_start].strip()
        if not section_text:
            continue
        sections.append(
            {
                "text": section_text,
                "heading": heading["title"],
                "heading_level": heading["level"],
                "heading_path": _build_heading_context(headings, index),
                "section_index": len(sections),
            }
        )
    return sections


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


# ── 结构化分块：语义单元解析 ────────────────────────

# 列表项正则：- 开头 或 数字. 开头
_LIST_ITEM_RE = re.compile(r"^(?:[-*+]|\d+[.．])\s+", re.MULTILINE)

# ── Q&A 单元识别正则 ──────────────────────────────────
# 例题模式：> 例题 / > 例N / > 例1：
_EXAMPLE_Q_RE = re.compile(r"^>\s*(?:例[题\d]|例\d+[：:])", re.MULTILINE)
# 答案模式：答案： / 正确答案： / 正确答案选择 X
_ANSWER_RE = re.compile(r"答案[：:；;]|正确答案[：:]", re.MULTILINE)
# 答案字母提取：正确答案：D / 答案：B
_ANSWER_KEY_RE = re.compile(r"(?:正确答案|答案)[：:；;]\s*([A-E])")
# 真题模式：##### N (纯数字标题)
_EXAM_Q_HEADING_RE = re.compile(r"^#{4,5}\s*\d+\s*$", re.MULTILINE)


def _merge_qa_blockquotes(text: str) -> str:
    """预扫描文本，将 Q&A 模式合并为原子块

    识别两种模式：
    1. 例题模式：> 例题/例N 开头，到 答案：/正确答案： 结束的 blockquote 区域
    2. 真题模式：##### N 标题行 + 题干 + 正确答案：X + 解析，到下一个 ##### N 或文件结束

    合并后的块以 __QA_PAIR_START__ 标记，后续 _parse_semantic_units 会将其识别为原子单元。
    """
    lines = text.splitlines()
    result_lines: list[str] = []
    qa_buffer: list[str] = []
    in_qa = False
    qa_source = ""  # "example" or "exam"

    for line in lines:
        stripped = line.strip()

        # ── 检测例题开头 ──
        if _EXAMPLE_Q_RE.match(line):
            # 如果之前有未关闭的 QA buffer，先输出
            if in_qa and qa_buffer:
                result_lines.append("__QA_PAIR_START__" + "\n".join(qa_buffer))
                qa_buffer = []
            in_qa = True
            qa_source = "example"
            qa_buffer.append(line)
            continue

        # ── 检测真题开头（##### N 纯数字标题） ──
        if _EXAM_Q_HEADING_RE.match(stripped):
            # 如果之前有未关闭的 QA buffer，先输出
            if in_qa and qa_buffer:
                result_lines.append("__QA_PAIR_START__" + "\n".join(qa_buffer))
                qa_buffer = []
            in_qa = True
            qa_source = "exam"
            qa_buffer.append(line)
            continue

        if in_qa:
            if qa_source == "example":
                # 例题模式：收集 blockquote 行和答案行
                if stripped.startswith(">") or _ANSWER_RE.search(stripped):
                    qa_buffer.append(line)
                    continue
                else:
                    # 非引用行出现，关闭当前 QA 块
                    result_lines.append("__QA_PAIR_START__" + "\n".join(qa_buffer))
                    qa_buffer = []
                    in_qa = False
                    result_lines.append(line)
                    continue
            elif qa_source == "exam":
                # 真题模式：收集所有行直到下一个 ##### N 或空行后的非连续内容
                # 策略：只要出现 答案标记 就继续收集（含解析部分）
                qa_buffer.append(line)
                # 如果遇到空行且之前已有答案标记，检查下一行是否是新 ##### N
                # 这里简单处理：答案标记出现后，遇到连续空行或新标题则关闭
                if _ANSWER_RE.search(stripped):
                    # 标记答案已出现，后续行仍收集直到新 ##### N
                    continue
                continue

        else:
            result_lines.append(line)

    # 处理未关闭的 QA buffer
    if in_qa and qa_buffer:
        result_lines.append("__QA_PAIR_START__" + "\n".join(qa_buffer))

    return "\n".join(result_lines)


def _restore_code_placeholders(text: str, code_blocks: list[str]) -> str:
    """将代码块占位符还原为实际代码"""
    def _restore(m: re.Match) -> str:
        idx = int(m.group(1))
        if 0 <= idx < len(code_blocks):
            return code_blocks[idx]
        return m.group(0)
    return re.sub(r"__CODE_BLOCK_(\d+)__", _restore, text)


def _extract_qa_fields(text: str) -> dict:
    """从 Q&A 文本中提取结构化字段

    Returns:
        {
            "question": str,    # 题干部分（答案之前的文本）
            "answer": str,      # 答案+解析部分（从答案标记开始）
            "answer_key": str,  # 正确答案字母（A/B/C/D/E），可能为空
        }
    """
    # 提取答案字母
    key_match = _ANSWER_KEY_RE.search(text)
    answer_key = key_match.group(1) if key_match else ""

    # 按答案标记分割题目和答案
    answer_match = _ANSWER_RE.search(text)
    if answer_match:
        question = text[:answer_match.start()].strip()
        answer = text[answer_match.start():].strip()
    else:
        question = text.strip()
        answer = ""

    # 清理 question 中的 blockquote 标记和多余前缀
    question = re.sub(r"^>\s*", "", question, flags=re.MULTILINE)
    question = re.sub(r"^例[题\d]+[：:]?\s*", "", question, count=1)
    # 清理真题标题前缀（##### N）
    question = re.sub(r"^#{4,5}\s*\d+\s*\n?", "", question, count=1)
    question = question.strip()

    # 清理 answer 中的前缀
    answer = re.sub(r"^(?:正确)?答案[：:；;]\s*", "", answer, count=1)
    answer = answer.strip()

    return {
        "question": question,
        "answer": answer,
        "answer_key": answer_key,
    }


def _parse_semantic_units(text: str) -> list[dict]:
    """将文本解析为语义单元（段落 / 列表项组 / 代码块 / Q&A 对 / 表格 / 公式块）

    结构化分块的核心：
    1. 代码块整体保留
    2. Q&A 对（例题+答案）合并为原子单元，不可拆分
    3. Markdown 表格整体保留，不可拆分
    4. LaTeX 公式块整体保留，不可拆分
    5. 列表项组（连续的 - 或 数字. 行）合并为一个单元
    6. 段落（空行分隔的文本块）作为一个单元
    7. 单个段落过长时，按句子边界拆分

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

    # 2. 提取 Markdown 表格，替换为占位符（表格原子保留，不拆分）
    _MD_TABLE_RE = re.compile(r"(?m)(?:^\|.+\|$\n?)+")
    table_blocks: list[str] = []
    def _table_placeholder(m: re.Match) -> str:
        table_blocks.append(m.group(0).strip())
        return f"\n__TABLE_BLOCK_{len(table_blocks) - 1}__\n"
    text_no_table = _MD_TABLE_RE.sub(_table_placeholder, text_no_code)

    # 3. 提取 LaTeX 公式块，替换为占位符（公式原子保留，不拆分）
    _LATEX_BLOCK_RE = re.compile(r"(?ms)\$\$.+?\$\$")
    formula_blocks: list[str] = []
    def _formula_placeholder(m: re.Match) -> str:
        formula_blocks.append(m.group(0).strip())
        return f"\n__FORMULA_BLOCK_{len(formula_blocks) - 1}__\n"
    text_no_formula = _LATEX_BLOCK_RE.sub(_formula_placeholder, text_no_table)

    # 4. 预扫描：检测 Q&A 模式，将连续的 blockquote 行合并为 Q&A 块
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
                units.append({"text": code_blocks[int(idx_match.group(1))], "is_code": True, "is_qa": False, "is_table": False, "is_formula": False})
                continue

        # 表格占位符还原（原子保留）
        if block.startswith("__TABLE_BLOCK_") and block.endswith("__"):
            idx_match = re.search(r"__TABLE_BLOCK_(\d+)__", block)
            if idx_match:
                units.append({"text": table_blocks[int(idx_match.group(1))], "is_code": False, "is_qa": False, "is_table": True, "is_formula": False})
                continue

        # 公式块占位符还原（原子保留）
        if block.startswith("__FORMULA_BLOCK_") and block.endswith("__"):
            idx_match = re.search(r"__FORMULA_BLOCK_(\d+)__", block)
            if idx_match:
                units.append({"text": formula_blocks[int(idx_match.group(1))], "is_code": False, "is_qa": False, "is_table": False, "is_formula": True})
                continue

        # Q&A 原子单元（已被 _merge_qa_blockquotes 标记）
        if block.startswith("__QA_PAIR_START__"):
            inner = block[len("__QA_PAIR_START__"):].strip()
            inner = _restore_code_placeholders(inner, code_blocks)
            units.append({"text": inner, "is_code": False, "is_qa": True, "is_table": False, "is_formula": False})
            continue

        # 列表项组：连续的列表行合并为一个单元
        lines = block.splitlines()
        list_lines: list[str] = []
        prose_lines: list[str] = []

        for line in lines:
            if _LIST_ITEM_RE.match(line):
                # 如果前面有散文行，先保存散文单元
                if prose_lines:
                    _add_prose_unit(units, "\n".join(prose_lines))
                    prose_lines = []
                list_lines.append(line)
            else:
                # 如果前面有列表行，先保存列表单元
                if list_lines:
                    units.append({"text": "\n".join(list_lines), "is_code": False, "is_qa": False, "is_table": False, "is_formula": False})
                    list_lines = []
                prose_lines.append(line)

        # 处理剩余
        if list_lines:
            units.append({"text": "\n".join(list_lines), "is_code": False, "is_qa": False, "is_table": False, "is_formula": False})
        if prose_lines:
            _add_prose_unit(units, "\n".join(prose_lines))

    return units


def _add_prose_unit(units: list[dict], text: str) -> None:
    """添加散文单元，过长时按句子边界拆分"""
    text = text.strip()
    if not text:
        return
    # 单个文本块不超过 chunk_size 的大部分情况，直接作为一个单元
    # 只有极端长段落才按句子拆分
    if len(text) <= 1200:
        units.append({"text": text, "is_code": False, "is_qa": False})
    else:
        # 按句子边界拆分
        sentences = _split_sentences(text)
        buf: list[str] = []
        buf_len = 0
        for sent in sentences:
            if buf and buf_len + len(sent) > 1200:
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


# _parse_semantic_units is called directly; wrapper removed for clarity


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
        if unit.get("is_code") or unit.get("is_qa") or unit.get("is_table") or unit.get("is_formula"):
            break
        unit_len = len(unit["text"])
        if total + unit_len > chunk_overlap:
            break
        overlap.insert(0, unit)  # prepend to preserve original order
        total += unit_len
    return [{"text": u["text"], "is_code": u.get("is_code", False), "is_qa": u.get("is_qa", False)} for u in overlap]


def _split_section_text(
    text: str,
    chunk_size: int = 800,
    chunk_overlap: int = 200,
) -> list[dict]:
    """结构化分块：按语义单元贪心合并，强制句子完整边界

    策略：
    1. 解析文本为语义单元（段落/列表项组/代码块/Q&A 对/表格/公式/句子）
    2. Q&A / 表格 / 公式 为原子单元，不可拆分，不可与其它单元合并
    3. 贪心合并：依次加入单元，直到接近 chunk_size
    4. 超出时输出当前 chunk，确保句子完整边界
    5. 超长单元按句子拆分，不超过 _CHUNK_HARD_LIMIT
    6. overlap 回溯优先同 section 尾部单元

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
            # 原子单元单独输出
            if is_qa:
                qa_fields = _extract_qa_fields(unit_text)
                chunks.append({"text": unit_text, "is_qa": True, "qa_fields": qa_fields})
            else:
                chunks.append({"text": unit_text, "is_qa": False, "qa_fields": None})
            continue

        # 超长单元：按句子拆分，不超过硬上限
        if len(unit_text) > _CHUNK_HARD_LIMIT:
            if current_units:
                _flush_chunk(chunks, current_units, chunk_size)
                current_units = []
            for sub in _split_oversized(unit_text, _CHUNK_HARD_LIMIT):
                chunks.append({"text": sub, "is_qa": False, "qa_fields": None})
            continue

        # 尝试加入当前 chunk
        candidate = [*current_units, unit]
        candidate_text = _render_units(candidate)

        if len(candidate_text) <= chunk_size:
            current_units.append(unit)
            continue

        # 超出：输出当前 chunk（确保句子完整）
        flushed_units = list(current_units)  # 保存用于 overlap
        if current_units:
            _flush_chunk(chunks, current_units, chunk_size)
            current_units = []

        # overlap 回溯（同 section 尾部优先）
        overlap_units = _build_overlap_units(flushed_units, chunk_overlap)
        if overlap_units and len(_render_units([*overlap_units, unit])) > chunk_size:
            overlap_units = []

        current_units = [*overlap_units, unit]

    # 输出剩余
    if current_units:
        _flush_chunk(chunks, current_units, chunk_size)

    # 后处理：合并过短 chunk
    chunks = _merge_short_chunks(chunks, _CHUNK_MIN_EFFECTIVE, chunk_size)

    return chunks


def _flush_chunk(chunks: list[dict], units: list[dict], chunk_size: int) -> None:
    """输出当前 chunk，确保句子完整边界

    如果最后一个单元的文本不在句子完整位置结束，
    尝试回退到上一个完整边界，避免句中截断。

    """
    if not units:
        return
    text = _render_units(units)
    if not text.strip():
        return

    # 检查是否句子完整
    if _is_sentence_complete(text):
        chunks.append({"text": text, "is_qa": False, "qa_fields": None})
        return

    # 不完整：尝试从后向前找到完整边界
    remaining = list(units)
    tail_units: list[dict] = []
    while remaining and not _is_sentence_complete(_render_units(remaining)):
        tail_units.insert(0, remaining.pop())

    if remaining:
        # 前部分完整，输出
        chunks.append({"text": _render_units(remaining), "is_qa": False, "qa_fields": None})
        if tail_units:
            tail_text = _render_units(tail_units)
            if len(tail_text.strip()) >= MIN_CHUNK_LENGTH:
                chunks.append({"text": tail_text, "is_qa": False, "qa_fields": None})
    else:
        # 无法找到完整边界，整体输出（兜底）
        chunks.append({"text": text, "is_qa": False, "qa_fields": None})


def _split_qa_oversized(text: str, limit: int) -> list[str]:
    """将超长 QA 块按题目边界拆分，每段不超过 limit

    识别两种题目边界：
    1. 真题模式：##### N 标题行
    2. 例题模式：> 例题/例N 开头

    每个题目+答案保持原子性，不跨题拆分。
    """
    # 按真题标题拆分
    parts = re.split(r"(?=^#{4,5}\s*\d+\s*$)", text, flags=re.MULTILINE)
    if len(parts) > 1:
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

    # 按例题标记拆分
    parts = re.split(r"(?=>\s*例[题\d])", text)
    if len(parts) > 1:
        result = []
        buf = []
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

    # 无法按题目边界拆分，整体保留，避免破坏题干-答案-解析原子性
    return [text.strip()] if text.strip() else []


def _split_oversized(text: str, limit: int) -> list[str]:
    """将超长文本按句子边界拆分，每段不超过 limit"""
    sentences = _split_sentences(text)
    result: list[str] = []
    buf: list[str] = []
    buf_len = 0
    for sent in sentences:
        if buf and buf_len + len(sent) > limit:
            result.append(" ".join(buf))
            buf = []
            buf_len = 0
        buf.append(sent)
        buf_len += len(sent)
    if buf:
        result.append(" ".join(buf))
    # 单句超 limit 的兜底
    return [r for r in result if r.strip()]


def _merge_short_chunks(chunks: list[dict], min_len: int, max_len: int) -> list[dict]:
    """后处理：将过短 chunk 与邻居合并"""
    if not chunks:
        return chunks
    merged: list[dict] = [dict(chunks[0])]
    for chunk in chunks[1:]:
        prev = merged[-1]
        prev_text = prev["text"]
        cur_text = chunk["text"]
        # 前一个过短 且 合并不超限 且 都不是 QA
        if (len(prev_text) < min_len
                and len(prev_text) + len(cur_text) + 2 <= max_len
                and not prev.get("is_qa") and not chunk.get("is_qa")):
            prev["text"] = prev_text + "\n\n" + cur_text
        else:
            merged.append(dict(chunk))
    return merged


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
    depth = _compute_section_depth(heading_level)

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

    # ── Q&A 字段（merged_qa 角色专用，存储合并检索分离） ──
    if chunk_role == "merged_qa":
        qa_fields = chunk.metadata.pop("_qa_fields", None)
        if qa_fields:
            chunk.metadata["qa.question"] = qa_fields.get("question", "")
            chunk.metadata["qa.answer"] = qa_fields.get("answer", "")
            chunk.metadata["qa.answer_key"] = qa_fields.get("answer_key", "")

    # ── 旧字段兼容（不删除，保证下游代码不 break） ──
    chunk.metadata["chunk_id"] = chunk_id
    chunk.metadata["heading"] = section["heading_path"]
    chunk.metadata["heading_title"] = section["heading"]
    chunk.metadata["heading_level"] = heading_level
    chunk.metadata["heading_path"] = section["heading_path"]
    chunk.metadata["section_index"] = section["section_index"]
    chunk.metadata["chunk_index"] = global_index
    chunk.metadata["chunk_index_in_section"] = local_index
    chunk.metadata["char_count"] = len(chunk.page_content)


def split_documents(
    documents: list[Document],
    chunk_size: int = 400,
    chunk_overlap: int = 100,
) -> list[Document]:
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
            rank = siblings.index(i)  # position in sibling list
            section_sibling_indices.append(rank)
            section_sibling_counts.append(len(siblings))

        # ── 切分 chunk ──
        from app.rag.rag_utils import detect_content_type as _detect_content_type

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

            # ── 真题/练习题 Q&A 检测 ──
            # 若 section 内含 "正确答案" 或 "答案：" 标记，且 heading 是纯数字（真题模式）
            # 或 heading 含 "题"/"例题"，则整个 section 视为 merged_qa
            section_text = section["text"]
            has_answer_marker = bool(_ANSWER_RE.search(section_text))
            heading_is_exam = bool(_EXAM_Q_HEADING_RE.match(section["heading"]))
            heading_is_exercise = any(kw in section["heading"] for kw in ("题", "例题", "习题", "练习"))
            if has_answer_marker and (heading_is_exam or heading_is_exercise or content_type in ("exercise", "answer")):
                content_type = "merged_qa"

            adaptive_size, adaptive_overlap = _resolve_chunk_params(content_type)

            # 生成 detail / merged_qa chunk
            # adaptive_size=0 表示原子结构不在通用切分器中拆分；
            # 真题整卷的拆分由下方 merged_qa fallback 按题号处理。
            effective_size = min(adaptive_size, _CHUNK_HARD_LIMIT) if adaptive_size > 0 else 999999
            section_chunks = _split_section_text(
                section["text"], effective_size, adaptive_overlap
            )
            detail_chunks: list[tuple[Document, str]] = []

            # 若 content_type 是 merged_qa 但 _split_section_text 未产出 is_qa 块
            # （真题模式：无 blockquote，整个 section 就是一个 Q&A 对），强制整体输出
            has_qa_chunk = any(
                (sc.get("is_qa", False) if isinstance(sc, dict) else False)
                for sc in section_chunks
            )
            if content_type == "merged_qa" and not has_qa_chunk and section_text.strip():
                # 超长 merged_qa section：按题目边界拆分，但不拆单题内部题干/答案/解析
                if len(section_text) > _QA_CHUNK_SOFT_LIMIT:
                    for sub in _split_qa_oversized(section_text, _QA_CHUNK_SOFT_LIMIT):
                        sub = sub.strip()
                        if len(sub) < MIN_CHUNK_LENGTH:
                            continue
                        qa_fields = _extract_qa_fields(sub)
                        chunk = _make_chunk(doc.metadata, sub)
                        if section["heading_path"] and not chunk.page_content.startswith(section["heading_path"]):
                            chunk.page_content = f"{section['heading_path']}\n{chunk.page_content}"
                        chunk.metadata["_qa_fields"] = qa_fields
                        detail_chunks.append((chunk, "merged_qa"))
                else:
                    qa_fields = _extract_qa_fields(section_text)
                    chunk = _make_chunk(doc.metadata, section_text.strip())
                    if section["heading_path"] and not chunk.page_content.startswith(section["heading_path"]):
                        chunk.page_content = f"{section['heading_path']}\n{chunk.page_content}"
                    chunk.metadata["_qa_fields"] = qa_fields
                    detail_chunks.append((chunk, "merged_qa"))
            else:
                for sc in section_chunks:
                    chunk_text = sc["text"].strip() if isinstance(sc, dict) else sc.strip()
                    if len(chunk_text) < MIN_CHUNK_LENGTH:
                        continue
                    is_qa = sc.get("is_qa", False) if isinstance(sc, dict) else False
                    qa_fields = sc.get("qa_fields") if isinstance(sc, dict) else None
                    chunk = _make_chunk(doc.metadata, chunk_text)
                    if section["heading_path"] and not chunk.page_content.startswith(section["heading_path"]):
                        chunk.page_content = f"{section['heading_path']}\n{chunk.page_content}"
                    # 临时存储 qa_fields，后续 _append_chunk_metadata 会消费
                    if is_qa and qa_fields:
                        chunk.metadata["_qa_fields"] = qa_fields
                    chunk_role = "merged_qa" if is_qa else "detail"
                    detail_chunks.append((chunk, chunk_role))

            chunk_count = len(detail_chunks)
            parent_windows = [
                _build_parent_window_text(detail_chunks, ci)
                for ci in range(chunk_count)
            ]

            for ci, (chunk, chunk_role) in enumerate(detail_chunks):
                _append_chunk_metadata(
                    chunk, section, sid, parent_id, child_ids,
                    len(valid_chunks), ci, chunk_role=chunk_role,
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
                chunk.metadata["section.content_type"] = "merged_qa" if chunk_role == "merged_qa" else content_type
                chunk.metadata["section.parent_id_index"] = sid
                chunk.metadata["section.parent_text"] = parent_windows[ci]
                chunk.metadata["section.parent_char_count"] = len(parent_windows[ci])
                chunk.metadata["section.parent_window_index"] = ci
                chunk.metadata["section.parent_window_budget"] = _PARENT_WINDOW_CHAR_BUDGET
                valid_chunks.append(chunk)

    # ── 统计 ──
    chunk_lengths = [int(c.metadata.get("char_count") or len(c.page_content or "")) for c in valid_chunks]
    incomplete_detail_count = sum(1 for c in valid_chunks if not _is_sentence_complete(c.page_content))
    merged_qa_count = sum(1 for c in valid_chunks if c.metadata.get("section.chunk_role") == "merged_qa")
    metrics.emit(
        event="split_documents",
        stage="splitter",
        values={
            "input_docs": len(documents),
            "total_chunks": len(valid_chunks),
            "detail_chunks": len(valid_chunks) - merged_qa_count,
            "merged_qa_chunks": merged_qa_count,
            "avg_chunk_chars": round(sum(chunk_lengths) / len(chunk_lengths), 3) if chunk_lengths else 0.0,
            "p50_chunk_chars": _percentile(chunk_lengths, 0.5),
            "p90_chunk_chars": _percentile(chunk_lengths, 0.9),
            "short_chunk_ratio": round(sum(1 for n in chunk_lengths if n < max(MIN_CHUNK_LENGTH * 3, 60)) / len(chunk_lengths), 6) if chunk_lengths else 0.0,
            "long_chunk_ratio": round(sum(1 for n in chunk_lengths if n > 1600) / len(chunk_lengths), 6) if chunk_lengths else 0.0,
            "mid_sentence_cut_rate": round(incomplete_detail_count / len(valid_chunks), 6) if valid_chunks else 0.0,
        },
    )
    logger.info("Split %d documents into %d chunks", len(documents), len(valid_chunks))
    return valid_chunks
