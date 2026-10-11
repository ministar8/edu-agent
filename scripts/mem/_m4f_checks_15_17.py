"""memory_step4fix_gate 判据组：⑮⑯⑰

从原单文件 `memory_step4fix_gate.py` 按判据边界原样搬出，逻辑一字未改。
"""

from __future__ import annotations

import ast
import asyncio

from _m4f_core import ROOT, check, section


def check_15() -> None:
    """⑮ D3（死代码删除）+ D4（record 落 `prompt_set_version`）的落地锁，零 LLM。"""
    section("⑮ 死代码已删净 / record 落提示词版本（D3 + D4）")
    _c15_dead()
    _c15_sqlite()
    _c15_prompt_ver(_c15_record())


def check_16() -> None:
    """⑯ 检索侧「可离线重算」快照（Step 9 前置，2026-10-07）。

    动机是两条实测取证的洞：
      ① 归档只有**结果布尔**（`category_hit`/`kp_hit`/`exam_hit`），没存 top-k 每条命中文档的
         类目/KP/来源 ⇒ 修好指标也无法离线重算老数字（#10 那 8 条因此被判「只能重跑」）。
      ② 也没存**配置**：`phase1_baseline_v2.log` 里有「重排已按部署开关关闭」的 WARNING，
         说明那次是「请求重排但没生效」；可没有 log 的 run（Step 5 两份就没有）无从取证。
    ⇒ 现在 `run_case` 落 `retrieval_cfg` + `top_items`。本节用**零 LLM** 的真实路径
    （`run_agent=False`）证明：字段真被填了，且**只用落盘字段就能重算出同一个指标值**。
    ★ 判据边界：重算用的是归档里的**数据**（类目/角色/来源/KP），但 `is_exam` 的**角色白名单**
      仍取自 `retrieval_probe._EXAM_ROLES`（语义常量）。 ⇒ 本节证明的是「输入齐备、可复算」，
      不是「重新发明真题判定」。
    """
    section("⑯ 检索配置与 top-k 落盘 ⇒ 检索侧指标可离线重算")
    _c16_check(*_c16_snapshot())


def check_17() -> None:
    """⑰ 逐轮执行日志 `turn_log`（2026-10-07 Step 9 补的 harness 洞）。

    起因是 Step 9 实跑出来的一个**无法归因**的现象：
        Store ON  三条正样本各只捕获 1 次批改 ⇒ 全部 `case_invalid`
        Store OFF 同三条各捕获 2 次批改
    而 `_record_grade_score` 明确「`score=None` 也登记」⇒ 逻辑上只能是
    **「第 2 轮根本没调批改工具」**。可归档里 `reply` 只存**最后一段会话**、
    `session_replies` 只到**段**一级 ⇒ 这个结论**证不了**。
    ⇒ 补 `turn_log`：每轮一条 `{session, turn, input, reply, tools, grade_scores}`。

    本节的验证方式：用**注入式 stub agent** 驱动**真实**的 `run_sessions`
    （零 LLM、零网络），断言它真的按轮记账 —— 而不是去读源码字符串。
    """
    section("⑰ 逐轮日志 turn_log ⇒ case_invalid 能归因到具体哪一轮")
    _c17_checks(_c17_body())


def _c15_dead() -> None:

    import memory

    # ⑮a D3：`asearch_episodes` 真的从导出面消失了
    check(
        "⑮a memory 不再导出 asearch_episodes（死代码已删）", not hasattr(memory, "asearch_episodes")
    )

    # ⑮b D3：全仓**没有任何 import / 名字引用**（防「删了模块但某处还在 import」——那要到运行时才炸）。
    #   ★ 判据必须是 AST 而不是「文件文本里有没有这个词」：本护栏自己的说明文字就含这个词，
    #     用文本匹配会**扫到自己**（实测第一版就是这样红的）—— 那是同义反复式的假红灯。
    hits: list[str] = []
    for d in ("src", "scripts"):
        for f in (ROOT / d).rglob("*.py"):
            try:
                tree = ast.parse(f.read_text(encoding="utf-8"))
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if (
                    isinstance(node, ast.ImportFrom)
                    and node.module
                    and (
                        "vector_search" in node.module
                        or any(a.name == "asearch_episodes" for a in node.names)
                    )
                ):
                    hits.append(f"{f.relative_to(ROOT)}:import")
                elif isinstance(node, ast.Attribute) and node.attr == "asearch_episodes":
                    hits.append(f"{f.relative_to(ROOT)}:attr")
                elif isinstance(node, ast.Name) and node.id == "asearch_episodes":
                    hits.append(f"{f.relative_to(ROOT)}:name")
    check("⑮b AST 级：src/ 与 scripts/ 对 asearch_episodes 零引用", not hits, str(hits[:3]))


