"""复核 §3⑥：分解路径 `top_k = k*2` 是否真的会让最终证据超过 k。

跑在**临时索引 + 就绪屏障**上（与 Step 4 的 probe 同法），避免生产索引的 Chroma 竞态。

用法：
  GATE_USE_REAL_EMBEDDING=1 GATE_RERANK_MODE=on GATE_USE_REAL_RERANK=1 \
    PYTHONPATH=src .venv/Scripts/python.exe k_semantics_check.py
"""

from __future__ import annotations

import asyncio
import tempfile

from evaluation import retrieval_gate as G

K = 5

QUERIES: list[tuple[str, str]] = [
    ("L1 短概念", "什么是死锁？"),
    ("L1 短概念", "什么是分页？"),
    ("L2 对比（应分解）", "进程和线程的区别是什么？"),
    ("L2 对比（应分解）", "分页和分段的区别是什么？"),
    ("L3 长结构化", "比较死锁、活锁与饥饿三者的成因、表现与处理方法，并各举一个例子。"),
    ("L2 练习", "请出一道考查磁盘空闲空间管理的题。"),
]


def main() -> None:
    tmp = tempfile.mkdtemp(prefix="k_sem_tmpidx_")
    G.configure_for_gate(tmp)
    counts = G.build_index()
    G.wait_for_index_ready(sorted(counts))
    print(
        f"索引 {sum(counts.values())} chunks | 路由 embed={G.embedding_mode()} "
        f"rerank={G.rerank_mode()}/{G.rerank_backend()} | k={K}",
        flush=True,
    )
    print()

    import rag.retriever as R
    from rag.query_classifier import classify_query
    from rag.rag_utils import extract_query_terms, normalize_query_text

    over = 0
    for label, q in QUERIES:
        cat = classify_query(q, extract_query_terms(normalize_query_text(q)))
        docs = asyncio.run(R.aretrieve_documents(q, k=K, use_rerank=True))
        n = len(docs)
        flag = "  ★ 超过 k" if n > K else ""
        if n > K:
            over += 1
        print(f"{label:18s} k={K} → 返回 {n} 条{flag}")
        print(f"    query: {q[:56]}")
        print(
            f"    cat: exercise={cat.is_exercise} comparison={cat.is_comparison} "
            f"long={cat.is_long} short={cat.is_short} code={cat.is_code}"
        )
        print()

    print(f"结论：{over} / {len(QUERIES)} 条返回条数 > k={K}")


if __name__ == "__main__":
    main()
