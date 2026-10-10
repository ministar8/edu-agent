"""各入库层共用的胶水：KP 载入、links 合并、章节头解析。

这些函数原先散落在 ``scripts/ingest_*.py`` 里（且互相 import），现下沉到
``src/rag/``，让**脚本**与**检索门禁**共用同一份实现（门禁据此走生产入库路径）。
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from langchain_core.documents import Document

from rag.chunking.splitter import split_documents

# knowledge/ 目录（src/rag/ingest_layers/_shared.py → parents[3] = 仓库根）
ROOT = Path(__file__).resolve().parents[3]
KNOWLEDGE_DIR = ROOT / "knowledge"
KP_DIR = KNOWLEDGE_DIR / "knowledge_points"
LINKS_PATH = KP_DIR / "links.jsonl"


def load_kp_ids() -> set[str]:
    """读出四科 KP 的全部 id（``links.jsonl`` 不算节点）。"""
    ids: set[str] = set()
    for p in KP_DIR.glob("*.jsonl"):
        if p.name == "links.jsonl":
            continue
        for line in p.read_text(encoding="utf-8").splitlines():
            if line.strip():
                ids.add(json.loads(line)["id"])
    return ids


def merge_links(edges: list[dict], links_path: Path = LINKS_PATH) -> int:
    """把边按 ``UNIQUE(from, type, to)`` 去重后并入 links.jsonl，返回新增条数。"""
    existing: list[dict] = []
    if links_path.exists():
        for line in links_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                existing.append(json.loads(line))
    seen = {(e.get("from"), e.get("type"), e.get("to")) for e in existing}
    added = 0
    for e in edges:
        key = (e["from"], e["type"], e["to"])
        if key not in seen:
            existing.append(e)
            seen.add(key)
            added += 1
    links_path.write_text(
        "\n".join(json.dumps(e, ensure_ascii=False) for e in existing) + "\n",
        encoding="utf-8",
    )
    return added


def parse_sections(text: str) -> tuple[str, list[dict]]:
    """解析文档头 + 带 ``section_id`` 元数据的 H2/H3 节（无 section_id 的标题为容器，跳过）。

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


def split_section(
    doc: Document, sid: str, extra_meta: dict, *, keep_short: bool = True
) -> list[Document]:
    """把一节 Document 切分，并给每个 chunk 打上 ``chunk_id`` 与继承元数据。

    ``keep_short=True``：splitter 因 ``MIN_CHUNK_LENGTH`` 丢弃过短节时，仍保留整节为单 chunk
    （``basic`` / ``advanced`` 的行为）；``False`` 则不加兜底（``code`` / ``exam_practice``）。
    """
    chunks: list[Document] = []
    for i, ch in enumerate(split_documents([doc]), 1):
        ch.metadata["chunk_id"] = f"{sid}-{i:03d}"
        ch.metadata.update(extra_meta)
        chunks.append(ch)
    if not chunks and keep_short:
        ch = Document(page_content=doc.page_content, metadata=dict(doc.metadata))
        ch.metadata["chunk_id"] = f"{sid}-001"
        ch.metadata.update(extra_meta)
        chunks.append(ch)
    return chunks
