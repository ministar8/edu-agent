"""Evidence Chain 护栏（零 LLM）。判据数量本身也是判据。"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

_EXPECTED_ITEMS = 26
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


def check_4() -> None:
    """报告必须只从 registry 取数；旧 `every_item_passes`/`delivery_rate` 不得再被引用。

    ★ 夹具即 §4.2 事故的形状（checkpoint 4 裁定，替代原稿的空 reply 夹具——
      空 reply 在旧代码下本就 rate=None，红→绿不可达）：
      四件套齐全的 reply + 无 gold ⇒ 旧代码 1.000（None 被剔出合取），
      registry 下 correctness/answerability missing_premise ⇒ 复合 missing_premise ⇒ rate=None。
    """
    import ast
    import pathlib

    from evaluation.task_eval.report import summarize_task

    # 旧式存储布尔（Task 2 之前的归档形状）：旧代码聚合出 1.000；
    # 同时 reply 四件套齐全 + gold 为空：新 registry 算出 missing_premise。
    # 两个世界共用这一条 record，红→绿才在 Step 2 前后各占一边。
    recs = [
        {
            "task": "generate",
            "case_id": "g1",
            "gen_structure": True,
            "gen_answerability": True,
            "gen_coverage": True,
            "gen_correctness": True,
            "gen_difficulty": None,
            "reply": (
                "题干：设 Cache 采用 2-Way 组相联，主存 64 块，Cache 8 行，问组号需要几位。\n"
                "A. 2\nB. 3\nC. 4\nD. 6\n"
                "标准答案：B\n"
                "解析：8 行分 2 路，8/2=4 组，组号需 2 位，因此选 B。"
            ),
            "top_items": [{"kp": ["co.overview"]}],
            "gold": {},
            "item_reasons": {},
        }
    ]
    rep = summarize_task("generate", recs)
    check(
        "4a gen_case_pass 变 missing_premise 而非 1.000（§4.2 回归）",
        isinstance(rep.gen_case_pass, dict) and rep.gen_case_pass.get("rate") is None,
    )
    check("4b 报告里带出 missing_n", isinstance(rep.gen_case_pass.get("n_a_missing_premise"), int))

    # ★ Task 4 评审 defer 的两词落点：`delivery_rate` 也在旧副本禁用名单里，且扫描
    #   从 src/ 扩到 ("src", "scripts") —— 当初逼出这条约束的调用点就长在 scripts 侧，
    #   只扫 src 等于把教训留在门外。（实测：scripts 侧仅剩 docstring 提及，AST 无命中。）
    banned = ("every_item_passes", "delivery_rate")
    hits = []
    for base_dir in ("src", "scripts"):
        for py in pathlib.Path(base_dir).rglob("*.py"):
            tree = ast.parse(py.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Name) and node.id in banned:
                    hits.append(f"{py}:{node.lineno}")
                if isinstance(node, ast.Attribute) and node.attr in banned:
                    hits.append(f"{py}:{node.lineno}")
    check("4c 生产代码不再引用旧合取函数", not hits, "; ".join(hits))

    import inspect

    from evaluation.task_eval import cli

    sig = inspect.signature(cli._update_retrieval_fields)
    check(
        "4d reprobe 必须显式接 k 与 cfg（不再硬编码 5）",
        {"k", "cfg"} <= set(sig.parameters),
        str(sig),
    )


def _gen_reply(
    *,
    stem: str = "题干：设 Cache 采用 2-Way 组相联，主存 64 块，Cache 8 行，问组号需要几位。",
    options: str = "A. 2\nB. 3\nC. 4\nD. 6",
    answer: str = "标准答案：B",
    explanation: str = "解析：8 行分 2 路，故 8/2=4 组，组号需 2 位……因此选 B。",
) -> str:
    """Task 5 的分段夹具：四段拼接，缺省全给（`falsify.apply` 逐段弄坏的原料）。"""
    parts = {"stem": stem, "options_or_task": options, "answer": answer, "explanation": explanation}
    return "\n\n".join(v for v in parts.values() if v)


def _base_record(**overrides: Any) -> dict:
    """falsify 的基线 record：四段齐全、答案键与解析结论**自洽**（都指 B）。"""
    rec = {
        "task": "generate",
        "case_id": "falsify-1",
        "reply": _gen_reply(),
        "top_items": [{"kp": ["co.overview"]}],
        "gold": {
            "gold_answer": "B",
            "gold_source_ref": {"gold_answer": "knowledge/co/ch3.md#组相联"},
            "expected_kp": ["co.overview"],
        },
        "item_reasons": {},
    }
    rec.update(overrides)
    return rec


def _falsify_all() -> dict[str, list[Any]]:
    """generate 每条判据 × 全部声明 mutation 的一次取证（check_5 与 --emit 共用）。"""
    from evaluation.task_eval import falsify
    from evaluation.task_eval.predicates import registry

    preds = registry.for_task("generate")
    out: dict[str, list[Any]] = {}
    for pred in preds:
        base = _base_record()
        siblings = {q.name: (q, base) for q in preds if q.name != pred.name}
        out[pred.name] = [
            falsify.evaluate(
                pred,
                base,
                falsify.apply(mutation=mut, record=base),
                mutation_input=mut["input"],
                siblings=siblings,
            )
            for mut in falsify.declared_mutations(pred)
        ]
    return out


def check_5() -> None:
    """R1-A：声明式 mutation 取证 —— 弄坏契约点名的每个输入，判据必须恰好变红。"""
    from evaluation.task_eval import falsify
    from evaluation.task_eval.predicates import registry

    all_results = _falsify_all()
    # ★ 5a-5d 按 brief 压在 gen_structure 上：它是唯一「夹具能使其 pass」的全 reply# 判据；
    #   冻结名（answerability/difficulty）基线本就 missing_premise（P-1 未做），
    #   那是诚实状态，不是夹具能修的前提（其余判据的逐 mutation 结果由 --emit 落盘披露）。
    p = registry.get("gen_structure")
    results = all_results[p.name]
    covered = {r.input for r in results}
    check(
        "5a 每个 contract_input 都有声明过的 mutation",
        covered == set(p.contract_inputs),
        f"缺 {set(p.contract_inputs) - covered}",
    )
    check(
        "5b 基线为 pass 且弄坏后不 pass（★ 基线本身就是红的话，这条必然红）",
        all(r.flipped for r in results),
        str(results),
    )
    check("5c 其余判据不受牵连", all(not r.collateral for r in results))
    check("5d 弄坏后不得抛异常", not any(r.raised for r in results))
    gaps = falsify.coverage(
        registry.for_task("generate"),
        {name: {r.input for r in rs} for name, rs in all_results.items()},
    )
    check("5e generate 判据无未覆盖契约输入", not gaps, str(gaps))


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
    return 0


if __name__ == "__main__":
    sys.exit(main())
