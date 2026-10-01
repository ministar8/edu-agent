"""L2 覆盖归因（只分析，不改代码）。

问题：L2 为什么是短板（l2_only kp_mrr 0.704）？

拆分：
  A. 数据不存在   → 该知识点在 L2 无 chunk（coverage gap）→ 补数据
  B. 数据存在
     B1 召回到     → 无问题
     B2 召回不到   → retrieval miss（路由/召回）
     B3 召回后掉了 → threshold / 排序 / 截断

统计维度：
  1. 每个 knowledge_point（章级）对应多少 L2 chunk
  2. method 类知识点中，完全没有 L2 的
  3. 有 L2 且黄金 query 没召回的
  4. 召回了但 final pack 掉的
  5. L2 chunk 跨学科污染（证据学科 ≠ 期望学科）

用法：
    uv run python scripts/l2_coverage_analysis.py
"""

from __future__ import annotations

import asyncio
import json
import sys
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from evaluation.retrieval_gate import (  # noqa: E402
    DEFAULT_GOLDEN_PATH,
    chapter_of_source,
    load_golden_queries,
)

OUT = ROOT / "evals" / "results" / "retrieval" / "ablation" / "l2_coverage.json"
COLLECTIONS = [
    "data_structure",
    "computer_organization",
    "operating_system",
    "computer_network",
    "questions",
]

# method 类查询（来自 task_layer_ablation，标注目标 L2）
METHOD_QUERIES = [
    "BST 删除时双支结点怎么处理？",
    "如何用银行家算法避免死锁？",
    "页面置换算法 LRU 怎么实现？",
    "Dijkstra 算法的步骤是什么？",
    "如何判断一个二叉树是平衡二叉树？",
    "TCP 拥塞控制怎么实现？",
]


def _chapter_index() -> dict[str, int]:
    """全库 L2 chunk 按章级知识点计数。"""
    import chromadb

    from core.settings import settings

    client = chromadb.PersistentClient(path=settings.CHROMA_PERSIST_DIR)
    counts: dict[str, int] = defaultdict(int)
    per_subject: dict[str, int] = defaultdict(int)
    total = 0
    for coll in COLLECTIONS:
        try:
            c = client.get_collection(coll)
        except Exception:
            continue
        # 取全部（分页）
        data = c.get(where={"kb_depth": "advanced"}, include=["metadatas"])
        for meta in data.get("metadatas") or []:
            meta = meta or {}
            src = str(meta.get("source_file") or meta.get("source") or "")
            ch = chapter_of_source(src)
            counts[ch] += 1
            per_subject[coll] += 1
            total += 1
    return dict(counts), dict(per_subject), total


async def _trace_query(query: str) -> dict:
    """单条 method query：L2 在召回池 / final pack 的存在与排名。"""
    from rag.evidence_policy import apply_evidence_policy, finalize_with_layer_ranking
    from rag.retriever import aretrieve_evidence_with_retry
    from rag.task_policy import policy_for_mode

    policy = policy_for_mode("method")
    fused, _ = await aretrieve_evidence_with_retry(
        query=query,
        k=5,
        use_rerank=True,
        max_retries=0,
        use_llm_verify=False,
        filter=policy.eligibility_where(),
        preferred_layers=list(policy.preferred_layers),
    )
    pool = list(fused.text_evidences or [])

    def _layer(ev):
        return str((ev.metadata or {}).get("kb_depth") or "")

    def _src(ev):
        m = ev.metadata or {}
        return str(m.get("source_file") or m.get("source") or ev.source or "")

    l2_ranks = [i for i, ev in enumerate(pool, 1) if _layer(ev) == "advanced"]
    packed = finalize_with_layer_ranking(fused, policy, keep=5)
    packed, _ = apply_evidence_policy(packed, policy)
    pack = list(packed.text_evidences or [])
    l2_pack = [_src(ev) for ev in pack if _layer(ev) == "advanced"]
    # 跨学科污染：pack 里 L2 所属学科 ≠ 该 query 主导学科
    pack_subjects = [chapter_of_source(_src(ev)) for ev in pack]
    return {
        "query": query,
        "l2_in_pool": bool(l2_ranks),
        "l2_pool_ranks": l2_ranks,
        "l2_in_pack": bool(l2_pack),
        "l2_pack_sources": l2_pack,
        "pack_chapters": pack_subjects,
    }


def main() -> int:
    print("==== 1. L2 chunk 覆盖（按章级知识点）====")
    counts, per_subject, total = _chapter_index()
    print(f"L2 总 chunk: {total}  按学科: {per_subject}")
    print("章级分布:")
    for ch, n in sorted(counts.items(), key=lambda x: -x[1]):
        print(f"  {ch:<20} {n}")

    print("\n==== 2/3/4. method query 的 L2 归因 ====")
    queries = load_golden_queries(DEFAULT_GOLDEN_PATH, limit=60)
    print(f"（黄金集 n={len(queries)}；method 专项 {len(METHOD_QUERIES)} 条）")
    rows = []
    for q in METHOD_QUERIES:
        r = asyncio.run(_trace_query(q))
        rows.append(r)
        status = []
        if not r["l2_in_pool"]:
            status.append("B2/B:召回不到")
        elif not r["l2_in_pack"]:
            status.append("B3:召回后被截断")
        else:
            status.append("B1:OK")
        print(f"\n  {q}")
        print(
            f"    pool L2 ranks={r['l2_pool_ranks']}  pack L2={len(r['l2_pack_sources'])}  → {','.join(status)}"
        )
        for s in r["l2_pack_sources"]:
            print(f"      pack L2: {s}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps(
            {
                # 审计要求：归档必须自带时间戳，否则跨版本追溯只能靠文件 mtime
                "recorded_at": datetime.now(UTC).isoformat(),
                "l2_total": total,
                "l2_by_subject": per_subject,
                "l2_by_chapter": counts,
                "method_queries": rows,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"\narchive → {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
