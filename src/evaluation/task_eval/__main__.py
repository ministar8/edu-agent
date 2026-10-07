"""`python -m evaluation.task_eval` 入口。"""

from __future__ import annotations

import sys

from evaluation.task_eval.cli import main

if __name__ == "__main__":
    sys.exit(main())
