"""Step 4 收尾 · 五项缺口修复的机械 Gate（**不跑 agent、零 LLM 成本**）。

验证 2026-10-06 定稿的五项修复**已实现且行为正确**：

    P0  ① `recalled` 脱离 judge —— 改由 harness 从记忆卡机械判定
    P0  ② `run_case` 真正接线 `run_sessions`（memory 任务走跨会话）
    P0  ③ Memory gold 两字段（expected_memory / expected_answer_property）
    P1  ④ checkpointer 跑后清理（finally）
    P1  ⑤ `MEMORY_CARD_MESSAGE_ID` 从产品导入（不再硬编码）

判据（全部可机械判定）：
    ①a harness 的 `MEMORY_CARD_MESSAGE_ID` **就是** 产品的同一对象（`is`）
    ①b `judge.apply_judge` 不再写 `memory_retrieved/used/correct`（护栏生效）
    ①c judge 的原判落到 `judge_memory_*` 诊断字段（可对照）
    ②a `runner._run_agent` 的签名接受 task/case_id
    ②b `task="memory"` 时确实调 `run_sessions`（猴补丁探测）
    ②c `task="qa"` 时仍走 `run_turns`（不误伤其他任务）
    ③a 合法 gold ⇒ 四问：recalled_pass / used / correct / N/A
    ③b **负样本**（should_be_recalled=false）实际未召回 ⇒ recalled_pass=True
    ③c gold 缺失 ⇒ 三项全 None（记 N/A，不退回 judge）
    ④a `_cleanup_threads` 存在且能删掉真实 thread
    ④b `run_sessions` 的清理在 `finally` 里（异常也清）
    ⑤a `gold_sanity` 对 memory 缺失 gold 报 ERROR
    ⑤b `gold_sanity` 对**非 canonical** 的 values 报 ERROR

Step 5 真跑暴露的 4 个产品缺陷，已各自的回归护栏（2026-10-06 追加）：

    ⑧ knowledge_points 示例名必须 canonical（缺陷 B）
    ⑨ 批改链路抗格式飘移（缺陷 A：feedback 截断 + 标记清洗 + 重试）
    ⑩ context-fallback（缺陷 C：工具拿不到 config ⇒ record_grade 被静默跳过）
    ⑪ `normalize_topic` 不得改坏 canonical name（缺陷 D）
    ⑫ `GRADE_PROMPT` 的词表与 `kp_index` 同源（缺陷 E · 方案 A，2026-10-07 E-4 追加）
    ⑬ 重判归因保全 / jsonl 尾换行 / 负样本前置条件（2026-10-07 review B 组）
    ㉓ 写入证据判据的位置 / 归因 / 下游（2026-10-08 review C1+I1+I3）

**判据数量本身也是判据**（2026-10-08 review I6）：`_EXPECTED_ITEMS` 声明总数，收尾比对实际
执行数（含 `skip()` 登记的「未执行」项）。少一项（某组提前 return、抛错被吞、改了没同步常量）
⇒ 退出码 1；有 `⏭ 未执行` ⇒ 同样不算「全绿」。背景：`⑬l/⑭d~f/⑱a~b/⑳d` 这 8 项读的是
`evals/results/task_eval/*.jsonl`，而按 D11 那些归档**不入库** ⇒ 干净克隆上它们会静默消失、
`main()` 却照样绿 —— 「175 项全绿」这句话在别的机器上其实只是「167 项跑过」。

用法::

    PYTHONPATH=src .venv/Scripts/python scripts/memory_step4fix_gate.py
"""

from __future__ import annotations

import ast
import asyncio
import inspect
import json
import sys
import textwrap
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

_ok_all = True
_n_pass = 0
_n_fail = 0
_n_skip = 0

# ★ 判据总数必须**声明**出来（2026-10-08 review I6）。
#   背景：`⑬l×2 / ⑭d~⑭f / ⑱a~⑱b / ⑳d` 这 8 项读的是 `evals/results/task_eval/*.jsonl`，
#   而按 D11 的裁决那些归档**不入库** ⇒ 干净克隆上它们会静默消失，`main()` 照样打印
#   「GATE 通过 · exit 0」。于是文档与标签里那句「175 项全绿」在别的机器上其实是
#   「167 项跑过 + 8 项压根没跑」，两者根本不等价（这是「护栏全绿而它描述的路径不可达」
#   那一类的镜像：**绿灯的数量本身不可信**）。
#   ⇒ 加两个不变量：① 执行数（含跳过）必须等于本常量；② 跳过数必须为 0。
#      少跑一项、或某组提前 `return`，都在这里变红，而不是安静地少几行。
#   ★ 改判据时同步更新这个数（改完跑一次，末行会印实际值）。
_EXPECTED_ITEMS = 194


def check(label: str, passed: bool, detail: str = "") -> None:
    global _ok_all, _n_pass, _n_fail
    mark = "✅" if passed else "❌"
    if not passed:
        _ok_all = False
        _n_fail += 1
    else:
        _n_pass += 1
    print(f"  {mark} {label}" + (f"  — {detail}" if detail else ""))


def skip(label: str, reason: str, count: int = 1) -> None:
    """显式登记「这一项**没跑**」—— 计数、并在收尾时把绿灯降级成红灯。

    ★ 与 `check(..., True)` 的区别：跳过**不是**通过。旧写法只 `print` 一行 `⏭`，
      不进任何计数 ⇒ 总数悄悄变小而退出码仍为 0（正是 I6）。
    `count`：一个 `if` 挡掉多项判据时用它（如 ⑭d~⑭f = 3 项）。
    """
    global _n_skip
    _n_skip += count
    print(f"  ⏭ {label} ×{count}：{reason}")


def _flag(message: str) -> None:
    """收尾阶段的失败判据（不参与计数：计数本身正是它检查的对象）。"""
    global _ok_all
    _ok_all = False
    print(f"  ❌ {message}")


def section(title: str) -> None:
    print()
    print("=" * 72)
    print(title)
    print("=" * 72)


# ── ① recalled 脱离 judge / 常量同源 ──────────────────────────


def check_1() -> None:
    section("① recalled 脱离 judge + ⑤ MEMORY_CARD_MESSAGE_ID 同源")

    import agent_behavior_smoke as harness  # type: ignore[import-not-found]

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


# ── ② run_case 接线 run_sessions ─────────────────────────────


def check_2() -> None:
    section("② run_case → run_sessions 接线")

    from evaluation.task_eval import runner

    sig = inspect.signature(runner._run_agent)
    check(
        "②a _run_agent 接受 task / case_id 参数",
        "task" in sig.parameters and "case_id" in sig.parameters,
        str(sig),
    )

    # ★ 用 **AST 静态检查**判断分支，而不是猴补丁动态探测（2026-10-06 修）。
    #   动态探测的坑（本 Gate 反向验证实测抓到）：`_run_agent` 内部是
    #   `from agent_behavior_smoke import run_sessions` —— **函数内局部导入**，
    #   替换模块属性拿不到（它每次从 sys.modules 取原函数）⇒ 猴补丁无效，
    #   检查恒绿 ⇒ 假阳性。AST 检查则直接证明「源码里存在
    #   `if task == "memory"` 且其分支内调用了 run_sessions」。
    src = inspect.getsource(runner._run_agent)
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

    # ★ ②e/②f：`sessions` 真被接线到 `run_sessions`（2026-10-06 补，Step 4 收尾）。
    #   为什么必须单列这两项：②b 只证明「调了 run_sessions」，**不证明分组来自 case**。
    #   若第 2 位置参数仍是硬编码 `[[t] for t in turns]`，跨会话就静默退化成单 thread，
    #   而 ②b/②c/②d 全绿 —— 这类「绿着的假接线」正是本 Gate 要拦的。
    import ast as _ast

    src_full = (ROOT / "src" / "evaluation" / "task_eval" / "runner.py").read_text(encoding="utf-8")
    tree_full = _ast.parse(src_full)
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


# ── ③ 机械 scorer ────────────────────────────────────────────


def _gold(should: bool, vals: list[str], forb: list[str]):
    from evaluation.task_eval.cases import Gold

    return Gold.from_dict(
        {
            "expected_memory": {
                "type": "weak_topics",
                "values": vals,
                "should_be_recalled": should,
            },
            "expected_answer_property": {"forbidden_values": forb},
            # ★ setup_conditions 自 2026-10-06 Step 5 起为**必填**（case-validity），
            #   故 gate 的 fixture 也必须带上，否则 ⑤c 会被 setup_conditions 的 ERROR 干扰。
            "setup_conditions": {"min_grade_calls": 2},
        }
    )


