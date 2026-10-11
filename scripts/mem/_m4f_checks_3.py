"""memory_step4fix_gate 判据组：③ 机械 scorer

从原单文件 `memory_step4fix_gate.py` 按判据边界原样搬出，逻辑一字未改。
"""

from __future__ import annotations

import ast

from _m4f_core import ROOT, _gold, check, section

# ── ③ 机械 scorer ────────────────────────────────────────────


def check_3() -> None:
    section("③ Memory 三项机械判定（scorer）")
    _c3_scorer_a()
    _c3_scorer_b()
    _c3_reports()
    _c3_subject_codes()
    _c3_verdict(*_c3_tolerance())
    _c3_parse()
    _c3_service()


def _c3_scorer_a() -> None:

    from evaluation.task_eval.cases import Gold
    from evaluation.task_eval.memory_scorer import judge_memory_mechanically as J

    r = J(
        memory_cards=["【学生记忆】\n薄弱：图"],
        reply="你的弱项是图，建议先复习图的遍历",
        gold=_gold(True, ["图"], ["栈"]),
    )
    check(
        "③a 正样本·卡有+用了+没说错 ⇒ True/True/True",
        (r.recalled_pass, r.used, r.correct) == (True, True, True),
        f"{r.recalled_pass}/{r.used}/{r.correct}",
    )

    r = J(
        memory_cards=["薄弱：图"],
        reply="你的弱项是栈，建议复习栈",
        gold=_gold(True, ["图"], ["栈"]),
    )
    check(
        "③a 正样本·**说反** ⇒ used=False（回复没提正确值）、correct=False（含禁止值）",
        (r.used, r.correct) == (False, False),
        f"forbidden_hits={r.forbidden_hits}",
    )

    r = J(memory_cards=[], reply="你好", gold=_gold(False, ["图"], []))
    check(
        "③b **负样本**·期望不召回且实际未召回 ⇒ recalled_pass=True",
        r.recalled_pass is True and r.recalled_actual is False,
        f"actual={r.recalled_actual} pass={r.recalled_pass}",
    )

    r = J(memory_cards=["薄弱：图"], reply="图", gold=_gold(False, ["图"], []))
    check(
        "③b 负样本·期望不召回但实际召回了 ⇒ recalled_pass=False",
        r.recalled_pass is False,
        f"actual={r.recalled_actual} pass={r.recalled_pass}",
    )

    r = J(memory_cards=["薄弱：图"], reply="图", gold=Gold.from_dict({}))
    check(
        "③c gold 缺失 ⇒ 三项全 None（N/A，不退回 judge）",
        (r.recalled_pass, r.used, r.correct, r.correct_use) == (None, None, None, None),
    )


def _c3_scorer_b() -> None:
    from evaluation.task_eval.memory_scorer import judge_memory_mechanically as J

    # ── ③d~③g 负样本方向（2026-10-07 修 #4 后新增；旧口径这三个方向全错）──
    #   旧实现：`used` 只看回复里有没有那个词 ⇒
    #     ③d 负样本碰巧提到期望值（其实来自 RAG/题面）⇒ used=True ⇒ 判「用了记忆」**假阳性**
    #     ③e 负样本什么都没做 ⇒ used=False ⇒ AND 失败 ⇒ 判「没用好记忆」**假阴性**
    r = J(memory_cards=[], reply="图的重点复习清单如下", gold=_gold(False, ["图"], []))
    check(
        "③d **负样本**·未召回但回复含期望值 ⇒ used=False（那个词不来自记忆）",
        r.used is False and r.recalled_actual is False,
        f"used={r.used} actual={r.recalled_actual} reply_hit={r.reply_hit_values}",
    )
    check(
        "③e **负样本**·什么都没召回也没误用 ⇒ correct_use=**True**（旧口径误判 False）",
        r.correct_use is True,
        f"pass={r.recalled_pass} used={r.used} cu={r.correct_use}",
    )

    r = J(memory_cards=[], reply="你好", gold=_gold(False, ["图"], []))
    check(
        "③f **负样本**·回复也不提 ⇒ correct_use=True（与 ③e 同向，不靠「碰巧」）",
        r.correct_use is True,
        f"cu={r.correct_use}",
    )

    r = J(memory_cards=["薄弱：图"], reply="你的弱项是图", gold=_gold(False, ["图"], []))
    check(
        "③g **负样本**·不该召回却召回了 ⇒ recalled_pass=False 且 correct_use=False",
        r.recalled_pass is False and r.correct_use is False,
        f"pass={r.recalled_pass} actual={r.recalled_actual} cu={r.correct_use}",
    )

    r = J(memory_cards=["薄弱：图"], reply="弱项是图，建议复习栈", gold=_gold(True, ["图"], ["栈"]))
    check(
        "③h 正样本·召回+用了但**用错**（含禁止值）⇒ used=True / correct=False ⇒ cu=False",
        (r.used, r.correct, r.correct_use) == (True, False, False),
        f"used={r.used} correct={r.correct} cu={r.correct_use}",
    )


