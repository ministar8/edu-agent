"""L3 Exams 入库 + assesses 边 + 回链/负向验收。

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

from langchain_core.documents import Document  # noqa: E402

from rag.splitter import split_documents  # noqa: E402
from rag.vectorstore import get_vector_store_manager  # noqa: E402

EXAMS_DIR = ROOT / "knowledge" / "exams"
LINKS_PATH = ROOT / "knowledge" / "knowledge_points" / "links.jsonl"
KP_DIR = ROOT / "knowledge" / "knowledge_points"
# 迁移期 alias：最终集合名 exams；questions 为现网路径
COLLECTION = "questions"

ANSWER_IN_BODY_RE = re.compile(r"(^|\n)\s*(答案[:：]|【答案】|\*\*答案)")


def load_kp_ids() -> set[str]:
    ids: set[str] = set()
    for p in KP_DIR.glob("*.jsonl"):
        if p.name == "links.jsonl":
            continue
        for line in p.read_text(encoding="utf-8").splitlines():
            if line.strip():
                ids.add(json.loads(line)["id"])
    return ids


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
        elif key in {"has_figure"}:
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
        body_clean = "\n".join(
            ln for ln in body.splitlines() if not ln.lstrip().startswith(">")
        ).strip()
        meta["body"] = body_clean
        out.append(meta)
    return out


def parse_answer(text: str) -> dict[str, dict]:
    parts = re.split(r"(?m)^## (\d{4}-Q\d+)\s*$", text)
    out: dict[str, dict] = {}
    for i in range(1, len(parts) - 1, 2):
        qid = parts[i]
        body = parts[i + 1]
        meta = _parse_meta(body.splitlines()[:20])
        body_clean = "\n".join(
            ln for ln in body.splitlines() if not ln.lstrip().startswith(">")
        ).strip()
        meta["body"] = body_clean
        out[qid] = meta
    return out


def ingest_year(year: int) -> dict:
    year_dir = EXAMS_DIR / str(year)
    items_path = year_dir / "items.md"
    answer_path = year_dir / "answer.md"
    if not items_path.exists():
        raise SystemExit(f"missing {items_path}")
    kp_ids = load_kp_ids()
    items = parse_items(items_path.read_text(encoding="utf-8"))
    answers = parse_answer(answer_path.read_text(encoding="utf-8")) if answer_path.exists() else {}

    mgr = get_vector_store_manager()
    chunks: list[Document] = []
    assesses: list[dict] = []
    fails: list[str] = []
    sec_ids: set[str] = set()

    for it in items:
        qid = it["question_id"]  # 2019-Q11
        sid = f"exam-{qid}"  # exam-2019-Q11
        sec_ids.add(sid)
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
        if ans:
            # 正文嵌入 question_id，避免「无文字解析」占位被 content_hash 去重吞掉
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

    ids = mgr.add_documents(chunks, collection_name=COLLECTION)
    mgr.wait_until_ready(COLLECTION)

    existing: list[dict] = []
    if LINKS_PATH.exists():
        for line in LINKS_PATH.read_text(encoding="utf-8").splitlines():
            if line.strip():
                existing.append(json.loads(line))
    seen = {(e.get("from"), e.get("type"), e.get("to")) for e in existing}
    added = 0
    for e in assesses:
        key = (e["from"], e["type"], e["to"])
        if key not in seen:
            existing.append(e)
            seen.add(key)
            added += 1
    LINKS_PATH.write_text(
        "\n".join(json.dumps(e, ensure_ascii=False) for e in existing) + "\n",
        encoding="utf-8",
    )
    print(f"year={year} chunks={len(chunks)} new={len(ids)} assesses_added={added}")
    if fails:
        print("parse_fails", len(fails))
        for x in fails[:20]:
            print(" !", x)
    return {
        "chunks": len(chunks),
        "new": len(ids),
        "assesses_added": added,
        "sec_ids": sec_ids,
        "fails": fails,
    }


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
    from rag.retriever import aretrieve_evidence_with_retry

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
