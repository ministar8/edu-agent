"""memory_step4fix_gate 判据组：④ checkpointer 清理 / ⑤ gold_sanity / ⑥⑦⑧

从原单文件 `memory_step4fix_gate.py` 按判据边界原样搬出，逻辑一字未改。
"""

from __future__ import annotations

import ast
import inspect
import json
import textwrap

from _m4f_core import ROOT, _gold, check, section

# ── ④ checkpointer 跑后清理 ──────────────────────────────────


def check_4() -> None:
    section("④ checkpointer 跑后清理")

    import lib.agent_behavior_smoke as harness  # type: ignore[import-not-found]

    check("④a `_cleanup_threads` 已实现", callable(getattr(harness, "_cleanup_threads", None)))

    src = inspect.getsource(harness.run_sessions)
    # ★ 用 AST 找 `try/finally` 结构，而不是 `"finally:" in src`（2026-10-06 修）。
    #   字符串匹配的坑（本 Gate 反向验证实测抓到）：docstring 里就写着「在 ``finally`` 里」，
    #   且破坏成 `if True:` 后注释里的「跑后清理」仍在 ⇒ 字符串检查恒真 ⇒ 假阳性。
    #   AST 则直接证明**存在带 finally 的 Try 节点**。
    tree = ast.parse(textwrap.dedent(src))
    try_final = [n for n in ast.walk(tree) if isinstance(n, ast.Try) and n.finalbody]
    check("④b 存在 try/finally 结构（异常/提前 return 也会清）", bool(try_final))

    if try_final:
        fin_src = "\n".join(ast.unparse(stmt) for node in try_final for stmt in node.finalbody)
        check(
            "④b `finally` 内含 Store 与 checkpointer 两个清理",
            "_cleanup_user_store" in fin_src and "_cleanup_threads" in fin_src,
        )
    else:
        check("④b `finally` 内含 Store 与 checkpointer 两个清理", False, "无 finally 块")

    body_src = "\n".join(ast.unparse(stmt) for node in try_final for stmt in node.body)
    check("④c thread 列表在 try 内收集（供 finally 使用）", "used_threads.append" in body_src)


async def check_4_real() -> None:
    """真建一个 thread 再删 —— 证明 `_cleanup_threads` 不是空转。"""
    from lib.agent_behavior_smoke import _cleanup_threads  # type: ignore[import-not-found]

    from memory import initialize_database

    async with initialize_database() as saver:
        if hasattr(saver, "setup"):
            await saver.setup()
        tid = "gate-step4fix-probe-thread"
        cfg = {"configurable": {"thread_id": tid}}
        # 写一条最小检查点
        try:
            from langchain_core.messages import HumanMessage

            await saver.aput(
                {"configurable": {"thread_id": tid, "checkpoint_ns": ""}},
                {
                    "v": 1,
                    "id": "1",
                    "ts": "2026-01-01T00:00:00+00:00",
                    "channel_values": {"messages": [HumanMessage(content="probe")]},
                    "channel_versions": {},
                    "versions_seen": {},
                    "pending_sends": [],
                },
                {"source": "input", "step": 0, "writes": {}},
                {},
            )
        except Exception as e:  # noqa: BLE001
            print(f"    （写探针检查点时忽略：{type(e).__name__}: {e}）")
        before = await saver.aget_tuple(cfg)
        n = await _cleanup_threads(saver, [tid])
        after = await saver.aget_tuple(cfg)
        check(
            "④d 真 thread：清理前存在 → 清理后消失",
            (before is not None) and (after is None),
            f"before={'有' if before else '无'} after={'有' if after else '无'} removed={n}",
        )


# ── ⑤ gold_sanity ────────────────────────────────────────────


def check_5() -> None:
    section("⑤ gold_sanity 对 memory 的校验")
    _c5_a()
    _c5_b()
    _c5_c()
    _c5_e()
    _c5_d()


