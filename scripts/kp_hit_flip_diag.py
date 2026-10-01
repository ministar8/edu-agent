"""D 诊断（只读，不改源码）：定位修复前后 kp_hit 掉分的那一条 query。

用法：
    uv run python scripts/kp_hit_flip_diag.py
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

LIMIT = 60


# ── 复刻修复前/后的 _raw_search（唯一差别：排序方向）──────────
def _make_raw_search(mode: str):
    """mode='violated' 复刻修复前（按 -score 降序）；'fixed' 为当前源码行为。"""
    import jieba
    from langchain_core.documents import Document  # noqa: F401

    from rag.bm25 import bm25_search
    from rag.rag_utils import content_key
    from rag.routes import _SEMANTIC_OVERSAMPLE, _copy_results, _query_cache

    def _raw_search(query, collection_name, k, filter=None, route_name=""):
        filter_key = json.dumps(filter, sort_keys=True, ensure_ascii=False) if filter else ""
        cache_key = f"{collection_name}:{route_name}:{query}:{filter_key}:k={k}"
        cached = _query_cache.get(cache_key)
        if cached is not None:
            return _copy_results(cached)

        if route_name == "keyword_bm25":
            from rag.recall import _BM25_STOP_WORDS

            allow = {
                "栈",
                "堆",
                "树",
                "图",
                "串",
                "队",
                "链",
                "表",
                "网",
                "库",
                "锁",
                "页",
                "段",
                "核",
                "集",
            }
            terms = [
                w
                for w in jieba.cut_for_search(query)
                if w.strip() and w not in _BM25_STOP_WORDS and (len(w) >= 2 or w in allow)
            ]
            if len(terms) > 6:
                terms = sorted(terms, key=len, reverse=True)[:6]
            if not terms:
                terms = [query.strip()]
            results = bm25_search(terms, collection_name, k, filter=filter)
        else:
            from rag.vectorstore import get_vector_store_manager

            oversampled = get_vector_store_manager().similarity_search_with_score(
                collection_name, query, k=k * _SEMANTIC_OVERSAMPLE, filter=filter
            )
            if mode == "violated":
                results = sorted(oversampled, key=lambda p: (-p[1], content_key(p[0])))[:k]
            else:
                results = sorted(oversampled, key=lambda p: (p[1], content_key(p[0])))[:k]

        for doc, _s in results:
            doc.metadata["_collection"] = collection_name
        _query_cache.set(cache_key, results)
        return results

    return _raw_search


def _kp_rank(outcome) -> int | None:
    return outcome.first_correct_kp_rank


async def collect(mode: str, queries) -> tuple[list, dict]:
    import rag.routes as routes
    from evaluation.retrieval_gate import QueryOutcome, chapter_of_source
    from rag.retriever import aretrieve_evidence_with_retry

    routes._raw_search = _make_raw_search(mode)  # type: ignore[assignment]
    routes._query_cache.clear()

    outcomes: list[QueryOutcome] = []
    per_query: dict[str, dict] = {}
    for query, expected, kps in queries:
        fused, _ = await aretrieve_evidence_with_retry(
            query=query, k=5, use_rerank=True, max_retries=0, use_llm_verify=False
        )
        docs = fused.text_evidences or []
        hits = []
        for ev in docs:
            m = ev.metadata or {}
            src = str(m.get("source_file") or m.get("source") or ev.source or "")
            hits.append(
                (
                    str(m.get("_collection") or ev.collection or ""),
                    chapter_of_source(src),
                    src,
                )
            )
        oc = QueryOutcome(
            query=query,
            expected_categories=expected,
            hit_categories=[h[0] for h in hits],
            expected_knowledge_points=kps,
            hit_knowledge_points=[h[1] for h in hits],
        )
        outcomes.append(oc)
        per_query[query] = {
            "kp_rank": _kp_rank(oc),
            "exp_kps": list(kps),
            "pack": [{"ch": h[1], "src": h[2]} for h in hits],
        }
    return outcomes, per_query


async def main() -> int:
    from evaluation.retrieval_gate import load_golden_queries

    golden = str(ROOT / "evals/datasets/golden/sample_408.jsonl")
    queries = load_golden_queries(golden, limit=LIMIT)

    _, before = await collect("violated", queries)
    _, after = await collect("fixed", queries)

    flipped = []
    for q in before:
        b, a = before[q]["kp_rank"], after[q]["kp_rank"]
        b_hit = b is not None
        a_hit = a is not None
        if b_hit != a_hit:
            flipped.append((q, b, a))
    print(f"n={len(queries)}  kp_hit 跳变的 query 数 = {len(flipped)}")
    for q, b, a in flipped:
        print(f"  '{q[:46]}'  before_rank={b}  after_rank={a}")

    if not flipped:
        return 0

    for q, b, a in flipped:
        print("\n" + "=" * 96)
        print(f"QUERY: {q}")
        print(f"gold kps = {before[q]['exp_kps']}")
        for tag, data in (("修复前(-score 降序)", before[q]), ("修复后(当前)", after[q])):
            print(f"\n── {tag}：kp_rank={data['kp_rank']}")
            for i, row in enumerate(data["pack"], 1):
                mark = "★" if row["ch"] in (data["exp_kps"] or []) else " "
                print(f"   {mark}{i} chapter={row['ch']:<12} {row['src']}")

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
