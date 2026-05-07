"""缺失值填充模块

在清洗后、分块前执行，对文档内容和元数据中的缺失值进行填充/标记：

内容层：
- 正文为空/过短 → 标记 content_status="empty"，不入库
- 含占位符（"此处为图片"等）→ 标记 has_placeholder=True
- 未闭合围栏/括号 → 标记 truncated=True

元数据层（核心）：
- heading 缺失 → 优先级：Markdown标题解析 > 章节标记识别 > 文件名推断 > 首行提取(停用词过滤) > 关键词组合
- heading_path 缺失 → 从 heading 构建
- category 缺失 → 从 source_path 路径推断

结构层：
- PDF 无章节标题 → 字体大小/加粗特征检测标题 + 语义连贯性分段
- 纯文本分段 → 语义连贯性检测（句子相似度）+ 空行边界

原则：不虚构内容，只标记缺失状态；不覆盖已有元数据。
"""

from __future__ import annotations

import logging
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from functools import wraps
from pathlib import Path
from typing import Optional

from langchain_core.documents import Document

logger = logging.getLogger(__name__)


# ── 资源控制配置 ────────────────────────────────────

# 各操作的调用配额与超时
_QUOTA_CONFIG = {
    "jieba_keyword": {"max_calls": 200, "timeout": 5.0},    # jieba 关键词提取
    "jieba_stopword": {"max_calls": 500, "timeout": 2.0},   # jieba 停用词过滤
    "semantic_segment": {"max_calls": 100, "timeout": 10.0}, # 语义连贯分段
    "pdf_feature": {"max_calls": 300, "timeout": 3.0},      # PDF 特征检测
    "llm_call": {"max_calls": 50, "timeout": 30.0, "retries": 2},  # LLM 调用（预留）
}


class _ResourceGuard:
    """资源配额监控器：跟踪昂贵操作调用次数，超限时自动降级"""

    def __init__(self, config: dict | None = None):
        self._config = config or _QUOTA_CONFIG
        self._counters: dict[str, int] = {}
        self._degraded: set[str] = set()  # 已降级的操作集合

    def is_available(self, operation: str) -> bool:
        """检查操作是否仍在配额内"""
        if operation in self._degraded:
            return False
        max_calls = self._config.get(operation, {}).get("max_calls", float("inf"))
        current = self._counters.get(operation, 0)
        return current < max_calls

    def record(self, operation: str) -> None:
        """记录一次操作调用"""
        self._counters[operation] = self._counters.get(operation, 0) + 1

    def degrade(self, operation: str) -> None:
        """标记操作为已降级"""
        if operation not in self._degraded:
            self._degraded.add(operation)
            logger.warning("ResourceGuard: '%s' degraded (calls=%d, limit=%d)",
                           operation, self._counters.get(operation, 0),
                           self._config.get(operation, {}).get("max_calls", 0))

    def check_and_record(self, operation: str) -> bool:
        """检查配额并记录调用，返回是否可用"""
        if not self.is_available(operation):
            if operation not in self._degraded:
                self.degrade(operation)
            return False
        self.record(operation)
        return True

    @property
    def degraded_ops(self) -> set[str]:
        return self._degraded.copy()

    def summary(self) -> str:
        parts = [f"{op}:{cnt}" for op, cnt in sorted(self._counters.items())]
        degraded = ", ".join(sorted(self._degraded)) if self._degraded else "none"
        return f"calls({', '.join(parts)}) degraded({degraded})"


# 全局资源监控器实例
_resource_guard = _ResourceGuard()


