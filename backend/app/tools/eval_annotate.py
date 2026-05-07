"""评测集标注辅助工具

帮助用户从实际检索结果中提取 section.id，快速填充评测集的 relevant_section_ids。

用法:
    python -m app.rag.eval_annotate --queries queries.json --output annotated.json
    python -m app.rag.eval_annotate --interactive --output annotated.json

交互模式下，用户输入查询，系统执行检索并展示结果，
用户选择相关 section，自动写入评测集。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from app.tools.retrieval_eval import EvalQuery, save_eval_set

logger = logging.getLogger(__name__)


def annotate_from_retrieval(
    queries: list[str],
    collection: str = "data_structure",
    k: int = 10,
) -> list[EvalQuery]:
    """对每条查询执行检索，提取所有返回的 section 信息供标注

    Args:
        queries: 查询文本列表
        collection: 目标集合
        k: 召回数量

    Returns:
        带候选 section 信息的 EvalQuery 列表（relevant_section_ids 留空待标注）
    """
    from app.rag.retriever import retrieve_documents

    eval_queries: list[EvalQuery] = []

    for query_text in queries:
        docs = retrieve_documents(
            query=query_text,
            collection_name=collection,
            k=k,
            use_rerank=True,
        )

        # 提取去重后的 section 信息
        seen_sections: dict[str, dict[str, Any]] = {}
        for doc in docs:
            sec_id = str(doc.metadata.get("section.id") or "")
            if not sec_id or sec_id in seen_sections:
                continue
            seen_sections[sec_id] = {
                "section_id": sec_id,
                "section_path": str(doc.metadata.get("section.path") or ""),
                "section_title": str(doc.metadata.get("section.title") or ""),
                "source_file": str(doc.metadata.get("source_file") or ""),
                "chunk_role": str(doc.metadata.get("section.chunk_role") or "detail"),
                "rerank_score": float(doc.metadata.get("rerank_score") or 0.0),
                "content_preview": doc.page_content[:120].replace("\n", " ") + "...",
            }

        eq = EvalQuery(
            query=query_text,
            collection=collection,
            relevant_section_ids=[],  # 待标注
        )
        eval_queries.append(eq)

        # 输出候选 section 供参考
        logger.info("Query: %s", query_text)
        for i, (sid, info) in enumerate(seen_sections.items(), 1):
            logger.info(
                "  [%d] %s | %s | %s | score=%.3f",
                i, sid, info["section_path"], info["source_file"], info["rerank_score"],
            )

    return eval_queries


def export_candidates_json(
    queries: list[str],
    collection: str = "data_structure",
    k: int = 10,
    output_path: str = "",
) -> list[dict[str, Any]]:
    """导出检索候选 section 到 JSON，便于人工标注

    输出格式：
    [
      {
        "query": "...",
        "collection": "data_structure",
        "relevant_section_ids": [],   // 待人工填写
        "candidates": [
          {"section_id": "...", "section_path": "...", "source_file": "...", "score": 0.85},
          ...
        ]
      }
    ]
    """
    from app.rag.retriever import retrieve_documents

    results: list[dict[str, Any]] = []

    for query_text in queries:
        docs = retrieve_documents(
            query=query_text,
            collection_name=collection,
            k=k,
            use_rerank=True,
        )

        seen_sections: dict[str, dict[str, Any]] = {}
        for doc in docs:
            sec_id = str(doc.metadata.get("section.id") or "")
            if not sec_id or sec_id in seen_sections:
                continue
            seen_sections[sec_id] = {
                "section_id": sec_id,
                "section_path": str(doc.metadata.get("section.path") or ""),
                "section_title": str(doc.metadata.get("section.title") or ""),
                "source_file": str(doc.metadata.get("source_file") or ""),
                "chunk_role": str(doc.metadata.get("section.chunk_role") or "detail"),
                "score": float(doc.metadata.get("rerank_score") or 0.0),
                "content_preview": doc.page_content[:150].replace("\n", " ") + "...",
            }

        results.append({
            "query": query_text,
            "collection": collection,
            "relevant_section_ids": [],
            "candidates": list(seen_sections.values()),
        })

    if output_path:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        logger.info("候选标注已导出: %s", output_path)

    return results


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="评测集标注辅助")
    parser.add_argument(
        "--queries", "-q",
        type=str,
        default="",
        help="查询文本 JSON 文件（每行一个查询字符串，或 JSON 数组）",
    )
    parser.add_argument(
        "--collection", "-c",
        type=str,
        default="data_structure",
        help="目标集合名",
    )
    parser.add_argument(
        "--k",
        type=int,
        default=10,
        help="每条查询召回数量",
    )
    parser.add_argument(
        "--output", "-o",
        type=str,
        default="eval_sets/candidates.json",
        help="候选标注输出路径",
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        default=False,
        help="交互模式：逐条输入查询",
    )
    args = parser.parse_args()

    queries: list[str] = []

    if args.interactive:
        print("交互标注模式（输入空行结束）")
        while True:
            q = input("查询: ").strip()
            if not q:
                break
            queries.append(q)
    elif args.queries:
        path = Path(args.queries)
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            queries = [str(item) if isinstance(item, str) else str(item.get("query", "")) for item in data]
        else:
            queries = [str(data)]
    else:
        print("请指定 --queries 或 --interactive")
        return

    if not queries:
        print("无查询，退出")
        return

    print(f"\n共 {len(queries)} 条查询，开始检索候选 section...\n")
    results = export_candidates_json(
        queries,
        collection=args.collection,
        k=args.k,
        output_path=args.output,
    )

    print(f"\n候选标注已导出到: {args.output}")
    print("请在文件中填写 relevant_section_ids 后，用 retrieval_eval.py 运行评测。")
    print("\n标注方法：在每条查询的 candidates 中找到相关 section，")
    print("将其 section_id 复制到 relevant_section_ids 数组中。")
    print("可选：在 relevance_levels 中指定相关性等级（0=不相关, 1=部分相关, 2=高度相关）。")


if __name__ == "__main__":
    main()
