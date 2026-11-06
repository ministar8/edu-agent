"""结构层缺失值填充：无章节标题长文档的自动分段标注。

三组能力：PDF 标题行检测 → 滑动窗口语义分段 → 空行/定长降级分段。
"""

from __future__ import annotations

import logging

from langchain_core.documents import Document

from ._constants import (
    _ALL_CAPS_RE,
    _CHAPTER_MARK_RE,
    _EXT_DEFAULT_CATEGORY,
    _NO_END_PUNCT_RE,
    _PAGE_NUM_RE,
    _PARAGRAPH_BOUNDARY_RE,
    _SEGMENT_PROFILES,
    _STOPWORDS,
    _SegmentProfile,
)
from ._resources import _QUOTA_CONFIG, _resource_guard, _with_timeout

logger = logging.getLogger(__name__)


def _resolve_segment_profile(doc: Document) -> _SegmentProfile:
    """根据文档类型动态解析语义分段配置

    查找优先级：
    1. metadata["category"] 精确匹配
    2. metadata["source_ext"] 映射到默认 category
    3. 兜底 "default"

    Returns:
        匹配的 _SegmentProfile 实例
    """
    meta = doc.metadata or {}

    # 1. category 精确匹配
    category = str(meta.get("category") or "").lower().strip()
    if category in _SEGMENT_PROFILES:
        return _SEGMENT_PROFILES[category]

    # 2. source_ext → 默认 category
    source_ext = str(meta.get("source_ext") or "").lower().strip()
    default_cat = _EXT_DEFAULT_CATEGORY.get(source_ext, "default")
    return _SEGMENT_PROFILES[default_cat]


def _detect_pdf_title_lines(text: str) -> list[dict]:
    """基于排版特征检测 PDF 中的标题行（规则方法，不依赖 LLM）

    检测规则：
    1. 短行(2-40字) + 无终结标点 + 独立成行(前后空行) → 标题候选
    2. 全大写英文行 → 标题候选
    3. 章节编号行("第X章"/"1."等) → 标题候选
    4. 过滤：排除页码/页眉/列表/代码行

    Returns:
        标题行列表 [{"line_num": int, "text": str, "position": int}]
    """
    lines = text.splitlines()
    title_lines: list[dict] = []
    pos = 0
    prev_blank = True

    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            prev_blank = True
            pos += len(line) + 1
            continue

        is_title = False

        # 跳过页码/纯数字行
        if stripped.isdigit() or _PAGE_NUM_RE.match(stripped):
            prev_blank = False
            pos += len(line) + 1
            continue

        # 规则1：章节编号行
        if _CHAPTER_MARK_RE.match(stripped):
            is_title = True

        # 规则2：全大写英文行
        elif _ALL_CAPS_RE.match(stripped):
            is_title = True

        # 规则3：短行 + 无终结标点 + 独立行
        elif 2 <= len(stripped) <= 40 and _NO_END_PUNCT_RE.search(stripped) and prev_blank:
            # 检查下一行是否为空行
            next_blank = i + 1 < len(lines) and not lines[i + 1].strip()
            if next_blank and not stripped.startswith(("-", "*", "+", ">", "```", "~~~", "#")):
                is_title = True

        if is_title:
            title_lines.append(
                {
                    "line_num": i,
                    "text": stripped,
                    "position": pos,
                }
            )

        prev_blank = False
        pos += len(line) + 1

    return title_lines


def _tokenize_with_positions(text: str) -> tuple[list[str], list[int]]:
    """分词，并同时给出每个词的字符起点。

    ★ 统一分词与字符位置计算，避免调用方重复分词后再重建位置。
    """
    if not text or not text.strip():
        return [], []

    try:
        import jieba

        raw = list(jieba.cut(text))
    except ImportError:
        # 字符级降级：词序列与位置一一对应
        chars = [(i, c) for i, c in enumerate(text) if c.strip() and c not in _STOPWORDS]
        return [c for _i, c in chars], [i for i, _c in chars]

    words = [w for w in raw if w.strip() and w not in _STOPWORDS]
    positions: list[int] = []
    search_start = 0
    for word in raw:
        if word.strip() and word not in _STOPWORDS:
            idx = text.find(word, search_start)
            if idx >= 0:
                positions.append(idx)
                search_start = idx + len(word)
    return words, positions


