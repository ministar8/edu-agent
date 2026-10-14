"""采样之后，报表的「条数」必须同时给出观测值和还原值。

`event_counts` 原本等于「发生了多少次」；采样后它等于「日志里有多少行」。
留着这个键名却悄悄改口径，正是本仓最忌讳的那类漂移 —— 所以 `scan_log` 必须另给
一份按记录自带的 `sampled_every` 乘回来的 `event_counts_estimated`。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from evaluation.diagnostics._telemetry_format import _fmt_header
from evaluation.diagnostics.telemetry_report import build_report, scan_log
from rag.common.metrics import MetricsWriter


@pytest.fixture
def sampled_log(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """用**真实 writer** 造日志（不手写 JSON），这样这条测试同时钉住写侧和读侧。"""
    monkeypatch.delenv("METRICS_SAMPLE_EVERY", raising=False)
    path = tmp_path / "rag_metrics.jsonl"
    writer = MetricsWriter(path)
    for _ in range(300):
        writer.emit(event="chroma_query", stage="vectorstore", status="ok")
    for _ in range(5):
        writer.emit(event="chroma_query", stage="vectorstore", status="error")
    for _ in range(20):
        writer.emit(event="retrieve_query", stage="retriever", status="ok")
    return path


def test_event_counts_stays_the_observed_line_count(sampled_log: Path) -> None:
    scan = scan_log(sampled_log)

    assert scan["event_counts"] == {"chroma_query": 8, "retrieve_query": 20}


def test_estimated_counts_restore_the_sampling_factor(sampled_log: Path) -> None:
    """3 条 ok 各代表 100 次，5 条 error 全量保留 ⇒ 305，而不是 8。"""
    scan = scan_log(sampled_log)

    assert scan["event_counts_estimated"] == {"chroma_query": 305, "retrieve_query": 20}


def test_unsampled_log_reports_identical_counts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """采样前的历史日志（没有任何 `sampled_every` 标注）里两份数字必须相等 ——
    否则读一份旧归档会得到凭空的放大。"""
    monkeypatch.delenv("METRICS_SAMPLE_EVERY", raising=False)
    path = tmp_path / "rag_metrics.jsonl"
    writer = MetricsWriter(path)
    for _ in range(7):
        writer.emit(event="retrieve_evidence", stage="evidence", status="ok")

    scan = scan_log(path)

    assert scan["event_counts"] == scan["event_counts_estimated"] == {"retrieve_evidence": 7}


def test_estimated_count_is_a_lower_bound_by_the_partial_cycle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """特征化测试（写出来就是绿的）：钉住模 N 计数的**固有下界**，
    免得以后有人把 `event_counts_estimated` 「修」成看上去精确的值 —— 那不是
    每 N 留 1 条能做到的事。250 条 ok 留 2 条 ⇒ 还原值只能是 200，缺的 50 条
    是最后一个不满周期，只有未采样的原始日志里才有。
    """
    monkeypatch.delenv("METRICS_SAMPLE_EVERY", raising=False)
    path = tmp_path / "rag_metrics.jsonl"
    writer = MetricsWriter(path)
    for _ in range(250):
        writer.emit(event="chroma_query", stage="vectorstore", status="ok")

    scan = scan_log(path)

    assert scan["event_counts"]["chroma_query"] == 2
    assert scan["event_counts_estimated"]["chroma_query"] == 200
    assert 0 < 250 - scan["event_counts_estimated"]["chroma_query"] < 100


def test_report_publishes_both_counts_and_the_annotated_line_count(sampled_log: Path) -> None:
    """算出来却没进报表 = 没人能看到。两份数字都要在顶层，
    `_meta.sampled_records` 说明「这份日志有多少行带采样标注」——
    读一份采样前/后混着的归档时，它和「两份计数是否相等」一起构成口径判据。
    """
    report = build_report(scan_log(sampled_log), {}, sampled_log, ["-"])

    assert report["event_counts"] == {"chroma_query": 8, "retrieve_query": 20}
    assert report["event_counts_estimated"] == {"chroma_query": 305, "retrieve_query": 20}
    assert report["_meta"]["sampled_records"] == 3


def test_text_header_states_the_sampling_caveat() -> None:
    """人读的是表，不是 JSON。抬头的口径警示与 `时间窗口 未过滤 ⚠` 同级 ——
    只在真的采过样时才出现，免得在没有标注的旧归档上制造疑心。
    """
    meta = {
        "log_path": "x.jsonl",
        "log_lines": 10,
        "log_bytes": 1000,
        "bad_lines": 0,
        "time_span": ["a", "b"],
        "window": {"filtered": False},
    }

    assert "采样" not in "".join(_fmt_header({**meta, "sampled_records": 0}))
    header = "".join(_fmt_header({**meta, "sampled_records": 3}))
    assert "3 行" in header and "event_counts_estimated" in header
