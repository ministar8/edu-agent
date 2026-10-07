"""Phase 1「Verify 修复 + Generate 回归」验收分析。

两条验收标准（**必须都过**）
--------------------------
1. **Verify 变好**：verify 探针里「列出真题」的比例显著高于 Phase 0B 的 1/10。
2. **Generate 未误伤**：generate 回归探针**全部仍出新题**，不得被吸到 knowledge_agent。

判定依据（纯文本特征，可复算）
------------------------------
- **列出真题**：出现 `YYYY-Qn` 或自然语言「YYYY 年第 N 题」；或明确的真题清单句式。
- **新出练习题**：出现「题目1 / 类型：选择 / 练习题 / 可直接作答」等出题模板句式。
- **诚实说明**：出现「未检索到 / 无法确认 / 知识库未覆盖」等。

生成任务里出现「真题」二字**不构成** Verify（可能是「真题风格」= 要新题），
故 generate 的判据只看**是否出新题**。

用法::

    PYTHONPATH=src uv run python scripts/analyze_phase1_probe.py \\
        evals/results/task_eval/phase1_verify_probe.jsonl
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

_QID_ID = re.compile(r"(?:19|20)\d{2}-Q\d+")
_QID_NATURAL = re.compile(r"(?:19|20)\d{2}\s*年?\s*第\s*\d+\s*题")
_PRACTICE = ("题目1", "题目2", "类型：选择", "类型：填空", "练习题", "可直接作答", "可提交批改")
_HONEST = ("未检索到", "无法确认", "知识库未覆盖", "没有检索到", "无法逐题定位", "无年份")


def _qids(text: str) -> list[str]:
    return _QID_ID.findall(text) + _QID_NATURAL.findall(text)


def classify_verify(reply: str) -> str:
    if _qids(reply):
        return "列出真题（✅ 正确）"
    if any(m in reply for m in _PRACTICE):
        return "新出练习题（❌ 走了出题）"
    if any(k in reply for k in _HONEST):
        return "诚实说明无法确认（△ 未编造）"
    return "其他"


def classify_generate(reply: str) -> str:
    """Generate 只看**是否出新题** —— 出了就是没被误伤。"""
    if any(m in reply for m in _PRACTICE) or "题干" in reply:
        return "出新题（✅ 未被误伤）"
    if _qids(reply):
        return "列真题（❌ 被误伤到 knowledge_agent）"
    return "其他（⚠️ 需人工看）"


def main(argv: list[str] | None = None) -> int:
    path = Path(
        argv[1] if argv and len(argv) > 1 else "evals/results/task_eval/phase1_verify_probe.jsonl"
    )
    rows = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]
    if not rows:
        print(f"读不到数据：{path}")
        return 2

    for task, fn, header in (
        ("verify", classify_verify, "Verify 探针"),
        ("generate", classify_generate, "Generate 回归探针"),
    ):
        sub = [r for r in rows if r["task"] == task]
        if not sub:
            continue
        print(f"\n## {header}（n={len(sub)}）\n")
        print(f"{'case':12s} {'query':40s} {'分类'}")
        print("-" * 100)
        tally: Counter[str] = Counter()
        for r in sub:
            reply = str(r.get("reply") or "")
            cls = fn(reply)
            tally[cls] += 1
            print(f"{r['case_id']:12s} {(r['query'] or '')[:38]:40s} {cls}")
        print("\n汇总：")
        for k, v in tally.most_common():
            print(f"  {k}: {v}/{len(sub)}")

    # ── 验收结论 ──
    ver = [r for r in rows if r["task"] == "verify"]
    gen = [r for r in rows if r["task"] == "generate"]
    n_ver_ok = sum(
        1 for r in ver if classify_verify(str(r.get("reply") or "")) == "列出真题（✅ 正确）"
    )
    n_gen_ok = sum(
        1 for r in gen if classify_generate(str(r.get("reply") or "")) == "出新题（✅ 未被误伤）"
    )
    print("\n" + "=" * 60)
    print(f"验收 ①  Verify 列出真题：{n_ver_ok}/{len(ver)}（Phase 0B 基线为 1/10）")
    print(f"验收 ②  Generate 未误伤：{n_gen_ok}/{len(gen)}")
    ok = n_ver_ok > 1 and n_gen_ok == len(gen)
    print(
        f"\n⇒ {'✅ 两条都过 —— 可进全量/并入基线' if ok else '❌ 未全过 —— 需调整 prompt 后重验'}"
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
