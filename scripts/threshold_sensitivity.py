"""E-next · RRF Threshold Sensitivity（只改 threshold，不改默认算法）。

固定：同一 60 golden · 同一索引/embedding/reranker · 同一 top-k。
扫：threshold × {1.0, 0.95, 0.90, 0.85, 0}，看全局指标 + q052 是否恢复。

用法：
    uv run python scripts/threshold_sensitivity.py                 # full（E-next 主表）
    uv run python scripts/threshold_sensitivity.py --arm vector_only
    uv run python scripts/threshold_sensitivity.py --arm full,vector_only
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

OUT_DIR = ROOT / "evals" / "results" / "retrieval" / "ablation" / "threshold_sensitivity"

# 相对当前 effective_threshold 的乘子；0 = 关闭阈值
SCALES = (1.0, 0.95, 0.90, 0.85, 0.0)

Q052 = "目录项与索引结点（inode）的关系是什么？"


@contextmanager
def scale_threshold(scale: float):
    """把 effective_threshold 乘 scale（0=禁用阈值）。不改源码。"""
    import rag.pipeline as pipeline

    orig = pipeline._stage_dedup_and_threshold

    async def wrapper(results, query, cat, effective_threshold, **kw):
        return await orig(results, query, cat, effective_threshold * scale, **kw)

    pipeline._stage_dedup_and_threshold = wrapper  # type: ignore[assignment]
    try:
        yield
    finally:
        pipeline._stage_dedup_and_threshold = orig  # type: ignore[assignment]


@contextmanager
def capture_fallback():
    """捕获「阈值清空后保底 top-1」次数（空/降级率）。"""
    import logging

    hits = {"n": 0, "queries": []}

    class _H(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            msg = record.getMessage()
            if "阈值过滤后为空" in msg or "保底返回 top-1" in msg:
                hits["n"] += 1
                hits["queries"].append(msg[:120])

    handler = _H(level=logging.WARNING)
    logging.getLogger("rag.pipeline").addHandler(handler)
    try:
        yield hits
    finally:
        logging.getLogger("rag.pipeline").removeHandler(handler)


from evaluation.provenance import build_provenance  # noqa: E402
from evaluation.retrieval_gate import (  # noqa: E402
    DEFAULT_GOLDEN_PATH,
    QueryOutcome,
    compute_metrics,
    load_golden_queries,
)


async def run_scale(scale: float, queries, arm: str = "full") -> dict[str, Any]:
    from ablation_retrieval import CONFIGS, apply_config

    from rag.retriever import aretrieve_evidence_with_retry

    flags = CONFIGS[arm]
    outcomes: list[QueryOutcome] = []
    rows: list[dict[str, Any]] = []
    k = 5

    with apply_config(flags), scale_threshold(scale), capture_fallback() as fb:
        t0 = time.perf_counter()
        for idx, (query, expected, expected_kps) in enumerate(queries):
            fused, _ = await aretrieve_evidence_with_retry(
                query=query,
                k=k,
                use_rerank=True,
                max_retries=0,
                use_llm_verify=False,
            )
            docs = fused.text_evidences or []
            hit_cats = []
            hit_kps = []
            for ev in docs:
                meta = ev.metadata or {}
                hit_cats.append(str(meta.get("_collection") or ev.collection or ""))
                src = str(meta.get("source_file") or meta.get("source") or ev.source or "")
                from evaluation.retrieval_gate import chapter_of_source

                hit_kps.append(chapter_of_source(src))
            outcomes.append(
                QueryOutcome(
                    query=query,
                    expected_categories=expected,
                    hit_categories=hit_cats,
                    expected_knowledge_points=expected_kps,
                    hit_knowledge_points=hit_kps,
                )
            )
            is_q052 = query.strip() == Q052
            rows.append(
                {
                    "qid": f"q{idx:03d}",
                    "query": query[:40],
                    "is_q052": is_q052,
                    "n_evidence": len(docs),
                    "hit_cats": hit_cats,
                    "hit_kps": hit_kps,
                    "expected_kps": list(expected_kps),
                }
            )
        elapsed = round(time.perf_counter() - t0, 1)

    metrics = compute_metrics(outcomes)
    q052 = next((r for r in rows if r["is_q052"]), None)
    # 质量代理：证据是否落在期望学科（category_hit@1 已有；另报 q052 的 pack 构成）
    return {
        "arm": arm,
        "scale": scale,
        "metrics": metrics.as_dict(),
        "fallback_count": fb["n"],
        "fallback_rate": round(fb["n"] / max(len(queries), 1), 4),
        "elapsed_s": elapsed,
        "q052": {
            "n_evidence": q052["n_evidence"] if q052 else None,
            "hit_kps": q052["hit_kps"] if q052 else [],
            "hit_cats": q052["hit_cats"] if q052 else [],
            "expected_kps": q052["expected_kps"] if q052 else [],
            "kp_hit": (
                any(k in (q052["expected_kps"] or []) for k in q052["hit_kps"]) if q052 else None
            ),
        },
    }


async def main() -> int:
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", default="full", help="full | vector_only | 逗号分隔")
    args = ap.parse_args()
    arms = [a.strip() for a in args.arm.split(",") if a.strip()]

    queries = load_golden_queries(DEFAULT_GOLDEN_PATH, limit=60)
    print(f"golden n={len(queries)}  arms={arms}  scales={SCALES}")
    print("只改 effective_threshold 乘子；不动默认配置\n")

    all_results = []
    for arm in arms:
        print(f"######## arm={arm} ########")
        arm_results = []
        for s in SCALES:
            print(f"[{arm} scale={s}] ...", flush=True)
            r = await run_scale(s, queries, arm=arm)
            arm_results.append(r)
            all_results.append(r)
            m = r["metrics"]
            print(
                f"  kp_mrr={m['kp_mrr']:.4f}  kp_hit={m['kp_hit_at_k']:.4f}  "
                f"cat@1={m['category_hit_at_1']:.4f}  n_ev={m['mean_evidence_count']:.2f}  "
                f"fallback={r['fallback_count']} ({r['fallback_rate']:.2%})  "
                f"q052_kp_hit={r['q052']['kp_hit']}"
            )
        print(f"\n==== Threshold Sensitivity ({arm}, n=60) ====")
        print(
            f"{'scale':<8} {'kp_hit':>8} {'kp_mrr':>8} {'cat@1':>8} "
            f"{'cat_mrr':>8} {'n_ev':>8} {'fallback':>10} {'q052':>6}"
        )
        print("-" * 72)
        for r in arm_results:
            m = r["metrics"]
            print(
                f"{r['scale']:<8} {m['kp_hit_at_k']:>8.3f} {m['kp_mrr']:>8.3f} "
                f"{m['category_hit_at_1']:>8.3f} {m['category_mrr']:>8.3f} "
                f"{m['mean_evidence_count']:>8.2f} {r['fallback_rate']:>10.2%} "
                f"{str(r['q052']['kp_hit']):>6}"
            )
        print()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / f"threshold_sensitivity_{time.strftime('%Y%m%d_%H%M%S')}.json"
    path.write_text(
        json.dumps(
            {
                "design": "E-next: RRF threshold × scale; fixed 60 golden / index / top-k; no LLM",
                "arms": arms,
                "scales": list(SCALES),
                "results": all_results,
                **build_provenance("scripts/threshold_sensitivity.py"),
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"archive → {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