def check_3() -> None:
    section("③ Memory 三项机械判定（scorer）")

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

    # ③j+ ★ 全体扫描（2026-10-07 补）：`cn` 这类漏洞的本质是「数据集里出现的学科码，
    #   映射表不认得」—— 单点断言防不住**下一个**新码。故扫遍 `evals/datasets/` 全部
    #   jsonl，取出实际出现过的学科码，逐个要求：① 能在 `SUBJECT_TO_CATEGORY` 里查到
    #   （查不到 = 该 case 的 `category_hit` 会静默变 N/A，等于悄悄减少样本）；
    #   ② 用映射到的真实类目自测必须 True（自测 False = 恒不命中，正是 `cn` 的老 bug）。
    import json as _json

    from evaluation.retrieval_gate import SUBJECT_TO_CATEGORY
    from evaluation.task_eval.metrics import _SUBJECT_ALIASES

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

    # ── ③o~③r `verdict_agreement`（#7 的合法替代指标，2026-10-07）──
    from evaluation.task_eval import metrics
    from evaluation.task_eval.metrics import WRONG_SCORE_LINE, verdict_agreement

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

    # ③u API 批改端点必须把 knowledge_points 透传给 record_grade
    #   ★ 这是**静态**检查（执行它要完整 app + DB）；"执行式"的端到端验证在
    #     `scripts/memory_e2e_fallback_probe.py`（注入假 LLM 驱动真实 `call_structured`）。
    #   用 AST 定位调用节点的 keywords，**不是搜源码子串** —— 注释里提一句该参数
    #   就能骗过子串搜索（⑨f 的教训）。
    import ast
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


# ── ④ checkpointer 跑后清理 ──────────────────────────────────


def check_4() -> None:
    section("④ checkpointer 跑后清理")

    import agent_behavior_smoke as harness  # type: ignore[import-not-found]

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
    from agent_behavior_smoke import _cleanup_threads  # type: ignore[import-not-found]

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

    from evaluation.task_eval.cases import TaskCase
    from evaluation.task_eval.gold_sanity import ERROR, run_sanity

    # 缺失 gold → ERROR
    c = TaskCase(case_id="mem-x", task="memory", query="q", turns=["a", "b"])
    rep = run_sanity([c])
    fields = {i.field_name for i in rep.errors}
    check(
        "⑤a gold 缺失 ⇒ ERROR（expected_memory + expected_answer_property）",
        {"expected_memory", "expected_answer_property"} <= fields,
        str(sorted(fields)),
    )

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

    import agent_behavior_smoke as harness  # type: ignore[import-not-found]

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
    import agent_behavior_smoke as _smoke

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
    import json
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


def check_9() -> None:
    """⑨ 批改链路抗格式飘移（2026-10-06 Step 5 实测缺陷 A 的回归护栏）。

    实测缺陷：模型在 function_calling 下偶发返回裸文本/带工具标记的文本，
    此前因 `feedback` 超 `max_length` 直接 `ValidationError` ⇒ 整次批改硬失败
    （修复前 ON 组 **5/9 = 55.6%**；分母 = A 段**预期**批改次数，失败含「分数不可解析」与
    「完全无落分记录」两种形态。旧记「62.5% = 5/8」的分母 8 无法从归档构造，
    见 `docs/EXPERIMENTS.md` §20.3）。三处修复必须都在位：
      ⑨a schema 超长**截断**而非拒绝
      ⑨b 真错误（score 越界 / 缺字段）**仍被拒绝**
      ⑨c 工具标记可被清洗
      ⑨d 兜底能从裸文本/含标记 JSON 重建对象（**全字段**断言，不只看 score）
      ⑨e `call_structured` 有重试且超时不重试
      ⑨f 超时不重试（AST 静态检查）
      ⑨g KV 白名单覆盖 schema 全部字段（第二轮 review 新增）
      ⑨h 首行有前言/空行仍能解析（防 D2-2 回归）
      ⑨i is_wrong 不被非 key 行污染（防 D2-1 语义反转回归）
      ⑨j/k 多行字段可续行 + list 字段按分隔符切分
    """
    section("⑨ 批改链路抗格式飘移")

    from pydantic import ValidationError

    from schema.grading import GradingResult

    # ⑨a 截断
    r = GradingResult.model_validate({"score": 40, "feedback": "字" * 2000, "is_wrong": True})
    check(
        "⑨a 超长 feedback **截断**而非拒绝（不再整次硬失败）",
        len(r.feedback) == 800,
        str(len(r.feedback)),
    )
    r2 = GradingResult.model_validate({"score": 40, "is_wrong": True})
    check("⑨a' feedback 可缺省（默认空串）", r2.feedback == "")

    # ⑨b 真错误仍拒绝
    rejected = 0
    for bad in (
        {"score": 150, "feedback": "x", "is_wrong": True},
        {"score": -1, "feedback": "x", "is_wrong": True},
        {"feedback": "x", "is_wrong": True},
        {"score": 40, "feedback": "x"},
    ):
        try:
            GradingResult.model_validate(bad)
        except ValidationError:
            rejected += 1
    check("⑨b 真错误（越界/缺必填）**仍被拒绝**", rejected == 4, f"{rejected}/4")

    # ⑨c 标记清洗
    from rag.llm_calls import _strip_tool_markup as S

    cases = [
        ("a<parameter=score>b", "ab"),
        ("x\n<tool_call>\ny", "x\n\ny"),
        ("<function_call>{}</function_call>", "{}"),
        ("正文无标记", "正文无标记"),
        ("泛型 <T> 保留", "泛型 <T> 保留"),
    ]
    ok = sum(1 for src, want in cases if S(src) == want)
    check("⑨c 工具标记清洗正确且不误伤普通尖括号", ok == len(cases), f"{ok}/{len(cases)}")

    # ⑨d 兜底重建
    #   ★ 第二轮 review 补强：原来只断言 `score`，导致 D2-1（is_wrong 反转）/
    #     D2-3（KP 丢失）**都不会变红**。现改为断言**全部已解析字段**。
    from rag.llm_calls import _salvage_from_raw

    kv = "score: 40\nfeedback: 反馈<parameter=x>ok\nis_wrong: true"
    r3 = _salvage_from_raw(kv, GradingResult, "gate")
    check("⑨d 裸文本+标记 ⇒ 兜底重建成功", r3 is not None and r3.score == 40)
    check(
        "⑨d-全字段 兜底结果**每个字段**都正确（不只 score）",
        r3 is not None and r3.score == 40 and r3.is_wrong is True and "ok" in r3.feedback,
        f"score={getattr(r3, 'score', None)} is_wrong={getattr(r3, 'is_wrong', None)}",
    )
    check(
        "⑨d' 无标记 ⇒ 不兜底（交回原逻辑）",
        _salvage_from_raw("score: 40\nfeedback: ok\nis_wrong: true", GradingResult, "gate") is None,
    )
    check(
        "⑨d'' 有标记但缺必填 ⇒ 兜底**不**硬凑（拒绝）",
        _salvage_from_raw("feedback: a<parameter=x>b", GradingResult, "gate") is None,
    )

    # ── ⑨g/h/i：第二轮 review 新增（针对裸文本 KV 解析的三个缺陷）──────────
    from rag.llm_calls import _KV_ALL_FIELDS, _try_kv_dict

    # ⑨g 协议一致性：KV 白名单必须**覆盖 schema 全部字段**。
    #   漏一个 ⇒ 该字段走 schema 默认值被静默丢弃（D2-3 的根因）。
    schema_fields = set(GradingResult.model_fields)
    missing = sorted(schema_fields - _KV_ALL_FIELDS)
    check(
        "⑨g KV 白名单覆盖 schema 全部字段（漏字段 ⇒ 静默丢失）",
        not missing,
        f"schema {len(schema_fields)} 个，缺失: {missing}"
        if missing
        else f"schema {len(schema_fields)} 个全覆盖",
    )

    # ⑨h 首行有前言/空行 ⇒ 仍应从第一个合法 key 起解析（D2-2 回归防护）
    preambles = [
        "好的，批改如下：\nscore: 40\nis_wrong: true",
        "Let me grade this.\nscore: 40\nis_wrong: true",
        "\n\nscore: 40\nis_wrong: true",
    ]
    h_bad = [p for p in preambles if (_try_kv_dict(p) or {}).get("score") != 40]
    check("⑨h 首行前言/空行 ⇒ 仍解析出 score（不再全盘放弃）", not h_bad, f"失败: {len(h_bad)}")

    # ⑨i is_wrong 不得被「后续非 key 行」污染（D2-1 回归防护）
    pollution = [
        "score: 55\nis_wrong: true\ntopic: 平衡二叉树",
        "score: 55\nis_wrong: true\n知识点: 平衡二叉树",
        "score: 55\nis_wrong: true\nreason: 概念混淆",
        "score: 55\nis_wrong: true\n# 备注",
    ]
    i_bad = [p for p in pollution if (_try_kv_dict(p) or {}).get("is_wrong") is not True]
    check(
        "⑨i is_wrong 不被后续非 key 行污染（防语义反转）",
        not i_bad,
        f"被污染: {len(i_bad)} 例",
    )

    # ⑨j 多行字段仍可续行（feedback / error_analysis），且 list 字段按分隔符切分
    kv_multi = _try_kv_dict("score: 40\nfeedback: 第一行\n第二行\nis_wrong: true")
    check(
        "⑨j feedback 多行续行仍生效（且不污染 is_wrong）",
        kv_multi is not None
        and kv_multi.get("feedback") == "第一行\n第二行"
        and kv_multi.get("is_wrong") is True,
    )
    kv_list = _try_kv_dict("score: 40\nis_wrong: true\nknowledge_points: 平衡二叉树、二叉排序树")
    check(
        "⑨k knowledge_points 按 list 解析（非硬塞字符串）",
        isinstance((kv_list or {}).get("knowledge_points"), list)
        and (kv_list or {}).get("knowledge_points") == ["平衡二叉树", "二叉排序树"],
    )

    # ⑨e 重试接线
    from core.settings import settings as _s

    check(
        "⑨e STRUCTURED_OUTPUT_RETRIES 存在且 ≥1（默认开重试）",
        int(_s.STRUCTURED_OUTPUT_RETRIES) >= 1,
        str(_s.STRUCTURED_OUTPUT_RETRIES),
    )
    import rag.llm_calls as L

    src = inspect.getsource(L.call_structured)
    tree = ast.parse(textwrap.dedent(src))
    has_timeout_break = any(
        isinstance(n, ast.If)
        and "TimeoutError" in ast.unparse(n.test)
        and any(isinstance(s, ast.Break) for s in n.body)
        for n in ast.walk(tree)
    )
    check("⑨f 超时**不**重试（避免成倍放大延迟）", has_timeout_break)