def _with_timeout(timeout: float):
    """超时装饰器：超时则返回 None 并降级"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            start = time.perf_counter()
            try:
                result = func(*args, **kwargs)
            except Exception as e:
                logger.debug("Timeout wrapper: %s raised %s", func.__name__, e)
                return None
            elapsed = time.perf_counter() - start
            if elapsed > timeout:
                logger.warning("Timeout: %s took %.1fs (limit=%.1fs)", func.__name__, elapsed, timeout)
                return None
            return result
        return wrapper
    return decorator

# ── 正则预编译 ──────────────────────────────────────

# 占位符检测：图片占位、附件引用、表格占位
_PLACEHOLDER_RE = re.compile(
    r"(此处|这里|见|参见|详见).{0,6}(图片|图|图示|插图|附件|附表|表格|视频)",
)

# 未闭合代码围栏
_UNCLOSED_FENCE_RE = re.compile(r"^\s*(```+|~~~+)", re.MULTILINE)

# ── 语义分段配置档案 ────────────────────────────────
# 不同文档类型的段落粘连度差异很大，需要不同的分段参数：
#   - 法律/合同：段落长、主题稳定 → 大窗口、高阈值（少分割）
#   - 技术文档：段落短、主题切换快 → 小窗口、低阈值（多分割）
#   - 小说/文学：连续叙事 → 大窗口、高阈值
#   - 新闻/论文：段落分明 → 中等参数
#   - 通用兜底：默认参数

@dataclass
class _SegmentProfile:
    """语义分段参数档案"""
    window_size: int = 50       # 滑动窗口大小（词数）
    stride: int = 25            # 步进（词数）
    diff_threshold: float = 0.55  # Jaccard 距离阈值
    min_chunk: int = 500       # 最小段落字符数
    max_chunk: int = 2000      # 最大段落字符数

# 按 category / source_ext 匹配的档案表
_SEGMENT_PROFILES: dict[str, _SegmentProfile] = {
    # ── 法律/合同：段落长、主题稳定，少分割 ──
    "law":       _SegmentProfile(window_size=80, stride=40, diff_threshold=0.65, min_chunk=800,  max_chunk=3000),
    "contract":  _SegmentProfile(window_size=80, stride=40, diff_threshold=0.65, min_chunk=800,  max_chunk=3000),
    "regulation":_SegmentProfile(window_size=80, stride=40, diff_threshold=0.65, min_chunk=800,  max_chunk=3000),
    # ── 技术文档：段落短、主题切换快，多分割 ──
    "tech":      _SegmentProfile(window_size=30, stride=15, diff_threshold=0.45, min_chunk=300,  max_chunk=1500),
    "api":       _SegmentProfile(window_size=30, stride=15, diff_threshold=0.45, min_chunk=300,  max_chunk=1500),
    "code":      _SegmentProfile(window_size=30, stride=15, diff_threshold=0.45, min_chunk=300,  max_chunk=1500),
    "tutorial":  _SegmentProfile(window_size=40, stride=20, diff_threshold=0.50, min_chunk=400,  max_chunk=1500),
    # ── 小说/文学：连续叙事，少分割 ──
    "novel":     _SegmentProfile(window_size=100, stride=50, diff_threshold=0.70, min_chunk=1000, max_chunk=4000),
    "fiction":   _SegmentProfile(window_size=100, stride=50, diff_threshold=0.70, min_chunk=1000, max_chunk=4000),
    "literature":_SegmentProfile(window_size=100, stride=50, diff_threshold=0.70, min_chunk=1000, max_chunk=4000),
    # ── 新闻/论文：段落分明 ──
    "news":      _SegmentProfile(window_size=50, stride=25, diff_threshold=0.55, min_chunk=500,  max_chunk=2000),
    "paper":     _SegmentProfile(window_size=50, stride=25, diff_threshold=0.55, min_chunk=500,  max_chunk=2000),
    "thesis":    _SegmentProfile(window_size=50, stride=25, diff_threshold=0.55, min_chunk=500,  max_chunk=2000),
    # ── 教材/讲义 ──
    "textbook":  _SegmentProfile(window_size=60, stride=30, diff_threshold=0.55, min_chunk=600,  max_chunk=2500),
    "lecture":   _SegmentProfile(window_size=60, stride=30, diff_threshold=0.55, min_chunk=600,  max_chunk=2500),
    # ── 默认兜底 ──
    "default":   _SegmentProfile(window_size=50, stride=25, diff_threshold=0.55, min_chunk=500,  max_chunk=2000),
}

# source_ext → 默认 category 映射（当 metadata 无 category 时使用）
_EXT_DEFAULT_CATEGORY: dict[str, str] = {
    ".pdf": "paper",
    ".md":  "tech",
    ".txt": "default",
    ".docx":"paper",
    ".html":"news",
}


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

# 未闭合括号对
_UNCLOSED_BRACKET_RE = re.compile(r"[(（](?:(?![)）]).)*$|[\[{](?:(?![\]}]).)*$", re.MULTILINE)

# 首行标题候选：≤30字符的非空行，非代码/列表/纯数字
_HEADING_CANDIDATE_RE = re.compile(r"^[^#\-*`\d\s].{0,28}[^\s]$")

# 段落边界：连续2+空行
_PARAGRAPH_BOUNDARY_RE = re.compile(r"\n{3,}")

# 中文标点结尾（适合做标题）
_ENDS_WITH_PUNCT_RE = re.compile(r"[。！？；：…—]$")

# ── Markdown 标题解析 ──
_MD_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)

# ── 章节标记识别 ──
# 匹配 "第X章/节"、"1."、"1.1"、"一、"、"（一）" 等编号模式
_CHAPTER_MARK_RE = re.compile(
    r"^(?:"
    r"第[一二三四五六七八九十百千零\d]+[章节篇部]"  # 第一章/第2节
    r"|[\d]+\.[\d.]*"                          # 1. / 1.1 / 1.1.1
    r"|[一二三四五六七八九十]+[、.]"              # 一、/ 二.
    r"|[（(][一二三四五六七八九十\d]+[)）]"       # （一）/ (2)
    r")\s*(.{1,40})"
)

# ── PDF 标题特征检测 ──
# 全大写英文行（可能为标题）
_ALL_CAPS_RE = re.compile(r"^[A-Z][A-Z\s]{2,40}$")
# 短行 + 无句末标点（标题候选）
_TITLE_LINE_RE = re.compile(r"^[^\n]{2,40}$", re.MULTILINE)
# 行末无句号等终结标点
_NO_END_PUNCT_RE = re.compile(r"[^。！？；：…—.!?,;:]$")

# ── 中文停用词表（首行提取质量过滤） ──
_STOPWORDS = frozenset({
    "的", "了", "在", "是", "我", "有", "和", "就", "不", "人", "都", "一", "一个",
    "上", "也", "很", "到", "说", "要", "去", "你", "会", "着", "没有", "看", "好",
    "自己", "这", "他", "她", "它", "们", "那", "些", "什么", "怎么", "如何", "哪",
    "为什么", "因为", "所以", "但是", "而且", "或者", "如果", "虽然", "不过",
    "可以", "可能", "应该", "必须", "需要", "已经", "正在", "将要",
    "这个", "那个", "这些", "那些", "其", "之", "以", "于", "为", "与",
    "从", "把", "被", "让", "给", "向", "比", "等", "及",
})

# ── 句子边界检测 ──
_SENTENCE_END_RE = re.compile(r"[。！？；.!?;]\s*")

# ── Heading 推断缓存 ──
# key = f"{source_ext}:{source_name}", value = (heading, confidence)
_heading_cache: dict[str, tuple[str, str]] = {}

# ── 置信度分级 ──
# high: 来源确定性高（原文提取），几乎无幻觉风险
# medium: 来源有依据但非原文（文件名），低幻觉风险
# low: 来源为统计推断（关键词/首行），有幻觉风险
_CONFIDENCE_HIGH = "high"
_CONFIDENCE_MEDIUM = "medium"
_CONFIDENCE_LOW = "low"

# 方法 → 置信度映射
_METHOD_CONFIDENCE = {
    "md_heading": _CONFIDENCE_HIGH,
    "chapter_mark": _CONFIDENCE_HIGH,
    "pdf_feature": _CONFIDENCE_HIGH,
    "filename": _CONFIDENCE_MEDIUM,
    "first_line_filtered": _CONFIDENCE_LOW,
    "keyword": _CONFIDENCE_LOW,
    "fallback": _CONFIDENCE_LOW,
}

# 低置信度 heading 的前缀标记
_LOW_CONFIDENCE_PREFIX = "[推测]"


def clear_heading_cache() -> None:
    """清空 heading 缓存（入库完成后调用）"""
    _heading_cache.clear()


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


# ── 内容层缺失值 ────────────────────────────────────

def _detect_content_status(doc: Document) -> str:
    """检测内容状态

    Returns:
        "empty" | "placeholder" | "truncated" | "normal"
    """
    text = doc.page_content.strip() if doc.page_content else ""

    if not text or len(text) < 10:
        return "empty"

    # 占位符检测
    if _PLACEHOLDER_RE.search(text):
        return "placeholder"

    # 截断检测：未闭合代码围栏
    fence_matches = _UNCLOSED_FENCE_RE.findall(text)
    if fence_matches and len(fence_matches) % 2 != 0:
        return "truncated"

    return "normal"


def _detect_truncation(text: str) -> bool:
    """检测文本是否被截断"""
    # 未闭合代码围栏
    fence_matches = _UNCLOSED_FENCE_RE.findall(text)
    if fence_matches and len(fence_matches) % 2 != 0:
        return True

    # 未闭合中文/英文括号
    open_paren = len(re.findall(r"[(（]", text))
    close_paren = len(re.findall(r"[)）]", text))
    if open_paren != close_paren and open_paren > close_paren:
        return True

    open_bracket = len(re.findall(r"[\[{【]", text))
    close_bracket = len(re.findall(r"[\]}】]", text))
    if open_bracket != close_bracket and open_bracket > close_bracket:
        return True

    return False


# ── 元数据层缺失值 ──────────────────────────────────

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


def _extract_md_heading(text: str) -> Optional[str]:
    """从 Markdown 文本中解析第一个标题

    优先取 # 级标题，其次 ## 级。
    """
    for match in _MD_HEADING_RE.finditer(text):
        level = len(match.group(1))
        title = match.group(2).strip()
        if level <= 2 and title:
            return title
    return None


def _extract_chapter_heading(text: str) -> Optional[str]:
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


def _extract_pdf_heading_by_features(text: str) -> Optional[str]:
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
        if (
            2 <= len(stripped) <= 40
            and _NO_END_PUNCT_RE.search(stripped)
            and prev_blank
        ):
            # 检查下一行是否为空行（独立行特征）
            next_blank = (i + 1 < len(search_lines) and not search_lines[i + 1].strip())
            if next_blank:
                # 排除列表项、代码行等
                if not stripped.startswith(("-", "*", "+", ">", "```", "~~~", "#")):
                    return stripped

        prev_blank = False

    return None


def _impute_heading(doc: Document, min_confidence: str = "low") -> Optional[tuple[str, str, str]]:
    """标题缺失填充

    优先级（从高到低）：
    1. metadata 中已有 heading → 保留，不覆盖
    2. 缓存命中 → 同名文件复用之前的推断结果
    3. Markdown 标题解析（.md 文件优先） → 取首个 #/## 标题       [high]
    4. 章节标记识别 → "第X章"/"1."/"一、" 等编号行                   [high]
    5. PDF 标题特征检测 → 短行+无终结标点+独立行                    [high]
    6. 文件名推断 → source_name 清洗后作为 heading                   [medium]
    7. 首行提取（停用词比例>50%）→ 非停用词占比过半的首行             [low]
    8. jieba Top-2 关键词组合                                        [low]
    9. 兜底 → "[未命名文档]"                                         [low]

    幻觉抑制机制：
    - 每个方法产出带 confidence 标签（high/medium/low）
    - low 置信度结果必须通过 _validate_heading_candidate 内容覆盖验证
    - 未通过验证的 low 候选被拒绝，降级到下一优先级
    - 通过验证的 low 候选添加 [推测] 前缀，明确标注来源不确定
    - min_confidence 参数控制截断：设为 "medium" 则跳过所有 low 方法

    Args:
        doc: 待填充文档
        min_confidence: 最低置信度阈值，"low"(默认)/"medium"/"high"
            - "low": 全部方法可用
            - "medium": 跳过首行/关键词/兜底
            - "high": 只使用原文提取方法

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
    _conf_level = {"high": 0, "medium": 1, "low": 2}
    min_level = _conf_level.get(min_confidence, 2)

    # 2. 缓存命中
    cache_key = f"{source_ext}:{source_name}"
    if cache_key in _heading_cache:
        cached_heading, cached_conf = _heading_cache[cache_key]
        cached_method = [k for k, v in _METHOD_CONFIDENCE.items() if v == cached_conf]
        return (cached_heading, cached_method[0] if cached_method else "cache", cached_conf)

    heading = None
    method = "fallback"
    confidence = _CONFIDENCE_LOW

    # 3. Markdown 标题解析（.md 文件优先）[high]
    if heading is None and source_ext == ".md" and text:
        result = _extract_md_heading(text)
        if result:
            heading, method, confidence = result, "md_heading", _CONFIDENCE_HIGH

    # 4. 章节标记识别（所有文件类型）[high]
    if heading is None and text:
        result = _extract_chapter_heading(text)
        if result:
            heading, method, confidence = result, "chapter_mark", _CONFIDENCE_HIGH

    # 5. PDF 标题特征检测（配额控制）[high]
    if heading is None and source_ext == ".pdf" and text:
        if _resource_guard.check_and_record("pdf_feature"):
            @_with_timeout(_QUOTA_CONFIG["pdf_feature"]["timeout"])
            def _pdf_detect():
                return _extract_pdf_heading_by_features(text)
            result = _pdf_detect()
            if result:
                heading, method, confidence = result, "pdf_feature", _CONFIDENCE_HIGH

    # ── 以下为 medium/low 置信度方法，受 min_confidence 控制 ──

    # 6. 文件名推断 [medium]
    if heading is None and source_name and min_level >= 1:
        clean_name = re.sub(r"^[\d]+[_.\-\s]*", "", source_name)
        clean_name = re.sub(r"[_\-]+", " ", clean_name).strip()
        if clean_name and len(clean_name) <= 50:
            heading, method, confidence = clean_name, "filename", _CONFIDENCE_MEDIUM

    # 7. 首行提取 [low]
    if heading is None and text and min_level >= 2:
        first_line = text.splitlines()[0].strip()
        if (
            first_line
            and len(first_line) <= 30
            and not first_line.startswith(("#", "*", "-", "`", "```", "~~~"))
            and not first_line.isdigit()
            and _HEADING_CANDIDATE_RE.match(first_line)
            and not _ENDS_WITH_PUNCT_RE.search(first_line)
            and _non_stopword_ratio(first_line) > 0.5
        ):
            candidate = first_line
            # 内容覆盖验证
            if _validate_heading_candidate(candidate, text):
                heading, method, confidence = candidate, "first_line_filtered", _CONFIDENCE_LOW

    # 8. 关键词组合 [low]
    if heading is None and text and min_level >= 2:
        if _resource_guard.check_and_record("jieba_keyword"):
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
                heading, method, confidence = candidate, "keyword", _CONFIDENCE_LOW

    # 9. 兜底 [low]
    if heading is None and min_level >= 2:
        heading, method, confidence = "[未命名文档]", "fallback", _CONFIDENCE_LOW

    # ── 低置信度标记 ──
    if confidence == _CONFIDENCE_LOW and heading != "[未命名文档]":
        # 低置信度且通过验证 → 添加 [推测] 前缀
        heading = f"{_LOW_CONFIDENCE_PREFIX}{heading}"

    # 写入缓存
    _heading_cache[cache_key] = (heading, confidence)
    return (heading, method, confidence)