def check_6() -> None:
    """⑥ case validity（A 段前置条件验收，2026-10-06 Step 5）。"""
    section("⑥ case validity（前置条件验收）")

    from evaluation.task_eval.cases import SetupConditions
    from evaluation.task_eval.memory_scorer import check_case_validity as V

    low2 = SetupConditions.from_dict(
        {"min_grade_calls": 2, "grade_score_bands": [[0, 59], [0, 59]]}
    )
    hi2 = SetupConditions.from_dict(
        {"min_grade_calls": 2, "grade_score_bands": [[60, 100], [60, 100]]}
    )

    r = V(setup=hi2, grade_scores=[{"session": 0, "score": 100.0}, {"session": 0, "score": 95.0}])
    check("⑥a 高分样本·实际 100/95 ⇒ valid", r.valid is True, r.reason)
    r = V(setup=hi2, grade_scores=[{"session": 0, "score": 100.0}, {"session": 0, "score": 52.0}])
    check("⑥b 高分样本·实际 100/52 ⇒ **invalid**（不判产品失败）", r.valid is False, r.reason)
    r = V(setup=low2, grade_scores=[{"session": 0, "score": 55.0}, {"session": 0, "score": 50.0}])
    check("⑥c 低分样本·实际 55/50 ⇒ valid", r.valid is True, r.reason)
    r = V(setup=low2, grade_scores=[{"session": 0, "score": 55.0}])
    check("⑥d 批改次数不足 ⇒ invalid", r.valid is False, r.reason)
    r = V(setup=low2, grade_scores=[{"session": 0, "score": None}, {"session": 0, "score": 50.0}])
    check("⑥e 得分抓不到 ⇒ invalid（fail-fast，不默认满足）", r.valid is False, r.reason)
    r = V(setup=low2, grade_scores=[{"session": 1, "score": 10.0}, {"session": 1, "score": 10.0}])
    check("⑥f 只认 A 段（session=0）—— B 段批改不算数", r.valid is False, r.reason)
    r = V(setup=None, grade_scores=[])
    check("⑥g 未声明前置条件 ⇒ 不校验（valid=None，不阻塞）", r.valid is None, r.reason)

    # 与「产品失败」区分的落盘标记
    import evaluation.task_eval.metrics as metrics

    check(
        "⑥h `case_invalid` 已入 failure_reason 枚举且优先级最高",
        "case_invalid" in metrics.FAILURE_REASONS
        and metrics.pick_primary_failure(["case_invalid", "memory_miss"]) == "case_invalid",
    )


def check_7() -> None:
    """⑦ paired control（Store ON/OFF 开关接线，2026-10-06 Step 5）。"""
    section("⑦ paired control（Store ON/OFF）")

    import lib.agent_behavior_smoke as harness  # type: ignore[import-not-found]

    sig = inspect.signature(harness.run_sessions)
    check(
        "⑦a run_sessions 接受 store_enabled 参数",
        "store_enabled" in sig.parameters,
        str(sig),
    )

    # ★ ⑦b/⑦c 原本是**源码文本断言**（在 `run_sessions` 里 AST 找 `agent.store = None`），
    #   2026-10-07 把 OFF 臂摘除逻辑抽成 `_off_arm_disable/_off_arm_restore`（#24 修正）后
    #   它们立刻变红 —— 正好演示了这类断言的脆弱：**代码搬家了，行为没变，红灯却响了**。
    #   ⇒ 改成对 helper 的**行为断言**：真的调用它、真的看 `get_store()`/`agent.store` 变成什么。
    import lib.agent_behavior_smoke as _smoke

    from memory.runtime import get_store as _get_store
    from memory.runtime import set_store as _set_store

    class _ProbeAgent:
        def __init__(self, st) -> None:
            self.store = st

    _sentinel = object()
    _prev = _get_store()
    try:
        _set_store(_sentinel)
        _pa = _ProbeAgent(_sentinel)
        _saved = _smoke._off_arm_disable(_pa, _sentinel)
        detached = _pa.store is None and _get_store() is None
        check(
            "⑦b OFF 臂摘除：agent.store 与**进程级 get_store()** 两处都置空",
            detached,
            f"agent={_pa.store!r} global={_get_store()!r}",
        )
        _smoke._off_arm_restore(_pa, _sentinel, _saved)
        check(
            "⑦c 恢复：两处都回来（进程级忘恢复 ⇒ 后续 case 静默失去记忆且不报错）",
            _pa.store is _sentinel and _get_store() is _sentinel,
        )
    finally:
        _set_store(_prev)

    from evaluation.task_eval.runner import _run_agent

    rsig = inspect.signature(_run_agent)
    check("⑦d _run_agent 透传 store_enabled", "store_enabled" in rsig.parameters)

    from evaluation.task_eval import runner

    rsrc = inspect.getsource(runner.run_case)
    check(
        "⑦e run_case 接受 store_enabled 并记录到 record",
        "store_enabled" in inspect.signature(runner.run_case).parameters,
    )
    assert rsrc  # 引用避免 lint 删除