async def check_10() -> None:
    """⑩ context-fallback 接线（2026-10-06 Step 5 实测第二个真实缺陷）。

    实测：LangChain **不**把运行时 ``RunnableConfig`` 注入工具函数参数，故工具里
    ``uid = user_id_from_config(config)`` 恒为 ``None`` ⇒ ``record_grade`` 的
    ``if uid:`` 分支被静默跳过 ⇒ 批改成功却 **EPISODES=0** ⇒ ``weak_topics`` 恒空
    ⇒ 跨会话永不召回。这是"成功但没落库"型缺陷，工具输出完全正常，极难发现。

    本节**零 LLM 成本**地验证修复：
      ⑩a 显式 config 优先（不破坏既有调用方）
      ⑩b 无显式 config 时回落运行时上下文（`ensure_config` 语义）
      ⑩c 无上下文时不抛错（直接单测场景）
      ⑩d 真写一条 episode 后 `weak_topics` 能派生（链路端到端）
    """
    section("⑩ context-fallback（工具 config 注入缺陷的修复）")

    from memory.remember import (
        batch_id_from_config,
        thread_id_from_config,
        user_id_from_config,
    )

    # ⑩a 显式优先
    c = {"configurable": {"user_id": "EXPLICIT", "thread_id": "T1", "question_batch_id": "B1"}}
    check(
        "⑩a 显式 config 优先（不破坏既有调用方）",
        user_id_from_config(c) == "EXPLICIT"
        and thread_id_from_config(c) == "T1"
        and batch_id_from_config(c) == "B1",
    )

    # ⑩c 无上下文不炸
    check(
        "⑩c 无 config 且无上下文 ⇒ 安全返回空（不抛错）",
        user_id_from_config(None) is None and thread_id_from_config(None) == "",
    )

    # ⑩b 上下文回落
    from langchain_core.runnables import RunnableLambda

    async def _inner(_):
        return user_id_from_config(None)

    got = await RunnableLambda(_inner).ainvoke(
        None, config={"configurable": {"user_id": "CTX-UID"}}
    )
    check("⑩b 无显式 config ⇒ 回落运行时上下文取到 user_id", got == "CTX-UID", str(got))

    # ⑩d 端到端：**经 config 解析取 uid** 写 episode ⇒ weak_topics 派生。
    #   ★ 关键：必须走 `user_id_from_config(None)`（而非显式传 uid），否则会绕过
    #     本缺陷所在的解析路径 —— 实测直接传 uid 时，护栏在破坏后**不变红**。
    from langchain_core.runnables import RunnableLambda

    from memory import initialize_store
    from memory.episodes import arecent_episodes
    from memory.namespaces import student_episodes_ns, student_profile_ns
    from memory.profile import aget_profile
    from memory.remember import record_grade
    from memory.runtime import set_store

    uid = "gate-ctx-e2e"
    async with initialize_store() as store:
        set_store(store)
        try:
            for ns in (student_episodes_ns(uid), student_profile_ns(uid)):
                for it in await store.asearch(ns, limit=200):
                    await store.adelete(ns, it.key)

            async def _write_two(_):
                # 模拟工具：只拿到 config 参数（此处为 None），uid 由回落解析得来
                resolved = user_id_from_config(None)
                if not resolved:
                    return None
                for _i in range(2):
                    await record_grade(
                        user_id=resolved,
                        topic="t",
                        score=40.0,
                        knowledge_points=["平衡二叉树"],
                    )
                return resolved

            resolved = await RunnableLambda(_write_two).ainvoke(
                None, config={"configurable": {"user_id": uid}}
            )
            eps = await arecent_episodes(store, uid)
            prof = await aget_profile(store, uid)
            check(
                "⑩d uid 经 config 解析（不是硬传）⇒ 真取到 user_id",
                resolved == uid,
                str(resolved),
            )
            check(
                "⑩d' 批改写入 ⇒ EPISODES 落库（不再静默跳过）",
                len(eps) == 2,
                f"{len(eps)} 条",
            )
            check(
                "⑩d'' 两次低分 ⇒ weak_topics 派生（跨会话召回的前置条件）",
                prof.weak_topics == ["平衡二叉树"],
                str(prof.weak_topics),
            )
        finally:
            for ns in (student_episodes_ns(uid), student_profile_ns(uid)):
                for it in await store.asearch(ns, limit=200):
                    await store.adelete(ns, it.key)
            set_store(None)

    # ⑩e ★ 回落**不会**串号：`get_config()` 读的是 contextvar，asyncio 每个 Task
    #   持有自己的 context 副本 ⇒ 「参数为 None 时用运行时上下文」取到的是
    #   **本次 graph 调用**的 config，不是「并发里算到谁头上算谁的」。
    #   这条判据是为了把 B3 里**被推翻的那半**固化下来：推翻一次不够，要留证据。
    async def _whoami(_):
        first = user_id_from_config(None)
        await asyncio.sleep(0.02)  # 强制让 4 个任务交错
        return first, user_id_from_config(None)

    results = await asyncio.gather(
        *[
            RunnableLambda(_whoami).ainvoke(None, config={"configurable": {"user_id": f"U{i}"}})
            for i in range(4)
        ]
    )
    check(
        "⑩e 并发交错下，回落仍各取自己的 user_id（contextvar 隔离）",
        all(a == f"U{i}" and b == f"U{i}" for i, (a, b) in enumerate(results)),
        str(results),
    )

    # ⑩f 契约：显式 config **整块替换**、不做键级合并（当前无调用方踩到，故**不改行为**，
    #   只把语义钉住 —— 将来若要改成合并，必须让这条变红后由人裁决）。
    partial = {"configurable": {"thread_id": "T-PARTIAL"}}
    check(
        "⑩f 只写 thread_id 的显式 config ⇒ user_id 为 None（不回落补键，契约见 docstring）",
        user_id_from_config(partial) is None and thread_id_from_config(partial) == "T-PARTIAL",
    )


