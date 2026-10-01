"""最终数据审计：把归档 JSON 的原始数字全部导出，供与文档逐项核对。

只读，不改任何产物。

用法：
    uv run python scripts/data_audit.py
"""

from __future__ import annotations

import json
from pathlib import Path

R = Path("evals/results")
B = Path("evals/baselines")

METRICS = ("faithfulness", "context_precision", "context_recall", "answer_relevancy")


def load(p: Path):
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        return {"_parse_error": str(e)}


def head(title: str) -> None:
    print("\n" + "=" * 96)
    print(title)


def section_timestamps() -> None:
    head("0. 归档时间戳（判断是否全部来自 V-2026-10-02 一轮）")
    for p in sorted(R.rglob("*.json")):
        if "_backup" in str(p):
            continue
        d = load(p)
        ts = ""
        if isinstance(d, dict):
            ts = d.get("recorded_at") or (d.get("_meta") or {}).get("recorded_at") or ""
            if not ts and "summary" in d:
                ts = str((d["summary"] or {}).get("recorded_at") or "")
        print(f"  {p.relative_to(R)!s:<66} ts={ts}")


def section_component() -> None:
    head("1. 组件消融 component_ablation.json")
    d = load(R / "retrieval/ablation/component_ablation.json")
    for r in (d or {}).get("rows", []):
        print(
            f"  {r['config']:<14} kp_hit={r['kp_hit_at_k']:<7} kp_mrr={r['kp_mrr']:<8} "
            f"cat@1={r['category_hit_at_1']:<7} n_ev={r['mean_evidence_count']}"
        )


def section_rerank() -> None:
    head("2. rerank_compare.json")
    d = load(R / "retrieval/ablation/rerank_compare.json")
    for r in (d or {}).get("rows", []):
        print(
            f"  {r['config']:<12} kp_hit={r['kp_hit_at_k']:<7} "
            f"kp_mrr={r['kp_mrr']:<8} n_ev={r['mean_evidence_count']}"
        )


def section_layers() -> None:
    head("3. 分层消融 layer_ablation.json")
    d = load(R / "retrieval/layer_policy/layer_ablation.json")
    for r in (d or {}).get("rows", []):
        print(
            f"  {r['config']:<14} kp_hit={r['kp_hit_at_k']:<7} "
            f"kp_mrr={r['kp_mrr']:<8} empty={r['empty_result_rate']}"
        )


def section_task_aware() -> None:
    head("4. Task-aware task_layer_ablation.json")
    d = load(R / "retrieval/ablation/task_layer_ablation.json")
    for arm in ("baseline", "ours"):
        blk = (d or {}).get(arm) or {}
        print(f"  [{arm}] MACRO={blk.get('macro_layer_hit')}")
        for m, v in (blk.get("by_mode") or {}).items():
            print(f"     {m:<10} hit={v.get('layer_hit_rate')} leak={v.get('leakage_rate')}")


def section_basic_rag() -> None:
    head("5. 基础 RAG basic_rag_compare.json")
    d = load(R / "retrieval/ablation/basic_rag_compare.json")
    for arm in ("basic_rag", "ours"):
        m = ((d or {}).get("retrieval") or {}).get(arm) or {}
        print(
            f"  {arm:<10} kp_hit={m.get('kp_hit_at_k')} kp_mrr={m.get('kp_mrr')} "
            f"cat@1={m.get('category_hit_at_1')} n_ev={m.get('mean_evidence_count')}"
        )


def section_tmlp() -> None:
    head("6. TMLP task_mode_x_layer_policy.json")
    d = load(R / "retrieval/layer_policy/task_mode_x_layer_policy.json")
    res = (d or {}).get("results") or {}
    pols = list(res)
    for key in ("layer_hit_rate", "layer_precision_pack", "pack_nonempty_rate"):
        print(f"  [{key}] cols={pols}")
        for m in ("learn", "method", "practice", "grade", "explain", "verify"):
            cells = [(res[p]["by_mode"].get(m) or {}).get(key) for p in pols]
            print(f"     {m:<9} {cells}")


def section_legacy_and_variance() -> None:
    head("7. legacy_runtime.json")
    d = load(R / "retrieval/legacy_runtime/legacy_runtime.json")
    for s in (d or {}).get("strategies", []):
        print(f"  {s['strategy']:<10} prec_pack={s['aggregate']['layer_precision_pack']}")

    head("8. 方差 component_variance/summary.json")
    s = (load(R / "retrieval/ablation/component_variance/summary.json") or {}).get("summary") or {}
    for cfg, blk in (s.get("per_config") or {}).items():
        row = " ".join(
            f"{k[:8]}={blk[k]['mean']}±{blk[k]['std']}"
            for k in ("kp_hit_at_k", "kp_mrr", "category_hit_at_1")
        )
        print(f"  {cfg:<12} {row}")


def section_threshold_and_ragas() -> None:
    head("9. 阈值敏感度 threshold_sensitivity.json")
    d = load(R / "retrieval/ablation/threshold_sensitivity/threshold_sensitivity.json")
    for r in (d or {}).get("results", []):
        m = r["metrics"]
        print(
            f"  arm={r['arm']:<12} scale={r['scale']:<5} kp_hit={m['kp_hit_at_k']:<7} "
            f"kp_mrr={m['kp_mrr']:<8} fallback={r['fallback_rate']} q052={r['q052']['kp_hit']}"
        )

    head("10. RAGAS metrics.json")
    d = load(R / "generation/ragas/metrics.json")
    if d:
        for k in METRICS:
            print(f"  {k:<20} {d.get(k)}")
        print(
            f"  judge={d.get('judge_model')} gen={d.get('generation_model')} "
            f"n={d.get('n_filled')} rerank={d.get('effective_rerank_enabled')}"
        )


def section_golden() -> None:
    head("12. 黄金集完整性")
    rows = []
    gp = Path("evals/datasets/golden/sample_408.jsonl")
    for line in gp.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        rows.append(json.loads(line))
    multi = [r for r in rows if len(r["metadata"].get("knowledge_points") or []) > 1]
    print(f"  条数={len(rows)}  多标签条数={len(multi)}")
    for r in multi:
        print(f"    {r['query'][:40]:<42} {r['metadata']['knowledge_points']}")


def main() -> None:
    section_timestamps()
    section_component()
    section_rerank()
    section_layers()
    section_task_aware()
    section_basic_rag()
    section_tmlp()
    section_legacy_and_variance()
    section_threshold_and_ragas()
    section_golden()


if __name__ == "__main__":
    main()
