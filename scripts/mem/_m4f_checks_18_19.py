"""memory_step4fix_gate 判据组：⑱⑲

从原单文件 `memory_step4fix_gate.py` 按判据边界原样搬出，逻辑一字未改。
"""

from __future__ import annotations

import asyncio

from _m4f_core import ROOT, check, section, skip


def check_18() -> None:
    """⑱ Memory 主指标**只允许一份公式**（2026-10-07 修 #21 —— 我自家 #4 修复的漏）。

    发现过程（Step 9 实跑时撞出来的）：新归档里三条**负样本**的
    `memory_correct_use` 全是 `False`，而 #4 改过的口径明确规定
    「负样本 = 未召回 ∧ 未误用 ⇒ True」。顺链一查：

        `memory_scorer.MemoryJudgement.correct_use`  ← #4 改在这里（极性版）✅
        `runner.CaseRecord.memory_correct_use`       ← property，**仍是旧三元 AND** ❌
        `CaseRecord.to_dict()`                       ← 用的是**那个 property**
        `report.py`                                  ← 读归档字段 ⇒ 拿到的是旧值

    ⇒ #4 的修复**从来没落进归档、也从来没进过报告**（实测报告印 2/6=0.333，
      极性口径应为 4/6=0.667）。而 ③d~③h 那组护栏当时全绿 —— 因为它们测的是
      `memory_scorer` 的**函数**，没测「函数结果如何被写出」。
      这正是「只测 helper、不测接线」那一类。
    """
    section("⑱ Memory 主指标三处一致（scorer / record / report）")
    _c18_archive()
    _c18_neg()
    m1 = _c18_m4()
    _c18_m1(m1)
    _c18_hanging(m1)


def check_19() -> None:
    """⑲ 「前置条件满足却没有记忆卡」的真因：KP 聚合按**精确名**计 hit（2026-10-07 #22）。

    Step 9 实跑撞到的现象：Store ON 的 mem-002 **两次批改都 0 分**（低分前置条件满足），
    但 `memory_cards = 0`、B 段召不回。只报数字的话会被读成「产品不召回」。

    真因用**纯函数**（零 LLM、零网络、零 DB）钉死：`compute_weak_topics` 的聚合单位是
    **KP 精确名**，阈值 `MEMORY_WEAK_MIN_HITS=2` ⇒ 两道题、同一章、不同考点 ⇒
    各 1 hit ⇒ 谁都不过线 ⇒ 画像为空。
    """
    section("⑲ KP 聚合按精确名计 hit ⇒ 正样本可能天然测不到召回（#22）")
    _c19_kp()
    _c19_run(*_c19_setup())


def _c18_archive() -> None:

    import json as _json

    from evaluation.task_eval import memory_scorer as _ms
    from evaluation.task_eval import metrics
    from evaluation.task_eval.report import build_report

    # ⑱a 已发表数字必须经**报告路径**复现（不是靠我手工重算）
    fp = ROOT / "evals" / "results" / "task_eval" / "phase1_memory_step5_store_on.jsonl"
    recs = []
    if fp.exists():
        recs = [
            _json.loads(ln)
            for ln in fp.read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.startswith("#")
        ]
        cu = build_report(recs)["tasks"]["memory"]["memory_correct_use"]
        check(
            "⑱a 报告路径复现 #4 的数字：ON 组 correct_use = 4/6 = 0.6667（旧口径是 2/6）",
            cu["passed"] == 4 and cu["n"] == 6,
            str(cu),
        )
        # ⑱b 逐条：report 的推导 必须 == scorer 的公式（两套账不许分叉）
        bad = []
        for r in recs:
            em = (r.get("gold") or {}).get("expected_memory") or {}
            j = _ms.MemoryJudgement(
                recalled_pass=r.get("memory_retrieved"),
                used=r.get("memory_used"),
                correct=r.get("memory_correct"),
                recalled_actual=r.get("memory_recalled_actual"),
                should_be_recalled=em.get("should_be_recalled"),
                forbidden_hits=tuple(r.get("memory_forbidden_hits") or ()),
            )
            if metrics.memory_correct_use_from_record(r) != j.correct_use:
                bad.append(r["case_id"])
        check("⑱b 逐条一致：report 推导 == scorer 公式（无第二套账）", not bad, str(bad))
    else:
        skip("⑱a/⑱b", "ON 归档不在本机（未入库）⇒ 已发表数字的报告路径复现未执行", count=2)


