"""Evidence Chain 护栏的判据组二：`check_8`（8a–8o：memory 读链 / 四态映射 / reset 配对 / AST 承重锁）。

从原单文件 `evidence_chain_gate.py` 按判据边界原样搬出，逻辑一字未改。
"""

from __future__ import annotations

import ast

from _ecg_core import _gold, check


def check_8() -> None:
    _c8a_f()
    _c8g()
    _c8h()
    _c8i()
    _c8j()
    _c8k()

    # ── 8l（F5/B4 单元边界）：**行为**取证，不是源码字符串 ───────────────
    #   上一轮的真实漏洞：`run_case` 里那行 `reset_memory_read_statuses()` 被删掉后，
    #   58 + 217 项判据**全绿**（读链明细会在进程级通道里跨 case 粘连）。
    #   ⇒ 本判据**真的跑两次** `run_case`：第一个 case 注入一条 `failed`，
    #     断言第二个 case 的**明细与聚合**都不含它。抵抗「注释里提到函数名」的假阳性：
    #     只有实际调用才会清空通道。
    #   ★ 零 LLM：`_run_agent` 与 `probe_retrieval` 换成合成替身（它们各自要打模型 / 起 TEI），
    #     被取证的对象是 `run_case` **自己的**边界纪律与聚合路径（真实代码）。
    _c8l()

    # ── 8m（F2/B7 收割配对）：reset 与 harvest 必须**成对**出现 ────────────
    #   上一轮实测：全仓**没有任何判据**碰过这个配对。「只 reset 不收割」比不修更静默 ——
    #   每条 query 前清空、却没人把清空前的记录累计起来 ⇒ 除最后一条 query 之外
    #   所有索引故障都被扔掉，门禁照样「健康」。
    #   ★ AST 依据（不是字符串）：在 `retrieval_gate.py` 里找到**含 reset 调用的那个函数**，
    #     要求它内部存在一个 `try/finally`，其 `finalbody` 里同时有
    #     ① 对 `.query_failures` 的**读取**（Load），② 对某个累计变量的 `.extend(...)` 调用，
    #     ③ 该累计变量出现在本函数的 `return` 值里（收割了又扔掉 = 仍然红）。
    _c8m()
    _c8n()
    _c8o()


def _c8a_f() -> None:
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


def _c8g() -> None:
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
            "src/evaluation/gates/retrieval_gate/_gate.py",
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


def _c8h_service() -> None:

    # ── 8h（T8-C）：可用性必须被**证明**，不是被相信 ─────────────────────
    #   把 BM25 打坏，走**真实服务链路**（`_raw_search` → `_run()` → `_safe_to_thread`），
    #   断言三件事同时成立：① 不抛出（服务仍能收敛为「该路由空结果」）
    #   ② 失败被记进 `query_failures`（不是咽掉）③ 结果是空/默认值。
    #   用**不存在的 collection 名**制造故障：`get_collection()` 必然抛，
    #   且不需要起 Chroma 服务、不需要 embedding、零 token。
    import asyncio

    from rag.common.vectorstore import get_vector_store_manager
    from rag.retrieval import routes
    from rag.retrieval.bm25 import bm25_search

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
    return (
        missing,
        service_raised,
        route_id,
        docs,
        service_failures,
        producer_raised,
        producer_failures,
    )


def _c8h_timeout() -> None:
    import asyncio

    from rag.common.vectorstore import get_vector_store_manager
    from rag.retrieval import routes

    mgr = get_vector_store_manager()

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
    return timeout_raised, timeout_default, timeout_failures


def _c8h() -> None:
    (
        missing,
        service_raised,
        route_id,
        docs,
        service_failures,
        producer_raised,
        producer_failures,
    ) = _c8h_service()
    timeout_raised, timeout_default, timeout_failures = _c8h_timeout()

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


def _c8i() -> None:

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


def _c8j() -> None:

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


