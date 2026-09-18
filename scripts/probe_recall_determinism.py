"""复测 #29：recall 层抖动是否会传到最终输出（backlog #29）。

**为什么做成脚本而不是测试**：这是**跨进程的低频现象**（8 次里 1 次），
写成 CI 测试必然偶发红 —— 那比没有测试更糟（会让人开始忽略门禁）。
所以固化成一个**可手动复查**的脚本，改动检索链后跑一次确认结论仍成立。

用法::

    for i in 1 2 3; do PYTHONPATH=src uv run python scripts/probe_recall_determinism.py; done

判读方式：

- **recall(L3) 签名可能变** —— 这是已知的上游现象（Chroma 近似检索 top-k 边界），
  属 #29 的根因所在，**不是本项目代码的问题**；
- **final 签名必须不变** —— 这是真正要守的契约。
  若 final 也开始变，说明**下游的吸收能力被破坏了**（典型诱因：把候选池放得过宽，
  例如 backlog #34 提的 `limit=max(k*30,300)`，实测会让 precision 变得不确定）。

**两个必须做对的地方**（踩过）：
1. `_raw_search` 的参数顺序是 `(query, collection_name, k, ...)`；
2. **每次调用前清查询缓存** —— 否则第 2 次起直接命中缓存，抖动被完全掩盖。
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import sys
import tempfile

logging.disable(logging.CRITICAL)
os.environ.setdefault("USE_FAKE_MODEL", "true")
os.environ.setdefault("USE_FAKE_EMBEDDING", "true")

from evaluation.retrieval_gate import (  # noqa: E402
    build_index,
    configure_for_gate,
    wait_for_index_ready,
)

CASES = [
    ("operating_system", "栈和队列的主要区别是什么？"),
    ("computer_organization", "什么是流水线冒险？"),
]


def _sig(docs) -> str:
    """稳定签名：只看集合（排序后哈希），不看顺序。"""
    keys = sorted(
        str(getattr(d, "metadata", {}).get("section.chunk_id") or d.page_content[:60]) for d in docs
    )
    return hashlib.md5("|".join(keys).encode()).hexdigest()[:10]


def main() -> int:
    tmp = tempfile.mkdtemp(prefix="recall_det_")
    configure_for_gate(tmp)
    build_index()
    wait_for_index_ready(["operating_system", "computer_organization"])

    from rag.retriever import _query_cache, _raw_search, aretrieve_documents

    for coll, query in CASES:
        _query_cache.clear()
        recall = _sig([d for d, _s in _raw_search(query, coll, 10)])

        _query_cache.clear()
        result = asyncio.run(aretrieve_documents(query, collection_name=coll))
        docs = result[0] if isinstance(result, tuple) else result

        print(f"[{coll}] {query}")
        print(f"  recall(L3): {recall}")
        print(f"  final     : {_sig(docs)}  ({len(docs)} 条)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
