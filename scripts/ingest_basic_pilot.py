"""L1 Basic 入库试点：解析 06_tree.md → chunk 元数据 → teaches 边。

用法：
    PYTHONPATH=src python scripts/ingest_basic_pilot.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from langchain_core.documents import Document  # noqa: E402

from rag.splitter import split_documents  # noqa: E402
from rag.vectorstore import get_vector_store_manager  # noqa: E402

DOC_PATH = ROOT / "knowledge" / "basic" / "data_structure" / "06_tree.md"
LINKS_PATH = ROOT / "knowledge" / "knowledge_points" / "links.jsonl"
COLLECTION = "data_structure"


def parse_basic_doc(text: str) -> dict:
    """解析 domain_kp / document_id / 各 section 元数据。"""
    domain_kp = ""
    document_id = ""
    for line in text.splitlines()[:20]:
        m = re.match(r">\s*domain_kp:\s*(\S+)", line)
        if m:
            domain_kp = m.group(1)
        m = re.match(r">\s*document_id:\s*(\S+)", line)
        if m:
            document_id = m.group(1)

    # 按 H2 切 section
    parts = re.split(r"(?m)^(## .+)$", text)
    # parts: [pre, h2, body, h2, body...]
    header = parts[0]
    sections = []
    for i in range(1, len(parts) - 1, 2):
        heading = parts[i].strip()
        body = parts[i + 1]
        title = heading.lstrip("# ").strip()
        if title == "学习目标":
            continue
        meta = {"title": title}
        for line in body.splitlines()[:15]:
            m = re.match(r">\s*section_id:\s*(\S+)", line)
            if m:
                meta["section_id"] = m.group(1)
            m = re.match(r">\s*primary_kp:\s*(\S+)", line)
            if m:
                meta["primary_kp"] = m.group(1)
            m = re.match(r">\s*kp_ids:\s*(\[[^\]]*\]|.*)", line)
            if m:
                raw = m.group(1).strip()
                if raw.startswith("["):
                    meta["kp_ids"] = [
                        x.strip().strip("'\"") for x in raw.strip("[]").split(",") if x.strip()
                    ]
                else:
                    meta["kp_ids"] = []
        # 去掉 blockquote 元数据行
        body_clean = "\n".join(ln for ln in body.splitlines() if not ln.startswith(">")).strip()
        meta["body"] = body_clean
        meta.setdefault("section_id", "")
        meta.setdefault("kp_ids", [])
        meta.setdefault("primary_kp", "")
        sections.append(meta)
    return {
        "domain_kp": domain_kp,
        "document_id": document_id,
        "header": header,
        "sections": sections,
    }


def main() -> int:
    text = DOC_PATH.read_text(encoding="utf-8")
    parsed = parse_basic_doc(text)
    print("document_id:", parsed["document_id"], "domain_kp:", parsed["domain_kp"])
    print("sections:", len(parsed["sections"]))

    mgr = get_vector_store_manager()
    chunks: list[Document] = []
    teaches: list[dict] = []

    for sec in parsed["sections"]:
        sid = sec["section_id"]
        if not sid or not sec["body"]:
            print("  skip section", sec["title"])
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
                "source": str(DOC_PATH.relative_to(ROOT)).replace("\\", "/"),
            },
        )
        parts = split_documents([doc])
        for i, ch in enumerate(parts, 1):
            ch.metadata["chunk_id"] = f"{sid}-{i:03d}"
            ch.metadata["document_id"] = parsed["document_id"]
            ch.metadata["section_id"] = sid
            ch.metadata["kb_depth"] = "basic"
            ch.metadata["doc_role"] = "textbook"
            ch.metadata["knowledge_points"] = json.dumps(sec["kp_ids"], ensure_ascii=False)
            chunks.append(ch)
        for kp in sec["kp_ids"]:
            teaches.append({"from": f"basic:{sid}", "to": kp, "type": "teaches"})

    print("chunks", len(chunks), "teaches", len(teaches))
    ids = mgr.add_documents(chunks, collection_name=COLLECTION)
    print("indexed", len(ids))
    mgr.wait_until_ready(COLLECTION)
    print("index ready")

    # 合并 teaches 到 links.jsonl（去重）
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
    print("links added", added, "total", len(existing))

    # 冒烟：按 section 元数据过滤
    from langchain_chroma import Chroma  # noqa: F401

    col = mgr.client.get_collection(COLLECTION)
    sample = col.get(where={"document_id": parsed["document_id"]}, include=["metadatas"])
    print("pilot chunks in store:", len(sample.get("ids") or []))
    if sample.get("metadatas"):
        m0 = sample["metadatas"][0]
        print(
            "sample meta:",
            {
                k: m0.get(k)
                for k in ["document_id", "section_id", "chunk_id", "kb_depth", "primary_kp"]
            },
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
