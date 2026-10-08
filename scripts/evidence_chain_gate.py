"""Evidence Chain 护栏（零 LLM）。判据数量本身也是判据。"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

_EXPECTED_ITEMS = 5
_ITEMS: list[tuple[str, bool, str]] = []


def check(label: str, passed: bool, detail: str = "") -> None:
    _ITEMS.append((label, bool(passed), detail))


def check_1() -> None:
    """新字段必须存在，且老归档读取按「未知」处理而非猜测填充。"""
    from evaluation.task_eval.runner import CaseRecord

    rec = CaseRecord(case_id="x", task="generate", task_mode="practice", query="q")
    check("1a rerank_status 默认空串（未知）", rec.rerank_status == "")
    check("1b memory_read_status 默认空串（未知）", rec.memory_read_status == "")
    check("1c item_reasons 默认空 dict", rec.item_reasons == {})
    check("1d provenance 默认空 dict", rec.provenance == {})
    legacy = CaseRecord(case_id="y", task="qa", task_mode="learn", query="q")
    check(
        "1e 空 provenance 不等于「配置已核对」", "experiment_config_hash" not in legacy.provenance
    )


def main() -> int:
    check_1()
    total = len(_ITEMS)
    for label, passed, detail in _ITEMS:
        print(f"{'PASS' if passed else 'FAIL'}  {label}{'  ' + detail if detail else ''}")
    if total != _EXPECTED_ITEMS:
        print(f"判据总数 {total} ≠ 声明的 {_EXPECTED_ITEMS} —— 数量本身也是判据")
        return 1
    failed = [label for label, passed, _ in _ITEMS if not passed]
    if failed:
        print("红灯：" + ", ".join(failed))
        return 1
    print(f"全绿（{total} 项）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
