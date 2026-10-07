"""canonical KP 词表的**唯一事实源**。

为什么必须单独成模块（2026-10-06 缺陷 E 的根治）
------------------------------------------------

`kp_index`（`knowledge/knowledge_points/{ds,co,os,cn}.jsonl`）的 `name` 字段
是「规范考点名」（canonical name）。它有两个消费方：

    ① `memory.topics.normalize_topic` —— 把自由文本**归一**到 canonical；
    ② `prompts.service.GRADE_PROMPT`   —— 约束**模型产出**必须是 canonical。

若两处**各读各的**，就会出现「模型被诱导产出的词表」与「归一化认的词表」
**不同源** —— 这正是缺陷 E 的成因：模型产出 `图的基本性质` / `堆的定义`，
而 canonical 里只有 `图` / `堆`，于是聚合桶互不相同、`MIN_HITS` 永不满足、
`weak_topics` 恒为空 ⇒ 跨会话召回被系统性抑制。

⇒ 把读取收敛到本模块，**任何一方都不得再自行解析 jsonl**。

★ 为什么放在 `core` 而非 `memory`
---------------------------------
`prompts` 层需要一个词表，但**不能**因此 `import memory.topics` ——
`memory/__init__.py` 会拉起 `langgraph` checkpointer / sqlite saver / vector search
等重依赖，让一个纯 prompt 模块背上整个记忆层的启动成本。
本模块**只依赖 `json` / `pathlib`**，两层都可安全复用。

★ 惰性 + 静默降级
-----------------
`memory` 会被 API 进程 import，而 kp_index 只在仓库里。故**惰性加载 + 缓存**，
读不到文件时返回**空集合/空字典**而非抛错 —— 服务与评测**不得**因缺文件而起不来。
消费方（`normalize_topic` / `GRADE_PROMPT`）各自按「词表为空」退化为旧行为。
"""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger(__name__)

# 仓库根 → knowledge/knowledge_points
#   src/core/kp_vocab.py → parents[0]=core, parents[1]=src, parents[2]=仓库根
_KP_DIR = Path(__file__).resolve().parents[2] / "knowledge" / "knowledge_points"

# 学科展示名。**顺序即 prompt 中的分组顺序**（先学科主干，后交叉）。
SUBJECT_LABELS: dict[str, str] = {
    "ds": "数据结构",
    "co": "计算机组成原理",
    "os": "操作系统",
    "cn": "计算机网络",
}


def _load() -> tuple[frozenset[str], dict[str, list[str]], dict[str, str]]:
    """解析 kp_index，返回 `(全部 canonical names, 按学科分组的有序名字, name→node_kind)`。

    只认有非空 `name` 的记录 ⇒ `links.jsonl`（只有 `from`/`to`/`type`）自然被跳过，
    不会污染词表。

    `node_kind` 只给 **prompt 侧**过滤用（见 `prompt_names_by_subject`）；归一化侧不受影响。

    任何 `OSError`（目录不存在 / 权限）⇒ 记 warning 并返回空值，**不抛错**。
    """
    names: set[str] = set()
    kinds: dict[str, str] = {}
    by_subject: dict[str, list[str]] = {k: [] for k in SUBJECT_LABELS}
    try:
        for path in sorted(_KP_DIR.glob("*.jsonl")):
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                name = str(obj.get("name") or "").strip()
                if not name:
                    continue
                names.add(name)
                kinds.setdefault(name, str(obj.get("node_kind") or ""))
                subject = str(obj.get("subject") or "")
                if subject in by_subject:
                    by_subject[subject].append(name)
    except OSError:
        logger.warning("读取 kp_index 失败，canonical 词表退化为空", exc_info=True)
        return frozenset(), {k: [] for k in SUBJECT_LABELS}, {}

    # 去重保序（同一学科内可能出现同名不同 id 的节点，或文件被追加过）
    for subject, items in by_subject.items():
        seen: set[str] = set()
        deduped: list[str] = []
        for name in items:
            if name not in seen:
                seen.add(name)
                deduped.append(name)
        by_subject[subject] = deduped
    return frozenset(names), by_subject, kinds


@lru_cache(maxsize=1)
def _cached() -> tuple[frozenset[str], dict[str, list[str]], dict[str, str]]:
    return _load()


def canonical_names() -> frozenset[str]:
    """全部 canonical name（只读，**含 4 个课程根节点**）。读不到 kp_index ⇒ 空集合。

    ★ 归一化侧必须用**全量**：把 `数据结构` 等从本集合里摘掉，会让
    `normalize_topic('数据结构')` 反过来变成「非 canonical」——那是另一种错。
    课程根节点该被禁止的是「**被 prompt 主动提供给模型选**」，不是「被认出来」。
    """
    return _cached()[0]


def names_by_subject() -> dict[str, list[str]]:
    """按学科分组的全部 canonical name（有序，**含 subject 根节点**）。"""
    return _cached()[1]


def node_kinds() -> dict[str, str]:
    """`name → node_kind`（`subject` / `domain` / `topic` / `point`；无该字段为 `""`）。"""
    return _cached()[2]


def prompt_names_by_subject() -> dict[str, list[str]]:
    """提供给批改 prompt 的词表：按数据字段剔掉 `node_kind == "subject"` 的 4 个课程根节点。

    ★ 2026-10-07 缺陷 #8：`GRADE_PROMPT` 的规则尾写着「**不是**学科名（如「数据结构」太粗）」，
    而全量词表又把 `数据结构 / 计算机组成原理 / 操作系统 / 计算机网络` 列进**可选取值**
    ⇒ prompt 自相矛盾。更实际的危害是：模型若选它，会聚成「整门课 = 一个薄弱点」的桶，
    并且**轻易满足 `MIN_HITS=2`** —— 比自造词更难发现，因为它确实是 canonical。

    ★ 判据取自数据字段 `node_kind`，**不是硬编码名单** —— 硬编码第二份口径正是缺陷 E 的成因。
    ★ `domain`（26 个，即 408 大纲章名：`图` / `排序` / `内存管理` …）**保留** ——
      它们是合法的薄弱点标签，E-5 的可接受集里就用到了 `图` 与 `堆排序`。
    """
    kinds = node_kinds()
    return {
        subject: [n for n in names if kinds.get(n) != "subject"]
        for subject, names in names_by_subject().items()
    }
