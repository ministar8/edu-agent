"""评估报告输出：JSON + Markdown"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def build_metadata(config: dict[str, Any]) -> dict[str, Any]:
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "config": config,
    }


# ════════════════════════════════════════════════════════
# JSON 报告
# ════════════════════════════════════════════════════════

def write_json_report(
    report: dict[str, Any],
    output_path: str | Path,
) -> Path:
    """写入 JSON 报告（排除 raw_scores 以控制文件大小）"""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    def _strip_raw_scores(obj: Any) -> Any:
        if isinstance(obj, dict):
            return {k: _strip_raw_scores(v) for k, v in obj.items() if k != "raw_scores"}
        if isinstance(obj, list):
            return [_strip_raw_scores(item) for item in obj]
        return obj

    with open(path, "w", encoding="utf-8") as f:
        json.dump(_strip_raw_scores(report), f, ensure_ascii=False, indent=2)
    logger.info("JSON 报告已写入: %s", path)
    return path


# ════════════════════════════════════════════════════════
# Markdown 报告
# ════════════════════════════════════════════════════════

def _score_row(label: str, data: dict[str, Any] | None) -> str:
    if not data:
        return f"| {label} | N/A | N/A | N/A | N/A | N/A | N/A |\n"
    return (
        f"| {label} "
        f"| {data.get('mean', 'N/A')} "
        f"| {data.get('std', 'N/A')} "
        f"| {data.get('p50', 'N/A')} "
        f"| {data.get('p90', 'N/A')} "
        f"| {data.get('valid_n', data.get('n', 'N/A'))} "
        f"| {data.get('nan_count', 0)} |\n"
    )


def _table_row(cols: list[str]) -> str:
    return "| " + " | ".join(cols) + " |\n"


def _table_header(cols: list[str]) -> str:
    sep = "| " + " | ".join("---" for _ in cols) + " |\n"
    return _table_row(cols) + sep


def generate_markdown_report(report: dict[str, Any]) -> str:
    """生成 Markdown 格式评估报告"""
    lines: list[str] = []
    lines.append("# Evaluation Report\n")
    meta = report.get("_metadata", {})
    cfg = meta.get("config", {})
    lines.append(f"**时间**: {meta.get('timestamp', 'N/A')}\n")
    lines.append(f"**数据集**: {cfg.get('dataset', 'N/A')}  ({cfg.get('sample_count', 0)} 条)\n")
    cfg_items = [f"- {k}: {v}" for k, v in cfg.items() if not k.startswith("_")]
    if cfg_items:
        lines.append("**配置**:\n" + "\n".join(cfg_items) + "\n")

    # ── Layer 1: RAGAS ──
    layer1 = report.get("layer1", {})
    if layer1:
        lines.append("## Layer 1: RAGAS Metrics\n")
        cols = ["Metric", "Mean", "Std", "P50", "P90", "Valid", "NaN"]
        lines.append(_table_header(cols))
        for metric, scores in sorted(layer1.items()):
            if metric.startswith("_"):
                continue
            if isinstance(scores, dict) and "mean" in scores:
                lines.append(_score_row(metric, scores))

        n = layer1.get("_meta", {}).get("n", 0)
        duration = layer1.get("_meta", {}).get("duration_ms", 0)
        lines.append(f"\n**样本数**: {n}  |  **耗时**: {duration}ms\n")

        # Token 统计
        ts = layer1.get("_meta", {}).get("token_stats", {})
        if ts:
            total_tokens = ts.get("answer_input_est", 0) + ts.get("answer_output_est", 0) + ts.get("judge_input_est", 0) + ts.get("judge_output_est", 0)
            lines.append(f"**Token 消耗估算**: {total_tokens:,} tokens\n")
            lines.append(f"- 答案生成: input {ts.get('answer_input_est', 0):,} + output {ts.get('answer_output_est', 0):,} ({ts.get('answer_llm_calls', 0)} calls)\n")
            lines.append(f"- Judge 评估: input {ts.get('judge_input_est', 0):,} + output {ts.get('judge_output_est', 0):,}\n")
            lines.append(f"- 缓存命中: {ts.get('cache_hits', 0)}  |  空 context 跳过: {ts.get('empty_context_skips', 0)}\n")

    # ── Layer 2: Diagnosis ──
    layer2 = report.get("layer2", {})
    if layer2:
        lines.append("## Layer 2: Diagnostics\n")

        # Route Ablation
        ra = layer2.get("route_ablation", {})
        if ra:
            lines.append("### Route Ablation\n")
            # 基线
            baseline = ra.get("baseline", {})
            if baseline:
                lines.append(f"**Baseline**: avg_chunks={baseline.get('avg_chunks', 'N/A')}, "
                             f"avg_rrf_score={baseline.get('avg_rrf_score', 'N/A')}, "
                             f"avg_rerank_score={baseline.get('avg_rerank_score', 'N/A')}, "
                             f"avg_latency={baseline.get('avg_latency_ms', 'N/A')}ms\n")
            cols = ["Disabled Route", "Avg Chunks", "Chunk Δ", "Avg RRF Score", "RRF Score Δ", "Avg Latency (ms)"]
            lines.append(_table_header(cols))
            # 优先用 by_group（metadata 路由已合并），回退到 by_route
            route_data = ra.get("by_group") or ra.get("by_route", {})
            for route, info in route_data.items():
                route_label = route
                if info.get("group_redundant"):
                    route_label = f"{route} ({len(info.get('redundant_routes', []))} routes, redundant)"
                lines.append(_table_row([
                    route_label,
                    str(info.get("avg_chunks", "N/A")),
                    str(info.get("chunk_delta_vs_baseline", "N/A")),
                    str(info.get("avg_rrf_score", "N/A")),
                    str(info.get("rrf_score_delta_vs_baseline", "N/A")),
                    str(info.get("avg_latency_ms", "N/A")),
                ]))
            if ra.get("metadata_redundant"):
                lines.append("\n> ⚠ Metadata routes are redundant: disabling any single one produces identical deltas. "
                             "See `metadata_routes` row for disabling all at once.\n")

        # Sentence Window
        sw = layer2.get("sentence_window", {})
        if sw:
            lines.append("\n### Sentence Window Effect\n")
            cols = ["Window Size", "Chunk Size", "Avg Chunks", "Avg Expanded", "Avg Latency (ms)"]
            lines.append(_table_header(cols))
            for cfg_result in sw.get("results", []):
                lines.append(_table_row([
                    str(cfg_result.get("window_size")),
                    str(cfg_result.get("chunk_size")),
                    str(cfg_result.get("avg_total_chunks")),
                    str(cfg_result.get("avg_expanded_chunks")),
                    str(cfg_result.get("avg_latency_ms")),
                ]))

        # Reranker
        ri = layer2.get("reranker_impact", {})
        if ri:
            lines.append("\n### Reranker Impact\n")
            cols = ["Mode", "Avg Chunks", "Avg RRF Score"]
            lines.append(_table_header(cols))
            wr = ri.get("with_rerank", {})
            wor = ri.get("without_rerank", {})
            lines.append(_table_row(["With Reranker", str(wr.get("avg_chunks_returned", "N/A")), str(wr.get("avg_rrf_score", "N/A"))]))
            lines.append(_table_row(["Without Reranker", str(wor.get("avg_chunks_returned", "N/A")), str(wor.get("avg_rrf_score", "N/A"))]))
            overhead = ri.get("rerank_overhead", {})
            lines.append(f"\n**Rerank Overhead**: {overhead.get('avg_rerank_ms', 'N/A')}ms avg\n")

        # Query Decomposition
        qd = layer2.get("query_decomposition", {})
        if qd:
            lines.append("\n### Query Decomposition\n")
            lines.append(f"- **Total Queries**: {qd.get('total_queries', 0)}\n")
            lines.append(f"- **Decomposed**: {qd.get('decomposed_count', 0)} ({qd.get('decompose_ratio', 0) * 100:.1f}%)\n")
            lines.append(f"- **Avg Sub-queries**: {qd.get('avg_sub_queries_per_decomposed', 0)}\n")

        # Pipeline Timing
        pt = layer2.get("pipeline_timing", {})
        if pt:
            lines.append("\n### Pipeline Timing\n")
            cols = ["Stage", "Avg (ms)", "P50 (ms)", "P95 (ms)", "% of Total"]
            lines.append(_table_header(cols))
            breakdown = pt.get("breakdown", {})
            for stage, stats in sorted(breakdown.items()):
                pct = stats.get("pct", "")
                pct_str = f"{pct}%" if pct else ""
                lines.append(_table_row([
                    stage,
                    str(stats.get("avg_ms", "")),
                    str(stats.get("p50_ms", "")),
                    str(stats.get("p95_ms", "")),
                    pct_str,
                ]))

        # Guard Governance
        gg = layer2.get("guard_governance", {})
        if gg and "error" not in gg:
            lines.append("\n### Guard Governance\n")
            lines.append(f"- **Total Messages**: {gg.get('total_messages', 0)}\n")
            lines.append(f"- **With Governance**: {gg.get('messages_with_governance', 0)}\n")
            lines.append(f"- **Pass Rate**: {gg.get('pass_rate', 0) * 100:.1f}%\n")
            lines.append(f"- **Source Rate**: {gg.get('source_rate', 0) * 100:.1f}%\n")
            conf = gg.get("confidence_distribution", {})
            if conf:
                lines.append(f"- **Confidence**: high={conf.get('high', 0)}, medium={conf.get('medium', 0)}, low={conf.get('low', 0)}\n")
            flags = gg.get("flags_summary", {})
            if flags:
                lines.append(f"- **Flags**: {dict(list(flags.items())[:5])}\n")

    return "".join(lines)


def write_markdown_report(
    report: dict[str, Any],
    output_path: str | Path,
) -> Path:
    """写入 Markdown 报告"""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    md = generate_markdown_report(report)
    with open(path, "w", encoding="utf-8") as f:
        f.write(md)
    logger.info("Markdown 报告已写入: %s", path)
    return path
