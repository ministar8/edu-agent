"""memory_step4fix_gate 判据组：㉔㉕㉖㉗

从原单文件 `memory_step4fix_gate.py` 按判据边界原样搬出，逻辑一字未改。
"""

from __future__ import annotations

from dataclasses import dataclass

from _m4f_core import ROOT, check, section, skip

# ㉖ 的夹具常量（模块级：被 _c26_consts / _c26_runs / _c26_checks 共用）
FAB = (
    "以下为网络体系结构相关练习题：\n\n**题目1**\n类型：选择\n"
    "题干：关于网络协议的三要素，下列说法正确的是（　）。\nA. 语法\nB. 语义\n"
    "C. 时序\nD. 都不对\n标准答案：C\n解析：协议三要素为语法、语义、时序。"
)
CITE_PROSE = (
    "## 真题清单\n\n- **2010 年 第 33 题**：下列选项中，不属于网络体系结构描述内容的是（　）。"
)
CITE_TABLE = "## 历年真题\n\n| 年份 | 题号 | 考查内容 |\n|---|---|---|\n| 2021 | Q14 | 不能用 IEEE 754 精确表示的是 |\n"
YEAR_ONLY = "- 涉及的年份来源文件：2010、2011、2012 年 408 真题（仅作为来源文件出现，未检索到各题具体题干）。"
DENIAL = "检索到的内容只有知识点讲解，未包含任何真题的年份、题号或题目原文，因此无法确认具体考过哪些真题。"
SPLIT_LINES = "某处提到 2011 年。\n另一处才写着 第 33 题。"  # ★ 跨行**不得**拼成 L1


def check_24() -> None:
    """㉔ 正样本 `values` 的**粒度**必须有机械约束（2026-10-08 review M10，接 #26）。

    D8 把 `mem-002`/`mem-003` 的 `expected_memory.values` 从章名（`图` / `排序`）收到具体考点
    （`图的存储` / `快速排序`），因为 `recalled` 是**子串包含**判定 —— 章名会被它下面
    任何一个子考点满足 ⇒ 「召回成功」测不出「召回的是不是设计的那个薄弱点」。
    ★ 但当时**只有人工承诺**：`章名` 本身就是 canonical（`node_kind=domain`），
      旧的 lint 只查「是否 canonical」⇒ 改回 `图` 依旧 ERROR 0。这条补上机械约束。
    """
    section("㉔ 正样本 values 必须是具体考点（粒度 lint，#26 的可执行化）")
    _c24_drift(_c24_granularity())


def check_25() -> None:
    """㉕ #27 的处置（D12 选 (B)）：评测侧从 metadata 兜底解析 KP，**产品契约不动**。

    缺陷：`rag/retrieval/layer_recall.py` 的 top-up 路径把 `knowledge_points` 写死成 `[]`，
    而同一份 `metadata` 里就带着 JSON 字符串 ⇒ 走这条路进 top-k 的证据在
    `kp_hit` / `kp_mrr` / Generate 的 `coverage` 眼里等于没标考点（系统性假阴性）。
    ⇒ (B) = 只在**评测读数**这一侧兜底；产品给 agent 的那份契约仍缺 KP，
      这条偏差必须单独披露（不顺手改产品，是因为 `EvidenceDoc.knowledge_points` 是
      对外契约字段，动它 = 动检索链 = 触发新锚点 + qa/generate 重跑）。
    """
    section("㉕ top-up 项的 KP 兜底解析（#27 / D12 选 B；产品契约保持不动）")
    _c25_doc(*_c25_meta())


def check_26() -> None:
    """㉖ Verify 行为层判据（D14）—— §3.1 冻结的头号指标不可计算时，这一行由谁把门。

    背景：`question_id_recall@k` 算不出来（#20/D7），而 `final_quality≥4` 在 verify 上
    测的是**检索覆盖**（未达成 case 全是 `exam_hit=False`，agent 诚实说"无法确认"是**正确行为**）
    ⇒ 拿它当 Gate 就是指标效度错。D14 选① = 把 `PHASE1_VERIFY.md` 里那两个人工读数**机械化**。
    """
    section("㉖ Verify 行为层判据（D14；仍出题必须为 0）")
    _c26_consts()
    _c26_archive()
    _d = _c26_harness()
    _c26_checks(_d, *_c26_runs(_d))


