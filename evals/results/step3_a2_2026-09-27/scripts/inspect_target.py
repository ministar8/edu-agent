"""取 #18 目标 chunk 的原文 + 直测 rerank 分（改动前基线）。"""

from __future__ import annotations

import re

import httpx

from core.settings import settings

QUERY = "用信号量写出生产者—消费者问题的伪代码。"
HEADING_RE = re.compile(r"^(?:\[[^\]]*\]\s*(?:>\s*)*)+\n")


def find_targets() -> list[tuple[str, str, dict]]:
    from rag.vectorstore import get_vector_store_manager

    mgr = get_vector_store_manager()
    out: list[tuple[str, str, dict]] = []
    for cat in ("operating_system", "questions", "data_structure"):
        col = mgr.client.get_collection(cat)
        res = col.get(include=["documents", "metadatas"])
        for cid, txt, meta in zip(res["ids"], res["documents"], res["metadatas"]):
            src = str((meta or {}).get("source_file") or (meta or {}).get("source") or "")
            sec = str((meta or {}).get("section.path") or (meta or {}).get("heading_path") or "")
            if "06_代码实现" in src and "生产者进程" in sec:
                out.append((cid, txt or "", meta or {}))
    return out


def score(texts: list[str], query: str = QUERY) -> list[dict]:
    url = f"{settings.RERANK_LOCAL_URL}/rerank"
    payload = {"query": query, "texts": texts, "top_n": len(texts)}
    with httpx.Client(timeout=60) as client:
        resp = client.post(url, json=payload)
        resp.raise_for_status()
    return resp.json()


def main() -> None:
    settings.SEMANTIC_CACHE_ENABLED = False
    targets = find_targets()
    print(f"找到目标 chunk {len(targets)} 个\n")

    texts_current: list[str] = []
    for cid, txt, meta in targets:
        print("=" * 66)
        print("chunk_id  :", cid)
        print("section   :", meta.get("section.path"))
        print("content_type:", meta.get("content_type"), "| chunk_role:", meta.get("chunk_role"))
        print("--- page_content 原文（前 700 字）---")
        print(txt[:700])
        stripped = HEADING_RE.sub("", txt)
        print("--- 现 rerank 实际送入的文本（剥掉 heading_path 后，前 300 字）---")
        print(stripped[:300])
        texts_current.append(stripped[:2000])

    print()
    print("=" * 66)
    print("直测 rerank（当前实现：剥掉 heading_path）")
    for item in score(texts_current):
        idx = item["index"]
        print(f"  score={item['score']:.4f}  chunk={targets[idx][0]}")

    # 对照：把 heading_path（section.path）作为自然语言前缀加回去
    print()
    print("=" * 66)
    print("对照：把 section.path 作为自然语言前缀附加")
    enriched = []
    for cid, txt, meta in targets:
        sec = str(meta.get("section.path") or "")
        sec_nl = " > ".join(p.strip("[]") for p in sec.split(">")) if sec else ""
        body = HEADING_RE.sub("", txt)[:2000]
        enriched.append(f"[{sec_nl}]\n{body}" if sec_nl else body)
    for item in score(enriched):
        idx = item["index"]
        print(f"  score={item['score']:.4f}  chunk={targets[idx][0]}")


if __name__ == "__main__":
    main()
