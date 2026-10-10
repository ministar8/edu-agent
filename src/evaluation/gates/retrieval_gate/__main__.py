"""`python -m evaluation.gates.retrieval_gate` 入口。"""

from __future__ import annotations

import sys

from ._gate import main

if __name__ == "__main__":
    sys.exit(main())
