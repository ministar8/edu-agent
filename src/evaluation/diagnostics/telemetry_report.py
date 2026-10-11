"""遥测报表：把 `data/metrics/rag_metrics.jsonl` 变成**可读的聚合报表**。

为什么需要它
------------
`rag.common.metrics` 只负责**写**（`MetricsWriter.emit`），全仓**没有任何读方** ——
于是这份日志一直是「只写不读」的：它已经积累了 20 万级的事件，却没有任何模块
消费它。本模块补上读方。

它**不是门禁**，是报表
------------------------
与 `retrieval_gate` / `probe_gate` 的关键区别：

- **无基线、无退出码判定**。退出码只用于「读不到文件」这类错误（返回 2）。
  理由：本日志的输入以**评测流量**为主（跑一次门禁就写入 936 条），
  内容随「跑了几次门禁」而变 ⇒ 拿它当带基线的门禁会引入一个**不稳定判据**。
- 只读，不碰索引、不碰生产数据。

★ 使用前必须知道的两件事
------------------------
**① 它大概率不是线上统计。** 用 `tags.query_preview ∩ 黄金集` 可以判断一条记录是不是
评测跑出来的。实测（2026-09-27）`retrieve_query` 里 **99.4% 是评测流量**，真实用户流量
约等于 0。所以本报表回答的是「**管线各层在黄金集上的行为分布**」，
**不是**「线上检索准不准」。`traffic_split` 一节会把这件事量化出来。

**② 它混了多个代码版本 ⇒ 必须按时间切开看。** 同一份日志里写着 Step 1~10 各轮实验的
运行记录，**同一个指标在不同时间段是不同的代码跑出来的**。实测（2026-09-27）：
`generate` 的过阈率在 09-27 07:00 UTC 前后从 **0.076 跳到 0.21**（Step 7/10 的
`_rrf_scale` 阈值量纲修正上线）—— 不切开就会读到一个「0.10 左右」的**混合口径**值，
既不是修前也不是修后。⇒ 用 `--since` / `--until` 把窗口钉在**单一代码版本**上：

    ... --since 2026-09-27T15:00          # 本机时区；只算此后的记录
    ... --since 6h                        # 最近 6 小时（锚点是日志最新一条事件，不是「现在」）

它比 `candidate_trace` 强的地方
--------------------------------
每条 `retrieve_query` 都带**完整逐阶段漏斗**
（`before_threshold → after_section_dedup → after_threshold → after_rerank → after_window`）
外加 `retrieval_layer` / `route_type` / `use_rerank` / `rerank_used` / `decomposed`。
而且它是**纯读日志**，没有 `candidate_trace` 那个「跑生产索引、无就绪屏障、
会间歇性撞 Chroma 竞态」的问题。

用法::

    PYTHONPATH=src uv run python -m evaluation.diagnostics.telemetry_report
    ... --json                       # 机器可读
    ... --output evals/results/telemetry_2026-09-27/report.json   # 落盘归档

归档约定：产物放 `evals/results/<描述>_<日期>/`（`.log` / `.json` 有 gitignore 例外），
**日志本体不入库** —— 它在 `data/`（已忽略）且是评测 exhaust，不是证据。
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import time
from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from statistics import mean
from typing import Any

from evaluation.diagnostics._telemetry_common import (
    DEFAULT_GOLDEN_PATH,
    DEFAULT_PAIRED_PATH,
    QUERY_TYPES,
    STAGES,
)
from evaluation.diagnostics._telemetry_format import format_report  # noqa: F401
from rag.common.metrics import DEFAULT_METRICS_PATH

logger = logging.getLogger(__name__)


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
    """只留 tags/values/ts，丢掉整条原始记录（日志行含大量无关字段）。"""
    tags = rec.get("tags")
    values = rec.get("values")
    return {
        "ts": str(rec.get("ts") or ""),
        "query_preview": str((tags or {}).get("query_preview") or ""),
        "file": str((tags or {}).get("file") or ""),
        "category": str((tags or {}).get("category") or ""),
        "values": values if isinstance(values, dict) else {},
    }


def parse_when(value: str, anchor: datetime) -> datetime:
    """解析时间边界：ISO-8601，或相对量 ``<N><s|m|h|d>``。

    ★ 相对量的锚点是**日志里最新的一条事件**（不是「现在」）—— 日志常常落后于当前时间，
    用「现在」做锚会让 ``--since 6h`` 落在日志之外、结果为空，看起来像「没数据」。
    无时区的 ISO 输入按**本机时区**解释。
    """
    text = value.strip()
    match = re.fullmatch(r"(\d+)\s*([smhd])", text)
    if match:
        amount, unit = int(match.group(1)), match.group(2)
        seconds = {"s": 1, "m": 60, "h": 3600, "d": 86400}[unit] * amount
        return anchor - timedelta(seconds=seconds)
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.astimezone()
    return parsed.astimezone(UTC)


def _latest_ts(scan: dict[str, Any]) -> datetime:
    """日志里最新一条事件的时间；取不到就退回当前时间。

    为什么需要它：相对时间量（`--since 6h`）要以**日志的最新记录**为锚点 ——
    日志常常落后于当前时间，用「现在」做锚会让窗口落在日志之外、结果为空，
    看起来像「这段时间没有数据」。
    """
    span = scan.get("time_span") or [None, None]
    text = span[1] if len(span) > 1 else None
    if isinstance(text, str):
        try:
            parsed = datetime.fromisoformat(text)
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
        except ValueError:
            logger.warning("无法解析日志最新时间戳 %r，改用当前时间做锚点", text)
    return datetime.now(UTC)


def filter_rows_by_time(
    rows: list[dict[str, Any]], since: datetime | None, until: datetime | None
) -> list[dict[str, Any]]:
    """按事件时间过滤。无法解析时间的行**保守保留**（宁可多算，不静默丢）。"""
    if since is None and until is None:
        return rows
    out: list[dict[str, Any]] = []
    for row in rows:
        try:
            when = datetime.fromisoformat(row["ts"])
            if when.tzinfo is None:
                when = when.replace(tzinfo=UTC)
            when = when.astimezone(UTC)
        except (ValueError, KeyError):
            out.append(row)
            continue
        if since is not None and when < since:
            continue
        if until is not None and when > until:
            continue
        out.append(row)
    return out


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


def _group_by_type(
    eval_rows: list[dict[str, Any]], query_index: dict[str, dict[str, str]]
) -> dict[str, list[dict[str, Any]]]:
    """把评测行按黄金集 `query_type` 分桶。"""
    by_type: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in eval_rows:
        meta = query_index.get(row["query_preview"])
        if meta:
            by_type[meta["query_type"]].append(row)
    return by_type


def _build_thresholds(by_type: dict[str, list[dict[str, Any]]]) -> dict[str, dict[str, int]]:
    """每个 query_type 的 `threshold` 取值分布（按键数值升序）。"""
    thresholds: dict[str, dict[str, int]] = {}
    for name in QUERY_TYPES:
        counter: Counter[str] = Counter()
        for row in by_type.get(name, []):
            value = row["values"].get("threshold")
            if isinstance(value, (int, float)):
                counter[str(round(value, 4))] += 1
        thresholds[name] = dict(sorted(counter.items(), key=lambda kv: float(kv[0])))
    return thresholds


def _build_meta(
    scan: dict[str, Any],
    log_path: Path,
    golden: list[str],
    query_index: dict[str, dict[str, str]],
    window: dict[str, str | None] | None,
) -> dict[str, Any]:
    """报表自描述头（口径全部写进这里）。"""
    return {
        "log_path": str(log_path),
        "log_bytes": scan["bytes"],
        "log_lines": scan["lines"],
        "bad_lines": scan["bad_lines"],
        "time_span": scan["time_span"],
        "golden_paths": golden,
        "golden_queries": len(query_index),
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        # 时间窗口：**必须**随报表一起落盘。日志混了多个代码版本，
        # 离开窗口就无法判断这份数字是哪一版代码跑出来的。
        "window": window or {"since": None, "until": None, "filtered": False},
        "note": (
            "只读遥测日志。① 输入以**评测流量**为主（见 traffic_split）⇒ "
            "本报表回答「管线各层在黄金集上的行为分布」，**不是**线上统计。"
            "② 日志混了多个代码版本 ⇒ 不看 window 就无法解释数字（同一指标在 "
            "不同时间段是不同代码跑出来的）。无基线、无判定 —— 它不是门禁。"
        ),
    }


def _build_traffic_split(
    query_rows: list[dict[str, Any]],
    eval_rows: list[dict[str, Any]],
    other_rows: list[dict[str, Any]],
    evidence_rows: list[dict[str, Any]],
    eval_ev: list[dict[str, Any]],
    other_ev: list[dict[str, Any]],
    other_top: list[tuple[str, int]],
) -> dict[str, Any]:
    """流量构成：评测 vs 其余（按 query_preview 是否命中黄金集）。"""
    return {
        "retrieve_query": {
            "total": len(query_rows),
            "evaluation": len(eval_rows),
            "other": len(other_rows),
            "evaluation_ratio": round(len(eval_rows) / len(query_rows), 4) if query_rows else None,
        },
        "retrieve_evidence": {
            "total": len(evidence_rows),
            "evaluation": len(eval_ev),
            "other": len(other_ev),
        },
        "other_top_queries": [[q, n] for q, n in other_top],
    }


def _build_distribution(eval_rows: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    """评测流量在若干 `values` 字段上的取值分布。"""
    return {
        key: summarize_by_key(eval_rows, key)
        for key in (
            "retrieval_layer",
            "route_type",
            "use_rerank",
            "rerank_used",
            "decomposed",
            "classifier_source",
        )
    }


def _build_evidence_block(evidence_rows: list[dict[str, Any]]) -> dict[str, Any]:
    """证据层聚合：语义缓存命中率 + 判定 / 重试分布。"""
    cache_hits = [
        1.0 if r["values"].get("semantic_cache_hit") else 0.0
        for r in evidence_rows
        if "semantic_cache_hit" in r["values"]
    ]
    return {
        "semantic_cache_hit_rate": round(mean(cache_hits), 4) if cache_hits else None,
        "semantic_cache_samples": len(cache_hits),
        "verifier_used": summarize_by_key(evidence_rows, "verifier_used"),
        "evidence_verdict": summarize_by_key(evidence_rows, "evidence_verdict"),
        # ★ 读 `hard_fail` 占比前必须同时看 `retry_count`：本字段只反映**该次**
        # 证据事件的判定，不反映「治理层是否随后重试成功」。实测 retry_count 全为 0，
        # 说明重试另走路径 —— 所以 hard_fail 占比**不能**直接读成「16% 的查询失败」。
        "retry_count": summarize_by_key(evidence_rows, "retry_count"),
    }


def build_report(
    scan: dict[str, Any],
    query_index: dict[str, dict[str, str]],
    log_path: Path,
    golden: list[str],
    window: dict[str, str | None] | None = None,
) -> dict[str, Any]:
    """把扫描结果整理成报表字典（自描述：口径全部写进 `_meta`）。"""
    query_rows: list[dict[str, Any]] = scan["query_rows"]
    evidence_rows: list[dict[str, Any]] = scan["evidence_rows"]
    eval_rows, other_rows = split_traffic(query_rows, query_index)
    eval_ev, other_ev = split_traffic(evidence_rows, query_index)

    by_type = _group_by_type(eval_rows, query_index)
    funnel: dict[str, Any] = {name: summarize_funnel(by_type.get(name, [])) for name in QUERY_TYPES}
    funnel["_all_eval"] = summarize_funnel(eval_rows)
    other_top = Counter(r["query_preview"] for r in other_rows).most_common(10)

    return {
        "_meta": _build_meta(scan, log_path, golden, query_index, window),
        "event_counts": dict(Counter(scan["event_counts"]).most_common()),
        "traffic_split": _build_traffic_split(
            query_rows, eval_rows, other_rows, evidence_rows, eval_ev, other_ev, other_top
        ),
        "funnel_by_query_type": funnel,
        "threshold_by_query_type": _build_thresholds(by_type),
        "distribution": _build_distribution(eval_rows),
        "evidence": _build_evidence_block(evidence_rows),
        "ingest": build_ingest_summary(scan["ingest_rows"]),
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="遥测报表：把 rag_metrics.jsonl 聚合成人可读报表")
    parser.add_argument("--log", default=str(DEFAULT_METRICS_PATH), help="遥测日志 jsonl 路径")
    parser.add_argument(
        "--golden",
        action="append",
        default=None,
        help=f"黄金集 jsonl（可重复；默认 {DEFAULT_GOLDEN_PATH} 与 {DEFAULT_PAIRED_PATH}）",
    )
    parser.add_argument("--output", default=None, help="把 JSON 报表写到该路径（父目录会自动创建）")
    parser.add_argument(
        "--since",
        default=None,
        help="只统计该时刻之后的记录。ISO-8601（无时区按本机时区）或相对量如 6h / 3d；"
        "相对量的锚点是日志最新一条事件，不是「现在」",
    )
    parser.add_argument("--until", default=None, help="只统计该时刻之前的记录（格式同 --since）")
    parser.add_argument("--json", action="store_true", help="打印 JSON 而不是表格")
    parser.add_argument("--verbose", action="store_true")
    return parser


def _resolve_time_window(
    args: argparse.Namespace, anchor: datetime
) -> tuple[dict[str, Any], datetime | None, datetime | None]:
    """解析 ``--since`` / ``--until`` → ``(window 描述, since, until)``；非法值抛 ValueError。"""
    since = parse_when(args.since, anchor) if args.since else None
    until = parse_when(args.until, anchor) if args.until else None
    window: dict[str, Any] = {
        "since": since.isoformat() if since else None,
        "until": until.isoformat() if until else None,
        "filtered": bool(since or until),
        "anchor": anchor.isoformat(),
    }
    return window, since, until


def _write_report(report: dict[str, Any], output: str) -> None:
    """把 JSON 报表落盘（父目录自动创建），并打印路径。"""
    out_path = Path(output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"报表已写入: {out_path}")


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )

    log_path = Path(args.log)
    if not log_path.exists():
        print(f"[错误] 遥测日志不存在: {log_path}", file=sys.stderr)
        print(
            "       提示：它由 rag.common.metrics 在检索/入库时写入；本机没跑过就没有。",
            file=sys.stderr,
        )
        return 2

    golden = args.golden or [DEFAULT_GOLDEN_PATH, DEFAULT_PAIRED_PATH]
    query_index = load_query_index(golden)
    if not query_index:
        print(f"[错误] 未能从 {golden} 读到任何 query —— join key 不可用", file=sys.stderr)
        return 2

    scan = scan_log(log_path)

    # 相对时间量的锚点 = 日志里最新的一条事件（不是「现在」，见 `parse_when`）。
    anchor = _latest_ts(scan)
    try:
        window, since, until = _resolve_time_window(args, anchor)
    except ValueError as exc:
        print(f"[错误] 无法解析时间参数: {exc}", file=sys.stderr)
        return 2
    for key in ("query_rows", "evidence_rows", "ingest_rows"):
        scan[key] = filter_rows_by_time(scan[key], since, until)

    report = build_report(scan, query_index, log_path, golden, window)

    if args.output:
        _write_report(report, args.output)

    print(json.dumps(report, ensure_ascii=False, indent=2) if args.json else format_report(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
