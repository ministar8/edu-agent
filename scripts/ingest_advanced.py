"""L2 Advanced 入库 + trains 边 + 回链/负向验收。

用法：
    PYTHONPATH=src uv run python scripts/ingest_advanced.py
    PYTHONPATH=src uv run python scripts/ingest_advanced.py --verify-only
    PYTHONPATH=src uv run python scripts/ingest_advanced.py knowledge/advanced/data_structure/03_tree.md
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

ADVANCED_DIR = ROOT / "knowledge" / "advanced"
LINKS_PATH = ROOT / "knowledge" / "knowledge_points" / "links.jsonl"
KP_DIR = ROOT / "knowledge" / "knowledge_points"

# 目录名 → subject 短码（与 chunk.schema / metadata 约定一致）
SUBJECT_CODE = {
    "data_structure": "ds",
    "computer_organization": "co",
    "operating_system": "os",
    "computer_network": "cn",
}
SUBJECT_TO_COLLECTION = {
    "data_structure": "data_structure",
    "computer_organization": "computer_organization",
    "operating_system": "operating_system",
    "computer_network": "computer_network",
}

# topic_tags 白名单（仅题型/形态；「综合」走 scope=cross）
TOPIC_TAGS_OK = {"选择", "计算", "代码", "填空", "分析"}
# L2 禁止的营销/书商/应试话术
FORBIDDEN_WORDS = re.compile(
    r"王道|出版社|应试|必考|押题|刷题|常考|考点|真题汇编|第\s*\d+\s*页|p\.\s*\d+",
    re.I,
)
# 整题特征：选项行 / 标准答案标记（L3 职责，不得进 L2）
FULL_EXAM_RE = re.compile(
    r"(^|\n)\s*A[.、．].*(\n\s*B[.、．].*){2,}|【答案】|标准答案[:：]|答案[:：]\s*[A-DＡ-Ｄ]",
    re.I,
)
# 方法维度：至少命中一种（非强制四件套）
METHOD_DIM_RE = re.compile(
    r"识别信号|方法步骤|计算流程|分析方法|易错点|变式|代码模板|综合拆解|解题步骤|处理路径",
)
EXAM_REF_RE = re.compile(r"^question:\d{4}-Q\d+$")
SKIP_SECTIONS = {"本章解决什么", "学习目标", "对照", "锚定"}


def load_kp_ids() -> set[str]:
    ids: set[str] = set()
    for p in KP_DIR.glob("*.jsonl"):
        if p.name == "links.jsonl":
            continue
        for line in p.read_text(encoding="utf-8").splitlines():
            if line.strip():
                ids.add(json.loads(line)["id"])
    return ids


def _parse_list(raw: str) -> list[str]:
    """解析 `[a, b]` 或逗号分隔列表。"""
    raw = raw.strip().strip("[]")
    return [x.strip().strip("'\"") for x in raw.split(",") if x.strip()]


def _parse_blockquote_meta(lines: list[str]) -> dict:
    """解析 `> key: value` 与多行列表（related_exams）。"""
    meta: dict = {}
    current_list: str | None = None
    for line in lines:
        if not line.startswith(">"):
            if current_list:
                current_list = None
            continue
        content = line.lstrip(">").strip()
        if not content:
            continue
        if current_list and content.startswith("-"):
            meta.setdefault(current_list, []).append(content.lstrip("- ").strip())
            continue
        current_list = None
        m = re.match(r"([A-Za-z_]+)\s*:\s*(.*)$", content)
        if not m:
            continue
        key, val = m.group(1), m.group(2).strip()
        if val == "":
            current_list = key
            meta[key] = []
            continue
        if key in {"kp_ids", "topic_tags", "related_exams"}:
            meta[key] = _parse_list(val)
        elif key == "difficulty":
            try:
                meta[key] = int(val)
            except ValueError:
                pass
        else:
            meta[key] = val
    return meta


def parse_advanced_doc(text: str, rel_path: str) -> dict:
    """解析 L2 文档：文档级元数据 + section 列表。"""
    head = _parse_blockquote_meta(text.splitlines()[:30])
    domain_kp = head.get("domain_kp", "")
    document_id = head.get("document_id", "")
    parts = re.split(r"(?m)^(## .+)$", text)
    sections: list[dict] = []
    for i in range(1, len(parts) - 1, 2):
        heading = parts[i].strip()
        body = parts[i + 1]
        title = heading.lstrip("# ").strip()
        if any(title.startswith(s) or s in title for s in SKIP_SECTIONS):
            continue
        meta = _parse_blockquote_meta(body.splitlines()[:40])
        meta["title"] = title
        body_clean = "\n".join(
            ln for ln in body.splitlines() if not ln.lstrip().startswith(">")
        ).strip()
        meta["body"] = body_clean
        meta.setdefault("section_id", "")
        meta.setdefault("kp_ids", [])
        meta.setdefault("primary_kp", "")
        meta.setdefault("topic_tags", [])
        meta.setdefault("related_exams", [])
        meta.setdefault("scope", "single")
        sections.append(meta)
    return {
        "domain_kp": domain_kp,
        "document_id": document_id,
        "kb_depth": head.get("kb_depth", "advanced"),
        "doc_role": head.get("doc_role", "method"),
        "sections": sections,
        "source": rel_path,
    }


def validate_section(sec: dict, doc: dict, kp_ids: set[str]) -> list[str]:
    """单节结构校验；返回失败项。"""
    fails: list[str] = []
    sid = sec.get("section_id") or ""
    tag = f"{doc['document_id']}::{sec.get('title', '?')}"
    if not sid:
        fails.append(f"{tag} missing section_id")
        return fails
    if not sec.get("body"):
        fails.append(f"{tag} empty body")
    if not METHOD_DIM_RE.search(sec.get("body") or ""):
        fails.append(f"{tag} no method dimension")
    kps = sec.get("kp_ids") or []
    if not kps:
        fails.append(f"{sid} empty kp_ids")
    for kp in kps:
        if kp not in kp_ids:
            fails.append(f"{sid} unknown KP {kp}")
    pk = sec.get("primary_kp") or ""
    if pk and pk not in kps:
        fails.append(f"{sid} primary_kp not in kp_ids: {pk}")
    scope = sec.get("scope") or "single"
    if scope == "cross" and len(kps) < 2:
        fails.append(f"{sid} scope=cross but kp_ids<2")
    for t in sec.get("topic_tags") or []:
        if t not in TOPIC_TAGS_OK:
            fails.append(f"{sid} bad topic_tag {t}")
    for e in sec.get("related_exams") or []:
        if not EXAM_REF_RE.match(e):
            fails.append(f"{sid} bad related_exams {e}")
    body = sec.get("body") or ""
    if FORBIDDEN_WORDS.search(body):
        fails.append(f"{sid} forbidden word")
    if FULL_EXAM_RE.search(body):
        fails.append(f"{sid} full exam in L2")
    # ID 链：section_id ⊂ document_id
    did = doc.get("document_id") or ""
    if did and not sid.startswith(did):
        fails.append(f"{sid} not under {did}")
    return fails


def ingest_files(paths: list[Path]) -> dict:
    """入库指定 Advanced 文档，写 trains 边。返回统计。"""
    kp_ids = load_kp_ids()
    mgr = get_vector_store_manager()
    by_col: dict[str, list[Document]] = {v: [] for v in SUBJECT_TO_COLLECTION.values()}
    trains: list[dict] = []
    sections_indexed: set[str] = set()
    parse_fails: list[str] = []
    stats = {"chunks": 0, "sections": 0, "docs": 0}

    for path in paths:
        rel = str(path.relative_to(ROOT)).replace("\\", "/")
        parsed = parse_advanced_doc(path.read_text(encoding="utf-8"), rel)
        subject_dir = path.parent.name
        subject = SUBJECT_CODE.get(subject_dir, subject_dir)
        collection = SUBJECT_TO_COLLECTION.get(subject_dir)
        if not collection:
            parse_fails.append(f"unknown subject dir {subject_dir}")
            continue
        if parsed["kb_depth"] != "advanced" or parsed["doc_role"] != "method":
            parse_fails.append(
                f"{rel} expect advanced/method got {parsed['kb_depth']}/{parsed['doc_role']}"
            )
        stats["docs"] += 1

        for sec in parsed["sections"]:
            parse_fails.extend(validate_section(sec, parsed, kp_ids))
            sid = sec["section_id"]
            if not sid or not sec["body"]:
                continue
            for kp in sec["kp_ids"]:
                if kp not in kp_ids:
                    continue
                trains.append({"from": f"advanced:{sid}", "to": kp, "type": "trains"})
            doc = Document(
                page_content=f"## {sec['title']}\n\n{sec['body']}",
                metadata={
                    "kb_depth": "advanced",
                    "doc_role": "method",
                    "subject": subject,
                    "document_id": parsed["document_id"],
                    "section_id": sid,
                    "domain_kp": parsed["domain_kp"],
                    "knowledge_points": json.dumps(sec["kp_ids"], ensure_ascii=False),
                    "primary_kp": sec["primary_kp"] or (sec["kp_ids"][0] if sec["kp_ids"] else ""),
                    "heading": sec["title"],
                    "topic_tags": json.dumps(sec["topic_tags"], ensure_ascii=False),
                    "scope": sec["scope"],
                    "related_exams": json.dumps(sec["related_exams"], ensure_ascii=False),
                    "source": rel,
                },
            )
            if sec.get("difficulty") is not None:
                doc.metadata["difficulty"] = int(sec["difficulty"])

            before = len(by_col[collection])
            for i, ch in enumerate(split_documents([doc]), 1):
                ch.metadata["chunk_id"] = f"{sid}-{i:03d}"
                ch.metadata["document_id"] = parsed["document_id"]
                ch.metadata["section_id"] = sid
                ch.metadata["kb_depth"] = "advanced"
                ch.metadata["doc_role"] = "method"
                ch.metadata["subject"] = subject
                ch.metadata["knowledge_points"] = json.dumps(sec["kp_ids"], ensure_ascii=False)
                ch.metadata["topic_tags"] = json.dumps(sec["topic_tags"], ensure_ascii=False)
                ch.metadata["scope"] = sec["scope"]
                ch.metadata["related_exams"] = json.dumps(sec["related_exams"], ensure_ascii=False)
                if sec.get("difficulty") is not None:
                    ch.metadata["difficulty"] = int(sec["difficulty"])
                by_col[collection].append(ch)
            # 短节：splitter 可能丢弃，仍保留单 chunk
            if len(by_col[collection]) == before:
                ch = Document(page_content=doc.page_content, metadata=dict(doc.metadata))
                ch.metadata["chunk_id"] = f"{sid}-001"
                ch.metadata["document_id"] = parsed["document_id"]
                ch.metadata["section_id"] = sid
                ch.metadata["kb_depth"] = "advanced"
                ch.metadata["doc_role"] = "method"
                ch.metadata["subject"] = subject
                ch.metadata["knowledge_points"] = json.dumps(sec["kp_ids"], ensure_ascii=False)
                by_col[collection].append(ch)
            sections_indexed.add(sid)
            stats["sections"] += 1

    total_new = 0
    for collection, chunks in by_col.items():
        if not chunks:
            continue
        ids = mgr.add_documents(chunks, collection_name=collection)
        mgr.wait_until_ready(collection)
        total_new += len(ids)
        stats["chunks"] += len(chunks)
        print(f"  [{collection}] chunks={len(chunks)} new={len(ids)}")

    # trains 边：UNIQUE(from, type, to)
    existing: list[dict] = []
    if LINKS_PATH.exists():
        for line in LINKS_PATH.read_text(encoding="utf-8").splitlines():
            if line.strip():
                existing.append(json.loads(line))
    seen = {(e.get("from"), e.get("type"), e.get("to")) for e in existing}
    added = 0
    for e in trains:
        key = (e["from"], e["type"], e["to"])
        if key not in seen:
            existing.append(e)
            seen.add(key)
            added += 1
    LINKS_PATH.write_text(
        "\n".join(json.dumps(e, ensure_ascii=False) for e in existing) + "\n",
        encoding="utf-8",
    )
    stats["trains_added"] = added
    stats["links_total"] = len(existing)
    stats["new_indexed"] = total_new
    stats["parse_fails"] = parse_fails
    stats["sections_indexed"] = sections_indexed
    print(
        f"trains_added={added} links_total={len(existing)} "
        f"new_indexed={total_new} sections={stats['sections']}"
    )
    if parse_fails:
        print(f"parse_fails={len(parse_fails)}")
        for x in parse_fails[:20]:
            print("  !", x)
    return stats


def test_backlink() -> list[str]:
    """回链：ID 链、KP 存在、trains 唯一且 from 指向已入库 section。"""
    fails: list[str] = []
    kp_ids = load_kp_ids()
    links = [
        json.loads(x) for x in LINKS_PATH.read_text(encoding="utf-8").splitlines() if x.strip()
    ]
    import chromadb

    client = chromadb.PersistentClient(path=str(ROOT / "chroma_db"))
    sec_ids: set[str] = set()
    n_chunks = 0
    for collection in SUBJECT_TO_COLLECTION.values():
        try:
            col = client.get_collection(collection)
        except Exception:
            continue
        got = col.get(where={"kb_depth": "advanced"}, include=["metadatas"])
        metas = got.get("metadatas") or []
        n_chunks += len(metas)
        for m in metas:
            cid = m.get("chunk_id") or ""
            sid = m.get("section_id") or ""
            did = m.get("document_id") or ""
            if not cid.startswith(sid) or not sid.startswith(did):
                fails.append(f"id chain {cid}")
            if m.get("doc_role") != "method":
                fails.append(f"{cid} doc_role={m.get('doc_role')}")
            try:
                kps = json.loads(m.get("knowledge_points") or "[]")
            except Exception:
                kps = []
                fails.append(f"bad kps {cid}")
            for kp in kps:
                if kp not in kp_ids:
                    fails.append(f"{cid} unknown {kp}")
            scope = m.get("scope") or "single"
            if scope == "cross" and len(kps) < 2:
                fails.append(f"{cid} cross but kps<2")
            sec_ids.add(sid)

    trains = [e for e in links if e.get("type") == "trains"]
    teaches = [e for e in links if e.get("type") == "teaches"]
    print(
        f"[回链] advanced_chunks={n_chunks} trains={len(trains)} "
        f"teaches={len(teaches)} sections={len(sec_ids)}"
    )
    if trains and n_chunks == 0:
        fails.append("trains edges exist but no advanced chunks")
    seen: set[tuple] = set()
    for e in trains + teaches:
        key = (e.get("from"), e.get("type"), e.get("to"))
        if key in seen:
            fails.append(f"dup link {key}")
        seen.add(key)
        if e["to"] not in kp_ids:
            fails.append(f"{e['type']} bad to {e['to']}")
        src = str(e["from"]).split(":", 1)[-1]
        prefix = str(e["from"]).split(":", 1)[0]
        if e["type"] == "trains":
            if prefix != "advanced":
                fails.append(f"trains bad prefix {e['from']}")
            if sec_ids and src not in sec_ids:
                fails.append(f"trains bad from {src}")
        if e["type"] == "teaches" and prefix != "basic":
            fails.append(f"teaches bad prefix {e['from']}")
    return fails


async def test_negative() -> list[str]:
    """负向：L2 不含整题/书商话术；方法问能召到 advanced；答案问 top1 非 L2 方法。"""
    fails: list[str] = []
    from rag.retriever import aretrieve_evidence_with_retry

    async def top(query: str, k: int = 5):
        fused, _ = await aretrieve_evidence_with_retry(query=query, k=k)
        return list(getattr(fused, "text_evidences", []) or [])

    def depth(ev) -> str:
        return (getattr(ev, "metadata", {}) or {}).get("kb_depth") or ""

    # A. 方法正文可召回：L2 未做专用路由，旧讲义仍占位；
    #    要求多条方法 query 中至少一条在 top-k 命中 advanced（防 orphan）
    method_queries = [
        "BST 双支删除中序前驱后继怎么替换",
        "AVL 插入后最小不平衡子树怎么旋转",
        "由先序和中序还原二叉树的步骤",
        "哈夫曼编码 WPL 计算流程",
    ]
    hit_q = 0
    for q in method_queries:
        evs = await top(q, k=8)
        adv = [e for e in evs if depth(e) == "advanced"]
        print(f"[负向 A] {q!r} n={len(evs)} advanced={len(adv)}")
        if adv:
            hit_q += 1
    print(f"[负向 A] method-hit-queries={hit_q}/{len(method_queries)}")
    if hit_q == 0:
        fails.append("method queries never reach advanced")

    # B. L2 chunk 不得含整题+答案 / 书商话术
    import chromadb

    client = chromadb.PersistentClient(path=str(ROOT / "chroma_db"))
    for collection in SUBJECT_TO_COLLECTION.values():
        try:
            col = client.get_collection(collection)
        except Exception:
            continue
        got = col.get(where={"kb_depth": "advanced"}, include=["documents", "metadatas"])
        for d, m in zip(got.get("documents") or [], got.get("metadatas") or []):
            body = re.sub(r"^>.*$", "", d or "", flags=re.M)
            if FULL_EXAM_RE.search(body):
                fails.append(f"full exam {m.get('chunk_id')}")
            if FORBIDDEN_WORDS.search(body):
                fails.append(f"forbidden word {m.get('chunk_id')}")
            tags_raw = m.get("topic_tags") or "[]"
            try:
                tags = json.loads(tags_raw) if isinstance(tags_raw, str) else tags_raw
            except Exception:
                tags = []
                fails.append(f"bad topic_tags {m.get('chunk_id')}")
            for t in tags:
                if t not in TOPIC_TAGS_OK:
                    fails.append(f"tag leak {m.get('chunk_id')}:{t}")

    # C. 标准答案问 top1 不应是 advanced method（L3 未入库时允许 basic/其他，但不能是 L2 方法条）
    evs = await top("2019年408第5题标准答案")
    if evs:
        m0 = getattr(evs[0], "metadata", {}) or {}
        print(f"[负向 C] answer top1 kb={m0.get('kb_depth')} doc={m0.get('document_id')}")
        if m0.get("kb_depth") == "advanced" and m0.get("doc_role") == "method":
            # 仅当 top1 正文还像答案时判失败
            body = getattr(evs[0], "content", "") or ""
            if re.search(r"答案[:：]\s*[A-DＡ-Ｄ]|【答案】|正确选项", body):
                fails.append("exam-answer top1 advanced method")
    return fails


async def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    verify_only = "--verify-only" in sys.argv
    paths = [Path(a) for a in args] if args else sorted(ADVANCED_DIR.rglob("*.md"))
    paths = [p if p.is_absolute() else ROOT / p for p in paths]
    if not paths:
        print("no advanced md found")
        return 1
    if not verify_only:
        print("==== ingest advanced ====")
        for p in paths:
            print(" ", p.relative_to(ROOT))
        ingest_files(paths)
    print("==== KP 回链 ====")
    f1 = test_backlink()
    print("==== 负向检索 ====")
    f2 = await test_negative()
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
