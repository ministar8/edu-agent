"""评估数据集加载模块

数据集格式：每行一个 JSON 对象，包含 query / reference / metadata。
保存在 data/evaluation/datasets/ 下，按学科分文件。
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# 默认数据集目录
_DEFAULT_DATASET_DIR = Path(__file__).resolve().parents[2] / "data" / "evaluation" / "datasets"


@dataclass
class EvalSample:
    """单条评估样本"""
    query: str
    reference: str = ""                # 参考答案（ground truth）
    metadata: dict[str, str] = field(default_factory=dict)
    contexts: list[str] = field(default_factory=list)   # 检索到的上下文（评估时填充）
    answer: str = ""                                      # 生成的答案（评估时填充）

    def to_ragas_dict(self) -> dict[str, Any]:
        """转换为 RAGAS 0.4.x evaluate() 所需格式

        RAGAS 0.4.x 字段名（SingleTurnSample）：
        - user_input: 用户提问
        - reference: 标准答案（ground truth）
        - retrieved_contexts: 检索到的上下文列表
        - response: 系统生成的答案
        """
        if not self.reference:
            logger.warning("样本 reference 为空，context_recall 将无法计算: query=%s", self.query[:50])
        return {
            "user_input": self.query,
            "response": self.answer,
            "retrieved_contexts": self.contexts,
            "reference": self.reference,
        }


def load_dataset(path: str, limit: int | None = None) -> list[EvalSample]:
    """从 .jsonl 文件加载评估样本

    Args:
        path: .jsonl 文件路径
        limit: 限制加载条数（调试用）

    Returns:
        EvalSample 列表
    """
    samples: list[EvalSample] = []
    filepath = Path(path)

    if not filepath.exists():
        logger.warning("数据集文件不存在: %s", filepath)
        return samples

    with open(filepath, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                raw = json.loads(line)
            except json.JSONDecodeError as e:
                logger.warning("数据集 %s 第 %d 行 JSON 解析失败: %s", filepath.name, line_num, e)
                continue

            query = raw.get("query", "").strip()
            if not query:
                logger.warning("数据集 %s 第 %d 行缺少 query，跳过", filepath.name, line_num)
                continue

            # 处理 metadata：list 值（如 cross_subject）转为逗号分隔字符串
            raw_meta = raw.get("metadata", {})
            meta: dict[str, str] = {}
            for k, v in raw_meta.items():
                if isinstance(v, list):
                    meta[str(k)] = ",".join(str(item) for item in v)
                else:
                    meta[str(k)] = str(v)

            sample = EvalSample(
                query=query,
                reference=raw.get("reference", "").strip(),
                metadata=meta,
            )
            samples.append(sample)

            if limit and len(samples) >= limit:
                break

    logger.info("加载数据集 %s: %d 条样本", filepath.name, len(samples))
    return samples


def load_all_datasets(
    dataset_dir: str = "",
    limit: int | None = None,
) -> dict[str, list[EvalSample]]:
    """加载 data/evaluation/datasets/ 下所有 .jsonl 文件

    Args:
        dataset_dir: 数据集目录路径，默认自动定位
        limit: 每个文件最大加载条数

    Returns:
        {文件名(不含扩展名): 样本列表}
    """
    if dataset_dir:
        root = Path(dataset_dir)
    else:
        root = _DEFAULT_DATASET_DIR

    if not root.exists():
        logger.warning("数据集目录不存在: %s", root)
        return {}

    datasets: dict[str, list[EvalSample]] = {}
    for filepath in sorted(root.glob("*.jsonl")):
        name = filepath.stem  # 不含 .jsonl 的文件名
        samples = load_dataset(str(filepath), limit=limit)
        if samples:
            datasets[name] = samples

    total = sum(len(s) for s in datasets.values())
    logger.info("共加载 %d 个数据集, %d 条样本", len(datasets), total)
    return datasets
