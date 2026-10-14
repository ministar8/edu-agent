"""遥测高频「簿记」事件的采样行为。

这些事件没有任何下游读方（`telemetry_report.scan_log` 只数条数）。2026-10-10→10-14 那段
日志在**追溯整理之前**占 44% 行数 / 31% 字节数（整理前的原件见仓外备份 gz）。
采样必须同时满足三条，缺一不可：
① 按比例削；② `status != "ok"` 的记录一条都不能削（错误证据是它们唯一的用途）；
③ 留下的记录要自带采样倍率，否则条数就从测量值变成了估计值却没人说明。
"""

from __future__ import annotations

import importlib
import json
import os
from pathlib import Path
from typing import Any

import pytest

from rag.common.metrics import MetricsWriter

# `core/__init__.py` 把 `settings` **实例**绑定成了同名属性，`from core import settings`
# 拿到的是实例而不是模块 ⇒ 要 reload 模块级导出，只能用 import_module 取模块对象。
SETTINGS_MODULE = importlib.import_module("core.settings")

SAMPLED_OK = {"event": "chroma_query", "stage": "vectorstore", "status": "ok"}
UNSAMPLED_OK = {"event": "retrieve_query", "stage": "retriever", "status": "ok"}


def _log_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, rate: str | None = None) -> Path:
    """设好采样倍率的环境，返回一个尚未创建的日志路径（writer 由各用例自己建）。"""
    if rate is None:
        monkeypatch.delenv("METRICS_SAMPLE_EVERY", raising=False)
    else:
        monkeypatch.setenv("METRICS_SAMPLE_EVERY", rate)
    return tmp_path / "rag_metrics.jsonl"


def _emit_many(writer: MetricsWriter, n: int, **kwargs: Any) -> None:
    for i in range(n):
        writer.emit(**kwargs, values={"i": i})


def _records(path: Path) -> list[dict[str, Any]]:
    """日志按追加写创建，所以「一条都没留」= 文件不存在，与空文件同义
    （`telemetry_report` 对缺失日志也是这么处理的）。
    """
    if not path.exists():
        return []
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def test_ok_records_of_sampled_events_are_kept_one_in_n(tmp_path: Path, monkeypatch) -> None:
    path = _log_path(tmp_path, monkeypatch)
    _emit_many(MetricsWriter(path), 300, **SAMPLED_OK)

    records = _records(path)
    assert len(records) == 3
    assert all(rec["sampled_every"] == 100 for rec in records)


def test_error_records_are_never_sampled(tmp_path: Path, monkeypatch) -> None:
    """削掉错误记录等于削掉故障现场 —— 采样只对 `status == "ok"` 生效。"""
    path = _log_path(tmp_path, monkeypatch)
    writer = MetricsWriter(path)
    for _ in range(300):
        writer.emit(event="chroma_query", stage="vectorstore", status="error")

    records = _records(path)
    assert len(records) == 300
    assert all("sampled_every" not in rec for rec in records)


def test_events_without_a_rule_keep_every_record(tmp_path: Path, monkeypatch) -> None:
    """`retrieve_query` 是报表的实际输入，削它会静默改掉漏斗数字。"""
    path = _log_path(tmp_path, monkeypatch)
    _emit_many(MetricsWriter(path), 300, **UNSAMPLED_OK)

    records = _records(path)
    assert len(records) == 300
    assert all("sampled_every" not in rec for rec in records)


def test_sampling_counters_are_per_event(tmp_path: Path, monkeypatch) -> None:
    """两条规则**共用**一个计数器时，交错写入会让其中一条被饿死。

    交错写 100+100 条：全局第 100、200 次都落在偶数位置（`embedding_batch`）上 ⇒
    共用计数器会得到 `{chroma_query: 0, embedding_batch: 2}`；按 key 计数才是各 1 条。
    ★ 早先这例是「先写完 A 再写 B」，那种顺序下两种实现都给 1:1，断言区分不了 —— 等于没测。
    """
    path = _log_path(tmp_path, monkeypatch)
    writer = MetricsWriter(path)
    for i in range(100):
        writer.emit(**SAMPLED_OK, values={"i": i})
        writer.emit(event="embedding_batch", stage="embeddings", status="ok", values={"i": i})

    counts: dict[str, int] = {}
    for rec in _records(path):
        counts[rec["event"]] = counts.get(rec["event"], 0) + 1
    assert counts == {"chroma_query": 1, "embedding_batch": 1}


