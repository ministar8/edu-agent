"""Layer 2: 系统专用诊断指标

含 6 项诊断：路由消融、Sentence Window 效果、Reranker 影响、
查询分解、Pipeline 耗时、守卫治理统计。

所有 RAG 依赖通过 adapters.py 接口注入，与具体实现解耦。
"""

from __future__ import annotations

import logging
from typing import Any

from app.evaluation.config import EvaluationConfig
from app.evaluation.dataset import EvalSample
from app.evaluation.adapters import (
    META_ROUTE_NAMES,
    get_diagnostic_retriever,
    get_decomposer,
)

logger = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════
# 1. 路由消融
# ════════════════════════════════════════════════════════

def diagnose_route_ablation(
    samples: list[EvalSample],
    collection_name: str,
    cfg: EvaluationConfig,
) -> dict[str, Any]:
    """对每条查询依次关闭每条路由，对比召回变化（延迟 + 质量）"""
    diag = get_diagnostic_retriever()
    routes = list(diag.route_names)
    use_rerank = cfg.use_rerank
    logger.info("Diagnosis: Route Ablation (%d samples, %d routes, rerank=%s)",
                len(samples), len(routes), use_rerank)

    result: dict[str, Any] = {
        "routes_tested": routes,
        "sample_count": len(samples),
        "by_route": {},
    }

    # 先跑全量基线
    baseline_counts: list[int] = []
    baseline_rrf_scores: list[float] = []   # recall_score (RRF, 始终存在, 0~0.5)
    baseline_rerank_scores: list[float] = []  # rerank_score (qwen3-rerank, 仅 rerank 时存在, 0~1)
    baseline_latencies: list[float] = []
    for sample in samples:
        docs, timing = diag.retrieve_diagnostic(
            sample.query, collection_name, cfg.retrieval_k,
            use_rerank=use_rerank,
        )
        baseline_counts.append(len(docs))
        # 统一用 recall_score（RRF 分数，始终存在，同一尺度）
        rrf_scores = [d.get("metadata", {}).get("recall_score") or 0 for d in docs]
        baseline_rrf_scores.append(sum(rrf_scores) / max(len(rrf_scores), 1) if rrf_scores else 0)
        rerank_scores = [d.get("metadata", {}).get("rerank_score") or 0 for d in docs]
        baseline_rerank_scores.append(sum(rerank_scores) / max(len(rerank_scores), 1) if rerank_scores else 0)
        baseline_latencies.append(timing.get("total_ms", 0))

    result["baseline"] = {
        "avg_chunks": round(sum(baseline_counts) / len(baseline_counts), 2) if baseline_counts else 0,
        "avg_rrf_score": round(sum(baseline_rrf_scores) / len(baseline_rrf_scores), 6) if baseline_rrf_scores else 0,
        "avg_rerank_score": round(sum(baseline_rerank_scores) / len(baseline_rerank_scores), 4) if baseline_rerank_scores else 0,
        "avg_latency_ms": round(sum(baseline_latencies) / len(baseline_latencies), 2) if baseline_latencies else 0,
        "rerank_enabled": use_rerank,
        "score_method": "recall_score (RRF)",
    }

    # ── metadata 路由集合（用于分组合并）──
    _meta_routes = META_ROUTE_NAMES

    for disabled_route in routes:
        route_log: dict[str, list[float | int]] = {"latency": [], "chunk_count": [], "avg_rrf_score": []}

        for sample in samples:
            docs, timing = diag.retrieve_diagnostic(
                sample.query,
                collection_name,
                cfg.retrieval_k,
                disable_routes=[disabled_route],
                use_rerank=use_rerank,
            )
            route_log["latency"].append(timing.get("total_ms", 0))
            route_log["chunk_count"].append(len(docs))
            # 统一用 recall_score（RRF 分数，始终存在，同一尺度）
            rrf_scores = [d.get("metadata", {}).get("recall_score") or 0 for d in docs]
            route_log["avg_rrf_score"].append(sum(rrf_scores) / max(len(rrf_scores), 1) if rrf_scores else 0)

        enabled_routes = [r for r in routes if r != disabled_route]
        latencies = route_log["latency"]
        counts = route_log["chunk_count"]
        rrf_scores = route_log["avg_rrf_score"]
        result["by_route"][disabled_route] = {
            "enabled_routes": enabled_routes,
            "avg_latency_ms": round(sum(latencies) / len(latencies), 2) if latencies else 0,
            "avg_chunks": round(sum(counts) / len(counts), 2) if counts else 0,
            "avg_rrf_score": round(sum(rrf_scores) / len(rrf_scores), 6) if rrf_scores else 0,
            "chunk_delta_vs_baseline": round(
                (sum(counts) / len(counts) - result["baseline"]["avg_chunks"]), 2
            ) if counts else 0,
            "rrf_score_delta_vs_baseline": round(
                (sum(rrf_scores) / len(rrf_scores) - result["baseline"]["avg_rrf_score"]), 6
            ) if rrf_scores else 0,
            "sample_count": len(samples),
        }

    # ── 合并 metadata 路由组：delta 完全相同的 metadata 路由合并为一行 ──
    meta_routes_in_result = [r for r in routes if r in _meta_routes]
    base_routes_in_result = [r for r in routes if r not in _meta_routes]

    # 检测 metadata 路由是否冗余（chunk_delta 和 rrf_score_delta 完全一致）
    meta_deltas: dict[str, tuple[float, float]] = {}
    for r in meta_routes_in_result:
        info = result["by_route"].get(r)
        if info:
            meta_deltas[r] = (info["chunk_delta_vs_baseline"], info["rrf_score_delta_vs_baseline"])

    unique_meta_deltas = set(meta_deltas.values())
    is_redundant = len(unique_meta_deltas) == 1 and len(meta_deltas) > 1

    # 额外跑一次"禁用全部 metadata 路由"
    all_meta_disabled_log: dict[str, list[float | int]] = {"latency": [], "chunk_count": [], "avg_rrf_score": []}
    for sample in samples:
        docs, timing = diag.retrieve_diagnostic(
            sample.query, collection_name, cfg.retrieval_k,
            disable_routes=meta_routes_in_result,
            use_rerank=use_rerank,
        )
        all_meta_disabled_log["latency"].append(timing.get("total_ms", 0))
        all_meta_disabled_log["chunk_count"].append(len(docs))
        rrf_scores = [d.get("metadata", {}).get("recall_score") or 0 for d in docs]
        all_meta_disabled_log["avg_rrf_score"].append(sum(rrf_scores) / max(len(rrf_scores), 1) if rrf_scores else 0)

    a_lat = all_meta_disabled_log["latency"]
    a_cnt = all_meta_disabled_log["chunk_count"]
    a_rrf = all_meta_disabled_log["avg_rrf_score"]
    all_meta_ablation = {
        "disabled_routes": meta_routes_in_result,
        "avg_latency_ms": round(sum(a_lat) / len(a_lat), 2) if a_lat else 0,
        "avg_chunks": round(sum(a_cnt) / len(a_cnt), 2) if a_cnt else 0,
        "avg_rrf_score": round(sum(a_rrf) / len(a_rrf), 6) if a_rrf else 0,
        "chunk_delta_vs_baseline": round(
            (sum(a_cnt) / len(a_cnt) - result["baseline"]["avg_chunks"]), 2
        ) if a_cnt else 0,
        "rrf_score_delta_vs_baseline": round(
            (sum(a_rrf) / len(a_rrf) - result["baseline"]["avg_rrf_score"]), 6
        ) if a_rrf else 0,
        "sample_count": len(samples),
    }

    # 构建 by_group：base 路由逐条 + metadata 合并行
    by_group: dict[str, Any] = {}
    for r in base_routes_in_result:
        if r in result["by_route"]:
            by_group[r] = result["by_route"][r]

    if is_redundant:
        # 冗余：合并为单行，标注冗余
        by_group["metadata_routes"] = {
            **all_meta_ablation,
            "group_redundant": True,
            "redundant_routes": meta_routes_in_result,
            "note": f"{len(meta_routes_in_result)} metadata routes have identical deltas; merged into one row",
        }
    else:
        # 非冗余：逐条保留 + 额外附"全部禁用"行
        for r in meta_routes_in_result:
            if r in result["by_route"]:
                by_group[r] = result["by_route"][r]
        by_group["all_metadata_disabled"] = {
            **all_meta_ablation,
            "group_redundant": False,
        }

    result["by_group"] = by_group
    result["metadata_redundant"] = is_redundant

    return result


