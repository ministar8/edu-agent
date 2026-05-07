"""一键重建全量索引 CLI

用法:
    python -m app.rag.ingest                      # 扫描所有分类目录，增量入库
    python -m app.rag.ingest --category data_structure   # 只处理数据结构分类
    python -m app.rag.ingest --rebuild            # 先清空再重建（全量重建）
    python -m app.rag.ingest --no-graph           # 跳过知识图谱构建
"""

from __future__ import annotations

import argparse
import os
import time

from app.config import settings
from app.rag.loader import load_single_file
from app.rag.cleaner import clean_documents
from app.rag.splitter import split_documents
from app.rag.enhancer import enhance_documents
from app.rag.graph_builder import build_graph_from_documents
from app.rag.vectorstore import get_vector_store_manager
from app.rag.knowledge_graph import get_kg_manager
from app.rag.metrics import metrics
from app.tools.quality_metrics import evaluate_documents, compare_reports, suggest_cleaning_priority


SUPPORTED_EXTENSIONS = {".pdf", ".txt", ".md", ".docx"}
DEFAULT_CATEGORIES = ["data_structure", "computer_organization", "operating_system", "computer_network", "questions", "learning_paths"]


def ingest_category(
    category: str,
    rebuild: bool = False,
    build_graph: bool = True,
    quality_report: bool = True,
) -> dict:
    """处理单个分类目录

    Returns:
        {"category": str, "files": int, "chunks": int, "graph_nodes": int, "graph_edges": int, "errors": int}
    """
    dir_path = os.path.join(settings.KNOWLEDGE_DIR, category)
    if not os.path.isdir(dir_path):
        return {"category": category, "files": 0, "chunks": 0, "graph_nodes": 0, "graph_edges": 0, "errors": 0, "skipped": True}

    vector_store_manager = get_vector_store_manager()
    kg_manager = get_kg_manager()

    # 重建模式：先清空（向量库 + 知识图谱同步清理）
    if rebuild:
        print(f"  [rebuild] 清空集合 '{category}'...")
        vector_store_manager.delete_collection(category)
        try:
            deleted = kg_manager.delete_by_category(category)
            if deleted:
                print(f"  [rebuild] 清空知识图谱分类 '{category}'：{deleted} 个节点")
        except Exception as e:
            print(f"  [rebuild] 知识图谱清理失败（非致命）：{e}")

    total_chunks = 0
    total_files = 0
    total_errors = 0
    total_graph_nodes = 0
    total_graph_edges = 0
    category_start = time.perf_counter()

    # 递归查找所有支持的文件（包括子目录）
    all_files = []
    for root, _dirs, files in os.walk(dir_path):
        for filename in files:
            ext = os.path.splitext(filename)[1].lower()
            if ext in SUPPORTED_EXTENSIONS:
                all_files.append(os.path.join(root, filename))
    all_files.sort()

    for filepath in all_files:
        filename = os.path.relpath(filepath, dir_path)
        total_files += 1

        try:
            start = time.perf_counter()
            graph_success = not build_graph

            # ETL Pipeline（带质量评估）
            documents = load_single_file(filepath)

            # 清洗前质量评估
            if quality_report:
                before_report, _ = evaluate_documents(documents)
                priority_list = suggest_cleaning_priority(documents)
                if priority_list and priority_list[0]["priority"] <= 2:
                    print(f"    [WARN] 质量预警: {filename} 优先级={priority_list[0]['priority']} 问题={', '.join(priority_list[0]['issues'])}")

            documents = clean_documents(
                documents,
                quality_report=quality_report,
                dedup=True,
                fuzzy_dedup=True,
                fuzzy_threshold=0.9,
            )

            # 解包清洗结果
            if quality_report and isinstance(documents, tuple):
                documents, before_rpt, after_rpt = documents
                improvement = compare_reports(before_rpt, after_rpt)
                print(f"    [STAT] 清洗效果: 完整性+{improvement['completeness']:.1%} 准确性+{improvement['accuracy']:.1%} 一致性+{improvement['consistency']:.1%}")

            chunks = split_documents(documents)
            chunks = enhance_documents(chunks)

            for chunk in chunks:
                chunk.metadata["category"] = category

            ids = vector_store_manager.add_documents(chunks, collection_name=category)
            total_chunks += len(chunks)

            # 自动构建知识图谱
            if build_graph:
                graph_result = build_graph_from_documents(
                    chunks, category=category, source_file=filename,
                )
                total_graph_nodes += graph_result["nodes_added"]
                total_graph_edges += graph_result["edges_added"]
                if graph_result["nodes_added"] > 0 or graph_result["errors"] == 0:
                    graph_success = True
                else:
                    # KG 构建失败：向量库有数据但 KG 为空，告警
                    print(f"  [WARN] 知识图谱构建失败: {filename} (向量库已入库 {len(ids)} chunks，但 KG 为空)")
                    metrics.emit(
                        event="kg_build_failure",
                        stage="ingest",
                        tags={"category": category, "file": filename},
                        values={"errors": graph_result["errors"], "indexed_chunks": len(ids)},
                    )

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
                    "graph_success": graph_success,
                    "documents": len(documents),
                    "chunks": len(chunks),
                    "indexed_chunks": len(ids),
                },
            )
            print(f"  [OK] {filename}: {len(chunks)} chunks, {len(ids)} indexed ({elapsed:.1f}s)")

        except Exception as e:
            total_errors += 1
            metrics.emit_ingest_file_summary(
                file=filename,
                category=category,
                elapsed_ms=round((time.perf_counter() - start) * 1000, 3),
                status="error",
                values={"error_type": e.__class__.__name__},
            )
            print(f"  [ERR] {filename}: ERROR - {e}")

    category_elapsed_ms = round((time.perf_counter() - category_start) * 1000, 3)
    metrics.emit(
        event="ingest_category_summary",
        stage="ingest",
        duration_ms=category_elapsed_ms,
        tags={"category": category},
        values={
            "files": total_files,
            "chunks": total_chunks,
            "graph_nodes": total_graph_nodes,
            "graph_edges": total_graph_edges,
            "errors": total_errors,
        },
    )
    return {
        "category": category,
        "files": total_files,
        "chunks": total_chunks,
        "graph_nodes": total_graph_nodes,
        "graph_edges": total_graph_edges,
        "errors": total_errors,
    }


