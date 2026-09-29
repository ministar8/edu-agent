"""链路打通 E2E：真实 @tool 入口 → policy → 检索 → Evidence Policy → 载荷。

断言：
- knowledge_search 走 learn（或 query 覆盖）
- search_question_templates 走 practice，载荷无答案/题号
- search_standard_answer 走 grade，可含答案
- payload 结构完整（context/docs/status）

用法：
    uv run python scripts/e2e_agent_chain.py
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agents.tools import (  # noqa: E402
    aknowledge_search,
    asearch_question_templates,
    asearch_standard_answer,
)

_QID = __import__("re").compile(r"(?:19|20)\d{2}-Q\d+")
_ANS = __import__("re").compile(r"answer_key|reference_answer|答案[:：]", __import__("re").I)


async def call_tool(t, query: str) -> dict:
    # langchain tool: await t.ainvoke({"query": ...})
    raw = await t.ainvoke({"query": query})
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except Exception:
            return {"status": "raw", "context": raw}
    return {"status": "unknown", "raw": str(raw)}


async def main() -> int:
    fails: list[str] = []
    print("==== E2E agent chain (real tools) ====")

    # 1) knowledge_search / learn
    p = await call_tool(aknowledge_search, "什么是二叉树的中序遍历？")
    print(f"[knowledge_search] status={p.get('status')} docs={len(p.get('docs') or [])}")
    print(f"  context[:80]={str(p.get('context') or '')[:80]!r}")
    if p.get("status") == "error":
        fails.append("knowledge_search error")
    blob = json.dumps(p, ensure_ascii=False)
    # learn 不应出现答案键字段
    if "answer_key" in blob or "reference_answer" in blob:
        # docs 可能只含 excerpt；严格检查
        fails.append("knowledge_search leaked answer fields")

    # 2) practice：出题模板
    p2 = await call_tool(asearch_question_templates, "给我一道 BST 删除的练习题")
    print(f"[practice] status={p2.get('status')} docs={len(p2.get('docs') or [])}")
    blob2 = json.dumps(p2, ensure_ascii=False)
    ctx2 = str(p2.get("context") or "")
    if _ANS.search(blob2) or _ANS.search(ctx2):
        fails.append("practice leaked answer")
    if _QID.search(blob2) or _QID.search(ctx2):
        fails.append("practice leaked question_id")

    # 3) grade：标准答案
    p3 = await call_tool(
        asearch_standard_answer,
        "2019-Q2 我选 B，树转二叉树后根遍历等于中序，对吗？请批改",
    )
    print(f"[grade] status={p3.get('status')} docs={len(p3.get('docs') or [])}")
    if p3.get("status") == "error":
        fails.append("grade tool error")

    # 4) 每个 payload 结构
    for name, payload in [
        ("knowledge", p),
        ("practice", p2),
        ("grade", p3),
    ]:
        for field in ("status", "query", "context"):
            if field not in payload:
                fails.append(f"{name} missing {field}")

    if fails:
        print("E2E CHAIN FAIL", len(fails))
        for x in fails:
            print(" -", x)
        return 1
    print("E2E CHAIN PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
