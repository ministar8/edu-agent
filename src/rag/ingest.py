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


def evaluate_warmup(result: dict, min_success_rate: float) -> tuple[bool, str]:
    """判断预热结果是否可接受。**纯函数**，便于单测。

    Returns:
        ``(是否可接受, 人类可读说明)``。

    为什么需要一个判定函数而不是直接打印：预热全落空几乎总是意味着索引未就绪或检索链
    故障，但旧代码只打印一行 INFO，问题会无声无息地滑过去。这里给出明确的判定与文案，
    让失败既进日志（ERROR 级）也进指标。
    """
    total = int(result.get("total", 0) or 0)
    succeeded = int(result.get("succeeded", 0) or 0)
    if total <= 0:
        return False, "预热查询集为空，无法判定（检查 _WARMUP_QUERIES）"
    rate = succeeded / total
    if rate < min_success_rate:
        return False, (
            f"预热成功率 {rate:.1%} 低于阈值 {min_success_rate:.0%}"
            f"（{succeeded}/{total}）—— 索引可能未就绪或检索链故障"
        )
    return True, f"预热成功率 {rate:.1%}（{succeeded}/{total}）"


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

    # ── 就绪屏障：等 HNSW 落盘 ──
    # 调用方（ingest_all）紧接着会预热查询缓存；不等就可能预热全落空，
    # 而预热只打印不报错 —— 表现为"上线后第一批查询特别慢"且无从定位。
    # 详见 VectorStoreManager.wait_until_ready 的 docstring。
    ready_retries = 0
    not_ready = False
    if total_chunks:
        try:
            ready_retries = vector_store_manager.wait_until_ready(
                category,
                retries=settings.INGEST_READY_RETRIES,
                delay=settings.INGEST_READY_DELAY,
            )
            if ready_retries:
                logger.warning(
                    "  [WARN] 集合 '%s' 重试 %d 次后才可查询（Chroma 落盘竞态）",
                    category,
                    ready_retries,
                )
        except RuntimeError as e:
            not_ready = True
            logger.error("  [ERR] 集合 '%s' 索引不可查询，后续检索将失败: %s", category, e)

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
        "ready_retries": ready_retries,
        "not_ready": not_ready,
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
    not_ready_categories: list[str] = []

    for category in categories:
        logger.info("\n[DIR] 处理分类: %s", category)
        result = ingest_category(category, rebuild=rebuild)
        if result.get("skipped"):
            logger.info("  [SKIP] 目录不存在，跳过")
            continue
        total_files += result["files"]
        total_chunks += result["chunks"]
        total_errors += result["errors"]
        if result.get("not_ready"):
            not_ready_categories.append(category)

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
    warmup_ok, warmup_verdict = evaluate_warmup(warmup_result, settings.WARMUP_MIN_SUCCESS_RATE)
    warmup_total = int(warmup_result.get("total", 0) or 0)
    metrics.emit(
        event="ingest_warmup_summary",
        stage="ingest",
        status="ok" if warmup_ok else "error",
        duration_ms=warmup_result.get("elapsed_ms"),
        values={
            "total": warmup_total,
            "succeeded": int(warmup_result.get("succeeded", 0) or 0),
            "failed": int(warmup_result.get("failed", 0) or 0),
            "success_rate": round(int(warmup_result.get("succeeded", 0) or 0) / warmup_total, 6)
            if warmup_total
            else 0.0,
            "min_success_rate": settings.WARMUP_MIN_SUCCESS_RATE,
            "not_ready_categories": not_ready_categories,
        },
    )
    if warmup_ok:
        logger.info("  %s, 耗时 %.0f ms", warmup_verdict, warmup_result.get("elapsed_ms", 0))
    else:
        # ERROR 级 + 指标，避免"预热全落空"被当成正常日志滑过去
        logger.error("  [ERR] %s", warmup_verdict)

    if not_ready_categories:
        logger.error(
            "  [ERR] 以下集合索引不可查询，相关学科检索会返回错误结果: %s。"
            "重试/重开客户端均无效，请重建：python -m rag.ingest --category <集合名> --rebuild",
            not_ready_categories,
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
