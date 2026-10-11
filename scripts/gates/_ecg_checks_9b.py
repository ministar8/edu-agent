"""Evidence Chain 护栏的判据组四：`check_9delivery`（9m–9p）+ `check_9goldstatus`（9q/9r）。

从原单文件 `evidence_chain_gate.py` 按判据边界原样搬出，逻辑一字未改。
"""

from __future__ import annotations

from _ecg_core import _base_record, _gen_reply, check


def check_9delivery() -> None:
    """收尾修复批 `9m`–`9p`（Important-3）——B2 四态「送达工件」的行为锁链。

    覆盖：pipeline `finally` 出参（9m-A）、retriever 空包桥接（9m-B）、
    基线 payload 导出（9n）、probe 读侧（9o）、record 落盘（9p）。
    """
    sink_a, sink_x, raised9m, a_ok, x_ok = _c9m_docs()
    results9mb = _c9m_bridge()

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
    _c9n()
    _c9o()
    _c9p()


def check_9goldstatus() -> None:
    """P−1 批 1：`gold_answer_status`（键集双向相等 + 值域 + 契约行为 + V0 归因）与
    `_as_tri_bool` 三态（`verdict_requires_figure` 的 None/true/false 且 false≠缺失）。

    ★ 全部夹具是**代码内合成数据** —— dataset 与归档里的 gold_answer_status 本批一律不填
      （填它 = 正式盲标开工，红线）。
    """
    _c9q_errors()
    _c9q_verdicts()
    _c9q_gaps()
    from evaluation.task_eval.cases import ANSWER_STATUSES
    from evaluation.task_eval.predicates import generate as gen

    e1, e2, e3, e4 = _c9q_errors()
    rec_no_status, rec_foreign_status, v_ok, v_und = _c9q_verdicts()
    g_all, g_status, grp, nke = _c9q_gaps()
    check(
        "9q gold_answer_status：键集双向相等+值域五枚举 / 缺状态不得折成 present（判据行为）/ V0 五元组可归因且缺字段与错键分开统计",
        not e1
        and ANSWER_STATUSES
        == frozenset({"present", "missing_key", "incomplete_source", "illegible", "undecidable"})
        and bool(e2)
        and all(i.level == "ERROR" for i in e2 + e3 + e4)
        and bool(e3)
        and bool(e4)
        and gen._correctness(rec_no_status) == "missing_premise"
        and gen._answerability(rec_no_status) == "missing_premise"
        and gen._correctness(rec_foreign_status) == "missing_premise"
        and v_ok == "pass"
        and v_und == "not_applicable"
        and len(g_status) == 4  # 2 条夹具记录 × 2 个声明它的判据
        and {t[3] for t in grp} == {"old_archive_missing_field", "new_record_schema_violation"}
        and all(t[2] == "gold_answer" and t[4] is True for t in grp)
        and {t[1] for t in grp} == {"gen_answerability", "gen_correctness"}
        and len(g_all) > 0
        and nke == 0,
        f"e1={len(e1)} e2={[i.message[:18] for i in e2]} e3={len(e3)} e4={len(e4)} "
        f"mp={gen._correctness(rec_no_status)} 外键借用={gen._correctness(rec_foreign_status)} "
        f"present={v_ok} undecidable={v_und} 五元组={sorted(grp)} 错键计数={nke}",
    )
    _c9r()


def _c9m_stubs() -> dict:
    """9m 的 stage 桩集合：供 `_c9m_docs` 在真实编排层上打补丁（IO 子阶段纯内存替身）。"""
    from rag.retrieval.pipeline import _HydeOutcome as _HO9m
    from rag.retrieval.pipeline import _RetrievalPlan as _RP9m
    from rag.retrieval.pipeline import _WindowOutcome as _WO9m

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

    return {
        "classify": _p_classify9m,
        "plan": _p_plan9m,
        "decompose": _p_decompose9m,
        "recall": _p_recall9m,
        "recall_boom": _p_recall_boom9m,
        "dedup": _p_dedup9m,
        "hyde": _p_hyde9m,
        "window": _p_window9m,
    }


