"""L3 Exams 入库 + assesses 边 + 回链/负向验收。

构建逻辑已下沉到 ``rag.ingest_layers.exams``；本脚本只做 CLI + 验收。

用法：
    PYTHONPATH=src uv run python scripts/ingest_exams.py 2019
    PYTHONPATH=src uv run python scripts/ingest_exams.py 2019 --verify-only
"""

from __future__ import annotations

import asyncio
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rag.ingest_layers import _shared  # noqa: E402
from rag.ingest_layers import exams as exams_layer  # noqa: E402

LINKS_PATH = _shared.LINKS_PATH
COLLECTION = exams_layer.COLLECTION
ANSWER_IN_BODY_RE = exams_layer.ANSWER_IN_BODY_RE
load_kp_ids = _shared.load_kp_ids


def ingest_year(year: int) -> None:
    exams_layer.ingest_year(year, load_kp_ids())


def test_backlink(year: int) -> list[str]:
    fails: list[str] = []
    kp_ids = load_kp_ids()
    links = [
        json.loads(x) for x in LINKS_PATH.read_text(encoding="utf-8").splitlines() if x.strip()
    ]
    import chromadb

    client = chromadb.PersistentClient(path=str(ROOT / "chroma_db"))
    col = client.get_collection(COLLECTION)
    got = col.get(where={"exam_year": str(year)}, include=["metadatas"])
    metas = got.get("metadatas") or []
    sec_ids = set()
    n_items = n_answers = 0
    seen_chunks: set[str] = set()
    for m in metas:
        cid = m.get("chunk_id") or ""
        sid = m.get("section_id") or ""
        if not cid.startswith(sid):
            fails.append(f"id chain {cid}")
        if cid in seen_chunks:
            fails.append(f"dup chunk_id {cid}")
        seen_chunks.add(cid)
        if m.get("doc_role") == "exam_item":
            n_items += 1
            role = "items"
            if m.get("completeness") not in {"complete", "partial", "incomplete"}:
                fails.append(f"{cid} bad completeness")
        elif m.get("doc_role") == "exam_answer":
            n_answers += 1
            role = "answer"
        else:
            continue
        if f"-{role}-" not in cid:
            fails.append(f"chunk role mismatch {cid}")
        try:
            kps = json.loads(m.get("knowledge_points") or "[]")
        except Exception:
            kps = []
        for kp in kps:
            if kp not in kp_ids:
                fails.append(f"{cid} unknown {kp}")
        sec_ids.add(sid)

    assesses = [
        e
        for e in links
        if e.get("type") == "assesses" and str(e.get("from", "")).startswith(f"question:{year}-")
    ]
    print(
        f"[回链] {year} items={n_items} answers={n_answers} assesses={len(assesses)} sections={len(sec_ids)}"
    )
    seen_e: set[tuple] = set()
    for e in assesses:
        key = (e["from"], e["type"], e["to"])
        if key in seen_e:
            fails.append(f"dup assesses {key}")
        seen_e.add(key)
        if e["to"] not in kp_ids:
            fails.append(f"assesses bad to {e['to']}")
        src = str(e["from"])
        if not src.startswith("question:"):
            fails.append(f"assesses bad from {src}")
        qid = src.split(":", 1)[1]
        sid = f"exam-{qid}"
        if sec_ids and sid not in sec_ids:
            fails.append(f"assesses from not indexed {qid}")
    return fails


async def test_negative(year: int) -> list[str]:
    fails: list[str] = []
    from rag.retrieval.retriever import aretrieve_evidence_with_retry

    async def top(query: str, k: int = 5):
        fused, _ = await aretrieve_evidence_with_retry(query=query, k=k)
        return list(getattr(fused, "text_evidences", []) or [])

    # 答案不得从题干 chunk 正文漏出
    import chromadb

    client = chromadb.PersistentClient(path=str(ROOT / "chroma_db"))
    col = client.get_collection(COLLECTION)
    got = col.get(
        where={"$and": [{"exam_year": str(year)}, {"doc_role": "exam_item"}]},
        include=["documents", "metadatas"],
    )
    for d, m in zip(got.get("documents") or [], got.get("metadatas") or []):
        if ANSWER_IN_BODY_RE.search(d or ""):
            fails.append(f"answer leak {m.get('chunk_id')}")
        # 正文不应出现加粗 ✅ 答案
        if re.search(r"\*\*[A-D][.、．].*✅", d or ""):
            fails.append(f"bold answer {m.get('chunk_id')}")

    # L2 related_exams 可解析：2019-Q2 必须在库（硬条件）
    # 检索命中为软信号（旧讲义仍占位），仅记录不判失败
    q2 = col.get(where={"question_id": f"{year}-Q2"}, include=["metadatas"])
    if not (q2.get("ids") or []):
        fails.append(f"{year}-Q2 missing (related_exams)")
    else:
        print(f"[负向] {year}-Q2 present for related_exams")

    evs = await top(f"{year} 年 408 第2题 树 转化为二叉树 后根遍历")
    hit = any((getattr(e, "metadata", {}) or {}).get("question_id") == f"{year}-Q2" for e in evs)
    print(f"[负向] retrieve Q2 hit={hit} (soft)")
    return fails


async def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    verify_only = "--verify-only" in sys.argv
    year = int(args[0]) if args else 2019
    if not verify_only:
        print("==== ingest exams", year, "====")
        ingest_year(year)
    print("==== KP 回链 ====")
    f1 = test_backlink(year)
    print("==== 负向 ====")
    f2 = await test_negative(year)
    fails = f1 + f2
    if fails:
        print("FAIL", len(fails))
        for x in fails[:30]:
            print(" -", x)
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
