"""入库侧聚合（从 `telemetry_report` 拆出，2026-10-14）。

拆出原因：`telemetry_report.py` 本周因采样同步从 556 行涨到 602 行，越过「单文件 ≤600 行」
红线。`build_ingest_summary` 是自成一块的入库口径（与检索侧的 scan / funnel 无共享状态），
按仓内既有的 `_telemetry_*` 兄弟模块模式拆出。**行为零变化**：函数体逐字搬移，
`telemetry_report` 经 import 继续沿用同一个名字。
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any


def build_ingest_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """入库侧聚合：**每个文件取最后一次**（同一文件被重入库多次）。

    ★ 为什么要同时统计 `chunks` 与 `indexed_chunks`：
    `chunks` 是切分产出，`indexed_chunks` 是**真正入库**的数量，两者之差是
    `vectorstore` 按**内容哈希**判重丢掉的量（`index_documents.dedup_skipped`）。
    实测（2026-09-27）合计 `indexed_chunks` = 2092，与生产索引规模**逐位一致** ⇒
    这个字段可以作为「遥测 vs 实际索引」的交叉校验；差值则指向具体文件。
    把差值单列出来，是为了不让「切分产出 106、实际入库 82」这种落差藏在合计里。
    """
    last: dict[tuple[str, str], tuple[int, int]] = {}
    for row in rows:
        if not row["file"]:
            continue
        chunks = row["values"].get("chunks")
        indexed = row["values"].get("indexed_chunks")
        if isinstance(chunks, int) and isinstance(indexed, int):
            last[(row["category"], row["file"])] = (chunks, indexed)

    per_category: dict[str, int] = defaultdict(int)
    for (_category, _file), (_chunks, indexed) in last.items():
        per_category[_category] += indexed
    mismatched = [
        {
            "category": category,
            "file": file,
            "chunks": chunks,
            "indexed_chunks": indexed,
            "dropped": chunks - indexed,
        }
        for (category, file), (chunks, indexed) in sorted(last.items())
        if chunks != indexed
    ]
    return {
        "events": len(rows),
        "files": len(last),
        "per_category": dict(sorted(per_category.items())),
        "indexed_total": sum(indexed for _c, indexed in last.values()),
        "split_total": sum(chunks for chunks, _i in last.values()),
        "mismatched_files": mismatched,
    }