def _window_jaccard_distances(
    words: list[str], window_size: int, stride: int
) -> list[tuple[int, float]]:
    """相邻滑窗的词集 Jaccard 距离 → `[(分割点词索引, 距离)]`；分割点取右窗口起始索引。"""
    n_words = len(words)
    bags = [
        frozenset(words[i : i + window_size]) for i in range(0, n_words - window_size + 1, stride)
    ]

    out: list[tuple[int, float]] = []
    for k in range(len(bags) - 1):
        left, right = bags[k], bags[k + 1]
        if not left or not right:
            continue
        union = len(left | right)
        sim = len(left & right) / union if union > 0 else 0.0
        out.append(((k + 1) * stride, 1.0 - sim))
    return out


def _find_split_word_indices(
    distances: list[tuple[int, float]], diff_threshold: float
) -> list[int]:
    """取「距离 ≥ 阈值」且**严格大于**左右邻居的局部峰值（与邻居相等时仍算峰值）。"""
    peaks: list[int] = []
    for k, (idx, dist) in enumerate(distances):
        if dist < diff_threshold:
            continue
        if k > 0 and distances[k - 1][1] > dist:
            continue
        if k < len(distances) - 1 and distances[k + 1][1] > dist:
            continue
        peaks.append(idx)
    return peaks


def _segments_from_split_indices(
    text: str, split_indices: list[int], word_positions: list[int], min_chunk: int
) -> list[dict]:
    """把分割点（词索引）映射成字符位置，产出达到 `min_chunk` 的分段 + 末尾余段。"""
    segments: list[dict] = []
    prev_char_pos = 0
    for word_idx in split_indices:
        # 词索引越界时退到文末（分词器与位置映射理论上应当等长，这是兜底）
        char_pos = word_positions[word_idx] if word_idx < len(word_positions) else len(text)

        seg_len = char_pos - prev_char_pos
        if seg_len < min_chunk:
            continue

        segments.append({"position": prev_char_pos, "label": "", "char_count": seg_len})
        prev_char_pos = char_pos

    remaining = len(text) - prev_char_pos
    if remaining > 0:
        segments.append({"position": prev_char_pos, "label": "", "char_count": remaining})
    return segments


def _merge_short_segments(segments: list[dict], min_chunk: int) -> list[dict]:
    """过短的段落并入**前一段**（首段无处可并时保留原样）。"""
    merged: list[dict] = []
    for seg in segments:
        if merged and seg["char_count"] < min_chunk:
            merged[-1]["char_count"] += seg["char_count"]
        else:
            merged.append(seg)
    return merged


def _split_long_segments(segments: list[dict], max_chunk: int) -> list[dict]:
    """过长段落按 `max_chunk` 等分；最后一片是**余数**，可能小于 `min_chunk`（69 按 60 拆 → 60+9）。"""
    final: list[dict] = []
    for seg in segments:
        if seg["char_count"] <= max_chunk:
            final.append(seg)
            continue
        n_parts = (seg["char_count"] + max_chunk - 1) // max_chunk
        for p in range(n_parts):
            final.append(
                {
                    "position": seg["position"] + p * max_chunk,
                    "label": "",
                    "char_count": min(max_chunk, seg["char_count"] - p * max_chunk),
                }
            )
    return final


