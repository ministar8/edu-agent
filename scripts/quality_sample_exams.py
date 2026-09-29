"""2009–2017 质量抽检：正常题 + gap 清单双抽样。"""

from __future__ import annotations

import json
import random
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))


YEARS = list(range(2009, 2018))
random.seed(2020)


def main() -> int:
    fails: list[str] = []
    # 1) 正常题抽检：每年抽 2 题看结构
    print("==== 正常题抽检 ====")
    for y in YEARS:
        items = ROOT / "knowledge" / "exams" / str(y) / "items.md"
        text = items.read_text(encoding="utf-8")
        blocks = re.split(r"(?m)^## (\d{4}-Q\d+)\s*$", text)
        qids = [blocks[i] for i in range(1, len(blocks) - 1, 2)]
        sample = random.sample(qids, min(2, len(qids)))
        for qid in sample:
            m = re.search(rf"(?m)^## {re.escape(qid)}\s*$\n\n(.*?)(?=\n---|\n## |\Z)", text, re.S)
            body = m.group(1) if m else ""
            checks = {
                "question_id": f"> question_id: {qid}" in body,
                "no_answer_in_body": not re.search(r"(^|\n)\s*(答案[:：]|【答案】)", body),
                "has_completeness": "> completeness:" in body,
                "has_gap_status": "> gap_status:" in body,
                "has_subject": "> subject:" in body,
                "options": bool(re.search(r"^- [A-D][.、．]", body, re.M)),
            }
            bad = [k for k, v in checks.items() if not v]
            status = "OK" if not bad else "FAIL " + ",".join(bad)
            print(f"  {y} {qid} {status}")
            if bad:
                fails.append(f"{qid} {bad}")

    # 2) gap 清单抽样
    print("==== gap 清单抽样 ====")
    inv = ROOT / "knowledge" / "exams" / "gap_inventory.jsonl"
    rows = [json.loads(x) for x in inv.read_text(encoding="utf-8").splitlines() if x.strip()]
    from collections import Counter

    print("  total", len(rows), "by_year", dict(Counter(r["year"] for r in rows)))
    print("  by_type", dict(Counter(r["gap_type"] for r in rows)))
    sample = random.sample(rows, min(8, len(rows)))
    for r in sample:
        ok = r.get("status") == "open" and r.get("gap_type") and r.get("asset")
        print(f"  {r['asset']} {r['gap_type']} {'OK' if ok else 'FAIL'}")
        if not ok:
            fails.append(f"gap record {r}")

    # 3) 缺答案是否都进了 gap（抽 3 条 answer gap 反查 items）
    print("==== answer gap 反查 ====")
    ans_gaps = [r for r in rows if r["gap_type"] == "answer" and r["year"] in YEARS]
    print(f"  answer_gaps={len(ans_gaps)}")
    for r in ans_gaps[:3]:
        y = r["year"]
        qid = r["asset"].split(":", 1)[1]
        text = (ROOT / "knowledge" / "exams" / str(y) / "items.md").read_text(encoding="utf-8")
        m = re.search(rf"(?m)^## {re.escape(qid)}\s*$\n\n(.*?)(?=\n---|\n## |\Z)", text, re.S)
        body = m.group(1) if m else ""
        has_null = "> answer_key: null" in body
        print(f"  {qid} answer_key:null={has_null} gap={r['gap_type']}")
        if not has_null:
            fails.append(f"{qid} should be null answer_key")

    if fails:
        print("FAIL", len(fails))
        for x in fails[:20]:
            print(" -", x)
        return 1
    print("QUALITY SAMPLE PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
