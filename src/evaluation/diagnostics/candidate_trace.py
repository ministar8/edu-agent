"""候选追踪诊断工具（CLI + 报告）：定位正确 chunk 在哪一层消失。

引擎（快照抓取 + 归因）见 ``evaluation.probe_tracing``；本模块只做 CLI 与人类可读报告。

★ **测量纪律**：语义缓存会把「缓存命中」混进「检索质量」，
所以本工具**强制关闭语义缓存**（``SEMANTIC_CACHE_ENABLED=False``），并在报告里声明。

用法::

    uv run python -m evaluation.diagnostics.candidate_trace                    # 跑默认 probe 表
    uv run python -m evaluation.diagnostics.candidate_trace --probe evals/datasets/golden/retrieval_probes.jsonl
    uv run python -m evaluation.diagnostics.candidate_trace --json             # 机器可读
    uv run python -m evaluation.diagnostics.candidate_trace --limit 2          # 只跑前 N 条
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging

from evaluation.probe_tracing import (
    DEFAULT_PROBE_PATH,
    TraceResult,
    load_probes,
    trace_probe,
)

# ── 报告 ──────────────────────────────────────────────


def _format(result: TraceResult) -> str:
    lines = [f"=== #{result.probe.id}  {result.probe.query}"]
    lines.append(
        f"    目标：{result.probe.target}"
        + (f"    （{result.probe.note}）" if result.probe.note else "")
    )
    if result.plan:
        lines.append(
            f"    计划：k={result.plan.get('k')} coarse_k={result.plan.get('coarse_k')} "
            f"阈值={result.plan.get('effective_threshold')} "
            f"重排={result.plan.get('use_rerank')} 层={result.plan.get('retrieval_layer')}"
        )
    for snap in result.stages:
        mark = f"rank {snap.rank} ✓" if snap.rank is not None else "缺失 ✗"
        lines.append(f"    {snap.label:<18}{snap.count:>4} 条 | 目标 {mark}")
    lines.append(f"    ⇒ dropped_by = {result.dropped_by}")
    if result.rerank_note:
        lines.append(f"    ⚠ {result.rerank_note}")

    # 消失点的前 3 条：看是什么把它挤掉的
    for snap in result.stages:
        if snap.rank is None and snap.top:
            lines.append(f"    ★ 「{snap.label}」前 3 条：")
            for item in snap.top:
                lines.append(f"        {item}")
            break
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="候选追踪：定位正确 chunk 在哪一层消失")
    parser.add_argument("--probe", default=DEFAULT_PROBE_PATH, help="probe 表 jsonl 路径")
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--limit", type=int, default=None, help="只跑前 N 条")
    parser.add_argument(
        "--rerank",
        dest="rerank",
        action="store_true",
        default=True,
        help="强制开启重排（默认；诊断重排漏斗必须开，否则该层是空转）",
    )
    parser.add_argument("--no-rerank", dest="rerank", action="store_false", help="强制关闭重排")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )

    # ★ 测量纪律：语义缓存会把「缓存命中」混进「检索质量」，强制关闭。
    from core.settings import settings

    settings.SEMANTIC_CACHE_ENABLED = False
    settings.RERANK_ENABLED = args.rerank
    import rag.retrieval.semantic_cache as sc

    sc._semantic_cache = None

    probes = load_probes(args.probe, limit=args.limit)
    if not probes:
        print("[错误] probe 表为空", flush=True)
        return 2

    results = [asyncio.run(trace_probe(p, k=args.k, use_rerank=True)) for p in probes]

    if args.json:
        print(json.dumps([r.as_dict() for r in results], ensure_ascii=False, indent=2))
        return 0

    print("=" * 68)
    print(f"  候选追踪   语义缓存=off   重排={'on' if args.rerank else 'off'}")
    print("=" * 68)
    for result in results:
        print(_format(result))
        print()

    print("归因汇总：")
    for result in results:
        print(f"  #{result.probe.id:<3} {result.dropped_by}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
