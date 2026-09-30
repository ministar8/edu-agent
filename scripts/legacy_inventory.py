"""Legacy inventory：盘点无 kb_depth 旧资产（不改权重）。

产出：
  evals/datasets/analysis/legacy_inventory.json
  - 各集合 legacy / 有标签 chunk 计数
  - 来源文件 top
  - 与新 L1/L2/L3 的重叠主题（抽样）

用法：
    uv run python scripts/legacy_inventory.py
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

import chromadb

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "evals" / "legacy_inventory.json"
COLLECTIONS = [
    "data_structure",
    "computer_organization",
    "operating_system",
    "computer_network",
    "questions",
    "learning_paths",
]


def main() -> int:
    client = chromadb.PersistentClient(path=str(ROOT / "chroma_db"))
    report = {"total": {}, "by_collection": {}, "legacy_sources": {}, "legacy_ids_sample": {}}

    for coll in COLLECTIONS:
        try:
            col = client.get_collection(coll)
        except Exception:
            continue
        got = col.get(include=["metadatas"])
        metas = got.get("metadatas") or []
        n = len(metas)
        legacy = 0
        tagged = Counter()
        src = Counter()
        ids_legacy = []
        for i, m in enumerate(metas):
            m = m or {}
            kb = str(m.get("kb_depth") or "")
            if kb:
                tagged[kb] += 1
            else:
                legacy += 1
                sid = str(m.get("chunk_id") or (got.get("ids") or [""])[i])
                # chk::file:: 或旧路径
                mm = re.match(r"chk::([^:]+)", sid)
                key = (
                    mm.group(1) if mm else str(m.get("source") or m.get("source_file") or sid[:40])
                )
                src[key] += 1
                if len(ids_legacy) < 5:
                    ids_legacy.append(sid)
        report["by_collection"][coll] = {
            "total": n,
            "legacy": legacy,
            "legacy_ratio": round(legacy / n, 3) if n else 0,
            "tagged_kb_depth": dict(tagged),
            "doc_roles": dict(Counter(str((m or {}).get("doc_role") or "") for m in metas)),
        }
        report["legacy_sources"][coll] = src.most_common(15)
        report["legacy_ids_sample"][coll] = ids_legacy
        report["total"][coll] = n

    # 汇总
    sum_legacy = sum(v["legacy"] for v in report["by_collection"].values())
    sum_total = sum(v["total"] for v in report["by_collection"].values())
    report["_meta"] = {
        "note": "只盘点，不改权重；legacy = 无 kb_depth",
        "sum_total": sum_total,
        "sum_legacy": sum_legacy,
        "legacy_ratio": round(sum_legacy / sum_total, 3) if sum_total else 0,
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"legacy {sum_legacy}/{sum_total} ratio={report['_meta']['legacy_ratio']}")
    for coll, v in report["by_collection"].items():
        print(f"  {coll}: legacy {v['legacy']}/{v['total']} tagged={v['tagged_kb_depth']}")
        top = report["legacy_sources"][coll][:5]
        for name, c in top:
            print(f"     {c:4d}  {name}")
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