# ════════════════════════════════════════════════════════
# 2. Sentence Window 效果
# ════════════════════════════════════════════════════════

def diagnose_sentence_window(
    samples: list[EvalSample],
    collection_name: str,
    cfg: EvaluationConfig,
) -> dict[str, Any]:
    """对比不同窗口大小和 chunk_size 的效果"""
    diag = get_diagnostic_retriever()
    logger.info("Diagnosis: Sentence Window (%d configs)", len(cfg.window_sizes) * len(cfg.chunk_sizes))

    config_results: list[dict[str, Any]] = []

    for ws in cfg.window_sizes:
        for cs in cfg.chunk_sizes:
            run_timings: list[float] = []
            run_chunk_counts: list[int] = []
            run_added_counts: list[int] = []

            for sample in samples:
                docs, timing = diag.retrieve_diagnostic(
                    sample.query,
                    collection_name,
                    cfg.retrieval_k,
                    window_size=ws,
                    use_rerank=cfg.use_rerank,
                )
                run_timings.append(timing.get("total_ms", 0))
                run_chunk_counts.append(len(docs))
                run_added_counts.append(
                    sum(1 for d in docs if d.get("metadata", {}).get("_window_expanded") or d.get("metadata", {}).get("_parent_expanded"))
                )

            config_results.append({
                "window_size": ws,
                "chunk_size": cs,
                "avg_latency_ms": round(sum(run_timings) / len(run_timings), 2) if run_timings else 0,
                "avg_total_chunks": round(sum(run_chunk_counts) / len(run_chunk_counts), 1) if run_chunk_counts else 0,
                "avg_expanded_chunks": round(sum(run_added_counts) / len(run_added_counts), 1) if run_added_counts else 0,
            })

    return {
        "configs_tested": [f"ws={r['window_size']}+cs={r['chunk_size']}" for r in config_results],
        "results": config_results,
        "recommended": min(config_results, key=lambda r: r["avg_latency_ms"]) if config_results else {},
    }