def _c3_reports() -> None:

    # ③i 失败率分母必须剔除 case_invalid（修 #6：方案 §2.B「validity ≠ product failure」）
    from evaluation.task_eval.report import summarize_task

    recs = [
        {"case_id": "a", "task": "qa", "primary_failure": "none", "generation_ok": True},
        {"case_id": "b", "task": "qa", "primary_failure": "retrieval_miss", "generation_ok": True},
        {
            "case_id": "c",
            "task": "qa",
            "primary_failure": "case_invalid",
            "validity_valid": False,
            "generation_ok": True,
        },
    ]
    rep = summarize_task("qa", recs)
    check(
        "③i 失败率分母剔除 case_invalid ⇒ 1/2 而非旧口径的 1/3",
        rep.failure_rate == 0.5 and rep.invalid_n == 1,
        f"failure_rate={rep.failure_rate} invalid_n={rep.invalid_n} n={rep.n}",
    )

    # ③j 学科码对齐（2026-10-07 修：`cn` 恒被判未命中，grade/verify 各 4 条被系统性压低）
    from evaluation.task_eval.metrics import category_hit

    check(
        "③j `cn` 经别名对齐后能命中 `computer_network`（旧实现恒 False）",
        category_hit("cn", ["computer_network"]) is True,
    )
    check(
        "③j 未登记学科码 ⇒ None（N/A，不进分母），**不是** False（测错）",
        category_hit("kexue_not_exists", ["computer_network"]) is None,
    )


def _c3_subject_codes() -> None:
    # ③j+ ★ 全体扫描（2026-10-07 补）：`cn` 这类漏洞的本质是「数据集里出现的学科码，
    #   映射表不认得」—— 单点断言防不住**下一个**新码。故扫遍 `evals/datasets/` 全部
    #   jsonl，取出实际出现过的学科码，逐个要求：① 能在 `SUBJECT_TO_CATEGORY` 里查到
    #   （查不到 = 该 case 的 `category_hit` 会静默变 N/A，等于悄悄减少样本）；
    #   ② 用映射到的真实类目自测必须 True（自测 False = 恒不命中，正是 `cn` 的老 bug）。
    import json as _json

    from evaluation.gates.retrieval_gate import SUBJECT_TO_CATEGORY
    from evaluation.task_eval.metrics import _SUBJECT_ALIASES, category_hit

    codes: set[str] = set()
    for f in sorted((ROOT / "evals" / "datasets").rglob("*.jsonl")):
        for line in f.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                obj = _json.loads(line)
            except _json.JSONDecodeError:
                continue
            if isinstance(obj, dict) and obj.get("subject"):
                codes.add(str(obj["subject"]))
    unmapped = sorted(
        c for c in codes if SUBJECT_TO_CATEGORY.get(_SUBJECT_ALIASES.get(c, c)) is None
    )
    selfmiss = sorted(
        c
        for c in codes
        if (w := SUBJECT_TO_CATEGORY.get(_SUBJECT_ALIASES.get(c, c))) is not None
        and category_hit(c, [w]) is not True
    )
    check(
        "③j+ 数据集里出现过的每个学科码都「可测且自命中」（防下一个 cn）",
        bool(codes) and not unmapped and not selfmiss,
        f"码={sorted(codes)} 未登记={unmapped} 自测不命中={selfmiss}",
    )