def check_11() -> None:
    """⑪ `normalize_topic` 不得改坏 canonical name（2026-10-06 Step 5 实测缺陷 D）。

    `normalize_topic` 是 Memory 写入 / 派生的**唯一入口**：
        Episode.knowledge_points ← normalize_topics(模型输出)
        模型输出 → normalize_topic → 与 kp_index 的 canonical name 做相等匹配

    修复前的两个破坏路径：
      ① `_WS.sub("", text)` 删掉全部空白 ⇒ 21 个**含空格**的 canonical 名被改写
         （`TCP 流量控制` → `TCP流量控制`），聚合从此永久错配；
      ② `_TOPIC_ALIASES` 的**目标值不是 canonical** ⇒ 归一后落到**不可达值**，
         共两例：`页面置换算法 → 页面置换`（canonical 改成非 canonical）、
                 `deadlock → 进程死锁`（kp_index 里根本没有「进程死锁」，只有「死锁」）。

    判据（全部机械）：
      ⑪a 162 个 canonical 经 `normalize_topic` **恒等**（0 破坏）
      ⑪b 含空格的 canonical 不被去空格
      ⑪c 别名表中**目标 canonical** 的条目仍被正确纠正
      ⑪d **反向映射必须被拦住**（canonical 名不得被 rag 同义词表改写成别的值）
      ⑪e 写入路径 `normalize_topics` 保序去重且结果全 canonical
      ⑪f **全表断言**：`_TOPIC_ALIASES` 的**每一条 target 都必须 ∈ canonical**
          —— 这是 `deadlock → 进程死锁` 漏检后的补丁。⑪c 只测样本，故漏掉了它。
    """
    section("⑪ normalize_topic 不得改坏 canonical name")

    from memory.topics import (
        _TOPIC_ALIASES,
        canonical_names,
        normalize_topic,
        normalize_topics,
    )

    canonical = canonical_names()
    check("⑪a' canonical 集合可加载", len(canonical) > 100, f"{len(canonical)} 个")

    broken = sorted(n for n in canonical if normalize_topic(n) != n)
    check(
        "⑪a 全部 canonical 经 normalize_topic 恒等（0 破坏）",
        not broken,
        f"被改坏: {len(broken)} / {len(canonical)}" + (f" → {broken[:5]}" if broken else ""),
    )

    spaced = sorted(n for n in canonical if " " in n or "　" in n)
    spaced_broken = sorted(n for n in spaced if normalize_topic(n) != n)
    check(
        "⑪b 含空格的 canonical 不被去空格",
        bool(spaced) and not spaced_broken,
        f"{len(spaced)} 个含空格" + (f"，破坏: {spaced_broken}" if spaced_broken else ""),
    )

    # ⑪c 别名表条目：逐个核验「键非 canonical 的条目」归一后确实到 canonical。
    #   ★ 注意：`AVL树` **不在** `_TOPIC_ALIASES` 里（它靠 rag 兜底 ③ 命中），
    #     故不能拿它当「别名表覆盖」的样本 —— 这里分开测，避免再次归因错误。
    alias_entries = {k: v for k, v in _TOPIC_ALIASES.items() if k not in canonical}
    alias_bad = [
        (k, normalize_topic(k), v)
        for k, v in alias_entries.items()
        if normalize_topic(k) != v or v not in canonical
    ]
    check(
        "⑪c 别名表条目归一后均到 canonical",
        bool(alias_entries) and not alias_bad,
        f"{len(alias_entries)} 条非 canonical 键" + (f"，错误: {alias_bad}" if alias_bad else ""),
    )

    # ⑪f ★ 全表断言：`_TOPIC_ALIASES` 的**每一条 target** 必须 ∈ canonical。
    #   这条是 `deadlock → 进程死锁` 漏检（⑪c 只测样本）后的补丁：
    #   任何「指向不存在考点」的别名都会**永久不命中**，且不报错，必须机械拦下。
    bad_targets = sorted(f"{k!r} → {v!r}" for k, v in _TOPIC_ALIASES.items() if v not in canonical)
    check(
        "⑪f **_TOPIC_ALIASES 每条 target 均 ∈ canonical**（不可达目标值 ⇒ 红）",
        not bad_targets,
        f"全表 {len(_TOPIC_ALIASES)} 条" + (f"，不可达: {bad_targets}" if bad_targets else ""),
    )

    # ⑪g 死代码检查（提示性）：键本身已是 canonical 的条目**永不触发**（① 先返回）。
    dead = sorted(k for k in _TOPIC_ALIASES if k in canonical)
    check(
        "⑪g 别名表无恒等自映射死代码（键不应是 canonical）",
        not dead,
        f"死代码条目: {dead}" if dead else "无",
    )

    # ⑪d 反向映射：canonical 名不得被 rag 同义词表改写成别的值
    #   反例来源：rag/synonyms.SYNONYM_MAP 含 '二叉排序树'→'二叉搜索树'，
    #   但 '二叉排序树' 本身是 canonical ⇒ 必须原样保留，不能被反向覆盖。
    reverse = ["二叉排序树", "平衡二叉树", "栈"]
    reverse_bad = [n for n in reverse if n in canonical and normalize_topic(n) != n]
    check(
        "⑪d 反向映射被拦住（canonical 不被同义词表改写）",
        not reverse_bad,
        "" if not reverse_bad else f"被改写: {reverse_bad}",
    )

    # ⑪e 写入路径：保序去重 + 结果全 canonical
    raw_in = ["TCP 流量控制", "页面置换算法", "Cache 映射方式", "平衡二叉树", "平衡二叉树"]
    out = normalize_topics(raw_in)
    check(
        "⑪e normalize_topics 保序去重且结果全 canonical",
        out == ["TCP 流量控制", "页面置换算法", "Cache 映射方式", "平衡二叉树"]
        and all(n in canonical for n in out),
        str(out),
    )


def _vocab_tokens(system_text: str) -> set[str]:
    """从批改 system 文本里抽出「按学科分组注入」的考点名集合。

    ★ 为什么按 `【学科】a、b、c` 的行结构抽，而不是全文散搜：
    只有**词表块**里的名字才是「模型可选的取值」；规则尾部的反例（如「数据结构」太粗）
    也存在于文本中，全文散搜会把反例当成合法值，护栏就失去意义。
    """
    import re

    return {
        name
        for line in re.findall(r"【[^】]*】([^\n]+)", system_text)
        for name in line.split("、")
        if name
    }


def _independent_scan() -> tuple[set[str], set[str]]:
    """**绕开 `kp_vocab`**，直接解析 kp_index，返回 `(全部 name, subject 根节点 name)`。

    ★ 为什么必须独立扫一遍：⑫a~⑫c 的两侧集合都来自 `core.kp_vocab` ⇒ 属同义反复，
    `kp_vocab` 自己解析漂移时全绿无感知（⑫i 即为此而设）。本轮 #8 又加了一层过滤
    （剔掉 `node_kind == "subject"`），所以**期望集本身也要由独立扫描算出**，
    否则「过滤是否正确」这件事没有外部判据。
    """
    import json
    from pathlib import Path

    names: set[str] = set()
    roots: set[str] = set()
    for p in sorted((Path(ROOT) / "knowledge" / "knowledge_points").glob("*.jsonl")):
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(obj, dict):
                continue
            name = str(obj.get("name") or "").strip()
            if not name:
                continue
            names.add(name)
            if str(obj.get("node_kind") or "") == "subject":
                roots.add(name)
    return names, roots


