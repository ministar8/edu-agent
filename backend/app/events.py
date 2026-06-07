"""知识追踪事件总线

解耦业务逻辑（RAG问答 / 批改 / 出题）与知识追踪服务。
业务代码只负责 emit(TrackingEvent)，追踪服务 subscribe 后自行处理。
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger(__name__)

# ── Delta 精确表 ──────────────────────────────────────────────
# (base_delta, difficulty_weight, outcome_weight)
# 正向 delta: 难度越高加分越多（攻克难题 = 更大进步）
# 负向 delta: 难度越高扣分越少（难题做错情有可原）

DELTA_TABLE: dict[str, tuple[float, float, float]] = {
    # event_type              base    d_wt    o_wt
    "qa_high_confidence":   (+0.06,  1.0,   1.0),    # governance.confidence = high
    "qa_low_confidence":    (+0.00,  1.0,   1.0),    # governance.confidence ≠ high → 不加分
    "quiz_correct":         (+0.10,  1.0,   1.0),    # 做题正确
    "quiz_partial":         (+0.03,  1.0,   0.5),    # 部分正确
    "quiz_wrong":           (-0.06,  1.0,   1.0),    # 做题错误
    "grading_excellent":    (+0.12,  1.0,   1.0),    # score ≥ 80%
    "grading_pass":         (+0.05,  1.0,   1.0),    # 50% ≤ score < 80%
    "grading_fail":         (-0.08,  1.0,   1.0),    # score < 50%
}


def compute_delta(event_type: str, difficulty: float, outcome: float) -> float:
    """计算掌握度变化量

    delta = base × difficulty_weight × difficulty × outcome_weight × outcome

    正向: 难度放大（难题做对进步更大）
    负向: 难度缩小（难题做错扣分更少）
    """
    entry = DELTA_TABLE.get(event_type)
    if entry is None:
        logger.warning("Unknown event_type: %s, delta=0", event_type)
        return 0.0
    base, d_wt, o_wt = entry

    if base > 0:
        return base * d_wt * difficulty * o_wt * max(outcome, 0.3)
    else:
        return base * d_wt * (1.0 / difficulty) * o_wt * outcome


# ── 事件定义 ──────────────────────────────────────────────────

@dataclass
class TrackingEvent:
    """知识追踪事件"""
    event_type: str                          # DELTA_TABLE 中的 key
    user_id: int
    knowledge_point_ids: list[int]           # Registry ID 列表（入库预打标签）
    category: str                            # 学科
    difficulty: float = 1.0                  # 1.0(基础) / 1.3(理解) / 1.6(综合) / 2.0(创新)
    outcome: float = 1.0                     # 0.0~1.0
    metadata: dict[str, Any] = field(default_factory=dict)


# ── 事件总线 ──────────────────────────────────────────────────

_handlers: dict[str, list[Callable]] = {}


def subscribe(event_type: str, handler: Callable) -> None:
    """订阅事件类型"""
    _handlers.setdefault(event_type, []).append(handler)


async def emit(event: TrackingEvent) -> None:
    """发射事件，异步调用所有订阅者

    异常不会中断其他 handler，但会记录日志。
    """
    handlers = _handlers.get(event.event_type, [])
    if not handlers:
        return
    for handler in handlers:
        try:
            result = handler(event)
            if asyncio.iscoroutine(result):
                await result
        except Exception as e:
            logger.error(
                "Event handler error: event_type=%s handler=%s error=%s",
                event.event_type, getattr(handler, "__name__", "?"), e,
                exc_info=True,
            )


def emit_sync(event: TrackingEvent) -> None:
    """同步发射事件（在非 async 上下文中使用，如 ingest 流程）

    注意：handler 如果是 async 函数，会创建 task 但不等待完成。
    """
    handlers = _handlers.get(event.event_type, [])
    if not handlers:
        return
    for handler in handlers:
        try:
            result = handler(event)
            if asyncio.iscoroutine(result):
                try:
                    loop = asyncio.get_running_loop()
                    loop.create_task(result)
                except RuntimeError:
                    logger.warning("Cannot schedule async handler in sync context, event dropped: %s", event.event_type)
        except Exception as e:
            logger.error(
                "Event handler error (sync): event_type=%s handler=%s error=%s",
                event.event_type, getattr(handler, "__name__", "?"), e,
                exc_info=True,
            )


# ── 辅助：从检索结果提取 knowledge_point_ids ────────────────

def _resolve_kp_ids_from_registry(
    names: list[str] | None = None,
    source_files: list[str] | None = None,
    heading_paths: list[str] | None = None,
) -> list[int]:
    """从 Registry 中匹配知识点 ID

    回退机制：当 chunk metadata 中没有预打 knowledge_point_ids 标签时，
    通过文件名、heading 路径与 Registry 中的记录匹配。

    匹配优先级：
      1. name 精确匹配
      2. source_file LIKE 匹配
      3. heading_path 前缀匹配

    Args:
        names: 知识点名称列表（从 source 文件名中提取）
        source_files: 来源文件路径列表
        heading_paths: heading 层级路径列表

    Returns:
        去重的 knowledge_point registry ID 列表
    """
    kp_ids: list[int] = []
    seen: set[int] = set()
    names = names or []
    source_files = source_files or []
    heading_paths = heading_paths or []

    if not names and not source_files and not heading_paths:
        return []

    try:
        from app.db.models import KnowledgePointRegistry
        from app.db.session import SessionLocal

        def _like_escape(value: str) -> str:
            """Escape SQL LIKE wildcards to prevent injection."""
            return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")

        with SessionLocal() as db:
            for name in names:
                # 精确匹配名称
                row = db.query(KnowledgePointRegistry).filter(
                    KnowledgePointRegistry.name == name,
                ).first()
                if row and row.id not in seen:
                    seen.add(row.id)
                    kp_ids.append(row.id)
                    continue
                # LIKE 匹配 source_file
                rows = db.query(KnowledgePointRegistry).filter(
                    KnowledgePointRegistry.source_file.like(f"%{_like_escape(name)}%", escape="\\"),
                ).all()
                for row in rows:
                    if row.id not in seen:
                        seen.add(row.id)
                        kp_ids.append(row.id)

            for sf in source_files:
                rows = db.query(KnowledgePointRegistry).filter(
                    KnowledgePointRegistry.source_file.like(f"%{_like_escape(sf)}%", escape="\\"),
                ).all()
                for row in rows:
                    if row.id not in seen:
                        seen.add(row.id)
                        kp_ids.append(row.id)

            for hp in heading_paths:
                rows = db.query(KnowledgePointRegistry).filter(
                    KnowledgePointRegistry.heading_path.like(f"%{_like_escape(hp)}%", escape="\\"),
                ).all()
                for row in rows:
                    if row.id not in seen:
                        seen.add(row.id)
                        kp_ids.append(row.id)
    except Exception as e:
        logger.debug("Registry fallback lookup failed (non-critical): %s", e)

    return kp_ids


def _extract_names_from_source(source: str) -> str:
    """从 source 文件名中提取知识点名称候选

    "数据结构/线性表/栈和队列.md" → "栈和队列"
    "线性表.md" → "线性表"
    """
    name = source.rsplit(".", 1)[0] if "." in source else source
    name = name.rsplit("/", 1)[-1] if "/" in name else name
    return name.strip()


def extract_kp_ids_from_docs(docs: list) -> list[int]:
    """从检索到的 Document 列表中提取去重的 knowledge_point_ids

    优先从 doc.metadata["knowledge_point_ids"] 读取（入库时预打标签）；
    若无标签则回退到 Registry 匹配（通过 source_file / heading_path）。
    """
    kp_ids: list[int] = []
    seen: set[int] = set()

    # 路径1：预打标签（ingest 时写入的 metadata）
    fallback_names: list[str] = []
    fallback_sources: list[str] = []
    fallback_headings: list[str] = []

    for doc in docs:
        metadata = getattr(doc, "metadata", {}) or {}
        raw = metadata.get("knowledge_point_ids", "[]")
        try:
            ids = json.loads(raw) if isinstance(raw, str) else raw
            if ids:
                for kp_id in ids:
                    if isinstance(kp_id, int) and kp_id not in seen:
                        seen.add(kp_id)
                        kp_ids.append(kp_id)
                continue  # 有预打标签就不再回退
        except (json.JSONDecodeError, TypeError):
            pass

        # 收集回退信息
        source_file = str(metadata.get("source_file") or "")
        heading_path = str(metadata.get("section.path") or metadata.get("heading_path") or "")
        if source_file:
            fallback_sources.append(source_file)
            fallback_names.append(_extract_names_from_source(source_file))
        if heading_path:
            fallback_headings.append(heading_path)

    # 路径2：Registry 回退匹配（无预打标签时）
    if not kp_ids and (fallback_names or fallback_sources or fallback_headings):
        resolved = _resolve_kp_ids_from_registry(
            names=fallback_names,
            source_files=fallback_sources,
            heading_paths=fallback_headings,
        )
        for kp_id in resolved:
            if kp_id not in seen:
                seen.add(kp_id)
                kp_ids.append(kp_id)

    return kp_ids


def extract_kp_ids_from_steps(steps: list[dict]) -> list[int]:
    """从 agent_steps 列表中提取去重的 knowledge_point_ids

    两层提取：
      1. JSON 解析 output_data（用于未来返回结构化数据的工具）
      2. 从 sources 文件名匹配 Registry（回退方案，对应当前文本输出）
    """
    kp_ids: list[int] = []
    seen: set[int] = set()

    fallback_names: list[str] = []
    fallback_sources: list[str] = []

    for step in steps:
        # 路径1：尝试 JSON 解析 output_data
        output = step.get("output_data", "")
        if output:
            try:
                data = json.loads(output) if isinstance(output, str) else output
                if isinstance(data, dict):
                    ids = data.get("knowledge_point_ids", [])
                    for kp_id in ids:
                        if isinstance(kp_id, int) and kp_id not in seen:
                            seen.add(kp_id)
                            kp_ids.append(kp_id)
            except (json.JSONDecodeError, TypeError):
                logger.debug("Event data JSON parse skipped (non-critical)")

        # 路径2：从 sources 提取文件名，收集用于 Registry 回退
        for source in step.get("sources", []):
            if not source:
                continue
            name = _extract_names_from_source(source)
            if name and name not in fallback_names:
                fallback_names.append(name)
            if source not in fallback_sources:
                fallback_sources.append(source)

    # 回退：从文件名匹配 Registry
    if not kp_ids and (fallback_names or fallback_sources):
        resolved = _resolve_kp_ids_from_registry(
            names=fallback_names,
            source_files=fallback_sources,
        )
        for kp_id in resolved:
            if kp_id not in seen:
                seen.add(kp_id)
                kp_ids.append(kp_id)

    return kp_ids
