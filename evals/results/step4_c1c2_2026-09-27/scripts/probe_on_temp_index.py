"""在「临时索引 + 就绪屏障」上跑 probe 表，得到**可信**的 dropped_by。

为什么不用 candidate_trace 的默认路径：它直接查生产 `chroma_db/`，**没有就绪屏障**，
会间歇性撞 Chroma「Nothing found on disk」，表现为召回池条数在两次运行间漂移
（2026-09-27 Step 3 实测 before 13 次 / after 9 次）。

本脚本复用 `retrieval_gate` 的建索引 + 就绪屏障，再用 `candidate_trace` 的追踪器。

用法：
  GATE_USE_REAL_EMBEDDING=1 GATE_RERANK_MODE=on GATE_USE_REAL_RERANK=1 \
    PYTHONPATH=src .venv/Scripts/python.exe probe_on_temp_index.py
"""

from __future__ import annotations

import asyncio
import tempfile

from evaluation import retrieval_gate as G


def main() -> None:
    tmp = tempfile.mkdtemp(prefix="probe_tmpidx_")
    G.configure_for_gate(tmp)
    counts = G.build_index()
    total = sum(counts.values())
    print(f"索引就绪: {total} chunks  {counts}", flush=True)
    G.wait_for_index_ready(sorted(counts))
    print(
        f"路由: embed={G.embedding_mode()} rerank={G.rerank_mode()} backend={G.rerank_backend()}",
        flush=True,
    )
    print()

    from evaluation.candidate_trace import load_probes, trace_probe
    from rag.recall import _infer_subject_collections

    for p in load_probes("evals/retrieval_probes.jsonl"):
        inferred = _infer_subject_collections(p.query)
        r = asyncio.run(trace_probe(p, k=5, use_rerank=True))
        chain = " -> ".join(
            f"{s.label}={s.rank if s.rank is not None else '缺'}({s.count})" for s in r.stages
        )
        print(f"#{p.id}  推断集合 = {inferred or '[]（空 ⇒ 回退全 4 科）'}")
        print(f"      {chain}")
        print(f"      dropped_by = {r.dropped_by}")
        print()


if __name__ == "__main__":
    main()