def check_12() -> None:
    """⑫ GRADE_PROMPT 的词表必须与 `kp_index` **同源**（2026-10-07 缺陷 E · 方案 A）。

    缺陷 E 的机制：批改产出的 `knowledge_points` 是 LLM 自造自由文本 ⇒ 归一化不命中
    ⇒ 每个自造词各成一个 1-hit 桶 ⇒ `MEMORY_WEAK_MIN_HITS` 永不满足 ⇒ `weak_topics` 恒空。
    修法是在 prompt 里注入候选 canonical 词表，从**上游**约束输出。

    本组护栏锁的是「注入这件事真的生效了、且注入的就是 kp_index 那一份」：
      ⑫a 词表确实进了 prompt（接线，不是只写了函数）
      ⑫b 无遗漏（canonical ⊆ prompt 词表；只注入半个学科 ⇒ 模型被迫自造）
      ⑫c 无多余（prompt 词表 ⊆ canonical；混入自造词会重新制造不同源）
      ⑫d **不注入别名**（别名会让模型输出 `AVL` 而非 `平衡二叉树`）
      ⑫e 降级：词表为空 ⇒ 退回 8 个示例且全 canonical（服务不得起不来）
      ⑫f prompt 不含花括号（否则 `ChatPromptTemplate` 在 import 期直接炸）
      ⑫g 成本上界：批改 system 不超 2000 字符（每次批改都付这个钱）
      ⑫h ★ **反向验证**：探测器对篡改文本必须报红（证明 ⑫b/⑫c 不是恒绿）
    """
    section("⑫ GRADE_PROMPT 词表与 kp_index 同源（缺陷 E · 方案 A）")
    from core.kp_vocab import canonical_names
    from prompts import GRADE_PROMPT
    from prompts.service import _knowledge_points_block

    system_text = GRADE_PROMPT.messages[0].prompt.template
    canonical = set(canonical_names())
    injected = _vocab_tokens(system_text)

    direct_names, subject_roots = _independent_scan()
    # #8 之后，prompt 该提供的是「canonical − 课程根节点」—— 期望集由独立扫描算出。
    expected = direct_names - subject_roots

    check(
        "⑫a 词表块确实进了 prompt（接线生效，非只定义函数）",
        len(injected) > 100,
        f"prompt 内 {len(injected)} 个 / canonical {len(canonical)} 个 / 应提供 {len(expected)} 个",
    )
    missing = sorted(expected - injected)
    check("⑫b 无遗漏（应提供的考点全部可选）", not missing, f"缺失 {len(missing)}: {missing[:3]}")
    extra = sorted(injected - canonical)
    check("⑫c 无多余（prompt 内全部 ∈ canonical）", not extra, f"多余 {len(extra)}: {extra[:3]}")

    # ⑫d 别名不得出现在取值表里。别名表的键是「非 canonical 的同义写法」，
    #   一旦出现就说明词表注入了 aliases 而不是 canonical。
    from memory.topics import _TOPIC_ALIASES

    aliased = sorted(set(_TOPIC_ALIASES) & injected)
    check(
        "⑫d 未注入别名（只给 canonical，防模型输出 AVL 而非平衡二叉树）",
        not aliased,
        f"混入别名: {aliased}" if aliased else f"别名表 {len(_TOPIC_ALIASES)} 条均未出现",
    )

    # ⑫e 降级分支
    import re as _re

    fallback = _knowledge_points_block({})
    fb_names = {
        n.strip("「」")
        for n in _re.split(r"[、]", _re.findall(r"例如[：:]\s*([^。]+)", fallback)[0])
    }
    check(
        "⑫e 降级：词表为空 ⇒ 退回 8 示例且全 canonical（服务不起不来）",
        _vocab_tokens(fallback) == set()
        and len(fb_names) == 8
        and fb_names <= canonical
        and bool(fallback),
        f"示例 {len(fb_names)} 个，非规范 {sorted(fb_names - canonical)}",
    )

    check(
        "⑫f prompt 不含花括号（不破坏 ChatPromptTemplate import 期校验）",
        "{" not in system_text and "}" not in system_text,
    )
    check(
        "⑫g 批改 system 长度在上界内（每次批改调用都付这个词表钱）",
        len(system_text) <= 2000,
        f"{len(system_text)} 字符",
    )

    # ⑫h 反向验证：探测器必须能抓到「删一个 + 造一个」的篡改。
    #   篡改样例取自缺陷 E 的**真实产出**（`图的基本性质`），不是随手编的串。
    tampered = system_text.replace("【数据结构】", "【数据结构】图的基本性质、", 1)
    if "平衡二叉树" in tampered:
        tampered = tampered.replace("平衡二叉树", "", 1)
    t_injected = _vocab_tokens(tampered)
    detector_caught = (
        "图的基本性质" in t_injected - canonical  # ⑫c 会红
        and "平衡二叉树" in canonical - t_injected  # ⑫b 会红
    )
    check(
        "⑫h **反向验证**：篡改文本被探测器抓出（证明 ⑫b/⑫c 非恒绿）",
        detector_caught,
        f"抓到 自造={sorted(t_injected - canonical)[:1]} 遗漏={sorted(canonical - t_injected)[:1]}",
    )

    # ⑫i ★ 双读校验：⑫a~⑫c 与 ⑫k 的期望集**都**要能脱离 `kp_vocab` 独立算出 ——
    #   否则 kp_vocab 自身解析漂移（漏学科、把 links.jsonl 当 name、去重并掉考点、
    #   过滤过头/不足）时，护栏会跟着一起绿。
    check(
        "⑫i kp_vocab 解析结果 == 独立解析 jsonl（防同源双份都漂）",
        direct_names == canonical,
        f"独立解析 {len(direct_names)} 个 / kp_vocab {len(canonical)} 个；"
        f"差异 {sorted(direct_names ^ canonical)[:3]}",
    )

    # ⑫k 缺陷 #8：课程根节点**不得被提供给模型**，但**不得过滤过头**。
    #   规则尾自己写着「不是学科名（如「数据结构」太粗）」—— 若把它列进可选取值，
    #   模型选它就能轻易凑满 `MIN_HITS=2`，聚成「整门课 = 一个薄弱点」的桶，
    #   且因为是 canonical 而**比自造词更难发现**。
    offered_roots = sorted(subject_roots & injected)
    check(
        "⑫k·1 未把课程根节点提供给模型（`node_kind=subject` 已全部剔除）",
        not offered_roots and len(subject_roots) == 4,
        f"根节点={sorted(subject_roots)} 混入={offered_roots}",
    )
    #   反向：domain 层（408 大纲章名）必须**保留** —— 它们是合法薄弱点标签，
    #   E-5 的可接受集里就用到 `图` 与 `堆排序`。过滤过头会把这些一起杀掉。
    domains_kept = sorted(n for n in ("图", "排序", "内存管理", "树与二叉树") if n in injected)
    check(
        "⑫k·2 domain 章名仍保留（过滤没有过头把合法薄弱点也剔掉）",
        len(domains_kept) == 4,
        f"保留 {domains_kept}",
    )


