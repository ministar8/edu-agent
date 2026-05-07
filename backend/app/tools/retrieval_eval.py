"""检索评估体系

离线评测 RAG 检索质量，量化系统检索有效性。

评测流程：
  1. 加载标注集（query + relevant_section_ids / chunk_ids）
  2. 对每条 query 执行检索
  3. 将检索结果与标注对比，计算指标
  4. 输出评测报告

支持的指标：
  - Hit@K   : 前 K 条结果中至少命中一个相关文档的查询占比
  - Recall@K: 前 K 条结果命中的相关文档占所有相关文档的比例
  - MRR      : 首个正确结果倒数排名的均值
  - nDCG@K   : 归一化折损累积增益（支持多级相关性）

用法:
    python -m app.rag.retrieval_eval                       # 使用默认评测集
    python -m app.rag.retrieval_eval --eval-set custom.json  # 指定评测集
    python -m app.rag.retrieval_eval --k 3,5,10            # 指定 K 值
    python -m app.rag.retrieval_eval --no-rerank           # 关闭重排对比
"""

from __future__ import annotations

import json
import logging
import math
import os
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

from app.rag.metrics import metrics

logger = logging.getLogger(__name__)


# ── 评测集条目 ──────────────────────────────────────────

@dataclass
class EvalQuery:
    """单条评测条目

    Attributes:
        query: 用户查询文本
        collection: 目标向量库集合名
        relevant_section_ids: 相关 section.id 列表（主匹配键）
        relevant_chunk_ids: 相关 section.chunk_id 列表（细粒度匹配）
        relevant_source_files: 相关 source_file 列表（粗粒度匹配）
        relevance_levels: section.id → 相关性等级映射
            0 = 不相关, 1 = 部分相关, 2 = 高度相关
            用于 nDCG 计算；若未指定则默认全部为 1
        tags: 自定义标签（如 "概念定义", "代码示例"）
    """
    query: str
    collection: str = "data_structure"
    relevant_section_ids: list[str] = field(default_factory=list)
    relevant_chunk_ids: list[str] = field(default_factory=list)
    relevant_source_files: list[str] = field(default_factory=list)
    relevance_levels: dict[str, int] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)

    def get_relevance_level(self, section_id: str) -> int:
        """获取 section 的相关性等级，默认为 1"""
        return self.relevance_levels.get(section_id, 1)


# ── 单条评测结果 ──────────────────────────────────────────

@dataclass
class EvalResult:
    """单条查询的评测结果"""
    query: str
    collection: str
    hit_at_k: dict[int, bool] = field(default_factory=dict)
    recall_at_k: dict[int, float] = field(default_factory=dict)
    mrr: float = 0.0
    ndcg_at_k: dict[int, float] = field(default_factory=dict)
    retrieved_count: int = 0
    relevant_count: int = 0
    matched_section_ids: list[str] = field(default_factory=list)
    first_relevant_rank: int | None = None
    retrieved_section_ids: list[str] = field(default_factory=list)
    duration_ms: float = 0.0


# ── 评测报告 ──────────────────────────────────────────────

