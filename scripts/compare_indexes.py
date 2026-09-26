"""两份索引的检索层对照（零 LLM 成本），用于决定「保留哪一份」。

口径：20 条配对样本（evals/ragas_paired20.jsonl），
按生产配置（RERANK_ENABLED=false）跑检索，只比较检索层可算的指标：
  - chapter_hit@5：top-5 证据里是否出现「期望章节文件」
  - first_hit_rank：首个命中期望章节的排名（越小越好，未命中记 ∞）
  - mean_evidence_count：平均证据条数

为什么用「章节文件」当判据：`metadata.knowledge_points` 就是章级标签，
且约定为 `knowledge/**/*.md` 的文件名（去两位编号前缀）。
"""

from __future__ import annotations

import asyncio
import json
import re
import sys
from pathlib import Path

ROOT = Path(r"C:/Users/26452/Desktop/edu-agent")
PAIRED = ROOT / "evals/ragas_paired20.jsonl"

_PREFIX = re.compile(r"^\d+_")


def chapter_of(source_file: str) -> str:
    stem = Path(str(source_file)).stem
    return _PREFIX.sub("", stem)


def load_samples() -> list[dict]:
    out = []
    for line in PAIRED.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        out.append(json.loads(line))
    return out


async def run() -> None:
    label = sys.argv[1] if len(sys.argv) > 1 else "?"
    from rag.retriever import aretrieve_evidence_with_retry

    samples = load_samples()
    hit = 0
    rank_sum = 0.0
    n = 0
    ev_sum = 0

    for s in samples:
        kps = set(s["metadata"].get("knowledge_points") or [])
        if not kps:
            continue
        n += 1
        try:
            fused, _ = await aretrieve_evidence_with_retry(
                query=s["query"], k=5, use_rerank=True, max_retries=0, use_llm_verify=False
            )
        except Exception as exc:  # noqa: BLE001
            print(f"  [ERR] {s['query'][:30]} {type(exc).__name__}")
            continue
        ev_sum += len(fused.text_evidences)
        first = None
        for i, ev in enumerate(fused.text_evidences, 1):
            if chapter_of(ev.source) in kps:
                first = i
                break
        if first is not None:
            hit += 1
            rank_sum += 1.0 / first  # MRR 形式
        else:
            rank_sum += 0.0

    print(f"##### {label}")
    print(
        f"  n={n}  chapter_hit@5={hit / n:.4f}  chapter_MRR={rank_sum / n:.4f}"
        f"  mean_evidence_count={ev_sum / n:.3f}"
    )


if __name__ == "__main__":
    asyncio.run(run())
