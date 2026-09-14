"""supervisor handoff 路径集成测试：跨「分派 → 专家 → 回流」的真实图闭环。

与 test_supervisor_forward.py 的分工：

- 前者是 hook 级单元测试 + 最小双节点闭环，证明短路逻辑本身成立；
- 本文件把真实 ``create_supervisor`` 装配、真实 handoff 工具（``transfer_to_*``）
  与 ``teaching_graph`` 的 load_memory/裁剪环节拼起来，验证端到端行为：
  分派后专家原文即终答、控制消息既不进 state 也不进用户可见流、多专家路由正确、
  多轮对话与消息窗口裁剪不失真。

专家图仍用脚本化假模型驱动（真实三个专家依赖 LLM 与 TEI，不适合单测），
但 supervisor 侧走真实 create_supervisor，handoff 工具与回流边都是库内真件。
"""

from __future__ import annotations

import pytest
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, MessagesState, StateGraph

from agents.supervisor import make_forward_after_agent

# UnclosedSpecialistOutput 必须在使用点从模块动态解析，不能 from-import：
# 同目录的 test_supervisor_forward 会用 importlib.reload 重载 agents.supervisor，
# 重载后模块里的类对象会被替换成新的，收集期拿到的旧类与生产代码实际抛出的
# 新类不再是同一个对象，pytest.raises 会漏接（单独跑过、全量跑挂）。


# ── 测试脚手架 ────────────────────────────────────────────────


class ScriptedModel(FakeMessagesListChatModel):
    """按队列返回预设消息的假模型；支持 bind_tools（返回自身）。

    队列耗尽后 FakeMessagesListChatModel 会循环复用首条应答 —— 配合
    ``GraphRecursionError`` 即可反证「supervisor 未被二次调用」。
    """

    def bind_tools(self, tools, *, tool_choice=None, **kwargs):  # noqa: ARG002
        return self


def _transfer_call(tool_name: str, call_id: str) -> dict:
    return {"name": tool_name, "args": {}, "id": call_id, "type": "tool_call"}


def _make_expert(name: str, reply: str, calls: list):
    """极简专家图：一次调用即返回带 name 的最终回答（模拟专家产出）。"""

    def _run(state: MessagesState) -> dict:  # noqa: ARG001
        calls.append(1)
        return {"messages": [AIMessage(content=reply, name=name)]}

    builder = StateGraph(MessagesState)
    builder.add_node("run", _run)
    builder.set_entry_point("run")
    builder.add_edge("run", END)
    return builder.compile(name=name)


def _build_supervisor(supervisor_model, experts: list, names: set[str], **overrides):
    """复刻生产 supervisor 装配参数（create_supervisor 真件），返回未编译的 StateGraph。

    与生产一致：``create_supervisor`` 返回 StateGraph，由调用方决定是否挂
    checkpointer 后 ``compile()``。
    """
    from langgraph_supervisor import create_supervisor

    kwargs = {
        "output_mode": "last_message",
        "add_handoff_messages": False,
        "add_handoff_back_messages": False,
        "pre_model_hook": make_forward_after_agent(names),
    }
    kwargs.update(overrides)
    return create_supervisor(experts, model=supervisor_model, prompt="路由到专家", **kwargs)


# ── 1. handoff 闭环：控制消息不落 state ───────────────────────


def test_dispatch_leaves_no_handoff_control_messages():
    """分派路径的 state 只含 Human + 专家终答，handoff 控制消息零残留。

    这是 add_handoff_messages=False / add_handoff_back_messages=False 的核心
    收益：否则 ``transfer_to_*`` 的 (AI tool_call, ToolMessage) 对与
    "Transferring back to supervisor" 会写进消息历史，既污染 /history 又会在
    后续轮次混入模型上下文。
    """
    expert_calls: list = []
    expert = _make_expert("knowledge_agent", "【知识讲解】进程是资源分配的基本单位。", expert_calls)
    supervisor_model = ScriptedModel(
        responses=[
            AIMessage(content="", tool_calls=[_transfer_call("transfer_to_knowledge_agent", "c1")])
        ]
    )
    graph = _build_supervisor(supervisor_model, [expert], {"knowledge_agent"}).compile()

    result = graph.invoke({"messages": [HumanMessage(content="什么是进程？")]})
    messages = result["messages"]

    assert [type(m).__name__ for m in messages] == ["HumanMessage", "AIMessage"]
    assert messages[-1].name == "knowledge_agent"
    assert messages[-1].content == "【知识讲解】进程是资源分配的基本单位。"
    # 无任何 tool 类控制消息（handoff 的 AI tool_calls / ToolMessage 都应缺席）
    assert not any(isinstance(m, ToolMessage) for m in messages)
    assert not any(getattr(m, "tool_calls", None) for m in messages)
    assert not any("transfer" in str(m.content).lower() for m in messages)
    assert len(expert_calls) == 1


