"""Task-aware Layer Ablation：证明「三层服务不同任务」而非刷同一指标。

对照设计：

    baseline：所有任务 L1/L2/L3 平铺（preferred=全层，legacy_policy=include）
    ours    ：task_mode → preferred_layers → legacy_policy

任务专有指标（不是 kp_mrr）：

    learn    → L1 hit（basic 进证据包）
    method   → L2 hit（advanced 进包）
    practice → L2/L3 hit + 答案泄漏（pack 不得含答案）
    grade    → L3 hit（exams 进包）
    explain  → L3 hit
    verify   → L3 hit

用法：
    uv run python scripts/task_layer_ablation.py
    uv run python scripts/task_layer_ablation.py --limit-per-mode 4
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rag.evidence_policy import apply_evidence_policy, finalize_with_layer_ranking  # noqa: E402
from rag.retriever import aretrieve_evidence_with_retry  # noqa: E402
from rag.task_policy import policy_for_mode  # noqa: E402
from schema.task_policy import TaskPolicy  # noqa: E402

OUT_DIR = ROOT / "evals" / "results" / "retrieval" / "ablation"

# 任务标注的黄金 query（每模式多条，覆盖四科）
TASK_QUERIES: dict[str, list[str]] = {
    "learn": [
        "什么是二叉排序树？",
        "什么是死锁？",
        "进程和线程的区别是什么？",
        "Cache 的映射方式有哪些？",
        "TCP 三次握手的过程是什么？",
        "什么是虚拟存储器？",
    ],
    "method": [
        "BST 删除时双支结点怎么处理？",
        "如何用银行家算法避免死锁？",
        "页面置换算法 LRU 怎么实现？",
        "Dijkstra 算法的步骤是什么？",
        "如何判断一个二叉树是平衡二叉树？",
        "TCP 拥塞控制怎么实现？",
    ],
    "practice": [
        "给我一道死锁练习题",
        "来一道 BST 删除的练习题",
        "出一道进程同步的题目",
        "给一道 Cache 映射的练习",
    ],
    "grade": [
        "请批改我对「进程死锁四个必要条件」的回答：互斥、占有并等待、不可剥夺、循环等待",
        "批改我的答案：TCP 三次握手是 SYN、SYN+ACK、ACK",
        "我对「页面置换 OPT 是最优算法」的理解是：它永不缺页。请批改",
    ],
    "explain": [
        "2019-Q2 为什么树的后根遍历对应二叉树的中序？",
        "2019-Q11 为什么选 B？请详细解析",
        "2020-Q2 这道题的解题思路是什么？",
    ],
    "verify": [
        "BST 删除考过哪些真题？",
        "死锁在历年真题中出现过吗？",
        "Cache 映射方式考过几次？",
    ],
}

# 任务专有指标：期望命中的语义层
TASK_TARGET_LAYER: dict[str, tuple[str, ...]] = {
    "learn": ("basic",),
    "method": ("advanced",),
    "practice": ("advanced", "exams"),
    "grade": ("exams",),
    "explain": ("exams",),
    "verify": ("exams",),
}

_ANS_FIELD_RE = re.compile(r"answer_key|reference_answer|correct_answer", re.I)
_ANS_BODY_RE = re.compile(r"答案[:：]|【答案】|正确答案|标准答案")


def _pack_layers(fused) -> list[str]:
    out = []
    for ev in fused.text_evidences or []:
        v = str((ev.metadata or {}).get("kb_depth") or "")
        out.append(v if v in ("basic", "advanced", "exams") else "legacy")
    return out


def _pack_blob(fused) -> str:
    parts = []
    for ev in fused.text_evidences or []:
        parts.append(ev.content or "")
        parts.append(str(ev.metadata or ""))
    return "\n".join(parts)


def _ours_policy(mode: str) -> TaskPolicy:
    return policy_for_mode(mode)  # type: ignore[arg-type]


def _baseline_policy(mode: str) -> TaskPolicy:
    """baseline：所有任务平铺 L1/L2/L3，legacy 等同主池。"""
    p = policy_for_mode(mode)  # type: ignore[arg-type]
    # 用 model_copy 覆盖层偏好与 legacy 策略（安全字段不动）
    return p.model_copy(
        update={
            "preferred_layers": ["basic", "advanced", "exams"],
            "legacy_policy": "include",
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
    fused, flags = apply_evidence_policy(fused, policy)

    layers = _pack_layers(fused)
    targets = TASK_TARGET_LAYER.get(mode, ())
    layer_hit = any(t in layers for t in targets)
    blob = _pack_blob(fused)
    # 泄漏只在「答案隐藏」的模式上有意义（learn/method/practice/verify）
    # grade/explain 的 answer_policy=released，含答案是预期
    answer_hidden = mode in ("learn", "method", "practice", "verify")
    leakage = bool(answer_hidden and (_ANS_FIELD_RE.search(blob) or _ANS_BODY_RE.search(blob)))
    return {
        "query": query,
        "mode": mode,
        "layers": layers,
        "layer_hit": layer_hit,
        "leakage": leakage,
        "answer_hidden_mode": answer_hidden,
        "n_pack": len(layers),
        "legacy_policy": policy.legacy_policy,
    }


async def run_arm(arm: str, queries: dict[str, list[str]]) -> dict[str, Any]:
    """跑一臂（baseline / ours），按任务模式聚合。"""
    by_mode: dict[str, dict[str, Any]] = {}
    all_rows: list[dict[str, Any]] = []
    for mode, qs in queries.items():
        hits = 0
        leaks = 0
        n = 0
        n_hidden = 0
        for q in qs:
            policy = _baseline_policy(mode) if arm == "baseline" else _ours_policy(mode)
            row = await run_one(q, mode, policy)
            all_rows.append(row)
            n += 1
            hits += int(row["layer_hit"])
            if row.get("answer_hidden_mode"):
                n_hidden += 1
                leaks += int(row["leakage"])
        by_mode[mode] = {
            "n": n,
            "layer_hit_rate": round(hits / n, 4) if n else 0.0,
            "leakage_rate": round(leaks / n_hidden, 4) if n_hidden else None,
            "target_layers": list(TASK_TARGET_LAYER.get(mode, ())),
        }
    # 总宏平均（仅 layer_hit）
    rates = [v["layer_hit_rate"] for v in by_mode.values()]
    return {
        "arm": arm,
        "by_mode": by_mode,
        "macro_layer_hit": round(sum(rates) / len(rates), 4) if rates else 0.0,
        "rows": all_rows,
    }


def print_table(baseline: dict[str, Any], ours: dict[str, Any]) -> None:
    print("\n==== Task-aware Layer Ablation ====")
    print(
        f"{'task_mode':<10} {'target':<16} {'baseline':>10} {'ours':>10} {'Δ hit':>8} {'leak b/o':>10}"
    )
    print("-" * 72)
    for mode in TASK_QUERIES:
        b = baseline["by_mode"].get(mode, {})
        o = ours["by_mode"].get(mode, {})
        targets = ",".join(TASK_TARGET_LAYER.get(mode, ()))
        bh, oh = b.get("layer_hit_rate", 0), o.get("layer_hit_rate", 0)
        bl, ol = b.get("leakage_rate"), o.get("leakage_rate")
        leak_s = f"{bl:.2f}/{ol:.2f}" if bl is not None and ol is not None else "n/a"
        print(f"{mode:<10} {targets:<16} {bh:>10.3f} {oh:>10.3f} {oh - bh:>+8.3f} {leak_s:>10}")
    print("-" * 72)
    print(
        f"{'MACRO':<10} {'':<16} {baseline['macro_layer_hit']:>10.3f} "
        f"{ours['macro_layer_hit']:>10.3f} "
        f"{ours['macro_layer_hit'] - baseline['macro_layer_hit']:>+8.3f}"
    )
    print("\n（layer_hit = 证据包命中任务目标层；leakage 仅统计 answer-hidden 模式）")
    print("（grade/explain 的 answer_policy=released，含答案是预期，不计泄漏）")


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit-per-mode", type=int, default=6)
    args = ap.parse_args()

    queries = {m: qs[: args.limit_per_mode] for m, qs in TASK_QUERIES.items()}
    print(f"queries/mode: {{{', '.join(f'{m}:{len(q)}' for m, q in queries.items())}}}")
    print("arm=baseline（L1/L2/L3 平铺 + legacy include）")

    t0 = time.perf_counter()
    baseline = await run_arm("baseline", queries)
    print("arm=ours（task_mode → preferred_layers → legacy_policy）", flush=True)
    ours = await run_arm("ours", queries)

    print_table(baseline, ours)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    path = OUT_DIR / f"task_layer_{ts}.json"
    path.write_text(
        json.dumps(
            {
                "recorded_at": ts,
                "queries": queries,
                # 当次配置快照（实验可追溯）
                "config_snapshot": {
                    "baseline": "preferred=[basic,advanced,exams] legacy=include",
                    "ours": "task_mode → preferred_layers → legacy_policy",
                    "task_target_layer": TASK_TARGET_LAYER,
                },
                "baseline": {k: v for k, v in baseline.items() if k != "rows"},
                "ours": {k: v for k, v in ours.items() if k != "rows"},
                "baseline_rows": baseline["rows"],
                "ours_rows": ours["rows"],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\narchive → {path}")
    print(f"elapsed={time.perf_counter() - t0:.0f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