def check_13() -> None:
    """⑬ B 组四条 review 结论的落地（2026-10-07，全部零 LLM）。

    先说清楚**验真伪**的结果，再锁修复：
      B1 **确认** —— 重判（`--rejudge`）走 `mechanical_reasons_from_record`，
         它照抄 `runner.mechanical_failures`，而 `case_invalid` / `memory_miss`
         是 runner 另两处分头写的 ⇒ 重判把它们**整个清掉**。实测归档里 4 条
         `case_invalid` 的 reasons 恰为 `["case_invalid"]` ⇒ 重判后变 `[]`、
         `primary_failure` 翻成 `none`（看起来像通过）。
      B2 **确认（潜伏）** —— `cli.py` 三处 `write_text("\\n".join(...))` 不留尾换行，
         与 `append_record` 的 `"a"` 模式相遇会把两条粘成一条坏行（实测 3 条只剩 1 条可读）。
         全盘扫过现存 12 份归档：末字节**都是** `\\n` ⇒ 尚未真的烧到过数据，属潜伏。
      B3 **一半被推翻** —— 「显式 config 只写一半会丢 `user_id`」成立，但仓内无此类调用方
         （`service.py:218` 两把键一起给）⇒ 不改行为，只把契约写进 docstring；
         「并发下回落会算到别人头上」**被实测推翻**：`get_config()` 读 contextvar，
         asyncio 每个 Task 各持副本，4 个交错任务仍各自取到自己的 uid（见 ⑩e）。
      B4 **大部分被推翻，剩一条真的** —— `forbidden_values` 是**回复文本里的自由词**，
         不是 KP 名，要求它 canonical 是错的规则（且 gold_sanity 已在查 `None` 与
         「与期望值重叠」）；`min_grade_calls` 改成 0 也**没放松** mem-001 的约束
         （真正兜底的是 `grade_score_bands`）。但 **mem-005 的前置条件确实是空标**：
         它只声明 `min_grade_calls: 0`，而 `len(calls) < 0` 永不成立 ⇒ 这条负样本对照
         从来没校验过「A 段真的没写入」。⇒ 新增 `max_grade_calls` 上限把它变成真约束。
    """
    section("⑬ 重判归因 / jsonl 落盘 / 负样本前置条件（B 组修复）")

    import tempfile
    from pathlib import Path as _P

    from evaluation.task_eval import memory_scorer as _ms
    from evaluation.task_eval.cases import SetupConditions, load_cases
    from evaluation.task_eval.gold_sanity import run_sanity
    from evaluation.task_eval.judge import mechanical_reasons_from_record
    from evaluation.task_eval.runner import CaseRecord, append_record, write_jsonl

    # —— B1：重判保留 runner 写的归因 ——
    rec_ci = {
        "case_id": "mem-001",
        "task": "memory",
        "validity_valid": False,
        "failure_reason": ["case_invalid"],
        "reply": "参考答案：略",
        "hard_fails": [],
    }
    got = mechanical_reasons_from_record(rec_ci)
    check("⑬a 重判保留 `case_invalid`（不再洗成『通过』）", got == ["case_invalid"], str(got))

    rec_mm = {
        "case_id": "mem-009",
        "task": "memory",
        "failure_reason": ["memory_miss"],
        "reply": "x",
    }
    got = mechanical_reasons_from_record(rec_mm)
    check(
        "⑬b 重判保留 `memory_miss`（标注缺口记号，非 judge 意见）", got == ["memory_miss"], str(got)
    )

    # 兜底路径：上一轮已被误清（reasons=[]）但 `validity_valid=False` 仍在 ⇒ 能恢复
    rec_wiped = {"case_id": "mem-002", "task": "memory", "validity_valid": False, "reply": "x"}
    got = mechanical_reasons_from_record(rec_wiped)
    check("⑬c reasons 已被洗空时按 `validity_valid` 重建", got == ["case_invalid"], str(got))

    # ★ 反向：保留面不能过宽 —— judge -only 的 reason 必须被清掉（否则新旧 judge 混在一起）
    rec_judge = {
        "case_id": "qa-001",
        "task": "qa",
        "pack_nonempty": True,
        "reply": "答案",
        "failure_reason": ["generation_wrong", "hallucination"],
    }
    got = mechanical_reasons_from_record(rec_judge)
    check(
        "⑬d 反向：judge-only reasons 仍被清除（保留面只有两项）",
        got == [],
        str(got),
    )

    # —— B2：行写出格式 ——
    tmp = _P(tempfile.mkdtemp()) / "b13.jsonl"
    rows = [{"case_id": f"a-{i}", "task": "qa"} for i in (1, 2)]
    write_jsonl(tmp, rows)
    raw = tmp.read_bytes()
    check(
        "⑬e write_jsonl 末行带换行（append 前置条件成立）",
        raw.endswith(b"\n") and len(raw.splitlines()) == 2,
        f"末字节={raw[-1:]} 行数={len(raw.splitlines())}",
    )
    append_record(CaseRecord(case_id="a-3", task="qa", task_mode="learn", query="q"), tmp)
    append_record(CaseRecord(case_id="a-4", task="qa", task_mode="learn", query="q"), tmp)
    ids = []
    bad = 0
    for ln in tmp.read_text(encoding="utf-8").splitlines():
        try:
            ids.append(json.loads(ln)["case_id"])
        except Exception:
            bad += 1
    check(
        "⑬f 追加到 write_jsonl 产物后 4 条全可解析",
        ids == ["a-1", "a-2", "a-3", "a-4"] and bad == 0,
        f"可解析={ids} 坏行={bad}",
    )

    # ★ 自愈路径：手写一份**没有**尾换行的文件（模拟旧 cli 产物 / 外部编辑）
    legacy = tmp.parent / "legacy.jsonl"
    legacy.write_text(
        "\n".join(json.dumps({"case_id": f"L-{i}", "task": "qa"}) for i in (1, 2)),
        encoding="utf-8",
    )
    append_record(CaseRecord(case_id="L-3", task="qa", task_mode="learn", query="q"), legacy)
    append_record(CaseRecord(case_id="L-4", task="qa", task_mode="learn", query="q"), legacy)
    got, bad = [], 0
    for ln in legacy.read_text(encoding="utf-8").splitlines():
        try:
            got.append(json.loads(ln)["case_id"])
        except Exception:
            bad += 1
    check(
        "⑬g 无尾换行的旧文件：append 前自动补分隔，4 条不丢（且幂等不多补）",
        got == ["L-1", "L-2", "L-3", "L-4"] and bad == 0,
        f"可解析={got} 坏行={bad} 物理行={len(legacy.read_text(encoding='utf-8').splitlines())}",
    )

    # —— B4：负样本对照的前置条件 ——
    cases = load_cases(ROOT / "evals" / "datasets" / "demo" / "memory_cases.jsonl")
    m5 = next((c for c in cases if c.case_id == "mem-005"), None)
    if m5 is None:
        check("⑬h mem-005 存在", False, "载入 0 条")
    else:
        sc = m5.gold.setup_conditions
        check(
            "⑬h mem-005 现声明「恰好 0 次批改」（min=0 且 max=0）",
            sc is not None and sc.min_grade_calls == 0 and sc.max_grade_calls == 0,
            f"min={getattr(sc, 'min_grade_calls', None)} max={getattr(sc, 'max_grade_calls', None)}",
        )
        v0 = _ms.check_case_validity(setup=sc, grade_scores=[], session_scope=0)
        v1 = _ms.check_case_validity(
            setup=sc, grade_scores=[{"session": 0, "score": 40.0}], session_scope=0
        )
        check(
            "⑬i 上限真生效：0 次⇒有效；A 段多出 1 次批改⇒case_invalid",
            v0.valid is True and v1.valid is False,
            f"0次={v0.valid} 1次={v1.valid} ({v1.reason})",
        )
        # ★ 反向：退回「只写 min:0」时空标 lint 必须变红
        m5_copy = load_cases(ROOT / "evals" / "datasets" / "demo" / "memory_cases.jsonl")
        target = next(c for c in m5_copy if c.case_id == "mem-005")
        target.gold.setup_conditions = SetupConditions(min_grade_calls=0)
        rep = run_sanity([target])
        check(
            "⑬j 反向：改回只写 `min: 0` ⇒ gold_sanity 必须报 ERROR（空标 lint 可红）",
            len(rep.errors) == 1 and rep.errors[0].field_name.endswith("min_grade_calls"),
            f"ERROR={[(i.field_name, i.message[:22]) for i in rep.errors]}",
        )
        check(
            "⑬k 真实 6 条 memory gold 体检仍全绿（新字段没制造假红灯）",
            not run_sanity(cases).errors,
            "",
        )

    # ★ 已发表的数字不许因为改 gold 而变动：逐条比对两份归档的 validity
    for fname in ("phase1_memory_step5_store_off.jsonl", "phase1_memory_step5_store_on.jsonl"):
        fp = ROOT / "evals" / "results" / "task_eval" / fname
        if not fp.exists():
            skip(f"⑬l {fname}", "本机归档未入库（D11 裁决 `*.jsonl` 不入库）⇒ 该项未执行", count=1)
            continue
        by_id = {c.case_id: c for c in cases}
        changed = []
        n = 0
        for ln in fp.read_text(encoding="utf-8").splitlines():
            ln = ln.strip()
            if not ln or ln.startswith("#"):
                continue
            r = json.loads(ln)
            if r.get("task") != "memory":
                continue
            n += 1
            c = by_id.get(r["case_id"])
            if c is None:
                changed.append(f"{r['case_id']}(gold 缺失)")
                continue
            new_v = _ms.check_case_validity(
                setup=c.gold.setup_conditions,
                grade_scores=r.get("grade_scores") or [],
                session_scope=0,
            ).valid
            if new_v != r.get("validity_valid"):
                changed.append(f"{r['case_id']}:{r.get('validity_valid')}→{new_v}")
        check(
            f"⑬l 新 gold 下 {fname} 的 validity 逐条不变（不动已发表数字）",
            n == 6 and not changed,
            f"{n} 条；变动={changed}",
        )

    tmp.unlink(missing_ok=True)
    legacy.unlink(missing_ok=True)


