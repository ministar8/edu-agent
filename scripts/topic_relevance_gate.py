"""topic_relevance_gate：错域 top-up 拦截门禁。

固定用例：哈夫曼 query 不得引入 CSMA/以太网等错域 top-up。

用法：
    uv run python scripts/topic_relevance_gate.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rag.topic_relevance import is_topic_relevant, topic_relevance_score  # noqa: E402

# (query, doc_snippet, meta_section, want_relevant)
CASES = [
    (
        "出一道哈夫曼编码的计算题",
        "哈夫曼编码与 WPL **计算流程**：每次取最小两个权合并，WPL = Σ wᵢ × lᵢ",
        "advanced-ds-tree-huffman_calc",
        True,
    ),
    (
        "出一道哈夫曼编码的计算题",
        "CSMA/CD 与以太网 最小帧长、争用期、冲突域",
        "advanced-cn-link-mac",
        False,
    ),
    (
        "BST 删除怎么做？双支结点如何处理？",
        "BST 判定与操作 删除双支结点中序前驱",
        "advanced-ds-tree-bst_ops",
        True,
    ),
    (
        "BST 删除怎么做？",
        "TCP 拥塞窗口慢启动",
        "advanced-cn-transport-congestion",
        False,
    ),
    (
        "2019-Q2 为什么树的后根遍历对应二叉树中序？",
        "树与森林转换 后根遍历 对应二叉树中序",
        "advanced-ds-tree-forest_convert",
        True,
    ),
    (
        "2019-Q2 为什么树的后根遍历对应二叉树中序？",
        "IEEE754 浮点阶码尾数",
        "advanced-co-representation-ieee754",
        False,
    ),
]


def main() -> int:
    fails = []
    print("==== topic_relevance_gate ====")
    for q, doc, sec, want in CASES:
        meta = {"section_id": sec}
        rel = topic_relevance_score(q, doc, meta)
        got = is_topic_relevant(q, doc, meta, min_score=0.25)
        ok = got == want
        print(f"  [{rel:.2f}] relevant={got} want={want} {sec} {'OK' if ok else 'FAIL'}")
        print(f"       q={q[:40]}")
        if not ok:
            fails.append(f"{sec} for {q[:30]!r}")
    if fails:
        print("TOPIC GATE FAIL", len(fails))
        for x in fails:
            print(" -", x)
        return 1
    print("TOPIC GATE PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
