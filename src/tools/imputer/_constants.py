"""imputer 的常量：正则、停用词表、分段参数档案、置信度分级。"""

from __future__ import annotations

import re
from dataclasses import dataclass

# ── 正则预编译 ──────────────────────────────────────

# 占位符检测：图片占位、附件引用、表格占位
_PLACEHOLDER_RE = re.compile(
    r"(此处|这里|见|参见|详见).{0,6}(图片|图|图示|插图|附件|附表|表格|视频)",
)

# 未闭合代码围栏
_UNCLOSED_FENCE_RE = re.compile(r"^\s*(```+|~~~+)", re.MULTILINE)

# PDF 页码行：单独一行的 "第X页" / "Page X" / "- X -" / 纯数字行
_PAGE_NUM_RE = re.compile(
    r"^\s*(?:第\s*\d+\s*页|page\s*\d+|-?\s*\d+\s*-?)\s*$",
    re.IGNORECASE | re.MULTILINE,
)

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

    window_size: int = 50  # 滑动窗口大小（词数）
    stride: int = 25  # 步进（词数）
    diff_threshold: float = 0.55  # Jaccard 距离阈值
    min_chunk: int = 500  # 最小段落字符数
    max_chunk: int = 2000  # 最大段落字符数


# 按 category / source_ext 匹配的档案表
_SEGMENT_PROFILES: dict[str, _SegmentProfile] = {
    # ── 法律/合同：段落长、主题稳定，少分割 ──
    "law": _SegmentProfile(
        window_size=80, stride=40, diff_threshold=0.65, min_chunk=800, max_chunk=3000
    ),
    "contract": _SegmentProfile(
        window_size=80, stride=40, diff_threshold=0.65, min_chunk=800, max_chunk=3000
    ),
    "regulation": _SegmentProfile(
        window_size=80, stride=40, diff_threshold=0.65, min_chunk=800, max_chunk=3000
    ),
    # ── 技术文档：段落短、主题切换快，多分割 ──
    "tech": _SegmentProfile(
        window_size=30, stride=15, diff_threshold=0.45, min_chunk=300, max_chunk=1500
    ),
    "api": _SegmentProfile(
        window_size=30, stride=15, diff_threshold=0.45, min_chunk=300, max_chunk=1500
    ),
    "code": _SegmentProfile(
        window_size=30, stride=15, diff_threshold=0.45, min_chunk=300, max_chunk=1500
    ),
    "tutorial": _SegmentProfile(
        window_size=40, stride=20, diff_threshold=0.50, min_chunk=400, max_chunk=1500
    ),
    # ── 小说/文学：连续叙事，少分割 ──
    "novel": _SegmentProfile(
        window_size=100, stride=50, diff_threshold=0.70, min_chunk=1000, max_chunk=4000
    ),
    "fiction": _SegmentProfile(
        window_size=100, stride=50, diff_threshold=0.70, min_chunk=1000, max_chunk=4000
    ),
    "literature": _SegmentProfile(
        window_size=100, stride=50, diff_threshold=0.70, min_chunk=1000, max_chunk=4000
    ),
    # ── 新闻/论文：段落分明 ──
    "news": _SegmentProfile(
        window_size=50, stride=25, diff_threshold=0.55, min_chunk=500, max_chunk=2000
    ),
    "paper": _SegmentProfile(
        window_size=50, stride=25, diff_threshold=0.55, min_chunk=500, max_chunk=2000
    ),
    "thesis": _SegmentProfile(
        window_size=50, stride=25, diff_threshold=0.55, min_chunk=500, max_chunk=2000
    ),
    # ── 教材/讲义 ──
    "textbook": _SegmentProfile(
        window_size=60, stride=30, diff_threshold=0.55, min_chunk=600, max_chunk=2500
    ),
    "lecture": _SegmentProfile(
        window_size=60, stride=30, diff_threshold=0.55, min_chunk=600, max_chunk=2500
    ),
    # ── 默认兜底 ──
    "default": _SegmentProfile(
        window_size=50, stride=25, diff_threshold=0.55, min_chunk=500, max_chunk=2000
    ),
}

# source_ext → 默认 category 映射（当 metadata 无 category 时使用）
_EXT_DEFAULT_CATEGORY: dict[str, str] = {
    ".pdf": "paper",
    ".md": "tech",
    ".txt": "default",
    ".docx": "paper",
    ".html": "news",
}


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
    r"|[\d]+\.[\d.]*"  # 1. / 1.1 / 1.1.1
    r"|[一二三四五六七八九十]+[、.]"  # 一、/ 二.
    r"|[（(][一二三四五六七八九十\d]+[)）]"  # （一）/ (2)
    r")\s*(.{1,40})"
)

# ── PDF 标题特征检测 ──
# 全大写英文行（可能为标题）
_ALL_CAPS_RE = re.compile(r"^[A-Z][A-Z\s]{2,40}$")
# 行末无句号等终结标点
_NO_END_PUNCT_RE = re.compile(r"[^。！？；：…—.!?,;:]$")

# ── 中文停用词表（首行提取质量过滤） ──
_STOPWORDS = frozenset(
    {
        "的",
        "了",
        "在",
        "是",
        "我",
        "有",
        "和",
        "就",
        "不",
        "人",
        "都",
        "一",
        "一个",
        "上",
        "也",
        "很",
        "到",
        "说",
        "要",
        "去",
        "你",
        "会",
        "着",
        "没有",
        "看",
        "好",
        "自己",
        "这",
        "他",
        "她",
        "它",
        "们",
        "那",
        "些",
        "什么",
        "怎么",
        "如何",
        "哪",
        "为什么",
        "因为",
        "所以",
        "但是",
        "而且",
        "或者",
        "如果",
        "虽然",
        "不过",
        "可以",
        "可能",
        "应该",
        "必须",
        "需要",
        "已经",
        "正在",
        "将要",
        "这个",
        "那个",
        "这些",
        "那些",
        "其",
        "之",
        "以",
        "于",
        "为",
        "与",
        "从",
        "把",
        "被",
        "让",
        "给",
        "向",
        "比",
        "等",
        "及",
    }
)

# ── 置信度分级 ──
# high: 来源确定性高（原文提取），几乎无幻觉风险
# medium: 来源有依据但非原文（文件名），低幻觉风险
# low: 来源为统计推断（关键词/首行），有幻觉风险
_CONFIDENCE_HIGH = "high"
_CONFIDENCE_MEDIUM = "medium"
_CONFIDENCE_LOW = "low"

# 低置信度 heading 的前缀标记
_LOW_CONFIDENCE_PREFIX = "[推测]"
