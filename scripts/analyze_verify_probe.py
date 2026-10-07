"""分析 Verify 问法探针：系统是「列出真题」还是「新出练习题」？

判定依据（纯文本特征，可复算）
------------------------------
- `题号`：回复中出现 `YYYY-Qn` 形式的真题号 —— 正确 Verify 的必要特征。
- `出题模板`：出现「题目N」「类型：选择」「以下是…练习题」「可直接作答」等
  出题 agent 的固定句式 —— 说明**路由到了 question_agent**。

两种特征同时出现时以「是否给出题号」为准：Verify 的本质是**报出真题**。

用法::

    PYTHONPATH=src uv run python scripts/analyze_verify_probe.py \\
        evals/results/task_eval/probe_verify_phrasing.jsonl
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

_QID_RE = re.compile(r"(?:19|20)\d{2}-Q\d+")
# ★ 2026-10-06 补：系统常用**自然语言**报真题，而非 ID 格式 —— 实测出现过
#   「2010 年第 1 题」「2021 年第 33 题」这类写法。只认 `YYYY-Qn` 会**漏判成失败**。
_QID_NATURAL_RE = re.compile(r"(?:19|20)\d{2}\s*年?\s*第\s*\d+\s*题")
_YEAR_RE = re.compile(r"(?:19|20)\d{2}\s*年")
_PRACTICE_MARKERS = (
    "题目1",
    "题目2",
    "类型：选择",
    "类型：填空",
    "练习题",
    "可直接作答",
    "可提交批改",
)
_VERIFY_MARKERS = ("真题", "考过", "历年")


def _find_qids(reply: str) -> list[str]:
    """同时抓 ID 形式与自然语言形式的真题引用。"""
    return _QID_RE.findall(reply) + _QID_NATURAL_RE.findall(reply)


def classify(reply: str) -> str:
    qids = _find_qids(reply)
    if qids:
        return "列出真题（正确）"
    if any(m in reply for m in _PRACTICE_MARKERS):
        return "新出练习题（路由到 question_agent）"
    # 明确声明「检索不到」也算诚实作答，但与「正确列出」区分开
    if any(k in reply for k in ("未检索到", "无法逐题定位", "无年份", "没有检索到")):
        return "诚实说明无法定位（未编造）"
    return "其他"


def main(argv: list[str] | None = None) -> int:
    path = Path(
        argv[1] if argv and len(argv) > 1 else "evals/results/task_eval/probe_verify_phrasing.jsonl"
    )
    rows = [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]
    if not rows:
        print(f"读不到数据：{path}")
        return 2

    print(f"# Verify 问法探针分析（n={len(rows)}）\n")
    print(f"{'case':12s} {'问法':46s} {'题号数':>6s} {'gold':>5s} {'分类'}")
    print("-" * 110)
    tally: Counter[str] = Counter()
    for r in rows:
        reply = r.get("reply") or ""
        gold_ids = (r.get("gold") or {}).get("expected_question_ids") or []
        qids = _find_qids(reply)
        cls = classify(reply)
        tally[cls] += 1
        query = (r.get("query") or "").replace("\n", " ")
        print(f"{r['case_id']:12s} {query[:44]:46s} {len(qids):>6d} {len(gold_ids):>5d} {cls}")

    print("\n## 分类汇总")
    for k, v in tally.most_common():
        print(f"  {k}: {v}/{len(rows)}")

    n_real = tally.get("列出真题（正确）", 0)
    print(f"\n**结论**：{n_real}/{len(rows)} 条正确列出真题。")
    if n_real == 0:
        print(
            "⇒ **换任何自然问法都不行** ⇒ 「Verify 能力不存在」的结论**成立**（非模板问法所致）。"
        )
    else:
        print(
            "⇒ 存在能正确回答的问法 ⇒ 原结论**需修正**：不是「能力不存在」，而是「部分问法不被识别」。"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