# ════════════════════════════════════════════════════════
# 3. Reranker 影响
# ════════════════════════════════════════════════════════

def diagnose_reranker_impact(
    samples: list[EvalSample],
    collection_name: str,
    cfg: EvaluationConfig,
) -> dict[str, Any]:
    """有/无 Reranker 的对比"""
    diag = get_diagnostic_retriever()
    logger.info("Diagnosis: Reranker Impact (%d samples)", len(samples))

    with_rerank_results: list[int] = []
    without_rerank_results: list[int] = []
    rerank_timings: list[float] = []
    with_rerank_rrf: list[float] = []
    without_rerank_rrf: list[float] = []

    for sample in samples:
        # 有 Reranker
        docs_on, timing_on = diag.retrieve_diagnostic(
            sample.query, collection_name, cfg.retrieval_k, use_rerank=True,
        )
        with_rerank_results.append(len(docs_on))
        rerank_timings.append(timing_on.get("rerank_ms", 0))
        rrf_on = [d.get("metadata", {}).get("recall_score") or 0 for d in docs_on]
        with_rerank_rrf.append(sum(rrf_on) / max(len(rrf_on), 1) if rrf_on else 0)

        # 无 Reranker
        docs_off, timing_off = diag.retrieve_diagnostic(
            sample.query, collection_name, cfg.retrieval_k, use_rerank=False,
        )
        without_rerank_results.append(len(docs_off))
        rrf_off = [d.get("metadata", {}).get("recall_score") or 0 for d in docs_off]
        without_rerank_rrf.append(sum(rrf_off) / max(len(rrf_off), 1) if rrf_off else 0)

    def _avg(vals: list[float | int]) -> float:
        return round(sum(vals) / len(vals), 2) if vals else 0.0

    return {
        "sample_count": len(samples),
        "with_rerank": {
            "avg_chunks_returned": _avg(with_rerank_results),
            "avg_rrf_score": round(_avg(with_rerank_rrf), 6),
        },
        "without_rerank": {
            "avg_chunks_returned": _avg(without_rerank_results),
            "avg_rrf_score": round(_avg(without_rerank_rrf), 6),
        },
        "rerank_overhead": {
            "avg_rerank_ms": _avg(rerank_timings),
        },
    }


# ════════════════════════════════════════════════════════
# 4. 查询分解诊断
# ════════════════════════════════════════════════════════

def diagnose_query_decomposition(
    samples: list[EvalSample],
    collection_name: str,
    cfg: EvaluationConfig,
) -> dict[str, Any]:
    """分析查询分解的触发率（零 LLM 成本：只判 should_decompose，不实际分解）"""
    decomposer = get_decomposer()
    logger.info("Diagnosis: Query Decomposition (%d samples)", len(samples))

    decomposed_count = 0
    # 不调用 decompose()：避免 LLM 调用，Layer 2 应零 LLM 成本
    # 只统计触发率，子查询数量从 runtime_stats 获取

    for sample in samples:
        if decomposer.should_decompose(sample.query):
            decomposed_count += 1

    stats = decomposer.stats()

    return {
        "total_queries": len(samples),
        "decomposed_count": decomposed_count,
        "decompose_ratio": round(decomposed_count / len(samples), 4) if samples else 0,
        "avg_sub_queries_per_decomposed": stats.get("decompose_avg_sub_count", 0),
        "runtime_stats": {
            "decompose_triggered": stats.get("decompose_triggered", 0),
            "decompose_success": stats.get("decompose_success", 0),
            "decompose_success_rate": stats.get("decompose_success_rate", 0),
            "decompose_avg_sub_count": stats.get("decompose_avg_sub_count", 0),
        },
    }


# ════════════════════════════════════════════════════════
# 5. Pipeline 耗时分解
# ════════════════════════════════════════════════════════

