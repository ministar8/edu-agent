"""遥测报表的渲染（从 telemetry_report.py 拆出，行为等价）。"""

from __future__ import annotations

import logging
from typing import Any

from evaluation.diagnostics._telemetry_common import QUERY_TYPES

logger = logging.getLogger(__name__)


def _fmt_header(meta: dict[str, Any]) -> list[str]:
    """报表抬头：标题 + 日志规模 + 时间跨度 + 时间窗口过滤态。"""
    out: list[str] = []
    out.append("=" * 78)
    out.append("  遥测报表（只读；非门禁、非线上统计）")
    out.append("=" * 78)
    out.append(f"  日志      {meta['log_path']}")
    out.append(
        f"  规模      {meta['log_lines']} 行 / {meta['log_bytes'] / 1e6:.1f} MB"
        f"  (坏行 {meta['bad_lines']})"
    )
    sampled = meta.get("sampled_records") or 0
    if sampled:
        out.append(
            f"  采样      {sampled} 行带 1/N 标注 ⇒ 各类条数是**日志行数**、"
            "不是发生次数（还原值见 event_counts_estimated，需 --json）"
        )
    out.append(f"  时间跨度  {meta['time_span'][0]} → {meta['time_span'][1]}")
    window = meta.get("window") or {}
    if window.get("filtered"):
        out.append(f"  时间窗口  since={window.get('since')}  until={window.get('until')}")
    else:
        out.append(
            "  时间窗口  **未过滤** ⚠ 日志混了多个代码版本，此报表是混合口径"
            "（用 --since/--until 钉到单一版本）"
        )
    return out


def _fmt_traffic(report: dict[str, Any]) -> list[str]:
    """流量构成一节。"""
    split = report["traffic_split"]["retrieve_query"]
    out: list[str] = [
        "",
        "-- 流量构成（query_preview ∩ 黄金集）--",
        f"  retrieve_query 共 {split['total']}：评测 {split['evaluation']}"
        f"（{split['evaluation_ratio']:.1%}） / 其余 {split['other']}",
        "  ★ 评测占比接近 100% ⇒ 本日志**不是**线上统计，别拿它推断生产表现",
    ]
    other_top = report["traffic_split"]["other_top_queries"]
    if other_top:
        out.append("  其余流量的高频 query（多为探针/手工测试）：")
        for query, count in other_top[:5]:
            out.append(f"    {count:5d}  {query[:52]}")
    return out


def _fmt_funnel(report: dict[str, Any]) -> list[str]:
    """逐阶段漏斗一节。"""
    out: list[str] = [
        "",
        "-- 逐阶段漏斗（评测流量，按黄金集 query_type）--",
        f"  {'type':9s} {'n':>6s} {'去重后':>8s} {'过阈后':>8s} {'重排后':>8s} "
        f"{'过阈率':>8s} {'hit率':>7s}",
    ]
    for name in QUERY_TYPES:
        item = report["funnel_by_query_type"][name]
        if not item["n"]:
            continue
        out.append(
            f"  {name:9s} {item['n']:6d} {item['after_section_dedup']:8.2f}"
            f" {item['after_threshold']:8.2f} {item['after_rerank']:8.2f}"
            f" {item['threshold_keep_rate']:8.3f} {item['hit_rate']:7.3f}"
        )
    out.append("  ★ 过阈率 = 过阈后 / 去重后。它低 = 阈值层砍得狠（见方案 §3⑦）")
    return out


def _fmt_thresholds(report: dict[str, Any]) -> list[str]:
    """有效阈值分布一节。"""
    out: list[str] = ["", "-- 有效阈值分布（每个 query_type 的阈值应当一致且可解释）--"]
    for name in QUERY_TYPES:
        dist = report["threshold_by_query_type"][name]
        if dist:
            out.append(f"  {name:9s} {dist}")
    return out


def _fmt_distribution(report: dict[str, Any]) -> list[str]:
    """分层 / 路由分布一节。"""
    out: list[str] = ["", "-- 分层 / 路由分布（评测流量）--"]
    for key, dist in report["distribution"].items():
        out.append(f"  {key:18s} {dist}")
    return out


def _fmt_evidence(report: dict[str, Any]) -> list[str]:
    """证据层一节。"""
    evidence = report["evidence"]
    return [
        "",
        "-- 证据层 --",
        f"  语义缓存命中率 {evidence['semantic_cache_hit_rate']}"
        f"  (n={evidence['semantic_cache_samples']})",
        f"  evidence_verdict {evidence['evidence_verdict']}",
        f"  retry_count      {evidence['retry_count']}",
        "  ★ hard_fail 占比不等于「查询失败率」—— 它不含治理层的重试结果",
    ]


def _fmt_ingest(report: dict[str, Any]) -> list[str]:
    """入库侧一节。"""
    ingest = report["ingest"]
    out: list[str] = [
        "",
        "-- 入库侧（每文件取最后一次；indexed 合计应与生产索引规模一致）--",
        f"  文件 {ingest['files']} 个（事件 {ingest['events']} 条）"
        f"  切分产出 {ingest['split_total']} → 实际入库 {ingest['indexed_total']}",
        f"  分集合（实际入库）{ingest['per_category']}",
    ]
    if ingest["mismatched_files"]:
        out.append("  ⚠ 切分产出 ≠ 实际入库的文件（差额 = 内容哈希判重丢弃）：")
        for item in ingest["mismatched_files"]:
            out.append(
                f"    {item['category']:22s} {item['file']:26s}"
                f" {item['chunks']} → {item['indexed_chunks']}  丢 {item['dropped']}"
            )
    return out


def format_report(report: dict[str, Any]) -> str:
    """人类可读版。刻意保持窄表 —— 宽表在终端会折行。"""
    out: list[str] = []
    out += _fmt_header(report["_meta"])
    out += _fmt_traffic(report)
    out += _fmt_funnel(report)
    out += _fmt_thresholds(report)
    out += _fmt_distribution(report)
    out += _fmt_evidence(report)
    out += _fmt_ingest(report)
    return "\n".join(out)
