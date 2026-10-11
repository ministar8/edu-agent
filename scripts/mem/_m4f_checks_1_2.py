"""memory_step4fix_gate 判据组：① recalled 脱离 judge / ② run_case 接线 run_sessions

从原单文件 `memory_step4fix_gate.py` 按判据边界原样搬出，逻辑一字未改。
"""

from __future__ import annotations

import ast
import inspect
import textwrap
from dataclasses import dataclass

from _m4f_core import ROOT, check, section

# ── ① recalled 脱离 judge / 常量同源 ──────────────────────────


def check_1() -> None:
    _c1_harness()
    _c1_judge()


# ── ② run_case 接线 run_sessions ─────────────────────────────


def check_2() -> None:
    section("② run_case → run_sessions 接线")
    _c2_sig()
    _c2_branch()
    _c2_sessions()


def _c1_harness() -> None:
    section("① recalled 脱离 judge + ⑤ MEMORY_CARD_MESSAGE_ID 同源")

    import lib.agent_behavior_smoke as harness  # type: ignore[import-not-found]

    from agents.teaching_graph import MEMORY_CARD_MESSAGE_ID as product_id

    # ★ 判据必须用「**源码里没有硬编码赋值**」，不能只用 `is`（2026-10-06 修）。
    #   为什么 `is` 不够：`"edu_memory_card"` 是字符串字面量，CPython 会**驻留**它，
    #   于是**硬编码副本与产品常量仍是同一对象**（实测 `is` → True）。
    #   即 `is` 判定对「常量被改回硬编码」这一破坏**完全无效**（反向验证实测抓到）。
    #   真正可靠的判据是 AST：**本模块顶层不存在对 MEMORY_CARD_MESSAGE_ID 的赋值**。
    src = inspect.getsource(harness)
    tree = ast.parse(src)
    assigns = [
        n
        for n in tree.body
        if isinstance(n, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "MEMORY_CARD_MESSAGE_ID" for t in n.targets)
    ]
    check(
        "⑤a harness **源码中无硬编码赋值**（从产品导入，而非本地副本）",
        not assigns,
        "发现顶层赋值"
        if assigns
        else f"导入自 agents.teaching_graph，值={harness.MEMORY_CARD_MESSAGE_ID!r}",
    )
    check(
        "⑤a harness 常量与产品常量取值一致",
        harness.MEMORY_CARD_MESSAGE_ID == product_id,
    )


def _c1_judge() -> None:

    # judge 护栏：即便 judge 判 False，主指标字段也不被覆盖
    from dataclasses import field as _field

    from evaluation.task_eval.judge import JudgeOutput, apply_judge

    @dataclass
    class _Rec:
        task: str = "memory"
        final_quality: float | None = None
        failure_reason: list[str] = _field(default_factory=list)
        primary_failure: str = "none"
        judge: str = ""
        memory_retrieved: bool | None = True
        memory_used: bool | None = True
        memory_correct: bool | None = True

    rec = _Rec()
    out = JudgeOutput(
        final_quality=5, memory_retrieved=False, memory_used=False, memory_correct=False
    )
    apply_judge(rec, out)

    check(
        "①b judge 不再写主指标字段（保持 True 未被 False 覆盖）",
        (rec.memory_retrieved, rec.memory_used, rec.memory_correct) == (True, True, True),
    )
    check(
        "①c judge 原判落到 judge_memory_* 诊断字段",
        (
            getattr(rec, "judge_memory_retrieved", None),
            getattr(rec, "judge_memory_used", None),
            getattr(rec, "judge_memory_correct", None),
        )
        == (False, False, False),
    )


def _c2_sig() -> None:

    from evaluation.task_eval import runner

    sig = inspect.signature(runner._run_agent)
    check(
        "②a _run_agent 接受 task / case_id 参数",
        "task" in sig.parameters and "case_id" in sig.parameters,
        str(sig),
    )