@dataclass
class EvalReport:
    """整体评测报告"""
    eval_set: str
    total_queries: int
    k_values: list[int]
    hit_at_k: dict[int, float] = field(default_factory=dict)
    recall_at_k: dict[int, float] = field(default_factory=dict)
    mrr: float = 0.0
    ndcg_at_k: dict[int, float] = field(default_factory=dict)
    per_query_results: list[EvalResult] = field(default_factory=list)
    avg_duration_ms: float = 0.0
    total_duration_ms: float = 0.0
    use_rerank: bool = True
    timestamp: str = ""

    def summary(self) -> str:
        lines = [
            f"评测集: {self.eval_set}",
            f"查询数: {self.total_queries}",
            f"Rerank: {'开启' if self.use_rerank else '关闭'}",
            "",
        ]
        for k in self.k_values:
            lines.append(f"Hit@{k}:     {self.hit_at_k.get(k, 0.0):.4f}")
        for k in self.k_values:
            lines.append(f"Recall@{k}:  {self.recall_at_k.get(k, 0.0):.4f}")
        lines.append(f"MRR:        {self.mrr:.4f}")
        for k in self.k_values:
            lines.append(f"nDCG@{k}:    {self.ndcg_at_k.get(k, 0.0):.4f}")
        lines.append(f"平均耗时:   {self.avg_duration_ms:.1f}ms")
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        d = {
            "eval_set": self.eval_set,
            "total_queries": self.total_queries,
            "k_values": self.k_values,
            "hit_at_k": self.hit_at_k,
            "recall_at_k": self.recall_at_k,
            "mrr": self.mrr,
            "ndcg_at_k": self.ndcg_at_k,
            "avg_duration_ms": round(self.avg_duration_ms, 3),
            "total_duration_ms": round(self.total_duration_ms, 3),
            "use_rerank": self.use_rerank,
            "timestamp": self.timestamp,
            "per_query": [],
        }
        for qr in self.per_query_results:
            d["per_query"].append({
                "query": qr.query,
                "collection": qr.collection,
                "hit_at_k": qr.hit_at_k,
                "recall_at_k": qr.recall_at_k,
                "mrr": qr.mrr,
                "ndcg_at_k": qr.ndcg_at_k,
                "retrieved_count": qr.retrieved_count,
                "relevant_count": qr.relevant_count,
                "matched_section_ids": qr.matched_section_ids,
                "first_relevant_rank": qr.first_relevant_rank,
                "duration_ms": round(qr.duration_ms, 3),
            })
        return d


# ── 指标计算 ──────────────────────────────────────────────

def _compute_hit_at_k(retrieved_section_ids: list[str], relevant_ids: set[str], k: int) -> bool:
    """Hit@K: 前 K 条结果中是否至少命中一个相关文档"""
    top_k = retrieved_section_ids[:k]
    return bool(set(top_k) & relevant_ids)


def _compute_recall_at_k(retrieved_section_ids: list[str], relevant_ids: set[str], k: int) -> float:
    """Recall@K: 前 K 条结果命中的相关文档占所有相关文档的比例"""
    if not relevant_ids:
        return 0.0
    top_k = set(retrieved_section_ids[:k])
    return len(top_k & relevant_ids) / len(relevant_ids)


def _compute_mrr(retrieved_section_ids: list[str], relevant_ids: set[str]) -> float:
    """MRR: 首个正确结果倒数排名的均值（单条为 1/rank 或 0）"""
    for rank, sec_id in enumerate(retrieved_section_ids, start=1):
        if sec_id in relevant_ids:
            return 1.0 / rank
    return 0.0


def _compute_ndcg_at_k(
    retrieved_section_ids: list[str],
    relevance_levels: dict[str, int],
    relevant_ids: set[str],
    k: int,
) -> float:
    """nDCG@K: 归一化折损累积增益

    DCG@K = sum_{i=1}^{K} rel_i / log2(i+1)
    IDCG@K = sum over ideal ranking of rel_i / log2(i+1)
    nDCG@K = DCG@K / IDCG@K
    """
    if not relevant_ids:
        return 0.0

    # DCG
    dcg = 0.0
    for i, sec_id in enumerate(retrieved_section_ids[:k]):
        rel = relevance_levels.get(sec_id, 0)
        if sec_id not in relevant_ids:
            rel = 0
        dcg += rel / math.log2(i + 2)

    # IDCG: 理想排序
    ideal_rels = sorted(
        [relevance_levels.get(sid, 1) for sid in relevant_ids],
        reverse=True,
    )
    idcg = 0.0
    for i, rel in enumerate(ideal_rels[:k]):
        idcg += rel / math.log2(i + 2)

    if idcg == 0.0:
        return 0.0
    return dcg / idcg


