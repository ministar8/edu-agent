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

    def to_ragas_dict(self) -> dict[str, Any]:
        if not self.reference:
            logger.warning("样本 reference 为空，context_recall 无法计算: %s", self.query[:50])
        return {
            "user_input": self.query,
            "response": self.answer,
            "retrieved_contexts": self.contexts,
            "reference": self.reference,
        }


def load_dataset(path: str, limit: int | None = None) -> list[EvalSample]:
    """从 .jsonl 加载样本；坏行跳过。"""
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
    logger.info("加载 %s: %d 条", filepath.name, len(samples))
    return samples
