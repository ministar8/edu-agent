"""memory_step4fix_gate 判据组：⑳㉑㉒㉓

从原单文件 `memory_step4fix_gate.py` 按判据边界原样搬出，逻辑一字未改。
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from _m4f_core import ROOT, check, section, skip


def check_20() -> None:
    """⑳ 校准报告的「非众数占比」露出（D6，登记为 §20.5 #19）。零 LLM。

    背景：`calibration_30.jsonl` 的人工分是 `{5:28, 0:1, 2:1}`，`spearman=0.7321`
    刚过 0.70 阈值 ⇒ PASS。破坏性检验显示：把那 2 条非众数行任一条改成 5 ⇒ 掉到 ~0.5（FAIL）；
    把那 2 条的 **judge 分改成 0**（judge 在唯一可判别处完全打错）⇒ **仍然 PASS**
    （秩相关只看排序）。⇒ 信息量只在 2/30 行上，必须让报告自己说出来。
    ★ 本项**不判成败、不动阈值**：只锁「露出存在且算对」，以及「分布正常时不许误报」（避免变成一刀切禁用）。
    """
    section("⑳ 校准 PASS 的秩相关信息量必须自己露出（D6 / #19）")
    _c20_rank()
    _c20_second()
    _c20_calib_file()


def check_21() -> None:
    """㉑ 预检要探到**推理端点**，写链断裂要标成**环境问题**（2026-10-07 实发事故）。

    事故过程（不是假想）：Step 9 跑完后 TEI 半死 —— `/health` 返 **200**，
    `/embeddings` 返 **502**；`memory.safe` 只打一行 WARNING「长期记忆写入超时（grade，>1.5s），
    已忽略」就**丢弃写入**。于是护栏 ⑩d' 报「EPISODES 落库 = 0 条」。
    真正的危险不是红灯，而是**绿灯时的假数字**：若这条发生在正式跑里，
    画像为空 ⇒ B 段召不回 ⇒ 会被写成「Memory 产品没召回」——
    而我们当天刚把同类现象归因给 #22 的 KP 阈值。**归因会被环境污染伪造。**
    ⇒ 两道闸：① 预检必须真发一次向量请求；② 「有批改但零 episode」标 env_error 并中止。
    """
    section("㉑ 预检探推理端点 / 写链断裂归环境类（防假归因）")
    old_base, old_fake = _c21_halfdead(_c21_setup())
    _c21_fake(old_base, old_fake)
    _c21_nohealth(old_base, old_fake)


def check_22() -> None:
    """㉒ paired control 的 OFF 臂必须真的关掉 Store（2026-10-07 D8 重跑暴露，登记为 #24）。

    事故：D8 把正样本改成「同考点两次低分」之后，**OFF 组也召回了**（`卡=1`、
    `recalled_actual=True`，而 harness 自己抓的 `episodes=0`）。查因：
    `teaching_graph.load_memory` 与 `remember._record_episode` 都在**调用时**取进程级
    `get_store()`，而 OFF 组原先只置 `agent.store = None` ⇒ Store 从未关闭，
    「ON 有卡 / OFF 无卡」的对照一直不成立。
    ★ 更糟的是：Step 5 当时 OFF 显示「0 卡 0 召回」被当成对照生效的证据，
      那其实是 #22（画像恒空）造成的假象 —— **两个缺陷互相掩盖**。
      D8 修好了 #22，才让 #24 露头。
    """
    section("㉒ OFF 组须真空白进程级 store（#24，防对照失效）")
    _c22_run(*_c22_setup())


def check_23() -> None:
    """㉓ 写入证据判据的**位置、归因与下游**（2026-10-08 review C1 / I1 / I3）。

    事故（C1）：`memory_write_missing` 的调用点原先落在 `if case.task == "memory"`
    **之外**。非 memory 任务走 `run_turns` —— 它照抓 `grade_scores`、却从不读 Store，
    `episodes` 恒空 ⇒ 任何一次 grade/verify/qa 实跑都会在**第一条**被判 `env_error`，
    而 `cli._run` 的 `break` 在 `append_record` **之前** ⇒ 整轮中止且那条记录连盘都不落，
    中止日志取 `hard_fails[0]`/`retrieval_error`（两者皆空）⇒ 屏幕上是一行没有原因的「中止」。
    ⇒ 这一组**必须驱动真实 `run_case`**（把 `_run_agent` 与检索探针打桩，零 LLM、零 TEI 依赖），
      只测纯函数的 ㉑ 抓不到它 —— 又是「测了 helper、没测接线」那一类。
    """
    section("㉓ 写入证据判据：位置 / 归因 / 下游排除（C1+I1+I3）")
    rec_m, rec_rf = _c23_a(_c23_setup())
    _c23_b(_c23_setup(), rec_m, rec_rf)


def _c20_rank() -> None:

    from evaluation.task_eval.judge import (
        CALIBRATION_THRESHOLDS,
        calibrate,
    )

    real_h = [5.0] * 28 + [0.0, 2.0]
    real_l = [5.0] * 26 + [4.0, 4.0, 0.0, 2.0]
    rep = calibrate(real_l, real_h)
    check(
        "⑳a 真实形状（28 个 5 + 2 条可判别）⇒ 报出非众数 2/30=6.7% 且标为秩退化",
        rep.informative_n == 2
        and abs((rep.informative_share or 0) - round(2 / 30, 4)) < 1e-9
        and rep.rank_degenerate is True
        and rep.human_mode == 5.0,
        f"n={rep.informative_n} share={rep.informative_share} mode={rep.human_mode} deg={rep.rank_degenerate}",
    )
    check(
        "⑳b 露出**不改变判定**：同一份表仍按原阈值给 PASS（阈值是预先约定的标准，不为好看调整）",
        rep.passed is True
        and rep.spearman is not None
        # ★ 引用阈值表本身，不写死 0.70（review M4）：阈值被调整时这条应该**跟着变**，
        #   而不是变成一条「恰好当时对的」的错断言。
        and rep.spearman >= CALIBRATION_THRESHOLDS["spearman_min"],
        f"spearman={rep.spearman} passed={rep.passed} "
        f"阈值={CALIBRATION_THRESHOLDS['spearman_min']}",
    )


def _c20_second() -> None:
    from evaluation.task_eval.judge import INFORMATIVE_SHARE_MIN, calibrate

    # ★ 反向：分布正常的表不许误报（否则这条露出会退化成「永远警告」= 没有信息）
    hum = [0, 1, 2, 3, 3, 4, 5, 5, 2, 3, 1, 4, 5, 3, 2, 4, 1, 0, 5, 3, 4, 2, 3, 5, 1, 4, 2, 3, 5, 4]
    llm = [0, 1, 2, 3, 4, 4, 5, 5, 2, 3, 1, 4, 5, 3, 2, 4, 2, 0, 5, 3, 4, 2, 3, 5, 1, 4, 2, 3, 5, 4]
    rep2 = calibrate([float(x) for x in llm], [float(x) for x in hum])
    check(
        f"⑳c 反向：分布正常（非众数 {rep2.informative_n}/30）⇒ 不误报退化",
        rep2.rank_degenerate is False and (rep2.informative_share or 0) >= INFORMATIVE_SHARE_MIN,
        f"share={rep2.informative_share} deg={rep2.rank_degenerate}",
    )


def _c20_calib_file() -> None:
    # ⑳d 真实文件本身必须被报告成退化（读的是仓内校准表，不调 LLM）
    import json as _json

    from evaluation.task_eval.judge import calibrate

    p = ROOT / "evals" / "datasets" / "demo" / "calibration_30.jsonl"
    if p.exists():
        rows = [
            _json.loads(ln)
            for ln in p.read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.startswith("#")
        ]
        pairs = [
            (float(r["llm_score"]), float(r["human_score"]))
            for r in rows
            if r.get("llm_score") is not None and r.get("human_score") is not None
        ]
        rep3 = calibrate([a for a, _ in pairs], [b for _, b in pairs])
        check(
            "⑳d 仓内真实校准表被报告为秩信息量不足（2/30）",
            rep3.rank_degenerate is True and rep3.informative_n == 2,
            f"n={len(pairs)} 非众数={rep3.informative_n} share={rep3.informative_share}",
        )
    else:
        skip("⑳d", "calibration_30.jsonl 不在本机 ⇒ 真实校准表的秩信息量未验证", count=1)


def _c22_setup() -> None:

    import lib.agent_behavior_smoke as smoke
    from langchain_core.messages import AIMessageChunk

    from memory.runtime import get_store

    class _SpyAgent:
        """在轮内观测 `get_store()` —— 这才是「变量到底有没有被控制」的直接证据。"""

        checkpointer = None

        def __init__(self, store) -> None:
            self.store = store
            self.seen: list[bool] = []

        async def astream(self, _inp, *, config, stream_mode, subgraphs):  # noqa: ARG002
            self.seen.append(get_store() is not None)
            yield (("supervisor",), "messages", (AIMessageChunk(content="回复"), {}))

    class _NullStore:
        """只为让 `store is not None` 成立的最小对象（OFF 臂要摘的就是它）。"""

        async def asearch(self, ns, query=None, filter=None, limit=None, offset=0):  # noqa: A002
            return []

        async def adelete(self, ns, key) -> None:
            return None

    async def _run(store_enabled: bool) -> tuple[smoke.CaseResult, bool | None]:
        # ★ 原先注解成 `tuple[_SpyAgent, bool]` —— 实际返回的是 `(CaseResult, observed)`，
        #   而 `pyrefly` 的 `project-includes` 只含 `src/`（`pyproject.toml`），scripts 从不被
        #   检查 ⇒ 这类真错一直静默存在（review I7）。
        spy = _SpyAgent(_NullStore())
        res = await smoke.run_sessions(
            spy,
            [["批改：题一"], ["换个会话：我哪里薄弱？"]],
            user_id=f"gate-off-arm-{store_enabled}",
            cleanup_first=False,
            store_enabled=store_enabled,
        )
        # 轮内观测：True = 那一轮 `get_store()` 有值（Store 开着）
        observed = spy.seen[0] if spy.seen else None
        return res, observed

    return _SpyAgent, _NullStore, _run


def _c22_run(_SpyAgent, _NullStore, _run) -> None:
    import asyncio as _aio

    from memory.runtime import get_store, set_store

    sentinel = _NullStore()
    old = get_store()
    try:
        set_store(sentinel)
        _res_on, obs_on = _aio.run(_run(True))
        check(
            "㉒a ON 臂：轮内 `get_store()` 有值（对照的前提：这一臂确实开着 Store）",
            obs_on is True,
            f"observed={obs_on}",
        )
        _res_off, obs_off = _aio.run(_run(False))
        check(
            "㉒b ★ OFF 臂：轮内 `get_store()` 必须为 None（旧实现只摘 agent.store ⇒ 这里会是 True）",
            obs_off is False,
            f"observed={obs_off}",
        )
        check(
            "㉒c OFF 臂跑完后进程级 store 已恢复（忘恢复会让后续所有 case 静默失去记忆）",
            get_store() is sentinel,
            f"get_store() is sentinel = {get_store() is sentinel}",
        )
        # ★ 原先这里还有一条「㉒d OFF 臂的 notes 里写明摘除方式」的判据，2026-10-08 删掉：
        #   它检查的是 harness 自己写的** note 文本**，突变实验（把 OFF 臂换成什么都不做）时
        #   它照样绿、而措辞一改就假红 —— 那是文档不是护栏（与本组 ⑦b/⑦c 从文本断言
        #   改成行为断言是同一条理由）。note 本身继续留在 harness 里，报告照常能读。
    finally:
        set_store(old)
    check(
        "㉒e 护栏自身不污染进程（跑完 store 回到入口前的状态）",
        get_store() is old,
    )


def _c21_setup() -> None:

    from http.server import BaseHTTPRequestHandler

    class _HalfDead(BaseHTTPRequestHandler):
        """复刻事故：健康检查说活着，推理端点 502。"""

        def do_GET(self):  # noqa: N802
            self.send_response(200 if self.path.startswith("/health") else 404)
            self.end_headers()
            self.wfile.write(b"ok")

        def do_POST(self):  # noqa: N802
            self.send_response(502)
            self.end_headers()
            self.wfile.write(b"gateway unavailable")

        def log_message(self, *_a):
            pass

    return _HalfDead


def _c21_halfdead(_HalfDead) -> None:
    import threading
    from http.server import HTTPServer

    from core.settings import settings as _s
    from evaluation.task_eval.runner import preflight_check

    srv = HTTPServer(("127.0.0.1", 0), _HalfDead)
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    old_base, old_fake = _s.EMBEDDING_API_BASE, _s.USE_FAKE_EMBEDDING
    try:
        _s.EMBEDDING_API_BASE = f"http://127.0.0.1:{port}"
        _s.USE_FAKE_EMBEDDING = False
        probs = preflight_check()
        check(
            "㉑a ★ /health 200 但 /embeddings 502 时，预检必须报问题（旧预检会放行的正是这种）",
            any("推理" in p for p in probs),
            f"problems={[p[:70] for p in probs]}",
        )
        _s.EMBEDDING_API_BASE = "http://127.0.0.1:1"  # 端口都没开
        probs2 = preflight_check()
        # ★ 双向断言（review I5）：只写 `len(probs2) >= 1` 的话，把 health 那一支删掉、
        #   推理支单独报一条也照样绿 —— 标题说的「两条路径不互相掩盖」根本没被检查。
        check(
            "㉑b 服务完全不可达时**两条**抱怨都在（health 支与推理支不互相掩盖）",
            any("不可达" in p for p in probs2) and any("推理" in p for p in probs2),
            f"{[p[:50] for p in probs2]}",
        )
    finally:
        _s.EMBEDDING_API_BASE, _s.USE_FAKE_EMBEDDING = old_base, old_fake
        srv.shutdown()
        srv.server_close()  # 释放监听套接字（review M9：只 shutdown 会把 socket 留到进程结束）
    return old_base, old_fake


def _c21_fake(old_base, old_fake) -> None:
    from core.settings import settings as _s
    from evaluation.task_eval.runner import memory_write_missing, preflight_check

    # 假嵌入模式（CI/单测）：base 指向死端口也应放行 —— 证明它没有"顺手多探一发"把 CI 打死
    # ★ 这一支原先在上面的 `finally` **之后**改 settings 却只还原 `USE_FAKE_EMBEDDING`
    #   ⇒ 跑完 `EMBEDDING_API_BASE` 停在 `127.0.0.1:1`，同一进程里后面的任何 embedding
    #   调用都会 ConnectTimeout（review I4）。今天没炸只是因为 ㉑ 后面只剩 ㉒（不碰 embedding）——
    #   护栏自己污染进程，正是它自己在 ㉒e 立的标准要拦的事。
    _s.USE_FAKE_EMBEDDING = True
    _s.EMBEDDING_API_BASE = "http://127.0.0.1:1"
    try:
        fake_probs = preflight_check()
    finally:
        base_seen_inside = _s.EMBEDDING_API_BASE
        _s.EMBEDDING_API_BASE, _s.USE_FAKE_EMBEDDING = old_base, old_fake
    check(
        "㉑c 假嵌入模式（CI/单测）下预检放行，即使 base 指向死端口",
        fake_probs == [],
        str([p[:50] for p in fake_probs]),
    )
    check(
        "㉑c' 跑完 settings 已还原（护栏不得把死端口留给后续检查）",
        base_seen_inside == "http://127.0.0.1:1"
        and _s.EMBEDDING_API_BASE == old_base
        and _s.USE_FAKE_EMBEDDING == old_fake,
        f"还原后 base={_s.EMBEDDING_API_BASE!r} fake={_s.USE_FAKE_EMBEDDING!r}",
    )

    # 写入证据判据的分支（纯函数，含「不该报」的两侧，防它退化成永远报警）
    check(
        "㉑d 有批改 + Store 开着 + 零 episode + 读链没坏 ⇒ 判「写入证据缺失」（唯一该报的组合）",
        memory_write_missing(store_enabled=True, grade_calls=2, episodes=[]) is True,
    )
    check(
        "㉑e 反向三例不报警：有 episode / OFF 组 / 压根没批改",
        memory_write_missing(
            store_enabled=True, grade_calls=2, episodes=[{"knowledge_points": ["x"]}]
        )
        is False
        and memory_write_missing(store_enabled=False, grade_calls=2, episodes=[]) is False
        and memory_write_missing(store_enabled=True, grade_calls=0, episodes=[]) is False,
    )
    # ★ review I3：取证**读**失败不能推断成**写**失败（`episodes==[]` 这时只表示没读到）
    check(
        "㉑f 读链自己抛过错 ⇒ 不做写入推断（反向：删掉 `read_failed` 短路这条必红）",
        memory_write_missing(store_enabled=True, grade_calls=2, episodes=[], read_failed=True)
        is False,
    )
    # ★ review I2：判据本身**不指认原因** —— 缺陷 C（record_grade 接线断）与 TEI 挂掉
    #   症状相同，而 `memory/safe.py` 只留 WARNING ⇒ 只能报「证据缺失」。用返回值形状检查：
    #   函数返回 bool（不是 "env"/"product" 之类的伪归因），归因由 preflight 与 is_env_error 做。
    check(
        "㉑g 判据只回布尔、不替原因下结论（环境类归 preflight / is_env_error）",
        isinstance(memory_write_missing(store_enabled=True, grade_calls=2, episodes=[]), bool)
        and "环境" not in (memory_write_missing.__doc__ or "").split("\n\n")[0],
        (memory_write_missing.__doc__ or "").splitlines()[0][:60],
    )


def _c21_nohealth(old_base, old_fake) -> None:
    # ★ review M7：有些 OpenAI 兼容服务**没有 `/health` 路由**（404），但 `/embeddings` 完全正常。
    #   旧预检会因为一句 HTTP 404 就 return 3 拒绝开跑 —— 那是**假红**，会把能用的 TEI 拦在门外。
    #   ⇒ 健康检查的抱怨只在推理也失败时才允许一起进 problems。
    import json as _json4h
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    from core.settings import settings as _s
    from evaluation.task_eval.runner import preflight_check

    class _NoHealth(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            self.send_response(404)  # 没有 /health 这个路由
            self.end_headers()
            self.wfile.write(b"not found")

        def do_POST(self):  # noqa: N802
            length = int(self.headers.get("Content-Length") or 0)
            self.rfile.read(length)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(
                _json4h.dumps(
                    {"data": [{"object": "embedding", "index": 0, "embedding": [0.01] * 16}]}
                ).encode("utf-8")
            )

        def log_message(self, *_a):
            pass

    srv2 = HTTPServer(("127.0.0.1", 0), _NoHealth)
    port2 = srv2.server_address[1]
    threading.Thread(target=srv2.serve_forever, daemon=True).start()
    try:
        _s.EMBEDDING_API_BASE = f"http://127.0.0.1:{port2}"
        _s.USE_FAKE_EMBEDDING = False
        probs3 = preflight_check()
    finally:
        _s.EMBEDDING_API_BASE, _s.USE_FAKE_EMBEDDING = old_base, old_fake
        srv2.shutdown()
        srv2.server_close()
    check(
        "㉑h 没有 /health 路由（404）但推理可用 ⇒ 预检必须放行（否则是假红）",
        probs3 == [],
        str([p[:60] for p in probs3]),
    )


def _c23_setup() -> None:

    from dataclasses import field

    import evaluation.task_eval.runner as R
    from evaluation.task_eval.cases import load_demo

    @dataclass
    class _Res:
        reply: str = "批改完成：评分 0/100。错因：概念混淆。"
        hard_fails: list[str] = field(default_factory=list)
        tool_payloads: list[dict] = field(default_factory=list)
        memory_cards: list[str] = field(default_factory=list)
        grade_scores: list[dict] = field(default_factory=list)
        turn_log: list[dict] = field(default_factory=list)
        episodes: list[dict] = field(default_factory=list)
        episodes_read_failed: bool = False

    class _Probe:
        """检索探针桩：这一组不能依赖 TEI（gate 必须可在无服务时给出同一结论）。"""

        ok = True
        status = "ok"
        pack_len = 120
        evidence_count = 2
        error = ""

        def top_k(self, k: int):  # noqa: ARG002
            return []

    async def _fake_probe(*_a, **_kw):
        return _Probe()

    def _drive(
        task: str,
        *,
        grade_scores: list[dict],
        episodes: list[dict],
        read_failed: bool = False,
        store_enabled: bool = True,
        hard_fails: list[str] | None = None,
    ):
        async def _fake_agent(_turns, **_kw):
            return _Res(
                grade_scores=list(grade_scores),
                episodes=list(episodes),
                episodes_read_failed=read_failed,
                hard_fails=list(hard_fails or []),
            )

        old_agent, old_probe = R._run_agent, R.probe_retrieval
        R._run_agent, R.probe_retrieval = _fake_agent, _fake_probe
        try:
            case = load_demo(task, limit=1)[0]
            return case, asyncio.run(R.run_case(case, store_enabled=store_enabled))
        finally:
            R._run_agent, R.probe_retrieval = old_agent, old_probe

    return _drive


def _c23_a(_drive) -> None:

    gs2 = [{"session": 0, "score": 0.0}, {"session": 0, "score": 0.0}]
    eps = [
        {"topic": "平衡二叉树", "score": 0.0, "knowledge_points": ["平衡二叉树"], "type": "grade"}
    ]

    # ① C1 的正解：grade 任务**不该**被写入证据判据碰到
    _c, rec_g = _drive("grade", grade_scores=[{"session": 0, "score": 62.0}], episodes=[])
    check(
        "㉓a ★ grade case（有批改分、episodes 恒空）不被判写入证据缺失、不中止整轮",
        rec_g.env_error is False and rec_g.memory_write_missing is False,
        f"env_error={rec_g.env_error} write_missing={rec_g.memory_write_missing} "
        f"primary={rec_g.primary_failure}",
    )

    # ② memory 命中时：报「证据缺失」，但**不指认环境**（I2）
    _c, rec_m = _drive("memory", grade_scores=gs2, episodes=[])
    check(
        "㉓b memory + 两次低分批改 + 零 episode ⇒ 判证据缺失、validity 置 False、标 case_invalid",
        rec_m.memory_write_missing is True
        and rec_m.validity_valid is False
        and "case_invalid" in rec_m.failure_reason,
        f"missing={rec_m.memory_write_missing} valid={rec_m.validity_valid} "
        f"reason={rec_m.validity_reason[:56]!r}",
    )
    check(
        "㉓c 理由文本只说「证据缺失」，**不**替环境/产品定罪（缺陷 C 与 TEI 挂症状相同）",
        "环境" not in rec_m.validity_reason and rec_m.env_error is False,
        rec_m.validity_reason[:70],
    )

    # ③ 反向三例：读到了 episode / 读链自己坏了 / OFF 臂 —— 都不该报
    _c, rec_ok = _drive("memory", grade_scores=gs2, episodes=eps)
    _c, rec_rf = _drive("memory", grade_scores=gs2, episodes=[], read_failed=True)
    _c, rec_off = _drive("memory", grade_scores=gs2, episodes=[], store_enabled=False)
    check(
        "㉓d 反向三例不报：有 episode / `episodes_read_failed` / OFF 臂（I3 + 不误伤对照）",
        rec_ok.memory_write_missing is False
        and rec_ok.validity_valid is True
        and rec_rf.memory_write_missing is False
        and rec_off.memory_write_missing is False,
        f"ok={rec_ok.memory_write_missing}/{rec_ok.validity_valid} "
        f"read_failed={rec_rf.memory_write_missing} off={rec_off.memory_write_missing}",
    )
    return rec_m, rec_rf


def _c23_b(_drive, rec_m, rec_rf) -> None:
    import lib.memory_step5_paired as paired

    from evaluation.task_eval.report import summarize_task

    check(
        "㉓d' 读链失败要**单独留痕**（否则归档里 `episodes=[]` 又会被误读成没写入）",
        rec_rf.episodes_read_failed is True and rec_rf.memory_write_missing is False,
        f"read_failed={rec_rf.episodes_read_failed}",
    )

    # ④ 下游读者必须真的把它排除（I1：以前只有 cli 一条路认它）
    d = rec_m.to_dict()
    rep = summarize_task("memory", [d])
    check(
        "㉓e `report.summarize_task` 把该样本从分母剔除（failure_rate=None 而非 0 或 1）",
        rep.invalid_n == 1 and rep.failure_rate is None,
        f"invalid_n={rep.invalid_n} failure_rate={rep.failure_rate}",
    )

    arm = paired.ArmSummary(store_enabled=True, records=[d])
    check(
        "㉓f 配对脚本 `ArmSummary` 同样剔除（n_valid=0 / n_case_invalid=1）——"
        "★ 这条才是「不进指标」的真正落点，产出 Memory 数字的是它而不是 cli",
        arm.n_valid == 0 and arm.n_case_invalid == 1,
        f"n={arm.n} n_valid={arm.n_valid} invalid={arm.n_case_invalid}",
    )

    # ⑤ 真实环境信号仍要开火（别把 C1 的修复做成「整条闸都拆了」）
    #   ★ 用 `_ENV_ERROR_MARKERS` 里**真实登记**的文案（DashScope 欠费 `Arrearage`），
    #     而不是随手编一句英文 —— 否则这条测的是白名单里恰好有的词，不是判据本身。
    _c, rec_env = _drive(
        "grade",
        grade_scores=[{"session": 0, "score": 62.0}],
        episodes=[],
        hard_fails=["400 Arrearage: your account is in arrears, please top up (overdue-payment)"],
    )
    check(
        "㉓g 反向：真实环境报错仍判 env_error（没被误修成「照常计分」）",
        rec_env.env_error is True,
        f"env_error={rec_env.env_error} failure={rec_env.failure_reason}",
    )
    check(
        "㉓h 中止日志取得到文案（`hard_fails` 或 `retrieval_error` 至少一个非空）",
        bool(rec_env.hard_fails) or bool(rec_env.retrieval_error),
        f"hard_fails={rec_env.hard_fails!r} retrieval_error={rec_env.retrieval_error!r}",
    )

    # ⑥ 取证字段必须真的落进归档（老归档缺键按空处理，不回填）
    keys = set(rec_m.to_dict())
    check(
        "㉓i record 自带 `memory_write_missing` / `episodes_read_failed` 两个标志位",
        {"memory_write_missing", "episodes_read_failed"} <= keys,
        f"缺失={sorted({'memory_write_missing', 'episodes_read_failed'} - keys)}",
    )
