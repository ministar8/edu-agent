"""知识点标签模块

入库时从 chunk 的 ``section.path`` 提取知识点，写入 chunk metadata
（``knowledge_points`` / ``difficulty`` / ``difficulty_source``），
不再维护 KnowledgePointRegistry 表。

粒度规则（``section.path`` 由 splitter 产出，**带外层方括号、不含学科前缀**）：

    section.path = "[绪论 > 2.数据结构三要素 > 四种存储结构对比]"
      第 1 段 = 章（聚合统计用）
      第 2 段 = 节（次一级聚合）
      第 3 段 = 小节 ← **追踪粒度**（最具体）

段数不足时以「最细的一级」充当第 3 段，保证调用方总能拿到追踪粒度。

字段名与格式的约定见 ``rag/_metadata_spec.py``；消费方是 ``rag/evidence.py``。
"""

from __future__ import annotations

import json
import logging

from langchain_core.documents import Document

logger = logging.getLogger(__name__)

# ── heading_path 解析 ─────────────────────────────────────────


def _parse_heading_path(heading_path: str) -> tuple[str, str, str]:
    """解析 ``section.path`` → ``(第 1 段, 第 2 段, 第 3 段)``，缺失的层级返回空串。

    ``section.path`` 由 ``splitter._build_heading_context`` 产出，**格式带外层方括号、
    且不含学科前缀**（见 ``rag/_metadata_spec.py`` 中 ``section.path`` 的定义）：

        "[绪论 > 2.数据结构三要素 > 四种存储结构对比]"
            → ("绪论", "2.数据结构三要素", "四种存储结构对比")

    按 ``section.depth`` 的约定：第 1 段 = 章、第 2 段 = 节、第 3 段 = 小节。

    ⚠️ **必须先剥掉方括号**：``splitter`` 只负责加包装、不负责拆。不剥的话末段会带上
    ``]``（实测曾污染 77% 的知识点名，如 ``"1.基本概念]"``）。
    ``enhancer._extract_heading_keywords`` 已做 ``strip("[]")``，此处与之对齐。

    段数不足时按「**最细的一级充当第 3 段**」退化，保证调用方总能拿到追踪粒度。
    """
    segments = [s.strip().strip("[]").strip() for s in heading_path.split(">")]
    segments = [s for s in segments if s]
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
    # 段位语义（见 _metadata_spec）：第 1 段=章、第 2 段=节、第 3 段=小节
    _chapter, section_title, topic = _parse_heading_path(heading_path)

    # 知识点名按「由细到粗」排列：最具体的一级在前（追踪粒度），次一级作聚合用。
    names: list[str] = []
    if topic:
        names.append(topic)
    if section_title and section_title != topic:
        names.append(section_title)

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

    写入的字段见 ``rag/_metadata_spec.py``：``knowledge_points`` / ``difficulty`` /
    ``difficulty_source``。

    ★ 字段名必须是 ``knowledge_points`` —— ``rag/evidence.py`` 正是按这个名字读的
    （``meta.get("knowledge_points")``）。此前这里写的是 ``knowledge_point_names``，
    **无任何消费方**，导致 ``EvidenceDoc.knowledge_points`` 恒为空、标注结果从未进入
    检索链（2026-09-24 修复）。改名后**需重新入库**，既有索引才会带上该字段。
    """
    tagged_count = 0
    for chunk in chunks:
        names, difficulty, diff_src = _tag_single_chunk(chunk)
        # 存 JSON 字符串而非 list：Chroma metadata 只接受 str/int/float/bool，
        # list 会被 `_metadata_spec.sanitize_for_chroma` 丢掉。
        # 读取端 `evidence._parse_knowledge_points` 会按 JSON 解析回来。
        chunk.metadata["knowledge_points"] = json.dumps(names, ensure_ascii=False)
        chunk.metadata["difficulty"] = difficulty
        chunk.metadata["difficulty_source"] = diff_src
        if names:
            tagged_count += 1
    logger.info("Tagged %d/%d chunks with knowledge points", tagged_count, len(chunks))
    return chunks
