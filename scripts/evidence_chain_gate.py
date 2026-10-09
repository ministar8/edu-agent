"""Evidence Chain 护栏（零 LLM）。判据数量本身也是判据。"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

_EXPECTED_ITEMS = 58  # Task 7 结束时 49；Task 8 Step 1（8a–8g）+7 = 56；T8-C/T8-E（8h/8i）+2 = 58
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


def check_6() -> None:
    from evaluation.task_eval import claims as cl

    ok = dict(
        falsify_passed=True, tier_ok=True, discriminating=True, provenance_match=True, signed=True
    )
    check("6a 五条件齐 ⇒ proven", cl.derive_status({}, **ok) == cl.CLAIM_PROVEN)
    for key in ok:
        bad = {**ok, key: False}
        check(
            f"6b 缺 {key} ⇒ 不得 proven",
            cl.derive_status({}, **bad) != cl.CLAIM_PROVEN,
        )
    check(
        "6c provenance 不符自动降级（§9 三态推导取证行）",
        cl.derive_status({}, **{**ok, "provenance_match": False}) == cl.CLAIM_MEASURED,
    )
    # tier_ok 的两个前置必须是**算出来的**，不是文档里写「已有抖动数据」
    check(
        "6d 边界档不足 ⇒ boundary_calibrated=False（实测 calibration_30 = {5:28,2:1,0:1}）",
        cl.boundary_calibrated([5.0] * 28 + [2.0, 0.0]) is False,
    )
    check("6e 边界两侧各 ≥3 ⇒ True", cl.boundary_calibrated([5.0, 5.0, 5.0, 3.0, 3.0, 3.0]) is True)
    # ★ 读**真实校准集**（不放夹具值，防止以后有人只测夹具）：当前边界档（3/4）零样本
    #   ⇒ False 是诚实状态。若将来补齐边界标注使此判据变 True，就把断言改成 True
    #   并在 commit message 里引用 EVIDENCE_CHAIN.md §7.2 —— 判据跟着事实走。
    import json

    human = [
        float(json.loads(line)["human_score"])
        for line in Path("evals/datasets/demo/calibration_30.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip() and not line.startswith("#")
    ]
    check("6f 真实校准集的边界覆盖状态被如实记录", cl.boundary_calibrated(human) is False)

    # ★ 评审 I-2 落地：tier 是「这个数字由谁决定」的声明。字面量必须带白名单锚点，
    #   且锚点跟着事实走 —— 防 `tier: 1  # 忘了为什么`，也防日后把 1 机械改成 2 而不重新证明。
    import build_claim_ledger as bcl  # noqa: E402  （同目录脚本，检查申报表的静态一致性）

    # ★ Task 7 Step 4b：白名单已上移到 `claims`（ledger 行侧与 registry 判据侧共用一份）
    #   ⇒ 这里引用 `cl.TIER_ANCHORS` / `cl.tier_justification`，不再引用 `bcl.*`。
    lit = bcl.LITERAL_TIER_REASONS
    bad_anchors = {
        d: sorted(a for a in ans if a not in cl.TIER_ANCHORS)
        for d, (t, ans) in lit.items()
        if any(a not in cl.TIER_ANCHORS for a in ans)
    }
    empty = sorted(d for d, (_t, ans) in lit.items() if not ans)
    check(
        "6g 字面量 tier 锚点全部在册且非空（缺依据 ⇒ 构建即抛）",
        not bad_anchors and not empty,
        f"越界 {bad_anchors} 空 {empty}",
    )
    # 牙齿实测（不是「存在即通过」）：现场拆掉依据，必须抛 ValueError 而不是放行
    teeth = []
    for spec, why in (
        ({"tier": 1}, "字面量无 tier_reason"),
        ({"tier": 1, "tier_reason": ("D99-not-a-decision",)}, "锚点不在白名单"),
    ):
        try:
            cl.tier_justification("Grade", spec)
            teeth.append(why)
        except ValueError:
            pass
    check("6g2 拆掉依据确实红（漏报=0）", len(teeth) == 0, str(teeth))
    uncovered = sorted(set(bcl._ROW_BUILDERS) - set(lit) - bcl.DERIVED_TIER_DIMS)
    check(
        "6h 每个维度行都申报了 tier 来源（无行能绕过）",
        not uncovered,
        f"未申报 {uncovered}",
    )
    tier2_dims = sorted(d for d in bcl._ROW_BUILDERS if (lit.get(d, (None, ()))[0] == 2))
    check(
        "6h2 走校准前置的 tier-2 行只有 QA（§6 原文的 judge 门槛；Verify/Grade 主指标已换轨 ⇒ 见 §7 偏离）",
        tier2_dims == ["QA"],
        str(tier2_dims),
    )
    # 派生行的 tier 由 registry 决定 ⇒ 这里核对「当前没有任何派生行落在 tier 2」。
    # tier=2 的判据若存在，只能是 optional 机械替身（不顶替主行）；其 tier 值本身属 Task 3 遗留
    # （替身按 §1.3 应为 tier 0/1），登记不在此处改。
    from evaluation.task_eval.predicates import registry as _reg

    derived_max: dict[str, int] = {}
    for dim in sorted(bcl.DERIVED_TIER_DIMS):
        task = {"Generate": "generate", "Verify": "verify", "Memory": "memory"}[dim]
        preds = _reg.for_task(task)
        keep = [p for p in preds if not p.optional] if dim != "Memory" else preds
        derived_max[dim] = max((p.tier for p in keep), default=1)
    tier2_preds = sorted(p.name for p in _reg.for_task("generate") if p.tier == 2 and p.optional)
    check(
        "6h3 派生行当前 max(tier)≤1；tier-2 只出现在 optional 替身（不进主行）",
        all(v <= 1 for v in derived_max.values()) and bool(tier2_preds),
        f"{derived_max}；optional tier2={tier2_preds}",
    )


def check_7() -> None:
    """V0（§8①/§8②）：schema 完整性 + 「未测量的 required 判据 ⇒ 禁止进门槛行」。"""
    from evaluation.task_eval import claims as cl
    from evaluation.task_eval import schema_gate as sg
    from evaluation.task_eval.predicates import registry as reg

    bad = {"task": "generate", "case_id": "z", "reply": ""}  # 缺 item_reasons / gold
    errs = sg.check_archive_records([bad])
    check("7a 缺字段 ⇒ 报错，而不是默认 False 通过", bool(errs))
    # ★ 评审 I-1：detail 里带上**实际扫到的文件数** —— 「0 命中」和「扫了 0 个文件」是两件事，
    #   前者是真绿，后者是包被改名/模块被挪层时的假绿（`rglob` 对不存在的目录不报错）。
    hits, n_scanned = sg.scan_default_masking("evaluation.task_eval.predicates")
    check(
        "7b predicates 包内无 .get(k, False) 掩盖",
        not hits and n_scanned > 0,
        f"扫到 {n_scanned} 个 .py" + (f"；命中 {'; '.join(hits)}" if hits else ""),
    )
    check(
        "7c 任一 required 判据 missing_premise ⇒ 该 claim 不可进门槛",
        sg.gate_rejects({"gen_correctness": "missing_premise"}) is True,
    )
    check(
        "7d 全 not_applicable 且非 required ⇒ 不阻塞（§8 划清）",
        sg.gate_rejects({"gen_difficulty": "not_applicable"}) is False,
    )
    # ★ 这一条钉住「生产者先于消费者」：registry 查不到判据 ⇒ required 为空 ⇒ gate_rejects 静默 False
    empty_required = [t for t in ("generate", "verify", "memory") if not sg.required_predicates(t)]
    check(
        "7e required_predicates() 对三个任务都非空（防 V0 因空集合静默放行）",
        not empty_required,
        f"registry 缺：{empty_required}",
    )

    # Step 4b：判据侧的 tier 申报（与 ledger 行侧同一道锁，白名单只有 `claims.TIER_ANCHORS` 一份）
    no_reason = sorted(
        p.name
        for p in reg.all_preds()
        if not p.tier_reason or any(a not in cl.TIER_ANCHORS for a in p.tier_reason)
    )
    check("7f 每个判据的 tier 都带白名单锚点（不许裸写）", not no_reason, str(no_reason))
    tier2 = sorted(p.name for p in reg.all_preds() if p.tier == 2)
    # ★ 评审 I-2：债标记是**双向**的锚点，不是只能被单方向验证的字符串 ——
    #   旧版只锁「tier==2 的集合」⇒ 把 `TIER-DEBT-task3` 贴到 tier=1 的判据上时 7f/7g 全绿，
    #   正式感很强的锚点于是可以贴在不是债的行上、被稀释成装饰。
    debt = sorted(p.name for p in reg.all_preds() if "TIER-DEBT-task3" in p.tier_reason)
    check(
        "7g tier=2 判据集合 == 已登记的 Task 3 遗留债名单（改判据须同步改本表）",
        tier2 == debt == ["gen_analysis_agreement", "gen_answer_key_validity"],
        f"tier=2 集合 {tier2}；挂 TIER-DEBT-task3 的集合 {debt}",
    )
    # ★ `7g` 通过的语义是「**债名单与登记一致**」，不是「债务已清偿」：
    #   这两条是 optional 机械替身，按 §1.3 的证据种类应为 tier 0/1（Task 3 registry debt），
    #   checkpoint 6 裁定本轮只登记不改。谁将来把 tier 改成 1，`7g` 会红 ⇒ 逼他同步删这条登记，
    #   而不是让「改了什么」静默消失。⇒ 报告里不得写「V0 全绿 ⇒ schema 问题已解决」。

    # 评审 I-4（= 偏差 D5）：`item_reasons` 缺键检查的**作用域**是推导出来的 ⇒ 必须双向钉死，
    #   否则「把它扩成整类任务都跳过」甚至「全部跳过」时，现有 7 项里不会有任何一条变红。
    def _reports_item_reasons(rec: dict[str, Any]) -> bool:
        return any(
            str(rec.get("case_id")) in e and "item_reasons" in e
            for e in sg.check_archive_records([rec])
        )

    # 夹具覆盖归档里出现过的**全部五个**任务名 ⇒ 跳过集合只要往任何一类上扩，就有一条变红。
    has_pred = [
        {"task": "generate", "case_id": "7h-gen"},
        {"task": "verify", "case_id": "7h-ver"},
        {"task": "memory", "case_id": "7h-mem"},
    ]
    no_pred = [{"task": "qa", "case_id": "7h-qa"}, {"task": "grade", "case_id": "7h-grade"}]
    reported = sorted(str(r["task"]) for r in has_pred if _reports_item_reasons(r))
    widened = sorted(str(r["task"]) for r in no_pred if _reports_item_reasons(r))
    still_clean = not any(sg.check_archive_records([r]) for r in no_pred)
    stats = sg.missing_key_report(has_pred + no_pred)
    derived_skip = sum(1 for r in has_pred + no_pred if not reg.for_task(str(r["task"])))
    check(
        "7h item_reasons 作用域双向锁：有判据任务必报 / qa·grade 必不报 + 跳过条数==无判据记录数",
        reported == ["generate", "memory", "verify"]
        and not widened
        and still_clean
        and stats.n_skipped_not_applicable == derived_skip == 2,
        f"报出={reported} 被多跳={widened} 无判据行仍报错={not still_clean} "
        f"跳过={stats.n_skipped_not_applicable}(推导 {derived_skip})",
    )


def _gold(*, should: bool = True, values: tuple[str, ...] = ("平衡二叉树",)):
    """造一份可机械判定的 gold。

    已核实的真源：`cases.py:85` ⇒ `MEMORY_TYPES = frozenset({"weak_topics"})`（**只有一个合法值**，
    且 frozenset 不能下标取元素 —— 别写 `MEMORY_TYPES[0]`）；
    `cases.py:120` ⇒ 可机械判定要求 `type ∈ MEMORY_TYPES` ∧ `bool(values)` ∧ `should_be_recalled is not None`。
    """
    from evaluation.task_eval.cases import ExpectedAnswerProperty, ExpectedMemory, Gold

    return Gold(
        expected_memory=ExpectedMemory(
            type="weak_topics", values=list(values), should_be_recalled=should
        ),
        # ★ 偏差（Task 8 报告 D-1）：brief 原样是 `ExpectedAnswerProperty()`，并注释
        #   「全默认 ⇒ forbidden_values 为空 ⇒ correct ≡ used」。**实测不成立** ——
        #   `cases.py:134` 的默认是 `forbidden_values: list[str] | None = None`，
        #   而 `None` 的语义是**未标注**（`cases.py:131` 明写「必填（可为 []）」），
        #   ⇒ `ExpectedAnswerProperty().is_valid()` 为 False ⇒ `memory_mechanizable()` False
        #   ⇒ 8a/8b/8c 全拿到 None（实测 FAIL 过，见报告）。
        #   本夹具要的是「可机械判定的 gold」⇒ 显式传 `[]`（= 标注了「无禁止值」，
        #   此时 `correct ≡ used` 这条退化才真的成立）。
        expected_answer_property=ExpectedAnswerProperty(forbidden_values=[]),
    )


def check_8() -> None:
    from evaluation.task_eval.memory_scorer import judge_memory_mechanically as J

    def _v(status: str, cards: list[str], hit: bool = True):
        return J(
            memory_cards=cards,
            reply="平衡二叉树" if hit else "",
            gold=_gold(),
            read_status=status,
        )

    check(
        "8a success+命中 ⇒ recalled_actual True",
        _v("success", ["数据结构 平衡二叉树"]).recalled_actual is True,
    )
    check("8b success+未命中 ⇒ False", _v("success", ["操作系统 页表"]).recalled_actual is False)
    check("8c empty ⇒ False（读到了，确实没卡）", _v("empty", []).recalled_actual is False)
    check("8d failed ⇒ None（★ 绝不记 False）", _v("failed", []).recalled_actual is None)
    check("8e not_attempted ⇒ None", _v("not_attempted", []).recalled_actual is None)
    check("8f failed 时 recalled_pass 为 None 而非 False", _v("failed", []).recalled_pass is None)
    from pathlib import Path

    sites = [
        p
        for p in (
            "src/evaluation/retrieval_gate.py",
            "src/evaluation/task_eval/runner.py",
            "src/rag/routes.py",
        )
        if "reset_query_failures()" in Path(p).read_text(encoding="utf-8")
    ]
    check(
        "8g reset 被三个取证单元各调一次（只加方法不调用 = B7 没闭合）",
        len(sites) == 3,
        f"只找到 {sites}",
    )

    # ── 8h（T8-C）：可用性必须被**证明**，不是被相信 ─────────────────────
    #   把 BM25 打坏，走**真实服务链路**（`_raw_search` → `_run()` → `_safe_to_thread`），
    #   断言三件事同时成立：① 不抛出（服务仍能收敛为「该路由空结果」）
    #   ② 失败被记进 `query_failures`（不是咽掉）③ 结果是空/默认值。
    #   用**不存在的 collection 名**制造故障：`get_collection()` 必然抛，
    #   且不需要起 Chroma 服务、不需要 embedding、零 token。
    import asyncio

    from rag import routes
    from rag.bm25 import bm25_search
    from rag.vectorstore import get_vector_store_manager

    mgr = get_vector_store_manager()
    missing = "__evidence_chain_gate_no_such_collection__"

    mgr.reset_query_failures()
    service_raised = ""
    try:
        route_id, docs = asyncio.run(
            routes._safe_to_thread(
                "keyword_bm25",
                lambda: (
                    "keyword_bm25",
                    routes._raw_search("平衡二叉树", missing, 3, route_name="keyword_bm25"),
                ),
                timeout=30.0,
                default=("keyword_bm25", []),
            )
        )
    except BaseException as exc:  # noqa: BLE001 — 这条判据的存在意义就是抓「服务路径 500」
        service_raised = f"{exc.__class__.__name__}: {exc}"
        route_id, docs = "", None
    service_failures = mgr.query_failures

    mgr.reset_query_failures()
    producer_raised = False
    try:
        bm25_search(["平衡二叉树"], missing, 3)
    except Exception:  # noqa: BLE001
        producer_raised = True
    producer_failures = mgr.query_failures
    check(
        "8h BM25 打坏：服务链不抛出+结果为空，且失败**确实被记录**（生产者侧必须抛）",
        not service_raised
        and route_id == "keyword_bm25"
        and docs == []
        and any(missing in f and "bm25" in f for f in service_failures)
        and producer_raised
        and any(missing in f and "bm25" in f for f in producer_failures),
        f"服务链={service_raised or '未抛出✓'} 结果={docs if docs is not None else 'N/A'} "
        f"服务侧记录={service_failures} 生产者抛={producer_raised} 生产者记录={producer_failures}",
    )

    # ── 8i（T8-E）：归因的 tier-0 门，用**合成 JudgeOutput**驱动真实写入函数 ──
    #   零 LLM：`JudgeOutput` 是 pydantic 模型，直接构造即可。
    #   三行规则逐条钉，断言打在 `apply_judge_to_dict` 的**实际输出**上。
    from evaluation.task_eval.judge import JudgeOutput, apply_judge_to_dict

    def _rec(**over: object) -> dict:
        rec = {
            "task": "verify",
            "case_id": "8i",
            "retrieval_status": "ok",
            "pack_nonempty": True,
            "hard_fails": [],
            "reply": "参考答案：A",
            "failure_reason": [],
            "validity_valid": None,
        }
        rec.update({k: v for k, v in over.items()})
        return rec

    retrieval_layer = {"retrieval_miss", "retrieval_dropped", "evidence_pollution"}

    # 行 1：`error` ⇒ 只能是 `tool_error`；judge 的 `retrieval_miss` 必须被隔离
    r1 = _rec(retrieval_status="error", pack_nonempty=False)
    apply_judge_to_dict(
        r1, JudgeOutput(final_quality=2, failure_reason=["retrieval_miss"]), judge_model="synthetic"
    )
    row1 = (
        "tool_error" in r1["failure_reason"]
        and "retrieval_miss" not in r1["failure_reason"]
        and r1["judge_failure_reasons"] == ["retrieval_miss"]
        and r1["primary_failure"] == "tool_error"
    )

    # 行 2：`empty` ∧ `pack_nonempty is False` ⇒ 机械 `retrieval_miss` **允许**进入
    r2 = _rec(retrieval_status="empty", pack_nonempty=False)
    apply_judge_to_dict(
        r2, JudgeOutput(final_quality=2, failure_reason=[]), judge_model="synthetic"
    )
    row2 = "retrieval_miss" in r2["failure_reason"] and not r2["judge_failure_reasons"]

    # 行 3：`ok` ∨ `pack_nonempty is True` ⇒ failure_reason 里**没有任何**检索层原因
    r3 = _rec(retrieval_status="ok", pack_nonempty=True)
    apply_judge_to_dict(
        r3,
        JudgeOutput(final_quality=2, failure_reason=sorted(retrieval_layer)),
        judge_model="synthetic",
    )
    row3 = not (set(r3["failure_reason"]) & retrieval_layer) and r3[
        "judge_failure_reasons"
    ] == sorted(retrieval_layer)
    check(
        "8i 检索层归因只由 tier-0 供给（error→tool_error / empty→允许 / ok→全禁）",
        row1 and row2 and row3,
        f"行1={r1['failure_reason']}/{r1['judge_failure_reasons']}/{r1['primary_failure']} "
        f"行2={r2['failure_reason']}/{r2['judge_failure_reasons']} "
        f"行3={r3['failure_reason']}/{r3['judge_failure_reasons']}",
    )


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
