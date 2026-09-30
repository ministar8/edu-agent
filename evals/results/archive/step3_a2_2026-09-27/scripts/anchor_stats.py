"""统计：带 [..] 锚点前缀的 chunk 有多少是代码块（避免 shell 转义问题）。"""

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


def main() -> None:
    mgr = get_vector_store_manager()
    tot = prefixed = pref_code = pref_nocode = 0
    samples: list[tuple[str, str, str]] = []
    for cat in CATS:
        col = mgr.client.get_collection(cat)
        res = col.get(include=["documents", "metadatas"])
        for _cid, txt, meta in zip(res["ids"], res["documents"], res["metadatas"]):
            txt = txt or ""
            tot += 1
            if not PRE.match(txt):
                continue
            prefixed += 1
            if FENCE in txt or TILDE in txt:
                pref_code += 1
            else:
                pref_nocode += 1
                if len(samples) < 6:
                    m = meta or {}
                    samples.append((cat, str(m.get("section.path")), str(m.get("content_type"))))

    print("总 chunk              :", tot)
    print("带 [..] 锚点前缀的 chunk:", prefixed)
    print("  其中含代码围栏       :", pref_code)
    print("  其中不含代码围栏     :", pref_nocode)
    print()
    print("无代码围栏的样例（category / section.path / content_type）：")
    for s in samples:
        print("   ", s)
    print()
    # 反向：含代码围栏但**没有**锚点前缀的 chunk（锚点机制漏掉的）
    miss = 0
    for cat in CATS:
        col = mgr.client.get_collection(cat)
        res = col.get(include=["documents"])
        for txt in res["documents"]:
            txt = txt or ""
            if (FENCE in txt or TILDE in txt) and not PRE.match(txt):
                miss += 1
    print("含代码围栏但无锚点前缀 :", miss)


if __name__ == "__main__":
    main()