def test_expert_answer_not_rewritten_by_supervisor():
    """专家原文必须逐字保留 —— supervisor 零 LLM 收尾，不做二次复述。

    反证调用次数：假模型队列只有一条应答，若回流后 supervisor 再调 LLM，
    会复用首条应答重新分派 → 死循环 → GraphRecursionError。invoke 能正常
    返回即证明短路生效、只调了一次。
    """
    expert_calls: list = []
    expert = _make_expert("grading_agent", "得分：8/10\n失分点：未说明抢占式调度。", expert_calls)
    supervisor_model = ScriptedModel(
        responses=[
            AIMessage(content="", tool_calls=[_transfer_call("transfer_to_grading_agent", "g1")])
        ]
    )
    graph = _build_supervisor(supervisor_model, [expert], {"grading_agent"}).compile()

    result = graph.invoke({"messages": [HumanMessage(content="批改我的答案")]})

    assert result["messages"][-1].content == "得分：8/10\n失分点：未说明抢占式调度。"
    assert len(expert_calls) == 1


# ── 2. 多专家路由：分派目标正确 ───────────────────────────────


@pytest.mark.parametrize(
    ("agent_name", "reply"),
    [
        pytest.param("knowledge_agent", "【知识讲解】", id="knowledge"),
        pytest.param("question_agent", "【练习题】", id="question"),
        pytest.param("grading_agent", "【批改结果】", id="grading"),
    ],
)
def test_each_specialist_is_reachable(agent_name, reply):
    """三个专家各自可被 transfer_to_<name> 命中，终答 name 与之一致。"""
    calls: list = []
    expert = _make_expert(agent_name, reply, calls)
    supervisor_model = ScriptedModel(
        responses=[
            AIMessage(content="", tool_calls=[_transfer_call(f"transfer_to_{agent_name}", "c")])
        ]
    )
    graph = _build_supervisor(supervisor_model, [expert], {agent_name}).compile()

    result = graph.invoke({"messages": [HumanMessage(content="请求")]})

    assert result["messages"][-1].name == agent_name
    assert result["messages"][-1].content == reply
    assert len(calls) == 1


def test_dispatch_to_second_expert_after_first():
    """多专家同图：两轮分别路由到不同专家，回流不会串台。"""
    kn_calls: list = []
    q_calls: list = []
    knowledge = _make_expert("knowledge_agent", "【知识讲解】", kn_calls)
    question = _make_expert("question_agent", "【练习题】", q_calls)
    supervisor_model = ScriptedModel(
        responses=[
            AIMessage(content="", tool_calls=[_transfer_call("transfer_to_knowledge_agent", "c1")]),
            AIMessage(content="", tool_calls=[_transfer_call("transfer_to_question_agent", "c2")]),
        ]
    )
    graph = _build_supervisor(
        supervisor_model, [knowledge, question], {"knowledge_agent", "question_agent"}
    ).compile(checkpointer=MemorySaver())
    config = {"configurable": {"thread_id": "t-two-experts"}}

    graph.invoke({"messages": [HumanMessage(content="第一问")]}, config=config)
    result = graph.invoke({"messages": [HumanMessage(content="出一题")]}, config=config)

    kinds = [(type(m).__name__, getattr(m, "name", None)) for m in result["messages"]]
    assert kinds == [
        ("HumanMessage", None),
        ("AIMessage", "knowledge_agent"),
        ("HumanMessage", None),
        ("AIMessage", "question_agent"),
    ]
    assert len(kn_calls) == 1
    assert len(q_calls) == 1


# ── 3. 两轮对话：历史干净、控制消息不累积 ─────────────────────