def check_14() -> None:
    """⑭ Generate 主指标口径（#2 定稿，2026-10-07）：主指标 = 逐题「适用项全过」。

    背景：`EFFECT_PLAN §3.1` 冻结的是**逐题 AND**，而 `report.py` 实为**项级池化**
    （把 15 题 × 每题 3~4 项倒进一个池子数通过率）。同一归档三个数并存：
    池化 **0.9423** / 逐题适用项全过 **0.80** / 严格 5/5 **0.00**。
    ⇒ 采纳「逐题适用项全过」为主指标，池化**降级为诊断**（不删，便于对照）。
    """
    section("⑭ Generate 主指标：逐题「适用项全过」（#2）")

    from evaluation.task_eval import metrics
    from evaluation.task_eval.report import build_report, render_markdown

    keys = ("gen_structure", "gen_answerability", "gen_coverage", "gen_correctness")

    # ⑭a 整题无可测项 ⇒ N/A（**绝不能算通过**，否则索引缺标签会被洗成满分）
    check(
        "⑭a 全 None 的题 ⇒ N/A（不进分母），不是 True",
        metrics.every_item_passes([None, None, None]) is None,
    )
    # ⑭b 逐题 AND + N/A 项不参与该题判定
    check(
        "⑭b 一题有 1 项 False ⇒ 该题不过；N/A 项不拉低该题",
        metrics.every_item_passes([True, False, True]) is False
        and metrics.every_item_passes([True, None, True]) is True,
    )

    # ⑭c ★ 方向性：池化**系统性偏乐观** —— 一道题崩得越集中、其他题可测项越多，
    #    稀释越狠。构造样本锁这个方向（真实归档上的差值是 0.9423 vs 0.80，由 ⑭d 钉住）。
    diluted = [{k: False for k in keys[:2]}] + [{k: True for k in keys}] * 13
    pooled = metrics.delivery_rate([r.get(k) for r in diluted for k in keys])["value"]
    per_case = metrics.rate([metrics.every_item_passes([r.get(k) for k in keys]) for r in diluted])[
        "value"
    ]
    check(
        "⑭c 同一样本两口径必须分叉，且池化**偏高**（证明换口径有信息量）",
        float(pooled) - float(per_case) > 0.02,
        f"池化={pooled} vs 逐题={per_case}（崩掉的题只算 1 题，却被 52 个好项摊薄）",
    )

    # ⑭d 真实归档复现（锁已发表数字）：15 条 ⇒ 主指标 0.80 / 诊断 0.9423
    import json as _json

    fp = ROOT / "evals" / "results" / "task_eval" / "phase1_baseline_v2.jsonl"
    if not fp.exists():
        skip(
            "⑭d~⑭f",
            "phase1_baseline_v2.jsonl 不在本机（未入库）⇒ 三项锁已发表数字的判据未执行",
            count=3,
        )
        return
    gen = [
        _json.loads(ln)
        for ln in fp.read_text(encoding="utf-8").splitlines()
        if ln.strip() and not ln.startswith("#")
    ]
    gen = [r for r in gen if r.get("task") == "generate"]
    rep = build_report(gen)
    g = rep["tasks"]["generate"]
    check(
        "⑭d 归档 15 条复现：主指标 0.80、诊断池化 0.9423（两数已发表，不许漂）",
        abs(float(g["gen_case_pass"]["value"]) - 0.80) < 1e-9
        and abs(float(g["gen_delivery"]["value"]) - 0.9423) < 1e-4
        and g["gen_case_pass"]["n"] == len(gen) == 15,
        f"主={g['gen_case_pass']['value']}({g['gen_case_pass']['passed']}/{g['gen_case_pass']['n']} 题) "
        f"池={g['gen_delivery']['value']}({g['gen_delivery']['passed']}/{g['gen_delivery']['n']} 项)",
    )
    # ⑭e 报告文案：主指标必须是逐题数，池化数必须自标「非主指标」，旧名必须消失
    md = render_markdown(rep)
    check(
        "⑭e 报告：逐题数挂「主指标」、池化数挂「诊断，非主指标」、旧名「交付完整率（主指标）」已消失",
        "适用项全过率（主指标）" in md
        and "诊断，非主指标" in md
        and "交付完整率（主指标）" not in md,
    )
    # ⑭f 整题不可测的题必须**显式露出**，不许静默进分母
    all_na = [
        {"task": "generate", **{k: None for k in keys + ("gen_difficulty",)}} for _ in range(3)
    ]
    st = build_report(all_na)["tasks"]["generate"]["gen_case_pass"]
    check(
        "⑭f 3 题全不可测 ⇒ 主指标 n=0、n_a=3（分母不会假装是 3）",
        st["n"] == 0 and st["n_a"] == 3,
        str(st),
    )


