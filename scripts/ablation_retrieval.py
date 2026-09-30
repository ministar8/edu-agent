"""P0 消融实验：逐组件开/关，同一黄金集对比检索指标。

论文用法：每行一个消融配置，列是 `retrieval_gate` 的核心指标（kp_* 比学科级更敏感）。

    python scripts/ablation_retrieval.py
    python scripts/ablation_retrieval.py --limit 40      # 快速预览
    python scripts/ablation_retrieval.py --configs full,no_rerank

输出：
    控制台对比表
    evals/results/retrieval/ablation/<timestamp>.json   运行归档

组件开关（只动检索链，不动安全字段）：
    no_bm25 / no_metadata / no_decompose / no_rerank / no_hyde / vector_only / +topup
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from evaluation.retrieval_gate import (  # noqa: E402
    DEFAULT_GOLDEN_PATH,
    GATE_K,
    QueryOutcome,
    compute_metrics,
    load_golden_queries,
)
from rag.query_classifier import QueryCategory  # noqa: E402

OUT_DIR = ROOT / "evals" / "results" / "retrieval"

_LAYER_CFGS = {
    "no_l1",
    "no_l2",
    "no_l3",
    "l1_only",
    "l2_only",
    "l3_only",
    "no_legacy",
    "legacy_only",
}


def _out_dir_for(names: list) -> Path:
    """按配置名分流：分层消融进 layer_policy，其余进 ablation。"""
    folder = "layer_policy" if any(n in _LAYER_CFGS for n in names) else "ablation"
    return OUT_DIR / folder


# 配置名 → 开关说明
CONFIGS: dict[str, dict[str, Any]] = {
    "full": {"note": "完整系统（当前默认）"},
    "no_bm25": {"skip_bm25": True, "note": "去掉 BM25 路由"},
    "no_metadata": {"skip_metadata_routes": True, "note": "去掉元数据路由"},
    "no_decompose": {"skip_decompose": True, "note": "去掉查询分解"},
    "no_rerank": {"rerank": False, "note": "去掉重排"},
    "no_hyde": {"hyde": False, "note": "去掉 HyDE"},
    "vector_only": {
        "skip_bm25": True,
        "skip_metadata_routes": True,
        "note": "仅语义向量（去 BM25+元数据）",
    },
    "plus_topup": {"topup": True, "note": "加 preferred 层 top-up"},
    # ── 第二轮：定位问题组件 ──
    "no_dead_routes": {
        "skip_route_names": ["code_meta", "comparison_meta", "formula_meta"],
        "note": "去掉低贡献元数据路由（code/comparison/formula）",
    },
    "no_window": {"no_window": True, "note": "去掉句子窗口展开"},
    "no_decomp_hyde": {
        "skip_decompose": True,
        "hyde": False,
        "note": "同时去 decompose+HyDE（消融已证无增益）",
    },
    "k3": {"k": 3, "note": "k=3（更窄预算）"},
    "k8": {"k": 8, "note": "k=8（更宽预算）"},
    "rerank_loose": {
        "rerank_min_score": 0.1,
        "note": "重排阈值放宽 0.1（默认 0.3，试救回被误杀的候选）",
    },
    # ── L1/L2/L3 分层消融（本系统独有卖点）──
    "no_l1": {
        "layer_filter": {"kb_depth": {"$ne": "basic"}},
        "note": "去掉 L1 基础层",
    },
    "no_l2": {
        "layer_filter": {"kb_depth": {"$ne": "advanced"}},
        "note": "去掉 L2 进阶层",
    },
    "no_l3": {
        "layer_filter": {"kb_depth": {"$ne": "exams"}},
        "note": "去掉 L3 真题层",
    },
    "l1_only": {"layer_filter": {"kb_depth": "basic"}, "note": "仅 L1 基础"},
    "l2_only": {"layer_filter": {"kb_depth": "advanced"}, "note": "仅 L2 进阶"},
    "l3_only": {"layer_filter": {"kb_depth": "exams"}, "note": "仅 L3 真题"},
    "no_legacy": {
        "layer_filter": {"kb_depth": {"$in": ["basic", "advanced", "exams"]}},
        "note": "去 legacy（仅 L1/L2/L3，对照 full 看旧资产贡献）",
    },
    "legacy_only": {
        "layer_filter": {"kb_depth": {"$nin": ["basic", "advanced", "exams"]}},
        "note": "仅 legacy（旧资产单独看）",
    },
}

# 汇报的核心列（学科级已饱和，kp_* 更敏感）
REPORT_COLS = (
    "kp_hit_at_k",
    "kp_mrr",
    "category_hit_at_1",
    "category_mrr",
    "empty_result_rate",
    "mean_evidence_count",
)


@contextmanager
def apply_config(flags: dict[str, Any]):
    """按配置临时开关组件；退出时恢复。"""
    import rag.pipeline as pipeline
    import rag.routes as routes
    from core import settings

    saved: list[tuple[Any, str, Any]] = []

    def _patch(obj: Any, name: str, value: Any) -> None:
        saved.append((obj, name, getattr(obj, name)))
        setattr(obj, name, value)

    try:
        if (
            flags.get("skip_bm25")
            or flags.get("skip_metadata_routes")
            or flags.get("skip_route_names")
        ):
            skip_bm25 = bool(flags.get("skip_bm25"))
            skip_meta = bool(flags.get("skip_metadata_routes"))
            skip_names = set(flags.get("skip_route_names") or [])
            orig_rq = routes.build_recall_queries
            orig_mr = routes.build_metadata_routes

            def rq_wrap(query, cat=None):
                pairs = orig_rq(query, cat=cat)
                if skip_bm25:
                    pairs = [(n, q) for n, q in pairs if n != "keyword_bm25"]
                if skip_names:
                    pairs = [(n, q) for n, q in pairs if n not in skip_names]
                return pairs

            def mr_wrap(query, base_filter=None, cat=None, terms=None):
                if skip_meta:
                    return []
                metas = orig_mr(query, base_filter=base_filter, cat=cat, terms=terms)
                if skip_names:
                    metas = [m for m in metas if m[0] not in skip_names]
                return metas

            _patch(routes, "build_recall_queries", rq_wrap)
            _patch(routes, "build_metadata_routes", mr_wrap)

        if flags.get("rerank") is False:
            _patch(settings, "RERANK_ENABLED", False)
        if flags.get("rerank_min_score") is not None:
            _patch(settings, "RERANK_MIN_SCORE", float(flags["rerank_min_score"]))
            _patch(settings, "RERANK_ENABLED", True)
        if flags.get("hyde") is False:
            _patch(settings, "HYDE_ENABLED", False)
        if flags.get("no_window"):
            # 短路窗口阶段：原样返回
            from rag.pipeline import _WindowOutcome

            async def expand_off(filtered, **kw: Any):
                return _WindowOutcome(filtered, 0.0)

            _patch(pipeline, "_stage_expand_windows", expand_off)

        if flags.get("skip_decompose"):

            async def decomp_off(query: str, cat: QueryCategory | None = None, **kw: Any):
                return [query]

            _patch(pipeline, "decompose", decomp_off)

        yield
    finally:
        for obj, name, value in reversed(saved):
            setattr(obj, name, value)


async def run_one_config(
    name: str,
    flags: dict[str, Any],
    queries: list[tuple[str, tuple[str, ...], tuple[str, ...]]],
) -> dict[str, Any]:
    from rag.retriever import aretrieve_evidence_with_retry

    use_topup = bool(flags.get("topup"))
    preferred = ["basic", "advanced", "exams"] if use_topup else None
    k = int(flags.get("k") or GATE_K)
    layer_filter = flags.get("layer_filter")  # Chroma where：按 kb_depth 过滤
    outcomes: list[QueryOutcome] = []
    errors: list[str] = []
    t0 = time.perf_counter()

    with apply_config(flags):
        for query, expected, expected_kps in queries:
            try:
                fused, _ = await aretrieve_evidence_with_retry(
                    query=query,
                    k=k,
                    use_rerank=True,
                    max_retries=0,
                    use_llm_verify=False,
                    preferred_layers=preferred,
                    filter=layer_filter,
                )
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{query[:30]}: {type(exc).__name__}")
                outcomes.append(
                    QueryOutcome(
                        query=query,
                        expected_categories=expected,
                        expected_knowledge_points=expected_kps,
                    )
                )
                continue

            docs = fused.text_evidences or []
            hit_cats: list[str] = []
            hit_kps: list[str] = []
            for ev in docs:
                meta = ev.metadata or {}
                coll = str(meta.get("_collection") or ev.collection or "")
                hit_cats.append(coll)
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

    metrics = compute_metrics(outcomes)
    return {
        "config": name,
        "note": str(flags.get("note") or ""),
        "n_queries": len(queries),
        "n_errors": len(errors),
        "errors": errors[:5],
        "elapsed_s": round(time.perf_counter() - t0, 1),
        **metrics.as_dict(),
    }


def print_table(rows: list[dict[str, Any]]) -> None:
    cols = ("config", *REPORT_COLS, "n_errors", "elapsed_s")
    widths = {"config": 14}
    for c in cols[1:]:
        widths[c] = 18 if c in REPORT_COLS else 12
    header = "".join(f"{c:<{widths[c]}}" for c in cols)
    print("\n==== 消融对比（越高越好，empty_result_rate 越低越好）====")
    print(header)
    print("-" * len(header))
    base = next((r for r in rows if r["config"] == "full"), None)
    for r in rows:
        line = f"{r['config']:<14}"
        for c in cols[1:]:
            w = widths[c]
            val = r.get(c)
            if val is None:
                line += f"{'—':<{w}}"
                continue
            if c in REPORT_COLS and base and r["config"] != "full":
                delta = float(val) - float(base.get(c, 0))
                cell = f"{float(val):.4f} ({delta:+.3f})"
            else:
                cell = str(val)
            line += f"{cell:<{w}}"
        print(line.rstrip())
        if r.get("note"):
            print(f"{'':<14}  # {r['note']}")


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--golden", default=DEFAULT_GOLDEN_PATH)
    ap.add_argument("--limit", type=int, default=None, help="只跑前 N 条（预览）")
    ap.add_argument(
        "--configs",
        default=None,
        help=f"逗号分隔配置名；默认全部。可选：{','.join(CONFIGS)}",
    )
    args = ap.parse_args()

    names = list(CONFIGS) if not args.configs else [c.strip() for c in args.configs.split(",")]
    for n in names:
        if n not in CONFIGS:
            print(f"未知配置: {n}；可选 {list(CONFIGS)}")
            return 2

    queries = load_golden_queries(args.golden, limit=args.limit)
    from core import settings

    print(f"golden={args.golden} n={len(queries)} configs={names}")
    print(
        f"运行开关: RERANK_ENABLED={settings.RERANK_ENABLED} "
        f"HYDE_ENABLED={settings.HYDE_ENABLED} "
        f"SEMANTIC_CACHE={settings.SEMANTIC_CACHE_ENABLED}"
    )

    rows: list[dict[str, Any]] = []
    for name in names:
        print(f"[run] {name} ...", flush=True)
        rows.append(await run_one_config(name, CONFIGS[name], queries))

    print_table(rows)

    out_dir = _out_dir_for(names)
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    path = out_dir / f"{ts}.json"
    path.write_text(
        json.dumps(
            {
                "recorded_at": ts,
                "golden": str(args.golden),
                "limit": args.limit,
                # 当次配置快照：实验可追溯（YAML 是文档，这里才是实际执行口径）
                "config_snapshot": {n: CONFIGS[n] for n in names},
                "rows": rows,
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