def check_27() -> None:
    """㉗ Memory 的 §6 判定改为**结构断言**（D15）—— 不再试图在 n=1 上写百分数门槛。

    为什么不能写百分数：0B 的 Memory 四率**全 N/A**（#9，那批 gold 里没有 `expected_memory`）
    ⇒ 「≥80% correct-use」根本没法按 Phase 0 回填；新口径下可测正样本只有 n=1（§20.8.6）。
    ⇒ 三条断言：① 配对成立（`paired_control_verdict`，含 **#24 探测器**）
      ② 被计入的正样本结论可追溯（`memory_traceable`）③ 分母摊开（`memory_measure_scope`）。
    """
    section("㉗ Memory 结构断言（D15：配对成立 / 可追溯 / 分母摊开）")
    _c27_pairs(_c27_setup())
    _c27_scope(_c27_setup())
    _c27_archive()


def _c24_granularity() -> None:

    import copy

    from evaluation.task_eval.cases import load_demo
    from evaluation.task_eval.gold_sanity import run_sanity

    cases = load_demo("memory")
    pos = [c for c in cases if getattr(c.gold.expected_memory, "should_be_recalled", None) is True]
    neg = [c for c in cases if getattr(c.gold.expected_memory, "should_be_recalled", None) is False]
    assert pos and neg, f"数据集形状变了：正样本 {len(pos)} 条 / 负样本 {len(neg)} 条"

    # ㉔a 反向：往正样本里种一个章名 ⇒ 必须报 ERROR（这才是「lint 有牙」的证据）
    bad = copy.deepcopy(pos[0])
    bad.gold.expected_memory.values = ["图"]  # domain 级：子串判定下任何子考点都算召回
    rep_bad = run_sanity([bad])
    check(
        "㉔a 反向：正样本 values 换成章名「图」⇒ gold_sanity 必须报 ERROR",
        any(
            i.field_name.endswith("expected_memory.values") and i.level == "ERROR"
            for i in rep_bad.errors
        ),
        str([(i.field_name, i.message[:40]) for i in rep_bad.errors]),
    )

    # ㉔b 现数据集必须真的过这条（否则 #26 的收紧本身就是假的）
    rep_real = run_sanity(cases)
    check(
        "㉔b 仓内 6 条 memory gold 过粒度 lint（D8 收到的具体考点是真的）",
        not [i for i in rep_real.errors if "正样本" in i.message],
        str([(i.case_id, i.message[:44]) for i in rep_real.errors]),
    )

    # ㉔c 负样本**允许**保留章名（偏松匹配让它更难通过，方向保守，#26 刻意不动）
    neg_case = copy.deepcopy(neg[0])
    neg_case.gold.expected_memory.values = ["图"]
    rep_neg = run_sanity([neg_case])
    check(
        "㉔c 负样本用章名不报（lint 不是一刀切禁用 domain）",
        not [i for i in rep_neg.errors if "正样本" in i.message],
        f"case={neg_case.case_id} errors={[(i.field_name, i.message[:36]) for i in rep_neg.errors]}",
    )
    return cases