def _c8k() -> None:
    # ── 8k（F1 的回归锁）：单元内 reset **不许回来** ─────────────────────
    #   ★ AST 定位（`ast.Call` 的函数名），**不是** grep 字符串 —— 注释/docstring 里
    #     提到 `reset_query_failures` 不算调用点（本文件与 routes.py 的注释里就有好几处，
    #     字符串判据会当场假红/假绿）。
    #   两个断言：① `src/rag/routes.py` 里**零**调用；
    #            ② 生产面（`src/`）该调用**恰好**落在**三个**独立取证单元文件
    #               （gate / run_case / reprobe；按**文件路径**判定，不是出现次数）——
    #               修复批 Important-1 把 `cli.py` 补成第三单元，`run_case` 与 `_reprobe`
    #               都以「一次检索探针」为单元边界；
    #            ③ `scripts/` 侧唯一持有者是 gate 自己的取证夹具（8h 与 9j）——列进白名单并说明理由，
    #               否则「谁都能拿 reset 当测试脚手架」这件事也会变成隐式的第三点。
    #               ★ 单文件拆成「内核 + 判据组」后，持有者是 `_ecg_check8`(8h) 与
    #                 `_ecg_checks_9a`(9j) 两个模块 ⇒ 白名单按事实同步（新增持有者仍会红）。
    import ast
    from pathlib import Path

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
    _routes_tree = ast.parse(Path("src/rag/retrieval/routes.py").read_text(encoding="utf-8"))
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
            "src/evaluation/gates/retrieval_gate/_gate.py",
            "src/evaluation/task_eval/runner.py",
            "src/evaluation/task_eval/cli.py",
        }
        and scripts_units == {"scripts/gates/_ecg_check8.py", "scripts/gates/_ecg_checks_9a.py"},
        f"routes 调用行={routes_reset_calls} src={sorted(src_units)} scripts={sorted(scripts_units)}",
    )


def _c8l_run() -> None:
    import asyncio

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
    return mid, reset_spies, rec_l1, rec_l2, folded


def _c8l() -> None:
    mid, reset_spies, rec_l1, rec_l2, folded = _c8l_run()

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


def _c8m_walk_many(nodes: list[ast.stmt]) -> list[ast.AST]:
    """`ast.walk` 只吃**单个**节点；`finalbody` 是节点列表 ⇒ 逐个展开再走。"""
    import ast

    return [n for body in nodes for n in ast.walk(body)]


def _c8m_has_reset_call(node: ast.AST) -> bool:
    """节点内是否含 `reset_query_failures()` 调用（AST 定位，非字符串 grep）。"""
    import ast

    return any(
        isinstance(c, ast.Call) and getattr(c.func, "attr", "") == "reset_query_failures"
        for c in ast.walk(node)
    )


def _c8m_pairing() -> None:
    import ast
    from pathlib import Path

    _rg_tree = ast.parse(
        Path("src/evaluation/gates/retrieval_gate/_gate.py").read_text(encoding="utf-8")
    )

    _rg_funcs = [
        n
        for n in ast.walk(_rg_tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and _c8m_has_reset_call(n)
    ]
    pairing: list[str] = []
    for fn in _rg_funcs:
        acc_vars: set[str] = set()
        for t in ast.walk(fn):
            if not isinstance(t, ast.Try) or not t.finalbody:
                continue
            final_nodes = _c8m_walk_many(t.finalbody)
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
        # ★ 收割「回到调用方」有两种等价形态：① 变量出现在本函数 `return` 里；
        #   ② 变量是本函数**入参**（可变 list，调用方持有引用）——`_run_one_query` 把
        #   reset+收割下移后就是 ②：`run_query_failures` 由 `run_gate` 建、传入、再 return 出去。
        #   两者都满足「收割了且没扔」这一本判据的意图。
        params = {a.arg for a in (*fn.args.posonlyargs, *fn.args.args, *fn.args.kwonlyargs)}
        if not acc_vars or not (acc_vars & (returned | params)):
            pairing.append(
                f"{fn.name}: 累计变量={sorted(acc_vars)} "
                f"return 里的名字={sorted(returned)} 入参={sorted(params)}"
            )
    return _rg_funcs, pairing


def _c8m() -> None:
    _rg_funcs, pairing = _c8m_pairing()
    check(
        "8m retrieval_gate 的 reset 与收割成对（finalbody 读 query_failures + extend 同一累计变量 + 该变量被 return 或作为入参）",
        bool(_rg_funcs) and not pairing,
        f"含 reset 的函数={[f.name for f in _rg_funcs]}；未配对={pairing}",
    )


def _c8n() -> None:

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


def _c8o() -> None:

    # ── 8o（F6 的**结构**承重锁）：缺键区分必须由 `has_path` 承担，不能退化成真值判断 ──
    #   ★ 为什么 8n 不够：`_correct_use` 里「缺键 / 空串 / failed」三条分支**输出相同**
    #     （都 `missing_premise`）⇒ 任何行为用例都分不出 `has_path(...)` 与
    #     `rec.get("memory_read_status")` 的真值写法。所以这条只能走 AST：
    #     断言 `_correct_use` **函数体内**确有对 `has_path` 的调用、且实参点名 `memory_read_status`。
    #   ★ 不是「源码里出现过 has_path 这个字符串」—— 那连 import 都能满足，去掉承重分支照样绿。
    import ast as _ast8o
    import pathlib as _pl8o

    _mem_src = (
        _pl8o.Path(__file__).resolve().parents[2] / "src/evaluation/task_eval/predicates/memory.py"
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
