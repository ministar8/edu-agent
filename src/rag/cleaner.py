"""文本清洗模块

在文档加载后、分块前执行，消除检索噪音：
- 去除多余空白/换行
- 统一全角/半角标点
- 去除 PDF 页码/页眉页脚
- 去除乱码/特殊字符
- 编码规范化
"""

from __future__ import annotations

import logging
import re
import time
import unicodedata
from collections import Counter
from pathlib import Path
from typing import TYPE_CHECKING

from langchain_core.documents import Document

from rag.metrics import metrics

if TYPE_CHECKING:
    # 仅供类型标注使用；运行时导入保持在函数内（避免循环依赖）
    from tools.anomaly import AnomalyRecord

logger = logging.getLogger(__name__)

# ── 正则预编译 ──────────────────────────────────

# PDF 页码：单独一行的 "第X页" / "Page X" / "- X -" / 纯数字行
_PAGE_NUM_RE = re.compile(
    r"^\s*(?:第\s*\d+\s*页|page\s*\d+|-?\s*\d+\s*-?)\s*$",
    re.IGNORECASE | re.MULTILINE,
)

# PDF 页眉页脚：短行（<40字）且出现在文档开头/结尾的重复行
_SHORT_LINE_RE = re.compile(r"^[^\n]{1,40}$", re.MULTILINE)

# 连续3个以上换行 → 2个换行
_MULTI_NEWLINE_RE = re.compile(r"\n{3,}")

# 连续3个以上空格 → 1个空格
_MULTI_SPACE_RE = re.compile(r"(?<=\S)[ \t]{3,}(?=\S)")

# 行尾空白（空格/制表符）
_LINE_TRIM_RE = re.compile(r"[ \t]+$", re.MULTILINE)

# 乱码：控制字符（\t \n \r 除外）
_CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

_FENCE_RE = re.compile(r"^\s*(```+|~~~+)")

_WEB_NOISE_MARKERS = (
    ".choice-container",
    ".choice-option",
    ".choice-inline",
    ".choice-text",
    ".explanation",
    ".feedback-area",
    ".multiple-choice-hint",
    "@media(",
    "@keyframes",
    "document.addEventListener",
    "querySelector",
    "localStorage",
    "window.quizChoiceFlag",
    "setupChoiceEventListeners",
    "restoreChoices()",
    "saveChoiceToLocalStorage",
)

_WEB_NOISE_LINE_RE = re.compile(
    r"(?:querySelector|addEventListener|localStorage|document\.|window\.|"
    r"choice-container|choice-option|feedback-area|multiple-choice-hint|"
    r"@media|@keyframes)"
)

_INLINE_EXAM_HEADING_RE = re.compile(r"(?<!\n)(#{4,5}\s*\d+\s*)")

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


# ── 同义词归一（统一数据源：rag.synonyms） ──────────
from rag.synonyms import normalize_synonyms  # noqa: E402


def _get_source_ext(doc: Document) -> str:
    return Path(_get_source_path(doc)).suffix.lower()


def _get_source_path(doc: Document) -> str:
    return str(
        doc.metadata.get("source_path")
        or doc.metadata.get("source_file")
        or doc.metadata.get("source")
        or ""
    )


def _normalize_text(text: str) -> str:
    if not text or not text.strip():
        return ""
    return unicodedata.normalize("NFKC", _CONTROL_CHARS_RE.sub("", text))


def _collapse_blank_lines(lines: list[str]) -> list[str]:
    collapsed: list[str] = []
    blank_run = 0
    for line in lines:
        if line.strip():
            blank_run = 0
            collapsed.append(line)
            continue
        blank_run += 1
        if blank_run <= 2:
            collapsed.append("")
    return collapsed


def _clean_markdown_text(text: str) -> str:
    normalized = _normalize_text(text)
    if not normalized:
        return ""
    cleaned_lines: list[str] = []
    in_fence = False
    for line in normalized.splitlines():
        stripped = _LINE_TRIM_RE.sub("", line)
        if _FENCE_RE.match(stripped):
            in_fence = not in_fence
            cleaned_lines.append(stripped)
            continue
        if in_fence:
            cleaned_lines.append(stripped)
            continue
        cleaned_lines.append(stripped)
    return "\n".join(_collapse_blank_lines(cleaned_lines)).strip()


def _is_exam_markdown_source(source: str) -> bool:
    normalized = source.replace("\\", "/").lower()
    return "/questions/" in normalized or normalized.endswith("_408_exam.md")