def test_multi_turn_history_stays_clean():
    """带 checkpointer 两轮对话：每轮专家答案入史，无控制消息累积。

    回归点：旧实现下这两轮之间会多出 4 条 handoff 控制消息
    （每轮 2 条 transfer_back），本断言锁死「零残留」。
    """
    expert_calls: list = []
    expert = _make_expert("knowledge_agent", "【专家答案】", expert_calls)
    supervisor_model = ScriptedModel(
        responses=[
            AIMessage(content="", tool_calls=[_transfer_call("transfer_to_knowledge_agent", "c1")]),
            AIMessage(content="", tool_calls=[_transfer_call("transfer_to_knowledge_agent", "c2")]),
        ]
    )
    graph = _build_supervisor(supervisor_model, [expert], {"knowledge_agent"}).compile(
        checkpointer=MemorySaver()
    )
    config = {"configurable": {"thread_id": "t-multi-turn"}}

    graph.invoke({"messages": [HumanMessage(content="第一问")]}, config=config)
    result = graph.invoke({"messages": [HumanMessage(content="第二问")]}, config=config)

    assert [type(m).__name__ for m in result["messages"]] == [
        "HumanMessage",
        "AIMessage",
        "HumanMessage",
        "AIMessage",
    ]
    assert all(getattr(m, "name", None) == "knowledge_agent" for m in result["messages"][1::2])
    assert len(expert_calls) == 2


def test_direct_answer_does_not_touch_expert():
    """寒暄直答：不分派、不触发专家，普通回复即结束。"""
    expert_calls: list = []
    expert = _make_expert("knowledge_agent", "【专家答案】", expert_calls)
    supervisor_model = ScriptedModel(responses=[AIMessage(content="你好，祝你备考顺利！")])
    graph = _build_supervisor(supervisor_model, [expert], {"knowledge_agent"}).compile()

    result = graph.invoke({"messages": [HumanMessage(content="你好")]})

    assert [type(m).__name__ for m in result["messages"]] == ["HumanMessage", "AIMessage"]
    assert result["messages"][-1].content == "你好，祝你备考顺利！"
    assert expert_calls == []


# ── 4. 与 teaching_graph 接线：记忆卡 + 窗口裁剪不破坏 handoff ──


@pytest.mark.asyncio
async def test_teaching_graph_wiring_trim_then_dispatch(monkeypatch):
    """teaching_graph 的裁剪 → supervisor 环节：裁剪后的消息仍能正常 handoff。

    run_supervisor 只把裁剪结果送进内层图，state 保留完整历史 —— 用 spy 捕获
    实际送入 inner_supervisor 的消息，断言：用户消息完整送达，且分派后专家
    终答成为最终消息。load_memory 仅实现 async，故走 ainvoke。
    """
    import agents.teaching_graph as tg

    captured: dict = {}

    class _SpySupervisor:
        async def ainvoke(self, payload, config=None):  # noqa: ARG002
            captured["sent"] = payload["messages"]
            # 模拟内层图产出：用户消息 + 专家终答
            return {
                "messages": [
                    *payload["messages"],
                    AIMessage(content="【知识讲解】终端设备。", name="knowledge_agent"),
                ]
            }

    monkeypatch.setattr(tg, "inner_supervisor", _SpySupervisor())
    graph = tg.build_teaching_graph()

    history = [
        HumanMessage(content="历史问题1"),
        AIMessage(content="历史回答1"),
        HumanMessage(content="当前问题"),
    ]
    result = await graph.ainvoke({"messages": history})

    sent = captured["sent"]
    # 记忆卡缺失时直接送原始消息；此处只验证用户消息完整送达
    assert [m.content for m in sent if isinstance(m, HumanMessage)] == ["历史问题1", "当前问题"]
    last = result["messages"][-1]
    assert isinstance(last, AIMessage)
    assert last.name == "knowledge_agent"
    assert last.content == "【知识讲解】终端设备。"


def test_trim_preserves_dispatch_pairs_after_handoff():
    """长历史裁剪后仍能被 supervisor 正常处理（工具对不残缺）。

    手工构造一段含「带 tool_calls 的 AI + ToolMessage」的历史 —— 这正是
    handoff 若泄漏进 state 会产生的形状；裁剪必须整体丢弃该残缺对手，
    而不是把它切一半送给模型。
    """
    from memory.window import trim_conversation

    history = [
        HumanMessage(content="老问题"),
        AIMessage(content="", tool_calls=[_transfer_call("transfer_to_knowledge_agent", "old-1")]),
        ToolMessage(content="Successfully transferred to knowledge_agent", tool_call_id="old-1"),
        AIMessage(content="【旧回答】", name="knowledge_agent"),
        HumanMessage(content="新问题"),
    ]

    trimmed = trim_conversation(history, max_messages=2)

    # 只留最近两条；首条是 Human 而非孤儿 Tool/带 tool_calls 的 AI
    assert [type(m).__name__ for m in trimmed] == ["AIMessage", "HumanMessage"]
    assert trimmed[0].content == "【旧回答】"
    assert not getattr(trimmed[0], "tool_calls", None)
    assert not any(isinstance(m, ToolMessage) for m in trimmed)


