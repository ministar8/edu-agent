"""task_eval：Phase 0 任务级效果评测（QA / Generate / Grade / Verify / Memory）。

与 `agent_behavior_gate.py` 的分工（决策 #2：职责不混）：
- gate     → 「有没有越过安全/行为边界？」（PASS / FAIL）
- task_eval→ 「这个系统到底答得好不好？」（rubric / metrics）

用法::

    PYTHONPATH=src uv run python -m evaluation.task_eval run --limit 3        # 0A smoke
    PYTHONPATH=src uv run python -m evaluation.task_eval run --task qa        # 单任务
    PYTHONPATH=src uv run python -m evaluation.task_eval run --no-agent       # 只跑检索探针
    PYTHONPATH=src uv run python -m evaluation.task_eval calibrate --input <path>
"""

from __future__ import annotations

from evaluation.task_eval.cases import TaskCase, load_cases, load_demo
from evaluation.task_eval.runner import CaseRecord, dump_records, run_case

__all__ = [
    "CaseRecord",
    "TaskCase",
    "dump_records",
    "load_cases",
    "load_demo",
    "run_case",
]
