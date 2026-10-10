"""L1 Basic 入库：``knowledge/basic/<科>/*.md`` → 四科集合（``kb_depth=basic``）。

文档模型：一个 ``## section`` = 一个 Document；section 头 ``> section_id/kp_ids/primary_kp``
挂 KP，写 ``basic:<sid> ──teaches──→ KP``。
"""

from __future__ import annotations

import json
import re

from langchain_core.documents import Document

from rag.common.vectorstore import get_vector_store_manager
from rag.ingest_layers import _shared

BASIC_DIR = _shared.KNOWLEDGE_DIR / "basic"

SUBJECT_DIRS = {
    "data_structure": BASIC_DIR / "data_structure",
    "computer_organization": BASIC_DIR / "computer_organization",
    "operating_system": BASIC_DIR / "operating_system",
    "computer_network": BASIC_DIR / "computer_network",
}
SUBJECT_TO_COLLECTION = {
    "data_structure": "data_structure",
    "computer_organization": "computer_organization",
    "operating_system": "operating_system",
    "computer_network": "computer_network",
}


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
    sections: list[dict] = []
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
    return {"domain_kp": domain_kp, "document_id": document_id, "sections": sections}


def build(kp_ids: set[str]) -> tuple[dict[str, list[Document]], list[dict], dict]:
    """构建四科 basic chunk（纯函数：不落库、不写 links）。"""
    by_col: dict[str, list[Document]] = {v: [] for v in SUBJECT_TO_COLLECTION.values()}
    teaches: list[dict] = []
    for subject_name, basic_dir in SUBJECT_DIRS.items():
        collection = SUBJECT_TO_COLLECTION[subject_name]
        for path in sorted(basic_dir.glob("*.md")):
            parsed = parse_basic_doc(path.read_text(encoding="utf-8"))
            for sec in parsed["sections"]:
                sid = sec["section_id"]
                if not sid or not sec["body"]:
                    continue
                if "对照" in sec["title"] or "锚定" in sec["title"]:
                    continue
                for kp in sec["kp_ids"]:
                    if kp not in kp_ids:
                        print("WARN unknown KP", kp, sid)
                        continue
                    teaches.append({"from": f"basic:{sid}", "to": kp, "type": "teaches"})
                doc = Document(
                    page_content=f"## {sec['title']}\n\n{sec['body']}",
                    metadata={
                        "kb_depth": "basic",
                        "doc_role": "textbook",
                        "subject": subject_name,
                        "document_id": parsed["document_id"],
                        "section_id": sid,
                        "domain_kp": parsed["domain_kp"],
                        "knowledge_points": json.dumps(sec["kp_ids"], ensure_ascii=False),
                        "primary_kp": sec["primary_kp"]
                        or (sec["kp_ids"][0] if sec["kp_ids"] else ""),
                        "heading": sec["title"],
                        "source": str(path.relative_to(_shared.ROOT)).replace("\\", "/"),
                    },
                )
                by_col[collection].extend(
                    _shared.split_section(
                        doc,
                        sid,
                        {
                            "kb_depth": "basic",
                            "doc_role": "textbook",
                            "subject": subject_name,
                            "knowledge_points": json.dumps(sec["kp_ids"], ensure_ascii=False),
                        },
                        keep_short=True,
                    )
                )
    return by_col, teaches, {"chunks": sum(len(v) for v in by_col.values())}


def ingest(kp_ids: set[str]) -> None:
    mgr = get_vector_store_manager()
    by_col, teaches, _ = build(kp_ids)
    for collection, chunks in by_col.items():
        ids = mgr.add_documents(chunks, collection_name=collection)
        mgr.wait_until_ready(collection)
        print(f"  [{collection}] chunks={len(chunks)} new={len(ids)}")
    added = _shared.merge_links(teaches)
    total = sum(len(v) for v in by_col.values())
    print(f"teaches_added={added} new_indexed={total}")