def _c3_tolerance() -> None:
    # ── ③l~③n Grade 的两极 gold（2026-10-07 修 #7）──
    #   实测 0B 的 human_score 分布 = {100: 8, 0: 7} ⇒ `score_tolerance` 报 1.000
    #   只证明"模型跟着说了 0/100"。必须置为不可判，且**不能把被隐藏的原始值弄丢**。
    from evaluation.task_eval.report import build_report, render_markdown, summarize_task

    def _grade_rec(i: int, human: float, model: float) -> dict:
        return {
            "case_id": f"grd-{i:03d}",
            "task": "grade",
            "reply": f"评分：{model:g}/100",
            "gold": {"human_score": human, "full_marks": 100},
            "final_quality": 5,
            "generation_ok": True,
            "primary_failure": "none",
        }

    # ③l 全两极：模型与人工完全一致 → 旧口径会报 tolerance=1.000
    binary = [
        _grade_rec(i, 100.0 if i % 2 == 0 else 0.0, 100.0 if i % 2 == 0 else 0.0)
        for i in range(1, 16)
    ]
    tol = summarize_task("grade", binary).score_tolerance
    md = render_markdown(build_report(binary))
    check(
        "③l 两极 gold ⇒ tolerance 判**不可判**（rate=None）且 raw_rate=1.0 保留",
        tol.get("degenerate_gold") is True
        and tol.get("rate") is None
        and tol.get("raw_rate") == 1.0
        and tol.get("n_distinct_gold") == 2,
        f"degenerate={tol.get('degenerate_gold')} rate={tol.get('rate')} "
        f"raw={tol.get('raw_rate')} distinct={tol.get('n_distinct_gold')}",
    )
    check(
        "③l' 报告必须渲染出 ⚠ 说明（不能只留一个让人误读成「还没跑」的 n/a）",
        any("不可判" in ln and "两极" in ln for ln in md.splitlines()) and "raw_rate=1.0" in md,
    )

    # ③m 分散 gold（含部分分）→ 指标正常可判
    spread_gold = [100.0, 0.0, 40.0, 65.0, 80.0, 20.0, 90.0, 55.0, 30.0, 70.0]
    spread = [
        _grade_rec(i, h, min(100.0, max(0.0, h + (5 if i % 2 else -5))))
        for i, h in enumerate(spread_gold, start=1)
    ]
    tol2 = summarize_task("grade", spread).score_tolerance
    check(
        "③m 分散 gold ⇒ 不判退化、tolerance 正常出值（护栏不是一刀切禁用）",
        tol2.get("degenerate_gold") is False and tol2.get("rate") is not None,
        f"degenerate={tol2.get('degenerate_gold')} rate={tol2.get('rate')}",
    )

    # ③n 样本 <5：那是「样本不足」，不该由退化检测冒充判定
    tol3 = summarize_task("grade", binary[:3]).score_tolerance
    check(
        "③n 样本 <5 ⇒ 不冒充退化判定（degenerate=False）",
        tol3.get("degenerate_gold") is False,
        f"n_gold={len(binary[:3])} degenerate={tol3.get('degenerate_gold')}",
    )
    return binary, tol


