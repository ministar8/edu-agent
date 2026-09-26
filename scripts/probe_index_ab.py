"""S3 预检：同代码、同参数，只换索引目录，比较四条 probe 的检索结果。

目的：回答「2ef8013 的 splitter 代码锚点修复（此前从未进入过索引）是否已解决 #18 / #17」。
若已解决，则 S5（A2 候选侧）可销项；若未解决，才需要改 rerank 期文本。
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

ROOT = Path(r"C:/Users/26452/Desktop/edu-agent")
DETAILS = ROOT / "evals/results/ragas_baseline20_qwen37_flash_details.json"

PROBE_INDEX = (4, 9, 17, 18)


def load_probes() -> list[tuple[int, str]]:
    items = json.loads(DETAILS.read_text(encoding="utf-8"))["details"]
    by_index = {it["index"]: it["query"] for it in items}
    return [(i, by_index[i]) for i in PROBE_INDEX]


async def main() -> None:
    label = sys.argv[1] if len(sys.argv) > 1 else "?"
    from rag.retriever import aretrieve_evidence_with_retry

    print(f"########## 索引={label}  (CHROMA_PERSIST_DIR={os.environ.get('CHROMA_PERSIST_DIR')})")
    for idx, query in load_probes():
        try:
            fused, _ = await aretrieve_evidence_with_retry(
                query=query, k=5, use_rerank=True, max_retries=0, use_llm_verify=False
            )
        except Exception as exc:  # noqa: BLE001
            print(f"--- #{idx} {query}\n    ERROR {type(exc).__name__}: {exc}")
            continue
        print(f"--- #{idx} {query}  (证据 {len(fused.text_evidences)} 条)")
        for ev in fused.text_evidences:
            rr = f"{ev.rerank_score:.4f}" if ev.rerank_score else "0"
            print(f"    rr={rr:<8} {ev.source} | {ev.section_path[:64]}")


if __name__ == "__main__":
    asyncio.run(main())
