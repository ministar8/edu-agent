"""L3 真题入库：``knowledge/exams/YYYY/{items,answer}.md`` → ``exams`` 集合。

一题 = 一 section（``exam-YYYY-QN``）；``items`` / ``answer`` 各自成 chunk 族
（``chunk_id = <sid>-{items|answer}-NNN``）。写 ``question:<qid> ──assesses──→ KP``。
"""

from __future__ import annotations

import json
import re

from langchain_core.documents import Document

from rag.chunking.splitter import split_documents
from rag.ingest_layers import _shared
from rag.vectorstore import get_vector_store_manager

EXAMS_DIR = _shared.KNOWLEDGE_DIR / "exams"
COLLECTION = "exams"
ANSWER_IN_BODY_RE = re.compile(r"(^|\n)\s*(答案[:：]|【答案】|\*\*答案)")


def _parse_meta(lines: list[str]) -> dict:
    meta: dict = {}
    for line in lines:
        if not line.lstrip().startswith(">"):
            continue
        content = line.lstrip(">").strip()
        m = re.match(r"([A-Za-z_]+)\s*:\s*(.*)$", content)
        if not m:
            continue
        key, val = m.group(1), m.group(2).strip()
        if key in {"kp_ids", "gap_fields", "related_exams"}:
            raw = val.strip("[]")
            meta[key] = [x.strip().strip("'\"") for x in raw.split(",") if x.strip()]
        elif key == "has_figure":
            meta[key] = val == "true"
        elif key == "score":
            try:
                meta[key] = int(val)
            except ValueError:
                pass
        else:
            meta[key] = val
    return meta


def parse_items(text: str) -> list[dict]:
    parts = re.split(r"(?m)^## (\d{4}-Q\d+)\s*$", text)
    out: list[dict] = []
    for i in range(1, len(parts) - 1, 2):
        qid = parts[i]
        body = parts[i + 1]
        meta = _parse_meta(body.splitlines()[:40])
        meta["question_id"] = qid
        meta["body"] = "\n".join(
            ln for ln in body.splitlines() if not ln.lstrip().startswith(">")
        ).strip()
        out.append(meta)
    return out


def parse_answer(text: str) -> dict[str, dict]:
    parts = re.split(r"(?m)^## (\d{4}-Q\d+)\s*$", text)
    out: dict[str, dict] = {}
    for i in range(1, len(parts) - 1, 2):
        qid = parts[i]
        body = parts[i + 1]
        meta = _parse_meta(body.splitlines()[:20])
        meta["body"] = "\n".join(
            ln for ln in body.splitlines() if not ln.lstrip().startswith(">")
        ).strip()
        out[qid] = meta
    return out


def years() -> list[int]:
    return sorted(
        int(p.parent.name) for p in EXAMS_DIR.glob("*/items.md") if p.parent.name.isdigit()
    )


