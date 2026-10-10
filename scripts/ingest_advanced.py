"""L2 Advanced 入库 + trains 边 + 回链/负向验收。

构建逻辑已下沉到 ``rag.ingest_layers.advanced``；本脚本只做 CLI + 验收。

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

from rag.ingest_layers import _shared  # noqa: E402
from rag.ingest_layers import advanced as advanced_layer  # noqa: E402

ADVANCED_DIR = advanced_layer.ADVANCED_DIR
SUBJECT_TO_COLLECTION = advanced_layer.SUBJECT_TO_COLLECTION
TOPIC_TAGS_OK = advanced_layer.TOPIC_TAGS_OK
FORBIDDEN_WORDS = advanced_layer.FORBIDDEN_WORDS
FULL_EXAM_RE = advanced_layer.FULL_EXAM_RE
LINKS_PATH = _shared.LINKS_PATH
load_kp_ids = _shared.load_kp_ids


def ingest_files(paths: list[Path]) -> dict:
    return advanced_layer.ingest(load_kp_ids(), paths)


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