def ingest_all(
    categories: list[str] | None = None,
    rebuild: bool = False,
    build_graph: bool = True,
    quality_report: bool = True,
) -> None:
    """一键重建全量索引"""
    if categories is None:
        categories = DEFAULT_CATEGORIES

    print("=" * 60)
    print("  智能教学系统 - 全量索引构建")
    print(f"  模式: {'全量重建' if rebuild else '增量入库'}")
    print(f"  知识图谱: {'开启' if build_graph else '关闭'}")
    print(f"  质量评估: {'开启' if quality_report else '关闭'}")
    print(f"  分类: {', '.join(categories)}")
    print("=" * 60)

    total_start = time.perf_counter()
    total_files = 0
    total_chunks = 0
    total_graph_nodes = 0
    total_graph_edges = 0
    total_errors = 0

    for category in categories:
        print(f"\n[DIR] 处理分类: {category}")
        result = ingest_category(category, rebuild=rebuild, build_graph=build_graph, quality_report=quality_report)

        if result.get("skipped"):
            print(f"  [SKIP] 目录不存在，跳过")
            continue

        total_files += result["files"]
        total_chunks += result["chunks"]
        total_graph_nodes += result["graph_nodes"]
        total_graph_edges += result["graph_edges"]
        total_errors += result["errors"]

        print(f"  小计: {result['files']} 文件, {result['chunks']} chunks, "
              f"{result['graph_nodes']} 图谱节点, {result['graph_edges']} 图谱边")

    total_elapsed = time.perf_counter() - total_start
    metrics.emit(
        event="ingest_all_summary",
        stage="ingest",
        duration_ms=round(total_elapsed * 1000, 3),
        values={
            "categories": categories,
            "total_files": total_files,
            "total_chunks": total_chunks,
            "total_graph_nodes": total_graph_nodes,
            "total_graph_edges": total_graph_edges,
            "total_errors": total_errors,
        },
    )

    print("\n" + "=" * 60)
    print("  构建完成!")
    print(f"  总文件数: {total_files}")
    print(f"  总 chunk 数: {total_chunks}")
    print(f"  图谱节点: {total_graph_nodes}")
    print(f"  图谱关系: {total_graph_edges}")
    print(f"  错误数: {total_errors}")
    print(f"  总耗时: {total_elapsed:.1f}s")
    print("=" * 60)

    # 打印集合信息
    print("\n[STAT] 当前索引状态:")
    vector_store_manager = get_vector_store_manager()
    collections = vector_store_manager.list_collections()
    for name in collections:
        info = vector_store_manager.get_collection_info(name)
        print(f"  {name}: {info.get('count', 0)} 条文档")


def main():
    parser = argparse.ArgumentParser(description="智能教学系统 - 全量索引构建")
    parser.add_argument(
        "--category", "-c",
        type=str,
        default=None,
        help="只处理指定分类（默认处理所有分类）",
    )
    parser.add_argument(
        "--rebuild", "-r",
        action="store_true",
        default=False,
        help="全量重建模式（先清空再重建）",
    )
    parser.add_argument(
        "--no-graph",
        action="store_true",
        default=False,
        help="跳过知识图谱构建（加速入库）",
    )
    parser.add_argument(
        "--no-quality",
        action="store_true",
        default=False,
        help="跳过质量评估（加速入库）",
    )
    args = parser.parse_args()

    categories = [args.category] if args.category else None
    ingest_all(
        categories=categories,
        rebuild=args.rebuild,
        build_graph=not args.no_graph,
        quality_report=not args.no_quality,
    )


if __name__ == "__main__":
    main()
