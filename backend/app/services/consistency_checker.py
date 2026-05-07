"""数据一致性检查与孤儿清理服务

定期检测 ChromaDB 与 Neo4j 之间的数据不一致：
- 孤儿节点：KG 中存在但 ChromaDB 中无对应文档的节点
- 支持自动清理孤儿节点
- 支持手动触发 API 检查
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

logger = logging.getLogger(__name__)

# 默认检查间隔（秒）
DEFAULT_CHECK_INTERVAL = 3600  # 1 小时


def _get_indexed_files() -> set[str]:
    """从 ChromaDB 所有集合中提取已索引的 source_file 集合"""
    from app.rag.vectorstore import get_vector_store_manager

    vsm = get_vector_store_manager()
    indexed: set[str] = set()
    for col_name in vsm.list_collections():
        try:
            collection = vsm.client.get_collection(col_name)
            if collection.count() == 0:
                continue
            result = collection.get(include=["metadatas"])
            for meta in result.get("metadatas", []) or []:
                if meta and meta.get("source_file"):
                    indexed.add(meta["source_file"])
        except Exception as e:
            logger.warning("Failed to read collection '%s': %s", col_name, e)
    return indexed


def check_consistency(category: str = "") -> dict[str, Any]:
    """执行一致性检查

    Args:
        category: 限定分类（空字符串表示检查全部）

    Returns:
        健康检查报告
    """
    from app.rag.knowledge_graph import get_kg_manager

    start = time.perf_counter()
    indexed_files = _get_indexed_files()
    report = get_kg_manager().health_check(indexed_files, category=category)
    report["check_duration_ms"] = round((time.perf_counter() - start) * 1000, 1)
    report["indexed_files_count"] = len(indexed_files)

    if report["orphan_nodes"] > 0:
        logger.warning(
            "Consistency check found %d orphan nodes (total: %d, ratio: %.2f%%)",
            report["orphan_nodes"],
            report["total_nodes"],
            (1 - report["consistency_ratio"]) * 100,
        )
    else:
        logger.info("Consistency check passed: %d nodes, no orphans", report["total_nodes"])

    return report


def cleanup_orphans(category: str = "") -> dict[str, Any]:
    """检测并清理孤儿节点

    Args:
        category: 限定分类（空字符串表示清理全部）

    Returns:
        清理报告
    """
    from app.rag.knowledge_graph import get_kg_manager

    start = time.perf_counter()
    kg_manager = get_kg_manager()
    indexed_files = _get_indexed_files()
    orphans = kg_manager.find_orphan_nodes(indexed_files, category=category)

    if not orphans:
        return {"cleaned": 0, "orphans_found": 0}

    # 按分类分组删除
    cleaned = 0
    by_category: dict[str, list[str]] = {}
    for orphan in orphans:
        cat = orphan.get("category", "unknown")
        by_category.setdefault(cat, []).append(orphan["name"])

    for cat, names in by_category.items():
        try:
            for name in names:
                kg_manager.delete_node(name, category=cat)
                cleaned += 1
            logger.info("Cleaned %d orphan nodes in category '%s'", len(names), cat)
        except Exception as e:
            logger.error("Failed to clean orphans in category '%s': %s", cat, e)

    duration = round((time.perf_counter() - start) * 1000, 1)
    return {
        "orphans_found": len(orphans),
        "cleaned": cleaned,
        "by_category": {cat: len(names) for cat, names in by_category.items()},
        "duration_ms": duration,
    }


async def _periodic_check(interval: int = DEFAULT_CHECK_INTERVAL) -> None:
    """后台定时检查任务"""
    while True:
        try:
            await asyncio.sleep(interval)
            logger.info("Running periodic consistency check...")
            report = await asyncio.to_thread(check_consistency)
            if report["orphan_nodes"] > 0:
                logger.warning(
                    "Periodic check: %d orphans detected, auto-cleaning",
                    report["orphan_nodes"],
                )
                result = await asyncio.to_thread(cleanup_orphans)
                logger.info("Auto-clean result: %s", result)
        except asyncio.CancelledError:
            logger.info("Periodic consistency check cancelled")
            break
        except Exception as e:
            logger.error("Periodic consistency check failed: %s", e)


# 全局任务句柄
_periodic_task: asyncio.Task | None = None


def start_periodic_check(interval: int = DEFAULT_CHECK_INTERVAL) -> None:
    """启动定时检查后台任务"""
    global _periodic_task
    if _periodic_task is not None and not _periodic_task.done():
        logger.warning("Periodic check already running")
        return

    _periodic_task = asyncio.ensure_future(_periodic_check(interval))
    logger.info("Started periodic consistency check (interval=%ds)", interval)


def stop_periodic_check() -> None:
    """停止定时检查后台任务"""
    global _periodic_task
    if _periodic_task and not _periodic_task.done():
        _periodic_task.cancel()
        _periodic_task = None
        logger.info("Stopped periodic consistency check")
