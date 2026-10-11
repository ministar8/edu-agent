"""Task Mode × Layer Policy 交互实验。

问题：层策略与任务是否存在交互？（不同任务是否需要不同的层策略）

对照（安全字段一律冻结，只动 preferred_layers）：

    flat      ：全任务 preferred=[basic, advanced, exams]，无任务区分
    ours      ：task_mode → preferred_layers（系统默认映射）
    prefer_l1 ：全任务 preferred=[basic]
    prefer_l2 ：全任务 preferred=[advanced]
    prefer_l3 ：全任务 preferred=[exams]

任务专有指标（与 basic_rag_ablation 共用 `task_layer_common`，保证同口径）：

    learn    → L1 hit（basic 进证据包）
    method   → L2 hit（advanced 进包）
    practice → L2/L3 hit + 答案泄漏
    grade    → L3 hit（exams 进包）
    explain  → L3 hit
    verify   → L3 hit

用法：
    uv run python scripts/exp/task_mode_layer_policy.py
    uv run python scripts/exp/task_mode_layer_policy.py --limit-per-mode 4
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from collections.abc import Iterable
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from lib.task_layer_common import (  # noqa: E402
    _ANS_BODY_RE,
    _ANS_FIELD_RE,
    TASK_QUERIES,
    TASK_TARGET_LAYER,
    _pack_blob,
    _pack_layers,
)

from evaluation.provenance import build_provenance  # noqa: E402
from rag.retrieval.evidence_policy import (  # noqa: E402
    apply_evidence_policy,
    finalize_with_layer_ranking,
)
from rag.retrieval.retriever import aretrieve_evidence_with_retry  # noqa: E402
from rag.retrieval.task_policy import policy_for_mode  # noqa: E402
from schema.task_policy import TaskPolicy  # noqa: E402

OUT_DIR = ROOT / "evals" / "results" / "retrieval" / "layer_policy"

# Layer Policy 臂：只改 preferred_layers（top-up + 排序软偏好）
# 安全字段（exam_resources / answer_policy / legacy_policy）一律取 policy_for_mode
LAYER_POLICIES: dict[str, dict[str, Any]] = {
    "flat": {
        "preferred": ["basic", "advanced", "exams"],
        "note": "全层平铺，无任务区分",
    },
    "ours": {
        "preferred": None,  # None = 用 policy_for_mode 的任务映射
        "note": "task_mode → preferred_layers（系统默认）",
    },
    "prefer_l1": {
        "preferred": ["basic"],
        "note": "全局软偏好 L1 basic",
    },
    "prefer_l2": {
        "preferred": ["advanced"],
        "note": "全局软偏好 L2 advanced",
    },
    "prefer_l3": {
        "preferred": ["exams"],
        "note": "全局软偏好 L3 exams",
    },
}


def _build_policy(mode: str, policy_id: str) -> TaskPolicy:
    """安全字段取系统默认；layer_policy 只覆盖 preferred_layers。"""
    p = policy_for_mode(mode)  # type: ignore[arg-type]
    preferred = LAYER_POLICIES[policy_id]["preferred"]
    if preferred is None:
        return p.model_copy(update={"layer_policy_id": policy_id})
    return p.model_copy(
        update={
            "preferred_layers": preferred,
            "layer_policy_id": policy_id,
        }
    )


async def run_one(query: str, mode: str, policy: TaskPolicy) -> dict[str, Any]:
    fused, _ = await aretrieve_evidence_with_retry(
        query=query,
        k=5,
        use_rerank=True,
        max_retries=0,
        use_llm_verify=False,
        filter=policy.eligibility_where(),
        preferred_layers=list(policy.preferred_layers),
        eligible_layers=policy.eligible_semantic_layers(),
    )
    fused = finalize_with_layer_ranking(fused, policy, keep=5)
    fused, _flags = apply_evidence_policy(fused, policy)

    layers = _pack_layers(fused)
    targets = TASK_TARGET_LAYER.get(mode, ())
    layer_hit = any(t in layers for t in targets)
    blob = _pack_blob(fused)
    # 泄漏只在「答案隐藏」模式上有意义（learn/method/practice/verify）
    answer_hidden = mode in ("learn", "method", "practice", "verify")
    leakage = bool(answer_hidden and (_ANS_FIELD_RE.search(blob) or _ANS_BODY_RE.search(blob)))
    return {
        "query": query,
        "mode": mode,
        "layer_policy_id": policy.layer_policy_id,
        "preferred_layers": list(policy.preferred_layers),
        "layers": layers,
        "layer_hit": layer_hit,
        "leakage": leakage,
        "answer_hidden_mode": answer_hidden,
        "n_pack": len(layers),
        "legacy_policy": policy.legacy_policy,
    }


async def run_policy_arm(policy_id: str, queries: dict[str, list[str]]) -> dict[str, Any]:
    """跑一层策略臂，按任务模式聚合。"""
    by_mode: dict[str, dict[str, Any]] = {}
    all_rows: list[dict[str, Any]] = []
    for mode, qs in queries.items():
        hits = 0
        leaks = 0
        n = 0
        n_hidden = 0
        n_pack_sum = 0
        n_nonempty = 0
        prec_sum = 0.0
        targets = set(TASK_TARGET_LAYER.get(mode, ()))
        for q in qs:
            policy = _build_policy(mode, policy_id)
            row = await run_one(q, mode, policy)
            all_rows.append(row)
            n += 1
            hits += int(row["layer_hit"])
            n_pack_sum += int(row["n_pack"])
            n_nonempty += int(row["n_pack"] > 0)
            layers = row["layers"]
            prec_sum += sum(1 for x in layers if x in targets) / max(len(layers), 1)
            if row.get("answer_hidden_mode"):
                n_hidden += 1
                leaks += int(row["leakage"])
        by_mode[mode] = {
            "n": n,
            "layer_hit_rate": round(hits / n, 4) if n else 0.0,
            "layer_precision_pack": round(prec_sum / n, 4) if n else 0.0,
            "leakage_rate": round(leaks / n_hidden, 4) if n_hidden else None,
            "pack_nonempty_rate": round(n_nonempty / n, 4) if n else 0.0,
            "mean_n_pack": round(n_pack_sum / n, 2) if n else 0.0,
            "target_layers": list(TASK_TARGET_LAYER.get(mode, ())),
        }
    rates = [v["layer_hit_rate"] for v in by_mode.values()]
    return {
        "layer_policy": policy_id,
        "note": LAYER_POLICIES[policy_id]["note"],
        "by_mode": by_mode,
        "macro_layer_hit": round(sum(rates) / len(rates), 4) if rates else 0.0,
        "rows": all_rows,
    }


def _print_matrix_table(
    title: str,
    results: dict[str, dict[str, Any]],
    key: str,
    modes: Iterable[str],
    *,
    fmt: str = ">12.3f",
    default: Any = 0.0,
) -> None:
    """打印一张 task_mode × layer_policy 矩阵（fmt 控格式，取到 None 记 n/a）。"""
    policy_ids = list(LAYER_POLICIES)
    header = f"{'task_mode':<10}" + "".join(f"{p:>12}" for p in policy_ids)
    print(f"\n==== {title}====")
    print(header)
    print("-" * len(header))
    for mode in modes:
        line = f"{mode:<10}"
        for p in policy_ids:
            v = results[p]["by_mode"].get(mode, {}).get(key, default)
            line += f"{v:{fmt}}" if v is not None else f"{'n/a':>12}"
        print(line)


def print_matrix(results: dict[str, dict[str, Any]]) -> None:
    policy_ids = list(LAYER_POLICIES)
    print("\n==== Task Mode × Layer Policy（layer_hit_rate）====")
    header = f"{'task_mode':<10} {'target':<16}" + "".join(f"{p:>12}" for p in policy_ids)
    print(header)
    print("-" * len(header))
    for mode in TASK_QUERIES:
        targets = ",".join(TASK_TARGET_LAYER.get(mode, ()))
        line = f"{mode:<10} {targets:<16}"
        best = -1.0
        best_p = ""
        for p in policy_ids:
            v = results[p]["by_mode"].get(mode, {}).get("layer_hit_rate", 0.0)
            line += f"{v:>12.3f}"
            if v > best:
                best = v
                best_p = p
        # 标出该任务的最优策略
        line += f"   best={best_p}"
        print(line)
    print("-" * len(header))
    line = f"{'MACRO':<10} {'':<16}"
    for p in policy_ids:
        line += f"{results[p]['macro_layer_hit']:>12.3f}"
    print(line)

    _print_matrix_table(
        "layer_precision@pack（目标层在包内占比）", results, "layer_precision_pack", TASK_QUERIES
    )
    _print_matrix_table(
        "pack_nonempty_rate（非空 Evidence Pack 占比）", results, "pack_nonempty_rate", TASK_QUERIES
    )
    _print_matrix_table(
        "mean_n_pack（证据包条数；prefer_l3 在禁 L3 任务上会被安全裁剪掏空）",
        results,
        "mean_n_pack",
        TASK_QUERIES,
        fmt=">12.2f",
    )

    print("\n（layer_hit = 证据包命中任务目标层；安全字段各臂相同，只动 preferred_layers）")
    print("（leakage 仅统计 answer-hidden 模式；grade/explain 的 answer_policy=released 不计）")

    _print_matrix_table(
        "leakage_rate（answer-hidden 模式）",
        results,
        "leakage_rate",
        ["learn", "method", "practice", "verify"],
        fmt=">12",
        default=None,
    )


def print_interaction(results: dict[str, dict[str, Any]]) -> None:
    """交互摘要：每个任务上最优策略 vs ours。"""
    print("\n==== 交互摘要 ====")
    print(
        f"{'task_mode':<10} {'best_policy':<12} {'best_hit':>10} {'ours_hit':>10} {'Δ best-ours':>12}"
    )
    print("-" * 56)
    for mode in TASK_QUERIES:
        hits = {
            p: results[p]["by_mode"].get(mode, {}).get("layer_hit_rate", 0.0)
            for p in LAYER_POLICIES
        }
        best_p = max(hits, key=hits.get)
        ours_v = hits.get("ours", 0.0)
        print(
            f"{mode:<10} {best_p:<12} {hits[best_p]:>10.3f} {ours_v:>10.3f} "
            f"{hits[best_p] - ours_v:>+12.3f}"
        )


def _write_archive(results: dict[str, dict[str, Any]], queries: dict[str, list[str]]) -> Path:
    """把本次结果落盘归档（含 provenance），返回写入路径。"""
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    path = OUT_DIR / f"task_mode_x_layer_policy_{ts}.json"
    path.write_text(
        json.dumps(
            {
                "recorded_at": ts,
                "queries": queries,
                "config_snapshot": {
                    "design": "Task Mode × Layer Policy（交互矩阵）",
                    "frozen": [
                        "exam_resources",
                        "answer_policy",
                        "explanation_policy",
                        "legacy_policy",
                    ],
                    "varied": "preferred_layers only",
                    "layer_policies": {
                        k: {
                            "preferred": v["preferred"] or "task_mapping",
                            "note": v["note"],
                        }
                        for k, v in LAYER_POLICIES.items()
                    },
                    "task_target_layer": TASK_TARGET_LAYER,
                },
                "results": {
                    p: {
                        "note": r["note"],
                        "macro_layer_hit": r["macro_layer_hit"],
                        "by_mode": r["by_mode"],
                    }
                    for p, r in results.items()
                },
                "rows": {p: r["rows"] for p, r in results.items()},
                **build_provenance("scripts/exp/task_mode_layer_policy.py"),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return path


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit-per-mode", type=int, default=6)
    ap.add_argument("--policies", default="", help="逗号分隔，只跑指定臂（默认全跑）")
    args = ap.parse_args()

    policy_ids = (
        [x.strip() for x in args.policies.split(",") if x.strip()]
        if args.policies
        else list(LAYER_POLICIES)
    )
    for p in policy_ids:
        if p not in LAYER_POLICIES:
            print(f"unknown layer policy {p}")
            return 2

    queries = {m: qs[: args.limit_per_mode] for m, qs in TASK_QUERIES.items()}
    n_q = sum(len(v) for v in queries.values())
    print(f"queries: {n_q} total  {{{', '.join(f'{m}:{len(q)}' for m, q in queries.items())}}}")
    print(f"layer_policies: {policy_ids}")
    print("安全字段冻结；只动 preferred_layers")

    t0 = time.perf_counter()
    results: dict[str, dict[str, Any]] = {}
    for p in policy_ids:
        print(f"\n---- arm={p} ({LAYER_POLICIES[p]['note']}) ----", flush=True)
        results[p] = await run_policy_arm(p, queries)
        print(f"  macro_layer_hit={results[p]['macro_layer_hit']}")

    print_matrix(results)
    print_interaction(results)

    path = _write_archive(results, queries)
    print(f"\narchive → {path}")
    print(f"elapsed={time.perf_counter() - t0:.0f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