def build(year: int, kp_ids: set[str]) -> tuple[list[Document], list[dict], dict]:
    """构建某年真题 chunk（纯函数：不落库、不写 links）。"""
    year_dir = EXAMS_DIR / str(year)
    items_path = year_dir / "items.md"
    answer_path = year_dir / "answer.md"
    if not items_path.exists():
        raise SystemExit(f"missing {items_path}")
    items = parse_items(items_path.read_text(encoding="utf-8"))
    answers = parse_answer(answer_path.read_text(encoding="utf-8")) if answer_path.exists() else {}

    chunks: list[Document] = []
    assesses: list[dict] = []
    fails: list[str] = []

    for it in items:
        qid = it["question_id"]
        sid = f"exam-{qid}"
        for kp in it.get("kp_ids") or []:
            if kp not in kp_ids:
                fails.append(f"{qid} unknown KP {kp}")
                continue
            assesses.append({"from": f"question:{qid}", "to": kp, "type": "assesses"})
        body = it.get("body") or ""
        if ANSWER_IN_BODY_RE.search(body):
            fails.append(f"{qid} answer leaked into item body")
        doc = Document(
            page_content=body,
            metadata={
                "kb_depth": "exams",
                "doc_role": "exam_item",
                "subject": it.get("subject") or "",
                "document_id": f"exam-{year}-items",
                "section_id": sid,
                "question_id": qid,
                "exam_year": str(year),
                "source_type": it.get("source_type") or "third_party",
                "credibility": it.get("credibility") or "",
                "explanation_status": it.get("explanation_status") or "none",
                "question_type": it.get("question_type") or "choice",
                "knowledge_points": json.dumps(it.get("kp_ids") or [], ensure_ascii=False),
                "primary_kp": (it.get("kp_ids") or [""])[0] if it.get("kp_ids") else "",
                "answer_key": it.get("answer_key") or "",
                "reference_answer": it.get("reference_answer") or "",
                "has_figure": bool(it.get("has_figure")),
                "figure_status": it.get("figure_status") or "",
                "completeness": it.get("completeness") or "",
                "gap_status": it.get("gap_status") or "",
                "gap_fields": json.dumps(it.get("gap_fields") or [], ensure_ascii=False),
                "heading": qid,
                "source": f"knowledge/exams/{year}/items.md",
            },
        )
        made = 0
        for i, ch in enumerate(split_documents([doc]), 1):
            ch.metadata["chunk_id"] = f"{sid}-items-{i:03d}"
            ch.metadata["document_id"] = f"exam-{year}-items"
            ch.metadata["section_id"] = sid
            ch.metadata["kb_depth"] = "exams"
            ch.metadata["doc_role"] = "exam_item"
            ch.metadata["question_id"] = qid
            chunks.append(ch)
            made += 1
        if made == 0:
            ch = Document(page_content=doc.page_content, metadata=dict(doc.metadata))
            ch.metadata["chunk_id"] = f"{sid}-items-001"
            chunks.append(ch)

        ans = answers.get(qid)
        if not ans:
            continue
        ans_body = (ans.get("body") or "").strip()
        if not ans_body:
            ans_body = "（无文字解析。）"
        if qid not in ans_body:
            ans_body = f"[{qid}]\n{ans_body}"
        adoc = Document(
            page_content=ans_body,
            metadata={
                "kb_depth": "exams",
                "doc_role": "exam_answer",
                "document_id": f"exam-{year}-answer",
                "section_id": sid,
                "question_id": qid,
                "exam_year": str(year),
                "source_type": "third_party",
                "explanation_status": ans.get("explanation_status") or "scan",
                "answer_key": ans.get("answer_key") or it.get("answer_key") or "",
                "heading": f"{qid} 解析",
                "source": f"knowledge/exams/{year}/answer.md",
            },
        )
        made = 0
        for i, ch in enumerate(split_documents([adoc]), 1):
            ch.metadata["chunk_id"] = f"{sid}-answer-{i:03d}"
            ch.metadata["document_id"] = f"exam-{year}-answer"
            ch.metadata["section_id"] = sid
            ch.metadata["kb_depth"] = "exams"
            ch.metadata["doc_role"] = "exam_answer"
            ch.metadata["question_id"] = qid
            chunks.append(ch)
            made += 1
        if made == 0:
            ch = Document(page_content=adoc.page_content, metadata=dict(adoc.metadata))
            ch.metadata["chunk_id"] = f"{sid}-answer-001"
            chunks.append(ch)
    return chunks, assesses, {"year": year, "chunks": len(chunks), "fails": fails}


def build_all(kp_ids: set[str]) -> tuple[list[Document], list[dict], dict]:
    all_chunks: list[Document] = []
    all_edges: list[dict] = []
    fails: list[str] = []
    for year in years():
        chunks, edges, stats = build(year, kp_ids)
        all_chunks.extend(chunks)
        all_edges.extend(edges)
        fails.extend(stats["fails"])
    return all_chunks, all_edges, {"chunks": len(all_chunks), "fails": fails}


def ingest_year(year: int, kp_ids: set[str]) -> dict:
    mgr = get_vector_store_manager()
    chunks, assesses, stats = build(year, kp_ids)
    ids = mgr.add_documents(chunks, collection_name=COLLECTION)
    mgr.wait_until_ready(COLLECTION)
    added = _shared.merge_links(assesses)
    print(f"year={year} chunks={len(chunks)} new={len(ids)} assesses_added={added}")
    if stats["fails"]:
        print("parse_fails", len(stats["fails"]))
        for x in stats["fails"][:20]:
            print(" !", x)
    return {"chunks": len(chunks), "new": len(ids), "assesses_added": added}


def ingest_all(kp_ids: set[str] | None = None) -> None:
    kp_ids = kp_ids if kp_ids is not None else _shared.load_kp_ids()
    for year in years():
        ingest_year(year, kp_ids)
