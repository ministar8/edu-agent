"""Agent 主链路完整验证（离线、不联网、不碰真实 LLM/检索依赖）。

直接调用**真实编译图** ``agents.orchestration.teaching_graph.edu_supervisor``
（prepare_task → load_memory → supervisor → finalize；内层 supervisor → handoff →
专家子图 → forward_after_agent 短路），验证七项关注点：

1. **Supervisor 直答**：寒暄类问题不进任何专家；task_mode=chat、active_agent=None。
2. **三个专家分别正常执行**（knowledge / question / grading 各一轮）。
3. **专家工具调用失败时错误正确传递**：错误文本经 ToolMessage 到达模型（不崩溃、
   专家仍闭环），并区分「检索依赖不可用 / 批改失败 / 出题失败」三类语义。
4. **专家终答跳过 Supervisor 二次 LLM 调用**：用假模型的调用计数证明
   supervisor 只被调用 1 次（仅路由），且终答与专家原文逐字节一致（无二次复述）。
5. **最终结果正确进入外层 State**：task_id / task_mode / active_agent /
   task_status / error 在外层 TeachingState 上的落点逐一断言。
6. **专家级硬失败（S8）**：specialist 模型在子图内硬抛异常 ⇒ ``run_supervisor``
   的异常分段包装（`SupervisorRunError`）上抛、``stage_of`` 映射正确。
   （`UnclosedSpecialistOutput → SpecialistRunError` 这条 fail-fast 在真实图里
   会烧掉整个 recursion 预算，不作真实图验证，由 ``tests/test_run_supervisor_errors.py``
   单测锁定。）
7. **多轮对话 + Checkpointer 恢复（S9）**：同一 thread 两轮；第 2 轮使用**全新的
   ``AsyncSqliteSaver`` 连接**（第 1 轮连接已关闭）——恢复只能来自磁盘上的
   checkpoint，而非进程内缓存；断言完整历史保留、记忆卡不累积、
   ``context_mode`` 线程级延续。

序幕（装配方式）：

- **LLM 替身**：``core.get_model`` 被替换为脚本化假模型（每个角色一个实例，
  带 ``calls`` 计数，脚本耗尽即抛错）。supervisor / 专家的真实装配、handoff
  工具、``forward_after_agent`` 短路、add_messages 合并、错误包装全部保持真实。
- **业务边界替身**（仅让主链路离线可跑；超出「主链路」范围的子系统各有独立测试）：
  ``tools._retrieve_payload``（检索链核心封装）、``question.agenerate_question_set``
  （结构化出题核心）、``grading.call_structured``（批改结构化 LLM 调用）。
  其中指标 3 的失败场景**不绕过** ``_retrieve_payload``：直接替换更底层的
  ``rag.retrieval.api.retrieve_for_task``，让真实的「异常分级 → 载荷映射 →
  ToolMessage → 模型决策」链路完整跑通。

用法::

    $env:PYTHONIOENCODING="utf-8"; $env:PYTHONPATH="src"
    .venv\\Scripts\\python.exe scripts\\ops\\verify_agent_chain.py

退出码：0 = 全部通过；1 = 任一断言失败。
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import sys
from collections.abc import Iterator
from pathlib import Path

# 防御性开关：环境变量优先于 .env，确保即使某些 import 期代码触碰到
# 检索 / embedding 相关配置，也不会建立任何真实网络连接。
os.environ["USE_FAKE_MODEL"] = "true"
os.environ["USE_FAKE_EMBEDDING"] = "true"
os.environ["USE_FAKE_RERANK"] = "true"

from langchain_core.language_models.chat_models import BaseChatModel  # noqa: E402
from langchain_core.messages import (  # noqa: E402
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.outputs import ChatGeneration, ChatResult  # noqa: E402
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver  # noqa: E402
from pydantic import Field  # noqa: E402

import core  # noqa: E402
from core import settings  # noqa: E402

# ─────────────────────────────────────────────────────────────────────────────
# 1. 脚本化假模型 + get_model 替换（必须在 import 任何 agent 模块之前完成）
# ─────────────────────────────────────────────────────────────────────────────


class Boom:
    """哨兵：假模型弹出它时硬抛异常（验证专家级失败的异常分段包装，S8）。"""

    def __init__(self, reason: str) -> None:
        self.reason = reason


class ScriptedModel(BaseChatModel):
    """脚本化假模型：按队列逐个返回预置 AIMessage，并计数每次模型调用。

    与项目内 ``core.llm.FakeToolModel`` 的关键差异：脚本耗尽即抛错，而不是
    静默循环复用 —— 主链路验证里出现脚本之外的模型调用必须显式失败。
    """

    label: str = ""
    queue: list = Field(default_factory=list)
    calls: int = 0
    # 每次模型调用收到的 ToolMessage 文本（模型视角，用于断言「错误真实到达模型」）
    tool_traffic: list[str] = Field(default_factory=list)

    @property
    def _llm_type(self) -> str:
        return "scripted-model"

    @property
    def _identifying_params(self) -> dict:
        return {"label": self.label}

    def _pop(self) -> BaseMessage:
        if not self.queue:
            raise RuntimeError(
                f"ScriptedModel[{self.label}] 脚本已耗尽：出现了脚本之外的模型调用"
            )
        item = self.queue.pop(0)
        self.calls += 1
        if isinstance(item, Boom):
            raise RuntimeError(f"{item.reason}（ScriptedModel[{self.label}] 预置崩溃）")
        if not isinstance(item, BaseMessage):
            item = AIMessage(content=str(item))
        return item

    def _generate(
        self, messages, stop=None, run_manager=None, config=None, **kwargs
    ) -> ChatResult:
        message = self._pop()
        self.tool_traffic.extend(
            str(m.content) for m in messages if isinstance(m, ToolMessage)
        )
        if not isinstance(message, BaseMessage):
            message = AIMessage(content=str(message))
        return ChatResult(generations=[ChatGeneration(message=message)])

    def bind_tools(self, tools, **kwargs):
        return self

    def reset(self, queue: list) -> None:
        self.calls = 0
        self.tool_traffic.clear()
        self.queue.clear()
        for item in queue:
            self.queue.append(item)

    def saw_tool_text(self, *needles: str) -> bool:
        """模型是否收到过一条同时包含所有 needle 的 ToolMessage。"""
        return any(all(n in t for n in needles) for t in self.tool_traffic)

    def aim(self, content: str, tool_calls: list | None = None) -> AIMessage:
        return AIMessage(content=content, tool_calls=tool_calls or [])


_MODELS: dict[str, ScriptedModel] = {
    "supervisor": ScriptedModel(label="supervisor"),
    "knowledge": ScriptedModel(label="knowledge"),
    "question": ScriptedModel(label="question"),  # question_agent 与 question_gen_agent 预期共用
    "grading": ScriptedModel(label="grading"),
}

# 温度无法区分全部角色（TEMP_CREATIVE == TEMP_DEFAULT == 0.3），改按**装配顺序**
# 分派，并用温度做交叉校验。装配序由 import 顺序固定：
#   agents.specialists 按 __init__ 顺序 grading → knowledge → question；
#   question 模块内 question_gen_agent 先于 question_agent；
#   最后是 supervisor 模块的 create_supervisor。
#   ⇒ 共 5 次 get_model 调用：grading / knowledge / question_gen / question / supervisor。
#
# ⚠️ 在这里的脚本迭代中，patch 之前**绝不能** import 任何 ``agents.*`` 模块：
# ``import agents`` 会触发 agents/__init__ → registry → teaching_graph 的完整装配链，
# 会在补丁生效前把所有 agent 用真实路径的 get_model 装配掉。温度常量由此不用
# agents.runtime.temperature，直接由 settings.TEMP_* 计算（两者恒等）。
EXPECTED_BUILD_SEQUENCE: list[str] = [
    "grading",  # TEMPERATURE_GRADING     = TEMP_PRECISE
    "knowledge",  # TEMPERATURE_KNOWLEDGE  = TEMP_DEFAULT
    "question",  # question_gen_agent      = TEMP_CREATIVE（本验证不触发它）
    "question",  # question_agent          = TEMP_CREATIVE
    "supervisor",  # TEMPERATURE_SUPERVISOR = TEMP_DEFAULT
]
_EXPECTED_TEMPS: list[float] = [
    settings.TEMP_PRECISE,
    settings.TEMP_DEFAULT,
    settings.TEMP_CREATIVE,
    settings.TEMP_CREATIVE,
    settings.TEMP_DEFAULT,
]
_build_index = 0


def _close(a: float, b: float) -> bool:
    return abs(a - b) < 1e-9


def scripted_get_model(model_ref=None, /, temperature=None):
    """按装配顺序分派假模型；每次返回都需与预期的温度一致（顺序或温度脱节 ⇒ 显式失败）。"""
    global _build_index
    if _build_index >= len(EXPECTED_BUILD_SEQUENCE):
        raise RuntimeError(
            f"scripted_get_model 第 {_build_index + 1} 次调用：装配次序超出预期 "
            f"（应为 {len(EXPECTED_BUILD_SEQUENCE)} 次）——出现了脚本未涵盖的 agent 构建"
        )
    role = EXPECTED_BUILD_SEQUENCE[_build_index]
    expected_temp = _EXPECTED_TEMPS[_build_index]
    temp = settings.TEMP_DEFAULT if temperature is None else float(temperature)
    if not _close(temp, expected_temp):
        raise RuntimeError(
            f"scripted_get_model 第 {_build_index + 1} 次调用温度 {temp} 与装配序预期 "
            f"{expected_temp}（{role}）不一致 —— 装配顺序假设被破坏，结果不可信，中止。"
        )
    _build_index += 1
    return _MODELS[role]


core.get_model = scripted_get_model  # supervisor.py 的模块顶层 from core import 绑定到它
core.llm.get_model = scripted_get_model

# 现在才 import agent 图（全部专家与 supervisor 以假模型完成真实装配）
import agents.runtime.tools as tools_mod  # noqa: E402
import agents.specialists.grading as grading_mod  # noqa: E402
import agents.specialists.question as question_mod  # noqa: E402
from agents.orchestration.state import (  # noqa: E402
    SpecialistRunError,
    SupervisorRunError,
    stage_of,
)
from agents.orchestration.teaching_graph import (  # noqa: E402  (patch 之后才有)
    MEMORY_CARD_MESSAGE_ID,
    edu_supervisor,
)
from infra.errors import RetrievalUnavailable  # noqa: E402
from schema.evidence import EvidenceDoc, RetrievalResult  # noqa: E402
from schema.grading import GradingResult  # noqa: E402
from schema.questions import GeneratedQuestion, GeneratedQuestionSet  # noqa: E402

if _build_index != len(EXPECTED_BUILD_SEQUENCE):
    raise RuntimeError(
        f"装配期分派异常：get_model 被调用 {_build_index} 次（应为 "
        f"{len(EXPECTED_BUILD_SEQUENCE)} 次）。脚本分派与装配序脱节，结果不可信，中止。"
    )


# ─────────────────────────────────────────────────────────────────────────────
# 2. 业务边界替身（作用域内生效，退出即还原真实实现）
# ─────────────────────────────────────────────────────────────────────────────

OK_DOC = EvidenceDoc(
    evidence_id="e1",
    source="data_structure/basic/bst.md",
    chunk_id="bst-001",
    excerpt="二叉搜索树：左子树所有节点小于根，右子树所有节点大于根；中序遍历得到升序序列。",
)
OK_CONTEXT = (
    "【二叉搜索树】左子树所有节点小于根，右子树所有节点大于根；"
    "中序遍历得到升序序列。\n\n来源: data_structure/basic/bst.md"
)


async def _ok_retrieve_payload(query, **_):
    """检索链核心替身：返回正常检索载荷（异常分级等方面的真实代码不被绕过）。"""
    return RetrievalResult(
        status="ok",
        query=query,
        context=OK_CONTEXT,
        sources=["data_structure/basic/bst.md"],
        docs=[OK_DOC],
        verification="pass",
        verification_reasons=[],
    ).as_tool_payload()


async def _ok_call_structured(
    messages,
    schema,
    *,
    temperature=None,
    timeout=None,
    stage=None,
    prompt_set_version=None,
    salvage=None,
):
    """批改结构化 LLM 调用替身：返回确定性的批改结果。"""
    assert schema is GradingResult
    return GradingResult(
        score=95,
        feedback="正确：中序遍历严格递增是 BST 定理的直接推论。",
        is_wrong=False,
        knowledge_points=["二叉搜索树"],
    )


async def _fake_agenerate_question_set(topic, count=1, difficulty="mixed"):
    del count, difficulty
    return GeneratedQuestionSet(
        questions=[
            GeneratedQuestion(
                question_type="choice",
                difficulty="basic",
                stem=f"关于 {topic} 的单选题（验证脚本预置）",
                standard_answer="A",
                explanation="解析：预置数据，用于主链路验证。",
            )
        ]
    )


async def _raise_retrieval(query, **_):
    """检索真依赖故障替身：模拟 TEI/Chroma 不可用（可重试类语义）。"""
    raise RetrievalUnavailable("TEI 宕机")


async def _raise_question_set(topic, count=1, difficulty="mixed"):
    del count, difficulty
    raise RuntimeError("结构化输出两次校验未通过")


_ORIGINALS = {
    "retrieve_ok": tools_mod._retrieve_payload,
    "retrieve_fail": tools_mod.retrieve_for_task,
    "grade_ok": grading_mod.call_structured,
    "question_ok": question_mod.agenerate_question_set,
    "question_fail": question_mod.agenerate_question_set,
}
_REPLACEMENTS = {
    "retrieve_ok": ("tools_mod", "_retrieve_payload", _ok_retrieve_payload),
    "retrieve_fail": ("tools_mod", "retrieve_for_task", _raise_retrieval),
    "grade_ok": ("grading_mod", "call_structured", _ok_call_structured),
    "question_ok": ("question_mod", "agenerate_question_set", _fake_agenerate_question_set),
    "question_fail": ("question_mod", "agenerate_question_set", _raise_question_set),
}


@contextlib.contextmanager
def stubs(*what: str) -> Iterator[None]:
    """在场景作用域内替换边界替身，退出时按快照还原全部真实实现。"""

    def apply(name: str) -> None:
        module_name, attr, replacement = _REPLACEMENTS[name]
        module = {"tools_mod": tools_mod, "grading_mod": grading_mod, "question_mod": question_mod}[module_name]
        setattr(module, attr, replacement)

    snapshot: dict[str, object] = {}
    for name in what:
        snapshot[name] = _ORIGINALS[name]

    def restore() -> None:
        for name, original in snapshot.items():
            module_name, attr, _ = _REPLACEMENTS[name]
            module = {"tools_mod": tools_mod, "grading_mod": grading_mod, "question_mod": question_mod}[module_name]
            setattr(module, attr, original)

    for name in what:
        apply(name)
    try:
        yield
    finally:
        restore()


# ─────────────────────────────────────────────────────────────────────────────
# 3. 结果收集、工具函数与场景
# ─────────────────────────────────────────────────────────────────────────────

_REPORT: list[tuple[str, bool, str]] = []


def check(section: str, ok: bool, detail: str) -> bool:
    _REPORT.append((section, bool(ok), detail))
    print(f"    {'✓' if ok else '✗'} {detail}", flush=True)
    return bool(ok)


def _tail(messages) -> AIMessage | None:
    """尾部最近一条实质 AI 消息（跳过 ToolMessage），与 state.last_ai_message 同口径。"""
    for m in reversed(messages):
        if isinstance(m, ToolMessage):
            continue
        return m if isinstance(m, AIMessage) else None
    return None


def _tool_messages(messages) -> list[ToolMessage]:
    return [m for m in messages if isinstance(m, ToolMessage)]


def _make_config(thread: str) -> dict:
    # 与 service 层同口径：recursion_limit 显式收紧（不设会落到 LangGraph 默认 10007）
    return {
        "configurable": {"thread_id": thread, "request_id": f"req-{thread}"},
        "recursion_limit": settings.AGENT_RECURSION_LIMIT,
    }


async def run_graph(query: str, thread: str) -> dict:
    return await edu_supervisor.ainvoke(
        {"messages": [HumanMessage(content=query)]},
        config=_make_config(thread),
    )


def _common_state_checks(state: dict, section: str, *, task_mode: str,
                         active_agent: str | None, final: AIMessage) -> None:
    """指标 5：外层 TeachingState 的落点（每个场景通用断言）。"""
    check(section, state.get("task_status") == "completed",
          f"task_status == completed（实际 {state.get('task_status')!r}）")
    check(section, state.get("task_mode") == task_mode,
          f"task_mode == {task_mode!r}（实际 {state.get('task_mode')!r}）")
    check(section, state.get("active_agent") == active_agent,
          f"active_agent == {active_agent!r}（实际 {state.get('active_agent')!r}）")
    check(section, state.get("error") is None, "error 字段为 None（无错误落状态）")
    check(section, str(state.get("task_id") or "").startswith(f"{section}:"),
          f"task_id 正确进入外层 State（{state.get('task_id')!r}）")
    check(section, state.get("context_mode") is not None,
          f"context_mode 进入外层 State（{state.get('context_mode')!r}）")
    tail = _tail(state.get("messages") or [])
    check(section, tail is not None and str(tail.content) == str(final.content),
          "终答 = 预置专家原文（逐字节一致：无二次复述/改写）")
    check(section, tail is not None and tail.name == (final.name or active_agent),
          f"终答 name == {final.name or active_agent!r}（实际 {getattr(tail, 'name', '?')!r}）")
    cards = [m for m in state["messages"]
             if isinstance(m, SystemMessage) and m.id == MEMORY_CARD_MESSAGE_ID]
    check(section, len(cards) == 0,
          "无记忆卡残留（本轮 uid 未提供 ⇒ not_attempted，不该有固定 ID 卡）")
    handoff_leak = [m for m in state["messages"]
                    if "Successfully transferred" in str(m.content)
                    or "Transferring back" in str(m.content)]
    check(section, not handoff_leak,
          "外层 State 无 handoff 控制消息泄漏（add_handoff_messages / add_handoff_back 未写入）")


async def scenario_direct_answer() -> None:
    S = "S1"
    print(f"\n[{S} Supervisor 直答] query='你好，简单介绍下你自己'")

    direct = _MODELS["supervisor"].aim("你好！我是 408 考研辅导助手，负责讲解、出题与批改。")
    _MODELS["supervisor"].reset([direct])
    _MODELS["knowledge"].reset([]), _MODELS["question"].reset([]), _MODELS["grading"].reset([])

    state = await run_graph("你好，简单介绍下你自己", S)

    check(S, _MODELS["supervisor"].calls == 1,
          "Supervisor 模型调用 1 次即结束（无 tool_calls ⇒ react 子图自然收敛）")
    check(S, _MODELS["knowledge"].calls == 0 and _MODELS["question"].calls == 0
          and _MODELS["grading"].calls == 0, "三个专家均未被调用（calls=0）")
    handoff_leak = [m for m in state["messages"] if "transfer_to" in str(getattr(m, "tool_calls", ""))]
    check(S, not handoff_leak, "无分派控制痕迹（未产生 handoff）")
    _common_state_checks(state, S, task_mode="chat", active_agent=None, final=direct)


async def scenario_knowledge() -> None:
    S = "S2"
    print(f"\n[{S} knowledge_agent 正常执行] query='什么是二叉搜索树？'")
    route = _MODELS["supervisor"].aim(
        "", tool_calls=[{"name": "transfer_to_knowledge_agent", "args": {}, "id": "call_route"}]
    )
    final = _MODELS["knowledge"].aim(
        "二叉搜索树（BST）：左子树所有节点小于根，右子树所有节点大于根，"
        "中序遍历得到升序序列。"
    )
    _MODELS["supervisor"].reset([route])
    _MODELS["knowledge"].reset([
        _MODELS["knowledge"].aim("", tool_calls=[
            {"name": "knowledge_search", "args": {"query": "二叉搜索树"}, "id": "call_k1"}
        ]),
        final,
    ])
    _MODELS["question"].reset([]), _MODELS["grading"].reset([])

    with stubs("retrieve_ok"):
        state = await run_graph("什么是二叉搜索树？", S)

    check(S, _MODELS["supervisor"].calls == 1, "Supervisor 仅 1 次调用：完成路由后不再进入 LLM")
    check(S, _MODELS["knowledge"].calls == 2, "knowledge 模型调用 2 次：1 次决定调工具 + 1 次终答")
    check(S, _MODELS["knowledge"].saw_tool_text("二叉搜索树", "知识库中未找到相关内容") is False
          and _MODELS["knowledge"].saw_tool_text("status", "ok"),
          "knowledge_search 工具真实执行：检索载荷（status=ok）到达知识讲解模型")
    _common_state_checks(state, S, task_mode="knowledge", active_agent="knowledge_agent", final=final)


async def scenario_question() -> None:
    S = "S3"
    print(f"\n[{S} question_agent 正常执行] query='请出 1 道关于平衡二叉树的基础选择题'")
    route = _MODELS["supervisor"].aim(
        "", tool_calls=[{"name": "transfer_to_question_agent", "args": {}, "id": "call_route"}]
    )
    final = _MODELS["question"].aim(
        "**题目1**\n类型：选择\n难度：基础\n题干：关于平衡二叉树的单选题（验证脚本预置）"
    )
    _MODELS["supervisor"].reset([route])
    _MODELS["question"].reset([
        _MODELS["question"].aim("", tool_calls=[
            {"name": "generate_practice_questions",
             "args": {"topic": "平衡二叉树", "count": 1, "difficulty": "basic"},
             "id": "call_q1"}
        ]),
        final,
    ])
    _MODELS["knowledge"].reset([]), _MODELS["grading"].reset([])

    with stubs("question_ok"):
        state = await run_graph("请出 1 道关于平衡二叉树的基础选择题", S)

    check(S, _MODELS["supervisor"].calls == 1, "Supervisor 仅 1 次调用（路由后短路）")
    check(S, _MODELS["question"].calls == 2, "question 模型调用 2 次：1 次工具调用 + 1 次终答")
    check(
        S,
        _MODELS["question"].saw_tool_text("题目1", "标准答案：A"),
        "generate_practice_questions 工具执行：结构化题目渲染为对话体到达出题模型",
    )
    check(
        S,
        not any("Error" in t and "Traceback" in t for t in _MODELS["question"].tool_traffic),
        "工具链无异常被静默吞成 Error ToolMessage",
    )
    _common_state_checks(state, S, task_mode="question", active_agent="question_agent", final=final)


async def scenario_grading() -> None:
    S = "S4"
    print(f"\n[{S} grading_agent 正常执行] query='帮我批改：中序遍历是不是升序？我的答案：对'")
    route = _MODELS["supervisor"].aim(
        "", tool_calls=[{"name": "transfer_to_grading_agent", "args": {}, "id": "call_route"}]
    )
    final = _MODELS["grading"].aim("评分：95/100\n结论：正确，中序遍历严格递增即 BST 定理。")
    _MODELS["supervisor"].reset([route])
    _MODELS["grading"].reset([
        _MODELS["grading"].aim("", tool_calls=[
            {"name": "grade_student_answer",
             "args": {"stem": "判断：二叉搜索树的中序遍历一定是升序序列。",
                      "user_answer": "对",
                      "standard_answer": "对。中序遍历严格递增是 BST 定理的直接推论。"},
             "id": "call_g1"}
        ]),
        final,
    ])
    _MODELS["knowledge"].reset([]), _MODELS["question"].reset([])

    with stubs("grade_ok"):
        state = await run_graph("帮我批改：判断我的作答是否正确，我的答案：对", S)

    check(S, _MODELS["supervisor"].calls == 1, "Supervisor 仅 1 次调用（路由后短路）")
    check(S, _MODELS["grading"].calls == 2, "grading 模型调用 2 次：1 次工具调用 + 1 次终答")
    check(S, _MODELS["grading"].saw_tool_text("评分：95/100"),
          "grade_student_answer 工具执行：结构化批改渲染（评分/结论）到达批改模型")
    check(
        S,
        not any("Error" in t and "Traceback" in t for t in _MODELS["grading"].tool_traffic),
        "工具链无异常被静默吞成 Error ToolMessage",
    )
    _common_state_checks(state, S, task_mode="grading", active_agent="grading_agent", final=final)


async def scenario_retrieval_error() -> None:
    S = "S5"
    print(f"\n[{S} 工具失败传递：检索依赖不可用（knowledge）]"
          " retrieve_for_task 抛 RetrievalUnavailable")
    route = _MODELS["supervisor"].aim(
        "", tool_calls=[{"name": "transfer_to_knowledge_agent", "args": {}, "id": "call_route"}]
    )
    final = _MODELS["knowledge"].aim("检索暂时不可用，本轮无法基于知识库作答，建议稍后重试。")
    _MODELS["supervisor"].reset([route])
    _MODELS["knowledge"].reset([
        _MODELS["knowledge"].aim("", tool_calls=[
            {"name": "knowledge_search", "args": {"query": "什么是进程？"}, "id": "call_k1"}
        ]),
        final,
    ])
    _MODELS["question"].reset([]), _MODELS["grading"].reset([])

    # 关键：不替换 _retrieve_payload —— 让真实的异常分级 → 载荷映射链路完整执行
    with stubs("retrieve_fail"):
        state = await run_graph("什么是进程？", S)

    check(S, _MODELS["knowledge"].saw_tool_text("检索失败"),
          "工具 catch 住异常并生成 status=error 载荷（进程未崩溃，错误文本到达模型）")
    check(S, _MODELS["knowledge"].saw_tool_text("知识库服务暂时不可用，请稍后重试"),
          "错误文案 = 可重试语义（RetrievalUnavailable 分级正确）")
    check(S, _MODELS["knowledge"].saw_tool_text("unavailable"),
          "机器可读分类 error_kind=unavailable 进入载荷")
    check(S, _MODELS["knowledge"].calls == 2,
          "专家模型收到失败 ToolMessage 后仍被再次调用（错误真实到达模型，calls=2）")
    check(S, _MODELS["supervisor"].calls == 1, "Supervisor 仍仅 1 次调用（失败没有触发二次复述）")
    _common_state_checks(state, S, task_mode="knowledge", active_agent="knowledge_agent", final=final)


async def scenario_grade_error() -> None:
    S = "S6"
    print(f"\n[{S} 工具失败传递：批改失败（grading）]"
          " standard_answer 为空 ⇒ 工具先检索标准答案，该检索失败")
    route = _MODELS["supervisor"].aim(
        "", tool_calls=[{"name": "transfer_to_grading_agent", "args": {}, "id": "call_route"}]
    )
    final = _MODELS["grading"].aim("批改失败：无法检索到评分依据，请稍后重试或直接提供标准答案。")
    _MODELS["supervisor"].reset([route])
    _MODELS["grading"].reset([
        _MODELS["grading"].aim("", tool_calls=[
            {"name": "grade_student_answer",
             "args": {"stem": "TCP 三次握手的作用是什么？", "user_answer": "建立连接"},
             "id": "call_g1"}
        ]),
        final,
    ])
    _MODELS["knowledge"].reset([]), _MODELS["question"].reset([])

    with stubs("retrieve_fail"):
        state = await run_graph("帮我批改：TCP 三次握手的作用？我的答案：建立连接", S)

    check(S, _MODELS["grading"].saw_tool_text("批改失败：检索标准答案失败")
          and _MODELS["grading"].saw_tool_text("TEI 宕机"),
          "批改工具把检索失败转成显式 '批改失败：检索标准答案失败（TEI 宕机）'，而非静默用空 std")
    check(S, _MODELS["grading"].calls == 2, "grading 模型收到失败 ToolMessage 后给出兜底终答（calls=2）")
    check(S, _MODELS["supervisor"].calls == 1, "Supervisor 仍仅 1 次调用")
    _common_state_checks(state, S, task_mode="grading", active_agent="grading_agent", final=final)


async def scenario_question_error() -> None:
    S = "S7"
    print(f"\n[{S} 工具失败传递：出题失败（question）] agenerate_question_set 抛 RuntimeError")
    route = _MODELS["supervisor"].aim(
        "", tool_calls=[{"name": "transfer_to_question_agent", "args": {}, "id": "call_route"}]
    )
    final = _MODELS["question"].aim("出题失败：结构化输出校验未通过，请换一个知识点或稍后再试。")
    _MODELS["supervisor"].reset([route])
    _MODELS["question"].reset([
        _MODELS["question"].aim("", tool_calls=[
            {"name": "generate_practice_questions",
             "args": {"topic": "哈夫曼树", "count": 1, "difficulty": "basic"},
             "id": "call_q1"}
        ]),
        final,
    ])
    _MODELS["knowledge"].reset([]), _MODELS["grading"].reset([])

    with stubs("question_fail"):
        state = await run_graph("请出 1 道哈夫曼树的题", S)

    check(S, _MODELS["question"].saw_tool_text("出题失败：结构化输出两次校验未通过"),
          "出题工具失败原因（原始 exception 文本）经 ToolMessage 到达模型，无吞错")
    check(S, _MODELS["question"].calls == 2, "question 模型收到失败后仍闭环（calls=2）")
    check(S, _MODELS["supervisor"].calls == 1, "Supervisor 仍仅 1 次调用")
    _common_state_checks(state, S, task_mode="question", active_agent="question_agent", final=final)


# ─────────────────────────────────────────────────────────────────────────────
# 4. 专家级失败与多轮/Checkpointer 场景
# ─────────────────────────────────────────────────────────────────────────────


async def scenario_specialist_hard_failure() -> None:
    """S8 专家失败：specialist 模型在 react 子图内硬抛异常 ⇒ 异常分段包装上抛。

    与 S5–S7 的区别：工具级失败由工具的 catch 转成错误载荷（软失败，专家仍闭环），
    这里是**模型调用本身炸掉**——没有任何一层的 ToolMessage 能兜住它，
    必须原样穿透到 ``run_supervisor`` 的 except 分支并包装为 ``SupervisorRunError``。
    """
    S = "S8"
    print(f"\n[{S} 专家失败传递：knowledge 模型在子图内硬抛 RuntimeError]")
    route = _MODELS["supervisor"].aim(
        "", tool_calls=[{"name": "transfer_to_knowledge_agent", "args": {}, "id": "call_route"}]
    )
    _MODELS["supervisor"].reset([route])
    _MODELS["knowledge"].reset([Boom("知识模型运行时崩溃")])
    _MODELS["question"].reset([]), _MODELS["grading"].reset([])

    # retrieve_fail 是防御性 stub（保证全程离线）；本场景预期根本走不到检索这一步
    with stubs("retrieve_fail"):
        exc: BaseException | None = None
        try:
            await run_graph("什么是二叉搜索树？", S)
        except BaseException as e:  # noqa: BLE001 —— 这里捕获的是「被验证的传递路径」本身
            exc = e

    check(S, exc is not None, "专家模型硬崩溃 ⇒ edu_supervisor.ainvoke 上抛异常（未静默返回）")
    if not check(S, isinstance(exc, SupervisorRunError),
                 f"内层失败被 run_supervisor 包装为 SupervisorRunError"
                 f"（实际 {type(exc).__name__ if exc else '无异常'}）"):
        return
    assert exc is not None
    check(S, stage_of(exc) == "supervisor",
          "stage_of(SupervisorRunError) == 'supervisor'（服务层 _mark_failed 的 stage 来源）")
    check(S, not isinstance(exc, SpecialistRunError),
          "非 UnclosedSpecialistOutput 类失败（那类会映射 specialist，由真实图难以复现，单测锁定）")
    check(S, "知识模型运行时崩溃" in str(exc) and "预置崩溃" in str(exc),
          "原始异常文本完整保留在包装链中（可归因到专家内部，而非吞成模糊错误）")
    check(S, _MODELS["knowledge"].calls == 1,
          "knowledge 模型确实被调用过 1 次（崩溃发生在第一次模型调用）")
    check(S, _MODELS["supervisor"].calls == 1,
          "Supervisor 已完成路由（1 次调用）就收到失败，未进入二次复述")


async def scenario_multiturn_checkpointer() -> None:
    """S9 多轮对话 + Checkpointer 磁盘恢复（真实 AsyncSqliteSaver，非 mock）。

    关键设计：第 2 轮的 ``AsyncSqliteSaver`` 是**全新连接**（第 1 轮的那条已关闭），
    进程里没有任何残留的图状态 —— 若第 2 轮还能看到第 1 轮的消息，
    只能说明 checkpoint 落在磁盘上并被恢复。与 service 层同口径：
    编译图不带 checkpointer，由调用方挂（``agent.checkpointer = saver``）。
    """
    S = "S9"
    print(f"\n[{S} 多轮对话 + Checkpointer 磁盘恢复]"
          " 同一 thread 两轮，第 2 轮换全新 saver 连接")

    ckdb = Path("data/tmp/verify_agent_chain_ck.sqlite3")
    ckdb.parent.mkdir(parents=True, exist_ok=True)
    ckdb.unlink(missing_ok=True)

    # ── 第 1 轮：knowledge 正常执行（脚本与 S2 同构）──────────────────────────
    q1 = "什么是二叉搜索树？"
    final1 = _MODELS["knowledge"].aim(
        "二叉搜索树（BST）：左子树所有节点小于根，右子树所有节点大于根，"
        "中序遍历得到升序序列。"
    )
    _MODELS["supervisor"].reset([
        _MODELS["supervisor"].aim("", tool_calls=[
            {"name": "transfer_to_knowledge_agent", "args": {}, "id": "call_route_t1"}])
    ])
    _MODELS["knowledge"].reset([
        _MODELS["knowledge"].aim("", tool_calls=[
            {"name": "knowledge_search", "args": {"query": "二叉搜索树"}, "id": "call_k_t1"}]),
        final1,
    ])
    _MODELS["question"].reset([]), _MODELS["grading"].reset([])

    state1: dict | None = None
    try:
        async with AsyncSqliteSaver.from_conn_string(str(ckdb)) as saver:
            # 与 service.lifespan 同口径：编译图不带 checkpointer，调用方挂载
            edu_supervisor.checkpointer = saver  # type: ignore[.assignment]
            with stubs("retrieve_ok"):
                state1 = await run_graph(q1, S)
    finally:
        edu_supervisor.checkpointer = None

    check(S, state1 is not None and state1.get("task_status") == "completed",
          "第 1 轮正常完成（task_status == completed）")
    check(S, _MODELS["supervisor"].calls == 1 and _MODELS["knowledge"].calls == 2,
          "第 1 轮模型调用：supervisor 1 次路由 + knowledge 2 次（工具轮 + 终答轮）")
    if state1 is None:
        return
    check(S, len(state1["messages"]) == 2,
          f"第 1 轮外层 State 只有 2 条实质消息（H + 终答，实际 {len(state1['messages'])}）")
    check(S, str(state1["messages"][0].content) == q1 and str(state1["messages"][1].content) == str(final1.content),
          "第 1 轮消息序 = [HumanQuestion, 专家终答]")

    # ── 第 2 轮：全新 saver 连接 → 先证明磁盘 checkpoint 可读，再跑第二轮 ──────
    q2 = "请基于刚才讲的 BST 出 1 道选择题，标准答案解析都要"
    final2 = _MODELS["question"].aim(
        "**题目**：下列关于 BST 的说法哪项正确？\n标准答案：A（中序遍历升序）\n解析：见上一轮讲解。"
    )
    _MODELS["supervisor"].reset([
        _MODELS["supervisor"].aim("", tool_calls=[
            {"name": "transfer_to_question_agent", "args": {}, "id": "call_route_t2"}])
    ])
    _MODELS["question"].reset([
        _MODELS["question"].aim("", tool_calls=[
            {"name": "generate_practice_questions",
             "args": {"topic": "BST", "count": 1, "difficulty": "basic"}, "id": "call_q_t2"}]),
        final2,
    ])
    _MODELS["knowledge"].reset([]), _MODELS["grading"].reset([])

    state2: dict | None = None
    try:
        async with AsyncSqliteSaver.from_conn_string(str(ckdb)) as saver2:
            edu_supervisor.checkpointer = saver2  # type: ignore[assignment]
            snap = await edu_supervisor.aget_state(_make_config(S))
            restored = (snap.values or {}).get("messages") if snap is not None else None

            check(S, restored is not None and len(restored) == 2,
                  f"全新 saver 连接能读到第 1 轮 checkpoint（恢复来源=磁盘，非进程内存，"
                  f"实际恢复 {len(restored or [])} 条）")
            check(S, bool(restored) and str(restored[0].content) == q1
                  and str(restored[1].content) == str(final1.content),
                  "恢复内容包括第 1 轮 Human + 专家终答（原文逐字节一致）")
            if snap is not None and (snap.values or {}).get("context_mode") is not None:
                check(S, snap.values.get("context_mode") == state1.get("context_mode"),
                      f"context_mode 线程级延续（第 1 轮 = "
                      f"{state1.get('context_mode')!r}，恢复后 = {snap.values.get('context_mode')!r}）")

            with stubs("question_ok"):
                state2 = await run_graph(q2, S)
    finally:
        edu_supervisor.checkpointer = None

    if not check(S, state2 is not None, "第 2 轮完成（未崩溃）"):
        return
    texts = [str(m.content) for m in state2["messages"]]
    check(S, len(texts) == 4 and texts == [q1, str(final1.content), q2, str(final2.content)],
          f"完整跨轮历史入 State（第 1 轮 Human+终答 + 第 2 轮 Human+终答，实际 {len(texts)} 条）")
    _common_state_checks(state2, S,
                         task_mode="question", active_agent="question_agent", final=final2)
    check(S, _MODELS["supervisor"].calls == 1 and _MODELS["question"].calls == 2,
          "第 2 轮模型调用：supervisor 1 次路由 + question 2 次（表明确实重置为新脚本，无跨轮重放）")
    ckdb.unlink(missing_ok=True)


# ─────────────────────────────────────────────────────────────────────────────
# 5. 汇总
# ─────────────────────────────────────────────────────────────────────────────


async def _run_all() -> int:
    scenarios: list[tuple[str, object]] = [
        ("S1", scenario_direct_answer),
        ("S2", scenario_knowledge),
        ("S3", scenario_question),
        ("S4", scenario_grading),
        ("S5", scenario_retrieval_error),
        ("S6", scenario_grade_error),
        ("S7", scenario_question_error),
        ("S8", scenario_specialist_hard_failure),
        ("S9", scenario_multiturn_checkpointer),
    ]
    broke: list[str] = []
    for name, fn in scenarios:
        try:
            await fn()  # type: ignore[operator]
        except Exception as exc:  # noqa: BLE001 —— 未预期异常也要显式可见，而不是中断全部场景
            broke.append(name)
            print(f"    ✗ [{name}] 场景执行期未预期异常 {type(exc).__name__}: {exc}")
            import traceback
            traceback.print_exc()

    print("\n" + "=" * 72)
    failures = [(s, d) for (s, ok, d) in _REPORT if not ok]
    for name in broke:
        failures.append((name, "场景执行期抛出未预期异常"))
    if failures:
        print(f"验证 FAIL：{len(failures)} 条断言未通过")
        for s, d in failures:
            print(f"  - [{s}] {d}")
        return 1
    print("验证 PASS：主链路九场景全部通过")
    print("  S1 直答 ✓ · S2/S3/S4 三专家 ✓ · S5/S6/S7 工具失败传递 ✓ · "
          "S8 专家硬失败 ✓ · S9 多轮+Checkpointer 恢复 ✓ · 外层 State 落点 ✓")
    return 0


def main() -> int:
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    return asyncio.run(_run_all())


if __name__ == "__main__":
    raise SystemExit(main())