def _c9m_docs() -> tuple:
    # ── 9m（Important-3）：B2 空包送达 —— 行为锁（破坏性验证 ① 的落点） ─────────────
    #   A) **真实** `pipeline.aretrieve_documents`（编排层，IO 子阶段纯内存替身）：
    #      空结果 + HyDE 交回 `failed` ⇒ 调用方出参 `rerank_status_out` 被写入 `failed`
    #      （写在 `finally` ⇒ 早段异常路径也必须落，且落 `""`＝未知、**不凭空造**）；
    import asyncio

    import rag.retrieval.pipeline as _pipe9m

    # 档2 拆包后阶段函数住在 pipeline._stages：编排层经该模块命名空间调用它们，
    # 故**补丁打 `_stages9m`**（打在 `_pipe9m` 包顶层是静默无效的）；调用仍走 `_pipe9m`。
    import rag.retrieval.pipeline._stages as _stages9m
    from rag.retrieval.retrieval_plan import L2_STANDARD as _L2_9m

    stubs = _c9m_stubs()
    _pnames9m = (
        "_stage_classify_query",
        "_stage_resolve_plan",
        "_stage_decompose_query",
        "_stage_recall_and_merge",
        "_stage_dedup_and_threshold",
        "_stage_hyde",
        "_stage_expand_windows",
    )
    _orig9m_pipe = {n: getattr(_stages9m, n) for n in _pnames9m}

    sink_a: dict[str, str] = {}
    sink_x: dict[str, str] = {}
    raised9m = False
    try:
        _stages9m._stage_classify_query = stubs["classify"]
        _stages9m._stage_resolve_plan = stubs["plan"]
        _stages9m._stage_decompose_query = stubs["decompose"]
        _stages9m._stage_recall_and_merge = stubs["recall"]
        _stages9m._stage_dedup_and_threshold = stubs["dedup"]
        _stages9m._stage_hyde = stubs["hyde"]
        _stages9m._stage_expand_windows = stubs["window"]
        # A1：空包 + HyDE 交回 failed ⇒ 出参送达（真实编排 + 真实 _stage_rerank + 真实 finally 写入）
        docs9m = asyncio.run(
            _pipe9m.aretrieve_documents(
                "9m 查询", k=3, depth=_L2_9m.depth, rerank_status_out=sink_a
            )
        )
        a_ok = docs9m == [] and sink_a == {"rerank_status": "failed"}
        # A2：重排**之前**抛异常 ⇒ `finally` 仍要落，且落 ""（未知，不回填）
        _stages9m._stage_recall_and_merge = stubs["recall_boom"]
        try:
            asyncio.run(
                _pipe9m.aretrieve_documents(
                    "9m 查询", k=3, depth=_L2_9m.depth, rerank_status_out=sink_x
                )
            )
        except RuntimeError:
            raised9m = True
        x_ok = raised9m and sink_x == {"rerank_status": ""}
    finally:
        for n, f in _orig9m_pipe.items():
            setattr(_stages9m, n, f)
    return sink_a, sink_x, raised9m, a_ok, x_ok


def _c9m_bridge() -> dict:
    #   B) **真实** `retriever.aretrieve_evidence` 桥接：off/degraded/failed/success + 未写
    #      五格 —— 空包分支的 `fused.metadata` **恒有** `rerank_status` 键且值=桥接送出值。
    #      旧代码空包分支**根本没有这个键**（评审实测：状态在桥接这一跳被整包丢弃）。
    import asyncio

    import rag.retrieval.retriever as _ret9m
    import rag.retrieval.semantic_cache as _sc9m
    from rag.retrieval.retrieval_plan import L2_STANDARD as _L2_9m

    _orig9m_ret = (
        _ret9m.aclassify_query,
        _ret9m.decompose,
        _ret9m.aretrieve_documents,
        _sc9m.get_semantic_cache,
    )

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

    results9mb: dict[object, object] = {}
    try:
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
        (
            _ret9m.aclassify_query,
            _ret9m.decompose,
            _ret9m.aretrieve_documents,
            _sc9m.get_semantic_cache,
        ) = _orig9m_ret
    return results9mb


