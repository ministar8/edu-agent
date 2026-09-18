"""知识点标签模块

入库时从 chunk 的 heading_path 提取知识点，写入 chunk metadata
（knowledge_point_names / difficulty），不再维护 KnowledgePointRegistry 表。

粒度规则：
  heading_path = "数据结构 > 线性表 > 链表"
    segments[0] = 学科（不追踪）
    segments[1] = 章（聚合统计用，不独立追踪）
    segments[2] = 知识点 ← 追踪粒度
"""

from __future__ import annotations

import json
import logging

from langchain_core.documents import Document

logger = logging.getLogger(__name__)

# ── heading_path 解析 ─────────────────────────────────────────


def _parse_heading_path(heading_path: str) -> tuple[str, str, str]:
    """解析 heading_path → (subject, chapter, topic)。"""
    segments = [s.strip() for s in heading_path.split(">") if s.strip()]
    if len(segments) >= 3:
        return segments[0], segments[1], segments[2]
    if len(segments) == 2:
        return segments[0], "", segments[1]
    if len(segments) == 1:
        return "", "", segments[0]
    return "", "", ""


# ── 难度推断 ────────────────────────────────────────────────

# 难度关键词 → 难度值（优先匹配高难度）
_DIFFICULTY_RULES: list[tuple[float, list[str]]] = [
    (2.0, ["创新", "优化", "拓展", "高级", "深入", "探究", "挑战"]),
    (1.6, ["综合", "应用", "分析", "设计", "实现", "计算", "算法实现", "编程"]),
    (1.3, ["理解", "掌握", "原理", "特征", "性质", "定义", "方法", "技术"]),
    (1.0, ["基础", "入门", "概述", "概念", "基本", "初识", "简介", "导论", "认识"]),
]


def infer_difficulty_from_heading(heading_path: str) -> tuple[float, bool]:
    """从 heading_path 推断难度，返回 (difficulty, matched)。"""
    if not heading_path:
        return 1.0, False
    for difficulty, keywords in _DIFFICULTY_RULES:
        if any(kw in heading_path for kw in keywords):
            return difficulty, True
    return 1.0, False


def _default_difficulty(heading_level: int, heading_path: str = "") -> tuple[float, str]:
    """推断难度 + 来源标记，返回 (difficulty, difficulty_source)。"""
    difficulty, matched = infer_difficulty_from_heading(heading_path)
    if matched:
        return difficulty, "auto"
    if heading_level <= 1:
        return 1.0, "auto"
    if heading_level == 2:
        return 1.3, "auto"
    return 1.6, "auto"


# ── 核心：为单个 chunk 打标签 ─────────────────────────────────


def _tag_single_chunk(chunk: Document) -> tuple[list[str], float, str]:
    """解析单个 chunk 的知识点名与难度，返回 (names, difficulty, difficulty_source)。"""
    heading_path = chunk.metadata.get("section.path", "") or chunk.metadata.get("heading_path", "")
    heading_level = chunk.metadata.get("section.heading_level", 0) or chunk.metadata.get(
        "heading_level", 0
    )
    _subject, chapter, topic = _parse_heading_path(heading_path)

    names: list[str] = []
    if topic:
        names.append(topic)
    if chapter and chapter != topic:
        names.append(chapter)

    difficulty, diff_src = _default_difficulty(heading_level, heading_path)
    return names, difficulty, diff_src


def tag_chunks_with_knowledge_points(
    chunks: list[Document],
    fallback_category: str = "",
) -> list[Document]:
    """为 chunk 列表打知识点标签（写入 metadata，不再注册 DB）。

    Args:
        chunks: 已 split + enhance 的 chunk 列表
        fallback_category: 未使用（保留签名以兼容调用方）

    Returns:
        原地修改 chunks 的 metadata，返回同一列表
    """
    tagged_count = 0
    for chunk in chunks:
        names, difficulty, diff_src = _tag_single_chunk(chunk)
        chunk.metadata["knowledge_point_names"] = json.dumps(names, ensure_ascii=False)
        chunk.metadata["difficulty"] = difficulty
        chunk.metadata["difficulty_source"] = diff_src
        if names:
            tagged_count += 1
    logger.info("Tagged %d/%d chunks with knowledge points", tagged_count, len(chunks))
    return chunks