def _c24_drift(cases) -> None:

    # ㉔d #26 的收紧**不许动已发表数字**。
    #   ★ 比的是「**归档内嵌 gold**」与「**当前数据集 gold**」两套 gold 在同一份代码下的结果
    #     —— 而不是「归档值 vs 当前重算」：后者会把 **#4 的口径修正**（负样本的 `used` 要
    #     召回事实前提）也算成"漂移"（实测 Step 5 ON 的 `mem-006`：归档 `(T,T,T)`、
    #     当前代码重算 `(T,F,F)`，那是 #4 已发表的 2→1，不是 #26）。
    #     一条判据只能绑一个变量 —— 绑两个的结论没法解释（本轮就差点把 #4 当成 #26 的回归）。
    #   ★ 原 ⑬l 只重算 validity，名字大于覆盖（review M11）：真正支撑
    #     「新 gold 不动已发表数字」的是三维，不是 validity。
    import json as _json24

    from evaluation.task_eval.cases import Gold as _Gold
    from evaluation.task_eval.memory_scorer import judge_memory_mechanically

    by_id = {c.case_id: c for c in cases}
    drift: list[str] = []
    n_cmp = 0
    for fname in ("phase1_memory_step5_store_on.jsonl", "phase1_memory_step5_store_off.jsonl"):
        fp = ROOT / "evals" / "results" / "task_eval" / fname
        if not fp.exists():
            skip(
                f"㉔d {fname}",
                "归档不在本机（D11 不入库）⇒ 两套 gold 的三维差异未验证",
                count=1,
            )
            continue
        for ln in fp.read_text(encoding="utf-8").splitlines():
            ln = ln.strip()
            if not ln or ln.startswith("#"):
                continue
            r = _json24.loads(ln)
            c = by_id.get(r.get("case_id"))
            if c is None:
                drift.append(f"{r.get('case_id')}(当前数据集里已无此 case)")
                continue
            cards = list(r.get("memory_cards") or [])
            reply = str(r.get("reply") or "")
            gold_now = judge_memory_mechanically(memory_cards=cards, reply=reply, gold=c.gold)
            gold_then = judge_memory_mechanically(
                memory_cards=cards, reply=reply, gold=_Gold.from_dict(r.get("gold") or {})
            )
            n_cmp += 1
            for fld, a, b in (
                ("recalled", gold_then.recalled_pass, gold_now.recalled_pass),
                ("used", gold_then.used, gold_now.used),
                ("correct", gold_then.correct, gold_now.correct),
                ("correct_use", gold_then.correct_use, gold_now.correct_use),
            ):
                if bool(a) != bool(b):
                    drift.append(f"{r['case_id']}.{fld}: {a}→{b}")
    check(
        f"㉔d 同一份代码下「归档 gold」与「当前 gold」的三维逐条一致（#26 收紧不动已发表数字；"
        f"可比对 {n_cmp} 条）",
        n_cmp >= 1 and not drift,
        f"可比对 {n_cmp} 条；差异={drift[:4]}",
    )


def _c25_meta() -> None:

    import json as _json25

    from evaluation.task_eval.retrieval_probe import _to_item
    from rag.retrieval.evidence import TextEvidence, parse_knowledge_points

    raw = _json25.dumps(["图的存储", "数组与特殊矩阵"], ensure_ascii=False)
    meta = {
        "chunk_id": "c-25",
        "kb_depth": "advanced",
        "doc_role": "method",
        "category": "data_structure",
        "knowledge_points": raw,
    }

    def _ev(kps: list[str]) -> TextEvidence:
        return TextEvidence(
            evidence_id="topup_data_structure_c-25",
            content="正文",
            source="knowledge/advanced/data_structure/01_graph.md",
            score=0.31,
            collection="data_structure",
            chunk_id="c-25",
            knowledge_points=kps,
            metadata=dict(meta),
        )

    item = _to_item(_ev([]))  # ★ topup 形状：对象上 KP 为空、metadata 里有值
    check(
        "㉕a ★ topup 形状的经**真实 `_to_item`** 兜底解析出 KP（旧写法这里会是 []）",
        item.knowledge_points == ["图的存储", "数组与特殊矩阵"],
        str(item.knowledge_points),
    )
    check(
        "㉕b 反向：metadata 里也没有 ⇒ 记空，**绝不虚构**标签",
        _to_item(
            TextEvidence(
                evidence_id="x",
                content="正文",
                source="s",
                score=0.1,
                collection="data_structure",
                chunk_id="c",
                knowledge_points=[],
                metadata={"doc_role": "exam_answer"},
            )
        ).knowledge_points
        == [],
    )
    check(
        "㉕c 复用同一份解析器（`_to_item` 的结果 == `parse_knowledge_points(meta)`，"
        "防两套解析分叉 —— 与 #10/#21 是同一个教训）",
        item.knowledge_points == parse_knowledge_points(meta["knowledge_points"]),
        f"{item.knowledge_points} vs {parse_knowledge_points(meta['knowledge_points'])}",
    )
    return meta, raw, item


