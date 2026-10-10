"""L3 章节题型入库：``knowledge/exams/<科>.md``（常考题型与例题）→ ``exams`` 集合。

构建逻辑已下沉到 ``rag.ingest_layers.exam_practice``；本脚本只做 CLI + 验收。

用法：
    PYTHONPATH=src uv run python scripts/ingest_exam_practice.py
    PYTHONPATH=src uv run python scripts/ingest_exam_practice.py --verify-only
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rag.ingest_layers import _shared  # noqa: E402
from rag.ingest_layers import exam_practice as practice_layer  # noqa: E402

COLLECTION = practice_layer.COLLECTION
SUBJECT_CODE = practice_layer.SUBJECT_CODE
LINKS_PATH = _shared.LINKS_PATH
load_kp_ids = _shared.load_kp_ids


def verify(kp_ids: set[str]) -> list[str]:
    """回链校验：exam-practice chunk 的 id 链 + trains 边双向存在性。"""
    import chromadb

    fails: list[str] = []
    links = [
        json.loads(x) for x in LINKS_PATH.read_text(encoding="utf-8").splitlines() if x.strip()
    ]
    trains_pairs = {(e["from"], e["to"]) for e in links if e.get("type") == "trains"}
    client = chromadb.PersistentClient(path=str(ROOT / "chroma_db"))
    try:
        col = client.get_collection(COLLECTION)
    except Exception:
        return [f"missing collection {COLLECTION}"]
    got = col.get(
        where={"document_id": {"$in": [f"exam-practice-{c}" for c in SUBJECT_CODE.values()]}},
        include=["metadatas"],
    )
    n = 0
    for m in got.get("metadatas") or []:
        n += 1
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
        if kps and (f"practice:{sid}", kps[0]) not in trains_pairs:
            fails.append(f"no trains edge for {sid}")
    print(f"[回链] practice_chunks={n} trains_pairs={len(trains_pairs)}")
    return fails


def main() -> int:
    verify_only = "--verify-only" in sys.argv
    kp_ids = load_kp_ids()
    if not verify_only:
        practice_layer.ingest(kp_ids)
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
