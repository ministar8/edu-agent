"""Evidence Chain 护栏的判据组三：`check_9`（9a–9h）+ `check_9reprobe`（9j）+ `check_9verify`（9k/9l）。

从原单文件 `evidence_chain_gate.py` 按判据边界原样搬出，逻辑一字未改。
"""

from __future__ import annotations

from pathlib import Path

from _ecg_core import check


def check_9() -> None:
    """B2 `rerank_status` 四态（§5 B2 / §6）+ B1 语义统一（§1.5 R4）的取证判据。

    Step 1 先红：`from rag.retrieval.pipeline import _derive_rerank_status` 触发 ImportError
    （生产者尚不存在）⇒ 判据先于实现落地，红→绿才可信。
    """
    _c9_states()
    _c9f()
    _c9g()
    _c9h()


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
    _rc9j, _a9j, _b9j, _note9j = _c9j_exec()
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
    _c9k()
    _c9l()


def _c9_states() -> None:
    from rag.retrieval.pipeline import _derive_rerank_status as D

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


def _c9f() -> None:

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


def _c9g() -> None:

    # ── 9g（B1 唯一权威换算点结构锁）：semantic_cache 私有实现必须已删除 ──────────
    #   ★ 破坏性验证 ④ 的落点：在 semantic_cache.py 恢复一份 `1.0 - distance` ⇒ 本判据红。
    import pathlib as _pl9

    from rag.common.embeddings import SUPPORTED_SPACES as _SS
    from rag.common.embeddings import similarity_from_distance as _SFD

    spaces_ok = _SS == frozenset({"cosine", "l2", "ip"})
    raised_unknown = False
    try:
        _SFD(0.1, "hamming")  # 未登记的 space ⇒ 必须抛，不静默回退成 cosine
    except ValueError:
        raised_unknown = True
    # ★ rag 重组后：semantic_cache 拆成 `semantic_cache.py + _semantic_cache_{codec,io}.py`、
    #   vectorstore 拆成 `vectorstore.py + _vectorstore_{base,query,ingest}.py` ⇒ 读整组，
    #   否则断言会因「字符串搬到了同包的另一文件」而假红（断言原意不变）。
    _root9g = _pl9.Path(__file__).resolve().parents[2]

    def _concat9g(pattern: str) -> str:
        return "".join(p.read_text(encoding="utf-8") for p in sorted(_root9g.glob(pattern)))

    _sc_src = _concat9g("src/rag/retrieval/*semantic_cache*.py")
    _vs_src = _concat9g("src/rag/common/*vectorstore*.py")
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


def _c9h() -> None:
    import pathlib as _pl9

    # ── 9h（B2 全链路**名称配对**结构锁）：`rerank_status` 要跨三跳改名才落到归档 ──────
    #   pipeline 写 `doc.metadata["_rerank_status"]` → retriever 桥接成 `fused.metadata["rerank_status"]`
    #   → retrieval_probe 读该键 → runner 落 `record.rerank_status`（`rerank_used` 由它派生）。
    #   ★ 为什么这条只能走结构：桥接发生在 `aretrieve_documents` 内部（要碰 Chroma），
    #     纯内存行为测试拿不到它；而每一跳都带 `""` 掩盖默认值 ⇒ 任何一侧改名都会让下游
    #     **静默变成「未知」**，9f/9g 都不会红（9f 测纯函数、9g 测 B1）。
    #   ★ 本判据锁的是「四处的键名与赋值方向必须成对存在」——改名即红；
    #     它**不**证明运行时真的有值送达，那由一次性端到端复证负责（见 task-9-report 阶段 A 末节）。
    _src9 = _pl9.Path
    _root9 = _src9(__file__).resolve().parents[2]

    def _read9(rel: str) -> str:
        return (_root9 / rel).read_text(encoding="utf-8")

    def _read9glob(pattern: str) -> str:
        """★ rag 重组后 `pipeline.py` 成了包、`retriever.py` 拆出 `retriever_io.py`
        （桥接两行搬了过去）⇒ 按组拼接读，断言原意（键名四跳配对）不变。"""
        return "".join(p.read_text(encoding="utf-8") for p in sorted(_root9.glob(pattern)))

    _pipe9 = _read9glob("src/rag/retrieval/pipeline/*.py")
    _ret9 = _read9glob("src/rag/retrieval/retriever*.py")
    _probe9 = _read9("src/evaluation/task_eval/retrieval_probe.py")
    # ★ `runner.py` 精简后拆出 `_runner_record.py`（`CaseRecord.rerank_used` property 在此）
    #   ⇒ 读 `*runner*.py` 整组，否则 ④ 的 `self.rerank_status == "success"` 查找假红。
    _run9 = _read9glob("src/evaluation/task_eval/*runner*.py")
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


def _c9j_exec() -> None:
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
    from rag.common.vectorstore import get_vector_store_manager as _gvsm

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
    return _rc9j, _a9j, _b9j, _note9j


def _c9k() -> None:

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


def _c9l() -> None:

    # ── 9l（Important-2 的**结构**承重锁，与 `8o` 同款）：缺键区分由 `has_path` 承担 ──
    #   ★ 为什么 9k 不够：`_no_reply` 对「缺键」与「空串」的**输出相同**（都 missing_premise）
    #     ⇒ 行为用例分不出 `has_path(...)` 与真值写法 `not rec.get("retrieval_status")`
    #     （后者今天行为等价，但它把「存在性」悄悄换成了「真值」——F6 的教训正是从这里长出来的）。
    #     与 `8o` 同一理由：只能走 AST，定位 `_no_reply` **函数体内**确有 `has_path` 调用且点名该键。
    import ast as _ast9l
    import pathlib as _pl9l

    _ver_src9l = (
        _pl9l.Path(__file__).resolve().parents[2] / "src/evaluation/task_eval/predicates/verify.py"
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
