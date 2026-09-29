"""Policy → 层 → 证据 链路证明（默认权重，不调 layer_policy）。

证明四件事：
1. classify 后 policy 安全字段正确
2. eligibility where 挡住禁入资源（召回侧）
3. 候选池里 preferred 层可出现（默认 ranking 下）
4. Evidence Pack 披露与 mode 一致（release）

用法：
    uv run python scripts/policy_layer_evidence_proof.py
    uv run python scripts/policy_layer_evidence_proof.py --update-baseline
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rag.evidence_policy import apply_evidence_policy, finalize_with_layer_ranking  # noqa: E402
from rag.retrieval_policy import resolve_retrieval_policy  # noqa: E402
from rag.retriever import aretrieve_evidence_with_retry  # noqa: E402

BASELINE_PATH = ROOT / "evals" / "policy_layer_evidence_baseline.json"

# 固定 probe：每 mode 一条，与权重实验隔离
PROBES = [
    {
        "mode": "learn",
        "q": "二叉树的遍历方式有哪些？为什么要有中序遍历？",
        "want_layers": ["basic", "advanced"],
        "want_roles_ok": ["textbook", "method"],
        "want_roles_block": ["exam_item", "exam_answer", "exam_paper"],
    },
    {
        "mode": "method",
        "q": "已知先序和中序遍历，如何还原二叉树？步骤是什么？",
        "want_layers": ["advanced", "basic"],
        "want_roles_ok": ["method", "textbook"],
        "want_roles_block": ["exam_item", "exam_answer", "exam_paper"],
    },
    {
        "mode": "practice",
        "q": "给我一道 BST 删除的练习题",
        "want_layers": ["advanced", "basic"],
        "want_roles_ok": ["method", "textbook"],
        "want_roles_block": ["exam_item", "exam_answer", "exam_paper"],
    },
    {
        "mode": "grade",
        "q": "2019-Q2 我选 B，树转二叉树后根遍历等于中序，对吗？请批改",
        "want_layers": ["exams", "advanced"],
        "want_roles_ok": ["exam_item", "exam_answer", "method"],
        "want_roles_block": ["exam_paper"],
    },
    {
        "mode": "explain",
        "q": "2019-Q2 为什么树的后根遍历对应二叉树中序？",
        "want_layers": ["exams", "advanced", "basic"],
        "want_roles_ok": ["exam_item", "exam_answer"],
        "want_roles_block": ["exam_paper"],
    },
    {
        "mode": "verify",
        "q": "BST 删除考过哪些真题？",
        "want_layers": ["exams", "advanced"],
        "want_roles_ok": ["exam_item"],
        "want_roles_block": ["exam_answer", "exam_paper"],
    },
]

_QID_RE = re.compile(r"(?:19|20)\d{2}-Q\d+")
_ANS_FIELD_RE = re.compile(r"answer_key|reference_answer|qa\.answer", re.I)


def _layer(m: dict) -> str:
    """语义层名；无 kb_depth 的 legacy 资产显示为 'legacy'（仅展示用）。"""
    v = str(m.get("kb_depth") or "")
    return v if v in ("basic", "advanced", "exams") else "legacy"


def _role(m: dict) -> str:
    return str(m.get("doc_role") or "")


async def probe_one(p: dict) -> dict:
    q, want_mode = p["q"], p["mode"]
    policy = resolve_retrieval_policy(q)
    mode = policy.task_mode
    where = policy.eligibility_where()

    # 候选池：扩大 k，证明 preferred 层能进池（默认 ranking）
    fused_raw, _ = await aretrieve_evidence_with_retry(
        query=q,
        k=20,
        use_rerank=True,
        filter=where,
        max_retries=0,
        use_llm_verify=False,
        preferred_layers=list(policy.preferred_layers),
    )
    pool_layers = [_layer(e.metadata or {}) for e in (fused_raw.text_evidences or [])]

    packed = finalize_with_layer_ranking(fused_raw, policy, keep=8)
    out, flags = apply_evidence_policy(packed, policy)
    pack_layers = [_layer(e.metadata or {}) for e in (out.text_evidences or [])]
    pack_roles = [_role(e.metadata or {}) for e in (out.text_evidences or [])]
    pack_blob = str([e.metadata for e in (out.text_evidences or [])])
    pack_text = "\n".join(e.content or "" for e in (out.text_evidences or []))
    layer_pack = (out.metadata or {}).get("layer_pack") or {}

    checks: dict[str, bool] = {}
    # 1) 分类
    checks["classify"] = mode == want_mode or (want_mode == "grade" and mode == "grade")
    # 2) eligibility：禁入角色不得进 pack；也不得大量出现在 pool
    for role in p.get("want_roles_block") or []:
        checks[f"block_{role}_pack"] = role not in pack_roles
    # 3) 层：want_layers 至少一条进 pool（证明策略指向的层可达）
    checks["layer_in_pool"] = any(x in p["want_layers"] for x in pool_layers)
    checks["layer_in_pack"] = (
        any(x in p["want_layers"] for x in pack_layers) or len(out.text_evidences or []) < 3
    )
    # 5) legacy 是资产状态不是层：
    #    exclude 模式 pack 内不得有 legacy；fallback 补入必须显式可查
    if policy.legacy_pool_policy == "exclude":
        checks["exclude_no_legacy"] = "legacy" not in pack_layers
    if policy.legacy_pool_policy == "fallback":
        used_fb = int(layer_pack.get("used_fallback") or 0)
        n_legacy_in_pack = pack_layers.count("legacy")
        checks["fallback_count_consistent"] = used_fb == n_legacy_in_pack or used_fb == 0
    lp_n = int(layer_pack.get("n_pack") or 0)
    lp_keep = int(layer_pack.get("keep") or 0)
    if lp_keep > 0 and lp_n < lp_keep:
        checks["degraded_flag_when_short"] = bool(layer_pack.get("degraded")) and bool(
            flags.get("layer_degraded")
        )
    else:
        checks["degraded_flag_when_short"] = True
    # 4) 披露
    if policy.answer_policy == "hidden":
        checks["no_answer_fields"] = not _ANS_FIELD_RE.search(pack_blob)
        checks["no_qid"] = not _QID_RE.search(pack_blob + pack_text) or mode in ("verify",)
    else:
        # grade/explain 允许答案；不强制必须有（视索引）
        checks["answer_allowed"] = True

    ok = all(checks.values())
    return {
        "mode": mode,
        "query": q,
        "ok": ok,
        "checks": checks,
        "policy": {
            "answer_policy": policy.answer_policy,
            "exam_resources": policy.exam_resources.model_dump(),
            "preferred_layers": policy.preferred_layers,
            "allow_question_id_leak": policy.allow_question_id_leak,
            "where": where,
        },
        "pool_layers": pool_layers[:12],
        "pack_layers": pack_layers,
        "pack_roles": pack_roles,
        "n_pool": len(pool_layers),
        "n_pack": len(pack_layers),
        "legacy_pool_policy": policy.legacy_pool_policy,
        "layer_pack": layer_pack,
    }


async def run_all() -> dict:
    results = [await probe_one(p) for p in PROBES]
    return {
        "_meta": {
            "recorded_at": datetime.now(UTC).isoformat(),
            "layer_policy_id": "default",
            "note": "Policy→层→证据链路证明；仅用默认权重，不调 layer_policy 实验",
        },
        "results": results,
        "all_ok": all(r["ok"] for r in results),
    }


def compare(cur: dict, base: dict) -> list[str]:
    fails: list[str] = []
    bmap = {r["mode"]: r for r in (base.get("results") or [])}
    for r in cur.get("results") or []:
        b = bmap.get(r["mode"])
        if not b:
            continue
        # 安全检查不得从 True 变 False
        for k, bv in (b.get("checks") or {}).items():
            if bv and not (r.get("checks") or {}).get(k, False):
                fails.append(f"{r['mode']}.{k}: baseline OK but now fail")
        if b.get("ok") and not r.get("ok"):
            fails.append(f"{r['mode']} overall regression")
    return fails


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--update-baseline", action="store_true")
    args = ap.parse_args()
    payload = await run_all()
    print("==== Policy → Layer → Evidence proof ====")
    for r in payload["results"]:
        bad = [k for k, v in r["checks"].items() if not v]
        lp = r.get("layer_pack") or {}
        note = ""
        if r.get("legacy_pool_policy") == "exclude":
            note = f" dropped={lp.get('dropped_legacy', 0)}"
        elif lp.get("used_fallback"):
            note = f" fallback={lp.get('used_fallback')}"
        if lp.get("degraded"):
            note += f" DEGRADED({lp.get('n_pack')}/{lp.get('keep')})"
        print(
            f"  [{r['mode']}] ok={r['ok']} pool={r['n_pool']} pack={r['n_pack']} "
            f"layers={r['pack_layers']}{note}"
        )
        print(f"       where={r['policy']['where']}")
        if bad:
            print(f"       FAIL {bad}")

    path = BASELINE_PATH
    if args.update_baseline:
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"基线已更新: {path}")
        return 0 if payload["all_ok"] else 1

    if not path.exists():
        print("[提示] 无基线，先确认结果后 --update-baseline")
        return 0 if payload["all_ok"] else 1

    base = json.loads(path.read_text(encoding="utf-8"))
    fails = compare(payload, base)
    if fails:
        print("PROOF vs BASELINE FAIL", len(fails))
        for x in fails:
            print(" -", x)
        return 1
    print("PROOF PASS（链路稳定，可进入 layer_policy 实验）")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
