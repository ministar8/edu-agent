"""Code 代码库入库：``knowledge/code/<科>/*.md`` → ``code_<科>`` 集合。

代码实现独立成库（不进 L1/L2/L3），供「代码类」查询定向召回。
Section 级 KP 锚定：``> section_id/kp_ids/primary_kp`` 头 → chunk 继承节级元数据 +
``code:<sid> ──teaches──→ KP`` 边。

``build()`` 纯构建（门禁用）；``ingest()`` 落库 + 写 links（脚本用）。
"""

from __future__ import annotations

import json

from langchain_core.documents import Document

from rag.common.vectorstore import get_vector_store_manager
from rag.ingest_layers import _shared

CODE_DIR = _shared.KNOWLEDGE_DIR / "code"

# 目录名 → 目标集合名（按科分，与检索路由一致）
SUBJECT_TO_COLLECTION = {
    "data_structure": "code_ds",
    "computer_organization": "code_co",
    "operating_system": "code_os",
    "computer_network": "code_cn",
}
SUBJECT_CODE = {
    "data_structure": "ds",
    "computer_organization": "co",
    "operating_system": "os",
    "computer_network": "cn",
}


def build(subject: str, kp_ids: set[str]) -> tuple[list[Document], list[dict], dict]:
    """构建单科代码 chunk（纯函数：不落库、不写 links）。"""
    dir_path = CODE_DIR / subject
    if not dir_path.is_dir():
        return [], [], {"subject": subject, "chunks": 0, "skipped": True}

    code = SUBJECT_CODE[subject]
    chunks: list[Document] = []
    edges: list[dict] = []
    for path in sorted(dir_path.rglob("*.md")):
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
                edges.append({"from": f"code:{sid}", "to": kp, "type": "teaches"})
            doc = Document(
                page_content=f"## {sec['title']}\n\n{sec['body']}",
                metadata={
                    "kb_depth": "code",
                    "doc_role": "code",
                    "subject": code,
                    "document_id": document_id or f"code-{code}",
                    "section_id": sid,
                    "knowledge_points": json.dumps(sec["kp_ids"], ensure_ascii=False),
                    "primary_kp": sec.get("primary_kp", ""),
                    "heading": sec["title"],
                    "source": rel,
                    "category": SUBJECT_TO_COLLECTION[subject],
                },
            )
            chunks.extend(
                _shared.split_section(
                    doc,
                    sid,
                    {
                        "kb_depth": "code",
                        "doc_role": "code",
                        "subject": code,
                        "document_id": document_id or f"code-{code}",
                        "section_id": sid,
                        "knowledge_points": doc.metadata["knowledge_points"],
                    },
                    keep_short=False,
                )
            )
    return chunks, edges, {"subject": subject, "chunks": len(chunks)}


def ingest(subject: str, kp_ids: set[str]) -> dict:
    """入库单科到 ``code_<科>`` 并写 teaches 边。"""
    collection = SUBJECT_TO_COLLECTION[subject]
    mgr = get_vector_store_manager()
    chunks, edges, stats = build(subject, kp_ids)
    if stats.get("skipped"):
        # 无代码文件的科也建空集合：检索侧 `is_code` 会查 `code_<科>`，
        # 缺集合会刷 "Collection does not exist" 并白花一次 Chroma 往返。
        mgr.get_store(collection)
        return {"collection": collection, **stats}
    ids = mgr.add_documents(chunks, collection_name=collection)
    mgr.wait_until_ready(collection)
    _shared.merge_links(edges)
    return {"collection": collection, "chunks": stats["chunks"], "new": len(ids)}


def ingest_all(kp_ids: set[str] | None = None) -> None:
    kp_ids = kp_ids if kp_ids is not None else _shared.load_kp_ids()
    for subject in SUBJECT_TO_COLLECTION:
        print(ingest(subject, kp_ids))