def _c15_sqlite() -> None:

    # ⑮c D3 的**边界**：向量开关本身仍被 sqlite.py 用着 ⇒ 删的只能是检索函数，不是配置
    sqlite_src = (ROOT / "src" / "memory" / "sqlite.py").read_text(encoding="utf-8")
    check(
        "⑮c MEMORY_STORE_VECTOR_ENABLED 仍被 sqlite.py 消费（没被顺手删成空配置）",
        "MEMORY_STORE_VECTOR_ENABLED" in sqlite_src,
    )


def _c15_record() -> None:

    # ⑮d D4：**真跑** `run_case(run_agent=False)`（只发检索探针、零 LLM）走真实落值路径
    import prompts as _prompts
    from evaluation.task_eval.cases import load_demo
    from evaluation.task_eval.runner import run_case

    case = load_demo("qa", limit=1)[0]
    rec = asyncio.run(run_case(case, run_agent=False))
    check(
        "⑮d 真实 record 带 prompt_set_version 且等于当前提示词 hash",
        rec.prompt_set_version == _prompts.PROMPT_SET_VERSION and rec.prompt_set_version != "",
        f"record={rec.prompt_set_version} 当前={_prompts.PROMPT_SET_VERSION}",
    )
    check(
        "⑮d' to_dict() 里必须看得到这个键（否则归档落不下去）",
        "prompt_set_version" in rec.to_dict(),
    )
    return case


def _c15_prompt_ver(case) -> None:
    import asyncio

    import prompts as _prompts
    from evaluation.task_eval.runner import run_case

    # ⑮e ★ 反向：换掉提示词版本 ⇒ 新 record 必须跟着变（证明它取的是**活值**，不是硬编码字符串。
    #   若当初写成 `record.prompt_set_version = "2f485d2d7ef7"`，⑮d 照样绿、这条必然红）
    orig = _prompts.PROMPT_SET_VERSION
    try:
        _prompts.PROMPT_SET_VERSION = "SENTINEL-FOR-REVERSE"
        rec2 = asyncio.run(run_case(case, run_agent=False))
        check(
            "⑮e 反向：改 PROMPT_SET_VERSION ⇒ 新 record 同步变化（取的是活值）",
            rec2.prompt_set_version == "SENTINEL-FOR-REVERSE",
            f"record={rec2.prompt_set_version}",
        )
    finally:
        _prompts.PROMPT_SET_VERSION = orig


def _c16_snapshot() -> None:

    import asyncio as _aio

    from core.settings import settings as _s
    from evaluation.task_eval.cases import load_demo
    from evaluation.task_eval.runner import run_case

    case = load_demo("grade", limit=1)[0]
    rec = _aio.run(run_case(case, run_agent=False))
    d = rec.to_dict()

    check(
        "⑯a retrieval_cfg 落盘，且 rerank_effective = 请求 ∧ 部署开关（不再只能靠 .log 取证）",
        set(d["retrieval_cfg"]) >= {"k", "use_rerank_requested", "rerank_effective"}
        and d["retrieval_cfg"]["rerank_effective"]
        == (d["retrieval_cfg"]["use_rerank_requested"] and bool(_s.RERANK_ENABLED)),
        str(d["retrieval_cfg"]),
    )
    check(
        "⑯b top_items 落盘每条命中的 类目/KP/doc_role/kb_depth/source（重算输入齐备）",
        bool(d["top_items"])
        and all(
            {"category", "kp", "doc_role", "kb_depth", "source"} <= set(i) for i in d["top_items"]
        ),
        f"{len(d['top_items'])} 条",
    )
    return d, case, rec