def _c18_neg() -> None:
    from evaluation.task_eval import metrics

    # ⑱c ★ 反向：负样本在旧三元 AND 下必判 False、在新口径下必判 True
    neg = {
        "gold": {
            "expected_memory": {
                "type": "weak_topics",
                "values": ["栈"],
                "should_be_recalled": False,
            }
        },
        "memory_retrieved": False,  # recalled_pass：负样本未召回 = 通过
        "memory_recalled_actual": False,
        "memory_used": False,
        "memory_correct": False,
        "memory_forbidden_hits": [],
    }
    old_and = (
        bool(neg["memory_retrieved"]) and bool(neg["memory_used"]) and bool(neg["memory_correct"])
    )
    check(
        "⑱c 反向：同一份负样本，旧三元 AND=False、新口径=True（口径差异真实存在）",
        old_and is False and metrics.memory_correct_use_from_record(neg) is True,
        f"旧={old_and} 新={metrics.memory_correct_use_from_record(neg)}",
    )


def _c18_m4() -> None:
    from dataclasses import asdict as _asdict

    from evaluation.task_eval import metrics
    from evaluation.task_eval.cases import load_cases
    from evaluation.task_eval.runner import (
        CaseRecord,
        _apply_memory_judgement,
    )

    # ⑱d ★★ 测**接线**而非只测函数：走真实的 `_apply_memory_judgement`，
    #   断言 scorer 的极性值真的写进了 record 并可从 `to_dict()` 读出。
    #   （#21 的成因恰恰是这一层被 property 覆盖 —— 只测 scorer 永远发现不了。）
    cases = load_cases(ROOT / "evals" / "datasets" / "demo" / "memory_cases.jsonl")
    m4 = next((c for c in cases if c.case_id == "mem-004"), None)
    if m4 is None:
        check("⑱d mem-004 存在", False, "载入 0 条")
        return
    rec = CaseRecord(
        case_id="mem-004",
        task="memory",
        task_mode=m4.task_mode,
        query=m4.query,
        # ★ Task 8 B4：这两条夹具断言的是「读链**测过了**之后的极性口径」，
        #   故显式补 `memory_read_status="success"` —— 该字段的新增语义是
        #   「`failed`/`not_attempted`/`""` ⇒ 三维 None（未测量）」，
        #   缺省成空串会让下面的断言读到 None（把「测试自己的缺项」当成产品红灯，
        #   正是 ⑱d 注释里已经避过一次的那类坑）。断言本身一个字没改。
        memory_read_status="success",
    )
    # ★ 必须按**真实 record 的状态**构造：`gold` 是 `run_case` 赋的、不是本函数赋的。
    #   少了这一步，`from_record` 读到空 gold ⇒ should_be_recalled=None ⇒ 返回 None，
    #   于是红灯来自测试自己的缺项而不是产品逻辑（实测踩过一次，红得很像真 bug）。
    rec.gold = _asdict(m4.gold)
    _apply_memory_judgement(rec, m4, memory_cards=[], reply="本题要点如下。")
    check(
        "⑱d 真实接线：负样本经 `_apply_memory_judgement` ⇒ record 字段与 to_dict 都是 True",
        rec.memory_correct_use is True
        and rec.to_dict()["memory_correct_use"] is True
        and metrics.memory_correct_use_from_record(rec.to_dict()) is True,
        f"字段={rec.memory_correct_use} to_dict={rec.to_dict()['memory_correct_use']}",
    )
    # ⑱e 正样本反例：没召回 ⇒ 必须 False（防「修复」变成「负样本一律放行」）
    m1 = next((c for c in cases if c.case_id == "mem-001"), None)
    return m1


