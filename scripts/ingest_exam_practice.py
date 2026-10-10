"""L3 章节题型入库：`knowledge/exams/<科>.md`（常考题型与例题）→ `exams` 集合。

与 `ingest_exams.py`（按年入库 `exams/YYYY/items+answer`）互补：本脚本入 exams/ 根下的
「按章节的例题集」，同样进 L3 `exams` 集合，`doc_role=exam_item`。
Section 级 KP 锚定：解析 H3 下的 `> section_id/kp_ids/primary_kp` 头，
chunk 继承节级元数据，并写 `practice:<section_id> ──trains──→ KP` 边
（混标真题结论节 `kp_ids: []`，不入边——真题侧已由 assesses 承载）。

用法：
    PYTHONPATH=src uv run python scripts/ingest_exam_practice.py
    PYTHONPATH=src uv run python scripts/ingest_exam_practice.py --verify-only
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ingest_code import load_kp_ids, merge_edges, parse_sections  # noqa: E402
from langchain_core.documents import Document  # noqa: E402

from rag.splitter import split_documents  # noqa: E402
from rag.vectorstore import get_vector_store_manager  # noqa: E402

EXAMS_DIR = ROOT / "knowledge" / "exams"
COLLECTION = "exams"

# 文件名（stem）→ subject 短码
SUBJECT_CODE = {
    "data_structure": "ds",
    "computer_organization": "co",
    "operating_system": "os",
    "computer_network": "cn",
}


def ingest_all(kp_ids: set[str]) -> int:
    mgr = get_vector_store_manager()
    chunks: list[Document] = []
    edges: list[dict] = []
    for path in sorted(EXAMS_DIR.glob("*.md")):
        code = SUBJECT_CODE.get(path.stem)
        if code is None:
            continue
        rel = str(path.relative_to(ROOT)).replace("\\", "/")
        document_id, sections = parse_sections(path.read_text(encoding="utf-8"))
        for sec in sections:
            sid = sec["section_id"]
            if not sec["body"]:
                print(f"WARN empty body {sid}")
                continue
            for kp in sec["kp_ids"]:
                if kp not in kp_ids:
                    print(f"WARN unknown KP {kp} {sid}")
                    continue
                edges.append({"from": f"practice:{sid}", "to": kp, "type": "trains"})
            doc = Document(
                page_content=f"### {sec['title']}\n\n{sec['body']}",
                metadata={
                    "kb_depth": "exams",
                    "doc_role": "exam_item",
                    "subject": code,
                    "document_id": document_id or f"exam-practice-{code}",
                    "section_id": sid,
                    "knowledge_points": json.dumps(sec["kp_ids"], ensure_ascii=False),
                    "primary_kp": sec.get("primary_kp", ""),
                    "heading": sec["title"],
                    "source": rel,
                    "category": COLLECTION,
                },
            )
            for i, ch in enumerate(split_documents([doc]), 1):
                ch.metadata.update(
                    chunk_id=f"{sid}-{i:03d}",
                    kb_depth="exams",
                    doc_role="exam_item",
                    subject=code,
                    document_id=document_id or f"exam-practice-{code}",
                    section_id=sid,
                    knowledge_points=doc.metadata["knowledge_points"],
                )
                chunks.append(ch)
        print(f"{rel}: {len(chunks)} chunks so far")

    ids = mgr.add_documents(chunks, collection_name=COLLECTION)
    mgr.wait_until_ready(COLLECTION)
    added = merge_edges(edges)
    print({"collection": COLLECTION, "chunks": len(chunks), "new": len(ids), "trains_added": added})
    return 0


def verify(kp_ids: set[str]) -> list[str]:
    """回链校验：exam-practice chunk 的 id 链 + trains 边双向存在性。"""
    import chromadb

    fails: list[str] = []
    links = [
        json.loads(x)
        for x in (ROOT / "knowledge" / "knowledge_points" / "links.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if x.strip()
    ]
    trains_pairs = {(e["from"], e["to"]) for e in links if e.get("type") == "trains"}
    client = chromadb.PersistentClient(path=str(ROOT / "chroma_db"))
    try:
        col = client.get_collection(COLLECTION)
    except Exception:
        return [f"missing collection {COLLECTION}"]
    got = col.get(
        where={"document_id": {"$in": [f"exam-practice-{c}" for c in SUBJECT_CODE.values()]}},
        include=["metadatas"],
    )
    n = 0
    for m in got.get("metadatas") or []:
        n += 1
        cid, sid = m.get("chunk_id") or "", m.get("section_id") or ""
        did = m.get("document_id") or ""
        if not sid or not cid.startswith(sid) or not sid.startswith(did):
            fails.append(f"id chain {cid}")
        try:
            kps = json.loads(m.get("knowledge_points") or "[]")
        except Exception:
            kps = []
            fails.append(f"bad kps {cid}")
        for kp in kps:
            if kp not in kp_ids:
                fails.append(f"{cid} unknown {kp}")
        if kps and (f"practice:{sid}", kps[0]) not in trains_pairs:
            fails.append(f"no trains edge for {sid}")
    print(f"[回链] practice_chunks={n} trains_pairs={len(trains_pairs)}")
    return fails


def main() -> int:
    verify_only = "--verify-only" in sys.argv
    kp_ids = load_kp_ids()
    if not verify_only:
        ingest_all(kp_ids)
    fails = verify(kp_ids)
    if fails:
        print("FAIL", len(fails))
        for x in fails[:25]:
            print(" -", x)
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
