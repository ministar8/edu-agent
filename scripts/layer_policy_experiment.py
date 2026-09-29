"""layer_policy 实验：固定 Probe，只改权重，分指标对比。

原则（与 RETRIEVAL_POLICY §9.1 一致）：
- probe 题面冻结，不随实验更换
- 只改 layer_weights / boost；不动 exam_resources / answer_policy 等安全字段
- 指标分列：layer_recall@pool、layer_recall@pack、layer_precision@pack、pack 占比

用法：
    uv run python scripts/layer_policy_experiment.py
    uv run python scripts/layer_policy_experiment.py --profile v2
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rag.evidence import FusedEvidence  # noqa: E402
from rag.evidence_policy import apply_evidence_policy  # noqa: E402
from rag.retrieval_policy import resolve_retrieval_policy  # noqa: E402
from rag.retriever import aretrieve_evidence_with_retry  # noqa: E402
from schema.retrieval_policy import LayerWeightProfile  # noqa: E402

OUT_DIR = ROOT / "evals" / "results" / "layer_policy"

# ★ 固定 Probe（禁止每轮换题）
FIXED_PROBES = [
    {
        "id": "method-tree-build",
        "mode": "method",
        "q": "已知先序和中序遍历，如何还原二叉树？步骤是什么？",
        "want_layers": ["advanced", "basic"],
    },
    {
        "id": "method-bst-delete",
        "mode": "method",
        "q": "BST 删除怎么做？双支结点如何处理？",
        "want_layers": ["advanced", "basic"],
    },
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
        "id": "learn-traversal",
        "mode": "learn",
        "q": "二叉树的遍历方式有哪些？为什么要有中序遍历？",
        "want_layers": ["basic", "advanced"],
    },
]

# ★ 固定 profile：只动排序系数（安全字段见 schema 校验，禁止写入）
PROFILES: dict[str, LayerWeightProfile] = {
    "v0": LayerWeightProfile(
        name="v0",
        layer_weights={"basic": 1.0, "advanced": 1.0, "exams": 1.0, "legacy": 1.0},
    ),
    "v1": LayerWeightProfile(
        name="v1",
        # 偏 L2：method/practice 应多出 advanced
        layer_weights={"basic": 1.0, "advanced": 1.4, "exams": 1.0, "legacy": 0.7},
    ),
    "v2": LayerWeightProfile(
        name="v2",
        # 偏 L1：概念课多出 basic
        layer_weights={"basic": 1.4, "advanced": 1.1, "exams": 1.0, "legacy": 0.7},
    ),
    "v3": LayerWeightProfile(
        name="v3",
        # 偏 L3：explain 多出 exams
        layer_weights={"basic": 1.0, "advanced": 1.1, "exams": 1.5, "legacy": 0.6},
    ),
}


@dataclass
class ProbeMetrics:
    probe_id: str
    mode: str
    n_pool: int = 0
    n_pack: int = 0
    # 分指标（不混用）
    layer_recall_pool: float = 0.0  # want 层是否进候选池
    layer_recall_pack: float = 0.0  # want 层是否进最终 pack
    layer_precision_pack: float = 0.0  # pack 中 want 层占比
    pack_layers: list[str] = field(default_factory=list)
    ok_safety: bool = True


def _layer(meta: dict) -> str:
    return str(meta.get("kb_depth") or "legacy")


def apply_profile_weights(
    fused: FusedEvidence,
    policy,
    profile: LayerWeightProfile,
    *,
    keep: int = 8,
) -> FusedEvidence:
    """只按 profile.layer_weights 重排；不改安全裁剪。"""
    weights = profile.layer_weights
    preferred = set(policy.preferred_layers)

    def key(item):
        idx, ev = item
        layer = _layer(ev.metadata or {})
        score = float((ev.metadata or {}).get("score") or getattr(ev, "score", 0) or 0.0)
        w = float(weights.get(layer, 1.0))
        if layer in preferred:
            w *= 1.15  # 轻微任务偏好，实验里可用 profile 重写
        return (-score * w, idx)

    ranked = [ev for _, ev in sorted(enumerate(fused.text_evidences or []), key=key)]
    out = fused.model_copy(deep=True)
    out.text_evidences = ranked[:keep] if keep > 0 else ranked
    return out


async def run_probe(probe: dict, profile: LayerWeightProfile) -> ProbeMetrics:
    q = probe["q"]
    want = set(probe["want_layers"])
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
    pool_layers = [_layer(e.metadata or {}) for e in (raw.text_evidences or [])]
    packed = apply_profile_weights(raw, policy, profile, keep=8)
    out, _flags = apply_evidence_policy(packed, policy)
    pack_layers = [_layer(e.metadata or {}) for e in (out.text_evidences or [])]
    roles = {str((e.metadata or {}).get("doc_role") or "") for e in (out.text_evidences or [])}

    m = ProbeMetrics(probe_id=probe["id"], mode=probe["mode"])
    m.n_pool = len(pool_layers)
    m.n_pack = len(pack_layers)
    m.layer_recall_pool = 1.0 if want.intersection(pool_layers) else 0.0
    m.layer_recall_pack = 1.0 if want.intersection(pack_layers) else 0.0
    m.layer_precision_pack = sum(1 for x in pack_layers if x in want) / max(len(pack_layers), 1)
    m.pack_layers = pack_layers
    # 安全与权重实验隔离：禁入角色不得出现在 pack
    if policy.answer_policy == "hidden" and ("exam_answer" in roles):
        m.ok_safety = False
    if policy.task_mode in ("learn", "method", "practice") and (
        roles & {"exam_item", "exam_answer", "exam_paper"}
    ):
        m.ok_safety = False
    return m


async def run_profile(name: str, profile: LayerWeightProfile) -> dict:
    rows = [await run_probe(p, profile) for p in FIXED_PROBES]
    by_mode: dict[str, dict] = {}
    for r in rows:
        acc = by_mode.setdefault(
            r.mode,
            {"n": 0, "recall_pool": 0.0, "recall_pack": 0.0, "prec_pack": 0.0, "safety_fail": 0},
        )
        acc["n"] += 1
        acc["recall_pool"] += r.layer_recall_pool
        acc["recall_pack"] += r.layer_recall_pack
        acc["prec_pack"] += r.layer_precision_pack
        if not r.ok_safety:
            acc["safety_fail"] += 1
    summary = {
        mode: {
            "n": a["n"],
            "layer_recall@pool": round(a["recall_pool"] / a["n"], 3),
            "layer_recall@pack": round(a["recall_pack"] / a["n"], 3),
            "layer_precision@pack": round(a["prec_pack"] / a["n"], 3),
            "safety_fail": a["safety_fail"],
        }
        for mode, a in by_mode.items()
    }
    return {
        "profile": name,
        "layer_weights": profile.layer_weights,
        "probes": [
            {
                "id": r.probe_id,
                "mode": r.mode,
                "n_pool": r.n_pool,
                "n_pack": r.n_pack,
                "layer_recall_pool": r.layer_recall_pool,
                "layer_recall_pack": r.layer_recall_pack,
                "layer_precision_pack": round(r.layer_precision_pack, 3),
                "pack_layers": r.pack_layers,
                "ok_safety": r.ok_safety,
            }
            for r in rows
        ],
        "by_mode": summary,
    }


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", default="", help="只跑指定 profile（默认全跑 v0–v3）")
    ap.add_argument("--out", default=str(OUT_DIR))
    args = ap.parse_args()

    names = [args.profile] if args.profile else ["v0", "v1", "v2", "v3"]
    report = {
        "_meta": {
            "recorded_at": datetime.now(UTC).isoformat(),
            "fixed_probes": [p["id"] for p in FIXED_PROBES],
            "note": "只改 layer_weights；指标分列 recall@pool / recall@pack / precision@pack",
        },
        "profiles": [],
    }
    for name in names:
        if name not in PROFILES:
            print(f"unknown profile {name}")
            return 2
        print(f"==== profile {name} weights={PROFILES[name].layer_weights} ====")
        res = await run_profile(name, PROFILES[name])
        report["profiles"].append(res)
        for mode, s in res["by_mode"].items():
            print(
                f"  [{mode}] recall@pool={s['layer_recall@pool']} "
                f"recall@pack={s['layer_recall@pack']} prec@pack={s['layer_precision@pack']} "
                f"safety_fail={s['safety_fail']}"
            )

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"layer_policy_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