# ── 评测执行 ──────────────────────────────────────────────

def _extract_section_ids_from_docs(docs: list) -> list[str]:
    """从检索结果中提取 section.id 列表（去重，保持顺序）"""
    seen: set[str] = set()
    result: list[str] = []
    for doc in docs:
        sec_id = str(doc.metadata.get("section.id") or "")
        if sec_id and sec_id not in seen:
            seen.add(sec_id)
            result.append(sec_id)
    return result


def evaluate_single_query(
    eval_query: EvalQuery,
    k_values: list[int],
    use_rerank: bool = True,
) -> EvalResult:
    """评测单条查询

    执行检索并计算各指标。
    """
    from app.rag.retriever import retrieve_documents

    start = time.perf_counter()
    docs = retrieve_documents(
        query=eval_query.query,
        collection_name=eval_query.collection,
        k=max(k_values),
        use_rerank=use_rerank,
    )
    duration_ms = round((time.perf_counter() - start) * 1000, 3)

    retrieved_section_ids = _extract_section_ids_from_docs(docs)
    relevant_ids = set(eval_query.relevant_section_ids)
    relevance_levels = eval_query.relevance_levels

    result = EvalResult(
        query=eval_query.query,
        collection=eval_query.collection,
        retrieved_count=len(docs),
        relevant_count=len(relevant_ids),
        retrieved_section_ids=retrieved_section_ids,
        matched_section_ids=list(set(retrieved_section_ids) & relevant_ids),
        duration_ms=duration_ms,
    )

    for k in k_values:
        result.hit_at_k[k] = _compute_hit_at_k(retrieved_section_ids, relevant_ids, k)
        result.recall_at_k[k] = _compute_recall_at_k(retrieved_section_ids, relevant_ids, k)
        result.ndcg_at_k[k] = _compute_ndcg_at_k(retrieved_section_ids, relevance_levels, relevant_ids, k)

    result.mrr = _compute_mrr(retrieved_section_ids, relevant_ids)

    # 首个相关结果的排名
    for rank, sec_id in enumerate(retrieved_section_ids, start=1):
        if sec_id in relevant_ids:
            result.first_relevant_rank = rank
            break

    return result


def evaluate_retrieval(
    eval_queries: list[EvalQuery],
    k_values: list[int] | None = None,
    use_rerank: bool = True,
    eval_set_name: str = "default",
) -> EvalReport:
    """执行完整评测

    Args:
        eval_queries: 评测条目列表
        k_values: 要计算的 K 值列表，默认 [3, 5, 10]
        use_rerank: 是否启用 rerank
        eval_set_name: 评测集名称

    Returns:
        EvalReport 评测报告
    """
    if k_values is None:
        k_values = [3, 5, 10]

    total_start = time.perf_counter()
    per_query_results: list[EvalResult] = []

    for i, eq in enumerate(eval_queries):
        logger.info("Evaluating query %d/%d: %s", i + 1, len(eval_queries), eq.query[:60])
        qr = evaluate_single_query(eq, k_values, use_rerank)
        per_query_results.append(qr)

    total_duration_ms = round((time.perf_counter() - total_start) * 1000, 3)
    n = len(eval_queries)

    # 汇总指标
    hit_at_k: dict[int, float] = {}
    recall_at_k: dict[int, float] = {}
    ndcg_at_k: dict[int, float] = {}

    for k in k_values:
        hit_at_k[k] = sum(1 for qr in per_query_results if qr.hit_at_k.get(k, False)) / n if n else 0.0
        recall_at_k[k] = sum(qr.recall_at_k.get(k, 0.0) for qr in per_query_results) / n if n else 0.0
        ndcg_at_k[k] = sum(qr.ndcg_at_k.get(k, 0.0) for qr in per_query_results) / n if n else 0.0

    mrr = sum(qr.mrr for qr in per_query_results) / n if n else 0.0

    from datetime import datetime, timezone
    report = EvalReport(
        eval_set=eval_set_name,
        total_queries=n,
        k_values=k_values,
        hit_at_k=hit_at_k,
        recall_at_k=recall_at_k,
        mrr=mrr,
        ndcg_at_k=ndcg_at_k,
        per_query_results=per_query_results,
        avg_duration_ms=total_duration_ms / n if n else 0.0,
        total_duration_ms=total_duration_ms,
        use_rerank=use_rerank,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )

    # 写入 metrics 事件
    metrics.emit(
        event="retrieval_eval",
        stage="eval",
        duration_ms=total_duration_ms,
        values={
            "eval_set": eval_set_name,
            "total_queries": n,
            "k_values": k_values,
            "use_rerank": use_rerank,
            "hit_at_k": hit_at_k,
            "recall_at_k": recall_at_k,
            "mrr": mrr,
            "ndcg_at_k": ndcg_at_k,
        },
    )

    return report