def _c25_doc(meta, raw, item) -> None:
    from rag.retrieval.layer_recall import _doc_to_evidence

    # ㉕d **边界**：产品侧那条路今天仍然丢 KP —— 这条不是放行缺陷，而是把
    #   「(B) 只改评测口径」这个决定钉成可检查的事实；将来若有人改成 (A)，这条会红，
    #   那时必须同时更新 §20.5 #27 的披露与锚点。
    class _Doc:
        def __init__(self, m: dict, c: str) -> None:
            self.metadata = m
            self.page_content = c

    prod = _doc_to_evidence(_Doc(dict(meta), "正文"), 0.42, "data_structure")
    check(
        "㉕d 产品契约仍不带宽 KP（(B) 的边界；改回 (A) 时这条必然红 ⇒ 提醒同步披露）",
        prod.knowledge_points == [] and prod.metadata.get("knowledge_points") == raw,
        f"契约={prod.knowledge_points} metadata={str(prod.metadata.get('knowledge_points'))[:40]}",
    )

    # ㉕e 下游聚合函数因此不再漏（`_all_kp` 是 kp_hit 的输入）
    from evaluation.task_eval.runner import _all_kp

    check(
        "㉕e `_all_kp` 能看到兜底后的 KP（Generate `coverage` 的 N/A 来源之一被消除）",
        _all_kp([item]) == ["图的存储", "数组与特殊矩阵"],
        str(_all_kp([item])),
    )


def _c26_consts() -> None:

    from evaluation.task_eval import metrics as _m26

    check(
        "㉖a 仍出题（题干+标准答案+出题标题同现）⇒ True",
        _m26.verify_fabricated(FAB) is True,
    )
    check(
        "㉖b 反向：列真题清单（散文 / 表格）都不算「仍出题」——否则修好反而更像在失败",
        _m26.verify_fabricated(CITE_PROSE) is False
        and _m26.verify_fabricated(CITE_TABLE) is False
        and _m26.verify_fabricated(YEAR_ONLY) is False,
    )
    check(
        "㉖c L1 认两种真实形态（散文「2010 年 第 33 题」+ 表格「| 2021 | Q14 |」）",
        _m26.verify_exam_item_cited(CITE_PROSE) is True
        and _m26.verify_exam_item_cited(CITE_TABLE) is True,
    )
    check(
        "㉖d 三个反向：自我否定句、跨行拼凑都不算 L1；L1 成立则 L2 必 False（两级互斥）",
        _m26.verify_exam_item_cited(DENIAL) is False
        and _m26.verify_exam_item_cited(SPLIT_LINES) is False
        and _m26.verify_exam_year_only(DENIAL) is False  # 整篇没给年份行命中 ⇒ 既非 L1 也非 L2
        and _m26.verify_exam_year_only(YEAR_ONLY) is True
        and (_m26.verify_exam_item_cited(CITE_PROSE) and _m26.verify_exam_year_only(CITE_PROSE))
        is False,
    )


