"""知识点标签模块

入库时从 chunk 的 heading_path 提取知识点，写入 KnowledgePointRegistry，
并将 knowledge_point_ids / knowledge_point_names 回写进 chunk metadata。

粒度规则：
  heading_path = "数据结构 > 线性表 > 链表"
    segments[0] = 学科（不追踪）
    segments[1] = 章（聚合统计用，不独立追踪）
    segments[2] = 知识点 ← 追踪粒度

  heading_level ≥ 3 的子节：上溯到最近的 level-2 section title 作为知识点归属。
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from langchain_core.documents import Document

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# ── 学科推断 ──────────────────────────────────────────────────

_SOURCE_CATEGORY_MAP: dict[str, str] = {
    "data_structure": "data_structure",
    "computer_organization": "computer_organization",
    "operating_system": "operating_system",
    "computer_network": "computer_network",
    "questions": "questions",
    "learning_paths": "learning_paths",
    "answers": "answers",
}

# source_file 路径中的目录名 → category
# 例如 "data_structure/02-线性表.md" → "data_structure"


def _infer_category(source_file: str, fallback_category: str = "") -> str:
    """从 source_file 路径推断学科分类"""
    parts = source_file.replace("\\", "/").split("/")
    if len(parts) >= 2:
        dir_name = parts[0]
        if dir_name in _SOURCE_CATEGORY_MAP:
            return dir_name
    return fallback_category


# ── heading_path 解析 ─────────────────────────────────────────

def _parse_heading_path(heading_path: str) -> tuple[str, str, str]:
    """解析 heading_path → (subject, chapter, topic)

    "数据结构 > 线性表 > 链表" → ("数据结构", "线性表", "链表")
    "数据结构 > 线性表"         → ("数据结构", "", "线性表")
    "数据结构"                  → ("", "", "数据结构")
    ""                          → ("", "", "")
    """
    segments = [s.strip() for s in heading_path.split(">") if s.strip()]
    if len(segments) >= 3:
        return segments[0], segments[1], segments[2]
    elif len(segments) == 2:
        return segments[0], "", segments[1]
    elif len(segments) == 1:
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
    """从 heading_path 推断难度

    Returns:
        (difficulty, matched) — matched=True 表示匹配到了关键词
    """
    if not heading_path:
        return 1.0, False

    # 优先匹配高难度关键词
    for difficulty, keywords in _DIFFICULTY_RULES:
        for kw in keywords:
            if kw in heading_path:
                return difficulty, True

    return 1.0, False


def _default_difficulty(heading_level: int, heading_path: str = "") -> tuple[float, str]:
    """推断难度 + 来源标记

    优先从 heading_path 关键词推断，匹配到则 difficulty_source='auto'。
    未匹配则按 heading_level 兜底，difficulty_source='auto'。

    Returns:
        (difficulty, difficulty_source)
    """
    # 优先关键词匹配
    difficulty, matched = infer_difficulty_from_heading(heading_path)
    if matched:
        return difficulty, "auto"

    # 兜底：按 heading_level
    if heading_level <= 1:
        return 1.0, "auto"
    elif heading_level == 2:
        return 1.3, "auto"
    else:
        return 1.6, "auto"


# ── 核心：为单个 chunk 打标签 ─────────────────────────────────

def _tag_single_chunk(
    chunk: Document,
    db: Session,
    fallback_category: str = "",
) -> list[int]:
    """为单个 chunk 解析知识点，写入 Registry，返回 ID 列表"""
    from app.db.models import KnowledgePointRegistry

    heading_path = chunk.metadata.get("section.path", "") or chunk.metadata.get("heading_path", "")
    heading_level = chunk.metadata.get("section.heading_level", 0) or chunk.metadata.get("heading_level", 0)
    source_file = chunk.metadata.get("source_file", "")

    category = _infer_category(source_file, fallback_category)
    _subject, chapter, topic = _parse_heading_path(heading_path)

    kp_ids: list[int] = []
    kp_names: list[str] = []

    # 1. 知识点级标签
    if topic:
        kp = db.query(KnowledgePointRegistry).filter(
            KnowledgePointRegistry.name == topic,
            KnowledgePointRegistry.category == category,
        ).first()
        if not kp:
            diff, diff_src = _default_difficulty(heading_level, heading_path)
            kp = KnowledgePointRegistry(
                name=topic,
                category=category,
                chapter=chapter,
                heading_path=heading_path,
                difficulty=diff,
                difficulty_source=diff_src,
                kg_node=False,
                source_file=source_file,
            )
            db.add(kp)
            db.flush()
        kp_ids.append(kp.id)
        kp_names.append(kp.name)

    # 2. 章级标签（用于聚合统计，chapter 非空且与 topic 不同时才记录）
    if chapter and chapter != topic:
        ch_kp = db.query(KnowledgePointRegistry).filter(
            KnowledgePointRegistry.name == chapter,
            KnowledgePointRegistry.category == category,
            KnowledgePointRegistry.chapter == "",
        ).first()
        if not ch_kp:
            ch_path = heading_path.rsplit(">", 1)[0].strip() if ">" in heading_path else heading_path
            ch_diff, ch_diff_src = _default_difficulty(1, ch_path)
            ch_kp = KnowledgePointRegistry(
                name=chapter,
                category=category,
                chapter="",
                heading_path=ch_path,
                difficulty=ch_diff,
                difficulty_source=ch_diff_src,
                kg_node=False,
                source_file=source_file,
            )
            db.add(ch_kp)
            db.flush()
        kp_ids.append(ch_kp.id)
        kp_names.append(ch_kp.name)

    return kp_ids


def tag_chunks_with_knowledge_points(
    chunks: list[Document],
    fallback_category: str = "",
) -> list[Document]:
    """为 chunk 列表打知识点标签

    从每个 chunk 的 section.path 提取知识点，写入 KnowledgePointRegistry，
    并将 knowledge_point_ids 和 knowledge_point_names 写入 chunk.metadata。

    Args:
        chunks: 已 split + enhance 的 chunk 列表
        fallback_category: 当 source_file 无法推断学科时的回退值

    Returns:
        原地修改 chunks 的 metadata，返回同一列表
    """
    from app.db.session import SessionLocal

    db: Session = SessionLocal()
    try:
        tagged_count = 0
        for chunk in chunks:
            kp_ids = _tag_single_chunk(chunk, db, fallback_category)
            if kp_ids:
                chunk.metadata["knowledge_point_ids"] = json.dumps(kp_ids)
                # 同时存可读名称 + 难度信息，方便检索时使用
                kp_names = []
                kp_difficulties = []
                from app.db.models import KnowledgePointRegistry
                for kp_id in kp_ids:
                    kp = db.get(KnowledgePointRegistry, kp_id)
                    if kp:
                        kp_names.append(kp.name)
                        kp_difficulties.append(kp.difficulty)
                chunk.metadata["knowledge_point_names"] = json.dumps(kp_names, ensure_ascii=False)
                # 注入难度到 chunk metadata（供检索时使用）
                if kp_difficulties:
                    chunk.metadata["difficulty"] = max(kp_difficulties)
                    chunk.metadata["difficulty_source"] = "auto"
                tagged_count += 1
            else:
                chunk.metadata["knowledge_point_ids"] = "[]"
                chunk.metadata["knowledge_point_names"] = "[]"
        db.commit()
        logger.info("Tagged %d/%d chunks with knowledge point IDs", tagged_count, len(chunks))
    except Exception:
        db.rollback()
        logger.error("Failed to tag chunks with knowledge points", exc_info=True)
        # 不中断 ingest 流程，只是标签缺失
        for chunk in chunks:
            chunk.metadata.setdefault("knowledge_point_ids", "[]")
            chunk.metadata.setdefault("knowledge_point_names", "[]")
    finally:
        db.close()

    return chunks