def _c18_m1(m1) -> None:
    from evaluation.task_eval.runner import (
        CaseRecord,
        _apply_memory_judgement,
    )

    if not m1 is not None:
        return
    rec1 = CaseRecord(
        case_id="mem-001",
        task="memory",
        task_mode=m1.task_mode,
        query=m1.query,
        # ★ 同 ⑱d：这条夹具断言「测过之后确实记 False」，前提必须是读链**测量成立**
        #   （`memory_read_status=""` 在新语义下 = 未测量 ⇒ 三维 None，
        #   那会让红灯来自夹具缺项而不是产品逻辑）。断言未改。
        memory_read_status="success",
    )
    _apply_memory_judgement(rec1, m1, memory_cards=[], reply="本题要点如下。")
    check(
        "⑱e 正样本未召回 ⇒ False（不是 N/A、更不是 True）",
        rec1.memory_correct_use is False,
        f"{rec1.memory_correct_use} | recalled_actual={rec1.memory_recalled_actual}",
    )


# ⑱f ★★ Task 8 B4：**故障注入走真实读链**（不是手搓一个 record 字段）。
#   把 Store 换成「`aget` 永远挂住」的假实现 ⇒ `load_memory` 的读超时 ⇒
#   `safe_remember_status` 报 `failed` ⇒ runner 聚合 ⇒ `_apply_memory_judgement`。
#   断言的是**方向**：测不到 ⇒ 三维 None（N/A，不进分母），
#   ★ 绝不能是 `False` —— 一次 Store 超时被记成「产品召回失败」就是
#   直接压低论文里的 Memory 数字（§4.3「Memory 三维」那一行的原话）。
def _c18_hanging(m1) -> None:
    from dataclasses import asdict as _asdict

    from agents.teaching_graph import load_memory, memory_read_statuses, reset_memory_read_statuses
    from core.settings import settings as _st
    from evaluation.task_eval.predicates import registry as _reg
    from evaluation.task_eval.runner import (
        CaseRecord,
        _apply_memory_judgement,
        aggregate_memory_read_status,
    )
    from memory.runtime import get_store, set_store

    class _HangingStore:
        async def aget(self, *_a, **_k):
            await asyncio.sleep(30)

    _prev_timeout, _prev_store = _st.MEMORY_WRITE_TIMEOUT, get_store()
    injected_status, dims, verdict = "", (), ""
    try:
        _st.MEMORY_WRITE_TIMEOUT = 0.05
        set_store(_HangingStore())
        reset_memory_read_statuses()
        asyncio.run(
            load_memory(
                {"messages": []},
                {"configurable": {"thread_id": "gate-18f", "user_id": 999}},
            )
        )
        injected_status = aggregate_memory_read_status(memory_read_statuses(), [])
        rec_f = CaseRecord(
            case_id=m1.case_id,
            task="memory",
            task_mode=m1.task_mode,
            query=m1.query,
            memory_read_status=injected_status,
        )
        rec_f.gold = _asdict(m1.gold)
        _apply_memory_judgement(rec_f, m1, memory_cards=[], reply="本题要点如下。")
        dims = (
            rec_f.memory_retrieved,
            rec_f.memory_used,
            rec_f.memory_correct,
            rec_f.memory_correct_use,
        )
        verdict = _reg.get("memory_correct_use").fn(rec_f.to_dict())
    finally:
        _st.MEMORY_WRITE_TIMEOUT = _prev_timeout
        set_store(_prev_store)
        reset_memory_read_statuses()
    check(
        "⑱f 故障注入（读链超时）⇒ 注入状态 failed 且三维 None 而非 False",
        injected_status == "failed"
        and all(d is None for d in dims)
        and verdict == "missing_premise",
        f"注入={injected_status!r} 三维={dims} verdict={verdict!r}",
    )


def _c19_kp() -> None:

    from core.settings import settings
    from memory.schemas import Episode
    from memory.weak_topics import compute_weak_topics

    def _ep(kps: list[str], score: float = 0.0) -> Episode:
        return Episode(type="grade", topic=kps[0] if kps else "", score=score, knowledge_points=kps)

    diff = compute_weak_topics(
        [_ep(["图的基本性质"]), _ep(["图的存储"])], allow_legacy_fallback=False
    )
    same = compute_weak_topics(
        [_ep(["平衡二叉树"]), _ep(["平衡二叉树"])], allow_legacy_fallback=False
    )
    check(
        f"⑲a 两次低分、**不同** KP ⇒ 画像为空（MIN_HITS={settings.MEMORY_WEAK_MIN_HITS} 是硬门槛）",
        diff == [] and settings.MEMORY_WEAK_MIN_HITS >= 2,
        str(diff),
    )
    check(
        "⑲b 两次低分、**同一** KP ⇒ 画像有值（对照：聚合机制本身是通的，不是坏在别处）",
        same == ["平衡二叉树"],
        str(same),
    )
    check(
        "⑲c 一道题给多个 KP ⇒ 每个各计 1 hit，单道题仍过不了线（跨题必须**同名**才累加）",
        compute_weak_topics([_ep(["平衡二叉树", "二叉排序树"])], allow_legacy_fallback=False) == [],
    )