def _c3_verdict(binary, tol) -> None:
    # ── ③o~③r `verdict_agreement`（#7 的合法替代指标，2026-10-07）──
    from evaluation.task_eval import metrics
    from evaluation.task_eval.metrics import WRONG_SCORE_LINE, verdict_agreement
    from evaluation.task_eval.report import build_report, render_markdown, summarize_task

    # ③o 换指标的理由必须被锁住：**数值差很多、但结论一致** ⇒ verdict 过 / tolerance 败
    check(
        "③o 模型 70 vs 人工 100 ⇒ verdict=True（结论同为「对」），而 tolerance 会判失败",
        verdict_agreement(70.0, 100.0) is True and metrics.score_tolerance(70.0, 100.0) is False,
        f"阈值线={WRONG_SCORE_LINE:g}（取自 schema：score<60 视为错误）",
    )
    # ③p 结论不一致：两个方向都要判 False（不能只抓"判错为对"）
    check(
        "③p 结论不一致 ⇒ False（模型 55/人工 100；模型 65/人工 0）",
        verdict_agreement(55.0, 100.0) is False and verdict_agreement(65.0, 0.0) is False,
    )
    check(
        "③p' 分数不可解析 ⇒ None（N/A，不进分母），不是 False",
        verdict_agreement(None, 100.0) is None and verdict_agreement(80.0, None) is None,
    )

    # ③r ★ 核心：两极 gold 让 tolerance 不可判，**但 verdict 必须仍然可判** ——
    #     否则这次"修复"等于把 Grade 轴整个删掉。
    verdict_block = summarize_task("grade", binary).verdict_agreement
    check(
        "③r 两极 gold 下 tolerance 不可判，而 verdict **仍可判**（n=15、rate=1.0）",
        tol.get("rate") is None
        and verdict_block.get("rate") == 1.0
        and verdict_block.get("n") == 15
        and verdict_block.get("n_a") == 0,
        f"tolerance.rate={tol.get('rate')} verdict.rate={verdict_block.get('rate')} "
        f"n={verdict_block.get('n')} n/a={verdict_block.get('n_a')}",
    )
    # ③r' 有批改失败时：不可解析的样本数必须**出现在报告里**（不许从分母静默消失）
    with_fail = binary[:13] + [
        {**binary[13], "reply": "批改失败（工具未返回评分结果）"},
        {**binary[14], "reply": "批改失败（工具未返回评分结果）"},
    ]
    vb2 = summarize_task("grade", with_fail).verdict_agreement
    md2 = render_markdown(build_report(with_fail))
    check(
        "③r' 2 条不可解析 ⇒ verdict 剔出分母(n=13)且报告打印 ⚠ 披露",
        vb2.get("n") == 13 and vb2.get("n_a") == 2 and "未产出可解析分数" in md2,
        f"n={vb2.get('n')} n/a={vb2.get('n_a')}",
    )


def _c3_parse() -> None:
    from evaluation.task_eval import metrics

    # ── ③s~③u A1/A2 的回归锁（2026-10-07）──
    # ③s 「满分/总分 X」是**说明性数字**，不能被当得分（旧正则取首个数字，必错这两条）
    s_cases = [
        ("总分 100 分，你得了 62 分", 62.0),
        ("得分（满分 100）：62", 62.0),
        ("评分：40/100", 40.0),
        ("你得 80 分", 80.0),
        ("得分：5/10", 50.0),
    ]
    bad_s = [
        (t, exp, metrics.parse_grade_score(t))
        for t, exp in s_cases
        if metrics.parse_grade_score(t) != exp
    ]
    check(
        "③s parse_grade_score 不把「满分/总分」的数字当得分",
        not bad_s,
        f"错 {len(bad_s)} 条: {bad_s[:2]}" if bad_s else f"{len(s_cases)} 条全对",
    )
    # ③t 解析不到必须给 None —— 那是 N/A，不是 0 分（0 会把"批改失败"算成"判零分"）
    t_bad = [
        t
        for t in ("批改失败（工具未返回评分结果）", "", "本题 2013 年真题", "结论：回答正确")
        if metrics.parse_grade_score(t) is not None
    ]
    check(
        "③t 无分数形态 ⇒ None（N/A），不得猜成 0 分",
        not t_bad,
        f"误判: {t_bad}" if t_bad else "4 条均为 None",
    )


def _c3_service() -> None:

    # ③u API 批改端点必须把 knowledge_points 透传给 record_grade
    #   ★ 这是**静态**检查（执行它要完整 app + DB）；"执行式"的端到端验证在
    #     `scripts/mem/memory_e2e_fallback_probe.py`（注入假 LLM 驱动真实 `call_structured`）。
    #   用 AST 定位调用节点的 keywords，**不是搜源码子串** —— 注释里提一句该参数
    #   就能骗过子串搜索（⑨f 的教训）。
    from pathlib import Path as _P

    _tree = ast.parse((_P(ROOT) / "src" / "service" / "service.py").read_text(encoding="utf-8"))
    grade_calls = [
        n
        for n in ast.walk(_tree)
        if isinstance(n, ast.Call)
        and getattr(n.func, "id", "") == "record_grade"
        and any(
            k.arg == "agent_path" and getattr(k.value, "value", None) == "api_grade"
            for k in n.keywords
        )
    ]
    check(
        "③u /api/questions/grade 的 record_grade 传了 knowledge_points",
        len(grade_calls) == 1 and any(k.arg == "knowledge_points" for k in grade_calls[0].keywords),
        f"api_grade 调用 {len(grade_calls)} 处；"
        f"keywords={sorted(str(k.arg) for k in grade_calls[0].keywords) if grade_calls else []}",
    )