def _c2_branch() -> None:

    # ★ 用 **AST 静态检查**判断分支，而不是猴补丁动态探测（2026-10-06 修）。
    #   动态探测的坑（本 Gate 反向验证实测抓到）：`_run_agent` 内部是
    #   `from lib.agent_behavior_smoke import run_sessions` —— **函数内局部导入**，
    #   替换模块属性拿不到（它每次从 sys.modules 取原函数）⇒ 猴补丁无效，
    #   检查恒绿 ⇒ 假阳性。AST 检查则直接证明「源码里存在
    #   `if task == "memory"` 且其分支内调用了 run_sessions」。
    # ★ 按事实修订（`runner.py` 重组后）：分派真身搬到 `_runner_agent._run_with_agent`
    #   （`runner._run_agent` 只剩 sys.path / checkpointer / store 的装配外壳），
    #   取证目标随之改 —— 断言原意（memory 分支调 run_sessions、其余走 run_turns）不变。
    from evaluation.task_eval._runner_agent import _run_with_agent

    src = inspect.getsource(_run_with_agent)
    tree = ast.parse(textwrap.dedent(src))

    def _calls_in(node: ast.AST, names: set[str]) -> bool:
        for sub in ast.walk(node):
            if isinstance(sub, ast.Call):
                f = sub.func
                if isinstance(f, ast.Name) and f.id in names:
                    return True
                if isinstance(f, ast.Attribute) and f.attr in names:
                    return True
        return False

    mem_call_ok = False
    # ★ 断言语义（2026-10-06 修）：`run_turns` 在 `async with` 末尾**裸调用**
    #   （不在任何 if 里），故不能只在「if 的非 memory 分支」里找它。
    #   正确的两条断言是：
    #     (a) 源码中确实出现了 run_turns 调用（其他任务有兜底路径）；
    #     (b) **memory 分支内不调 run_turns**（否则接线被绕过）。
    mem_branch_calls_turns = False
    mem_branch_calls_sessions = False
    for node in ast.walk(tree):
        if isinstance(node, ast.If):
            cond = ast.dump(node.test)
            if "memory" not in cond:
                continue
            if _calls_in(node, {"run_sessions"}):
                mem_branch_calls_sessions = True
            if _calls_in(node, {"run_turns"}):
                mem_branch_calls_turns = True

    mem_call_ok = mem_branch_calls_sessions
    any_turns = _calls_in(tree, {"run_turns"})

    check("②b 源码中 task=memory 分支确实调用 run_sessions", mem_call_ok)
    check("②c 其他任务仍有 run_turns 兜底路径", any_turns)
    check("②d memory 分支**不**走 run_turns（接线未被绕过）", not mem_branch_calls_turns)


def _c2_sessions() -> None:

    # ★ ②e/②f：`sessions` 真被接线到 `run_sessions`（2026-10-06 补，Step 4 收尾）。
    #   为什么必须单列这两项：②b 只证明「调了 run_sessions」，**不证明分组来自 case**。
    #   若第 2 位置参数仍是硬编码 `[[t] for t in turns]`，跨会话就静默退化成单 thread，
    #   而 ②b/②c/②d 全绿 —— 这类「绿着的假接线」正是本 Gate 要拦的。
    import ast as _ast

    src_full = (ROOT / "src" / "evaluation" / "task_eval" / "runner.py").read_text(encoding="utf-8")
    # ★ 按事实修订：`run_sessions` 的第 2 实参长在 `_runner_agent._run_with_agent`（重组后），
    #   `runner.py` 只留 `sessions=case.all_sessions ...` 的传参（②f 仍读它）。
    _dispatcher_src = (ROOT / "src" / "evaluation" / "task_eval" / "_runner_agent.py").read_text(
        encoding="utf-8"
    )
    tree_full = _ast.parse(_dispatcher_src)
    sess_arg_names: list[str] = []
    for node in _ast.walk(tree_full):
        if not isinstance(node, _ast.If) or "memory" not in _ast.dump(node.test):
            continue
        for sub in _ast.walk(node):
            if isinstance(sub, _ast.Call) and getattr(sub.func, "id", None) == "run_sessions":
                if len(sub.args) >= 2:
                    sess_arg_names.append(_ast.unparse(sub.args[1]))
    passed_sessions = any(
        a != "[[t] for t in turns]" and "[[t] for t in turns]" not in a for a in sess_arg_names
    ) and bool(sess_arg_names)
    check(
        "②e run_sessions 的会话分组**取自传入 sessions**（非硬编码 [[t] for t in turns]）",
        passed_sessions,
        f"第2位置参数 = {sess_arg_names}",
    )
    check(
        "②f run_case 用 `case.all_sessions` 驱动（解析处与执行处同源，避免分组逻辑漂移）",
        "case.all_sessions" in src_full,
    )