# ── 评测集加载与保存 ──────────────────────────────────────

def load_eval_set(filepath: str) -> list[EvalQuery]:
    """从 JSON 文件加载评测集

    JSON 格式：
    [
      {
        "query": "什么是进程死锁",
        "collection": "operating_system",
        "relevant_section_ids": ["sec_os_deadlock_01"],
        "relevant_chunk_ids": ["sec_os_deadlock_01_0", "sec_os_deadlock_01_1"],
        "relevant_source_files": ["wangdao_15 死锁.md"],
        "relevance_levels": {"sec_os_deadlock_01": 2},
        "tags": ["概念定义"]
      },
      ...
    ]
    """
    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(f"评测集文件不存在: {filepath}")

    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    queries: list[EvalQuery] = []
    for item in data:
        queries.append(EvalQuery(
            query=item["query"],
            collection=item.get("collection", "data_structure"),
            relevant_section_ids=item.get("relevant_section_ids", []),
            relevant_chunk_ids=item.get("relevant_chunk_ids", []),
            relevant_source_files=item.get("relevant_source_files", []),
            relevance_levels=item.get("relevance_levels", {}),
            tags=item.get("tags", []),
        ))
    return queries


def save_eval_set(queries: list[EvalQuery], filepath: str) -> None:
    """保存评测集到 JSON 文件"""
    path = Path(filepath)
    path.parent.mkdir(parents=True, exist_ok=True)

    data = []
    for q in queries:
        item: dict[str, Any] = {"query": q.query, "collection": q.collection}
        if q.relevant_section_ids:
            item["relevant_section_ids"] = q.relevant_section_ids
        if q.relevant_chunk_ids:
            item["relevant_chunk_ids"] = q.relevant_chunk_ids
        if q.relevant_source_files:
            item["relevant_source_files"] = q.relevant_source_files
        if q.relevance_levels:
            item["relevance_levels"] = q.relevance_levels
        if q.tags:
            item["tags"] = q.tags
        data.append(item)

    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    logger.info("评测集已保存: %s (%d 条)", filepath, len(queries))


def save_report(report: EvalReport, filepath: str) -> None:
    """保存评测报告到 JSON 文件"""
    path = Path(filepath)
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as f:
        json.dump(report.to_dict(), f, ensure_ascii=False, indent=2)
    logger.info("评测报告已保存: %s", filepath)


# ── 对比评测（开启/关闭 rerank 对比） ──────────────────────