def _impute_heading_path(doc: Document, heading: Optional[str]) -> Optional[str]:
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


def _impute_category(doc: Document) -> Optional[str]:
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


# ── 结构层缺失值 ────────────────────────────────────

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
        if stripped.isdigit() or re.match(r"^\s*(?:第\s*\d+\s*页|page\s*\d+|-?\s*\d+\s*-?)\s*$", stripped, re.IGNORECASE):
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
        elif (
            2 <= len(stripped) <= 40
            and _NO_END_PUNCT_RE.search(stripped)
            and prev_blank
        ):
            # 检查下一行是否为空行
            next_blank = (i + 1 < len(lines) and not lines[i + 1].strip())
            if next_blank and not stripped.startswith(("-", "*", "+", ">", "```", "~~~", "#")):
                is_title = True

        if is_title:
            title_lines.append({
                "line_num": i,
                "text": stripped,
                "position": pos,
            })

        prev_blank = False
        pos += len(line) + 1

    return title_lines


def _tokenize_text(text: str) -> list[str]:
    """对整段文本做一次分词，返回词序列（含停用词过滤）

    一次分词，后续复用，避免重复调用 jieba。
    """
    if not text or not text.strip():
        return []
    try:
        import jieba
        return [w for w in jieba.cut(text) if w.strip() and w not in _STOPWORDS]
    except ImportError:
        # 降级：字符级
        return [c for c in text if c.strip() and c not in _STOPWORDS]


