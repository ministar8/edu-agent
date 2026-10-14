from __future__ import annotations

import json
import logging
import os
import threading
import time
from contextlib import AbstractContextManager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class MetricsTimer(AbstractContextManager):
    def __init__(
        self, writer: MetricsWriter, event: str, stage: str, tags: dict[str, Any] | None = None
    ):
        self._writer = writer
        self._event = event
        self._stage = stage
        self._tags = dict(tags or {})
        self._values: dict[str, Any] = {}
        self._status = "ok"
        self._start = 0.0

    def __enter__(self) -> MetricsTimer:
        self._start = time.perf_counter()
        return self

    def set(self, key: str, value: Any) -> None:
        self._values[key] = value

    def update(self, values: dict[str, Any]) -> None:
        self._values.update(values)

    def fail(self, error: BaseException | str) -> None:
        self._status = "error"
        self._values["error_type"] = (
            error.__class__.__name__ if isinstance(error, BaseException) else str(error)
        )

    def __exit__(self, exc_type, exc, exc_tb) -> bool:
        if exc is not None:
            self.fail(exc)
        duration_ms = round((time.perf_counter() - self._start) * 1000, 3)
        self._writer.emit(
            event=self._event,
            stage=self._stage,
            status=self._status,
            duration_ms=duration_ms,
            tags=self._tags,
            values=self._values,
        )
        return False


# 遥测日志的默认落盘位置。★ 这里是**唯一**的定义处 ——
# `evaluation.diagnostics.telemetry_report` 把它当作默认输入。两份各写一遍这个表达式迟早漂移，
# 而漂移的表现是「报表读到的是另一份日志」，**不报错、只是数字变了**。
# ★ parents[3]：本文件在 `src/rag/common/` 下 ⇒ parents[2]=`src`、parents[3]=仓根。
#   落盘位置应为**仓根** `data/metrics/`（与 `telemetry_report` 文档串、`.gitignore` 的 `data/` 一致）；
#   若误用 parents[2] 会静默改写到 `src/data/`。
DEFAULT_METRICS_PATH = (
    Path(__file__).resolve().parents[3] / "data" / "metrics" / "rag_metrics.jsonl"
)


# ── 高频「簿记」事件的采样 ────────────────────────────────────────────
# 这三个 (event, stage) 在全仓没有任何明细读方：`telemetry_report.scan_log` 只数条数、
# 明细直接丢（见其 docstring）。实测本机 2026-10-10→10-14 窗口（**追溯整理之前**的那份日志，
# 原件见 `../edu-agent-eval-archive/telemetry/rag_metrics_live_20261014_before_sampling_trim.jsonl.gz`）
# 它们占 **44.28% 行数 / 31.01% 字节数**（`chroma_query` 28.50% + `embedding_batch` 8.41% +
# `embed_documents` 7.36%，其中 `chroma_query` 单类就 13.5 万行）。全量写盘换来的
# 只是日志变成磁盘负债，所以每 N 条留 1 条。★ 别拿当前活文件复算这组百分比 ——
# 那段历史已按同一规则削过，复算要回上面那个 gz。
_TELEMETRY_SAMPLE_EVERY: dict[tuple[str, str], int] = {
    ("chroma_query", "vectorstore"): 100,
    ("embedding_batch", "embeddings"): 100,
    ("embed_documents", "embeddings"): 100,
}
# ★ `split_documents` **刻意不进本表**（写侧仍全量）：它占整理前日志 44.3% 行数、是最大的一类，
#   但只在入库切分时发射（`rag.chunking.splitter`），而入库是低频运维动作、不是问答路径。
#   2026-10-14 项目所有者裁定「今后入库不会很频繁」⇒ 不为它加写侧采样，只对 10-10→10-14 那段
#   历史做了追溯整理（1/100，见 `../edu-agent-eval-archive/telemetry/MANIFEST.json` 的
#   `sampling_trim_2026-10-14`）。★ 重审触发条件：入库变成批量/频繁操作（如全量重建进日常流程）、
#   或 `data/metrics/` 体积再次异常增长时，回来把它补进表里。

# ★ 采样只削 `status == "ok"`：同一窗口里 `chroma_query` 有 2,852 条 `status == "error"`、
#   `embedding_batch` 有 129 条。错误记录是「向量库读失败」的唯一现场证据，
#   按 1/100 削掉它们会把故障样本一起削成 28 条。
_OK_STATUS = "ok"

# 覆写表里所有规则的倍率（`1` = 全量捕获，复现/消融用）。非法值退回表值。
_SAMPLE_EVERY_ENV = "METRICS_SAMPLE_EVERY"


def _read_rate_override() -> int | None:
    raw = os.environ.get(_SAMPLE_EVERY_ENV)
    if raw is None:
        return None
    try:
        return max(1, int(raw))
    except ValueError:
        logger.warning("%s=%r 不是整数，改用表内采样倍率", _SAMPLE_EVERY_ENV, raw)
        return None