def _c26_archive() -> None:
    import json as _json26

    from evaluation.task_eval import metrics as _m26

    # ★ ㉖e 归档复现：机械判据必须复现 `PHASE1_VERIFY.md` 的人工读数（含 case_id 级）
    def _archive_rates(fname: str):
        fp = ROOT / "evals" / "results" / "task_eval" / fname
        if not fp.exists():
            return None
        v = [
            _json26.loads(ln)
            for ln in fp.read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.strip().startswith("#")
        ]
        v = [r for r in v if r.get("task") == "verify"]
        fab = [r["case_id"] for r in v if _m26.verify_fabricated(str(r.get("reply") or ""))]
        l1 = [r["case_id"] for r in v if _m26.verify_exam_item_cited(str(r.get("reply") or ""))]
        l2 = [r["case_id"] for r in v if _m26.verify_exam_year_only(str(r.get("reply") or ""))]
        return fab, l1, l2, len(v)

    a0, a1 = (
        _archive_rates("phase0_baseline_final.jsonl"),
        _archive_rates("phase1_baseline_v2.jsonl"),
    )
    if a0 is None or a1 is None:
        skip("㉖e", "0B / Phase 1 归档不在本机（D11 不入库）⇒ 未与人工读数对账", count=1)
    else:
        (fab0, l10, l20, n0), (fab1, l11, l21, _n1) = a0, a1
        check(
            "㉖e 归档复现人工读数：仍出题 6/15→0/15；有真题信息 0B L1=3、Phase1 L1+L2=9",
            len(fab0) == 6
            and len(fab1) == 0
            and len(l10) == 3
            and len(l11) + len(l21) == 9
            and n0 == 15,
            f"仍出题 {len(fab0)}/{n0}→{len(fab1)}/15（id={fab0}）| L1 {len(l10)}→{len(l11)} | L2 {len(l20)}→{len(l21)}",
        )


def _c26_harness() -> None:
    import asyncio as _aio26
    from dataclasses import field

    import evaluation.task_eval.runner as R26
    from evaluation.task_eval.cases import load_demo

    # ★ ㉖f/㉖g 接线：真实 `run_case` 必须写字段，且**没跑 agent 时一律 N/A**
    @dataclass
    class _Res26:
        reply: str = "回复"
        hard_fails: list[str] = field(default_factory=list)
        tool_payloads: list[dict] = field(default_factory=list)
        memory_cards: list[str] = field(default_factory=list)
        grade_scores: list[dict] = field(default_factory=list)
        turn_log: list[dict] = field(default_factory=list)
        episodes: list[dict] = field(default_factory=list)
        episodes_read_failed: bool = False

    class _Probe26:
        ok = True
        status = "ok"
        pack_len = 120
        evidence_count = 2
        error = ""

        def top_k(self, k: int):  # noqa: ARG002
            return []

    async def _fake_probe26(*_a, **_kw):
        return _Probe26()

    def _drive26(reply: str, *, run_agent: bool = True, task: str = "verify"):
        async def _fake_agent26(_turns, **_kw):
            return _Res26(reply=reply)

        old_agent, old_probe = R26._run_agent, R26.probe_retrieval
        R26._run_agent, R26.probe_retrieval = _fake_agent26, _fake_probe26
        try:
            case = load_demo(task, limit=1)[0]
            return _aio26.run(R26.run_case(case, run_agent=run_agent))
        finally:
            R26._run_agent, R26.probe_retrieval = old_agent, old_probe

    return _drive26


def _c26_runs(_drive26) -> None:
    from evaluation.task_eval.report import summarize_task

    rec_fab = _drive26(FAB)
    rec_cite = _drive26(CITE_TABLE)
    check(
        "㉖f 接线：verify case 的三判据真的落进 record（仍出题 case ⇒ fabricated=True）",
        rec_fab.ver_fabricated is True
        and rec_fab.ver_exam_item_cited is False
        and rec_cite.ver_fabricated is False
        and rec_cite.ver_exam_item_cited is True,
        f"出题={rec_fab.ver_fabricated}/{rec_fab.ver_exam_item_cited} "
        f"引用={rec_cite.ver_fabricated}/{rec_cite.ver_exam_item_cited}",
    )
    rec_probe = _drive26("", run_agent=False)
    check(
        "㉖g ★ 没跑 agent（或空回复）⇒ 三条全是 None（N/A）——探针跑不得被读成「没出题」",
        rec_probe.ver_fabricated is None
        and rec_probe.ver_exam_item_cited is None
        and rec_probe.ver_exam_year_only is None,
        f"{rec_probe.ver_fabricated}/{rec_probe.ver_exam_item_cited}/{rec_probe.ver_exam_year_only}",
    )
    rep26 = summarize_task(
        "verify",
        [rec_fab.to_dict(), rec_cite.to_dict(), rec_probe.to_dict()],
    )
    return rec_fab, rec_cite, rec_probe, rep26


