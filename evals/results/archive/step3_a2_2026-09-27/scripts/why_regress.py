"""定位 real/on 上「写 C 代码用位运算交换两个整数」被什么 chunk 顶掉了。

用法：python why_regress.py after|before
"""

from __future__ import annotations

import asyncio
import re
import sys

from core.settings import settings

PHASE = sys.argv[1] if len(sys.argv) > 1 else "after"
Q = "写一段 C 代码用位运算交换两个整数，并说明为什么它未必比使用临时变量更快。"


def summarize(doc) -> str:
    m = doc.metadata or {}
    src = str(m.get("source_file") or m.get("source") or "?")
    sec = str(m.get("section.path") or "")
    sec = sec.rsplit(">", 1)[-1].strip() if ">" in sec else sec
    rs = m.get("rerank_score")
    txt = doc.page_content or ""
    has_fence = ("`" * 3) in txt or ("~" * 3) in txt
    anchored = bool(re.match(r"^\[[^\]]*\]\n", txt))
    return (
        f"{float(rs):.4f}  {src} :: {sec[:34]:<34}"
        f"  代码块={'Y' if has_fence else 'n'} 锚点={'Y' if anchored else 'n'}"
    )


def main() -> None:
    settings.SEMANTIC_CACHE_ENABLED = False
    settings.RERANK_ENABLED = True
    import rag.semantic_cache as sc

    sc._semantic_cache = None

    if PHASE == "before":
        import rag.reranker as RR

        old = re.compile(r"^(?:\[[^\]]*\]\s*(?:>\s*)*)+\n")
        RR._rerank_text = lambda doc: old.sub("", doc.page_content)[:2000]

    import rag.retriever as R
    from evaluation.candidate_trace import _capture

    with _capture() as (events, _plan):
        asyncio.run(R.aretrieve_documents(Q, k=5, use_rerank=True))

    print(f"##### PHASE = {PHASE} #####")
    for key, docs in events:
        if key == "rerank_topn":
            print("  [重排后 top_n 内的文档]")
            for d in docs[:6]:
                print("   ", summarize(d))
            break


if __name__ == "__main__":
    main()
