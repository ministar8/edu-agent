"""L1 Basic 全量入库（数据结构 9 章）+ KP 回链 / 负向检索验收。

用法：
    PYTHONPATH=src python scripts/ingest_basic_ds.py
    PYTHONPATH=src python scripts/ingest_basic_ds.py --verify
"""

from __future__ import annotations

import asyncio
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from langchain_core.documents import Document  # noqa: E402

from rag.splitter import split_documents  # noqa: E402
from rag.vectorstore import get_vector_store_manager  # noqa: E402

BASIC_DIR = ROOT / "knowledge" / "basic" / "data_structure"
LINKS_PATH = ROOT / "knowledge" / "knowledge_points" / "links.jsonl"
KP_DIR = ROOT / "knowledge" / "knowledge_points"
COLLECTION = "data_structure"
EXAM_WORDS = re.compile(r"选择题|计算题|真题|常考|考点|刷题|王道|应试")


def load_kp_ids() -> set[str]:
    ids = set()
    for p in KP_DIR.glob("*.jsonl"):
        if p.name == "links.jsonl":
            continue
        for line in p.read_text(encoding="utf-8").splitlines():
            ids.add(json.loads(line)["id"])
    return ids


def parse_basic_doc(text: str) -> dict:
    domain_kp = document_id = ""
    for line in text.splitlines()[:20]:
        m = re.match(r">\s*domain_kp:\s*(\S+)", line)
        if m:
            domain_kp = m.group(1)
        m = re.match(r">\s*document_id:\s*(\S+)", line)
        if m:
            document_id = m.group(1)
    parts = re.split(r"(?m)^(## .+)$", text)
    sections = []
    for i in range(1, len(parts) - 1, 2):
        heading = parts[i].strip()
        body = parts[i + 1]
        title = heading.lstrip("# ").strip()
        if title == "学习目标":
            continue
        meta: dict = {"title": title}
        for line in body.splitlines()[:15]:
            m = re.match(r">\s*section_id:\s*(\S+)", line)
            if m:
                meta["section_id"] = m.group(1)
            m = re.match(r">\s*primary_kp:\s*(\S+)", line)
            if m:
                meta["primary_kp"] = m.group(1)
            m = re.match(r">\s*kp_ids:\s*(\[[^\]]*\])", line)
            if m:
                raw = m.group(1).strip("[]")
                meta["kp_ids"] = [x.strip().strip("'\"") for x in raw.split(",") if x.strip()]
        body_clean = "\n".join(ln for ln in body.splitlines() if not ln.startswith(">")).strip()
        meta["body"] = body_clean
        meta.setdefault("section_id", "")
        meta.setdefault("kp_ids", [])
        meta.setdefault("primary_kp", "")
        sections.append(meta)
    return {
        "domain_kp": domain_kp,
        "document_id": document_id,
        "sections": sections,
    }


def ingest_all() -> tuple[int, int, list[dict]]:
    kp_ids = load_kp_ids()
    mgr = get_vector_store_manager()
    chunks: list[Document] = []
    teaches: list[dict] = []
    for path in sorted(BASIC_DIR.glob("*.md")):
        parsed = parse_basic_doc(path.read_text(encoding="utf-8"))
        for sec in parsed["sections"]:
            sid = sec["section_id"]
            if not sid or not sec["body"]:
                continue
            for kp in sec["kp_ids"]:
                if kp not in kp_ids:
                    print("WARN unknown KP", kp, "at", sid)
                    continue
                teaches.append({"from": f"basic:{sid}", "to": kp, "type": "teaches"})
            if "对照" in sec["title"] or "锚定" in (sec.get("title") or ""):
                continue
            doc = Document(
                page_content=f"## {sec['title']}\n\n{sec['body']}",
                metadata={
                    "kb_depth": "basic",
                    "doc_role": "textbook",
                    "subject": "data_structure",
                    "document_id": parsed["document_id"],
                    "section_id": sid,
                    "domain_kp": parsed["domain_kp"],
                    "knowledge_points": json.dumps(sec["kp_ids"], ensure_ascii=False),
                    "primary_kp": sec["primary_kp"] or (sec["kp_ids"][0] if sec["kp_ids"] else ""),
                    "heading": sec["title"],
                    "source": str(path.relative_to(ROOT)).replace("\\", "/"),
                },
            )
            for i, ch in enumerate(split_documents([doc]), 1):
                ch.metadata["chunk_id"] = f"{sid}-{i:03d}"
                ch.metadata["document_id"] = parsed["document_id"]
                ch.metadata["section_id"] = sid
                ch.metadata["kb_depth"] = "basic"
                ch.metadata["doc_role"] = "textbook"
                ch.metadata["knowledge_points"] = json.dumps(sec["kp_ids"], ensure_ascii=False)
                chunks.append(ch)
    ids = mgr.add_documents(chunks, collection_name=COLLECTION)
    mgr.wait_until_ready(COLLECTION)
    # links merge
    existing = []
    if LINKS_PATH.exists():
        for line in LINKS_PATH.read_text(encoding="utf-8").splitlines():
            if line.strip():
                existing.append(json.loads(line))
    seen = {(e.get("from"), e.get("type"), e.get("to")) for e in existing}
    added = 0
    for e in teaches:
        key = (e["from"], e["type"], e["to"])
        if key not in seen:
            existing.append(e)
            seen.add(key)
            added += 1
    LINKS_PATH.write_text(
        "\n".join(json.dumps(e, ensure_ascii=False) for e in existing) + "\n",
        encoding="utf-8",
    )
    print(
        f"docs chunks={len(chunks)} new_indexed={len(ids)} teaches_added={added} links_total={len(existing)}"
    )
    return len(chunks), added, teaches


