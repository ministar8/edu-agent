from __future__ import annotations

import json
import logging
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
# `evaluation.telemetry_report` 把它当作默认输入。两份各写一遍这个表达式迟早漂移，
# 而漂移的表现是「报表读到的是另一份日志」，**不报错、只是数字变了**。
DEFAULT_METRICS_PATH = (
    Path(__file__).resolve().parents[2] / "data" / "metrics" / "rag_metrics.jsonl"
)


class MetricsWriter:
    def __init__(self, output_path: Path | None = None) -> None:
        self._output_path = output_path or DEFAULT_METRICS_PATH
        self._lock = threading.Lock()
        self._output_path.parent.mkdir(parents=True, exist_ok=True)

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
        line = json.dumps(payload, ensure_ascii=False)
        try:
            with self._lock:
                with self._output_path.open("a", encoding="utf-8") as f:
                    f.write(line + "\n")
        except Exception as e:
            logger.debug("metrics write failed: %s", e)
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
