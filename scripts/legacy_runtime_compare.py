"""Legacy 三种运行时策略对比（不改索引、不改 layer_weight）。

策略（eligibility / ranking 可配，见 RETRIEVAL_POLICY）：
  keep     原样保留 legacy
  downrank 保留但降权（legacy_weight_class=downrank）
  drop     候选池剔除 legacy

指标分列：
  layer_recall@pool / @pack、layer_precision@pack、legacy_in_pack、safety_fail

用法：
    uv run python scripts/legacy_runtime_compare.py
"""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rag.evidence_policy import apply_evidence_policy  # noqa: E402
from rag.retriever import aretrieve_evidence_with_retry  # noqa: E402
from rag.task_policy import resolve_task_policy  # noqa: E402

# 与 layer_policy_experiment 相同固定 probe
PROBES = [
    (
        "method-tree-build",
        "method",
        "已知先序和中序遍历，如何还原二叉树？步骤是什么？",
        ["advanced", "basic"],
    ),
    ("method-bst-delete", "method", "BST 删除怎么做？双支结点如何处理？", ["advanced", "basic"]),
    ("practice-bst", "practice", "给我一道 BST 删除的练习题", ["advanced", "basic"]),
    ("practice-huffman", "practice", "出一道哈夫曼编码的计算题", ["advanced", "basic"]),
    (
        "explain-q2",
        "explain",
        "2019-Q2 为什么树的后根遍历对应二叉树中序？",
        ["exams", "advanced", "basic"],
    ),
    (
        "learn-traversal",
        "learn",
        "二叉树的遍历方式有哪些？为什么要有中序遍历？",
        ["basic", "advanced"],
    ),
]

OUT = ROOT / "evals" / "results" / "legacy_runtime"


def _layer(m: dict) -> str:
    return str(m.get("kb_depth") or "legacy")


def rank_pack(fused, policy, mode: str, keep: int = 8):
    """mode: keep | downrank | drop —— 只影响排序/入池，不改安全裁剪。"""
    preferred = set(policy.preferred_layers)

    def key(item):
        idx, ev = item
        layer = _layer(ev.metadata or {})
        score = float((ev.metadata or {}).get("score") or getattr(ev, "score", 0) or 0.0)
        if layer == "legacy":
            if mode == "drop":
                w = 0.0
            elif mode == "downrank":
                w = 0.5
            else:
                w = 1.0
        else:
            w = 1.35 if layer in preferred else 1.0
        return (-score * w, idx)

    ranked = [ev for _, ev in sorted(enumerate(fused.text_evidences or []), key=key)]
    if mode == "drop":
        ranked = [e for e in ranked if _layer(e.metadata or {}) != "legacy"]
    out = fused.model_copy(deep=True)
    out.text_evidences = ranked[:keep]
    return out


async def run_mode(strategy: str) -> dict:
    rows = []
    for pid, want_mode, q, want_layers in PROBES:
        policy = resolve_task_policy(q)
        fused, _ = await aretrieve_evidence_with_retry(
            query=q,
            k=20,
            use_rerank=True,
            filter=policy.eligibility_where(),
            max_retries=0,
            use_llm_verify=False,
            preferred_layers=list(policy.preferred_layers),
        )
        packed = rank_pack(fused, policy, strategy, keep=8)
        out, _ = apply_evidence_policy(packed, policy)
        layers = [_layer(e.metadata or {}) for e in (out.text_evidences or [])]
        want = set(want_layers)
        rec_pool = (
            1.0
            if any(_layer(e.metadata or {}) in want for e in (fused.text_evidences or []))
            else 0.0
        )
        rec_pack = 1.0 if any(x in want for x in layers) else 0.0
        prec = sum(1 for x in layers if x in want) / max(len(layers), 1)
        legacy_n = sum(1 for x in layers if x == "legacy")
        rows.append(
            {
                "id": pid,
                "mode": policy.task_mode,
                "n_pack": len(layers),
                "layer_recall_pool": rec_pool,
                "layer_recall_pack": rec_pack,
                "layer_precision_pack": round(prec, 3),
                "legacy_in_pack": legacy_n,
                "pack_layers": layers,
            }
        )
    agg = {
        "layer_recall_pool": round(sum(r["layer_recall_pool"] for r in rows) / len(rows), 3),
        "layer_recall_pack": round(sum(r["layer_recall_pack"] for r in rows) / len(rows), 3),
        "layer_precision_pack": round(sum(r["layer_precision_pack"] for r in rows) / len(rows), 3),
        "legacy_in_pack_sum": sum(r["legacy_in_pack"] for r in rows),
    }
    return {"strategy": strategy, "by_probe": rows, "aggregate": agg}


async def main() -> int:
    report = {
        "_meta": {
            "recorded_at": datetime.now(UTC).isoformat(),
            "note": "Legacy 运行时三策略；不改索引、不改 layer_weight 数字",
            "probes": [p[0] for p in PROBES],
        },
        "strategies": [],
    }
    for strategy in ("keep", "downrank", "drop"):
        print(f"==== legacy strategy: {strategy} ====")
        res = await run_mode(strategy)
        report["strategies"].append(res)
        a = res["aggregate"]
        print(
            f"  recall@pool={a['layer_recall_pool']} recall@pack={a['layer_recall_pack']} "
            f"prec@pack={a['layer_precision_pack']} legacy_in_pack={a['legacy_in_pack_sum']}"
        )
        for r in res["by_probe"]:
            print(
                f"    {r['id']}: prec={r['layer_precision_pack']} legacy={r['legacy_in_pack']} {r['pack_layers']}"
            )

    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"legacy_runtime_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {path}")

    # 简表
    print("\n==== 对比 ====")
    for res in report["strategies"]:
        a = res["aggregate"]
        print(
            f"  {res['strategy']:10s}  rec_pack={a['layer_recall_pack']}  "
            f"prec_pack={a['layer_precision_pack']}  legacy_sum={a['legacy_in_pack_sum']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
