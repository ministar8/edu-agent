"""Evidence Chain 护栏（零 LLM）。判据数量本身也是判据。"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

_EXPECTED_ITEMS = 17
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


def check_2() -> None:
    """provenance 必须能区分「没记」与「记了且不同」；gold 必须有出处。

    ★ 断言打在**嵌套的 `provenance`** 上：`build_provenance()` 返回
      `{"recorded_at": ..., "provenance": {...}}`（`provenance.py:85-93`）。
      原稿在这里踩过坑 —— 顶层没有这些键，从顶层取会永远取到 None（就是 #3 那条 bug 的成因）。
    """
    import json

    from evaluation.provenance import build_provenance

    inner = build_provenance("evaluation.task_eval.runner")["provenance"]
    check(
        "2a script/argv 已在既有输出里（本 Task 的活是不再丢弃，不是新造）",
        bool(inner.get("script")) and isinstance(inner.get("argv"), list),
    )
    check("2b 含 experiment_config_hash", isinstance(inner.get("experiment_config_hash"), str))
    check("2c 含 dependency_lock_hash", isinstance(inner.get("dependency_lock_hash"), str))
    check("2d 不落任何密钥原值", "api_key" not in json.dumps(inner).lower())

    from evaluation.task_eval.cases import Gold

    check("2e Gold 有 gold_source_ref 字段", "gold_source_ref" in Gold.__dataclass_fields__)


def check_3() -> None:
    """R5：应有但测不到 ⇒ 毒化合取。「不适用」⇒ 不毒化。"""
    from evaluation.task_eval.predicates import common as pc

    mix: dict[str, pc.Verdict] = {"gen_structure": "pass", "gen_coverage": "pass"}
    check("3a 全 pass ⇒ pass", pc.composite(mix) == "pass")
    check("3b 任一 fail ⇒ fail", pc.composite({**mix, "gen_correctness": "fail"}) == "fail")
    check(
        "3c required 项 missing_premise ⇒ 复合 missing_premise（★ 不得为 pass）",
        pc.composite(
            {**mix, "gen_correctness": "missing_premise", "gen_answerability": "missing_premise"}
        )
        == "missing_premise",
    )
    check(
        "3d not_applicable 不毒化",
        pc.composite({**mix, "gen_difficulty": "not_applicable"}) == "pass",
    )
    r = pc.rate(["pass", "fail", "missing_premise", "not_applicable"])
    check("3e 分母只含已测", r["n"] == 2, str(r))
    check("3f 两种 N/A 分开计数", r["n_a_missing_premise"] == 1 and r["n_a_not_applicable"] == 1)
    check(
        "3g 全 missing_premise ⇒ rate=None 而非 0.0",
        pc.rate(["missing_premise", "missing_premise"])["rate"] is None,
    )


def main() -> int:
    check_1()
    check_2()
    check_3()
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
