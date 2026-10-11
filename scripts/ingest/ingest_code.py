"""Code 代码库入库：``knowledge/code/<科>/*.md`` → ``code_<科>`` 集合。

构建逻辑已下沉到 ``rag.ingest_layers.code``；本脚本只做 CLI + 验收。

用法：
    PYTHONPATH=src uv run python scripts/ingest/ingest_code.py
    PYTHONPATH=src uv run python scripts/ingest/ingest_code.py --verify-only
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from rag.ingest_layers import _shared  # noqa: E402
from rag.ingest_layers import code as code_layer  # noqa: E402

SUBJECT_TO_COLLECTION = code_layer.SUBJECT_TO_COLLECTION
LINKS_PATH = _shared.LINKS_PATH
load_kp_ids = _shared.load_kp_ids


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
        code_layer.ingest_all(kp_ids)
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