def _window_word_bag(words: list[str], start: int, size: int) -> frozenset[str]:
    """从词序列中提取一个窗口的词袋"""
    window = words[start:start + size]
    return frozenset(window)


def _semantic_segment(text: str, min_chunk: int = 500, max_chunk: int = 2000,
                      window_size: int = 50, stride: int = 25,
                      diff_threshold: float = 0.55) -> list[dict]:
    """基于滑动窗口的语义分段

    策略：
    1. 对全文本做一次 jieba 分词，得到词序列
    2. 预计算所有窗口词袋（利用重叠复用，stride < window_size 时窗口间共享词汇）
    3. 计算相邻窗口的词集 Jaccard 距离 = 1 - Jaccard相似度
    4. 距离峰值 > diff_threshold → 主题切换候选点
    5. 在候选点中按文本位置映射到字符偏移，生成分段
    6. 合并过短段落，拆分过长段落

    性能优化：
    - 全文只做一次分词（O(N)），而非逐句分词（O(N×M)）
    - 窗口词袋预计算：避免每次循环重建 frozenset
    - stride 控制计算密度，stride=25 时窗口数约为 N/25

    Args:
        text: 正文文本
        min_chunk: 最小段落字符数
        max_chunk: 最大段落字符数
        window_size: 滑动窗口大小（词数），默认 50
        stride: 滑动步进（词数），默认 25
        diff_threshold: Jaccard 距离阈值，默认 0.55（即相似度 < 0.45 时分割）

    Returns:
        分段列表 [{"position": int, "label": str, "char_count": int}]
    """
    if not text or len(text) <= min_chunk:
        return []

    # 1. 一次分词 + 建立词→字符位置映射
    words = _tokenize_text(text)
    if len(words) < window_size * 2:
        # 词数太少，无法做窗口比较
        return []

    # 建立词索引到字符偏移的映射
    # 通过在原文中逐词定位，记录每个词的起始字符位置
    word_positions: list[int] = []
    search_start = 0
    # 重新分词获取位置（使用同样的分词器）
    try:
        import jieba
        tokenizer = jieba
    except ImportError:
        tokenizer = None

    if tokenizer:
        for word in jieba.cut(text):
            if word.strip() and word not in _STOPWORDS:
                idx = text.find(word, search_start)
                if idx >= 0:
                    word_positions.append(idx)
                    search_start = idx + len(word)
    else:
        # 字符级降级
        for i, ch in enumerate(text):
            if ch.strip() and ch not in _STOPWORDS:
                word_positions.append(i)

    # 2. 预计算所有窗口词袋（避免循环中重复构建 frozenset）
    n_words = len(words)
    window_bags: list[frozenset[str]] = []
    for i in range(0, n_words - window_size + 1, stride):
        window_bags.append(frozenset(words[i:i + window_size]))

    # 3. 计算相邻窗口对 Jaccard 距离
    #    相邻对: bag[k] vs bag[k+1]，对应词索引 k*stride vs (k+1)*stride
    distances: list[tuple[int, float]] = []  # (分割点词索引, 距离)

    for k in range(len(window_bags) - 1):
        bag_left = window_bags[k]
        bag_right = window_bags[k + 1]

        if not bag_left or not bag_right:
            continue

        intersection = len(bag_left & bag_right)
        union = len(bag_left | bag_right)
        jaccard_sim = intersection / union if union > 0 else 0.0
        jaccard_dist = 1.0 - jaccard_sim

        # 分割点 = 右窗口起始词索引
        center_word_idx = (k + 1) * stride
        distances.append((center_word_idx, jaccard_dist))

    if not distances:
        return []

    # 3. 找距离峰值：大于阈值 且 大于前后邻居
    split_word_indices: list[int] = []
    for k in range(len(distances)):
        idx, dist = distances[k]
        if dist < diff_threshold:
            continue
        # 检查是否为局部峰值（大于左右邻居）
        is_peak = True
        if k > 0 and distances[k - 1][1] > dist:
            is_peak = False
        if k < len(distances) - 1 and distances[k + 1][1] > dist:
            is_peak = False
        if is_peak:
            split_word_indices.append(idx)

    if not split_word_indices:
        return []

    # 4. 将词索引映射到字符位置，生成分段
    segments: list[dict] = []
    prev_char_pos = 0

    for word_idx in split_word_indices:
        if word_idx < len(word_positions):
            char_pos = word_positions[word_idx]
        else:
            char_pos = len(text)

        # 确保分段达到最小长度
        seg_len = char_pos - prev_char_pos
        if seg_len < min_chunk:
            continue

        segments.append({
            "position": prev_char_pos,
            "label": "",
            "char_count": seg_len,
        })
        prev_char_pos = char_pos

    # 最后一段
    remaining = len(text) - prev_char_pos
    if remaining > 0:
        segments.append({
            "position": prev_char_pos,
            "label": "",
            "char_count": remaining,
        })

    # 5. 合并过短段落
    merged: list[dict] = []
    for seg in segments:
        if merged and seg["char_count"] < min_chunk:
            merged[-1]["char_count"] += seg["char_count"]
        else:
            merged.append(seg)

    # 6. 拆分过长段落
    final: list[dict] = []
    for seg in merged:
        if seg["char_count"] > max_chunk:
            n_parts = (seg["char_count"] + max_chunk - 1) // max_chunk
            for p in range(n_parts):
                final.append({
                    "position": seg["position"] + p * max_chunk,
                    "label": "",
                    "char_count": min(max_chunk, seg["char_count"] - p * max_chunk),
                })
        else:
            final.append(seg)

    # 7. 编号
    for i, seg in enumerate(final):
        seg["label"] = f"[第{i + 1}段]"

    return final if len(final) > 1 else []


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
        title_lines = _detect_pdf_title_lines(text)
        if len(title_lines) >= 2:
            # 用标题行作为分段锚点
            sections = []
            for i, tl in enumerate(title_lines):
                label = tl["text"]
                # 截断过长标题
                if len(label) > 40:
                    label = label[:40] + "…"
                sections.append({
                    "position": tl["position"],
                    "label": label,
                })
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

    # 策略3：降级 — 按空行边界分割
    paragraphs = _PARAGRAPH_BOUNDARY_RE.split(text)
    if len(paragraphs) > 1:
        sections = []
        pos = 0
        for i, para in enumerate(paragraphs):
            if para.strip():
                sections.append({
                    "position": pos,
                    "label": f"[第{i + 1}段]",
                })
            pos += len(para) + 3
        return sections if len(sections) > 1 else []

    # 策略4：降级 — 固定长度分段
    chunk_size = 1500
    sections = []
    for i in range(0, len(text), chunk_size):
        sections.append({
            "position": i,
            "label": f"[第{i // chunk_size + 1}段]",
        })
    return sections


