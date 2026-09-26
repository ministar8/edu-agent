"""零成本问题盘点：一次性取齐各项判定所需的数据（不花 LLM 费用）。

输出四块：
  A. #9 / #17 的学科推断到底命中了哪些关键词（核实 C 阶段靶心）
  B. #18 目标 chunk 单独送 rerank 的分数（判定 A2 是否必要）
  C. #4 / #18 的**完整** rerank 排序 vs `top_n` 截断（判定 A3′ 靶心）
  D. 全库「被改写但字面不可匹配」的术语规模（BM25 失效面）
"""

from __future__ import annotations

import asyncio
import re

import chromadb
from langchain_core.documents import Document

from core.settings import settings
from rag.rag_utils import normalize_query_text
from rag.recall import (
    _COLLECTION_KEYWORDS,
    _contains_collection_keyword,
    _infer_subject_collections,
)
from rag.synonyms import SYNONYM_MAP, expand_query_with_synonyms

settings.RERANK_ENABLED = True  # 让 rerank 真正打分（本地 TEI，零成本）

C = chromadb.PersistentClient(path=settings.CHROMA_PERSIST_DIR)

QUERIES = {
    9: "请出一道考查磁盘空闲空间管理的题。",
    17: "用 C 语言写一段程序打印 float 的 32 位二进制表示，并说明如何据此读出阶码与尾数。",
    18: "用信号量写出生产者—消费者问题的伪代码。",
    4: "折半查找的适用条件是什么？",
}

TARGETS = {
    4: ("data_structure", "07_查找.md", "2.1", "关键码有序"),
    18: ("operating_system", "06_代码实现.md", "生产者进程", None),
}


def _matched_keywords(query: str) -> dict[str, list[str]]:
    normalized = normalize_query_text(query)
    expanded = expand_query_with_synonyms(normalized, max_expansions=6)
    compact = re.sub(r"\s+", "", expanded)
    out: dict[str, list[str]] = {}
    for col, kws in _COLLECTION_KEYWORDS.items():
        hits = [
            k
            for k in kws
            if _contains_collection_keyword(normalized, k)
            or _contains_collection_keyword(expanded, k)
            or _contains_collection_keyword(compact, k)
        ]
        if hits:
            out[col] = hits
    return out


def _target_doc(case: int) -> Document | None:
    col_name, src, sec, must = TARGETS[case]
    col = C.get_collection(col_name)
    r = col.get(where={"source_file": src}, include=["documents", "metadatas"])
    for text, meta in zip(r["documents"], r["metadatas"]):
        path = str(meta.get("section.path") or "")
        if sec in path and (must is None or must in (text or "")):
            return Document(page_content=text or "", metadata=dict(meta))
    return None


def _tei_available() -> tuple[bool, str]:
    """探测 TEI 的 embedding 与 rerank 是否都可用。

    本地 TEI 是**反复出现的故障点**（仓库文档记录过它宕机后闲置 24h，`restart=no`）。
    两个端点**必须都探**：只探 rerank 时，若 embedding 宕机，召回池会不完整，
    B/C 块仍会打印出「目标排名靠后」这类**看起来像结论的失真数据**。

    ★ 请求体 schema 两个端点不同（见 `docs/DOCKER.md` 的「TEI 端点契约」）：
    `/embeddings` 是 **OpenAI 兼容**（`input`），`/rerank` 是 **TEI 原生**（`query/texts`）。
    """
    import httpx

    problems: list[str] = []
    try:
        r = httpx.post(
            f"{settings.EMBEDDING_API_BASE}/embeddings",
            json={"model": settings.EMBEDDING_MODEL, "input": ["探活"]},
            timeout=15.0,
        )
        if r.status_code != 200:
            problems.append(f"embedding HTTP {r.status_code}")
    except Exception as exc:  # noqa: BLE001
        problems.append(f"embedding {type(exc).__name__}")
    try:
        r = httpx.post(
            f"{settings.RERANK_LOCAL_URL}/rerank",
            json={"query": "探活", "texts": ["探活"], "top_n": 1},
            timeout=15.0,
        )
        if r.status_code != 200:
            problems.append(f"rerank HTTP {r.status_code}")
    except Exception as exc:  # noqa: BLE001
        problems.append(f"rerank {type(exc).__name__}")
    return (not problems), "、".join(problems)


