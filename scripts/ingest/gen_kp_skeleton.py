"""生成四科 Knowledge Point 骨架（level 1–3）。

粒度原则：一个 KP = 一道真题可**单独考查**的语义单元。
- pipeline 与 pipeline_hazard 分开
- ARP 与 ICMP 分开
- importance = 知识体系中的地位，不是真题频次
- question_types = typical_question_types（典型考法，非历史统计）

★ 四科骨架数据已按科拆出（`_kp_ds/_kp_co/_kp_os/_kp_cn.py`），构造原语在 `_kp_node.py`；
  本文件只留编排：写盘 + 入口。
"""

from __future__ import annotations

import json
from pathlib import Path

from _kp_cn import cn
from _kp_co import co
from _kp_ds import ds
from _kp_os import os

OUT = Path(r"C:\Users\26452\Desktop\edu-agent\knowledge\knowledge_points")
OUT.mkdir(parents=True, exist_ok=True)


def write_subject(code: str, nodes: list[dict]) -> None:
    path = OUT / f"{code}.jsonl"
    with path.open("w", encoding="utf-8") as f:
        for node in nodes:
            f.write(json.dumps(node, ensure_ascii=False) + "\n")
    print(f"{path.name}: {len(nodes)} nodes")


def main() -> int:
    write_subject("ds", ds)
    write_subject("co", co)
    write_subject("os", os)
    write_subject("cn", cn)
    links = OUT / "links.jsonl"
    if not links.exists():
        links.write_text("", encoding="utf-8")
    print("TOTAL", sum(map(len, [ds, co, os, cn])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
