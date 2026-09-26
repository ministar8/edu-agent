"""隔离实验：关掉 B2（窗口填充合并回锚点）后跑门禁，用于判定 mean_evidence_count
与 cat_* 的下降到底是不是 B2 造成的。

做法：把 `rag.retriever.merge_window_into_anchors` 换成恒等函数。
`_stage_expand_windows` 引用的是模块全局名，故替换即生效（与 candidate_trace 同手法）。
"""

from __future__ import annotations

import sys


def main() -> int:
    import rag.retriever as R

    R.merge_window_into_anchors = lambda docs: docs  # 关闭 B2

    from evaluation.retrieval_gate import main as gate_main

    return gate_main(sys.argv[1:])


if __name__ == "__main__":
    raise SystemExit(main())