def _c9n() -> None:

    # ── 9n（Important-3）：基线 payload 导出（破坏性验证 ② 的落点） ────────────────
    #   `build_baseline_payload` 传**合成**观察（四态各一 + 一格老链路未写），断言
    #   `_meta.rerank_status_counts` 逐格导出、`""` 单列 `unknown`（不折进任何一态）；
    #   没传观察 ⇒ **不写该键**（没证据就不造一份「全未知」冒充送达）。
    #   ★ 口径红线：这只锁「自本批起新录基线会带该字段」；历史 9 份基线**没有**这个键，
    #     引用时不得写成「历史工件已补齐」（见 fixbatch 报告与 §20.7.2 B12 的更正登记）。
    from evaluation.gates.retrieval_gate import RerankObservation as _RO9n
    from evaluation.gates.retrieval_gate import RetrievalMetrics as _RM9n
    from evaluation.gates.retrieval_gate import build_baseline_payload as _bbp9n

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


def _c9o() -> None:
    import asyncio

    # ── 9o（Important-3）：probe 读侧送达 —— 行为锁（hop ③，评审实证的零 IO 路线） ──
    #   `aretrieve_evidence_with_retry` 换成返回**带 `rerank_status` 的 fused**（零 Chroma
    #   零 TEI），四态 + 空串各跑一次**真实** `probe_retrieval`（policy/finalize/apply 真码），
    #   断言 `probe.rerank_status` 逐格等值 —— 缺省/未知不落任何冒充值。
    import rag.retrieval.retriever as _ret9o
    from evaluation.task_eval.retrieval_probe import probe_retrieval as _probe9o
    from rag.retrieval.evidence import FusedEvidence as _FE9o

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


def _c9p() -> None:
    import asyncio

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


def _c9q_errors() -> None:
    from evaluation.task_eval import gold_status_sanity as gss
    from evaluation.task_eval.cases import Gold, TaskCase
    from evaluation.task_eval.gold_sanity import SanityIssue

    # ── 9q：键集相等（双向）+ 值域 + 「缺状态≠present」+ 分开统计 ─────────────
    def _sanity_errors(gold: Gold) -> list[SanityIssue]:
        out: list[SanityIssue] = []
        gss.check_gold_answer_status(
            TaskCase(case_id="9q", task="generate", query="q", gold=gold), out
        )
        return out

    # 格 1（一致）：ref 与 status 同键、值合法 ⇒ 零错误
    ok_gold = Gold(
        gold_answer="B",
        gold_source_ref={"gold_answer": "knowledge/exams/2012/items.md#x"},
        gold_answer_status={"gold_answer": "present"},
    )
    e1 = _sanity_errors(ok_gold)
    # 格 2（status 少一侧键）：有出处有值、无状态 ⇒ ERROR（且不得默认 present）
    e2 = _sanity_errors(
        Gold(
            gold_answer="B",
            gold_source_ref={"gold_answer": "knowledge/exams/2012/items.md#x"},
            gold_answer_status={},
        )
    )
    # 格 3（status 多一侧键，出处侧缺）——只查单向就漏这一格（牙齿③）
    e3 = _sanity_errors(
        Gold(gold_answer_status={"expected_difficulty": "present"}, gold_source_ref={})
    )
    # 格 4（越界值）：非五值枚举 ⇒ ERROR
    e4 = _sanity_errors(
        Gold(
            gold_answer="B",
            gold_source_ref={"gold_answer": "r"},
            gold_answer_status={"gold_answer": "verified_ok"},
        )
    )
    return e1, e2, e3, e4


def _c9q_verdicts() -> None:
    from evaluation.task_eval.predicates import generate as gen

    # 格 5（判据行为）：gold 值与出处都在、**缺状态** ⇒ gen_correctness 必须 missing_premise。
    #   ★ 牙齿①的位置：谁把缺失当 present（`st = status.get(k) or "present"`），这格变 pass 变红。
    rec_no_status = {
        "task": "generate",
        "case_id": "9q-mp",
        "reply": _gen_reply(),
        "gold": {
            "gold_answer": "B",
            "gold_source_ref": {"gold_answer": "knowledge/co/ch3.md#组相联"},
        },
    }
    # 格 6（读自己那一个 gold 字段）：status 里只有 expected_difficulty=present，
    #   gold_answer 无状态 ⇒ correctness 仍 missing_premise（别的键 present **不**外借）。
    rec_foreign_status = {
        "task": "generate",
        "case_id": "9q-foreign",
        "reply": _gen_reply(),
        "gold": {
            "gold_answer": "B",
            "gold_source_ref": {"gold_answer": "knowledge/co/ch3.md#组相联"},
            "gold_answer_status": {"expected_difficulty": "present"},
        },
    }
    # 格 7（合法 present ⇒ 正常测仍 pass，收紧不误伤）
    v_ok = gen._correctness(_base_record())
    # 格 8（undecidable 分流）：来源题不可唯一判定 ⇒ not_applicable，不是 missing/fail
    v_und = gen._correctness(
        {
            **_base_record(),
            "gold": {
                **_base_record()["gold"],
                "gold_answer_status": {"gold_answer": "undecidable"},
            },
        }
    )
    return rec_no_status, rec_foreign_status, v_ok, v_und


