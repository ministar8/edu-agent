"""评估样本加载（jsonl）。"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class EvalSample:
    query: str
    reference: str = ""
    metadata: dict[str, str] = field(default_factory=dict)
    contexts: list[str] = field(default_factory=list)
    answer: str = ""
    # 逐条评测明细：与 contexts 同序，保存来源/章节/分数等检索溯源字段。
    retrieval_details: list[dict[str, Any]] = field(default_factory=list)

    def to_ragas_dict(self) -> dict[str, Any]:
        if not self.reference:
            logger.warning("样本 reference 为空，context_recall 无法计算: %s", self.query[:50])
        return {
            "user_input": self.query,
            "response": self.answer,
            "retrieved_contexts": self.contexts,
            "reference": self.reference,
        }


def _stratified_sample(samples: list[EvalSample], per_type: int) -> list[EvalSample]:
    """按 ``metadata.query_type`` 分层**等距**抽样，每类 ``per_type`` 条。

    ★ 为什么不能简单取前 N，也不能取「每类前 N」—— 黄金集里存在**两层成块排列**：

    1. **类型成块**：concept 1~60、generate 61~92、grade 93~124、code 125~156。
       取前 40 条 = 40 条纯概念题，**正好退回 0.1 之前的盲区**。
    2. **类型块内部按学科成块**：ds → co → os → network。
       取「每类前 15 条」会得到 ds 8 + co 7，**os / network 为 0**。

    等距抽样同时跨过这两层块，故类型与学科都均衡（实测见 `--sample-per-type` 的输出）。

    ★ 缺 ``query_type`` 的样本按 ``concept`` 处理：2026-09-24 扩量前的 40 条全部是概念题，
    只是当时还没有这个字段。若按 ``unknown`` 单独成桶，抽样会把它们排除在 ``concept``
    之外 —— 实测会得到 5 个桶、总数超出预期（每类 15 条 → 75 条而非 60 条）。
    """
    buckets: dict[str, list[EvalSample]] = {}
    for s in samples:
        buckets.setdefault(s.metadata.get("query_type") or "concept", []).append(s)

    picked: list[EvalSample] = []
    for name in sorted(buckets):
        block = buckets[name]
        n = min(per_type, len(block))
        if n >= len(block):
            picked.extend(block)
        elif n == 1:
            picked.append(block[len(block) // 2])
        else:
            step = (len(block) - 1) / (n - 1)
            picked.extend(block[round(i * step)] for i in range(n))

    # 恢复文件顺序：让抽样结果与「按文件顺序跑」的报告可对照
    order = {id(s): i for i, s in enumerate(samples)}
    picked.sort(key=lambda s: order[id(s)])
    return picked


def load_dataset(
    path: str,
    limit: int | None = None,
    sample_per_type: int | None = None,
) -> list[EvalSample]:
    """从 .jsonl 加载样本；坏行跳过。

    ``limit``：取**前 N 条**（原语义，供快速抽查）。
    ``sample_per_type``：按 ``metadata.query_type`` 分层等距抽样，每类 N 条
    （见 `_stratified_sample` 为何不能替代）。两者**互斥**。
    """
    if limit and sample_per_type:
        raise ValueError("limit 与 sample_per_type 不能同时使用 —— 两种口径会互相覆盖")

    samples: list[EvalSample] = []
    filepath = Path(path)
    if not filepath.exists():
        logger.warning("数据集不存在: %s", filepath)
        return samples

    with open(filepath, encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                raw = json.loads(line)
            except json.JSONDecodeError as e:
                logger.warning("%s 第 %d 行 JSON 失败: %s", filepath.name, line_num, e)
                continue
            query = str(raw.get("query", "")).strip()
            if not query:
                continue
            raw_meta = raw.get("metadata") or {}
            meta: dict[str, str] = {}
            for k, v in raw_meta.items():
                meta[str(k)] = ",".join(str(x) for x in v) if isinstance(v, list) else str(v)
            samples.append(
                EvalSample(
                    query=query,
                    reference=str(raw.get("reference", "")).strip(),
                    metadata=meta,
                )
            )
            if limit and len(samples) >= limit:
                break

    if sample_per_type:
        samples = _stratified_sample(samples, sample_per_type)

    logger.info("加载 %s: %d 条", filepath.name, len(samples))
    return samples
