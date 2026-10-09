"""Evidence Chain 护栏（零 LLM）。判据数量本身也是判据。"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

_EXPECTED_ITEMS = 79  # Task 7 结束 49；Task 8 Step 1（8a–8g）+7 = 56；T8-C/T8-E（8h/8i）+2 = 58
# ★ 修复轮 F7 再 +4：`8j`（map_route_failures 双向）/`8k`（单元内 reset 回归锁）/
#   `8l`（run_case 必调 reset_memory_read_statuses，**行为**取证）/`8m`（gate 的 reset↔收割配对）
#   ⇒ 62；控制器复验发现 F6 的映射只由外部探针证明、62 项里没有一条会因它回归而红
#   ⇒ 补 `8n`（缺键/空串/failed ⇒ missing_premise 的双向回归锁）⇒ 63；
#   checkpoint 8 用户追加 `8o`（F6 的**结构**承重锁 —— 8n 的四条行为用例分不出 `has_path`
#   与真值写法，因为那三条分支输出同为 `missing_premise` ⇒ 只能走 AST 定位函数体内调用）⇒ **64**；
#   Task 9 Step 1（B2 四态判据 9a/9b/9c/9d/9e）+5 ⇒ 69；阶段 A 后半段 B2 两条验收探针 `9f`
#   + B1 唯一权威换算点结构锁 `9g` +2 ⇒ 71；控制器复验 B2「产生→存储→聚合→报告」全链路时发现
#   `rerank_status` 要跨**三跳改名**才落到归档（`_rerank_status` → `rerank_status` → probe → record），
#   每跳都带 `""` 掩盖默认值、且桥接在 `aretrieve_documents` 内部（纯内存测试拿不到）⇒ 补 `9h`
#   键名配对结构锁 ⇒ **72**；
#   ★ 收尾修复批（Important-1/2/3）+7：`9j`（reprobe 的 B7 消费侧**行为**锁：注入故障 ⇒ error
#   不降级 + 凭据成对刷新 + 下一条干净 record 不受染）/`9k`（verify 缺键/空串/ok/error 四格
#   **行为**锁，钉死「缺键不得 pass」）/`9l`（`_no_reply` 体内 `has_path` 的 AST 承重锁，8o 同款）/
#   `9m`（空包送达**行为**锁：真实 aretrieve_documents 的 finally 出参 + 真实 retriever 桥接五格）/
#   `9n`（基线 payload 导出 `_meta.rerank_status_counts` **行为**锁）/`9o`（probe 读侧五格等值
#   **行为**锁）/`9p`（record 侧 probe⇒record⇒to_dict 工件送达**行为**锁）⇒ **79**。
#   计数器只增不减：既有判据一条都不许删；`8g`/`8k` 的期望文件集随 reprobe 第三单元**按事实生长**
#   （不是放松 —— 单元内部 reset 的禁句 `8k` routes 零调用断言原样保留）。
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

    # ★ v1.3（checkpoint 8 裁定 R1-A）：原判据要求「三处」，其中 `rag/routes._amulti_route_search`
    #   每轮开头的**单元内** reset 已**撤销** —— 一条 query 会跑多轮（HyDE 在第一轮空/差之后才跑），
    #   后一轮的 reset 会抹掉前一轮**尚未被 `run_case` 消费**的失败证据（实测注入 BM25 全线故障
    #   ⇒ 读取时失败记录为 `[]`），检测能力反而**低于改动前**。reset 只允许在**独立取证单元的边界**
    #   （单元内部清空 = 销毁本单元的物证）⇒ 本判据期望 **两处**，撤销的回归锁由 `8k` 承担。
    # ★ 修复批 Important-1 的**按事实修订**（不是放松，是边界集合随新单元生长）：
    #   `cli._reprobe` 每条 record 的 reprobe 与 `run_case` 同构 = 独立取证单元 ⇒ 第三处**单元边界**
    #   （`src/evaluation/task_eval/cli.py`）。单元**内部**依旧禁止 reset（`8k` 的 routes 零调用不变）。
    reset_units = [
        p
        for p in (
            "src/evaluation/retrieval_gate.py",
            "src/evaluation/task_eval/runner.py",
            "src/evaluation/task_eval/cli.py",
        )
        if "reset_query_failures()" in Path(p).read_text(encoding="utf-8")
    ]
    check(
        "8g reset 被三个独立取证单元边界各调一次（gate/run_case/reprobe；单元内 reset 于 v1.3 撤销）",
        len(reset_units) == 3,
        f"只找到 {reset_units}",
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

    # ★ F3（覆盖面收进一处）把**两个方向**都压在同一条判据上（原判据的断言一条没减）：
    #   ① **不漏报**：超时**只有** `_safe_to_thread` 看得见 —— `asyncio.to_thread` 取消不了
    #      已启动的线程，被弃用的调用里的生产者永远不会记录。这里让被包的函数睡过 timeout，
    #      断言「不抛出 + 返回 default + 清单里恰有一条 `8h-timeout: TimeoutError`」。
    #      ⇒ 删掉 `_safe_to_thread` 的 TimeoutError 记录 ⇒ 本判据红（破坏性验证 ④ 的落点）。
    #   ② **不重复计数**：同一个异常会穿过**两层**收敛（`bm25_search` 就地记录后 `raise`，
    #      `_safe_to_thread` 又对**同一个异常对象**记一次）。去重键是**异常对象身份**
    #      （`VectorStoreManager.record_query_failure(..., exc=)`），不是文案匹配
    #      ⇒ 上面那次服务链调用结束时清单必须**恰好一条**（`len(service_failures) == 1`）。
    import time as _time

    mgr.reset_query_failures()
    timeout_raised = ""
    timeout_default: object = None
    try:
        timeout_default = asyncio.run(
            routes._safe_to_thread(
                "8h-timeout",
                lambda: (_time.sleep(0.4), "never-returned")[1],
                timeout=0.01,
                default="SENTINEL-DEFAULT",
            )
        )
    except BaseException as exc:  # noqa: BLE001 — 超时同样必须是「收敛 + 留痕」，不许外泄
        timeout_raised = f"{exc.__class__.__name__}: {exc}"
    timeout_failures = mgr.query_failures
    mgr.reset_query_failures()

    check(
        "8h BM25 打坏：服务链不抛出+结果为空，且失败**确实被记录**（生产者侧必须抛；"
        "超时不漏报、同异常不重复计数）",
        not service_raised
        and route_id == "keyword_bm25"
        and docs == []
        and any(missing in f and "bm25" in f for f in service_failures)
        and producer_raised
        and any(missing in f and "bm25" in f for f in producer_failures)
        and len(service_failures) == 1
        and not timeout_raised
        and timeout_default == "SENTINEL-DEFAULT"
        and timeout_failures == ["8h-timeout: TimeoutError"],
        f"服务链={service_raised or '未抛出✓'} 结果={docs if docs is not None else 'N/A'} "
        f"服务侧记录={service_failures} 生产者抛={producer_raised} 生产者记录={producer_failures} "
        f"超时链={timeout_raised or '未抛出✓'} 默认值={timeout_default!r} 超时记录={timeout_failures}",
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

    # ── 8j（F2）：消费侧的映射规则是**纯函数** ⇒ 判据里零 IO ─────────────
    #   双向都要钉：空清单**原样**（不许把 ok 折成 empty、也不许凭空造 error）；
    #   非空 ∧ `ok`/`empty` ⇒ 升 `error`；已是 `error` ⇒ **不降级**；未知值 ⇒ 不发明状态。
    from evaluation.task_eval.runner import map_route_failures

    notes = ["ds:keyword_bm25: RuntimeError"]
    j = {
        "空+ok": map_route_failures([], "ok"),
        "空+empty": map_route_failures([], "empty"),
        "空+error": map_route_failures([], "error"),
        "有+ok": map_route_failures(notes, "ok"),
        "有+empty": map_route_failures(notes, "empty"),
        "有+error": map_route_failures(notes, "error"),
        "有+未知": map_route_failures(notes, "weird"),
    }
    check(
        "8j map_route_failures 双向：空清单原样 / ok+empty 升 error / 已 error 不降级",
        j["空+ok"] == ("ok", [])
        and j["空+empty"] == ("empty", [])
        and j["空+error"] == ("error", [])
        and j["有+ok"] == ("error", notes)
        and j["有+empty"] == ("error", notes)
        and j["有+error"] == ("error", notes)
        and j["有+未知"] == ("weird", notes)
        # 返回的是**副本**（消费者拿到的清单不会与生产者的列表共享可变对象）
        and j["有+ok"][1] is not notes
        and j["空+ok"][1] is not notes,
        str(j),
    )

    # ── 8k（F1 的回归锁）：单元内 reset **不许回来** ─────────────────────
    #   ★ AST 定位（`ast.Call` 的函数名），**不是** grep 字符串 —— 注释/docstring 里
    #     提到 `reset_query_failures` 不算调用点（本文件与 routes.py 的注释里就有好几处，
    #     字符串判据会当场假红/假绿）。
    #   两个断言：① `src/rag/routes.py` 里**零**调用；
    #            ② 生产面（`src/`）该调用**恰好**落在**三个**独立取证单元文件
    #               （gate / run_case / reprobe；按**文件路径**判定，不是出现次数）——
    #               修复批 Important-1 把 `cli.py` 补成第三单元，`run_case` 与 `_reprobe`
    #               都以「一次检索探针」为单元边界；
    #            ③ `scripts/` 侧唯一持有者是 gate 自己的取证夹具（8h）——列进白名单并说明理由，
    #               否则「谁都能拿 reset 当测试脚手架」这件事也会变成隐式的第三点。
    import ast

    def _reset_call_files(base: str) -> set[str]:
        found: set[str] = set()
        for py in Path(base).rglob("*.py"):
            tree = ast.parse(py.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and getattr(node.func, "attr", "") == (
                    "reset_query_failures"
                ):
                    found.add(py.as_posix())
        return found

    routes_reset_calls: list[int] = []
    _routes_tree = ast.parse(Path("src/rag/routes.py").read_text(encoding="utf-8"))
    for _node in ast.walk(_routes_tree):
        if (
            isinstance(_node, ast.Call)
            and getattr(_node.func, "attr", "") == "reset_query_failures"
        ):
            routes_reset_calls.append(_node.lineno)
    src_units = _reset_call_files("src")
    scripts_units = _reset_call_files("scripts")
    check(
        "8k 单元内 reset 回归锁：routes 零调用 + src 恰好三个单元边界",
        not routes_reset_calls
        and src_units
        == {
            "src/evaluation/retrieval_gate.py",
            "src/evaluation/task_eval/runner.py",
            "src/evaluation/task_eval/cli.py",
        }
        and scripts_units == {"scripts/evidence_chain_gate.py"},
        f"routes 调用行={routes_reset_calls} src={sorted(src_units)} scripts={sorted(scripts_units)}",
    )

    # ── 8l（F5/B4 单元边界）：**行为**取证，不是源码字符串 ───────────────
    #   上一轮的真实漏洞：`run_case` 里那行 `reset_memory_read_statuses()` 被删掉后，
    #   58 + 217 项判据**全绿**（读链明细会在进程级通道里跨 case 粘连）。
    #   ⇒ 本判据**真的跑两次** `run_case`：第一个 case 注入一条 `failed`，
    #     断言第二个 case 的**明细与聚合**都不含它。抵抗「注释里提到函数名」的假阳性：
    #     只有实际调用才会清空通道。
    #   ★ 零 LLM：`_run_agent` 与 `probe_retrieval` 换成合成替身（它们各自要打模型 / 起 TEI），
    #     被取证的对象是 `run_case` **自己的**边界纪律与聚合路径（真实代码）。
    import agents.teaching_graph as _tg
    from evaluation.task_eval import runner as _runner
    from evaluation.task_eval.cases import TaskCase
    from evaluation.task_eval.retrieval_probe import RetrievalProbe

    _orig_run_agent = _runner._run_agent
    _orig_probe = _runner.probe_retrieval
    _orig_reset = _tg.reset_memory_read_statuses
    reset_spies: list[str] = []

    class _FakeCaseResult:
        reply = ""
        hard_fails: list[str] = []
        tool_payloads: list[dict] = []
        memory_cards: list[str] = []
        grade_scores: list[dict] = []
        turn_log: list[dict] = []
        episodes: list[dict] = []
        episodes_read_failed = False

    async def _fake_run_agent(_turns, **_kw):
        # 第一个 case 的读链坏一轮（走**唯一写入口**，四态之一）
        if _kw.get("case_id") == "8l-first":
            _tg.record_memory_read_status("failed")
        return _FakeCaseResult()

    async def _fake_probe(*_a, **_k):
        return RetrievalProbe(ok=True, status="ok", pack_len=10, evidence_count=1)

    def _spy_reset() -> None:
        reset_spies.append("called")
        _orig_reset()

    try:
        _runner._run_agent = _fake_run_agent
        _runner.probe_retrieval = _fake_probe
        _tg.reset_memory_read_statuses = _spy_reset
        _orig_reset()
        rec_l1 = asyncio.run(
            _runner.run_case(TaskCase(case_id="8l-first", task="memory", query="q"), k=1)
        )
        mid = len(reset_spies)
        rec_l2 = asyncio.run(
            _runner.run_case(TaskCase(case_id="8l-second", task="memory", query="q"), k=1)
        )
        # 聚合规则第 1 条（有卡 ⇒ success）压掉 `failed` 的**对应关系**取证：
        # 造一条「两轮里一轮坏、一轮拿到卡」的明细，验证聚合值与明细可同时成立。
        folded = _runner.aggregate_memory_read_status(["failed", "success"], ["平衡二叉树"])
    finally:
        _runner._run_agent = _orig_run_agent
        _runner.probe_retrieval = _orig_probe
        _tg.reset_memory_read_statuses = _orig_reset
        _orig_reset()

    check(
        "8l run_case 必调 reset_memory_read_statuses（行为：第二个 case 不含第一个的 failed）",
        mid == 1  # 每次 run_case 各调一次（第一条 case 期间正好一次）
        and len(reset_spies) == 2
        and rec_l1.memory_read_statuses == ["failed"]
        and rec_l1.memory_read_status == "failed"
        and rec_l2.memory_read_statuses == []  # ← 删掉那行 reset 会变成 ["failed"]
        and rec_l2.memory_read_status == ""
        # 明细 ↔ 聚合可对应：规则 1 把 failed 压成 success 时，明细里仍看得见 failed
        and folded == "success",
        f"reset 调用={len(reset_spies)} 次（第一 case 后 {mid}）"
        f" case1 明细={rec_l1.memory_read_statuses}/{rec_l1.memory_read_status}"
        f" case2 明细={rec_l2.memory_read_statuses}/{rec_l2.memory_read_status}"
        f" 折叠示例={folded}",
    )

    # ── 8m（F2/B7 收割配对）：reset 与 harvest 必须**成对**出现 ────────────
    #   上一轮实测：全仓**没有任何判据**碰过这个配对。「只 reset 不收割」比不修更静默 ——
    #   每条 query 前清空、却没人把清空前的记录累计起来 ⇒ 除最后一条 query 之外
    #   所有索引故障都被扔掉，门禁照样「健康」。
    #   ★ AST 依据（不是字符串）：在 `retrieval_gate.py` 里找到**含 reset 调用的那个函数**，
    #     要求它内部存在一个 `try/finally`，其 `finalbody` 里同时有
    #     ① 对 `.query_failures` 的**读取**（Load），② 对某个累计变量的 `.extend(...)` 调用，
    #     ③ 该累计变量出现在本函数的 `return` 值里（收割了又扔掉 = 仍然红）。
    _rg_tree = ast.parse(Path("src/evaluation/retrieval_gate.py").read_text(encoding="utf-8"))

    def _walk_many(nodes: list[ast.stmt]) -> list[ast.AST]:
        """`ast.walk` 只吃**单个**节点；`finalbody` 是节点列表 ⇒ 逐个展开再走。"""
        return [n for body in nodes for n in ast.walk(body)]

    def _has_reset_call(node: ast.AST) -> bool:
        return any(
            isinstance(c, ast.Call) and getattr(c.func, "attr", "") == "reset_query_failures"
            for c in ast.walk(node)
        )

    _rg_funcs = [
        n
        for n in ast.walk(_rg_tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and _has_reset_call(n)
    ]
    pairing: list[str] = []
    for fn in _rg_funcs:
        acc_vars: set[str] = set()
        for t in ast.walk(fn):
            if not isinstance(t, ast.Try) or not t.finalbody:
                continue
            final_nodes = _walk_many(t.finalbody)
            loads_failures = any(
                isinstance(x, ast.Attribute) and x.attr == "query_failures" for x in final_nodes
            )
            extends = [
                x
                for x in final_nodes
                if isinstance(x, ast.Call)
                and isinstance(x.func, ast.Attribute)
                and x.func.attr == "extend"
                and isinstance(x.func.value, ast.Name)
            ]
            if loads_failures and extends:
                acc_vars.update(e.func.value.id for e in extends)  # type: ignore[attr-defined]
        returned = {
            n.id
            for r in ast.walk(fn)
            if isinstance(r, ast.Return) and r.value is not None
            for n in ast.walk(r.value)
            if isinstance(n, ast.Name)
        }
        if not acc_vars or not (acc_vars & returned):
            pairing.append(
                f"{fn.name}: 累计变量={sorted(acc_vars)} return 里的名字={sorted(returned)}"
            )
    check(
        "8m retrieval_gate 的 reset 与收割成对（finalbody 读 query_failures + extend 同一累计变量 + 该变量被 return）",
        bool(_rg_funcs) and not pairing,
        f"含 reset 的函数={[f.name for f in _rg_funcs]}；未配对={pairing}",
    )

    # ── 8n（修复轮 F6 的回归锁）：四态不许把「键缺失」折成「样本不适用」──────────
    #   ★ 控制器实测（2026-10-09）：F6 的映射此前只有外部探针脚本在证，62 项里没有一条会因
    #     它回归而红 ⇒ 这里补成双向断言。老归档（无 `memory_read_status` 键）跨多份归档实测 37 条。
    from evaluation.task_eval.predicates import registry as _reg8

    _pred = _reg8.get("memory_correct_use")
    _mech_gold = {
        "expected_memory": {
            "type": "weak_topics",
            "values": ["平衡二叉树"],
            "should_be_recalled": True,
        },
        "expected_answer_property": {"forbidden_values": []},
    }
    _base = {"task": "memory", "case_id": "f6", "reply": "", "memory_cards": []}
    missing_key = {**_base, "gold": _mech_gold}
    empty_val = {**missing_key, "memory_read_status": ""}
    failed_val = {**missing_key, "memory_read_status": "failed"}
    non_mech = {
        **_base,
        "memory_read_status": "success",
        "gold": {**_mech_gold, "expected_memory": {**_mech_gold["expected_memory"], "values": []}},
    }
    folded = [
        name
        for name, v in (
            ("缺键", missing_key),
            ("空串值", empty_val),
            ("读链故障", failed_val),
        )
        if _pred.fn(v) != "missing_premise"
    ]
    na_wrong = _pred.fn(non_mech) != "not_applicable"
    check(
        "8n 缺键/空串/failed ⇒ missing_premise，只有不可机械判定的样本才是 not_applicable（F6 回归锁）",
        not folded and not na_wrong,
        f"被折叠={folded}；不适用正例异常={na_wrong}",
    )

    # ── 8o（F6 的**结构**承重锁）：缺键区分必须由 `has_path` 承担，不能退化成真值判断 ──
    #   ★ 为什么 8n 不够：`_correct_use` 里「缺键 / 空串 / failed」三条分支**输出相同**
    #     （都 `missing_premise`）⇒ 任何行为用例都分不出 `has_path(...)` 与
    #     `rec.get("memory_read_status")` 的真值写法。所以这条只能走 AST：
    #     断言 `_correct_use` **函数体内**确有对 `has_path` 的调用、且实参点名 `memory_read_status`。
    #   ★ 不是「源码里出现过 has_path 这个字符串」—— 那连 import 都能满足，去掉承重分支照样绿。
    import ast as _ast8o
    import pathlib as _pl8o

    _mem_src = (
        _pl8o.Path(__file__).resolve().parents[1] / "src/evaluation/task_eval/predicates/memory.py"
    ).read_text(encoding="utf-8")
    _fn = next(
        (
            n
            for n in _ast8o.walk(_ast8o.parse(_mem_src))
            if isinstance(n, _ast8o.FunctionDef) and n.name == "_correct_use"
        ),
        None,
    )
    _hp_calls = [
        n
        for n in _ast8o.walk(_fn)
        if isinstance(n, _ast8o.Call)
        and (getattr(n.func, "id", "") or getattr(n.func, "attr", "")) == "has_path"
    ]
    _names_key = any(
        any("memory_read_status" in _ast8o.unparse(a) for a in n.args) for n in _hp_calls
    )
    check(
        "8o _correct_use 体内确以 has_path 区分缺键（AST 承重锁，非字符串存在性）",
        _fn is not None and len(_hp_calls) >= 1 and _names_key,
        f"_correct_use 存在={_fn is not None}；体内 has_path 调用={len(_hp_calls)} 处；点名键={_names_key}",
    )


def check_9() -> None:
    """B2 `rerank_status` 四态（§5 B2 / §6）+ B1 语义统一（§1.5 R4）的取证判据。

    Step 1 先红：`from rag.pipeline import _derive_rerank_status` 触发 ImportError
    （生产者尚不存在）⇒ 判据先于实现落地，红→绿才可信。
    """
    from rag.pipeline import _derive_rerank_status as D

    class _D:
        def __init__(self, md):
            self.metadata = md

    check("9a 开关关 ⇒ off", D([_D({})], active=False, raised=False, empty_result=False) == "off")
    check(
        "9b 抛错 ⇒ failed",
        D([_D({"rerank_score": 0.1})], active=True, raised=True, empty_result=False) == "failed",
    )
    check(
        "9c 无分降级 ⇒ degraded",
        D([_D({})], active=True, raised=False, empty_result=False) == "degraded",
    )
    check(
        "9d 合法 0.0 分仍是 success（★ on 路由不被误翻）",
        D([_D({"rerank_score": 0.0})], active=True, raised=False, empty_result=False) == "success",
    )
    check(
        "9e 空 docs 不得因 all([]) == True 被判 success",
        D([], active=True, raised=False, empty_result=False) == "degraded",
    )

    # ── 9f（B2 验收 · 存储/派生）：缺失前提不折叠 + off 不冒充 success ──────────
    #   用户原话两条验收各写一条行为探针，别只在文字里声明。
    from evaluation.task_eval.runner import CaseRecord as _CR

    def _used(status: str) -> bool:
        return _CR(
            case_id="x", task="qa", task_mode="learn", query="q", rerank_status=status
        ).rerank_used

    # 只有 success ⇒ rerank_used True；off/degraded/failed/""（未知）全 False。
    derived_ok = (
        _used("success") is True
        and _used("off") is False  # ★ 未执行重排(off) 不得被误报为重排成功
        and _used("degraded") is False
        and _used("failed") is False
        and _used("") is False  # ★ 缺失前提（老归档没写）不得被折成成功
    )
    # `rerank_used` 必须是**派生 property**，不再是独立自报布尔字段（不进 __dataclass_fields__）。
    is_derived = "rerank_used" not in _CR.__dataclass_fields__ and isinstance(
        getattr(_CR, "rerank_used", None), property
    )
    # 未知态（""）既不等于 failed 也不等于 success —— 缺失前提不得被折成普通失败。
    not_folded = _CR(case_id="y", task="qa", task_mode="learn", query="q").rerank_status == ""
    check(
        "9f rerank_used 是派生 property：仅 success⇒True；off/degraded/failed/未知 全 False 且缺失不折成失败（B2 验收）",
        derived_ok and is_derived and not_folded,
        f"派生={is_derived} off冒充={_used('off')} 未知冒充={_used('')}",
    )

    # ── 9g（B1 唯一权威换算点结构锁）：semantic_cache 私有实现必须已删除 ──────────
    #   ★ 破坏性验证 ④ 的落点：在 semantic_cache.py 恢复一份 `1.0 - distance` ⇒ 本判据红。
    import pathlib as _pl9

    from rag.embeddings import SUPPORTED_SPACES as _SS
    from rag.embeddings import similarity_from_distance as _SFD

    spaces_ok = _SS == frozenset({"cosine", "l2", "ip"})
    raised_unknown = False
    try:
        _SFD(0.1, "hamming")  # 未登记的 space ⇒ 必须抛，不静默回退成 cosine
    except ValueError:
        raised_unknown = True
    _sc_src = (_pl9.Path(__file__).resolve().parents[1] / "src/rag/semantic_cache.py").read_text(
        encoding="utf-8"
    )
    _vs_src = (_pl9.Path(__file__).resolve().parents[1] / "src/rag/vectorstore.py").read_text(
        encoding="utf-8"
    )
    # semantic_cache 不再持有私有换算（`1.0 - distance` 只允许出现在注释里，不能作为赋值表达式）
    _sc_no_private = not any(
        line.strip().startswith(("similarity =", "score =", "sim ="))
        and "1.0 - distance" in line
        and not line.strip().startswith("#")
        for line in _sc_src.splitlines()
    )
    _sc_routes_through = "similarity_from_distance(" in _sc_src
    _vs_routes_through = _vs_src.count("similarity_from_distance(") >= 1 and "hnsw:space" in _vs_src
    check(
        "9g B1 唯一权威换算点：未知 space 抛错 + semantic_cache 私有实现已删 + vectorstore 经此换算（结构锁）",
        spaces_ok
        and raised_unknown
        and _sc_no_private
        and _sc_routes_through
        and _vs_routes_through,
        f"表={_SS} 未知抛={raised_unknown} 私有删={_sc_no_private} "
        f"cache经点={_sc_routes_through} vectorstore经点={_vs_routes_through}",
    )

    # ── 9h（B2 全链路**名称配对**结构锁）：`rerank_status` 要跨三跳改名才落到归档 ──────
    #   pipeline 写 `doc.metadata["_rerank_status"]` → retriever 桥接成 `fused.metadata["rerank_status"]`
    #   → retrieval_probe 读该键 → runner 落 `record.rerank_status`（`rerank_used` 由它派生）。
    #   ★ 为什么这条只能走结构：桥接发生在 `aretrieve_documents` 内部（要碰 Chroma），
    #     纯内存行为测试拿不到它；而每一跳都带 `""` 掩盖默认值 ⇒ 任何一侧改名都会让下游
    #     **静默变成「未知」**，9f/9g 都不会红（9f 测纯函数、9g 测 B1）。
    #   ★ 本判据锁的是「四处的键名与赋值方向必须成对存在」——改名即红；
    #     它**不**证明运行时真的有值送达，那由一次性端到端复证负责（见 task-9-report 阶段 A 末节）。
    _src9 = _pl9.Path
    _root9 = _src9(__file__).resolve().parents[1]

    def _read9(rel: str) -> str:
        return (_root9 / rel).read_text(encoding="utf-8")

    _pipe9 = _read9("src/rag/pipeline.py")
    _ret9 = _read9("src/rag/retriever.py")
    _probe9 = _read9("src/evaluation/task_eval/retrieval_probe.py")
    _run9 = _read9("src/evaluation/task_eval/runner.py")
    hops = {
        "①pipeline 写 _rerank_status": 'metadata["_rerank_status"] = ' in _pipe9,
        "②retriever 读 _rerank_status": '"_rerank_status"' in _ret9,
        "②retriever 写 rerank_status": 'metadata["rerank_status"] = ' in _ret9,
        "③probe 读 rerank_status": 'get("rerank_status"' in _probe9,
        "④runner 落 record.rerank_status": "record.rerank_status = " in _run9,
        "④rerank_used 派生自 status": 'self.rerank_status == "success"' in _run9,
    }
    check(
        "9h B2 三跳改名的键名配对全在位（结构锁；断链即红，不许静默降级成未知）",
        all(hops.values()),
        f"缺失={[k for k, v in hops.items() if not v]}",
    )


def check_9reprobe() -> None:
    """收尾修复批 `9j`（Important-1）——reprobe 的 B7 消费侧**行为**锁。

    拆成 `9reprobe`/`9verify`/`9delivery` 三个函数只因 `check_9` 与单函数的圈复杂度
    已达 ruff C901 上限（判据编号仍属 `9` 系列，计数器链不变：`9h` 之后是 `9j`，
    `9i` 按 §20.7.2 B12 的登记**留空不占用**）。
    ★ 全部是**行为**锁（项目所有者的验收原话：「不能再只依赖键名/AST 结构锁」「必须证明
    状态实际抵达工件」）：真调被修函数/消费链，断言**实际产出的值**。
    零 token 硬约束的执行方式：IO 依赖一律**纯内存 monkeypatch**
    （`src/core/llm.py:192` 明说 `USE_FAKE_MODEL` 只让 agent 层变假 ⇒ 任何可能真跑检索
    链的用例都必须把召回/重排/缓存这些跳整个换掉，本批没有一条会打到 dashscope/TEI）。
    """

    # ── 9j（Important-1）：reprobe 的 B7 消费侧 —— 行为锁 ──────────────────────
    #   注入路由故障 ⇒ reprobe 后该 record 的 `retrieval_status` **仍是 `error`**、
    #   不得降回 ok/empty（探针自报 `ok`——`_safe_to_thread` 按路由收敛，异常到不了探针层）；
    #   凭据与状态**成对刷新**（`route_failure_notes` / `rerank_status` 都落到本次读数）；
    #   ★ 下一条**干净** record 必须是 `ok` + 空凭据 ⇒ 这就是 reset 早于每条探针的证据：
    #     删掉 `_reprobe` 循环里的 reset ⇒ A 的故障漏进 B ⇒ 本判据红（reset↔消费成对锁）。
    import argparse as _ap9j
    import asyncio
    import contextlib as _cl9j
    import io as _io9j
    import json as _js9j
    import tempfile as _tf9j

    from evaluation.task_eval import cli as _cli9j
    from evaluation.task_eval import retrieval_probe as _rp9j
    from evaluation.task_eval.cases import load_demo as _ld9j
    from evaluation.task_eval.retrieval_probe import RetrievalProbe as _Probe9j
    from rag.vectorstore import get_vector_store_manager as _gvsm

    _qa_cases9j = [c for c in _ld9j() if c.task == "qa"]
    _case_a, _case_b = _qa_cases9j[0], _qa_cases9j[1]
    _orig_probe9j = _rp9j.probe_retrieval
    _note9j = "__9j_gate_fixture__: RuntimeError"
    _mgr9j = _gvsm()

    async def _fake_probe9j(query: str, **_kw):
        if str(query) == _case_a.query:
            # 模拟「路由故障、被 `_safe_to_thread` 收敛」：探针无感、自报 ok，
            # 故障只落 manager 的 append-only 清单（生产者侧行为，逐字同 8h）。
            _mgr9j.record_query_failure(_note9j)
        return _Probe9j(
            ok=True, status="ok", pack_len=10, evidence_count=1, rerank_status="degraded"
        )

    def _mkrec9j(c, status: str) -> dict:
        return {
            "case_id": c.case_id,
            "task": "qa",
            "task_mode": c.task_mode,
            "query": c.query,
            "retrieval_status": status,
            "reply": "经核对：题干与参考答案一致。",
            "hard_fails": [],
            "route_failure_notes": [],
            "rerank_status": "",
        }

    with _tf9j.TemporaryDirectory() as _td9j:
        _inp9j = Path(_td9j) / "in.jsonl"
        _outp9j = Path(_td9j) / "out.jsonl"
        _inp9j.write_text(
            "".join(
                _js9j.dumps(r, ensure_ascii=False) + "\n"
                for r in (_mkrec9j(_case_a, "error"), _mkrec9j(_case_b, "ok"))
            ),
            encoding="utf-8",
        )
        _args9j = _ap9j.Namespace(records=str(_inp9j), out=str(_outp9j), k=5, no_rerank=True)
        _rp9j.probe_retrieval = _fake_probe9j
        _mgr9j.reset_query_failures()
        try:
            with _cl9j.redirect_stdout(_io9j.StringIO()):  # `_reprobe` 会打印报告，吞进内存
                _rc9j = asyncio.run(_cli9j._reprobe(_args9j))
        finally:
            _rp9j.probe_retrieval = _orig_probe9j
            _mgr9j.reset_query_failures()
        _rows9j = [
            _js9j.loads(line)
            for line in _outp9j.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    _a9j = next((r for r in _rows9j if r.get("case_id") == _case_a.case_id), {})
    _b9j = next((r for r in _rows9j if r.get("case_id") == _case_b.case_id), {})
    check(
        "9j reprobe 消费侧（行为）：故障注入 ⇒ error 不降级 + 凭据/重排状态成对刷新；下一条干净 record 不受染（reset↔消费成对）",
        _rc9j == 0
        and _a9j.get("retrieval_status") == "error"
        and _a9j.get("route_failure_notes") == [_note9j]
        and _a9j.get("rerank_status") == "degraded"
        and "reprobe_of" in _a9j
        and _b9j.get("retrieval_status") == "ok"
        and _b9j.get("route_failure_notes") == []
        and _b9j.get("rerank_status") == "degraded",
        f"rc={_rc9j} A={_a9j.get('retrieval_status')}/{_a9j.get('route_failure_notes')}/{_a9j.get('rerank_status')} "
        f"B={_b9j.get('retrieval_status')}/{_b9j.get('route_failure_notes')}",
    )


def check_9verify() -> None:
    """收尾修复批 `9k`/`9l`（Important-2）——verify 侧「缺键 ≠ 可测」的行为锁 + 结构承重锁。"""

    # ── 9k（Important-2）：verify 判据「缺键 ≠ 可测」—— 行为锁 ─────────────────
    #   四条各一（项目所有者验收原话）：缺键 / 空串 / `ok` / `error`；
    #   「缺键不得返回 pass」被钉死 —— 修复前的实测反例正是 **缺键 ⇒ `ver_fabricated = pass`**
    #   （把「没有这个证据」读成「测到了且通过」，与同包 memory.py 的 F6 裁定互相矛盾）。
    #   ★ `error` 仍属可测（reply 本身是可观测物证，§1.3 tier-1）—— 本批一字未动，这里钉住。
    from evaluation.task_eval.predicates import registry as _reg9k

    _verf9k = _reg9k.get("ver_fabricated").fn
    _reply9k = "经核对：2023 年第 14 题参考答案为 B，与真题一致。"  # 三特征不同现 ⇒ 未编题
    _base9k = {"task": "verify", "case_id": "9k", "reply": _reply9k}
    _v_missing = _verf9k(dict(_base9k))
    _v_empty = _verf9k({**_base9k, "retrieval_status": ""})
    _v_ok = _verf9k({**_base9k, "retrieval_status": "ok"})
    _v_error = _verf9k({**_base9k, "retrieval_status": "error"})
    check(
        "9k verify：缺键/空串 ⇒ missing_premise（★ 缺键不得 pass）；ok/error ⇒ 可测且同判（行为，F6 镜像项）",
        _v_missing == "missing_premise"
        and _v_empty == "missing_premise"
        and _v_ok == "pass"
        and _v_error == "pass",
        f"缺键={_v_missing} 空串={_v_empty} ok={_v_ok} error={_v_error}",
    )

    # ── 9l（Important-2 的**结构**承重锁，与 `8o` 同款）：缺键区分由 `has_path` 承担 ──
    #   ★ 为什么 9k 不够：`_no_reply` 对「缺键」与「空串」的**输出相同**（都 missing_premise）
    #     ⇒ 行为用例分不出 `has_path(...)` 与真值写法 `not rec.get("retrieval_status")`
    #     （后者今天行为等价，但它把「存在性」悄悄换成了「真值」——F6 的教训正是从这里长出来的）。
    #     与 `8o` 同一理由：只能走 AST，定位 `_no_reply` **函数体内**确有 `has_path` 调用且点名该键。
    import ast as _ast9l
    import pathlib as _pl9l

    _ver_src9l = (
        _pl9l.Path(__file__).resolve().parents[1] / "src/evaluation/task_eval/predicates/verify.py"
    ).read_text(encoding="utf-8")
    _fn9l = next(
        (
            n
            for n in _ast9l.walk(_ast9l.parse(_ver_src9l))
            if isinstance(n, _ast9l.FunctionDef) and n.name == "_no_reply"
        ),
        None,
    )
    _hp9l = (
        [
            n
            for n in _ast9l.walk(_fn9l)
            if isinstance(n, _ast9l.Call)
            and (getattr(n.func, "id", "") or getattr(n.func, "attr", "")) == "has_path"
        ]
        if _fn9l is not None
        else []
    )
    _key9l = any(any("retrieval_status" in _ast9l.unparse(a) for a in n.args) for n in _hp9l)
    check(
        "9l _no_reply 体内确以 has_path 区分缺键（AST 承重锁，与 8o 同款；import/体外 decoy 不算）",
        _fn9l is not None and len(_hp9l) >= 1 and _key9l,
        f"_no_reply 存在={_fn9l is not None}；体内 has_path 调用={len(_hp9l)} 处；点名键={_key9l}",
    )


def check_9delivery() -> None:
    """收尾修复批 `9m`–`9p`（Important-3）——B2 四态「送达工件」的行为锁链。

    覆盖：pipeline `finally` 出参（9m-A）、retriever 空包桥接（9m-B）、
    基线 payload 导出（9n）、probe 读侧（9o）、record 落盘（9p）。
    """
    import asyncio

    # ── 9m（Important-3）：B2 空包送达 —— 行为锁（破坏性验证 ① 的落点） ─────────────
    #   A) **真实** `pipeline.aretrieve_documents`（编排层，IO 子阶段纯内存替身）：
    #      空结果 + HyDE 交回 `failed` ⇒ 调用方出参 `rerank_status_out` 被写入 `failed`
    #      （写在 `finally` ⇒ 早段异常路径也必须落，且落 `""`＝未知、**不凭空造**）；
    #   B) **真实** `retriever.aretrieve_evidence` 桥接：off/degraded/failed/success + 未写
    #      五格 —— 空包分支的 `fused.metadata` **恒有** `rerank_status` 键且值=桥接送出值。
    #      旧代码空包分支**根本没有这个键**（评审实测：状态在桥接这一跳被整包丢弃）。
    import rag.pipeline as _pipe9m
    import rag.retriever as _ret9m
    import rag.semantic_cache as _sc9m
    from rag.pipeline import _HydeOutcome as _HO9m
    from rag.pipeline import _RetrievalPlan as _RP9m
    from rag.pipeline import _WindowOutcome as _WO9m
    from rag.retrieval_plan import L2_STANDARD as _L2_9m

    _pnames9m = (
        "_stage_classify_query",
        "_stage_resolve_plan",
        "_stage_decompose_query",
        "_stage_recall_and_merge",
        "_stage_dedup_and_threshold",
        "_stage_hyde",
        "_stage_expand_windows",
    )
    _orig9m_pipe = {n: getattr(_pipe9m, n) for n in _pnames9m}
    _orig9m_ret = (
        _ret9m.aclassify_query,
        _ret9m.decompose,
        _ret9m.aretrieve_documents,
        _sc9m.get_semantic_cache,
    )

    async def _p_classify9m(query, cat=None):
        return [], cat

    def _p_plan9m(query, cat, k, score_threshold, use_rerank, depth):
        return _RP9m(
            depth=depth,
            k=k,
            use_rerank=False,
            effective_threshold=0.0,
            coarse_k=k,
            retrieval_layer="L2",
            route_type="l2_standard",
        )

    async def _p_decompose9m(query, cat, depth, precomputed_sub_queries):
        return [query], False

    async def _p_recall9m(req):
        return []

    async def _p_recall_boom9m(req):
        raise RuntimeError("9m 模拟重排阶段之前的异常")

    async def _p_dedup9m(results, query, cat, threshold):
        return [], 0, 0

    async def _p_hyde9m(filtered, **_kw):
        return _HO9m([], False, 0, "", "failed", 0.0)

    async def _p_window9m(filtered, **_kw):
        return _WO9m([], 0.0, 0)

    sink_a: dict[str, str] = {}
    sink_x: dict[str, str] = {}
    raised9m = False
    results9mb: dict[object, object] = {}
    try:
        _pipe9m._stage_classify_query = _p_classify9m
        _pipe9m._stage_resolve_plan = _p_plan9m
        _pipe9m._stage_decompose_query = _p_decompose9m
        _pipe9m._stage_recall_and_merge = _p_recall9m
        _pipe9m._stage_dedup_and_threshold = _p_dedup9m
        _pipe9m._stage_hyde = _p_hyde9m
        _pipe9m._stage_expand_windows = _p_window9m
        # A1：空包 + HyDE 交回 failed ⇒ 出参送达（真实编排 + 真实 _stage_rerank + 真实 finally 写入）
        docs9m = asyncio.run(
            _pipe9m.aretrieve_documents(
                "9m 查询", k=3, depth=_L2_9m.depth, rerank_status_out=sink_a
            )
        )
        a_ok = docs9m == [] and sink_a == {"rerank_status": "failed"}
        # A2：重排**之前**抛异常 ⇒ `finally` 仍要落，且落 ""（未知，不回填）
        _pipe9m._stage_recall_and_merge = _p_recall_boom9m
        try:
            asyncio.run(
                _pipe9m.aretrieve_documents(
                    "9m 查询", k=3, depth=_L2_9m.depth, rerank_status_out=sink_x
                )
            )
        except RuntimeError:
            raised9m = True
        x_ok = raised9m and sink_x == {"rerank_status": ""}

        # B：真实 `aretrieve_evidence` 桥接（只换掉 IO：分类/分解/召回/缓存）
        async def _p_aclassify9mb(query, terms):
            return None

        async def _p_adecompose9mb(query, cat=None):
            return [query]

        class _NoCache9m:
            async def alookup(self, *a, **k):
                raise RuntimeError("9m 缓存关闭")

            async def astore(self, *a, **k):
                raise RuntimeError("9m 缓存关闭")

        def _mk_aretdocs(status):
            async def _p_aretdocs9mb(**kw):
                _sink = kw["rerank_status_out"]  # retriever 忘传出参 ⇒ KeyError ⇒ 行为锁红
                if status is not None:
                    _sink["rerank_status"] = status
                return []

            return _p_aretdocs9mb

        _ret9m.aclassify_query = _p_aclassify9mb
        _ret9m.decompose = _p_adecompose9mb
        _sc9m.get_semantic_cache = lambda: _NoCache9m()
        for _st9mb in ("off", "degraded", "failed", "success", None):
            _ret9m.aretrieve_documents = _mk_aretdocs(_st9mb)
            _fused9mb = asyncio.run(
                _ret9m.aretrieve_evidence("9m 查询", k=3, use_rerank=False, depth=_L2_9m.depth)
            )
            results9mb[_st9mb] = _fused9mb.metadata.get("rerank_status", "<键缺失>")
    finally:
        for n, f in _orig9m_pipe.items():
            setattr(_pipe9m, n, f)
        (
            _ret9m.aclassify_query,
            _ret9m.decompose,
            _ret9m.aretrieve_documents,
            _sc9m.get_semantic_cache,
        ) = _orig9m_ret

    b_ok = (
        results9mb.get("off") == "off"
        and results9mb.get("degraded") == "degraded"
        and results9mb.get("failed") == "failed"
        and results9mb.get("success") == "success"
        and results9mb.get(None) == ""
    )
    check(
        "9m B2 送达（行为）：aretrieve_documents 出参经 finally 送达（含异常路径落 "
        "）；retriever 空包分支恒写 rerank_status 且=桥接值（五格）",
        a_ok and x_ok and b_ok,
        f"A(空包送达)={sink_a} A2(异常)={sink_x} raised={raised9m} B(桥接五格)={results9mb}",
    )

    # ── 9n（Important-3）：基线 payload 导出（破坏性验证 ② 的落点） ────────────────
    #   `build_baseline_payload` 传**合成**观察（四态各一 + 一格老链路未写），断言
    #   `_meta.rerank_status_counts` 逐格导出、`""` 单列 `unknown`（不折进任何一态）；
    #   没传观察 ⇒ **不写该键**（没证据就不造一份「全未知」冒充送达）。
    #   ★ 口径红线：这只锁「自本批起新录基线会带该字段」；历史 9 份基线**没有**这个键，
    #     引用时不得写成「历史工件已补齐」（见 fixbatch 报告与 §20.7.2 B12 的更正登记）。
    from evaluation.retrieval_gate import RerankObservation as _RO9n
    from evaluation.retrieval_gate import RetrievalMetrics as _RM9n
    from evaluation.retrieval_gate import build_baseline_payload as _bbp9n

    _m9n = _RM9n(
        n_queries=5,
        category_hit_at_1=1.0,
        category_hit_at_k=1.0,
        category_mrr=1.0,
        category_precision=1.0,
        empty_result_rate=0.0,
        mean_evidence_count=3.0,
    )
    _obs9n = [
        _RO9n(True, s == "success", s == "success", s)
        for s in ("off", "success", "degraded", "failed")
    ]
    _obs9n.append(_RO9n(True, False, False, ""))
    _pl9n = _bbp9n(
        metrics=_m9n, golden_path="g.jsonl", indexed_chunks=10, rerank_observations=_obs9n
    )
    _pl9n_none = _bbp9n(metrics=_m9n, golden_path="g.jsonl", indexed_chunks=10)
    check(
        "9n 基线 payload（行为）：_meta.rerank_status_counts 四态+unknown 各列导出；无观察 ⇒ 不造键",
        _pl9n["_meta"].get("rerank_status_counts")
        == {"off": 1, "success": 1, "degraded": 1, "failed": 1, "unknown": 1}
        and "rerank_status_counts" not in _pl9n_none["_meta"],
        f"导出={_pl9n['_meta'].get('rerank_status_counts')} 无观察时含键={('rerank_status_counts' in _pl9n_none['_meta'])}",
    )

    # ── 9o（Important-3）：probe 读侧送达 —— 行为锁（hop ③，评审实证的零 IO 路线） ──
    #   `aretrieve_evidence_with_retry` 换成返回**带 `rerank_status` 的 fused**（零 Chroma
    #   零 TEI），四态 + 空串各跑一次**真实** `probe_retrieval`（policy/finalize/apply 真码），
    #   断言 `probe.rerank_status` 逐格等值 —— 缺省/未知不落任何冒充值。
    import rag.retriever as _ret9o
    from evaluation.task_eval.retrieval_probe import probe_retrieval as _probe9o
    from rag.evidence import FusedEvidence as _FE9o

    _orig9o = _ret9o.aretrieve_evidence_with_retry
    got9o: dict[str, object] = {}
    try:
        for _st9o in ("off", "success", "degraded", "failed", ""):

            def _mk9o(_st: str):
                async def _fake_retry(_query: str = "", **_kw):
                    return _FE9o(
                        final_context="包", sources=[], metadata={"rerank_status": _st}
                    ), None

                return _fake_retry

            _ret9o.aretrieve_evidence_with_retry = _mk9o(_st9o)
            _p9o = asyncio.run(
                _probe9o("数据结构怎么复习", task_mode="learn", k=3, use_rerank=False)
            )
            got9o[_st9o] = _p9o.rerank_status
    finally:
        _ret9o.aretrieve_evidence_with_retry = _orig9o
    check(
        "9o probe 读侧送达（行为）：fused.metadata.rerank_status ⇒ probe.rerank_status 五格等值（含未知不冒充）",
        all(got9o.get(st) == st for st in ("off", "success", "degraded", "failed", "")),
        f"读到={got9o}",
    )

    # ── 9p（Important-3）：record 侧送达 —— 行为锁（probe ⇒ record ⇒ 工件键） ────────
    #   `run_case(run_agent=False)` + 合成探针（`rerank_status="failed"`），断言
    #   record.rerank_status、`to_dict()` 工件键、派生 `rerank_used` 三者同时成立 ——
    #   「failed 不得冒充 success、送达不再断链」在这里闭掉 record 这一跳。
    from evaluation.task_eval import runner as _runner
    from evaluation.task_eval.cases import TaskCase
    from evaluation.task_eval.retrieval_probe import RetrievalProbe as _Probe9p

    _orig9p = _runner.probe_retrieval
    try:

        async def _fake_probe9p(*_a, **_k):
            return _Probe9p(
                ok=True, status="ok", pack_len=5, evidence_count=1, rerank_status="failed"
            )

        _runner.probe_retrieval = _fake_probe9p
        _rec9p = asyncio.run(
            _runner.run_case(
                TaskCase(case_id="9p", task="qa", task_mode="learn", query="q"),
                k=1,
                run_agent=False,
            )
        )
    finally:
        _runner.probe_retrieval = _orig9p
    _d9p = _rec9p.to_dict()
    check(
        "9p record 侧送达（行为）：probe.rerank_status ⇒ record.rerank_status ⇒ to_dict 工件键；failed ⇒ 派生 rerank_used False",
        _rec9p.rerank_status == "failed"
        and _d9p.get("rerank_status") == "failed"
        and _rec9p.rerank_used is False,
        f"record={_rec9p.rerank_status!r} 工件={_d9p.get('rerank_status')!r} 派生 used={_rec9p.rerank_used}",
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
    check_9()
    check_9reprobe()
    check_9verify()
    check_9delivery()
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
