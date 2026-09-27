"""A2 的 A/B：全 4 条 probe 的逐层名次对比。

用法：python ab_trace.py after|before
  after  = 当前实现（代码 chunk 保留锚点）
  before = 旧实现（无条件剥掉 heading 前缀，用 monkeypatch 复现）

★ 两个相位必须分**独立进程**跑：`_rerank_cache` 是按 (query, docs, top_k) 键的，
  同一进程内跑两遍会命中缓存、把第二轮的结果污染成第一轮的。
"""

from __future__ import annotations

import asyncio
import re
import sys

from core.settings import settings

PHASE = sys.argv[1] if len(sys.argv) > 1 else "after"


def main() -> None:
    settings.SEMANTIC_CACHE_ENABLED = False
    settings.RERANK_ENABLED = True
    import rag.semantic_cache as sc

    sc._semantic_cache = None

    if PHASE == "before":
        import rag.reranker as RR

        old = re.compile(r"^(?:\[[^\]]*\]\s*(?:>\s*)*)+\n")
        RR._rerank_text = lambda doc: old.sub("", doc.page_content)[:2000]

    from evaluation.candidate_trace import load_probes, trace_probe

    probes = load_probes("evals/retrieval_probes.jsonl")
    print(f"##### PHASE = {PHASE} #####")
    for p in probes:
        r = asyncio.run(trace_probe(p, k=5, use_rerank=True))
        chain = " -> ".join(
            f"{s.label}={s.rank if s.rank is not None else '缺'}({s.count})" for s in r.stages
        )
        print(f"#{p.id:<3} dropped_by={r.dropped_by}")
        print(f"     {chain}")
        print()


if __name__ == "__main__":
    main()
