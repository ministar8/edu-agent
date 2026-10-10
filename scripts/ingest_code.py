"""Code 代码库入库：`knowledge/code/<科>/*.md` → `code_<科>` 集合。

代码实现独立成库（不进 L1/L2/L3），供「代码类」查询定向召回。
Section 级 KP 锚定：解析 H2/H3 下的 `> section_id/kp_ids/primary_kp` 头，
chunk 继承节级元数据，并写 `code:<section_id> ──teaches──→ KP` 边。

用法：
    PYTHONPATH=src uv run python scripts/ingest_code.py
    PYTHONPATH=src uv run python scripts/ingest_code.py --verify-only
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

CODE_DIR = ROOT / "knowledge" / "code"
LINKS_PATH = ROOT / "knowledge" / "knowledge_points" / "links.jsonl"

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

META_KEYS = ("section_id", "kp_ids", "primary_kp")


def load_kp_ids() -> set[str]:
    ids = set()
    for p in (ROOT / "knowledge" / "knowledge_points").glob("*.jsonl"):
        if p.name == "links.jsonl":
            continue
        for line in p.read_text(encoding="utf-8").splitlines():
            ids.add(json.loads(line)["id"])
    return ids


def parse_sections(text: str) -> tuple[str, list[dict]]:
    """解析文档头 + 带 section_id 元数据的 H2/H3 节（无 section_id 的标题为容器，跳过）。

    ★ body 边界 = **下一个 H2/H3 标题**（不是文件末尾）——否则每个 section 的 body
      会把后续所有内容吞进来，导致 chunk 重复膨胀。
    """
    document_id = ""
    for line in text.splitlines()[:20]:
        m = re.match(r">\s*document_id:\s*(\S+)", line)
        if m:
            document_id = m.group(1)
    lines = text.split("\n")
    sections: list[dict] = []
    i = 0
    while i < len(lines):
        m = re.match(r"^(#{2,3}) (.+)$", lines[i])
        if not m:
            i += 1
            continue
        # 下一个标题 = body 边界
        k = i + 1
        while k < len(lines) and not re.match(r"^#{2,3} ", lines[k]):
            k += 1
        meta: dict = {"title": m.group(2).strip()}
        j = i + 1
        while j < k:
            mm = re.match(r">\s*(section_id|primary_kp):\s*(\S+)", lines[j])
            mk = re.match(r">\s*kp_ids:\s*(\[[^\]]*\])", lines[j])
            if mm:
                meta[mm.group(1)] = mm.group(2)
            elif mk:
                raw = mk.group(1).strip("[]")
                meta["kp_ids"] = [x.strip() for x in raw.split(",") if x.strip()]
            elif lines[j].strip() == "":
                j += 1
                continue
            else:
                break
            j += 1
        if "section_id" in meta:
            meta["body"] = "\n".join(lines[j:k]).strip()
            sections.append(meta)
        i = k
    return document_id, sections


def ingest_subject(subject: str, kp_ids: set[str]) -> dict:
    """入库单个科目的代码文件到 `code_<科>` 集合，并写 teaches 边。"""
    dir_path = CODE_DIR / subject
    collection = SUBJECT_TO_COLLECTION[subject]
    mgr = get_vector_store_manager()
    if not dir_path.is_dir():
        # 无代码文件的科也建空集合：检索侧 `is_code` 会查 `code_<科>`，
        # 缺集合会刷 "Collection does not exist" 并白花一次 Chroma 往返。
        mgr.get_store(collection)
        return {
            "subject": subject,
            "collection": collection,
            "chunks": 0,
            "new": 0,
            "skipped": True,
        }

    code = SUBJECT_CODE[subject]
    chunks: list[Document] = []
    edges: list[dict] = []

    for path in sorted(dir_path.rglob("*.md")):
        text = path.read_text(encoding="utf-8")
        rel = str(path.relative_to(ROOT)).replace("\\", "/")
        document_id, sections = parse_sections(text)
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
                    "category": collection,
                },
            )
            for i, ch in enumerate(split_documents([doc]), 1):
                ch.metadata.update(
                    chunk_id=f"{sid}-{i:03d}",
                    kb_depth="code",
                    doc_role="code",
                    subject=code,
                    document_id=document_id or f"code-{code}",
                    section_id=sid,
                    knowledge_points=doc.metadata["knowledge_points"],
                )
                chunks.append(ch)

    ids = mgr.add_documents(chunks, collection_name=collection)
    mgr.wait_until_ready(collection)
    merge_edges(edges)
    return {"subject": subject, "collection": collection, "chunks": len(chunks), "new": len(ids)}


def merge_edges(edges: list[dict]) -> int:
    """UNIQUE(from, type, to) 去重后并入 links.jsonl，返回新增条数。"""
    existing = [
        json.loads(x) for x in LINKS_PATH.read_text(encoding="utf-8").splitlines() if x.strip()
    ]
    seen = {(e.get("from"), e.get("type"), e.get("to")) for e in existing}
    added = 0
    for e in edges:
        key = (e["from"], e["type"], e["to"])
        if key not in seen:
            existing.append(e)
            seen.add(key)
            added += 1
    LINKS_PATH.write_text(
        "\n".join(json.dumps(e, ensure_ascii=False) for e in existing) + "\n",
        encoding="utf-8",
    )
    return added


def verify(kp_ids: set[str]) -> list[str]:
    """回链校验：chunk 元数据链 + teaches 边双向存在性。"""
    import chromadb

    fails: list[str] = []
    links = [
        json.loads(x) for x in LINKS_PATH.read_text(encoding="utf-8").splitlines() if x.strip()
    ]
    teaches = {
        e["from"].split(":", 1)[-1]: e["to"] for e in links if e.get("type") == "teaches"
    }  # from 侧 sid → KP（多 KP 节会被覆盖，仅用于存在性检查）
    teaches_pairs = {(e["from"], e["to"]) for e in links if e.get("type") == "teaches"}
    client = chromadb.PersistentClient(path=str(ROOT / "chroma_db"))
    n_chunks = 0
    for subject, collection in SUBJECT_TO_COLLECTION.items():
        try:
            col = client.get_collection(collection)
        except Exception:
            fails.append(f"missing collection {collection}")
            continue
        got = col.get(where={"kb_depth": "code"}, include=["metadatas"])
        for m in got.get("metadatas") or []:
            n_chunks += 1
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
            if kps and (f"code:{sid}", kps[0]) not in teaches_pairs:
                fails.append(f"no teaches edge for {sid}")
    print(f"[回链] code_chunks={n_chunks} teaches={len(teaches)}")
    return fails


def main() -> int:
    verify_only = "--verify-only" in sys.argv
    kp_ids = load_kp_ids()
    if not verify_only:
        for subject in SUBJECT_TO_COLLECTION:
            print(ingest_subject(subject, kp_ids))
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
