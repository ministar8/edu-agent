"""L2 Advanced 入库：``knowledge/advanced/<科>/*.md`` → 四科集合（``kb_depth=advanced``）。

方法层（``doc_role=method``）：``## section`` = 一个 Document；写
``advanced:<sid> ──trains──→ KP``。
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from langchain_core.documents import Document

from rag.ingest_layers import _shared
from rag.vectorstore import get_vector_store_manager

ADVANCED_DIR = _shared.KNOWLEDGE_DIR / "advanced"

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

TOPIC_TAGS_OK = {"选择", "计算", "代码", "填空", "分析"}
FORBIDDEN_WORDS = re.compile(
    r"王道|出版社|应试|必考|押题|刷题|常考|考点|真题汇编|第\s*\d+\s*页|p\.\s*\d+", re.I
)
FULL_EXAM_RE = re.compile(
    r"(^|\n)\s*A[.、．].*(\n\s*B[.、．].*){2,}|【答案】|标准答案[:：]|答案[:：]\s*[A-DＡ-Ｄ]",
    re.I,
)
METHOD_DIM_RE = re.compile(
    r"识别信号|方法步骤|计算流程|分析方法|易错点|变式|代码模板|综合拆解|解题步骤|处理路径"
)
EXAM_REF_RE = re.compile(r"^question:\d{4}-Q\d+$")
SKIP_SECTIONS = {"本章解决什么", "学习目标", "对照", "锚定"}


def _parse_list(raw: str) -> list[str]:
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
    head = _parse_blockquote_meta(text.splitlines()[:30])
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
        "domain_kp": head.get("domain_kp", ""),
        "document_id": head.get("document_id", ""),
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
        return [f"{tag} missing section_id"]
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
    if (sec.get("scope") or "single") == "cross" and len(kps) < 2:
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
    did = doc.get("document_id") or ""
    if did and not sid.startswith(did):
        fails.append(f"{sid} not under {did}")
    return fails


def build(
    kp_ids: set[str], paths: list[Path] | None = None
) -> tuple[dict[str, list[Document]], list[dict], dict]:
    """构建四科 advanced chunk（纯函数：不落库、不写 links）。"""
    if paths is None:
        paths = sorted(ADVANCED_DIR.rglob("*.md"))
    by_col: dict[str, list[Document]] = {v: [] for v in SUBJECT_TO_COLLECTION.values()}
    trains: list[dict] = []
    parse_fails: list[str] = []
    stats = {"chunks": 0, "sections": 0, "docs": 0, "parse_fails": parse_fails}

    for path in paths:
        rel = str(path.relative_to(_shared.ROOT)).replace("\\", "/")
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
            extra = {
                "kb_depth": "advanced",
                "doc_role": "method",
                "subject": subject,
                "knowledge_points": json.dumps(sec["kp_ids"], ensure_ascii=False),
                "topic_tags": json.dumps(sec["topic_tags"], ensure_ascii=False),
                "scope": sec["scope"],
                "related_exams": json.dumps(sec["related_exams"], ensure_ascii=False),
            }
            if sec.get("difficulty") is not None:
                extra["difficulty"] = int(sec["difficulty"])
            by_col[collection].extend(_shared.split_section(doc, sid, extra, keep_short=True))
            stats["sections"] += 1
    stats["chunks"] = sum(len(v) for v in by_col.values())
    return by_col, trains, stats


def ingest(kp_ids: set[str], paths: list[Path] | None = None) -> dict:
    mgr = get_vector_store_manager()
    by_col, trains, stats = build(kp_ids, paths)
    total_new = 0
    for collection, chunks in by_col.items():
        if not chunks:
            continue
        ids = mgr.add_documents(chunks, collection_name=collection)
        mgr.wait_until_ready(collection)
        total_new += len(ids)
        print(f"  [{collection}] chunks={len(chunks)} new={len(ids)}")
    added = _shared.merge_links(trains)
    stats["trains_added"] = added
    stats["new_indexed"] = total_new
    print(
        f"trains_added={added} new_indexed={total_new} sections={stats['sections']} "
        f"parse_fails={len(stats['parse_fails'])}"
    )
    return stats
