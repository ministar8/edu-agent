"""Evidence Chain 护栏（零 LLM）。判据数量本身也是判据。

★ 原单文件已拆为「内核 `_ecg_core` + 判据组」：`_ecg_checks_basic`（1–7）/
  `_ecg_check8`（8a–8o）/`_ecg_checks_9a`（9·9j·9k-l）/`_ecg_checks_9b`（9m–9r）。
  本文件只留装配（`main`）与取证落盘（`emit_falsify_report`）；计数器、共用夹具
  （`check` / `_falsify_all` / `_gold` 等）与 sys.path 注入见 `_ecg_core`。
"""

from __future__ import annotations

import sys

from _ecg_check8 import check_8
from _ecg_checks_9a import check_9, check_9reprobe, check_9verify
from _ecg_checks_9b import check_9delivery, check_9goldstatus
from _ecg_checks_basic import check_1, check_2, check_3, check_4, check_5, check_6, check_7
from _ecg_core import _EXPECTED_ITEMS, _ITEMS, _falsify_all


def emit_falsify_report(path: str = "evals/claims/falsify_latest.json") -> None:
    """把取证结果落盘成 ledger 的输入（Task 6 的 `falsify_passed` 读它，不靠人回忆）。"""
    import json
    from pathlib import Path

    rows = []
    for name, results in _falsify_all().items():
        rows.append(
            {
                "predicate": name,
                "inputs": [r.input for r in results],
                "all_flipped": all(r.flipped for r in results),
                "no_collateral": all(not r.collateral for r in results),
                "no_raise": all(not r.raised for r in results),
                # ★ baselines_pass 是夹具不变量（基线必须 pass）的落盘形式；
                #   冻结名此处为 False 属预期（P-1 未做），由 Task 6 按任务语义解读。
                "baselines_pass": all(r.baseline == "pass" for r in results),
            }
        )
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"falsify_latest.json 已写入 {path}")


def main() -> int:
    check_1()
    check_2()
    check_3()
    check_4()
    check_5()
    check_6()
    check_7()
    check_8()
    check_9()
    check_9reprobe()
    check_9verify()
    check_9delivery()
    check_9goldstatus()
    if "--emit" in sys.argv:
        emit_falsify_report()
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
    # ★ 评审 M-7：固定脚注（**不是判据**、不进计数器）—— 防止「越读越乐观」：
    #   gate 绿只证明拦网在位，V0 清偿与否是归档事实，只有 `--check` 第 3 段说得了。
    print("★ gate 全绿 = 拦网在位；V0 是否清偿只看 build_claim_ledger --check 的第 3 段。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
