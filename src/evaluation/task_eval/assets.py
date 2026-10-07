"""仓库资产解析的**单一真源**：考点表 / 真题 / 黄金集。

为什么单独一个模块
------------------
demo 集生成器（`scripts/build_demo_cases.py`）与 Gold Sanity Check
（`evaluation/task_eval/gold_sanity.py`）**必须看到同一份资产解析结果**。
各写一份解析器的后果是：sanity 说「gold 合法」，而生成器产出的 gold 却不合法 ——
评测工具自己先分裂，0B 的 fail 就无法归因到系统。

故解析逻辑只在这里一份；上游脚本一律 import 本模块。

本模块**只读文件、不 import rag / agents**，可离线运行。
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[3]
GOLDEN = ROOT / "evals" / "datasets" / "golden" / "sample_408.jsonl"
KP_DIR = ROOT / "knowledge" / "knowledge_points"
EXAMS_DIR = ROOT / "knowledge" / "exams"

_ITEM_SPLIT = re.compile(r"^##\s+(\d{4}-Q\d+)\s*$", re.M)
_META_RE = re.compile(r"^>\s*([a-z_]+):\s*(.*)$", re.M)
_STEM_RE = re.compile(r"\*\*题干\*\*[：:]\s*(.+?)(?=\n\s*-\s*[A-D]\.|\n---|\Z)", re.S)
_OPT_RE = re.compile(r"^\s*-\s*([A-D])\.\s*(.+)$", re.M)
_KP_LIST_RE = re.compile(r"\[(.*?)\]")


def load_kp_index() -> dict[str, dict[str, str]]:
    """考点 ID → {name, subject}（来自 `knowledge/knowledge_points/*.jsonl`）。"""
    out: dict[str, dict[str, str]] = {}
    for path in sorted(KP_DIR.glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            kp_id = str(obj.get("id") or "")
            if kp_id:
                out[kp_id] = {
                    "name": str(obj.get("name") or kp_id),
                    "subject": str(obj.get("subject") or ""),
                }
    return out


def build_name2id(kp_index: dict[str, dict[str, str]]) -> dict[str, str]:
    """考点中文名 → ID（把黄金集的**名字**统一到**ID 命名空间**）。"""
    out: dict[str, str] = {}
    for kp_id, info in kp_index.items():
        out.setdefault(info["name"], kp_id)
    return out


def is_valid_kp_id(kp_id: str, kp_index: dict[str, dict[str, str]]) -> bool:
    """ID 是否在考点表中（支持祖先校验：`co.storage.cache` 合法则 `co.storage` 亦合法）。"""
    if kp_id in kp_index:
        return True
    # 祖先：任一既有 ID 以 `kp_id.` 开头即认为该父节点合法
    return any(existing.startswith(kp_id + ".") for existing in kp_index)


def _norm_answer_key(raw: str) -> str | None:
    """把 ``answer_key`` 的**占位符**归一化为 ``None``。

    ★ 2026-10-06 实测教训：`items.md` 里有些题写的是 ``answer_key: null``（扫描缺失），
      原实现把它当**字符串** ``'null'`` 返回 —— 而 ``'null'`` 是 **truthy**，
      于是这些「无答案」的题**通过了筛选**混进 Grade 集；
      生成器又因 ``'null' not in A/B/C/D`` 回退到 ``opts[0]``（恒为 A），
      **凭空编造了一个「正确答案 A」** ⇒ 整批 Grade 的 gold 失真。
      ⇒ 必须在**解析层**就把占位符清掉，让下游能正确过滤。
    """
    text = str(raw or "").strip()
    if text.lower() in ("", "null", "none", "n/a", "na", "-"):
        return None
    return text


def load_answer_corrections() -> dict[str, str]:
    """读人工核验的 answer_key 修正表（**评测侧覆盖**，不改 KB 原文）。

    ★ 2026-10-06：`items.md` 的 `answer_key` 来自扫描，实测 24% 缺失 + 15 条抽样中 5 条错误。
      若不修正，Grade 的 `score_tolerance` 测的是「gold 质量」而非「系统能力」。
      修正表只被本模块（评测侧）读取 —— **不触碰 KB 与检索链**。
    """
    path = ROOT / "evals" / "datasets" / "exam_answer_corrections.json"
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        logger.warning("答案修正表解析失败：%s", path)
        return {}
    return {
        str(k): str(v.get("answer_key"))
        for k, v in (data.get("corrections") or {}).items()
        if isinstance(v, dict) and v.get("answer_key")
    }


def parse_exam_items() -> list[dict[str, Any]]:
    """解析 `knowledge/exams/*/items.md` → 结构化题目列表（并套用答案修正表）。"""
    corrections = load_answer_corrections()
    n_fixed = 0
    items: list[dict[str, Any]] = []
    for path in sorted(EXAMS_DIR.glob("*/items.md")):
        text = path.read_text(encoding="utf-8")
        marks = list(_ITEM_SPLIT.finditer(text))
        for i, m in enumerate(marks):
            end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
            block = text[m.end() : end]
            meta = {k: v.strip() for k, v in _META_RE.findall(block)}
            stem_m = _STEM_RE.search(block)
            kp_match = _KP_LIST_RE.search(meta.get("kp_ids", ""))
            qid = m.group(1)
            key = _norm_answer_key(meta.get("answer_key", ""))
            if qid in corrections and corrections[qid] != key:
                n_fixed += 1
                key = corrections[qid]
            items.append(
                {
                    "question_id": qid,
                    "year": meta.get("exam_year", ""),
                    "subject": meta.get("subject", ""),
                    "question_type": meta.get("question_type", ""),
                    "score": meta.get("score", ""),
                    "answer_key": key,
                    "kp_ids": [x.strip() for x in kp_match.group(1).split(",") if x.strip()]
                    if kp_match
                    else [],
                    "stem": " ".join(stem_m.group(1).split()) if stem_m else "",
                    "options": {o.group(1): o.group(2).strip() for o in _OPT_RE.finditer(block)},
                }
            )
    if n_fixed:
        logger.info("套用答案修正表：修正 %d 条 answer_key", n_fixed)
    return items


def load_golden() -> list[dict[str, Any]]:
    """读 `sample_408.jsonl`（`#` 注释行跳过）。"""
    out: list[dict[str, Any]] = []
    for line in GOLDEN.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        out.append(json.loads(line))
    return out