def _remove_exam_web_noise(text: str) -> tuple[str, int]:
    if not text or not text.strip():
        return text, 0

    removed = 0
    cleaned_lines: list[str] = []
    in_fence = False

    for line in text.splitlines():
        stripped = line.strip()
        if _FENCE_RE.match(stripped):
            in_fence = not in_fence
            cleaned_lines.append(line)
            continue
        if in_fence:
            cleaned_lines.append(line)
            continue

        cut_pos = -1
        for marker in _WEB_NOISE_MARKERS:
            pos = line.find(marker)
            if pos >= 0 and (cut_pos < 0 or pos < cut_pos):
                cut_pos = pos

        if cut_pos >= 0:
            prefix = line[:cut_pos].rstrip(" -`},;")
            if prefix:
                cleaned_lines.append(prefix)
            removed += len(line) - len(prefix)
            continue

        if len(stripped) > 160 and _WEB_NOISE_LINE_RE.search(stripped):
            removed += len(line)
            continue

        if len(stripped) > 300 and (
            stripped.count("{") + stripped.count("}") >= 4
            or stripped.count("=>") >= 2
            or stripped.count("`") >= 4
        ):
            removed += len(line)
            continue

        cleaned_lines.append(line)

    cleaned = "\n".join(_collapse_blank_lines(cleaned_lines)).strip()
    return cleaned, removed


def _normalize_exam_question_headings(text: str) -> str:
    if not text or not text.strip():
        return text
    normalized = _INLINE_EXAM_HEADING_RE.sub(r"\n\1\n", text)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    return normalized.strip()