def _c16_check(d, case, rec) -> None:
    from evaluation.task_eval import metrics
    from evaluation.task_eval.retrieval_probe import _EXAM_ROLES

    k = d["retrieval_cfg"]["k"]
    items = d["top_items"]
    cats = [i["category"] for i in items]
    allkp = [x for i in items for x in i["kp"]]
    is_exam = [
        (
            i["kb_depth"] == "exams"
            or i["doc_role"] in _EXAM_ROLES
            or i["category"] == "exams"
            or "/exams/" in i["source"].replace("\\", "/").lower()
            or i["source"].replace("\\", "/").lower().startswith("exams/")
        )
        for i in items
    ]
    r_cat = metrics.category_hit(case.subject, cats)
    r_exam = metrics.exam_hit_at_k(is_exam, k)
    r_kp = metrics.kp_coverage(d["gold"].get("expected_kp"), allkp) if allkp else None
    check(
        "⑯c 只用归档字段重算 category/exam ⇒ 与存值一致（这才叫「可复算」）",
        r_cat == rec.category_hit and r_exam == rec.exam_hit,
        f"重算 cat={r_cat}/存={rec.category_hit} exam={r_exam}/存={rec.exam_hit}",
    )
    check(
        "⑯d 重算 kp_hit 与存值一致（无 KP 元数据时两侧都必须 N/A，不许一边 False 一边 None）",
        r_kp == rec.kp_hit,
        f"重算={r_kp} 存值={rec.kp_hit}",
    )
    # ★ 反向：把落盘的类目换成不相干值 ⇒ 重算必须**从 True 翻成 False**，
    #   证明 ⑯c 的相等不是「喂什么都得同一个值」的空转。
    #   （所以这里挑一条 `category_hit is True` 的 case 来验；挑不到就明确判红，不留后门）
    garbage = metrics.category_hit(case.subject, ["__不相干类目__"] * len(items))
    check(
        "⑯e 反向：类目换成不相干值 ⇒ 重算从 True 翻成 False（⑯c 确有依赖）",
        rec.category_hit is True and garbage is False,
        f"存值 cat={rec.category_hit} 不相干输入 cat={garbage}",
    )


def _c17_body() -> None:

    import lib.agent_behavior_smoke as smoke
    from langchain_core.messages import AIMessageChunk, ToolMessage

    from agents.grading_core import format_grading_for_chat
    from schema.grading import GradingResult

    _graded_text = format_grading_for_chat(
        GradingResult(score=40, feedback="概念混淆", is_wrong=True, error_analysis="漏了要点")
    )

    class _StubAgent:
        """最小可用替身：只实现 `astream`，事件形状与真 agent 一致。

        第 1 轮**调**批改工具（有 ToolMessage），第 2 轮**不调** —— 这正是 Step 9
        观察到的形态，用它检验日志能否区分两者。
        """

        store = None
        checkpointer = None

        def __init__(self) -> None:
            self._n = 0

        async def astream(self, _inp, *, config, stream_mode, subgraphs):  # noqa: ARG002
            self._n += 1
            if self._n == 1:
                yield (
                    ("supervisor",),
                    "messages",
                    (
                        ToolMessage(
                            # ★ 文本由**产品自己的渲染器**产出（不手打字符串）：
                            #   手打的形状与 `format_grading_for_chat` 的 `评分：X/100`
                            #   不一致时，正则抓不到分 ⇒ 护栏会红在「形状」上而不是「逻辑」上
                            #   （实测第一版就是这么红的：写了「得分：40/100」→ 抓到 None）。
                            content=_graded_text,
                            tool_call_id="c1",
                            name="grade_student_answer",
                        ),
                        {},
                    ),
                )
            yield (("supervisor",), "messages", (AIMessageChunk(content=f"回复{self._n}"), {}))

    agent = _StubAgent()
    import asyncio as _aio

    res = _aio.run(
        smoke.run_sessions(
            agent,
            [["帮我批改：题面……我答 X", "再批改一题：题面……我答 Y"], ["我最近哪里薄弱？"]],
            user_id="gate-turn-log-stub",
            cleanup_first=False,
            store_enabled=True,
        )
    )
    return res


def _c17_checks(res) -> None:

    tl = res.turn_log
    check(
        "⑰a 每轮各一条（3 轮 ⇒ 3 条，含 session/turn 下标）",
        len(tl) == 3 and [(x["session"], x["turn"]) for x in tl] == [(0, 0), (0, 1), (1, 0)],
        str([(x.get("session"), x.get("turn")) for x in tl]),
    )
    check(
        "⑰b 该轮的输入与回复都留痕（旧归档只有最后一段）",
        all(x.get("input") and x.get("reply") for x in tl),
        str([len(x.get("reply") or "") for x in tl]),
    )
    check(
        "⑰c ★ 能区分「调了工具」与「没调工具」：第 1 轮有 grade、第 2 轮 tools 为空",
        tl[0]["tools"] == ["grade_student_answer"]
        and tl[0]["grade_scores"] == [40.0]
        and tl[1]["tools"] == []
        and tl[1]["grade_scores"] == [],
        str([(x["tools"], x["grade_scores"]) for x in tl]),
    )
    check(
        "⑰d 与 grade_scores 总量一致（逐轮明细加总 == 全局计数，不许两套账）",
        sum(len(x["grade_scores"]) for x in tl) == len(res.grade_scores) == 1,
        f"逐轮加总={sum(len(x['grade_scores']) for x in tl)} 全局={len(res.grade_scores)}",
    )