def _c26_checks(_drive26, rec_fab, rec_cite, rec_probe, rep26) -> None:
    from evaluation.task_eval.report import summarize_task

    check(
        "㉖h 报告层：N/A 不进分母（3 条 record ⇒ 可测 2 条、仍出题 1 条）",
        rep26.ver_fabrication["n"] == 2
        and rep26.ver_fabrication["passed"] == 1
        and rep26.ver_fabrication["n_a"] == 1,
        str(rep26.ver_fabrication),
    )
    # ★ 反向：同一段「带题目模板」的回复放在 **qa** 任务上不该产生这三条判据
    #   （QA 出题是正常行为 ⇒ 判据只属 verify）
    rec_qa = _drive26(FAB, task="qa")
    check(
        "㉖i 判据只在 verify 分支写：同样的回复放在 qa ⇒ 三条保持 None",
        rec_qa.ver_fabricated is None
        and rec_qa.ver_exam_item_cited is None
        and rec_qa.ver_exam_year_only is None,
        f"qa record: {rec_qa.ver_fabricated}/{rec_qa.ver_exam_item_cited}/{rec_qa.ver_exam_year_only}",
    )

    # ★ ㉖j 老归档兼容：没有 `ver_*` 键的 record 必须读成**未测量**，
    #   绝不能把「字段缺失」读成「仍出题 0%」——那正是 #21 那类「读不到就当真」的错。
    legacy = {k: v for k, v in rec_fab.to_dict().items() if not k.startswith("ver_")}
    rep_legacy = summarize_task("verify", [legacy, legacy])
    fb = rep_legacy.ver_fabrication
    check(
        "㉖j 老归档（无 ver_* 键）读成未测量：rate=None、n=0、n_a=2 ⇒ 不会被印成「仍出题 0%」",
        fb["rate"] is None and fb["n"] == 0 and fb["n_a"] == 2,
        str(fb),
    )


def _c27_setup() -> None:

    def rec(cid, *, recalled, cards, valid=True, positive=True, trace=True):
        r = {
            "case_id": cid,
            "task": "memory",
            "validity_valid": valid,
            "memory_recalled_actual": recalled,
            "memory_cards": list(cards),
            "store_enabled": True,
            "gold": {"expected_memory": {"should_be_recalled": positive, "values": ["图的存储"]}},
        }
        if trace:
            r["turn_log"] = [{"session": 0, "turn": 0}]
            r["episodes"] = []
        return r

    return rec