def _semantic_segment(
    text: str,
    min_chunk: int = 500,
    max_chunk: int = 2000,
    window_size: int = 50,
    stride: int = 25,
    diff_threshold: float = 0.55,
) -> list[dict]:
    """基于滑动窗口的语义分段

    策略：一次分词 → 预计算滑窗词袋 → 相邻窗 Jaccard 距离 → 取局部峰值作分割点 →
    映射到字符位置 → 合并过短段、拆分过长段。全文只分词一次（O(N)，而非逐句 O(N×M)），
    `stride` 控制计算密度（stride=25 时窗口数约 N/25）。六步各抽成独立函数，可单独测。

    Args:
        text: 正文文本
        min_chunk: 最小段落字符数
        max_chunk: 最大段落字符数
        window_size: 滑动窗口大小（词数），默认 50
        stride: 滑动步进（词数），默认 25
        diff_threshold: Jaccard 距离阈值，默认 0.55（即相似度 < 0.45 时分割）

    Returns:
        分段列表 [{"position": int, "label": str, "char_count": int}]；
        **只有 ≥2 段时才返回**，否则返回 `[]`（单段等于「没分段」）。
    """
    if not text or len(text) <= min_chunk:
        return []

    words, word_positions = _tokenize_with_positions(text)
    if len(words) < window_size * 2:
        # 词数太少，无法做窗口比较
        return []

    distances = _window_jaccard_distances(words, window_size, stride)
    if not distances:
        return []

    split_indices = _find_split_word_indices(distances, diff_threshold)
    if not split_indices:
        return []

    segments = _segments_from_split_indices(text, split_indices, word_positions, min_chunk)
    final = _split_long_segments(_merge_short_segments(segments, min_chunk), max_chunk)
    for i, seg in enumerate(final):
        seg["label"] = f"[第{i + 1}段]"

    return final if len(final) > 1 else []


def _section_headings_from_pdf(text: str) -> list[dict]:
    """策略1：用 PDF 排版特征检测到的标题行作分段锚点（<2 行时返回 []）"""
    title_lines = _detect_pdf_title_lines(text)
    if len(title_lines) < 2:
        return []
    sections = []
    for tl in title_lines:
        label = tl["text"]
        if len(label) > 40:  # 截断过长标题
            label = label[:40] + "…"
        sections.append({"position": tl["position"], "label": label})
    return sections


def _section_headings_by_paragraphs(text: str) -> list[dict] | None:
    """策略3：按空行边界分段

    Returns:
        分段列表；`None` 表示「段落数 ≤1，不适用」由调用方转向定长分段。
    """
    paragraphs = _PARAGRAPH_BOUNDARY_RE.split(text)
    if len(paragraphs) <= 1:
        return None
    sections = []
    pos = 0
    for i, para in enumerate(paragraphs):
        if para.strip():
            sections.append({"position": pos, "label": f"[第{i + 1}段]"})
        pos += len(para) + 3
    return sections if len(sections) > 1 else []


def _section_headings_fixed(text: str, chunk_size: int = 1500) -> list[dict]:
    """策略4：定长切分"""
    return [
        {"position": i, "label": f"[第{i // chunk_size + 1}段]"}
        for i in range(0, len(text), chunk_size)
    ]


def _impute_section_headings(doc: Document) -> list[dict]:
    """为无章节标题的文档自动分段并标注段落标题

    增强策略：
    1. PDF 文件：先尝试基于排版特征检测标题行，用标题行作为分段锚点
    2. 所有文件：基于语义连贯性检测分段（句子相似度阈值）
    3. 降级：纯空行边界 + 固定长度分段

    仅当文档无 heading 且内容较长（>2000字符）时触发。

    Returns:
        段落分割点列表 [{"position": int, "label": str}]
    """
    text = doc.page_content.strip() if doc.page_content else ""
    meta = doc.metadata or {}
    source_ext = str(meta.get("source_ext") or "")

    # 已有标题或内容过短，不需要
    if meta.get("heading") or len(text) <= 2000:
        return []

    # 策略1：PDF 基于排版特征检测标题行
    if source_ext == ".pdf":
        sections = _section_headings_from_pdf(text)
        if sections:
            return sections

    # 策略2：语义连贯性分段（所有文件类型，配额控制，动态配置）
    if _resource_guard.is_available("semantic_segment"):
        _resource_guard.record("semantic_segment")
        profile = _resolve_segment_profile(doc)

        @_with_timeout(_QUOTA_CONFIG["semantic_segment"]["timeout"])
        def _semantic():
            return _semantic_segment(
                text,
                min_chunk=profile.min_chunk,
                max_chunk=profile.max_chunk,
                window_size=profile.window_size,
                stride=profile.stride,
                diff_threshold=profile.diff_threshold,
            )

        semantic_sections = _semantic()
        if semantic_sections:
            return semantic_sections
    # 配额耗尽或超时 → 跳过语义分段

    # 策略3/4：降级 — 先空行边界，不适用则定长分段
    sections = _section_headings_by_paragraphs(text)
    if sections is not None:
        return sections
    return _section_headings_fixed(text)