async def main() -> None:
    from rag.query_classifier import classify_query
    from rag.rag_utils import extract_query_terms
    from rag.reranker import rerank
    from rag.retriever import _amulti_route_search

    print("=" * 72)
    print("A. 学科推断命中词（C 阶段靶心）")
    print("=" * 72)
    for case in (9, 17):
        q = QUERIES[case]
        print(f"  #{case} {q[:44]}")
        print(f"     推断结果: {_infer_subject_collections(q)}")
        for col, hits in _matched_keywords(q).items():
            print(f"       ← {col}: {hits}")

    print()
    print("=" * 72)
    print("B/C. 目标 chunk 的 rerank 分与完整排名（A2 / A3′ 靶心）")
    print("=" * 72)
    ok, detail = _tei_available()
    if not ok:
        print(f"  [跳过] TEI 未就绪：{detail}")
        print("         embedding 或 rerank 任一不可用都会让 B/C 的数据失真")
        print("         （召回池不完整 / 分数全 None），打印出来会被误读成结论。")
        print("         恢复后重跑本脚本。")
    else:
        for case in (4, 18):
            q = QUERIES[case]
            doc = _target_doc(case)
            if doc is None:
                print(f"  #{case} 未找到目标 chunk")
                continue
            solo = rerank(
                q,
                [Document(page_content=doc.page_content, metadata={"content_hash": "x"})],
                top_k=1,
            )
            solo_score = solo[0].metadata.get("rerank_score")
            print(f"  #{case} 目标单独送 rerank = {solo_score}")

            terms = extract_query_terms(normalize_query_text(q))
            cat = classify_query(q, terms)
            pool = await _amulti_route_search(q, "", 5, cat=cat, use_rerank=True, terms=terms)
            docs = [d for d, _s in pool]
            print(
                f"     召回池 {len(docs)} 条 → 送 rerank 前 "
                f"{min(len(docs), 30)} 条（_RERANK_MAX_CANDIDATES=30）"
            )
            full = rerank(q, docs, top_k=len(docs))
            rank = next(
                (
                    i
                    for i, d in enumerate(full, 1)
                    if TARGETS[case][1] in str(d.metadata.get("source_file") or "")
                    and TARGETS[case][2] in str(d.metadata.get("section.path") or "")
                ),
                None,
            )
            plan_k = 6 if case == 18 else 5
            print(f"     完整重排后目标 rank = {rank}/{len(full)}   而 top_n = {plan_k}")

    print()
    print("=" * 72)
    print("D. BM25 失效面：被改写但字面不可匹配的术语")
    print("=" * 72)
    rewritten = {k: v for k, v in SYNONYM_MAP.items() if k != v}
    print(f"  SYNONYM_MAP 中会改写原文的条目: {len(rewritten)} / {len(SYNONYM_MAP)}")
    for col_name in (
        "computer_organization",
        "data_structure",
        "operating_system",
        "computer_network",
    ):
        col = C.get_collection(col_name)
        docs = col.get(include=["documents"], limit=col.count())["documents"]
        text = "".join(docs)
        sample = list(rewritten.items())[:0]
        zero = [k for k in rewritten if text.count(k) == 0 and text.count(rewritten[k]) > 0]
        print(f"  {col_name:<24} 该集合内「变体 0 次、标准词 >0 次」的术语数: {len(zero)}")
        sample = zero[:6]
        if sample:
            print(f"      例: {[(k, rewritten[k]) for k in sample]}")


if __name__ == "__main__":
    asyncio.run(main())