def diagnose_pipeline_timing(
    samples: list[EvalSample],
    collection_name: str,
    cfg: EvaluationConfig,
) -> dict[str, Any]:
    """逐阶段分解 Pipeline 耗时"""
    diag = get_diagnostic_retriever()
    logger.info("Diagnosis: Pipeline Timing (%d samples)", len(samples))

    agg: dict[str, list[float]] = {
        "total_ms": [],
        "rrf_ms": [],
        "rerank_ms": [],
        "window_ms": [],
    }

    for sample in samples:
        _, timing = diag.retrieve_diagnostic(
            sample.query, collection_name, cfg.retrieval_k,
            use_rerank=cfg.use_rerank,
        )
        for key in agg:
            val = timing.get(key, 0)
            if isinstance(val, (int, float)):
                agg[key].append(float(val))

    def _pct(vals: list[float]) -> dict[str, float]:
        if not vals:
            return {"avg": 0, "p50": 0, "p95": 0}
        s = sorted(vals)
        return {
            "avg_ms": round(sum(s) / len(s), 2),
            "p50_ms": round(s[len(s) // 2], 2),
            "p95_ms": round(s[min(len(s) - 1, int(len(s) * 0.95))], 2),
        }

    breakdown = {key: _pct(vals) for key, vals in agg.items()}

    # 计算占比
    total_avg = breakdown.get("total_ms", {}).get("avg_ms", 0) or 1
    for key in breakdown:
        if key != "total_ms":
            breakdown[key]["pct"] = round(
                (breakdown[key].get("avg_ms", 0) / total_avg) * 100, 1,
            )

    return {
        "sample_count": len(samples),
        "breakdown": breakdown,
    }


# ════════════════════════════════════════════════════════
# 6. 守卫治理统计
# ════════════════════════════════════════════════════════

def diagnose_guard_governance(
    samples: list[EvalSample],
    collection_name: str,
    cfg: EvaluationConfig,
) -> dict[str, Any]:
    """统计守卫治理效果：从历史消息中分析 governance 字段"""
    logger.info("Diagnosis: Guard Governance (%d samples)", len(samples))

    try:
        from app.db.session import get_db as get_session
        from app.db.models import Message
    except ImportError:
        logger.warning("Guard Governance: 数据库模块不可用，跳过")
        return {"error": "database module not available"}

    import json as _json

    stats: dict[str, Any] = {
        "total_messages": 0,
        "messages_with_governance": 0,
        "confidence_distribution": {"high": 0, "medium": 0, "low": 0, "unknown": 0},
        "flags_summary": {},
        "pass_rate": 0.0,
        "source_rate": 0.0,
    }

    try:
        db = next(get_session())
        try:
            messages = db.query(Message).filter(
                Message.role == "assistant",
                Message.governance.isnot(None),
            ).all()

            stats["total_messages"] = db.query(Message).filter(
                Message.role == "assistant"
            ).count()
            stats["messages_with_governance"] = len(messages)

            if not messages:
                return stats

            pass_count = 0
            source_count = 0

            for msg in messages:
                try:
                    gov = _json.loads(msg.governance) if isinstance(msg.governance, str) else msg.governance
                except (_json.JSONDecodeError, TypeError):
                    continue

                conf = gov.get("confidence", "unknown")
                stats["confidence_distribution"][conf] = stats["confidence_distribution"].get(conf, 0) + 1

                if gov.get("passed", True):
                    pass_count += 1

                if gov.get("has_source", False):
                    source_count += 1

                for flag in gov.get("flags", []):
                    stats["flags_summary"][flag] = stats["flags_summary"].get(flag, 0) + 1

            n = len(messages)
            stats["pass_rate"] = round(pass_count / n, 4) if n else 0
            stats["source_rate"] = round(source_count / n, 4) if n else 0

        finally:
            db.close()
    except Exception as e:
        logger.warning("Guard Governance: 数据库查询失败: %s", e)
        stats["error"] = str(e)

    return stats


# ════════════════════════════════════════════════════════
# 整体入口
# ════════════════════════════════════════════════════════

def run_all_diagnostics(
    samples: list[EvalSample],
    collection_name: str,
    cfg: EvaluationConfig,
) -> dict[str, Any]:
    """运行所有启用的诊断"""
    results: dict[str, Any] = {}

    if cfg.enable_route_ablation:
        results["route_ablation"] = diagnose_route_ablation(samples, collection_name, cfg)

    results["sentence_window"] = diagnose_sentence_window(samples, collection_name, cfg)

    if cfg.enable_reranker_ablation:
        results["reranker_impact"] = diagnose_reranker_impact(samples, collection_name, cfg)

    results["pipeline_timing"] = diagnose_pipeline_timing(samples, collection_name, cfg)

    results["guard_governance"] = diagnose_guard_governance(samples, collection_name, cfg)

    return results
