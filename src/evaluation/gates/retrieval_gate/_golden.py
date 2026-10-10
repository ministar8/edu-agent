"""黄金集加载与章节 / 学科映射。"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from ._constants import QUESTIONS_CATEGORY, SUBJECT_TO_CATEGORY

logger = logging.getLogger(__name__)

_CHAPTER_ALIASES: dict[str, str] = {
    # ── 数据结构 ──
    "linear_list": "线性表",
    "stack_queue": "栈和队列",
    "array_matrix": "特殊矩阵压缩存储",
    "string": "串",
    "tree": "树与二叉树",
    "graph": "图",
    "search": "查找",
    "sort": "排序",
    "code": "代码实现",
    "code_impl": "代码实现",
    "comprehensive": "代码实现",
    # ── 计算机组成原理 ──
    "intro": "计算机系统概述",
    "overview": "计算机系统概述",
    "arch": "体系结构",
    "cpu": "中央处理器",
    "instruction": "指令系统",
    "pipeline": "体系结构",
    "representation": "数据表示与运算",
    "storage": "存储系统",
    "storage_cache": "存储系统",
    "bus": "总线",
    "bus_io": "输入输出系统",
    "io": "输入输出系统",
    # ── 操作系统 ──
    "process": "进程管理",
    "process_sync": "进程管理",
    "memory": "内存管理",
    "file": "文件管理",
    "file_disk": "文件管理",
    # ── 计算机网络 ──
    "physical": "物理层",
    "datalink": "数据链路层",
    "link": "数据链路层",
    "network": "网络层",
    "network_ip": "网络层",
    "transport": "传输层",
    "application": "应用层",
}


def chapter_of_source(source: str) -> str:
    """从证据的 ``source``（知识库文件名）取**章级知识点标签**。

    ``"05_树与二叉树.md"`` → ``"树与二叉树"``
    ``"knowledge/basic/data_structure/06_tree.md"`` → ``"树与二叉树"``（经别名映射）

    ★ 为什么「章」的载体取**文件**而不是 H1 标题：实测 H1 不均匀 ——
    大文件里 H1 = 章（`二、二叉树Binary tree`），小文件里 H1 = 具体主题
    （`3.链栈` / `8.虚拟机`），还有 `1定义` / `3性质` 这类碎片；
    而文件恰好是标准章单元（`05_树与二叉树` / `03_存储系统` / `05_传输层` …）。

    ★ 别名映射：L1/L2 新层用英文 stem（`file_disk`），黄金集标注是中文（`文件管理`）。
    不映射时分层消融的 kp_* 会把「命名差异」误判成「检索失败」。
    """
    name = Path(str(source)).stem if source else ""
    # 去掉两位编号前缀（`05_树与二叉树` → `树与二叉树`）。
    # 用长度+字符判断而非正则：4 位年份前缀（`2019_408_exam`）不会被误剥。
    if len(name) > 2 and name[:2].isdigit() and name[2] in "_-":
        name = name[3:]
    name = name.strip()
    # 新层英文 stem → 黄金集中文标签
    return _CHAPTER_ALIASES.get(name, name)


def _parse_expected_kps(value: Any) -> tuple[str, ...]:
    """解析黄金集里的 ``metadata.knowledge_points`` 标注。

    容忍两种形态：
    - ``list``（门禁直读 JSONL 时的原形）；
    - 逗号串（``evaluation.ragas.dataset`` 会把 list **join 成逗号串**，见其 `:57`）。

    两种都收，是为了让同一份黄金集既能被门禁读、也能被 RAGAS 链路读而不失真。
    """
    if value is None:
        return ()
    items = [str(v) for v in value] if isinstance(value, list) else str(value).split(",")
    return tuple(s.strip() for s in items if s.strip())


def load_golden_queries(
    path: str | Path, limit: int | None = None
) -> list[tuple[str, tuple[str, ...], tuple[str, ...]]]:
    """加载 ``(query, expected_categories, expected_knowledge_points)`` 列表。

    跳过无法映射 subject 的行。``knowledge_points`` 缺失时返回空 tuple ——
    该条不参与 ``kp_hit@k``（未标注 ≠ 未命中，见 ``QueryOutcome.first_correct_kp_rank``）。

    ★ ``expected_categories`` 是**多值**（2026-09-24 起）。原因：对**出题类**查询，
    返回历年真题（`questions` 集合）**恰恰是正确行为** —— 但 `questions` 不是学科，
    原先只认 `SUBJECT_TO_CATEGORY` 映射出的那一个类目，于是「返回真题」被判成
    「学科未命中」（实测 generate 类 `cat@1` 一度只有 0.0312，几乎全判错）。
    现在出题类的合法来源是**「对应学科的讲义」或「历年真题」二者之一**。
    """
    filepath = Path(path)
    if not filepath.exists():
        raise FileNotFoundError(f"黄金集不存在: {filepath}")

    items: list[tuple[str, tuple[str, ...], tuple[str, ...]]] = []
    with open(filepath, encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                raw = json.loads(line)
            except json.JSONDecodeError:
                logger.warning("黄金集第 %d 行解析失败，跳过", line_num)
                continue
            query = str(raw.get("query", "")).strip()
            meta = raw.get("metadata") or {}
            subject = str(meta.get("subject", "")).strip()
            category = SUBJECT_TO_CATEGORY.get(subject)
            if not query or not category:
                logger.warning("黄金集第 %d 行缺 query 或 subject 无法映射，跳过", line_num)
                continue
            categories: tuple[str, ...] = (category,)
            if str(meta.get("query_type") or "") == "generate":
                categories = (category, QUESTIONS_CATEGORY)
            items.append((query, categories, _parse_expected_kps(meta.get("knowledge_points"))))
            if limit and len(items) >= limit:
                break
    return items