# ── 5. 专家未闭环：端到端 fail fast 取代误导性报错 ─────────────


def _make_unclosed_expert(name: str, n_calls: int = 2, n_results: int = 1):
    """专家以未闭环 tool_calls 收尾（发 N 个调用、只回 M 个结果）。"""

    def _run(state: MessagesState) -> dict:  # noqa: ARG001
        calls = [
            {"name": f"tool_{i}", "args": {}, "id": f"c{i}", "type": "tool_call"}
            for i in range(1, n_calls + 1)
        ]
        msgs: list = [
            AIMessage(content="我去查资料", name=name, tool_calls=calls, id="ai-unclosed")
        ]
        msgs += [
            ToolMessage(content=f"结果{i}", tool_call_id=f"c{i}", id=f"tm{i}")
            for i in range(1, n_results + 1)
        ]
        return {"messages": msgs}

    builder = StateGraph(MessagesState)
    builder.add_node("run", _run)
    builder.set_entry_point("run")
    builder.add_edge("run", END)
    return builder.compile(name=name)


def test_unclosed_specialist_fails_fast_not_recursion():
    """专家未闭环时抛 UnclosedSpecialistOutput，而非 GraphRecursionError / ValueError。

    回归点：此前该场景的报错是
      - GraphRecursionError（像是路由死循环），或
      - ValueError: Found AIMessages with tool_calls that do not have a
        corresponding ToolMessage（像是消息格式问题）
    两者都指向不了真凶「专家中途断了」。改为 fail fast 后错误自解释，
    且日志能直接看出是哪位专家。
    """
    supervisor_model = ScriptedModel(
        responses=[
            AIMessage(content="", tool_calls=[_transfer_call("transfer_to_knowledge_agent", "c1")])
        ]
    )
    graph = _build_supervisor(
        supervisor_model, [_make_unclosed_expert("knowledge_agent")], {"knowledge_agent"}
    ).compile()

    # 动态解析（而非 from-import），以免被 reload 换掉的类对象导致漏接
    import agents.supervisor as supervisor_module

    with pytest.raises(supervisor_module.UnclosedSpecialistOutput) as exc:
        graph.invoke({"messages": [HumanMessage(content="q")]}, config={"recursion_limit": 8})

    assert "knowledge_agent" in str(exc.value)


def test_closed_expert_with_tools_still_completes():
    """反例守卫：正常闭环的专家（多个工具全部配对 + 终答）不得被 fail fast 误伤。"""

    def _run(state: MessagesState) -> dict:  # noqa: ARG001
        calls = [
            {"name": f"tool_{i}", "args": {}, "id": f"c{i}", "type": "tool_call"}
            for i in range(1, 3)
        ]
        msgs: list = [
            AIMessage(content="查资料", name="knowledge_agent", tool_calls=calls, id="a1")
        ]
        msgs += [
            ToolMessage(content=f"结果{i}", tool_call_id=f"c{i}", id=f"t{i}") for i in range(1, 3)
        ]
        msgs.append(
            AIMessage(content="【最终回答】进程是资源分配的基本单位。", name="knowledge_agent")
        )
        return {"messages": msgs}

    builder = StateGraph(MessagesState)
    builder.add_node("run", _run)
    builder.set_entry_point("run")
    builder.add_edge("run", END)
    expert = builder.compile(name="knowledge_agent")

    supervisor_model = ScriptedModel(
        responses=[
            AIMessage(content="", tool_calls=[_transfer_call("transfer_to_knowledge_agent", "c1")])
        ]
    )
    graph = _build_supervisor(supervisor_model, [expert], {"knowledge_agent"}).compile()

    result = graph.invoke({"messages": [HumanMessage(content="q")]})

    assert [type(m).__name__ for m in result["messages"]] == ["HumanMessage", "AIMessage"]
    assert result["messages"][-1].content == "【最终回答】进程是资源分配的基本单位。"
