"""数据质量评估模块

在清洗前后对文档集合进行三维质量评估：
1. 完整性 (Completeness) — 内容是否完整、元数据是否齐全
2. 准确性 (Accuracy)     — 编码/乱码/异常字符是否消除
3. 一致性 (Consistency)   — 格式/元数据/内容是否一致

评估结果用于：
- 生成质量报告（入库时输出）
- 确定清洗优先级（质量低的文件优先处理）
- 清洗前后对比（量化清洗效果）
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from langchain_core.documents import Document

logger = logging.getLogger(__name__)

# ── 正则预编译 ──────────────────────────────────────

# 乱码检测：匹配不属于正常文本的字符
# 正常文本 = CJK汉字 + CJK标点 + 全角符号 + ASCII可打印字符
_ALLOWED_CHARS = (
    r"\u4e00-\u9fff"     # CJK 统一汉字
    r"\u3000-\u303f"     # CJK 标点符号
    r"\uff00-\uffef"     # 全角ASCII/半角片假名
    r"a-zA-Z0-9"         # ASCII 字母数字
    r"\s"                 # 空白字符
    r"\x20-\x7e"         # ASCII 可打印字符
)
_GARBAGE_RE = re.compile(f"[^{_ALLOWED_CHARS}]")

# 重复行检测
_DUPLICATE_LINE_RE = re.compile(r"^(.+)$", re.MULTILINE)

# 孤立标点（连续3个以上同类标点）
_ORPHAN_PUNCT_RE = re.compile(r"([，。！？：；、）】》])\1{2,}")

# 编码异常（替换字符 U+FFFD）
_REPLACEMENT_CHAR_RE = re.compile(r"\ufffd")

# 过短行（<5字符的非空行，可能为残留噪音）
_SHORT_NOISE_RE = re.compile(r"^[^\n]{1,4}$", re.MULTILINE)


# ── 评估指标数据结构 ────────────────────────────────

@dataclass
class QualityMetrics:
    """单文档质量指标"""

    # ── 完整性 ──
    has_content: bool = False          # 正文非空
    has_source: bool = False           # 有来源信息
    has_heading: bool = False          # 有标题/章节
    content_length: int = 0            # 正文长度
    metadata_completeness: float = 0.0 # 元数据完整度 (0~1)
    completeness_score: float = 0.0    # 完整性总分 (0~1)

    # ── 准确性 ──
    garbage_char_ratio: float = 0.0    # 乱码字符占比
    replacement_char_count: int = 0    # U+FFFD 替换字符数
    orphan_punct_count: int = 0        # 孤立标点数
    encoding_issue: bool = False       # 存在编码问题
    accuracy_score: float = 0.0        # 准确性总分 (0~1)

    # ── 一致性 ──
    duplicate_line_ratio: float = 0.0  # 重复行占比
    short_noise_ratio: float = 0.0     # 过短噪音行占比
    mixed_encoding: bool = False       # 混合编码（全角半角混用）
    consistency_score: float = 0.0     # 一致性总分 (0~1)

    # ── 综合 ──
    overall_score: float = 0.0         # 综合质量分 (0~1)
    quality_level: str = "unknown"     # excellent / good / fair / poor
    priority: int = 0                  # 清洗优先级 (1=最高, 5=最低)

    # ── 关键元数据字段（用于计算完整度）──
    _KEY_METADATA_FIELDS = [
        "source_path", "source_file", "source_ext", "source_name",
        "heading", "heading_path", "keywords", "content_type",
    ]


@dataclass
class QualityReport:
    """文档集合质量报告"""

    total_docs: int = 0
    evaluated_docs: int = 0
    skipped_docs: int = 0            # 内容过短被跳过

    # ── 集合级指标 ──
    avg_completeness: float = 0.0
    avg_accuracy: float = 0.0
    avg_consistency: float = 0.0
    avg_overall: float = 0.0

    # ── 分布 ──
    quality_distribution: dict[str, int] = field(default_factory=lambda: {
        "excellent": 0, "good": 0, "fair": 0, "poor": 0,
    })

    # ── 问题统计 ──
    docs_with_garbage: int = 0
    docs_with_encoding_issues: int = 0
    docs_with_duplicates: int = 0
    docs_missing_metadata: int = 0
    docs_missing_heading: int = 0

    # ── 清洗优先级排序 ──
    priority_files: list[dict] = field(default_factory=list)

    # ── 清洗前后对比 ──
    before_metrics: Optional["QualityReport"] = None
    improvement: Optional[dict] = None

    def summary(self) -> str:
        lines = [
            f"质量评估: {self.evaluated_docs} 篇文档",
            f"  完整性: {self.avg_completeness:.1%}  准确性: {self.avg_accuracy:.1%}  一致性: {self.avg_consistency:.1%}",
            f"  综合质量: {self.avg_overall:.1%}  等级分布: {self.quality_distribution}",
            f"  问题文档: 乱码={self.docs_with_garbage}  编码={self.docs_with_encoding_issues}  重复={self.docs_with_duplicates}  缺元数据={self.docs_missing_metadata}  缺标题={self.docs_missing_heading}",
        ]
        if self.improvement:
            lines.append(f"  清洗提升: 完整性+{self.improvement.get('completeness', 0):.1%}  准确性+{self.improvement.get('accuracy', 0):.1%}  一致性+{self.improvement.get('consistency', 0):.1%}")
        if self.priority_files:
            top3 = self.priority_files[:3]
            names = [f"{p['source']}(P{p['priority']})" for p in top3]
            lines.append(f"  清洗优先: {', '.join(names)}")
        return "\n".join(lines)


# ── 单文档评估 ──────────────────────────────────────

def evaluate_document(doc: Document) -> QualityMetrics:
    """评估单个文档的数据质量"""
    m = QualityMetrics()
    text = doc.page_content or ""
    meta = doc.metadata or {}

    # ── 完整性 ──
    m.has_content = bool(text.strip())
    m.has_source = bool(meta.get("source_path") or meta.get("source_file"))
    m.has_heading = bool(meta.get("heading") or meta.get("heading_path"))
    m.content_length = len(text.strip())

    # 元数据完整度
    filled = sum(1 for k in QualityMetrics._KEY_METADATA_FIELDS
                 if meta.get(k) not in (None, "", []))
    m.metadata_completeness = filled / len(QualityMetrics._KEY_METADATA_FIELDS)

    # 完整性得分：内容权重50% + 元数据权重30% + 标题权重20%
    content_score = min(m.content_length / 200, 1.0) if m.has_content else 0.0
    m.completeness_score = (
        content_score * 0.5
        + m.metadata_completeness * 0.3
        + (1.0 if m.has_heading else 0.0) * 0.2
    )

    # ── 准确性 ──
    if text:
        # 乱码字符占比
        garbage_chars = len(_GARBAGE_RE.findall(text))
        m.garbage_char_ratio = garbage_chars / max(len(text), 1)

        # U+FFFD 替换字符
        m.replacement_char_count = len(_REPLACEMENT_CHAR_RE.findall(text))

        # 孤立标点
        m.orphan_punct_count = len(_ORPHAN_PUNCT_RE.findall(text))

        # 编码问题标记
        m.encoding_issue = (
            m.garbage_char_ratio > 0.02
            or m.replacement_char_count > 0
        )

    # 准确性得分：乱码越少越好
    accuracy_penalty = (
        min(m.garbage_char_ratio * 10, 0.5)       # 乱码惩罚
        + (0.2 if m.replacement_char_count > 0 else 0)  # 替换字符惩罚
        + min(m.orphan_punct_count * 0.02, 0.1)   # 孤立标点惩罚
        + (0.2 if m.encoding_issue else 0)         # 编码问题惩罚
    )
    m.accuracy_score = max(0.0, 1.0 - accuracy_penalty)

    # ── 一致性 ──
    if text:
        lines = [l for l in text.splitlines() if l.strip()]

        # 重复行占比
        if lines:
            from collections import Counter
            line_counts = Counter(lines)
            duplicate_lines = sum(count - 1 for count in line_counts.values() if count > 1)
            m.duplicate_line_ratio = duplicate_lines / max(len(lines), 1)

        # 过短噪音行占比
        short_noise = len(_SHORT_NOISE_RE.findall(text))
        total_lines = len(text.splitlines()) or 1
        m.short_noise_ratio = short_noise / total_lines

        # 混合编码检查（全角半角混用）
        has_fullwidth = bool(re.search(r"[\uff01-\uff5e]", text))
        has_halfwidth = bool(re.search(r"[!~]", text))
        m.mixed_encoding = has_fullwidth and has_halfwidth

    # 一致性得分
    consistency_penalty = (
        min(m.duplicate_line_ratio * 5, 0.4)
        + min(m.short_noise_ratio * 3, 0.3)
        + (0.3 if m.mixed_encoding else 0)
    )
    m.consistency_score = max(0.0, 1.0 - consistency_penalty)

    # ── 综合得分 ──
    m.overall_score = (
        m.completeness_score * 0.35
        + m.accuracy_score * 0.35
        + m.consistency_score * 0.30
    )

    # ── 质量等级 ──
    if m.overall_score >= 0.85:
        m.quality_level = "excellent"
    elif m.overall_score >= 0.70:
        m.quality_level = "good"
    elif m.overall_score >= 0.50:
        m.quality_level = "fair"
    else:
        m.quality_level = "poor"

    # ── 清洗优先级 (1=最紧急, 5=无需清洗) ──
    if m.overall_score < 0.50:
        m.priority = 1
    elif m.overall_score < 0.65:
        m.priority = 2
    elif m.overall_score < 0.75:
        m.priority = 3
    elif m.overall_score < 0.85:
        m.priority = 4
    else:
        m.priority = 5

    return m


# ── 集合评估 ────────────────────────────────────────

def evaluate_documents(documents: list[Document]) -> tuple[QualityReport, list[QualityMetrics]]:
    """评估文档集合的数据质量

    Returns:
        (QualityReport, list[QualityMetrics]) — 报告 + 每篇文档的指标
    """
    report = QualityReport(total_docs=len(documents))
    all_metrics: list[QualityMetrics] = []

    for doc in documents:
        m = evaluate_document(doc)
        all_metrics.append(m)

        if not m.has_content or m.content_length < 10:
            report.skipped_docs += 1
            continue

        report.evaluated_docs += 1

        # 累计分布
        report.quality_distribution[m.quality_level] += 1

        # 问题统计
        if m.garbage_char_ratio > 0.01:
            report.docs_with_garbage += 1
        if m.encoding_issue:
            report.docs_with_encoding_issues += 1
        if m.duplicate_line_ratio > 0.1:
            report.docs_with_duplicates += 1
        if m.metadata_completeness < 0.5:
            report.docs_missing_metadata += 1
        if not m.has_heading:
            report.docs_missing_heading += 1

        # 清洗优先级排序
        source = str(doc.metadata.get("source_path") or doc.metadata.get("source_file") or "unknown")
        report.priority_files.append({
            "source": Path(source).name if source else "unknown",
            "priority": m.priority,
            "overall_score": round(m.overall_score, 3),
            "issues": _summarize_issues(m),
        })

    # 计算平均值
    evaluated = [m for m in all_metrics if m.has_content and m.content_length >= 10]
    if evaluated:
        n = len(evaluated)
        report.avg_completeness = sum(m.completeness_score for m in evaluated) / n
        report.avg_accuracy = sum(m.accuracy_score for m in evaluated) / n
        report.avg_consistency = sum(m.consistency_score for m in evaluated) / n
        report.avg_overall = sum(m.overall_score for m in evaluated) / n

    # 按优先级排序（优先级数字越小越紧急）
    report.priority_files.sort(key=lambda x: (x["priority"], -1 + x["overall_score"]))

    return report, all_metrics


def _summarize_issues(m: QualityMetrics) -> list[str]:
    """汇总单文档的问题列表"""
    issues: list[str] = []
    if m.garbage_char_ratio > 0.01:
        issues.append(f"乱码({m.garbage_char_ratio:.1%})")
    if m.replacement_char_count > 0:
        issues.append(f"替换字符({m.replacement_char_count})")
    if m.encoding_issue:
        issues.append("编码异常")
    if m.duplicate_line_ratio > 0.1:
        issues.append(f"重复行({m.duplicate_line_ratio:.1%})")
    if m.short_noise_ratio > 0.2:
        issues.append(f"噪音行({m.short_noise_ratio:.1%})")
    if m.mixed_encoding:
        issues.append("全角半角混用")
    if m.metadata_completeness < 0.5:
        issues.append(f"元数据缺失({m.metadata_completeness:.0%})")
    if not m.has_heading:
        issues.append("缺标题")
    if m.orphan_punct_count > 3:
        issues.append(f"孤立标点({m.orphan_punct_count})")
    return issues


# ── 清洗前后对比 ────────────────────────────────────

def compare_reports(before: QualityReport, after: QualityReport) -> dict:
    """对比清洗前后质量报告，计算提升幅度"""
    improvement = {
        "completeness": after.avg_completeness - before.avg_completeness,
        "accuracy": after.avg_accuracy - before.avg_accuracy,
        "consistency": after.avg_consistency - before.avg_consistency,
        "overall": after.avg_overall - before.avg_overall,
        "garbage_fixed": before.docs_with_garbage - after.docs_with_garbage,
        "encoding_fixed": before.docs_with_encoding_issues - after.docs_with_encoding_issues,
        "duplicates_fixed": before.docs_with_duplicates - after.docs_with_duplicates,
        "quality_upgrade": {
            level: after.quality_distribution.get(level, 0) - before.quality_distribution.get(level, 0)
            for level in ("excellent", "good", "fair", "poor")
        },
    }
    after.improvement = improvement
    after.before_metrics = before
    return improvement


# ── 清洗优先级建议 ──────────────────────────────────

def suggest_cleaning_priority(documents: list[Document]) -> list[dict]:
    """根据质量评估结果，返回清洗优先级排序

    Returns:
        按优先级排序的文件列表，每个条目包含：
        - source: 文件名
        - priority: 1~5 (1=最紧急)
        - overall_score: 综合质量分
        - issues: 问题列表
        - suggested_actions: 建议的清洗操作
    """
    report, metrics_list = evaluate_documents(documents)

    results: list[dict] = []
    for doc, m in zip(documents, metrics_list):
        source = str(doc.metadata.get("source_path") or doc.metadata.get("source_file") or "unknown")
        results.append({
            "source": Path(source).name if source else "unknown",
            "priority": m.priority,
            "overall_score": round(m.overall_score, 3),
            "completeness": round(m.completeness_score, 3),
            "accuracy": round(m.accuracy_score, 3),
            "consistency": round(m.consistency_score, 3),
            "issues": _summarize_issues(m),
            "suggested_actions": _suggest_actions(m),
        })

    results.sort(key=lambda x: (x["priority"], -1 + x["overall_score"]))
    return results


def _suggest_actions(m: QualityMetrics) -> list[str]:
    """根据质量问题建议清洗操作"""
    actions: list[str] = []
    if m.garbage_char_ratio > 0.01 or m.replacement_char_count > 0:
        actions.append("乱码清理 + 编码规范化(NFKC)")
    if m.duplicate_line_ratio > 0.1:
        actions.append("重复行去重")
    if m.short_noise_ratio > 0.2:
        actions.append("噪音短行过滤")
    if m.mixed_encoding:
        actions.append("全角半角统一")
    if m.orphan_punct_count > 3:
        actions.append("孤立标点修正")
    if not m.has_heading:
        actions.append("标题回填/结构化增强")
    if m.metadata_completeness < 0.5:
        actions.append("元数据补全")
    if m.content_length < 50:
        actions.append("过短文档合并或标记")
    if not actions and m.priority >= 4:
        actions.append("无需额外清洗")
    return actions
