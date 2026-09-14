"""一键重建全量索引 CLI

用法（需 PYTHONPATH=src 或从 src 目录运行）:
    python -m rag.ingest                      # 扫描所有分类目录，增量入库
    python -m rag.ingest --category data_structure   # 只处理数据结构分类
    python -m rag.ingest --rebuild            # 先清空再重建（全量重建）
"""

from __future__ import annotations

import argparse
import logging
import os
import time

from core.settings import settings
from rag.cleaner import clean_documents
from rag.enhancer import enhance_documents
from rag.knowledge_tagger import tag_chunks_with_knowledge_points
from rag.loader import SUPPORTED_EXTENSIONS, load_single_file
from rag.metrics import metrics
from rag.splitter import split_documents
from rag.vectorstore import get_vector_store_manager

logger = logging.getLogger(__name__)

DEFAULT_CATEGORIES = [
    "data_structure",
    "computer_organization",
    "operating_system",
    "computer_network",
    "questions",
    "learning_paths",
]


def ingest_category(category: str, rebuild: bool = False) -> dict:
    """处理单个分类目录。"""
    dir_path = os.path.join(settings.KNOWLEDGE_DIR, category)
    if not os.path.isdir(dir_path):
        return {"category": category, "files": 0, "chunks": 0, "errors": 0, "skipped": True}

    vector_store_manager = get_vector_store_manager()

    if rebuild:
        logger.info("  [rebuild] 清空集合 '%s'...", category)
        vector_store_manager.delete_collection(category)

    total_chunks = 0
    total_files = 0
    total_errors = 0
    category_start = time.perf_counter()

    all_files: list[str] = []
    for root, _dirs, files in os.walk(dir_path):
        for filename in files:
            if os.path.splitext(filename)[1].lower() in SUPPORTED_EXTENSIONS:
                all_files.append(os.path.join(root, filename))
    all_files.sort()

    for filepath in all_files:
        filename = os.path.relpath(filepath, dir_path)
        total_files += 1
        start = time.perf_counter()
        try:
            documents = load_single_file(filepath)
            documents = clean_documents(
                documents, dedup=True, fuzzy_dedup=False, fuzzy_threshold=0.9
            )
            chunks = split_documents(documents)
            chunks = enhance_documents(chunks)
            for chunk in chunks:
                chunk.metadata["category"] = category
            chunks = tag_chunks_with_knowledge_points(chunks, fallback_category=category)
            ids = vector_store_manager.add_documents(chunks, collection_name=category)
            total_chunks += len(chunks)

            elapsed = time.perf_counter() - start
            metrics.emit_ingest_file_summary(
                file=filename,
                category=category,
                elapsed_ms=round(elapsed * 1000, 3),
                values={
                    "parse_success": True,
                    "clean_success": True,
                    "split_success": True,
                    "index_success": True,
                    "documents": len(documents),
                    "chunks": len(chunks),
                    "indexed_chunks": len(ids),
                },
            )
            logger.info(
                "  [OK] %s: %d chunks, %d indexed (%.1fs)",
                filename,
                len(chunks),
                len(ids),
                elapsed,
            )
        except Exception as e:
            total_errors += 1
            logger.info("  [ERR] %s: ERROR - %s", filename, e)

    logger.info(
        "  小计(%s): %d 文件, %d chunks, %d 错误, %.1fs",
        category,
        total_files,
        total_chunks,
        total_errors,
        time.perf_counter() - category_start,
    )
    return {
        "category": category,
        "files": total_files,
        "chunks": total_chunks,
        "errors": total_errors,
    }


def ingest_all(categories: list[str] | None = None, rebuild: bool = False) -> None:
    """一键重建全量索引。"""
    if categories is None:
        categories = DEFAULT_CATEGORIES

    if rebuild:
        # 全量重建时清空语义缓存，避免旧知识残留导致跨版本缓存命中
        from rag.semantic_cache import get_semantic_cache

        get_semantic_cache().clear()
        logger.info("  已清空语义缓存")

    logger.info("=" * 60)
    logger.info("  智能教学系统 - 全量索引构建")
    logger.info("  模式: %s", "全量重建" if rebuild else "增量入库")
    logger.info("  分类: %s", ", ".join(categories))
    logger.info("=" * 60)

    total_start = time.perf_counter()
    total_files = 0
    total_chunks = 0
    total_errors = 0

    for category in categories:
        logger.info("\n[DIR] 处理分类: %s", category)
        result = ingest_category(category, rebuild=rebuild)
        if result.get("skipped"):
            logger.info("  [SKIP] 目录不存在，跳过")
            continue
        total_files += result["files"]
        total_chunks += result["chunks"]
        total_errors += result["errors"]

    logger.info("\n" + "=" * 60)
    logger.info("  构建完成!")
    logger.info("  总文件数: %d", total_files)
    logger.info("  总 chunk 数: %d", total_chunks)
    logger.info("  错误数: %d", total_errors)
    logger.info("  总耗时: %.1fs", time.perf_counter() - total_start)
    logger.info("=" * 60)

    logger.info("\n[STAT] 当前索引状态:")
    vector_store_manager = get_vector_store_manager()
    for name in vector_store_manager.list_collections():
        info = vector_store_manager.get_collection_info(name)
        logger.info("  %s: %s 条文档", name, info.get("count", 0))

    logger.info("\n[WARMUP] 预热查询缓存...")
    from rag.retriever import warmup_query_cache

    warmup_result = warmup_query_cache(quiet=True)
    logger.info(
        "  %d/%d 条预热成功, 耗时 %.0f ms",
        warmup_result["succeeded"],
        warmup_result["total"],
        warmup_result["elapsed_ms"],
    )


def main():
    parser = argparse.ArgumentParser(description="智能教学系统 - 全量索引构建")
    parser.add_argument("--category", "-c", type=str, default=None, help="只处理指定分类")
    parser.add_argument("--rebuild", "-r", action="store_true", default=False, help="全量重建")
    args = parser.parse_args()
    categories = [args.category] if args.category else None
    ingest_all(categories=categories, rebuild=args.rebuild)


if __name__ == "__main__":
    main()