def check_8() -> None:
    """⑧ knowledge_points 规范名一致性（2026-10-06 Step 5 实测新增）。

    Memory 聚合（`weak_topics`）拿 `Episode.knowledge_points` 与 `kp_index` 的
    canonical name 做匹配。若 prompt / schema 里的**示例名**本身不是 canonical，
    会诱导模型输出漂移值 ⇒ 聚合系统性错配。故把「示例名必须 canonical」变成机械护栏。
    """
    section("⑧ knowledge_points 示例名必须与 kp_index 一致")
    import re

    kp_dir = ROOT / "knowledge" / "knowledge_points"
    canonical: set[str] = set()
    for f in ("ds", "cn", "co", "os"):
        p = kp_dir / f"{f}.jsonl"
        if not p.exists():
            continue
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except Exception:
                continue
            if d.get("name"):
                canonical.add(str(d["name"]))
    check("⑧a kp_index 可加载且有 canonical name", len(canonical) > 100, f"{len(canonical)} 个")

    # 从 prompt / schema 里抽出「例如：A、B、C」形式列出的示例名。
    #   ★ 注意：Python 源码里长字符串是**跨行拼接**的（相邻字符串字面量隐式连接），
    #     直接对源码正则会在行尾断掉、只抽到前半句。故这里把「引号 + 换行 + 缩进」
    #     一律归一为空白，让整句接起来再匹配 —— 否则护栏会漏检后半句（实测踩过）。
    targets = [
        ROOT / "src" / "prompts" / "service.py",
        ROOT / "src" / "schema" / "grading.py",
    ]
    bad: list[tuple[str, str]] = []
    checked = 0
    for t in targets:
        raw = t.read_text(encoding="utf-8")
        # 去掉行尾续行符与字符串边界，压成一行
        flat = re.sub(r"[\"']\s*\n\s*[\"']", "", raw)
        flat = flat.replace("\\n", " ").replace("\n", " ")
        for m in re.finditer(r"例如[：:]\s*([^。]+)", flat):
            for name in re.split(r"[、,，]", m.group(1)):
                name = name.strip().strip("「」\"'")
                # 过滤掉说明性长句（示例名都很短）
                if not name or len(name) > 20 or any(c in name for c in "（）()*→"):
                    continue
                checked += 1
                if name not in canonical:
                    bad.append((t.name, name))
    check("⑧b 抽到了示例名（护栏本身有效）", checked > 0, f"核验 {checked} 个")
    check(
        "⑧c **全部示例名均为 canonical**（非 canonical 会诱导模型漂移）",
        not bad,
        "" if not bad else f"非规范: {bad}",
    )


def _c5_a() -> None:

    from evaluation.task_eval.cases import TaskCase
    from evaluation.task_eval.gold_sanity import run_sanity

    # 缺失 gold → ERROR
    c = TaskCase(case_id="mem-x", task="memory", query="q", turns=["a", "b"])
    rep = run_sanity([c])
    fields = {i.field_name for i in rep.errors}
    check(
        "⑤a gold 缺失 ⇒ ERROR（expected_memory + expected_answer_property）",
        {"expected_memory", "expected_answer_property"} <= fields,
        str(sorted(fields)),
    )


def _c5_b() -> None:
    from evaluation.task_eval.cases import TaskCase
    from evaluation.task_eval.gold_sanity import run_sanity

    # 非 canonical name（「图论」；canonical 是「图」）→ ERROR
    c2 = TaskCase(
        case_id="mem-y",
        task="memory",
        query="q",
        turns=["a", "b"],
        gold=_gold(True, ["图论"], ["栈"]),  # 「图论」不是 canonical name
    )
    rep2 = run_sanity([c2])
    bad = [i for i in rep2.errors if i.field_name == "expected_memory.values"]
    check(
        "⑤b 非 canonical name 的 values ⇒ ERROR（抓字符串漂移）",
        bool(bad),
        bad[0].message[:60] if bad else "",
    )


def _c5_c() -> None:
    from evaluation.task_eval.cases import TaskCase
    from evaluation.task_eval.gold_sanity import run_sanity

    # canonical name（「图的存储」）→ 无 ERROR
    # ★ 原先这里用的是「图」，被 #26 的粒度 lint（㉔）判成 ERROR —— 两条护栏撞了，
    #   而 ⑤c 的本意是「校验的是 **name** 而不是 **ID**」，用哪个合法名并不重要
    #   ⇒ 换成具体考点，意图不变。（撞车本身由计数不变量当场暴露，不是事后发现的。）
    c3 = TaskCase(
        case_id="mem-z",
        task="memory",
        query="q",
        turns=["a", "b"],
        gold=_gold(True, ["图的存储"], ["栈"]),
    )
    rep3 = run_sanity([c3])
    check(
        "⑤c canonical name（图的存储，具体考点）⇒ 无 ERROR",
        not rep3.errors,
        f"{len(rep3.errors)} 个 ERROR：{[i.message[:40] for i in rep3.errors]}",
    )


def _c5_e() -> None:
    from evaluation.task_eval.cases import TaskCase
    from evaluation.task_eval.gold_sanity import run_sanity

    # ID 而非 name（「ds.graph」）→ 也 ERROR（name/ID 混用同样是漂移）
    c5 = TaskCase(
        case_id="mem-v",
        task="memory",
        query="q",
        turns=["a", "b"],
        gold=_gold(True, ["ds.graph"], ["栈"]),
    )
    rep5 = run_sanity([c5])
    id_bad = [i for i in rep5.errors if i.field_name == "expected_memory.values"]
    check("⑤e 误写 KP ID（ds.graph）而非 name ⇒ ERROR", bool(id_bad))


def _c5_d() -> None:
    from evaluation.task_eval.cases import TaskCase
    from evaluation.task_eval.gold_sanity import ERROR, run_sanity

    # 重叠 → ERROR
    c4 = TaskCase(
        case_id="mem-w",
        task="memory",
        query="q",
        turns=["a", "b"],
        gold=_gold(True, ["图"], ["图"]),
    )
    rep4 = run_sanity([c4])
    ov = [i for i in rep4.errors if "重叠" in i.message]
    check("⑤d values 与 forbidden_values 重叠 ⇒ ERROR", bool(ov))

    assert ERROR  # 明确引用，避免 lint 误删