def test_backlink() -> list[str]:
    fails = []
    kp_ids = load_kp_ids()
    links = [
        json.loads(x) for x in LINKS_PATH.read_text(encoding="utf-8").splitlines() if x.strip()
    ]
    import chromadb

    col = chromadb.PersistentClient(path=str(ROOT / "chroma_db")).get_collection(COLLECTION)
    got = col.get(where={"kb_depth": "basic"}, include=["metadatas"])
    metas = got.get("metadatas") or []
    print(f"[回链] basic chunks={len(metas)}")
    sec_ids = set()
    for m in metas:
        cid = m.get("chunk_id") or ""
        sid = m.get("section_id") or ""
        did = m.get("document_id") or ""
        if not cid.startswith(sid) or not sid.startswith(did):
            fails.append(f"id chain {cid}")
        if m.get("kb_depth") != "basic":
            fails.append(f"kb_depth {cid}")
        try:
            kps = json.loads(m.get("knowledge_points") or "[]")
        except Exception:
            kps = []
            fails.append(f"bad kps {cid}")
        for kp in kps:
            if kp not in kp_ids:
                fails.append(f"{cid} unknown KP {kp}")
        sec_ids.add(sid)
    teaches = [
        e
        for e in links
        if e.get("type") == "teaches" and str(e.get("from", "")).startswith("basic:")
    ]
    print(f"[回链] teaches={len(teaches)}")
    for e in teaches:
        if e["to"] not in kp_ids:
            fails.append(f"teaches to unknown {e['to']}")
        src = e["from"].split(":", 1)[-1]
        if src not in sec_ids:
            fails.append(f"teaches from unknown section {src}")
    return fails


async def test_negative() -> list[str]:
    fails = []
    from rag.retriever import aretrieve_evidence_with_retry

    async def top(query: str, k: int = 5):
        fused, _ = await aretrieve_evidence_with_retry(query=query, k=k)
        return list(getattr(fused, "text_evidences", []) or [])

    def is_basic(ev) -> bool:
        return (getattr(ev, "metadata", {}) or {}).get("kb_depth") == "basic"

    evs = await top("IPv4 子网划分怎么做")
    b = sum(1 for e in evs if is_basic(e))
    print(f"[负向 A 离题] n={len(evs)} basic_hits={b}")
    if evs and b == len(evs):
        fails.append("off-topic all basic")

    evs = await top("BST 删除的三种情况怎么解题")
    bad = []
    for e in evs:
        meta = getattr(e, "metadata", {}) or {}
        if meta.get("kb_depth") != "basic":
            continue
        if re.search(r"先判断删除|三种情况分别|答题步骤|解题步骤", getattr(e, "content", "") or ""):
            bad.append(meta.get("chunk_id"))
    print(f"[负向 B L2] trick={bad}")
    if bad:
        fails.append(f"L1 has L2 tactics {bad}")

    evs = await top("2019年408第5题标准答案")
    if evs:
        m0 = getattr(evs[0], "metadata", {}) or {}
        print(f"[负向 D 真题] top1 doc={m0.get('document_id')} kb={m0.get('kb_depth')}")
        if m0.get("kb_depth") == "basic":
            fails.append("exam-answer top1 is basic")

    import chromadb

    col = chromadb.PersistentClient(path=str(ROOT / "chroma_db")).get_collection(COLLECTION)
    got = col.get(where={"kb_depth": "basic"}, include=["documents", "metadatas"])
    for d, m in zip(got.get("documents") or [], got.get("metadatas") or []):
        body = re.sub(r"^>.*$", "", d or "", flags=re.M)
        if EXAM_WORDS.search(body):
            fails.append(f"exam word in {m.get('chunk_id')}")
    return fails


async def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 else "ingest"
    if mode != "--verify-only":
        print("==== ingest ====")
        ingest_all()
    print("==== KP 回链 ====")
    f1 = test_backlink()
    print("==== 负向检索 ====")
    f2 = await test_negative()
    fails = f1 + f2
    if fails:
        print("FAIL", len(fails))
        for x in fails[:20]:
            print(" -", x)
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