def _c9q_gaps() -> None:
    from evaluation.task_eval import schema_gate as sg

    # 格 9（V0 五元组归因 + 缺字段/错键分开统计）
    gap_recs = [
        # 老归档形状：gold 快照里连 gold_source_ref 都没有
        {
            "task": "generate",
            "case_id": "9q-old",
            "reply": _gen_reply(),
            "gold": {"gold_answer": "B"},
            "item_reasons": {},
        },
        # 新记录形状：Task 2+ 快照（带 gold_source_ref）却缺 gold_answer_status ⇒ 违反 schema
        {
            "task": "generate",
            "case_id": "9q-new",
            "reply": _gen_reply(),
            "gold": {
                "gold_answer": "B",
                "gold_source_ref": {"gold_answer": "knowledge/co/ch3.md#组相联"},
            },
            "item_reasons": {},
        },
    ]
    g_all = sg.contract_gaps(gap_recs)
    g_status = [g for g in g_all if g.missing_field == "gold.gold_answer_status"]
    grp = {
        (g.missing_field, g.predicate, g.gold_field, g.archive_state, g.resolvable_by_evidence)
        for g in g_status
    }
    nke = sg.confirmed_answer_key_error_count(gap_recs)
    return g_all, g_status, grp, nke


def _c9r() -> None:
    from evaluation.task_eval.cases import Gold, _as_tri_bool
    from evaluation.task_eval.predicates import generate as gen

    # ── 9r：_as_tri_bool 三态 + §4.4.3 incomplete_source×requires_figure 三格 ──
    tb_none = _as_tri_bool(None)  # 缺失 ⇒ 未声明
    tb_true = _as_tri_bool(True)
    tb_false = _as_tri_bool(False)
    tb_junk = _as_tri_bool("true")  # 畸形 = 没填（同 _as_str_dict 口径）
    parsed_none = Gold.from_dict({}).verdict_requires_figure
    parsed_false = Gold.from_dict({"verdict_requires_figure": False}).verdict_requires_figure
    v_none = gen._correctness(
        {
            **_base_record(),
            "gold": {
                **_base_record()["gold"],
                "gold_answer_status": {"gold_answer": "incomplete_source"},
            },
        }
    )  # 未声明 ⇒ missing_premise（硬规则：漏填不得绕过缺图保护）
    v_true = gen._correctness(
        {
            **_base_record(),
            "gold": {
                **_base_record()["gold"],
                "gold_answer_status": {"gold_answer": "incomplete_source"},
                "verdict_requires_figure": True,
            },
        }
    )  # 声明需要图 ⇒ missing_premise
    v_false = gen._correctness(
        {
            **_base_record(),
            "gold": {
                **_base_record()["gold"],
                "gold_answer_status": {"gold_answer": "incomplete_source"},
                "verdict_requires_figure": False,
            },
        }
    )  # 显式声明不需要 ⇒ 正常测（+披露走 item_reasons 通道）
    check(
        "9r _as_tri_bool 三态（None/true/false 各一，★ false≠缺失；bool(x) 实现会吞 false 格）+ incomplete_source×requires_figure 按 §4.4.3 三格分流",
        tb_none is None
        and tb_true is True
        and tb_false is False
        and tb_false is not tb_none
        and tb_junk is None
        and parsed_none is None
        and parsed_false is False
        and v_none == "missing_premise"
        and v_true == "missing_premise"
        and v_false == "pass",
        f"tri=({tb_none!r},{tb_true!r},{tb_false!r},畸形{tb_junk!r}) "
        f"from_dict=({parsed_none!r},{parsed_false!r}) 三格=未声明:{v_none} true:{v_true} false:{v_false}",
    )
