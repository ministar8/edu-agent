"""遥测报表：把 `data/metrics/rag_metrics.jsonl` 变成**可读的聚合报表**。

为什么需要它
------------
`rag.metrics` 只负责**写**（`MetricsWriter.emit`），全仓**没有任何读方** ——
于是这份日志一直是「只写不读」的：它已经积累了 20 万级的事件，却没有任何模块
消费它。本模块补上读方。

它**不是门禁**，是报表
------------------------
与 `retrieval_gate` / `probe_gate` 的关键区别：

- **无基线、无退出码判定**。退出码只用于「读不到文件」这类错误（返回 2）。
  理由：本日志的输入以**评测流量**为主（跑一次门禁就写入 936 条），
  内容随「跑了几次门禁」而变 ⇒ 拿它当带基线的门禁会引入一个**不稳定判据**。
- 只读，不碰索引、不碰生产数据。

★ 使用前必须知道的一件事：它**不是线上统计**
--------------------------------------------
用 `tags.query_preview ∩ 黄金集` 可以判断一条记录是不是评测跑出来的。实测
（2026-09-27）`retrieve_query` 里 **99.4% 是评测流量**，真实用户流量约等于 0。
所以本报表回答的是「**管线各层在黄金集上的行为分布**」，
**不是**「线上检索准不准」。`traffic_split` 一节会把这件事量化出来。

它比 `candidate_trace` 强的地方
--------------------------------
每条 `retrieve_query` 都带**完整逐阶段漏斗**
（`before_threshold → after_section_dedup → after_threshold → after_rerank → after_window`）
外加 `retrieval_layer` / `route_type` / `use_rerank` / `rerank_used` / `decomposed`。
而且它是**纯读日志**，没有 `candidate_trace` 那个「跑生产索引、无就绪屏障、
会间歇性撞 Chroma 竞态」的问题。

用法::

    PYTHONPATH=src uv run python -m evaluation.telemetry_report
    ... --json                       # 机器可读
    ... --output evals/results/telemetry_2026-09-27/report.json   # 落盘归档

归档约定：产物放 `evals/results/<描述>_<日期>/`（`.log` / `.json` 有 gitignore 例外），
**日志本体不入库** —— 它在 `data/`（已忽略）且是评测 exhaust，不是证据。
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean
from typing import Any

from rag.metrics import DEFAULT_METRICS_PATH

logger = logging.getLogger(__name__)

DEFAULT_GOLDEN_PATH = "evals/sample_408.jsonl"
DEFAULT_PAIRED_PATH = "evals/ragas_paired20.jsonl"

# 逐阶段漏斗的键（顺序即管线顺序）。取自 `retriever` 写入 `retrieve_query` 的字段名，
# **不要重排** —— 报表的「过阈率」按下标取，重排会静默算错。
STAGES: tuple[str, ...] = (
    "before_threshold",
    "after_section_dedup",
    "after_threshold",
    "after_rerank",
    "after_window",
)
QUERY_TYPES: tuple[str, ...] = ("concept", "generate", "grade", "code")


def load_query_index(paths: list[str]) -> dict[str, dict[str, str]]:
    """把黄金集（可多份）读成 ``{query: metadata}``，用于给遥测行反查 query_type。

    为什么用 query 文本而不是 id 做 join key：`retrieve_query` 的 tags 里
    **只有 `query_preview`**（前 120 字符），没有黄金集 id。所以 join 只能按文本。
    ★ 副作用：超过 120 字符的 query 会 join 不上 —— `load_query_index` 因此
    **同时登记截断后的形式**，否则长 query 会被静默算进「非评测流量」。
    """
    out: dict[str, dict[str, str]] = {}
    for path in paths:
        p = Path(path)
        if not p.exists():
            logger.warning("query 索引文件不存在，跳过: %s", p)
            continue
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                raw = json.loads(line)
            except json.JSONDecodeError:
                continue
            query = str(raw.get("query", "")).strip()
            if not query:
                continue
            meta = raw.get("metadata") or {}
            entry = {
                "query_type": str(meta.get("query_type") or "concept"),
                "subject": str(meta.get("subject") or ""),
            }
            out.setdefault(query, entry)
            out.setdefault(query[:120], entry)
    return out


def scan_log(log_path: Path) -> dict[str, Any]:
    """**单遍**扫日志，只保留聚合所需的最小信息。

    刻意不保存 `chroma_query` / `embedding_batch` / `embed_documents` 的明细 ——
    它们占全部行数的九成以上，而报表只需要条数（保存会把内存打满）。
    """
    event_counts: Counter[str] = Counter()
    query_rows: list[dict[str, Any]] = []
    evidence_rows: list[dict[str, Any]] = []
    ingest_rows: list[dict[str, Any]] = []
    first_ts: str | None = None
    last_ts: str | None = None
    lines = 0
    bad_lines = 0

    with log_path.open(encoding="utf-8", errors="replace") as fh:
        for line in fh:
            lines += 1
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                bad_lines += 1
                continue
            event = str(rec.get("event") or "")
            event_counts[event] += 1
            ts = rec.get("ts")
            if isinstance(ts, str):
                first_ts = first_ts or ts
                last_ts = ts
            if event == "retrieve_query":
                query_rows.append(_slim(rec))
            elif event == "retrieve_evidence":
                evidence_rows.append(_slim(rec))
            elif event == "ingest_file_summary":
                ingest_rows.append(_slim(rec))

    return {
        "event_counts": dict(event_counts),
        "query_rows": query_rows,
        "evidence_rows": evidence_rows,
        "ingest_rows": ingest_rows,
        "lines": lines,
        "bad_lines": bad_lines,
        "bytes": log_path.stat().st_size,
        "time_span": [first_ts, last_ts],
    }


def _slim(rec: dict[str, Any]) -> dict[str, Any]:
    """只留 tags/values，丢掉整条原始记录（日志行含大量无关字段）。"""
    tags = rec.get("tags")
    values = rec.get("values")
    return {
        "query_preview": str((tags or {}).get("query_preview") or ""),
        "file": str((tags or {}).get("file") or ""),
        "category": str((tags or {}).get("category") or ""),
        "values": values if isinstance(values, dict) else {},
    }


def split_traffic(
    rows: list[dict[str, Any]], query_index: dict[str, dict[str, str]]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """按 `query_preview` 是否命中黄金集/配对集，把行分成「评测」与「其余」。"""
    evaluation: list[dict[str, Any]] = []
    other: list[dict[str, Any]] = []
    for row in rows:
        (evaluation if row["query_preview"] in query_index else other).append(row)
    return evaluation, other


def summarize_funnel(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """逐阶段均值 + 过阈率 + 命中率。**纯函数**。

    `threshold_keep_rate`（过阈率）= `after_threshold / after_section_dedup`
    —— 它衡量**阈值层砍掉了多少**，是 `docs/RETRIEVAL_PLAN.md` §3⑦
    （RRF 阈值量纲错配）的直接观测量。
    """
    out: dict[str, Any] = {"n": len(rows)}
    for stage in STAGES:
        vals = [
            r["values"][stage] for r in rows if isinstance(r["values"].get(stage), (int, float))
        ]
        out[stage] = round(mean(vals), 4) if vals else None
    dedup, kept = out["after_section_dedup"], out["after_threshold"]
    out["threshold_keep_rate"] = (
        round(kept / dedup, 4) if isinstance(dedup, (int, float)) and dedup else None
    )
    hits = [1.0 if r["values"].get("hit") else 0.0 for r in rows if "hit" in r["values"]]
    out["hit_rate"] = round(mean(hits), 4) if hits else None
    return out


def summarize_by_key(rows: list[dict[str, Any]], key: str) -> dict[str, int]:
    """统计某个 `values` 字段的取值分布（如 `retrieval_layer` / `use_rerank`）。"""
    counter: Counter[str] = Counter()
    for row in rows:
        if key in row["values"]:
            counter[str(row["values"][key])] += 1
    return dict(counter.most_common())


def build_ingest_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """入库侧聚合：**每个文件取最后一次**（同一文件被重入库多次）。

    ★ 为什么要同时统计 `chunks` 与 `indexed_chunks`：
    `chunks` 是切分产出，`indexed_chunks` 是**真正入库**的数量，两者之差是
    `vectorstore` 按**内容哈希**判重丢掉的量（`index_documents.dedup_skipped`）。
    实测（2026-09-27）合计 `indexed_chunks` = 2092，与生产索引规模**逐位一致** ⇒
    这个字段可以作为「遥测 vs 实际索引」的交叉校验；差值则指向具体文件。
    把差值单列出来，是为了不让「切分产出 106、实际入库 82」这种落差藏在合计里。
    """
    last: dict[tuple[str, str], tuple[int, int]] = {}
    for row in rows:
        if not row["file"]:
            continue
        chunks = row["values"].get("chunks")
        indexed = row["values"].get("indexed_chunks")
        if isinstance(chunks, int) and isinstance(indexed, int):
            last[(row["category"], row["file"])] = (chunks, indexed)

    per_category: dict[str, int] = defaultdict(int)
    for (_category, _file), (_chunks, indexed) in last.items():
        per_category[_category] += indexed
    mismatched = [
        {
            "category": category,
            "file": file,
            "chunks": chunks,
            "indexed_chunks": indexed,
            "dropped": chunks - indexed,
        }
        for (category, file), (chunks, indexed) in sorted(last.items())
        if chunks != indexed
    ]
    return {
        "events": len(rows),
        "files": len(last),
        "per_category": dict(sorted(per_category.items())),
        "indexed_total": sum(indexed for _c, indexed in last.values()),
        "split_total": sum(chunks for chunks, _i in last.values()),
        "mismatched_files": mismatched,
    }


def build_report(
    scan: dict[str, Any], query_index: dict[str, dict[str, str]], log_path: Path, golden: list[str]
) -> dict[str, Any]:
    """把扫描结果整理成报表字典（自描述：口径全部写进 `_meta`）。"""
    query_rows: list[dict[str, Any]] = scan["query_rows"]
    evidence_rows: list[dict[str, Any]] = scan["evidence_rows"]
    eval_rows, other_rows = split_traffic(query_rows, query_index)
    eval_ev, other_ev = split_traffic(evidence_rows, query_index)

    by_type: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in eval_rows:
        meta = query_index.get(row["query_preview"])
        if meta:
            by_type[meta["query_type"]].append(row)

    funnel: dict[str, Any] = {name: summarize_funnel(by_type.get(name, [])) for name in QUERY_TYPES}
    funnel["_all_eval"] = summarize_funnel(eval_rows)

    thresholds: dict[str, dict[str, int]] = {}
    for name in QUERY_TYPES:
        counter: Counter[str] = Counter()
        for row in by_type.get(name, []):
            value = row["values"].get("threshold")
            if isinstance(value, (int, float)):
                counter[str(round(value, 4))] += 1
        thresholds[name] = dict(sorted(counter.items(), key=lambda kv: float(kv[0])))

    other_top = Counter(r["query_preview"] for r in other_rows).most_common(10)

    cache_hits = [
        1.0 if r["values"].get("semantic_cache_hit") else 0.0
        for r in evidence_rows
        if "semantic_cache_hit" in r["values"]
    ]

    return {
        "_meta": {
            "log_path": str(log_path),
            "log_bytes": scan["bytes"],
            "log_lines": scan["lines"],
            "bad_lines": scan["bad_lines"],
            "time_span": scan["time_span"],
            "golden_paths": golden,
            "golden_queries": len(query_index),
            "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "note": (
                "只读遥测日志。输入以**评测流量**为主（见 traffic_split）⇒ "
                "本报表回答「管线各层在黄金集上的行为分布」，**不是**线上统计。"
                "无基线、无判定 —— 它不是门禁。"
            ),
        },
        "event_counts": dict(Counter(scan["event_counts"]).most_common()),
        "traffic_split": {
            "retrieve_query": {
                "total": len(query_rows),
                "evaluation": len(eval_rows),
                "other": len(other_rows),
                "evaluation_ratio": round(len(eval_rows) / len(query_rows), 4)
                if query_rows
                else None,
            },
            "retrieve_evidence": {
                "total": len(evidence_rows),
                "evaluation": len(eval_ev),
                "other": len(other_ev),
            },
            "other_top_queries": [[q, n] for q, n in other_top],
        },
        "funnel_by_query_type": funnel,
        "threshold_by_query_type": thresholds,
        "distribution": {
            key: summarize_by_key(eval_rows, key)
            for key in (
                "retrieval_layer",
                "route_type",
                "use_rerank",
                "rerank_used",
                "decomposed",
                "classifier_source",
            )
        },
        "evidence": {
            "semantic_cache_hit_rate": round(mean(cache_hits), 4) if cache_hits else None,
            "semantic_cache_samples": len(cache_hits),
            "verifier_used": summarize_by_key(evidence_rows, "verifier_used"),
            "evidence_verdict": summarize_by_key(evidence_rows, "evidence_verdict"),
            # ★ 读 `hard_fail` 占比前必须同时看 `retry_count`：本字段只反映**该次**
            # 证据事件的判定，不反映「治理层是否随后重试成功」。实测 retry_count 全为 0，
            # 说明重试另走路径 —— 所以 hard_fail 占比**不能**直接读成「16% 的查询失败」。
            "retry_count": summarize_by_key(evidence_rows, "retry_count"),
        },
        "ingest": build_ingest_summary(scan["ingest_rows"]),
    }


def format_report(report: dict[str, Any]) -> str:
    """人类可读版。刻意保持窄表 —— 宽表在终端会折行。"""
    meta = report["_meta"]
    out: list[str] = []
    out.append("=" * 78)
    out.append("  遥测报表（只读；非门禁、非线上统计）")
    out.append("=" * 78)
    out.append(f"  日志      {meta['log_path']}")
    out.append(
        f"  规模      {meta['log_lines']} 行 / {meta['log_bytes'] / 1e6:.1f} MB"
        f"  (坏行 {meta['bad_lines']})"
    )
    out.append(f"  时间跨度  {meta['time_span'][0]} → {meta['time_span'][1]}")

    split = report["traffic_split"]["retrieve_query"]
    out.append("")
    out.append("-- 流量构成（query_preview ∩ 黄金集）--")
    out.append(
        f"  retrieve_query 共 {split['total']}：评测 {split['evaluation']}"
        f"（{split['evaluation_ratio']:.1%}） / 其余 {split['other']}"
    )
    out.append("  ★ 评测占比接近 100% ⇒ 本日志**不是**线上统计，别拿它推断生产表现")
    other_top = report["traffic_split"]["other_top_queries"]
    if other_top:
        out.append("  其余流量的高频 query（多为探针/手工测试）：")
        for query, count in other_top[:5]:
            out.append(f"    {count:5d}  {query[:52]}")

    out.append("")
    out.append("-- 逐阶段漏斗（评测流量，按黄金集 query_type）--")
    header = f"  {'type':9s} {'n':>6s} {'去重后':>8s} {'过阈后':>8s} {'重排后':>8s} {'过阈率':>8s} {'hit率':>7s}"
    out.append(header)
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

    out.append("")
    out.append("-- 有效阈值分布（每个 query_type 的阈值应当一致且可解释）--")
    for name in QUERY_TYPES:
        dist = report["threshold_by_query_type"][name]
        if dist:
            out.append(f"  {name:9s} {dist}")

    out.append("")
    out.append("-- 分层 / 路由分布（评测流量）--")
    for key, dist in report["distribution"].items():
        out.append(f"  {key:18s} {dist}")

    evidence = report["evidence"]
    out.append("")
    out.append("-- 证据层 --")
    out.append(
        f"  语义缓存命中率 {evidence['semantic_cache_hit_rate']}"
        f"  (n={evidence['semantic_cache_samples']})"
    )
    out.append(f"  evidence_verdict {evidence['evidence_verdict']}")
    out.append(f"  retry_count      {evidence['retry_count']}")
    out.append("  ★ hard_fail 占比不等于「查询失败率」—— 它不含治理层的重试结果")

    ingest = report["ingest"]
    out.append("")
    out.append("-- 入库侧（每文件取最后一次；indexed 合计应与生产索引规模一致）--")
    out.append(
        f"  文件 {ingest['files']} 个（事件 {ingest['events']} 条）"
        f"  切分产出 {ingest['split_total']} → 实际入库 {ingest['indexed_total']}"
    )
    out.append(f"  分集合（实际入库）{ingest['per_category']}")
    if ingest["mismatched_files"]:
        out.append("  ⚠ 切分产出 ≠ 实际入库的文件（差额 = 内容哈希判重丢弃）：")
        for item in ingest["mismatched_files"]:
            out.append(
                f"    {item['category']:22s} {item['file']:26s}"
                f" {item['chunks']} → {item['indexed_chunks']}  丢 {item['dropped']}"
            )
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="遥测报表：把 rag_metrics.jsonl 聚合成人可读报表")
    parser.add_argument("--log", default=str(DEFAULT_METRICS_PATH), help="遥测日志 jsonl 路径")
    parser.add_argument(
        "--golden",
        action="append",
        default=None,
        help=f"黄金集 jsonl（可重复；默认 {DEFAULT_GOLDEN_PATH} 与 {DEFAULT_PAIRED_PATH}）",
    )
    parser.add_argument("--output", default=None, help="把 JSON 报表写到该路径（父目录会自动创建）")
    parser.add_argument("--json", action="store_true", help="打印 JSON 而不是表格")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )

    log_path = Path(args.log)
    if not log_path.exists():
        print(f"[错误] 遥测日志不存在: {log_path}", file=sys.stderr)
        print(
            "       提示：它由 rag.metrics 在检索/入库时写入；本机没跑过就没有。", file=sys.stderr
        )
        return 2

    golden = args.golden or [DEFAULT_GOLDEN_PATH, DEFAULT_PAIRED_PATH]
    query_index = load_query_index(golden)
    if not query_index:
        print(f"[错误] 未能从 {golden} 读到任何 query —— join key 不可用", file=sys.stderr)
        return 2

    scan = scan_log(log_path)
    report = build_report(scan, query_index, log_path, golden)

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(f"报表已写入: {out_path}")

    print(json.dumps(report, ensure_ascii=False, indent=2) if args.json else format_report(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
