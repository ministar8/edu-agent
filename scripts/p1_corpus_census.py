"""P−1 语料普查（只读，零 LLM）：题本体形态 + generate case 的事前可标性。

★ 只读 `knowledge/exams/**/items.md` 的 metadata 与 `evals/datasets/demo/generate_cases.jsonl` 的
  **输入侧**（query / 已填 gold 字段）。**不读任何模型输出**（归档 reply）—— 盲标防自证规程要求
  gold 不得从 system_output 反推，普查阶段同样不许看它。

"""

from __future__ import annotations

import argparse
import collections
import json
import re
import sys
from pathlib import Path

Q_RE = re.compile(r"^## (\d{4}-Q\d+)\s*$", re.M)
META_RE = re.compile(r"^>\s*([a-z_]+):\s*(.*)$", re.M)
SUBQ_RE = re.compile(r"[（(]\s*(\d{1,2})\s*[)）]")

ITEMS_DIR = Path("knowledge/exams")
CASES = Path("evals/datasets/demo/generate_cases.jsonl")


def _meta_of(block: str) -> dict[str, str]:
    head = re.split(r"\*\*题干\*\*|\*\*\w+\*\*\s*[：:]", block)[0]
    return dict(META_RE.findall(head))


def census_items() -> dict[str, object]:
    files = sorted(ITEMS_DIR.rglob("items.md"))
    n = 0
    qtype: collections.Counter[str] = collections.Counter()
    keyshape: collections.Counter[str] = collections.Counter()
    comp: collections.Counter[str] = collections.Counter()
    gap: collections.Counter[str] = collections.Counter()
    expl: collections.Counter[str] = collections.Counter()
    subq = 0
    kp_nodes: set[str] = set()
    for f in files:
        txt = f.read_text(encoding="utf-8", errors="replace")
        spans = [(m.group(1), m.start(), m.end()) for m in Q_RE.finditer(txt)]
        for i, (qid, st, en) in enumerate(spans):
            nxt = spans[i + 1][1] if i + 1 < len(spans) else len(txt)
            body = txt[en:nxt]
            meta = _meta_of(body)
            n += 1
            qtype[meta.get("question_type") or "(缺)"] += 1
            comp[meta.get("completeness") or "(缺)"] += 1
            gap[(meta.get("gap_fields") or "[]").strip() or "[]"] += 1
            expl[meta.get("explanation_status") or "(缺)"] += 1
            ak = (meta.get("answer_key") or "null").strip()
            if ak in ("null", ""):
                keyshape["缺键(null)"] += 1
            elif re.fullmatch(r"[A-H]", ak):
                keyshape["单字母"] += 1
            elif re.fullmatch(r"[A-H,，\s]+", ak):
                keyshape["多字母（多选）"] += 1
            else:
                keyshape["文本/数值/其他"] += 1
            if len(set(SUBQ_RE.findall(body[:900]))) >= 2:
                subq += 1
            kp_nodes.update(
                re.findall(r"[a-z][a-z0-9_]*(?:\.[a-z0-9_]+)+", meta.get("kp_ids") or "")
            )
    return {
        "files": len(files),
        "items": n,
        "question_type": dict(qtype),
        "answer_key_shape": dict(keyshape),
        "completeness": dict(comp),
        "gap_fields": dict(gap),
        "explanation_status": dict(expl),
        "items_with_subquestions": subq,
        "distinct_kp_nodes": len(kp_nodes),
    }


def census_cases() -> dict[str, object]:
    rows = [
        json.loads(line)
        for line in CASES.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]
    feat: collections.Counter[str] = collections.Counter()
    gold_filled: collections.Counter[str] = collections.Counter()
    for r in rows:
        q = r.get("query") or ""
        specified = False
        for pat, name in (
            (r"单选|多项选择|选择题", "指定选择题"),
            (r"判断(题|对错)", "指定判断题"),
            (r"填空", "指定填空"),
            (r"解答|简答|计算题|证明", "指定解答题"),
        ):
            if re.search(pat, q):
                feat[name] += 1
                specified = True
        if not specified:
            feat["未指定题型"] += 1
        feat["指定难度" if re.search(r"难度|难易", q) else "未指定难度"] += 1
        g = r.get("gold") or {}
        for k in ("expected_kp", "gold_answer", "expected_difficulty"):
            if g.get(k) not in (None, "", [], {}):
                gold_filled[k] += 1
    return {"cases": len(rows), "query_constraints": dict(feat), "gold_filled": dict(gold_filled)}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="evals/claims/p1_corpus_census.json")
    args = ap.parse_args(argv)
    data = {"corpus": census_items(), "generate_cases": census_cases()}
    Path(args.out).write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(data, ensure_ascii=False, indent=2), file=sys.stdout)
    print(f"\n已写入 {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
