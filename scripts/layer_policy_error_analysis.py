"""layer_policy error analysis：固定 probe 的 pack 构成诊断。

回答：
A. practice rec@pack=0.5 —— 目标层没进 pool，还是进 pool 后被挤出？
B. explain prec@pack=0.5 —— 谁占了非目标位？L1/L2 还是 legacy？

用法：
    uv run python scripts/layer_policy_error_analysis.py
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rag.evidence_policy import apply_evidence_policy  # noqa: E402
from rag.retrieval_policy import resolve_retrieval_policy  # noqa: E402
from rag.retriever import aretrieve_evidence_with_retry  # noqa: E402
from schema.retrieval_policy import LayerWeightProfile  # noqa: E402

# 与 layer_policy_experiment 固定 probe 一致
TARGETS = [
    {
        "id": "practice-bst",
        "mode": "practice",
        "q": "给我一道 BST 删除的练习题",
        "want_layers": ["advanced", "basic"],
    },
    {
        "id": "practice-huffman",
        "mode": "practice",
        "q": "出一道哈夫曼编码的计算题",
        "want_layers": ["advanced", "basic"],
    },
    {
        "id": "explain-q2",
        "mode": "explain",
        "q": "2019-Q2 为什么树的后根遍历对应二叉树中序？",
        "want_layers": ["exams", "advanced", "basic"],
    },
    {
        "id": "method-bst-delete",
        "mode": "method",
        "q": "BST 删除怎么做？双支结点如何处理？",
        "want_layers": ["advanced", "basic"],
    },
]

V1 = LayerWeightProfile(
    name="v1",
    # 只动语义层系数；legacy 是资产状态，不在权重表里
    layer_weights={"basic": 1.0, "advanced": 1.4, "exams": 1.0},
)


def _layer(meta: dict) -> str:
    return str(meta.get("kb_depth") or "legacy")


def _brief(ev) -> str:
    m = ev.metadata or {}
    c = (ev.content or "").replace("\n", " ")[:70]
    return f"layer={_layer(m)} role={m.get('doc_role')} id={m.get('chunk_id') or m.get('section_id')} | {c}"


def apply_v1(fused, policy, keep=8):
    weights = V1.layer_weights
    preferred = set(policy.preferred_layers)

    def key(item):
        idx, ev = item
        layer = _layer(ev.metadata or {})
        score = float((ev.metadata or {}).get("score") or getattr(ev, "score", 0) or 0.0)
        w = float(weights.get(layer, 1.0))
        if layer in preferred:
            w *= 1.15
        return (-score * w, idx)

    ranked = [ev for _, ev in sorted(enumerate(fused.text_evidences or []), key=key)]
    out = fused.model_copy(deep=True)
    out.text_evidences = ranked[:keep]
    return out, ranked


async def analyze_one(p: dict) -> dict:
    q, want = p["q"], set(p["want_layers"])
    policy = resolve_retrieval_policy(q)
    where = policy.eligibility_where()
    raw, _ = await aretrieve_evidence_with_retry(
        query=q,
        k=20,
        use_rerank=True,
        filter=where,
        max_retries=0,
        use_llm_verify=False,
        preferred_layers=list(policy.preferred_layers),
    )
    pool = list(raw.text_evidences or [])
    packed, full_ranked = apply_v1(raw, policy, keep=8)
    out, _ = apply_evidence_policy(packed, policy)
    pack = list(out.text_evidences or [])

    pool_layers = [_layer(e.metadata or {}) for e in pool]
    pack_layers = [_layer(e.metadata or {}) for e in pack]

    want_in_pool = [e for e in pool if _layer(e.metadata or {}) in want]
    want_in_pack = [e for e in pack if _layer(e.metadata or {}) in want]
    # 挤出分析：目标层在 rank 的第几，是否被截断
    want_ranks = [i for i, e in enumerate(full_ranked) if _layer(e.metadata or {}) in want]
    non_target_pack = [e for e in pack if _layer(e.metadata or {}) not in want]
    non_target_layer_counts: dict[str, int] = {}
    for e in non_target_pack:
        ly = _layer(e.metadata or {})
        non_target_layer_counts[ly] = non_target_layer_counts.get(ly, 0) + 1

    diagnosis = []
    if not want_in_pool:
        diagnosis.append("A1 目标层未进候选池（路由/召回问题，非权重）")
    elif want_in_pool and not want_in_pack:
        diagnosis.append(f"A2 目标层在 pool 但被挤出 pack（排名过低：want_ranks={want_ranks[:8]}）")
    elif want_in_pool and want_in_pack and len(want_in_pack) < len(pack):
        diagnosis.append(f"A3 目标层在 pack 但非目标占位多（prec 低）：{non_target_layer_counts}")
    if non_target_layer_counts.get("legacy", 0) >= max(1, len(pack) // 2):
        diagnosis.append("B1 legacy 占比高 —— 压 legacy 比抬 L3 更关键")
    if "exams" in want and non_target_layer_counts.get("legacy", 0) >= 3:
        diagnosis.append("B2 explain 精度低主因是 legacy/旧讲义，而非 exams 权重")

    return {
        "id": p["id"],
        "mode": policy.task_mode,
        "query": q,
        "n_pool": len(pool),
        "n_pack": len(pack),
        "pool_layers": pool_layers,
        "pack_layers": pack_layers,
        "want_in_pool": len(want_in_pool),
        "want_in_pack": len(want_in_pack),
        "want_ranks_in_full": want_ranks[:12],
        "non_target_pack_counts": non_target_layer_counts,
        "diagnosis": diagnosis,
        "pack_brief": [_brief(e) for e in pack],
        "pool_target_brief": [_brief(e) for e in want_in_pool[:5]],
    }


async def main() -> int:
    print("==== layer_policy error analysis (v1) ====")
    results = []
    for p in TARGETS:
        r = await analyze_one(p)
        results.append(r)
        print(f"\n## {r['id']} mode={r['mode']} pack={r['n_pack']} pool={r['n_pool']}")
        print(f"   pack_layers={r['pack_layers']}")
        print(f"   want in pool={r['want_in_pool']} in pack={r['want_in_pack']}")
        print(f"   want ranks in full={r['want_ranks_in_full']}")
        print(f"   non_target={r['non_target_pack_counts']}")
        for d in r["diagnosis"]:
            print(f"   → {d}")
        print("   pack:")
        for b in r["pack_brief"]:
            print(f"     - {b}")

    out = ROOT / "evals" / "results" / "layer_policy" / "error_analysis_v1.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\nwrote {out}")

    # 汇总答案
    print("\n==== 回答 ====")
    print("A practice rec@pack=0.5：见 practice-* 的 diagnosis（A1 无进池 / A2 被挤出）")
    print("B explain prec@pack=0.5：看 non_target_pack_counts 是否以 legacy 为主（B1/B2）")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