def _c27_pairs(rec) -> None:
    from evaluation.task_eval import metrics as _m27

    v_ok = _m27.paired_control_verdict(
        [rec("m1", recalled=True, cards=["薄弱：图的存储"])],
        [rec("m1", recalled=False, cards=[])],
    )
    check(
        "㉗a 断言①：两臂都 valid 的正样本上 ON 召回、OFF 未召回 ⇒ 通过",
        v_ok["passed"] is True and v_ok["n_pairs"] == 1 and v_ok["n_ok"] == 1,
        str(v_ok),
    )
    v_card = _m27.paired_control_verdict(
        [rec("m1", recalled=True, cards=["薄弱：图的存储"])],
        [rec("m1", recalled=True, cards=["薄弱：图的存储"])],  # OFF 侧照样有卡 = #24
    )
    check(
        "㉗b ★ #24 探测器：OFF 侧出现记忆卡 ⇒ 一律判失败（旧代码正是这个形状）",
        v_card["passed"] is False and v_card["off_has_card"] == ["m1"],
        str(v_card),
    )
    v_no_pair = _m27.paired_control_verdict(
        [rec("m1", recalled=True, cards=["卡"])],
        [rec("m1", recalled=False, cards=[], valid=False)],  # 该臂前置条件没凑成
    )
    check(
        "㉗c 交集为 0 ⇒ **不许**声称通过（防「压根没配对」被印成「OFF 干净」）",
        v_no_pair["n_pairs"] == 0 and v_no_pair["passed"] is False,
        str(v_no_pair),
    )
    v_miss = _m27.paired_control_verdict(
        [rec("m1", recalled=False, cards=[])],
        [rec("m1", recalled=False, cards=[])],
    )
    check(
        "㉗d ON 侧没召回 ⇒ 进 failed（不是「两边都空所以干净」）",
        v_miss["passed"] is False and v_miss["failed"] == ["m1"],
        str(v_miss),
    )
    check(
        "㉗e 断言②：可追溯 = 逐轮日志 + 卡通道 + `episodes` 字段 + `store_enabled`；缺任一即 False"
        "（OFF 臂 `episodes=[]` 仍算可追溯 —— 空是合法结果，缺字段才是没测）",
        _m27.memory_traceable(rec("m", recalled=True, cards=["x"])) is True
        and _m27.memory_traceable(rec("m", recalled=True, cards=["x"], trace=False)) is False,
    )


def _c27_scope(rec) -> None:
    from evaluation.task_eval.report import summarize_task

    recs = [
        rec("p1", recalled=True, cards=["卡"]),
        rec("p2", recalled=False, cards=[], valid=False),
        rec("p3", recalled=False, cards=[], valid=False),
    ]
    sc = summarize_task("memory", recs).memory_measure_scope
    check(
        "㉗f 断言③：报告把分母摊开（正样本 3、valid 1、不可测 2、可追溯 1）⇒ 100% 旁边必须能看到 1/3",
        sc
        == {
            "positives_total": 3,
            "positives_valid": 1,
            "positives_invalid": 2,
            "positives_traceable": 1,
        },
        str(sc),
    )


def _c27_archive() -> None:
    import json as _json27

    from evaluation.task_eval import metrics as _m27

    # ★ ㉗g 真实归档回归：这三份合起来就是「断言能不能分辨历史上那三种情形」
    def _read(fname: str):
        fp = ROOT / "evals" / "results" / "task_eval" / fname
        if not fp.exists():
            return None
        return [
            _json27.loads(ln)
            for ln in fp.read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.strip().startswith("#")
        ]

    def _load_pair(tag: str):
        on, off = (
            _read(f"phase1_memory_step5_store_on_step9_{tag}.jsonl"),
            _read(f"phase1_memory_step5_store_off_step9_{tag}.jsonl"),
        )
        if on is None or off is None:
            return None
        return _m27.paired_control_verdict(on, off)

    d8b, d8, kp = _load_pair("d8b"), _load_pair("d8"), _load_pair("kp")
    if not (d8b and d8 and kp):
        skip("㉗g", "Step 9 的 d8/d8b/kp 归档不在本机（不入库）⇒ 未做历史三情形回归", count=1)
    else:
        check(
            "㉗g 历史三情形可分辨：d8b（修好后）通过 / d8（OFF 有卡）被探测器抓住 / kp（无交集）不算通过",
            d8b["passed"] is True
            and d8b["n_pairs"] == 1
            and d8["passed"] is False
            and d8["off_has_card"] == ["mem-002"]
            and kp["n_pairs"] == 0
            and kp["passed"] is False,
            f"d8b={d8b['n_pairs']}/{d8b['n_ok']} pass={d8b['passed']} | "
            f"d8 off_has_card={d8['off_has_card']} | kp pairs={kp['n_pairs']}",
        )
