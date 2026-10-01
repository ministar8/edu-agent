"""基础 RAG 消融：朴素纯向量 RAG vs 本系统。

    baseline = 语义向量 top-k（无 BM25/元数据/分解/HyDE/窗口/任务策略）
    ours     = 完整系统（多路召回 + task_mode → preferred_layers → legacy_policy）

指标双口径：
    检索口径  kp_hit@k / kp_mrr / cat@1（复用 retrieval_gate）
    任务口径  任务目标层命中 + 答案泄漏（复用 task_layer 逻辑）

用法：
    uv run python scripts/basic_rag_ablation.py
    uv run python scripts/basic_rag_ablation.py --limit 60
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from task_layer_ablation import (  # noqa: E402
    TASK_QUERIES,
    TASK_TARGET_LAYER,
    _baseline_policy,
    _ours_policy,
    run_one,
)

from evaluation.provenance import build_provenance  # noqa: E402
from evaluation.retrieval_gate import (  # noqa: E402
    DEFAULT_GOLDEN_PATH,
    GATE_K,
    QueryOutcome,
    chapter_of_source,
    compute_metrics,
    load_golden_queries,
)

OUT_DIR = ROOT / "evals" / "results" / "retrieval" / "ablation"


async def run_retrieval_arm(arm: str, queries, limit: int | None) -> dict:
    """在黄金集上跑检索口径指标（basic_rag = 纯向量，ours = 完整）。"""
    from dataclasses import replace

    from rag.query_classifier import RetrievalDepth
    from rag.retriever import aretrieve_evidence_with_retry

    basic = arm == "basic_rag"
    # baseline 用浅层策略：跳过分解/元数据/BM25/重排
    depth = replace(
        RetrievalDepth(
            depth="standard",
            k=GATE_K,
            skip_bm25=True,
            skip_decompose=True,
            skip_hyde=True,
            skip_metadata_routes=True,
            skip_rerank=True,
        )
    )

    outcomes: list[QueryOutcome] = []
    t0 = time.perf_counter()
    for query, expected, expected_kps in queries:
        try:
            if basic:
                fused, _ = await aretrieve_evidence_with_retry(
                    query=query,
                    k=GATE_K,
                    use_rerank=False,
                    max_retries=0,
                    use_llm_verify=False,
                    depth=depth,
                    filter={"kb_depth": {"$in": ["basic", "advanced", "exams"]}},
                )
            else:
                fused, _ = await aretrieve_evidence_with_retry(
                    query=query,
                    k=GATE_K,
                    use_rerank=True,
                    max_retries=0,
                    use_llm_verify=False,
                )
        except Exception:  # noqa: BLE001
            outcomes.append(
                QueryOutcome(
                    query=query,
                    expected_categories=expected,
                    expected_knowledge_points=expected_kps,
                )
            )
            continue

        docs = fused.text_evidences or []
        hit_cats, hit_kps = [], []
        for ev in docs:
            meta = ev.metadata or {}
            hit_cats.append(str(meta.get("_collection") or ev.collection or ""))
            hit_kps.append(
                chapter_of_source(
                    str(meta.get("source_file") or meta.get("source") or ev.source or "")
                )
            )
        outcomes.append(
            QueryOutcome(
                query=query,
                expected_categories=expected,
                hit_categories=hit_cats,
                expected_knowledge_points=expected_kps,
                hit_knowledge_points=hit_kps,
            )
        )

    metrics = compute_metrics(outcomes)
    return {"arm": arm, "elapsed_s": round(time.perf_counter() - t0, 1), **metrics.as_dict()}


async def run_task_arm(arm: str) -> dict:
    """任务口径：layer hit + leakage。"""
    by_mode: dict[str, dict] = {}
    for mode, qs in TASK_QUERIES.items():
        hits = leaks = n_hidden = 0
        for q in qs:
            policy = _baseline_policy(mode) if arm == "basic_rag" else _ours_policy(mode)
            if arm == "basic_rag":
                # basic RAG：层偏好平铺 + legacy 同主池（与 task_layer baseline 一致）
                pass
            row = await run_one(q, mode, policy)
            hits += int(row["layer_hit"])
            if row.get("answer_hidden_mode"):
                n_hidden += 1
                leaks += int(row["leakage"])
        by_mode[mode] = {
            "layer_hit_rate": round(hits / len(qs), 4) if qs else 0.0,
            "leakage_rate": round(leaks / n_hidden, 4) if n_hidden else None,
        }
    rates = [v["layer_hit_rate"] for v in by_mode.values()]
    return {"arm": arm, "by_mode": by_mode, "macro_layer_hit": round(sum(rates) / len(rates), 4)}


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=60)
    args = ap.parse_args()

    queries = load_golden_queries(DEFAULT_GOLDEN_PATH, limit=args.limit)
    print(f"golden n={len(queries)}")

    print("[1/4] basic_rag 检索口径 ...", flush=True)
    ret_basic = await run_retrieval_arm("basic_rag", queries, args.limit)
    print("[2/4] ours 检索口径 ...", flush=True)
    ret_ours = await run_retrieval_arm("ours", queries, args.limit)
    print("[3/4] basic_rag 任务口径 ...", flush=True)
    task_basic = await run_task_arm("basic_rag")
    print("[4/4] ours 任务口径 ...", flush=True)
    task_ours = await run_task_arm("ours")

    print("\n==== 基础 RAG vs 本系统（检索口径）====")
    cols = ("kp_hit_at_k", "kp_mrr", "category_hit_at_1", "category_mrr", "mean_evidence_count")
    print(f"{'arm':<12}" + "".join(f"{c:>18}" for c in cols))
    for r in (ret_basic, ret_ours):
        print(f"{r['arm']:<12}" + "".join(f"{r.get(c):>18}" for c in cols))
    print(
        "Δ(ours-bas)" + "".join(f"{ret_ours.get(c, 0) - ret_basic.get(c, 0):>+18.4f}" for c in cols)
    )

    print("\n==== 基础 RAG vs 本系统（任务口径）====")
    print(f"{'task_mode':<10} {'target':<16} {'basic':>10} {'ours':>10} {'Δ':>8}")
    print("-" * 58)
    for mode in TASK_QUERIES:
        b = task_basic["by_mode"].get(mode, {})
        o = task_ours["by_mode"].get(mode, {})
        bh, oh = b.get("layer_hit_rate", 0), o.get("layer_hit_rate", 0)
        tgt = ",".join(TASK_TARGET_LAYER.get(mode, ()))
        print(f"{mode:<10} {tgt:<16} {bh:>10.3f} {oh:>10.3f} {oh - bh:>+8.3f}")
    print("-" * 58)
    print(
        f"{'MACRO':<10} {'':<16} {task_basic['macro_layer_hit']:>10.3f} "
        f"{task_ours['macro_layer_hit']:>10.3f} "
        f"{task_ours['macro_layer_hit'] - task_basic['macro_layer_hit']:>+8.3f}"
    )

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    path = OUT_DIR / f"basic_rag_{ts}.json"
    path.write_text(
        json.dumps(
            {
                "recorded_at": ts,
                "limit": args.limit,
                # 当次配置快照（实验可追溯；YAML 是文档，此处是实际执行口径）
                "config_snapshot": {
                    "basic_rag": "semantic top-k only (no bm25/metadata/decompose/hyde/rerank/task_policy)",
                    "ours": "full system (multi-route + task_mode policy)",
                },
                "retrieval": {"basic_rag": ret_basic, "ours": ret_ours},
                "task": {"basic_rag": task_basic, "ours": task_ours},
                **build_provenance("scripts/basic_rag_ablation.py"),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\narchive → {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