# ── 主函数 ──────────────────────────────────────────

def _impute_single_doc(doc: Document) -> tuple[Document, list[dict]]:
    """处理单个文档的缺失值填充（可并行化）

    Returns:
        (填充后文档, 填充记录列表)
    """
    meta = doc.metadata or {}
    source = str(meta.get("source_path") or meta.get("source_file") or "unknown")
    doc_log: list[dict] = []

    # ── 内容层 ──
    content_status = _detect_content_status(doc)
    if content_status != "normal":
        doc.metadata["content_status"] = content_status

        if content_status == "empty":
            doc_log.append({
                "field": "content_status",
                "method": "mark_empty",
                "source": source,
                "value": "empty",
            })
            return doc, doc_log

        if content_status == "placeholder":
            doc.metadata["has_placeholder"] = True
            doc_log.append({
                "field": "has_placeholder",
                "method": "detect",
                "source": source,
                "value": True,
            })

        if content_status == "truncated":
            doc.metadata["truncated"] = True
            doc_log.append({
                "field": "truncated",
                "method": "detect",
                "source": source,
                "value": True,
            })
    else:
        doc.metadata["content_status"] = "normal"

    # ── 元数据层：heading ──
    heading_result = _impute_heading(doc)
    heading_filled = None
    if heading_result is not None:
        heading_filled, heading_method, heading_confidence = heading_result
        doc.metadata["heading"] = heading_filled
        doc.metadata["heading_source"] = heading_method
        doc.metadata["heading_confidence"] = heading_confidence
        doc.metadata["has_heading"] = bool(heading_filled and heading_filled != "[未命名文档]" and not heading_filled.startswith(_LOW_CONFIDENCE_PREFIX))
        doc_log.append({
            "field": "heading",
            "method": heading_method,
            "source": source,
            "value": heading_filled,
            "confidence": heading_confidence,
        })

    # ── 元数据层：heading_path ──
    heading_path_filled = _impute_heading_path(doc, heading_filled)
    if heading_path_filled is not None:
        doc.metadata["heading_path"] = heading_path_filled
        doc_log.append({
            "field": "heading_path",
            "method": "from_heading",
            "source": source,
            "value": heading_path_filled,
        })

    # ── 元数据层：category ──
    category_filled = _impute_category(doc)
    if category_filled is not None:
        doc.metadata["category"] = category_filled
        doc_log.append({
            "field": "category",
            "method": "path_infer",
            "source": source,
            "value": category_filled,
        })

    # ── 结构层：自动分段标注 ──
    sections = _impute_section_headings(doc)
    if sections:
        doc.metadata["auto_sections"] = sections
        doc.metadata["has_auto_sections"] = True
        doc_log.append({
            "field": "auto_sections",
            "method": "auto_segment",
            "source": source,
            "value": f"{len(sections)} sections",
        })

    # ── 记录审计日志 ──
    if doc_log:
        doc.metadata["_impute_log"] = doc_log

    return doc, doc_log


