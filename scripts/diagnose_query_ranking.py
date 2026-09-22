"""诊断「某条查询为什么首条命中了错学科」。

**为什么需要它**：门禁只会告诉你 `hit@1` 掉了、以及哪几条没命中，但**不会告诉你原因**。
实测踩过的坑就分属完全不同的两层：

- **收窄层**：`resolve_collection_routes` 用关键词把检索范围收窄到某几个学科；
  收窄失败会**静默退化成「全 4 科检索」**（关键词写法不一致、表里缺词都会触发）。
- **融合层**：跨集合时所有 `(集合 × 路由)` 结果丢进**同一个 RRF 池**，
  而 RRF 奖励「出现在更多列表里的文档」、不奖励「分数更高的文档」——
  于是单集合内排名更高的文档，融合后可能被反超。

本脚本把这两层**分开打印**，一眼就能看出问题在哪一层：
若目标学科的集合**单独**召回时 top-1 就输，是收窄/召回问题；
若它单独召回时赢、融合后输，是排序问题。

用法::

    python scripts/diagnose_query_ranking.py "什么是段页式存储管理？"
    python scripts/diagnose_query_ranking.py "查询A" "查询B" --k 5
    python scripts/diagnose_query_ranking.py "查询" --fake-embedding   # 不依赖 TEI

**默认用真实 embedding**（需要 TEI）—— 用假 embedding 诊断排序问题没有意义，
因为它没有语义泛化能力、分数分布也和生产不同。
"""

from __future__ import annotations

import argparse
import asyncio
import shutil
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))


def _print_evidence(label: str, results: list, expected: str | None = None) -> None:
    print(f"    {label}")
    if not results:
        print("      （空）")
        return
    for rank, (doc, score) in enumerate(results, 1):
        meta = doc.metadata or {}
        source = meta.get("source_file") or meta.get("source") or "?"
        heading = str(meta.get("section_path") or meta.get("heading_path") or "")[:44]
        category = str(meta.get("category", "?"))
        mark = ""
        if expected:
            mark = "  ✓" if category == expected else "  ← 错学科"
        print(f"      {rank}. score={score:.4f}  [{category}] {source}{mark}")
        if heading:
            print(f"         {heading}")
        print(f"         {doc.page_content[:56].replace(chr(10), ' ')}")


def _print_fused(label: str, evidences: list, expected: str | None = None) -> None:
    """最终结果用的是 `TextEvidence`（字段与 `Document` **不同**：`content` / `source`
    / `collection`，没有 `page_content`），所以不能复用上面那个函数。"""
    print(f"    {label}")
    if not evidences:
        print("      （空）")
        return
    for rank, ev in enumerate(evidences, 1):
        category = str(ev.metadata.get("category") or ev.collection or "?")
        mark = ""
        if expected:
            mark = "  ✓" if category == expected else "  ← 错学科"
        print(f"      {rank}. score={ev.score:.4f}  [{category}] {ev.source}{mark}")
        if ev.section_path:
            print(f"         {ev.section_path[:56]}")
        print(f"         {ev.content[:56].replace(chr(10), ' ')}")


async def _diagnose(queries: list[str], expected: str | None, k: int) -> None:
    from rag.recall import resolve_collection_routes
    from rag.retriever import _amulti_route_search, aretrieve_evidence_with_retry

    for query in queries:
        collections = resolve_collection_routes(query, "")
        print("=" * 78)
        print(f"查询: {query}")
        print(f"  收窄到的集合: {collections}")
        if not collections:
            print("  ⚠️ 收窄结果为空 —— 会退化成全学科检索")
        print()
        print(f"  ── 各集合**单独**多路召回（k={k}）──")
        for collection in collections:
            try:
                results = await _amulti_route_search(query, collection, k)
            except Exception as exc:  # noqa: BLE001 — 诊断脚本，任何异常都要报出来
                print(f"    {collection}: 召回异常 {type(exc).__name__}: {exc}")
                continue
            _print_evidence(collection, results, expected)
        print()
        print("  ── 全链路最终顺序（跨集合融合 + 去重 + 阈值）──")
        fused, _verdict = await aretrieve_evidence_with_retry(
            query=query, k=k, use_rerank=False, max_retries=0, use_llm_verify=False
        )
        _print_fused("最终", fused.text_evidences, expected)
        print()
        print("  读法：若目标学科在「单独召回」时就排第二 → 收窄/召回层的问题；")
        print("        若它单独召回时是第一、融合后掉下去 → 跨集合 RRF 融合层的问题。")
        print()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="诊断查询首条命中错学科的原因")
    parser.add_argument("queries", nargs="+", help="要诊断的查询（可多条）")
    parser.add_argument("--k", type=int, default=5, help="检索条数（默认 5）")
    parser.add_argument("--expected", default=None, help="期望学科集合名（用于标出「错学科」）")
    parser.add_argument(
        "--fake-embedding",
        action="store_true",
        help="改用确定性假 embedding（无需 TEI，但排序诊断意义有限）",
    )
    args = parser.parse_args(argv)

    from evaluation import retrieval_gate as gate

    # 必须在 configure_for_gate 之前设置：它是 import 期读取的模块级开关
    gate.GATE_USE_REAL_EMBEDDING = not args.fake_embedding

    tmp_dir = tempfile.mkdtemp(prefix="diag_rank_")
    try:
        gate.configure_for_gate(tmp_dir)
        mode = "假 embedding（仅验证接线）" if args.fake_embedding else "真实 TEI embedding"
        print(f"建索引中（{mode}）…")
        counts = gate.build_index()
        print(f"索引就绪：{sum(counts.values())} chunks")
        gate.wait_for_index_ready(sorted(counts))
        asyncio.run(_diagnose(args.queries, args.expected, args.k))
        return 0
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