class MetricsWriter:
    def __init__(self, output_path: Path | None = None) -> None:
        self._output_path = output_path or DEFAULT_METRICS_PATH
        self._lock = threading.Lock()
        self._output_path.parent.mkdir(parents=True, exist_ok=True)
        # 延迟到首条事件才解析（见 `_sampling_rates`），None = 尚未解析。
        self._sampling_table: dict[tuple[str, str], int] | None = None
        self._sample_counts: dict[tuple[str, str], int] = {}

    def _sampling_rates(self) -> dict[tuple[str, str], int]:
        """倍率表。★ 必须**惰性**解析：`metrics` 单例在本模块导入期就构造，
        而 `METRICS_SAMPLE_EVERY` 是 `core.settings` 在**它自己被导入时**才导出进
        `os.environ` 的（pydantic-settings 读 dotenv 并不写回环境）。构造时读环境
        就可能早于那次导出，于是 `.env` 里配的倍率被静默忽略。
        """
        if self._sampling_table is None:
            override = _read_rate_override()
            self._sampling_table = (
                _TELEMETRY_SAMPLE_EVERY
                if override is None
                else {key: override for key in _TELEMETRY_SAMPLE_EVERY}
            )
        return self._sampling_table

    def _sampling_factor(self, event: str, stage: str, status: str) -> int:
        """0 = 丢弃本条；1 = 原样写；N>1 = 原样写并标注「这一条代表 N 条」。

        ★ 调用方必须持锁：`self._sample_counts` 跨线程共享，边计数边写盘才不会出现
        「两条都留」或「两条都丢」。
        """
        every = self._sampling_rates().get((event, stage), 1)
        if every <= 1 or status != _OK_STATUS:
            return 1
        count = self._sample_counts.get((event, stage), 0) + 1
        self._sample_counts[(event, stage)] = count
        return 0 if count % every else every

    def emit(
        self,
        *,
        event: str,
        stage: str,
        status: str = "ok",
        duration_ms: float | None = None,
        tags: dict[str, Any] | None = None,
        values: dict[str, Any] | None = None,
    ) -> None:
        payload = {
            "ts": datetime.now(UTC).isoformat(),
            "event": event,
            "stage": stage,
            "status": status,
            "duration_ms": duration_ms,
            "tags": self._sanitize(tags or {}),
            "values": self._sanitize(values or {}),
        }
        line: str | None = None
        try:
            with self._lock:
                factor = self._sampling_factor(event, stage, status)
                if factor == 0:
                    return
                if factor > 1:
                    payload["sampled_every"] = factor
                line = json.dumps(payload, ensure_ascii=False)
                with self._output_path.open("a", encoding="utf-8") as f:
                    f.write(line + "\n")
        except Exception as e:
            logger.debug("metrics write failed: %s", e)
        if line is not None:
            logger.debug("METRIC %s", line)

    def timer(self, event: str, stage: str, tags: dict[str, Any] | None = None) -> MetricsTimer:
        return MetricsTimer(self, event=event, stage=stage, tags=tags)

    def emit_ingest_file_summary(
        self,
        *,
        file: str,
        category: str,
        elapsed_ms: float,
        values: dict[str, Any] | None = None,
        status: str = "ok",
    ) -> None:
        tags = {"file": file, "category": category}
        self.emit(
            event="ingest_file_summary",
            stage="ingest",
            status=status,
            duration_ms=elapsed_ms,
            tags=tags,
            values=values,
        )

    def emit_retrieve_summary(
        self,
        *,
        query: str,
        collection: str,
        duration_ms: float | None = None,
        values: dict[str, Any] | None = None,
        status: str = "ok",
    ) -> None:
        tags = {"collection": collection, "query_preview": query[:120], "query_len": len(query)}
        self.emit(
            event="retrieve_query",
            stage="retriever",
            status=status,
            duration_ms=duration_ms,
            tags=tags,
            values=values,
        )

    def emit_evidence_summary(
        self,
        *,
        query: str,
        collection: str,
        duration_ms: float | None = None,
        values: dict[str, Any] | None = None,
        status: str = "ok",
    ) -> None:
        tags = {"collection": collection, "query_preview": query[:120], "query_len": len(query)}
        self.emit(
            event="retrieve_evidence",
            stage="evidence",
            status=status,
            duration_ms=duration_ms,
            tags=tags,
            values=values,
        )

    def _sanitize(self, data: dict[str, Any]) -> dict[str, Any]:
        return {str(k): self._sanitize_value(v) for k, v in data.items()}

    def _sanitize_value(self, value: Any) -> Any:
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, Path):
            return str(value)
        if isinstance(value, dict):
            return {str(k): self._sanitize_value(v) for k, v in value.items()}
        if isinstance(value, (list, tuple, set)):
            return [self._sanitize_value(v) for v in value]
        return str(value)


metrics = MetricsWriter()


# ── 查询分解统计 ──────────────────────────────────────────
