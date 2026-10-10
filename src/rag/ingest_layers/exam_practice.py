"""L3 章节题型入库：``knowledge/exams/<科>.md``（常考题型与例题）→ ``exams`` 集合。

与 ``exams.py``（按年 items+answer）互补：本模块入 exams/ 根下的「按章节的例题集」，
同样进 ``exams``，``doc_role=exam_item``。写
``practice:<sid> ──trains──→ KP`` 边（混标真题结论节 ``kp_ids: []`` 不入边）。
"""

from __future__ import annotations

import json

from langchain_core.documents import Document

from rag.ingest_layers import _shared
from rag.vectorstore import get_vector_store_manager

EXAMS_DIR = _shared.KNOWLEDGE_DIR / "exams"
COLLECTION = "exams"

# 文件名（stem）→ subject 短码
SUBJECT_CODE = {
    "data_structure": "ds",
    "computer_organization": "co",
    "operating_system": "os",
    "computer_network": "cn",
}


def build(kp_ids: set[str]) -> tuple[list[Document], list[dict], dict]:
    """构建章节例题 chunk（纯函数：不落库、不写 links）。"""
    chunks: list[Document] = []
    edges: list[dict] = []
    for path in sorted(EXAMS_DIR.glob("*.md")):
        code = SUBJECT_CODE.get(path.stem)
        if code is None:
            continue
        rel = str(path.relative_to(_shared.ROOT)).replace("\\", "/")
        document_id, sections = _shared.parse_sections(path.read_text(encoding="utf-8"))
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
            chunks.extend(
                _shared.split_section(
                    doc,
                    sid,
                    {
                        "kb_depth": "exams",
                        "doc_role": "exam_item",
                        "subject": code,
                        "document_id": document_id or f"exam-practice-{code}",
                        "section_id": sid,
                        "knowledge_points": doc.metadata["knowledge_points"],
                    },
                    keep_short=False,
                )
            )
    return chunks, edges, {"chunks": len(chunks)}


def ingest(kp_ids: set[str]) -> int:
    mgr = get_vector_store_manager()
    chunks, edges, _ = build(kp_ids)
    ids = mgr.add_documents(chunks, collection_name=COLLECTION)
    mgr.wait_until_ready(COLLECTION)
    added = _shared.merge_links(edges)
    print({"collection": COLLECTION, "chunks": len(chunks), "new": len(ids), "trains_added": added})
    return 0