def test_env_override_replaces_the_table_rate(tmp_path: Path, monkeypatch) -> None:
    path = _log_path(tmp_path, monkeypatch, rate="10")
    _emit_many(MetricsWriter(path), 100, **SAMPLED_OK)

    records = _records(path)
    assert len(records) == 10
    assert all(rec["sampled_every"] == 10 for rec in records)


def test_env_override_of_one_restores_full_capture(tmp_path: Path, monkeypatch) -> None:
    """复现/消融需要全量日志时能一键关掉采样，而不是改代码。"""
    path = _log_path(tmp_path, monkeypatch, rate="1")
    _emit_many(MetricsWriter(path), 300, **SAMPLED_OK)

    records = _records(path)
    assert len(records) == 300
    assert all("sampled_every" not in rec for rec in records)


def test_invalid_env_value_falls_back_to_the_table_rate(tmp_path: Path, monkeypatch) -> None:
    path = _log_path(tmp_path, monkeypatch, rate="not-a-number")
    _emit_many(MetricsWriter(path), 300, **SAMPLED_OK)

    assert len(_records(path)) == 3


def test_rate_is_resolved_at_first_emit_not_at_construction(tmp_path: Path, monkeypatch) -> None:
    """倍率必须在**首次写事件**时解析，而不是 writer 构造时。

    `metrics` 单例在 `rag.common.metrics` 导入期就构造好了，而 `.env` 的值要靠
    `core.settings` 导入后才被导出进进程环境（见 `test_settings_exports...`）——
    构造时读环境会读到「没有这个变量」。症状是本仓最怕的那类：配了、不报错、行为没变。
    """
    path = _log_path(tmp_path, monkeypatch)
    writer = MetricsWriter(path)
    monkeypatch.setenv("METRICS_SAMPLE_EVERY", "5")
    _emit_many(writer, 50, **SAMPLED_OK)

    assert len(_records(path)) == 10


def test_settings_exports_the_knob_into_process_env() -> None:
    """钉住「导出」这一步 —— 环境里本来没有这个变量，导入 `core.settings` 之后必须有。

    `rag.common.metrics` 只读 `os.environ`（它刻意不 import `core.settings`，连项目模块都不碰，
    以免埋点把配置层的导入期校验拖进主链路），而 pydantic-settings 读 dotenv **不写回**环境 ⇒
    必须由 `core.settings` 导出，否则 `.env.example` 里那行是死的（同一手法见 `export_langsmith_env`）。
    ★ 本用例不复现 dotenv→Settings 那一跳（那是 pydantic 的职责）。早先它先 setenv 再断言
      「环境值 == 字段值」，两边都是同一个 "1" ⇒ 把导出那行删掉它照样绿，等于没测。
    ★ 自己存取环境而不是用 monkeypatch：实测 `monkeypatch.delenv` 对「原本不存在」的变量
      在 undo 时**不会**清掉被测代码新写进去的值，会把倍率泄漏给后面的用例。
    """
    saved = os.environ.pop("METRICS_SAMPLE_EVERY", None)
    try:
        importlib.reload(SETTINGS_MODULE)
        assert os.environ.get("METRICS_SAMPLE_EVERY") == str(
            SETTINGS_MODULE.settings.METRICS_SAMPLE_EVERY
        ), "core.settings 没把采样倍率导出到进程环境 ⇒ `.env` 里配了也不会生效"
    finally:
        os.environ.pop("METRICS_SAMPLE_EVERY", None)
        if saved is not None:
            os.environ["METRICS_SAMPLE_EVERY"] = saved
        assert os.environ.get("METRICS_SAMPLE_EVERY", None) == saved, "环境未复原"


@pytest.mark.parametrize("n,expected", [(1, 0), (99, 0), (100, 1), (250, 2)])
def test_kept_count_is_the_floor_of_emits_over_n(
    tmp_path: Path, monkeypatch, n: int, expected: int
) -> None:
    path = _log_path(tmp_path, monkeypatch)
    _emit_many(MetricsWriter(path), n, **SAMPLED_OK)

    assert len(_records(path)) == expected