def _c19_setup() -> None:
    from langchain_core.messages import AIMessageChunk, ToolMessage

    from memory.schemas import Episode

    # ⑲d ★ 接线：`run_sessions` 必须在**跑后清理之前**把 Store 里的 episodes 读出来。
    #   用最小假 store（只实现 asearch/adelete）驱动**真实**的 run_sessions ——
    #   与 ⑰ 同一思路：测函数如何被调用，而不是只测函数本身（#21 就是漏在这一层）。
    class _FakeItem:
        def __init__(self, value: dict) -> None:
            self.value = value

    class _FakeStore:
        def __init__(self, episodes: list[Episode]) -> None:
            # ★ `Episode` 是 **Pydantic 模型**（不是 dataclass）⇒ 用 `model_dump()`；
            #   用 `dataclasses.asdict` 会 TypeError（实测踩过），假 store 就装不出真实形状。
            self._items = [_FakeItem(e.model_dump()) for e in episodes]
            self.deleted = 0

        async def asearch(self, ns, query=None, filter=None, limit=None, offset=0):  # noqa: A002
            return list(self._items)

        async def adelete(self, ns, key) -> None:
            self.deleted += 1

    class _StubAgent:
        def __init__(self, store) -> None:
            self.store = store
            self.checkpointer = None
            self._n = 0

        async def astream(self, _inp, *, config, stream_mode, subgraphs):  # noqa: ARG002
            self._n += 1
            if self._n == 1:
                yield (
                    ("supervisor",),
                    "messages",
                    (
                        ToolMessage(
                            content=_graded_text(),
                            tool_call_id="c1",
                            name="grade_student_answer",
                        ),
                        {},
                    ),
                )
            yield (("supervisor",), "messages", (AIMessageChunk(content="回复"), {}))

    def _graded_text() -> str:
        from agents.grading_core import format_grading_for_chat
        from schema.grading import GradingResult

        return format_grading_for_chat(
            GradingResult(score=30, feedback="概念混淆", is_wrong=True, error_analysis="漏要点")
        )

    return _FakeStore, _StubAgent, _graded_text


def _c19_run(_FakeStore, _StubAgent, _graded_text) -> None:
    import asyncio as _aio

    import lib.agent_behavior_smoke as smoke

    from memory.episodes import coerce_episode
    from memory.schemas import Episode
    from memory.weak_topics import compute_weak_topics

    eps_in = [
        Episode(type="grade", topic="图的存储", score=30.0, knowledge_points=["图的存储"]),
        Episode(type="grade", topic="图的基本性质", score=0.0, knowledge_points=["图的基本性质"]),
    ]
    fs = _FakeStore(eps_in)
    agent = _StubAgent(fs)
    res = _aio.run(
        smoke.run_sessions(
            agent,
            [["批改：图题一", "批改：图题二"]],
            user_id="gate-episodes-capture",
            cleanup_first=False,
            store_enabled=True,
        )
    )
    check(
        "⑲d 接线：run_sessions 在清理前读出 episodes，且带 knowledge_points（否则#22 又无从取证）",
        len(res.episodes) == 2 and all("knowledge_points" in e for e in res.episodes),
        f"{len(res.episodes)} 条 KPs={[e.get('knowledge_points') for e in res.episodes]}",
    )
    check(
        "⑲e 读到的 episodes 直接喂聚合 ⇒ 复现「两个不同 KP ⇒ 空画像」的同一条链",
        compute_weak_topics(
            [
                Episode(
                    type="grade",
                    topic=e["topic"],
                    score=e["score"],
                    knowledge_points=e["knowledge_points"],
                )
                for e in res.episodes
            ],
            allow_legacy_fallback=False,
        )
        == [],
        str([e["knowledge_points"] for e in res.episodes]),
    )
    _ = coerce_episode  # 仅表明假 store 的形状与真实读出路径一致（coerce_episode 消费 dict）