def check_15() -> None:
    """⑮ D3（死代码删除）+ D4（record 落 `prompt_set_version`）的落地锁，零 LLM。"""
    section("⑮ 死代码已删净 / record 落提示词版本（D3 + D4）")

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

    # ⑮c D3 的**边界**：向量开关本身仍被 sqlite.py 用着 ⇒ 删的只能是检索函数，不是配置
    sqlite_src = (ROOT / "src" / "memory" / "sqlite.py").read_text(encoding="utf-8")
    check(
        "⑮c MEMORY_STORE_VECTOR_ENABLED 仍被 sqlite.py 消费（没被顺手删成空配置）",
        "MEMORY_STORE_VECTOR_ENABLED" in sqlite_src,
    )

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

    import asyncio as _aio

    from core.settings import settings as _s
    from evaluation.task_eval import metrics
    from evaluation.task_eval.cases import load_demo
    from evaluation.task_eval.retrieval_probe import _EXAM_ROLES
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

    k = d["retrieval_cfg"]["k"]
    items = d["top_items"]
    cats = [i["category"] for i in items]
    allkp = [x for i in items for x in i["kp"]]
    is_exam = [
        (
            i["kb_depth"] == "exams"
            or i["doc_role"] in _EXAM_ROLES
            or i["category"] == "questions"
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

    import agent_behavior_smoke as smoke
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

    import json as _json
    from dataclasses import asdict as _asdict

    from evaluation.task_eval import memory_scorer as _ms
    from evaluation.task_eval import metrics
    from evaluation.task_eval.cases import load_cases
    from evaluation.task_eval.report import build_report
    from evaluation.task_eval.runner import CaseRecord, _apply_memory_judgement

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

    # ⑱d ★★ 测**接线**而非只测函数：走真实的 `_apply_memory_judgement`，
    #   断言 scorer 的极性值真的写进了 record 并可从 `to_dict()` 读出。
    #   （#21 的成因恰恰是这一层被 property 覆盖 —— 只测 scorer 永远发现不了。）
    cases = load_cases(ROOT / "evals" / "datasets" / "demo" / "memory_cases.jsonl")
    m4 = next((c for c in cases if c.case_id == "mem-004"), None)
    if m4 is None:
        check("⑱d mem-004 存在", False, "载入 0 条")
    else:
        rec = CaseRecord(case_id="mem-004", task="memory", task_mode=m4.task_mode, query=m4.query)
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
        if m1 is not None:
            rec1 = CaseRecord(
                case_id="mem-001", task="memory", task_mode=m1.task_mode, query=m1.query
            )
            _apply_memory_judgement(rec1, m1, memory_cards=[], reply="本题要点如下。")
            check(
                "⑱e 正样本未召回 ⇒ False（不是 N/A、更不是 True）",
                rec1.memory_correct_use is False,
                f"{rec1.memory_correct_use} | recalled_actual={rec1.memory_recalled_actual}",
            )


def check_19() -> None:
    """⑲ 「前置条件满足却没有记忆卡」的真因：KP 聚合按**精确名**计 hit（2026-10-07 #22）。

    Step 9 实跑撞到的现象：Store ON 的 mem-002 **两次批改都 0 分**（低分前置条件满足），
    但 `memory_cards = 0`、B 段召不回。只报数字的话会被读成「产品不召回」。

    真因用**纯函数**（零 LLM、零网络、零 DB）钉死：`compute_weak_topics` 的聚合单位是
    **KP 精确名**，阈值 `MEMORY_WEAK_MIN_HITS=2` ⇒ 两道题、同一章、不同考点 ⇒
    各 1 hit ⇒ 谁都不过线 ⇒ 画像为空。
    """
    section("⑲ KP 聚合按精确名计 hit ⇒ 正样本可能天然测不到召回（#22）")

    import asyncio as _aio

    import agent_behavior_smoke as smoke
    from langchain_core.messages import AIMessageChunk, ToolMessage

    from core.settings import settings
    from memory.episodes import coerce_episode
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


def check_20() -> None:
    """⑳ 校准报告的「非众数占比」露出（D6，登记为 §20.5 #19）。零 LLM。

    背景：`calibration_30.jsonl` 的人工分是 `{5:28, 0:1, 2:1}`，`spearman=0.7321`
    刚过 0.70 阈值 ⇒ PASS。破坏性检验显示：把那 2 条非众数行任一条改成 5 ⇒ 掉到 ~0.5（FAIL）；
    把那 2 条的 **judge 分改成 0**（judge 在唯一可判别处完全打错）⇒ **仍然 PASS**
    （秩相关只看排序）。⇒ 信息量只在 2/30 行上，必须让报告自己说出来。
    ★ 本项**不判成败、不动阈值**：只锁「露出存在且算对」，以及「分布正常时不许误报」（避免变成一刀切禁用）。
    """
    section("⑳ 校准 PASS 的秩相关信息量必须自己露出（D6 / #19）")

    from evaluation.task_eval.judge import (
        CALIBRATION_THRESHOLDS,
        INFORMATIVE_SHARE_MIN,
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
    # ★ 反向：分布正常的表不许误报（否则这条露出会退化成「永远警告」= 没有信息）
    hum = [0, 1, 2, 3, 3, 4, 5, 5, 2, 3, 1, 4, 5, 3, 2, 4, 1, 0, 5, 3, 4, 2, 3, 5, 1, 4, 2, 3, 5, 4]
    llm = [0, 1, 2, 3, 4, 4, 5, 5, 2, 3, 1, 4, 5, 3, 2, 4, 2, 0, 5, 3, 4, 2, 3, 5, 1, 4, 2, 3, 5, 4]
    rep2 = calibrate([float(x) for x in llm], [float(x) for x in hum])
    check(
        f"⑳c 反向：分布正常（非众数 {rep2.informative_n}/30）⇒ 不误报退化",
        rep2.rank_degenerate is False and (rep2.informative_share or 0) >= INFORMATIVE_SHARE_MIN,
        f"share={rep2.informative_share} deg={rep2.rank_degenerate}",
    )
    # ⑳d 真实文件本身必须被报告成退化（读的是仓内校准表，不调 LLM）
    import json as _json

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

    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    from core.settings import settings as _s
    from evaluation.task_eval.runner import memory_write_missing, preflight_check

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

    # ★ review M7：有些 OpenAI 兼容服务**没有 `/health` 路由**（404），但 `/embeddings` 完全正常。
    #   旧预检会因为一句 HTTP 404 就 return 3 拒绝开跑 —— 那是**假红**，会把能用的 TEI 拦在门外。
    #   ⇒ 健康检查的抱怨只在推理也失败时才允许一起进 problems。
    import json as _json4h

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

    import asyncio as _aio

    import agent_behavior_smoke as smoke
    from langchain_core.messages import AIMessageChunk

    from memory.runtime import get_store, set_store

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

    from dataclasses import dataclass, field

    import evaluation.task_eval.runner as R
    from evaluation.task_eval.cases import load_demo
    from evaluation.task_eval.report import summarize_task

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
    import memory_step5_paired as paired  # type: ignore[import-not-found]

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


def check_24() -> None:
    """㉔ 正样本 `values` 的**粒度**必须有机械约束（2026-10-08 review M10，接 #26）。

    D8 把 `mem-002`/`mem-003` 的 `expected_memory.values` 从章名（`图` / `排序`）收到具体考点
    （`图的存储` / `快速排序`），因为 `recalled` 是**子串包含**判定 —— 章名会被它下面
    任何一个子考点满足 ⇒ 「召回成功」测不出「召回的是不是设计的那个薄弱点」。
    ★ 但当时**只有人工承诺**：`章名` 本身就是 canonical（`node_kind=domain`），
      旧的 lint 只查「是否 canonical」⇒ 改回 `图` 依旧 ERROR 0。这条补上机械约束。
    """
    section("㉔ 正样本 values 必须是具体考点（粒度 lint，#26 的可执行化）")

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


def check_25() -> None:
    """㉕ #27 的处置（D12 选 (B)）：评测侧从 metadata 兜底解析 KP，**产品契约不动**。

    缺陷：`rag/layer_recall.py:43` 的 top-up 路径把 `knowledge_points` 写死成 `[]`，
    而同一份 `metadata` 里就带着 JSON 字符串 ⇒ 走这条路进 top-k 的证据在
    `kp_hit` / `kp_mrr` / Generate 的 `coverage` 眼里等于没标考点（系统性假阴性）。
    ⇒ (B) = 只在**评测读数**这一侧兜底；产品给 agent 的那份契约仍缺 KP，
      这条偏差必须单独披露（不顺手改产品，是因为 `EvidenceDoc.knowledge_points` 是
      对外契约字段，动它 = 动检索链 = 触发新锚点 + qa/generate 重跑）。
    """
    section("㉕ top-up 项的 KP 兜底解析（#27 / D12 选 B；产品契约保持不动）")

    import json as _json25

    from evaluation.task_eval.retrieval_probe import _to_item
    from rag.evidence import TextEvidence, parse_knowledge_points
    from rag.layer_recall import _doc_to_evidence

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


def check_26() -> None:
    """㉖ Verify 行为层判据（D14）—— §3.1 冻结的头号指标不可计算时，这一行由谁把门。

    背景：`question_id_recall@k` 算不出来（#20/D7），而 `final_quality≥4` 在 verify 上
    测的是**检索覆盖**（未达成 case 全是 `exam_hit=False`，agent 诚实说"无法确认"是**正确行为**）
    ⇒ 拿它当 Gate 就是指标效度错。D14 选① = 把 `PHASE1_VERIFY.md` 里那两个人工读数**机械化**。
    """
    section("㉖ Verify 行为层判据（D14；仍出题必须为 0）")

    import asyncio as _aio26
    import json as _json26
    from dataclasses import dataclass, field

    import evaluation.task_eval.runner as R26
    from evaluation.task_eval import metrics as _m26
    from evaluation.task_eval.cases import load_demo
    from evaluation.task_eval.report import summarize_task

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


def main() -> int:
    check_1()
    check_2()
    check_3()
    check_4()
    asyncio.run(check_4_real())
    check_5()
    check_6()
    check_7()
    check_8()
    check_9()
    asyncio.run(check_10())
    check_11()
    check_12()
    check_13()
    check_14()
    check_15()
    check_16()
    check_17()
    check_18()
    check_19()
    check_20()
    check_21()
    check_22()
    check_23()
    check_24()
    check_25()
    check_26()

    total = _n_pass + _n_fail + _n_skip
    print()
    print("=" * 72)
    print(
        f"判定项 {total} = 通过 {_n_pass} · 失败 {_n_fail} · 未执行 {_n_skip}"
        f"（声明值 {_EXPECTED_ITEMS}）"
    )
    if total != _EXPECTED_ITEMS:
        _flag(
            f"判据总数 {total} ≠ 声明的 {_EXPECTED_ITEMS} —— "
            "要么某组提前 return/抛错吞掉了后续项，要么改了判据没同步常量"
        )
    if _n_skip:
        _flag(f"有 {_n_skip} 项**未执行** ⇒ 本次不能称为「全绿」，只能说「跑了的那几项绿」")
    if _ok_all and total == _EXPECTED_ITEMS:
        print(
            "✅ STEP 4/5 GATE 通过 —— 五项修复 + case-validity + paired control "
            "+ KP 规范名 + 批改抗飘移 + context-fallback + topic 归一 + 写入证据判据均就位"
        )
    else:
        print("❌ STEP 4/5 GATE 未通过")
    print("=" * 72)
    if _ok_all and total == _EXPECTED_ITEMS and not _n_skip:
        print("★ 遗留：A→B 真跨 thread 召回（真跑 agent）属 Step 5 实跑，需消耗 token。")
    return 0 if (_ok_all and total == _EXPECTED_ITEMS and not _n_skip) else 1


if __name__ == "__main__":
    raise SystemExit(main())
