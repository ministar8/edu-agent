"""telemetry_report 的共享常量（从 telemetry_report.py 拆出，行为等价）。"""

from __future__ import annotations

DEFAULT_GOLDEN_PATH = "evals/datasets/golden/sample_408.jsonl"
DEFAULT_PAIRED_PATH = "evals/datasets/ragas/ragas_paired20.jsonl"

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