def _edge_lines(text: str) -> list[str]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return []
    candidates = lines[:2] + lines[-2:]
    return [
        line
        for line in candidates
        if len(line) <= 40 and _SHORT_LINE_RE.match(line) and not _PAGE_NUM_RE.match(line)
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


def _finalize_whitespace(cleaned: str) -> str:
    """收尾空白清理：压缩多余换行/空格并去除首尾空白"""
    cleaned = _MULTI_NEWLINE_RE.sub("\n\n", cleaned)
    cleaned = _MULTI_SPACE_RE.sub(" ", cleaned)
    return cleaned.strip()


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


def _clean_plain_text(text: str) -> str:
    normalized = _normalize_text(text)
    if not normalized:
        return ""
    cleaned_lines = [_LINE_TRIM_RE.sub("", line) for line in normalized.splitlines()]
    cleaned = "\n".join(cleaned_lines)
    cleaned = _PAGE_NUM_RE.sub("", cleaned)
    return _finalize_whitespace(cleaned)


def _pdf_source_key(doc: Document) -> str:
    """PDF 页边重复行去重的分组键（_dedupe_pdf_edges 与 pdf 分派共用这一份规则）"""
    return str(doc.metadata.get("source_path") or doc.metadata.get("source_file") or id(doc))


def _dispatch_clean(
    doc: Document,
    ext: str,
    source_path: str,
    repeated_edges: set[str],
) -> None:
    """按扩展名分派单文档清洗：.md / .pdf / 其它（三分支顺序与条件是行为的一部分）"""
    if ext == ".md":
        doc.page_content = _clean_markdown_text(doc.page_content)
        if _is_exam_markdown_source(source_path):
            doc.page_content, removed_noise = _remove_exam_web_noise(doc.page_content)
            doc.page_content = _normalize_exam_question_headings(doc.page_content)
            if removed_noise:
                doc.metadata["exam_web_noise_removed_chars"] = removed_noise
    elif ext == ".pdf":
        doc.page_content = _clean_pdf_text(doc.page_content, repeated_edges)
    else:
        doc.page_content = _clean_plain_text(doc.page_content)


def _clean_by_extension(documents: list[Document]) -> tuple[list[Document], int]:
    """阶段0：按扩展名分派清洗，丢弃过短文档并标记 cleaned_ratio

    Returns:
        (清洗后保留的文档列表, 被丢弃的文档数)
    """
    cleaned: list[Document] = []
    dropped_docs = 0
    pdf_edge_map = _dedupe_pdf_edges([doc for doc in documents if _get_source_ext(doc) == ".pdf"])
    for doc in documents:
        original_len = len(doc.page_content)
        ext = _get_source_ext(doc)
        source_path = _get_source_path(doc)
        repeated_edges = pdf_edge_map.get(_pdf_source_key(doc), set()) if ext == ".pdf" else set()
        _dispatch_clean(doc, ext, source_path, repeated_edges)

        if len(doc.page_content.strip()) < 10:
            dropped_docs += 1
            continue

        if len(doc.page_content) < original_len * 0.5:
            doc.metadata["cleaned_ratio"] = f"{1 - len(doc.page_content) / original_len:.0%}"

        cleaned.append(doc)
    return cleaned, dropped_docs


def _run_normalization(cleaned: list[Document]) -> tuple[list[Document], list[dict]]:
    """阶段1：数据转换与标准化（清洗后、填充前执行）"""
    from tools.normalizer import normalize_documents

    cleaned, norm_log = normalize_documents(cleaned)
    if norm_log:
        logger.info("标准化: %d 篇文档已转换", len(norm_log))
    return cleaned, norm_log


def _run_synonym_normalize(cleaned: list[Document]) -> list[Document]:
    """阶段2：同义词归一（标准化后、填充前执行）"""
    # ★ 跨侧契约的文档侧：一旦改写原文，query 侧做字面匹配的消费者（BM25 的 `$contains`、
    #   cross-encoder reranker）就必须同样归一，否则错配。开关默认开（保持既有行为），
    #   关掉即「文档保持原文」，用于与 query 侧归一做对照；实测代价见 settings 同名开关的注释。
    from core.settings import settings

    synonym_total = 0
    if settings.INGEST_SYNONYM_NORMALIZE:
        for doc in cleaned:
            doc.page_content, replaced_count = normalize_synonyms(doc.page_content)
            synonym_total += replaced_count
    if synonym_total:
        logger.info("同义词归一: %d 处替换", synonym_total)
    return cleaned


def _run_imputation(cleaned: list[Document]) -> tuple[list[Document], list[dict]]:
    """阶段3：缺失值填充（标准化后、去重前执行）"""
    from tools.imputer import impute_documents

    cleaned, impute_log = impute_documents(cleaned)
    if impute_log:
        logger.info("缺失值填充: %d 条记录", len(impute_log))
    return cleaned, impute_log


def _detect_content_anomalies_stage(
    cleaned: list[Document],
) -> tuple[list[Document], list[AnomalyRecord], int]:
    """阶段4：异常检测·内容层（去重前，处理乱码型异常）"""
    from tools.anomaly import detect_content_anomalies

    cleaned, content_anomaly_records = detect_content_anomalies(cleaned)
    # 过滤全乱码文档（不入库）
    cleaned = [doc for doc in cleaned if doc.metadata.get("content_status") != "full_garbage"]
    content_anomaly_count = sum(1 for r in content_anomaly_records if r.actions_taken)
    if content_anomaly_count:
        logger.info("异常检测[阶段1/内容层]: %d 篇文档存在异常", content_anomaly_count)
    return cleaned, content_anomaly_records, content_anomaly_count


def _run_dedup(
    cleaned: list[Document],
    *,
    dedup: bool,
    fuzzy_dedup: bool,
    fuzzy_threshold: float,
) -> tuple[list[Document], list[dict]]:
    """阶段5：去重（内容异常处理后执行，基于清洗后的内容）"""
    if not (dedup or fuzzy_dedup):
        return cleaned, []

    from tools.dedup import dedup_documents

    cleaned, dup_records = dedup_documents(
        cleaned,
        exact=dedup,
        fuzzy=fuzzy_dedup,
        fuzzy_threshold=fuzzy_threshold,
    )
    if dup_records:
        logger.info("去重结果: 移除 %d 条重复记录", len(dup_records))
    return cleaned, dup_records


def _detect_statistical_anomalies_stage(
    cleaned: list[Document],
    content_anomaly_records: list[AnomalyRecord],
) -> tuple[list[Document], int]:
    """阶段6：异常检测·统计层（去重后，统计指标更准确）"""
    from tools.anomaly import detect_statistical_anomalies

    cleaned, anomaly_records = detect_statistical_anomalies(
        cleaned, prev_records=content_anomaly_records
    )
    stat_anomaly_count = sum(1 for r in anomaly_records if r.actions_taken)
    if stat_anomaly_count:
        logger.info("异常检测[阶段2/统计层]: %d 篇文档存在异常", stat_anomaly_count)
    return cleaned, stat_anomaly_count


def clean_documents(
    documents: list[Document],
    *,
    dedup: bool = True,
    fuzzy_dedup: bool = True,
    fuzzy_threshold: float = 0.9,
) -> list[Document]:
    """清洗文档集合

    Args:
        documents: 待清洗文档列表
        dedup: 是否启用精确去重（MD5）
        fuzzy_dedup: 是否启用模糊去重（MinHash + LSH）
        fuzzy_threshold: 模糊去重相似度阈值，默认 0.9

    Returns:
        清洗后文档列表
    """
    start = time.perf_counter()
    original_total_chars = sum(len(doc.page_content or "") for doc in documents)
    cleaned, dropped_docs = _clean_by_extension(documents)

    cleaned, norm_log = _run_normalization(cleaned)

    cleaned = _run_synonym_normalize(cleaned)

    cleaned, impute_log = _run_imputation(cleaned)

    cleaned, content_anomaly_records, content_anomaly_count = _detect_content_anomalies_stage(
        cleaned
    )

    cleaned, dup_records = _run_dedup(
        cleaned, dedup=dedup, fuzzy_dedup=fuzzy_dedup, fuzzy_threshold=fuzzy_threshold
    )

    cleaned, stat_anomaly_count = _detect_statistical_anomalies_stage(
        cleaned, content_anomaly_records
    )

    cleaned_total_chars = sum(len(doc.page_content or "") for doc in cleaned)
    retention_ratio = cleaned_total_chars / original_total_chars if original_total_chars else 0.0
    metrics.emit(
        event="clean_documents",
        stage="cleaner",
        duration_ms=round((time.perf_counter() - start) * 1000, 3),
        values={
            "input_docs": len(documents),
            "output_docs": len(cleaned),
            "dropped_docs": dropped_docs,
            "normalized_docs": len(norm_log),
            "imputed_docs": len(impute_log),
            "content_anomaly_docs": content_anomaly_count,
            "stat_anomaly_docs": stat_anomaly_count,
            "dedup_removed": len(dup_records),
            "retention_ratio": round(retention_ratio, 6),
            "original_total_chars": original_total_chars,
            "cleaned_total_chars": cleaned_total_chars,
        },
    )
    return cleaned
