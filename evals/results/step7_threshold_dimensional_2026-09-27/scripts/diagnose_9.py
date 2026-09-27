"""诊断 #9：目标 chunk 的 RRF 融合分 vs 有效阈值，以及它被哪些路由命中。

跑在临时索引 + 就绪屏障上（避免生产索引的 Chroma 竞态）。

用法：
  GATE_USE_REAL_EMBEDDING=1 GATE_RERANK_MODE=off \
    PYTHONPATH=src .venv/Scripts/python.exe diagnose_9.py
（用 rerank=off，因为重排发生在阈值之后，与本题无关。）
"""

from __future__ import annotations

import asyncio
import tempfile

from evaluation import retrieval_gate as G

QUERY = "请出一道考查磁盘空闲空间管理的题。"
EXPECT_SOURCE = "04_文件管理.md"
EXPECT_SECTION = "空闲"


def main() -> None:
    tmp = tempfile.mkdtemp(prefix="diag9_tmpidx_")
    G.configure_for_gate(tmp)
    counts = G.build_index()
    G.wait_for_index_ready(sorted(counts))
    print(f"索引 {sum(counts.values())} chunks | embed={G.embedding_mode()} "
          f"rerank={G.rerank_mode()}", flush=True)
    print()

    import rag.retriever as R
    from rag.postprocess import dedup_same_section as _orig_dedup

    recorded: dict[str, list] = {}

    def spy(results, *a, **kw):
        out = _orig_dedup(results, *a, **kw)
        recorded["deduped"] = out
        return out

    R.dedup_same_section = spy

    # 计划阶段：拿阈值
    plan_box: dict = {}
    orig_plan = R._stage_resolve_plan

    def plan_spy(*a, **kw):
        out = orig_plan(*a, **kw)
        plan_box.update(
            effective_threshold=float(out.effective_threshold),
            k=int(out.k),
            coarse_k=int(out.coarse_k),
            depth=str(out.depth.depth),
            layer=str(out.retrieval_layer),
        )
        return out

    R._stage_resolve_plan = plan_spy

    docs = asyncio.run(R.aretrieve_documents(QUERY, k=5, use_rerank=False))

    deduped = recorded.get("deduped") or []
    thr = plan_box.get("effective_threshold")
    print(f"query        : {QUERY}")
    print(f"计划         : k={plan_box.get('k')} coarse_k={plan_box.get('coarse_k')} "
          f"层={plan_box.get('layer')} depth={plan_box.get('depth')}")
    print(f"有效阈值     : {thr}")
    print(f"去重后候选   : {len(deduped)} 条")
    if deduped:
        print(f"最高分       : {max(s for _, s in deduped):.4f}")
        print(f"过阈值条数   : {sum(1 for _, s in deduped if s >= thr)}")
    print()

    def matches(doc) -> bool:
        m = doc.metadata or {}
        src = str(m.get("source_file") or m.get("source") or "")
        sec = str(m.get("section.path") or m.get("heading_path") or "")
        return EXPECT_SOURCE in src and EXPECT_SECTION in sec

    hit = [(i, d, s) for i, (d, s) in enumerate(deduped, 1) if matches(d)]
    if not hit:
        print("目标不在去重后的候选里")
    for rank, doc, score in hit:
        m = doc.metadata or {}
        print(f"★ 目标在去重后 rank {rank}，RRF 分 = {score:.4f}"
              f"（阈值 {thr:.4f}，差 {score - thr:+.4f}）")
        print(f"   source  : {m.get('source_file')}")
        print(f"   section : {m.get('section.path')}")
        print(f"   routes  : {m.get('recall_routes')}")
    print()
    print("前 6 名的分数与命中路由：")
    for i, (d, s) in enumerate(deduped[:6], 1):
        m = d.metadata or {}
        print(f"  {i}. {s:.4f}  {m.get('source_file')} :: "
              f"{str(m.get('section.path'))[:40]}  routes={m.get('recall_routes')}")


if __name__ == "__main__":
    main()
