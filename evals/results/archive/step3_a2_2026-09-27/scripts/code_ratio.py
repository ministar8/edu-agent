"""296 个带锚点 chunk 的「代码占比」分布 —— 决定 A2 是否需要收窄到「代码为主」。"""

from __future__ import annotations

import re

from rag.vectorstore import get_vector_store_manager

PRE = re.compile(r"^(?:\[[^\]]*\]\s*(?:>\s*)*)+\n")
FENCE = "`" * 3
TILDE = "~" * 3
CATS = (
    "data_structure",
    "computer_organization",
    "operating_system",
    "computer_network",
    "questions",
    "learning_paths",
)


def code_chars(text: str) -> int:
    """代码围栏内的字符数（粗略）。"""
    total = 0
    for m in re.finditer(r"```[^\n]*\n(.*?)```", text, re.S):
        total += len(m.group(1))
    for m in re.finditer(r"~~~[^\n]*\n(.*?)~~~", text, re.S):
        total += len(m.group(1))
    return total


def main() -> None:
    mgr = get_vector_store_manager()
    buckets = {"<20%": 0, "20-50%": 0, "50-80%": 0, ">=80%": 0}
    n = 0
    samples: list[tuple[float, str, str]] = []
    for cat in CATS:
        col = mgr.client.get_collection(cat)
        res = col.get(include=["documents", "metadatas"])
        for txt, meta in zip(res["documents"], res["metadatas"]):
            txt = txt or ""
            if not PRE.match(txt):
                continue
            n += 1
            body = PRE.sub("", txt)
            ratio = code_chars(body) / max(len(body), 1)
            if ratio < 0.2:
                buckets["<20%"] += 1
            elif ratio < 0.5:
                buckets["20-50%"] += 1
            elif ratio < 0.8:
                buckets["50-80%"] += 1
            else:
                buckets[">=80%"] += 1
            m = meta or {}
            samples.append((ratio, cat, str(m.get("section.path"))[:52]))

    print(f"带锚点的 chunk 总数: {n}")
    for k, v in buckets.items():
        print(f"  代码占比 {k:<8}: {v:4d}  ({v / max(n, 1):.1%})")
    print()
    print("代码占比最低的 6 个（这些正是「正文夹代码片段」）：")
    for r, cat, sec in sorted(samples)[:6]:
        print(f"  {r:.1%}  {cat[:6]:<7} {sec}")
    print()
    print("代码占比最高的 6 个：")
    for r, cat, sec in sorted(samples, reverse=True)[:6]:
        print(f"  {r:.1%}  {cat[:6]:<7} {sec}")


if __name__ == "__main__":
    main()
