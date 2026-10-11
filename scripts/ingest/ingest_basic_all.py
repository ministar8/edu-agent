"""L1 Basic 全科入库（ds/co/os/cn）+ KP 回链 / 负向验收。

构建逻辑已下沉到 ``rag.ingest_layers.basic``；本脚本只做 CLI + 验收。

用法：
    PYTHONPATH=src python scripts/ingest/ingest_basic_all.py
    PYTHONPATH=src python scripts/ingest/ingest_basic_all.py --verify-only
"""

from __future__ import annotations

import asyncio
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from rag.ingest_layers import _shared  # noqa: E402
from rag.ingest_layers import basic as basic_layer  # noqa: E402

SUBJECT_TO_COLLECTION = basic_layer.SUBJECT_TO_COLLECTION
LINKS_PATH = _shared.LINKS_PATH
KP_DIR = _shared.KP_DIR
load_kp_ids = _shared.load_kp_ids
EXAM_WORDS = re.compile(r"选择题|计算题|真题|常考|考点|刷题|王道|应试")


def ingest_all() -> None:
    basic_layer.ingest(_shared.load_kp_ids())


def test_backlink() -> list[str]:
    fails = []
    kp_ids = load_kp_ids()
    links = [
        json.loads(x) for x in LINKS_PATH.read_text(encoding="utf-8").splitlines() if x.strip()
    ]
    import chromadb

    client = chromadb.PersistentClient(path=str(ROOT / "chroma_db"))
    sec_ids = set()
    n_chunks = 0
    for collection in SUBJECT_TO_COLLECTION.values():
        col = client.get_collection(collection)
        got = col.get(where={"kb_depth": "basic"}, include=["metadatas"])
        metas = got.get("metadatas") or []
        n_chunks += len(metas)
        for m in metas:
            cid = m.get("chunk_id") or ""
            sid = m.get("section_id") or ""
            did = m.get("document_id") or ""
            if not cid.startswith(sid) or not sid.startswith(did):
                fails.append(f"id chain {cid}")
            try:
                kps = json.loads(m.get("knowledge_points") or "[]")
            except Exception:
                kps = []
                fails.append(f"bad kps {cid}")
            for kp in kps:
                if kp not in kp_ids:
                    fails.append(f"{cid} unknown {kp}")
            sec_ids.add(sid)
    teaches = [e for e in links if e.get("type") == "teaches"]
    print(f"[回链] basic_chunks={n_chunks} teaches={len(teaches)} sections={len(sec_ids)}")
    for e in teaches:
        if e["to"] not in kp_ids:
            fails.append(f"teaches bad to {e['to']}")
        src = str(e["from"]).split(":", 1)[-1]
        if e["from"].startswith("basic:") and src not in sec_ids:
            fails.append(f"teaches bad from {src}")
    return fails


async def test_negative() -> list[str]:
    fails = []
    from rag.retrieval.retriever import aretrieve_evidence_with_retry

    async def top(query: str, k: int = 5):
        fused, _ = await aretrieve_evidence_with_retry(query=query, k=k)
        return list(getattr(fused, "text_evidences", []) or [])

    def is_basic(ev) -> bool:
        return (getattr(ev, "metadata", {}) or {}).get("kb_depth") == "basic"

    evs = await top("IPv4 子网划分怎么做")
    b = sum(1 for e in evs if is_basic(e))
    print(f"[负向 A] n={len(evs)} basic={b}")
    if evs and b == len(evs):
        fails.append("off-topic all basic")

    evs = await top("BST 删除的三种情况怎么解题")
    bad = []
    for e in evs:
        meta = getattr(e, "metadata", {}) or {}
        if meta.get("kb_depth") != "basic":
            continue
        if re.search(r"先判断删除|三种情况分别|答题步骤|解题步骤", getattr(e, "content", "") or ""):
            bad.append(meta.get("chunk_id"))
    print(f"[负向 B] trick={bad}")
    if bad:
        fails.append(f"L2 leak {bad}")

    evs = await top("2019年408第5题标准答案")
    if evs:
        m0 = getattr(evs[0], "metadata", {}) or {}
        print(f"[负向 D] top1 kb={m0.get('kb_depth')} doc={m0.get('document_id')}")
        if m0.get("kb_depth") == "basic":
            fails.append("exam-answer top1 basic")

    import chromadb

    client = chromadb.PersistentClient(path=str(ROOT / "chroma_db"))
    for collection in SUBJECT_TO_COLLECTION.values():
        col = client.get_collection(collection)
        got = col.get(where={"kb_depth": "basic"}, include=["documents", "metadatas"])
        for d, m in zip(got.get("documents") or [], got.get("metadatas") or []):
            body = re.sub(r"^>.*$", "", d or "", flags=re.M)
            if EXAM_WORDS.search(body):
                fails.append(f"exam word {m.get('chunk_id')}")
    return fails


async def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if mode != "--verify-only":
        print("==== ingest all basic ====")
        ingest_all()
    print("==== KP 回链 ====")
    f1 = test_backlink()
    print("==== 负向检索 ====")
    f2 = await test_negative()
    fails = f1 + f2
    if fails:
        print("FAIL", len(fails))
        for x in fails[:25]:
            print(" -", x)
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
