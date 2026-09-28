"""试点验证：KP 回链测试 + 负向检索测试。

1) 回链：chunk → section → document → KP / teaches
2) 负向：错误锚定、越层内容、离题查询
"""

from __future__ import annotations

import asyncio
import json
import re
import sys
from pathlib import Path

ROOT = Path(r"C:\Users\26452\Desktop\edu-agent")
sys.path.insert(0, str(ROOT / "src"))

KP_DIR = ROOT / "knowledge" / "knowledge_points"
DOC_ID = "basic-ds-tree"

EXAM_WORDS = re.compile(r"选择题|计算题|真题|常考|考点|刷题|王道|应试")


def load_kp_ids() -> set[str]:
    ids = set()
    for p in KP_DIR.glob("*.jsonl"):
        if p.name == "links.jsonl":
            continue
        for line in p.read_text(encoding="utf-8").splitlines():
            ids.add(json.loads(line)["id"])
    return ids


def load_links() -> list[dict]:
    p = KP_DIR / "links.jsonl"
    if not p.exists():
        return []
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]


def test_backlink() -> list[str]:
    fails = []
    kp_ids = load_kp_ids()
    links = load_links()

    import chromadb

    col = chromadb.PersistentClient(path=str(ROOT / "chroma_db")).get_collection("data_structure")
    got = col.get(where={"document_id": DOC_ID}, include=["metadatas"])
    metas = got.get("metadatas") or []
    print(f"[回链] store chunks={len(metas)}")
    if not metas:
        fails.append("no pilot chunks in store")
        return fails

    sec_ids = set()
    for m in metas:
        cid = m.get("chunk_id") or ""
        sid = m.get("section_id") or ""
        did = m.get("document_id") or ""
        if not cid.startswith(sid):
            fails.append(f"chunk_id not under section: {cid}")
        if not sid.startswith(did):
            fails.append(f"section_id not under document: {sid}")
        if did != DOC_ID:
            fails.append(f"document_id mismatch: {did}")
        if m.get("kb_depth") != "basic":
            fails.append(f"kb_depth {m.get('kb_depth')}")
        raw = m.get("knowledge_points") or "[]"
        try:
            kps = json.loads(raw) if isinstance(raw, str) else list(raw)
        except Exception:
            kps = []
            fails.append(f"bad knowledge_points on {cid}")
        for kp in kps:
            if kp not in kp_ids:
                fails.append(f"{cid} -> unknown KP {kp}")
        sec_ids.add(sid)

    # teaches 边
    teaches = [
        e
        for e in links
        if e.get("type") == "teaches" and str(e.get("from", "")).startswith("basic:")
    ]
    print(f"[回链] teaches edges={len(teaches)}")
    for e in teaches:
        if e["to"] not in kp_ids:
            fails.append(f"teaches to unknown KP {e['to']}")
        src = e["from"].split(":", 1)[-1]
        if src not in sec_ids:
            # 本章对照表跳过的节不应有边
            fails.append(f"teaches from unknown section {src}")

    # 每个有 kp 的 section 至少一条 teaches
    for sid in sec_ids:
        mine = [e for e in teaches if e["from"] == f"basic:{sid}"]
        # tree_concept 故意无 KP
        if sid.endswith("tree_concept"):
            if mine:
                fails.append(f"intro section should have no teaches: {sid}")
        elif not mine:
            fails.append(f"section missing teaches: {sid}")
    print("[回链] ok" if not fails else f"[回链] FAIL {fails[:5]}")
    return fails


async def test_negative() -> list[str]:
    fails = []
    from rag.retriever import aretrieve_evidence_with_retry

    async def top(query: str, k: int = 5):
        fused, _ = await aretrieve_evidence_with_retry(query=query, k=k)
        return list(getattr(fused, "text_evidences", []) or [])

    # A. 离题查询：不应以 basic-ds-tree 为唯一/绝对主导
    evs = await top("IPv4 子网划分怎么做")
    pilot = [
        e for e in evs if str((getattr(e, "metadata", {}) or {}).get("document_id", "")) == DOC_ID
    ]
    print(f"[负向 A 离题] n={len(evs)} pilot_hits={len(pilot)}")
    if evs and len(pilot) == len(evs):
        fails.append("off-topic query fully answered by tree pilot")

    # B. L2 技巧查询：basic 不得假装含解题步骤
    evs = await top("BST 删除的三种情况怎么解题")
    bad = []
    for e in evs:
        meta = getattr(e, "metadata", {}) or {}
        if meta.get("document_id") != DOC_ID:
            continue
        text = getattr(e, "content", "") or ""
        if re.search(r"先判断删除|三种情况分别|答题步骤|解题步骤", text):
            bad.append(meta.get("chunk_id"))
    print(
        f"[负向 B L2技巧] pilot_hits={sum(1 for e in evs if (getattr(e, 'metadata', {}) or {}).get('document_id') == DOC_ID)} trick_chunks={bad}"
    )
    if bad:
        fails.append(f"L1 chunk contains L2 tactics: {bad}")

    # C. 元数据不得含考试导向词（正文）
    import chromadb

    col = chromadb.PersistentClient(path=str(ROOT / "chroma_db")).get_collection("data_structure")
    got = col.get(where={"document_id": DOC_ID}, include=["documents", "metadatas"])
    for d, m in zip(got.get("documents") or [], got.get("metadatas") or []):
        body = re.sub(r"^>.*$", "", d or "", flags=re.M)
        if EXAM_WORDS.search(body):
            fails.append(f"exam wording in {m.get('chunk_id')}")

    # D. 真题索取答案：不得把 basic 当答案权威 top1（允许出现概念）
    evs = await top("2019年408第5题标准答案")
    if evs:
        m0 = getattr(evs[0], "metadata", {}) or {}
        if m0.get("document_id") == DOC_ID:
            fails.append("exam-answer query top1 is basic tree")
        print(f"[负向 D 真题答案] top1={m0.get('document_id')} / {m0.get('source')}")
    return fails


async def main() -> int:
    print("========== KP 回链测试 ==========")
    f1 = test_backlink()
    print()
    print("========== 负向检索测试 ==========")
    f2 = await test_negative()
    fails = f1 + f2
    print()
    if fails:
        print("FAIL", len(fails))
        for x in fails:
            print(" -", x)
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
