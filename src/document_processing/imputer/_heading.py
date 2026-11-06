"""元数据层缺失值填充：heading / heading_path / category 推断。"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from langchain_core.documents import Document

from ._constants import (
    _ALL_CAPS_RE,
    _CHAPTER_MARK_RE,
    _CONFIDENCE_HIGH,
    _CONFIDENCE_LOW,
    _CONFIDENCE_MEDIUM,
    _ENDS_WITH_PUNCT_RE,
    _HEADING_CANDIDATE_RE,
    _LOW_CONFIDENCE_PREFIX,
    _MD_HEADING_RE,
    _NO_END_PUNCT_RE,
    _PAGE_NUM_RE,
    _STOPWORDS,
)
from ._resources import _QUOTA_CONFIG, _resource_guard, _with_timeout

logger = logging.getLogger(__name__)


# ── Heading 推断缓存 ──
# key = f"{source_ext}:{source_path}"，value = (heading, method, confidence)
# ★ 必须连 method 一起存：只想缓存 confidence 的话，命中时要靠 confidence 反查 method，
#   而 low 置信度对应**多个**方法（首行 / 关键词 / 兜底），反查只能取到字典里第一个
#   ⇒ 报出的方法名被错标（实测首轮的 keyword 在后续调用里被报成 first_line_filtered）。
#   缓存生命周期见 `impute_documents` 开头：每次调用清空，不跨次复用。
_heading_cache: dict[str, tuple[str, str, str]] = {}


def get_heading_cache_stats() -> dict:
    """获取缓存统计"""
    return {"size": len(_heading_cache)}


def _validate_heading_candidate(candidate: str, text: str) -> bool:
    """验证 heading 候选是否与正文内容相关（抑制幻觉）

    检查规则：
    1. 候选中的关键词必须至少部分出现在正文中
    2. 纯停用词组合 → 拒绝
    3. 过短（<2字）→ 拒绝
    4. 候选是数字或纯编号 → 拒绝

    Returns:
        True = 候选可信，False = 候选可能是幻觉
    """
    if not candidate or len(candidate) < 2:
        return False

    # 纯数字/编号拒绝
    if candidate.isdigit() or re.match(r"^[\d._\-]+$", candidate):
        return False

    # 兜底标记不验证
    if candidate == "[未命名文档]":
        return True

    # 检查候选中的非停用词是否出现在正文中
    # 提取候选中的关键词（去除停用词）
    try:
        import jieba

        candidate_words = [w for w in jieba.cut(candidate) if w.strip() and w not in _STOPWORDS]
    except ImportError:
        candidate_words = [c for c in candidate if c.strip() and c not in _STOPWORDS]

    if not candidate_words:
        # 候选全是停用词 → 幻觉风险极高
        return False

    # 至少 50% 的关键词出现在正文中
    text_lower = text.lower()
    hits = sum(1 for w in candidate_words if w.lower() in text_lower)
    coverage = hits / len(candidate_words)

    return coverage >= 0.5


def _non_stopword_ratio(text: str) -> float:
    """计算非停用词比例，用于首行提取质量过滤

    配额控制：jieba_stopword 超限时降级为字符级判断
    """
    if not _resource_guard.check_and_record("jieba_stopword"):
        # 降级：字符级判断（无停用词过滤，直接返回 1.0 放行）
        return 1.0

    @_with_timeout(_QUOTA_CONFIG["jieba_stopword"]["timeout"])
    def _compute():
        try:
            import jieba

            words = [w for w in jieba.cut(text) if w.strip()]
        except ImportError:
            words = [c for c in text if c.strip()]
        if not words:
            return 0.0
        non_stop = sum(1 for w in words if w not in _STOPWORDS)
        return non_stop / len(words)

    result = _compute()
    return result if result is not None else 1.0  # 超时降级为放行


def _extract_md_heading(text: str) -> str | None:
    """从 Markdown 文本中解析第一个标题

    优先取 # 级标题，其次 ## 级。
    """
    for match in _MD_HEADING_RE.finditer(text):
        level = len(match.group(1))
        title = match.group(2).strip()
        if level <= 2 and title:
            return title
    return None


def _extract_chapter_heading(text: str) -> str | None:
    """从正文中识别章节标记生成 heading

    识别 "第X章"、"1."、"一、" 等编号行，取第一个匹配作为文档标题。
    """
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        match = _CHAPTER_MARK_RE.match(line)
        if match:
            # 完整行作为标题（编号 + 标题文字）
            heading = line.strip()
            if len(heading) <= 60:
                return heading
            # 过长则只取编号+后续文字
            return line[:60].rstrip(".")
    return None


def _extract_pdf_heading_by_features(text: str) -> str | None:
    """基于字体大小/加粗特征检测 PDF 标题（规则方法，不依赖 LLM）

    PDF 经 PyPDFLoader 加载后，文本中不直接包含字体信息，
    但标题行通常具有以下特征：
    - 短行（2-40字符）
    - 无句末终结标点（。！？等）
    - 位于文档前部（前20行）
    - 非页码/页眉
    - 全大写英文行
    - 独立成行（前后有空行）
    """
    lines = text.splitlines()
    # 只搜索前20行
    search_lines = lines[:20]

    prev_blank = True  # 上一行是否为空行
    for i, line in enumerate(search_lines):
        stripped = line.strip()
        if not stripped:
            prev_blank = True
            continue

        # 跳过页码/纯数字行
        if stripped.isdigit() or _PAGE_NUM_RE.match(stripped):
            prev_blank = False
            continue

        # 特征1：全大写英文行
        if _ALL_CAPS_RE.match(stripped):
            return stripped

        # 特征2：短行 + 无终结标点 + 前后有空行（独立行）
        if 2 <= len(stripped) <= 40 and _NO_END_PUNCT_RE.search(stripped) and prev_blank:
            # 检查下一行是否为空行（独立行特征）
            next_blank = i + 1 < len(search_lines) and not search_lines[i + 1].strip()
            if next_blank:
                # 排除列表项、代码行等
                if not stripped.startswith(("-", "*", "+", ">", "```", "~~~", "#")):
                    return stripped

        prev_blank = False

    return None


def _looks_like_heading_line(line: str) -> bool:
    """首行是否**像**一个标题（纯形态判断，不验证内容相关性）。

    短、不以 Markdown 标记符开头、非纯数字、不像句子（不以终结标点收尾）、非停用词堆。
    """
    return bool(
        line
        and len(line) <= 30
        and not line.startswith(("#", "*", "-", "`", "```", "~~~"))
        and not line.isdigit()
        and _HEADING_CANDIDATE_RE.match(line)
        and not _ENDS_WITH_PUNCT_RE.search(line)
        and _non_stopword_ratio(line) > 0.5
    )


def _heading_from_original(text: str, source_ext: str) -> tuple[str, str, str] | None:
    """高置信度方法（从原文提取）：Markdown 标题 > 章节标记 > PDF 版式特征"""
    if not text:
        return None

    if source_ext == ".md":
        result = _extract_md_heading(text)
        if result:
            return result, "md_heading", _CONFIDENCE_HIGH

    result = _extract_chapter_heading(text)
    if result:
        return result, "chapter_mark", _CONFIDENCE_HIGH

    if source_ext == ".pdf" and _resource_guard.check_and_record("pdf_feature"):

        @_with_timeout(_QUOTA_CONFIG["pdf_feature"]["timeout"])
        def _pdf_detect():
            return _extract_pdf_heading_by_features(text)

        result = _pdf_detect()
        if result:
            return result, "pdf_feature", _CONFIDENCE_HIGH

    return None


def _impute_heading_medium_low(
    text: str, source_name: str, min_level: int
) -> tuple[str, str, str] | None:
    """中/低置信度方法：文件名 → 首行 → 关键词 → 兜底

    Returns:
        命中元组；`None` 表示被 `min_level` 截断（不应填充）。
    """
    # 文件名推断 [medium]
    if source_name and min_level >= 1:
        clean_name = re.sub(r"^[\d]+[_.\-\s]*", "", source_name)
        clean_name = re.sub(r"[_\-]+", " ", clean_name).strip()
        if clean_name and len(clean_name) <= 50:
            return clean_name, "filename", _CONFIDENCE_MEDIUM

    # 首行提取 [low]
    if text and min_level >= 2:
        first_line = text.splitlines()[0].strip()
        if _looks_like_heading_line(first_line) and _validate_heading_candidate(first_line, text):
            return first_line, "first_line_filtered", _CONFIDENCE_LOW

    # 关键词组合 [low]
    if text and min_level >= 2 and _resource_guard.check_and_record("jieba_keyword"):

        @_with_timeout(_QUOTA_CONFIG["jieba_keyword"]["timeout"])
        def _keyword_extract():
            try:
                import jieba.analyse

                keywords = jieba.analyse.extract_tags(text, topK=2, withWeight=False)
                if len(keywords) >= 2:
                    return f"{keywords[0]}与{keywords[1]}"
                elif len(keywords) == 1:
                    return keywords[0]
            except ImportError:
                pass
            return None

        candidate = _keyword_extract()
        if candidate and _validate_heading_candidate(candidate, text):
            return candidate, "keyword", _CONFIDENCE_LOW

    # 兜底 [low]。★ min_confidence 高于 low 时兜底不生效，返回 None（无需填充），
    # 不能把 None 拼成字符串 "[推测]None" 再写进缓存（backlog #38）。
    if min_level < 2:
        return None
    return "[未命名文档]", "fallback", _CONFIDENCE_LOW


def _impute_heading(doc: Document, min_confidence: str = "low") -> tuple[str, str, str] | None:
    """标题缺失填充

    优先级（从高到低）：
    1. metadata 中已有 heading → 保留，不覆盖
    2. 缓存命中 → 同名文件复用之前的推断结果
    3~5. 高置信度（原文提取）：Markdown 标题 / 章节标记 / PDF 版式特征 → `_heading_from_original`
    6~9. 中/低置信度：文件名 / 首行 / 关键词 / 兜底 → `_impute_heading_medium_low`

    幻觉抑制：low 结果须通过 `_validate_heading_candidate` 内容覆盖验证，通过后加 [推测] 前缀；
    `min_confidence` 控制截断（"medium" 跳过所有 low 方法，"high" 只用原文提取方法）。

    Args:
        doc: 待填充文档
        min_confidence: 最低置信度阈值，"low"(默认)/"medium"/"high"

    Returns:
        (heading, method, confidence) 或 None（无需填充）
    """
    meta = doc.metadata or {}

    # 1. 已有 heading，不覆盖
    if meta.get("heading"):
        return None  # 无需填充

    source_path = str(meta.get("source_path") or meta.get("source_file") or "")
    source_ext = str(meta.get("source_ext") or Path(source_path).suffix.lower())
    source_name = Path(source_path).stem if source_path else ""
    text = doc.page_content.strip() if doc.page_content else ""

    # 置信度阈值映射
    min_level = {"high": 0, "medium": 1, "low": 2}.get(min_confidence, 2)

    # 2. 缓存命中。★ 键必须**唯一标识来源文件**（backlog #37）：用完整路径，无路径时退到内容前缀；
    #    只用文件名会让跨目录同名文件互相串标题。
    cache_key = f"{source_ext}:{source_path or text[:64]}"
    if cache_key in _heading_cache:
        return _heading_cache[cache_key]

    # 3~5. 高置信度（原文提取）
    result = _heading_from_original(text, source_ext)
    if result is None:
        # 6~9. 中/低置信度（受 min_confidence 控制）
        result = _impute_heading_medium_low(text, source_name, min_level)
        if result is None:
            return None

    heading, method, confidence = result
    # 低置信度且非兜底 → 添加 [推测] 前缀
    if confidence == _CONFIDENCE_LOW and heading != "[未命名文档]":
        heading = f"{_LOW_CONFIDENCE_PREFIX}{heading}"

    # 写入缓存（含 method）
    _heading_cache[cache_key] = (heading, method, confidence)
    return (heading, method, confidence)


def _impute_heading_path(doc: Document, heading: str | None) -> str | None:
    """标题路径缺失填充"""
    meta = doc.metadata or {}

    # 已有 heading_path，不覆盖
    if meta.get("heading_path"):
        return None

    # 从 heading 构建
    h = heading or meta.get("heading") or ""
    if h:
        return f"[{h}]"

    # 从 source_name 构建
    source_path = str(meta.get("source_path") or meta.get("source_file") or "")
    source_name = Path(source_path).stem if source_path else ""
    if source_name:
        return f"[{source_name}]"

    return None


def _impute_category(doc: Document) -> str | None:
    """分类缺失填充：从 source_path 路径推断"""
    meta = doc.metadata or {}

    # 已有 category，不覆盖
    if meta.get("category"):
        return None

    source_path = str(meta.get("source_path") or meta.get("source_file") or "")
    if not source_path:
        return None

    # 路径格式：operating_system/chapter1.md → category="operating_system"
    parts = Path(source_path).parts
    if len(parts) >= 2:
        potential_category = parts[0]
        # 排除常见非分类目录名
        if potential_category not in ("docs", "files", "data", "resources"):
            return potential_category

    return None