def compare_rerank_impact(
    eval_queries: list[EvalQuery],
    k_values: list[int] | None = None,
    eval_set_name: str = "default",
) -> dict[str, EvalReport]:
    """对比开启/关闭 rerank 的检索效果

    Returns:
        {"with_rerank": EvalReport, "without_rerank": EvalReport}
    """
    if k_values is None:
        k_values = [3, 5, 10]

    logger.info("=== 对比评测: Rerank 开启 ===")
    with_rerank = evaluate_retrieval(
        eval_queries, k_values, use_rerank=True,
        eval_set_name=f"{eval_set_name}_with_rerank",
    )

    logger.info("=== 对比评测: Rerank 关闭 ===")
    without_rerank = evaluate_retrieval(
        eval_queries, k_values, use_rerank=False,
        eval_set_name=f"{eval_set_name}_no_rerank",
    )

    return {"with_rerank": with_rerank, "without_rerank": without_rerank}


# ── CLI ──────────────────────────────────────────────────

DEFAULT_EVAL_SET_PATH = str(Path(__file__).resolve().parent / "eval_sets" / "default.json")


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="RAG 检索评估")
    parser.add_argument(
        "--eval-set", "-e",
        type=str,
        default=DEFAULT_EVAL_SET_PATH,
        help="评测集 JSON 文件路径",
    )
    parser.add_argument(
        "--k", "-k",
        type=str,
        default="3,5,10",
        help="K 值列表，逗号分隔（默认 3,5,10）",
    )
    parser.add_argument(
        "--no-rerank",
        action="store_true",
        default=False,
        help="关闭 rerank 评测",
    )
    parser.add_argument(
        "--compare-rerank",
        action="store_true",
        default=False,
        help="对比开启/关闭 rerank 的效果",
    )
    parser.add_argument(
        "--output", "-o",
        type=str,
        default="",
        help="评测报告输出路径（JSON）",
    )
    args = parser.parse_args()

    k_values = [int(x.strip()) for x in args.k.split(",")]
    eval_set_path = args.eval_set

    print("=" * 60)
    print("  RAG 检索评估")
    print(f"  评测集: {eval_set_path}")
    print(f"  K 值: {k_values}")
    print(f"  Rerank: {'关闭' if args.no_rerank else '开启'}")
    print("=" * 60)

    try:
        eval_queries = load_eval_set(eval_set_path)
    except FileNotFoundError:
        print(f"\n⚠ 评测集文件不存在: {eval_set_path}")
        print("请先创建评测集，参考格式:")
        print(json.dumps([{
            "query": "示例问题",
            "collection": "data_structure",
            "relevant_section_ids": ["sec_example_01"],
            "relevant_source_files": ["example.md"],
            "relevance_levels": {"sec_example_01": 2},
            "tags": ["示例"],
        }], ensure_ascii=False, indent=2))
        return

    print(f"\n加载评测集: {len(eval_queries)} 条查询\n")

    eval_set_name = Path(eval_set_path).stem

    if args.compare_rerank:
        results = compare_rerank_impact(eval_queries, k_values, eval_set_name)
        for label, report in results.items():
            print(f"\n{'─' * 40}")
            print(f"  {label}")
            print(f"{'─' * 40}")
            print(report.summary())
    else:
        report = evaluate_retrieval(
            eval_queries,
            k_values,
            use_rerank=not args.no_rerank,
            eval_set_name=eval_set_name,
        )
        print(report.summary())

        # 输出详细 per-query 结果
        print(f"\n{'─' * 60}")
        print("  逐条结果")
        print(f"{'─' * 60}")
        for i, qr in enumerate(report.per_query_results, 1):
            hit_str = ", ".join(f"K={k}:{'✓' if qr.hit_at_k.get(k) else '✗'}" for k in k_values)
            recall_str = ", ".join(f"K={k}:{qr.recall_at_k.get(k, 0):.2f}" for k in k_values)
            rank_str = f"#{qr.first_relevant_rank}" if qr.first_relevant_rank else "未命中"
            print(f"  {i}. {qr.query[:40]:<40} 命中={rank_str}  Hit=[{hit_str}]  Recall=[{recall_str}]")

        if args.output:
            save_report(report, args.output)
            print(f"\n报告已保存: {args.output}")


if __name__ == "__main__":
    main()