def impute_documents(
    documents: list[Document],
    max_workers: int = 4,
    parallel: bool = True,
) -> tuple[list[Document], list[dict]]:
    """缺失值填充主函数

    对文档集合执行三级缺失值填充：
    1. 内容层：标记空内容/占位符/截断
    2. 元数据层：填充 heading / heading_path / category
    3. 结构层：为长文档自动分段标注

    支持并行处理和资源配额控制。

    Args:
        documents: 待填充文档列表（通常是清洗后的文档）
        max_workers: 并行工作线程数，默认 4
        parallel: 是否启用并行处理，默认 True

    Returns:
        (填充后文档列表, 填充记录列表)
        填充记录: [{"field": str, "method": str, "source": str, "value": str}]
    """
    # 重置资源监控器（每次入库开始时重置配额）
    _resource_guard._counters.clear()
    _resource_guard._degraded.clear()

    filled_docs: list[Document] = []
    impute_log: list[dict] = []

    if parallel and len(documents) > 10:
        # ── 并行处理 ──
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(_impute_single_doc, doc): i
                       for i, doc in enumerate(documents)}

            results: list[tuple[int, Document, list[dict]]] = []
            for future in as_completed(futures):
                idx = futures[future]
                try:
                    doc, doc_log = future.result()
                    results.append((idx, doc, doc_log))
                except Exception as e:
                    logger.error("Impute parallel error on doc %d: %s", idx, e)

            # 按原始顺序排列
            results.sort(key=lambda x: x[0])
            for idx, doc, doc_log in results:
                if doc.metadata.get("content_status") == "empty":
                    impute_log.extend(doc_log)
                    continue
                filled_docs.append(doc)
                impute_log.extend(doc_log)
    else:
        # ── 串行处理（文档数 ≤10 或禁用并行） ──
        for doc in documents:
            doc, doc_log = _impute_single_doc(doc)

            if doc.metadata.get("content_status") == "empty":
                impute_log.extend(doc_log)
                continue

            filled_docs.append(doc)
            impute_log.extend(doc_log)

    # ── 汇总日志 ──
    if impute_log:
        filled_fields = {}
        for entry in impute_log:
            field = entry["field"]
            filled_fields[field] = filled_fields.get(field, 0) + 1
        logger.info(
            "Imputer: filled %d fields across %d docs — %s | cache=%s | guard=%s",
            len(impute_log),
            len(set(e["source"] for e in impute_log)),
            ", ".join(f"{k}:{v}" for k, v in sorted(filled_fields.items())),
            get_heading_cache_stats(),
            _resource_guard.summary(),
        )

    return filled_docs, impute_log
