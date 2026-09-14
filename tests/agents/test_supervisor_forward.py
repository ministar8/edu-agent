"""supervisor「专家答案即终答」：pre_model_hook 短路逻辑与最小闭环集成。

用脚本化假模型强制触发 handoff（分派 → 专家 → 回流 supervisor），
断言：专家原文是最终消息、控制消息不入历史、supervisor 不做二次复述。
此前 FakeToolModel 永不发工具调用，整条 handoff 路径零覆盖。
"""

import importlib

import pytest
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, MessagesState, StateGraph
from langgraph.types import Command
from langgraph_supervisor import create_supervisor

from agents.supervisor import (
    UnclosedSpecialistOutput,
    forward_after_agent,
    make_forward_after_agent,
)


class ScriptedModel(FakeMessagesListChatModel):
    """按队列返回预设消息的假模型；支持 bind_tools（返回自身）。"""

    def bind_tools(self, tools, *, tool_choice=None, **kwargs):  # noqa: ARG002
        return self


def _transfer_call(tool_name: str, call_id: str) -> dict:
    return {"name": tool_name, "args": {}, "id": call_id, "type": "tool_call"}


# ── 1. hook 单元测试 ──────────────────────────────────────────


def test_hook_ends_when_expert_final():
    hook = make_forward_after_agent({"knowledge_agent"})
    state = {
        "messages": [
            HumanMessage(content="问题"),
            AIMessage(content="专家答案", name="knowledge_agent"),
        ]
    }
    result = hook(state)
    assert isinstance(result, Command)
    # 必须 PARENT 作用域：本地 Command(goto=END) 在 langgraph 1.x 无法覆盖
    # pre_model_hook → agent 的静态边（实测仍会进 LLM 节点导致死循环）
    assert result.graph == Command.PARENT
    assert result.goto == END


@pytest.mark.parametrize(
    "messages",
    [
        pytest.param([], id="empty"),
        pytest.param([HumanMessage(content="问题")], id="human-last"),
        pytest.param(
            [
                HumanMessage(content="问题"),
                AIMessage(
                    content="",
                    tool_calls=[_transfer_call("transfer_to_knowledge_agent", "c1")],
                ),
            ],
            id="routing-with-tool-calls",
        ),
        pytest.param(
            [HumanMessage(content="问题"), AIMessage(content="专家答案")],
            id="ai-without-expert-name",
        ),
        pytest.param(
            [
                HumanMessage(content="问题"),
                ToolMessage(content="工具结果", tool_call_id="c1"),
            ],
            id="tool-message-last",
        ),
    ],
)
def test_hook_falls_through_to_llm(messages):
    """非专家终答（首轮路由 / 寒暄 / 专家异常收尾）一律放行给 supervisor LLM。"""
    assert (
        make_forward_after_agent({"knowledge_agent"})(  # type: ignore[arg-type]
            {"messages": messages}
        )
        == {}
    )


def test_production_hook_covers_all_specialists():
    assert (
        forward_after_agent({"messages": [AIMessage(content="答案", name="question_agent")]}).goto
        == END
    )
    assert (
        forward_after_agent({"messages": [AIMessage(content="答案", name="grading_agent")]}).goto
        == END
    )


# ── 1b. 专家未闭环输出：fail fast（不放行给 LLM）────────────────


def _unclosed_ai(name: str, n_calls: int = 1) -> AIMessage:
    """专家发起了 n_calls 个工具调用、尚未拿到（全部）结果的 AI 消息。"""
    return AIMessage(
        content="我去查一下资料",
        name=name,
        tool_calls=[
            {"name": f"tool_{i}", "args": {}, "id": f"c{i}", "type": "tool_call"}
            for i in range(1, n_calls + 1)
        ],
    )


@pytest.mark.parametrize(
    "messages",
    [
        pytest.param([_unclosed_ai("knowledge_agent")], id="bare-unclosed-ai"),
        pytest.param(
            [
                _unclosed_ai("knowledge_agent", 2),
                ToolMessage(content="只回了一个结果", tool_call_id="c1"),
            ],
            id="two-calls-one-result",
        ),
        pytest.param(
            [HumanMessage(content="问题"), _unclosed_ai("grading_agent")],
            id="unclosed-after-history",
        ),
    ],
)
def test_hook_fails_fast_on_unclosed_specialist(messages):
    """专家以未闭环 tool_calls 收尾时必须抛错，而不是放行给 supervisor LLM。

    放行的后果实测有两种，都指向不了病因：末条带 tool_calls 的 AI 留在 state，
    下一次模型调用被 _validate_chat_history 判为「tool_call 无对应 ToolMessage」，
    或反复分派同一专家直至 GraphRecursionError。故改为 fail fast。
    """
    hook = make_forward_after_agent({"knowledge_agent", "grading_agent"})
    with pytest.raises(UnclosedSpecialistOutput) as exc:
        hook({"messages": messages})  # type: ignore[arg-type]
    # 错误信息必须点明是哪位专家，才能一眼定位
    assert "knowledge_agent" in str(exc.value) or "grading_agent" in str(exc.value)


def test_hook_does_not_flag_tool_only_tail():
    """尾部只有 ToolMessage（AI 已被 last_message 切掉）不算未闭环 —— 不误伤。

    真实场景：专家发 N 个工具、全部配对但没有终答时，切片产出的是 [Tool, ...]，
    此时应放行让 supervisor 收尾，而非报错。
    """
    hook = make_forward_after_agent({"knowledge_agent"})
    tail = [
        ToolMessage(content="结果1", tool_call_id="c1"),
        ToolMessage(content="结果2", tool_call_id="c2"),
    ]
    assert hook({"messages": tail}) == {}  # type: ignore[arg-type]


def test_hook_ignores_supervisor_own_tool_calls():
    """supervisor 自己的分派 tool_call（无专家 name）不是未闭环，必须放行。

    分派消息是 AI(tool_calls) 但 name 为 None/supervisor；若被误判成专家未闭环，
    首次路由就会直接崩溃。
    """
    hook = make_forward_after_agent({"knowledge_agent"})
    routing = AIMessage(
        content="",
        tool_calls=[
            {"name": "transfer_to_knowledge_agent", "args": {}, "id": "c1", "type": "tool_call"}
        ],
    )
    assert hook({"messages": [HumanMessage(content="问题"), routing]}) == {}  # type: ignore[arg-type]


# ── 1c. 装配期一致性校验（P1）──────────────────────────────────


def test_specialist_names_rejects_missing_name():
    """专家缺 name 时装配期即报错：handoff 与短路都依赖它。"""
    from agents.supervisor import _specialist_names

    class _NoName:
        pass

    with pytest.raises(ValueError, match="缺少 name"):
        _specialist_names((_NoName(),))


def test_specialist_names_rejects_duplicates():
    """专家 name 重复时装配期即报错。"""
    from agents.supervisor import _specialist_names

    class _Dup:
        name = "knowledge_agent"

    with pytest.raises(ValueError, match="重复"):
        _specialist_names((_Dup(), _Dup()))


def test_production_hook_whitelist_matches_specialists():
    """白名单与专家集合必须一致（P1）：生产 hook 的 name 集合等于专家集合。

    这是把「改名/漏配导致短路静默失效」变成启动期崩溃的守卫；此处验证生产
    装配后的不变量成立（装配期已有 _assert_hook_covers_specialists 强制）。
    """
    import agents.supervisor as supervisor_module

    assert set(supervisor_module.forward_after_agent.agent_names) == {  # type: ignore[attr-defined]
        "knowledge_agent",
        "question_agent",
        "grading_agent",
    }


def test_assembly_rejects_mismatched_whitelist():
    """装配期校验必须真的会拦下不一致的白名单（否则守卫形同虚设）。"""
    from agents.supervisor import _assert_hook_covers_specialists

    class _Expert:
        name = "knowledge_agent"

    mismatched = make_forward_after_agent({"typo_agent"})
    with pytest.raises(ValueError, match="不一致"):
        _assert_hook_covers_specialists(mismatched, (_Expert(),))


# ── 2. 最小闭环集成（真实 create_supervisor 装配 + 脚本化模型）──


def _make_expert(name: str, reply: str, calls: list):
    """极简专家图：一次调用即返回带 name 的最终回答。"""

    def _run(state: MessagesState) -> dict:  # noqa: ARG001
        calls.append(1)
        return {"messages": [AIMessage(content=reply, name=name)]}

    builder = StateGraph(MessagesState)
    builder.add_node("run", _run)
    builder.set_entry_point("run")
    builder.add_edge("run", END)
    return builder.compile(name=name)


def _build_supervisor(supervisor_model, expert):
    """装配未编译的 supervisor StateGraph；调用方按需 compile(checkpointer=...)。"""
    return create_supervisor(
        [expert],
        model=supervisor_model,
        prompt="路由到专家",
        output_mode="last_message",
        add_handoff_messages=False,
        add_handoff_back_messages=False,
        pre_model_hook=make_forward_after_agent({"expert_a"}),
    )


def test_dispatch_path_expert_answer_is_final():
    """分派后专家原文即终答：无复述、无控制消息、supervisor 只调一次 LLM。

    调用次数由结构性证明：假模型应答耗尽后会循环复用第一答，若 supervisor
    在专家回流后再发起 LLM 调用，必然重新分派并死循环（GraphRecursionError）；
    invoke 能以恰好两条消息完成，即证明短路生效、只调了一次。
    """
    expert_calls: list = []
    expert = _make_expert("expert_a", "【专家答案】进程是资源分配的基本单位。", expert_calls)
    supervisor_model = ScriptedModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[_transfer_call("transfer_to_expert_a", "call-1")],
            )
        ]
    )
    graph = _build_supervisor(supervisor_model, expert).compile()

    result = graph.invoke({"messages": [HumanMessage(content="什么是进程？")]})

    messages = result["messages"]
    assert [type(m).__name__ for m in messages] == ["HumanMessage", "AIMessage"]
    assert messages[1].name == "expert_a"
    assert messages[1].content == "【专家答案】进程是资源分配的基本单位。"
    assert not any("transferred" in str(m.content).lower() for m in messages)
    assert len(expert_calls) == 1


def test_direct_answer_path_unchanged():
    """寒暄直答：supervisor 不分派，普通回复即结束。"""
    expert_calls: list = []
    expert = _make_expert("expert_a", "【专家答案】", expert_calls)
    supervisor_model = ScriptedModel(responses=[AIMessage(content="你好，祝你备考顺利！")])
    graph = _build_supervisor(supervisor_model, expert).compile()

    result = graph.invoke({"messages": [HumanMessage(content="你好")]})

    messages = result["messages"]
    assert [type(m).__name__ for m in messages] == ["HumanMessage", "AIMessage"]
    assert messages[1].content == "你好，祝你备考顺利！"
    assert expert_calls == []


def test_multi_turn_dispatch_keeps_history_clean():
    """两轮对话（带 checkpointer）：每轮专家答案入史，无控制消息累积。"""
    expert_calls: list = []
    expert = _make_expert("expert_a", "【专家答案】", expert_calls)
    responses = [
        AIMessage(content="", tool_calls=[_transfer_call("transfer_to_expert_a", "c1")]),
        AIMessage(content="", tool_calls=[_transfer_call("transfer_to_expert_a", "c2")]),
    ]
    supervisor_model = ScriptedModel(responses=responses)
    graph = _build_supervisor(supervisor_model, expert).compile(checkpointer=MemorySaver())
    config = {"configurable": {"thread_id": "t-multi"}}

    graph.invoke({"messages": [HumanMessage(content="第一问")]}, config=config)
    result = graph.invoke({"messages": [HumanMessage(content="第二问")]}, config=config)

    messages = result["messages"]
    kinds = [(type(m).__name__, getattr(m, "name", None)) for m in messages]
    assert kinds == [
        ("HumanMessage", None),
        ("AIMessage", "expert_a"),
        ("HumanMessage", None),
        ("AIMessage", "expert_a"),
    ]
    assert not any("transferred" in str(m.content).lower() for m in messages)
    assert len(expert_calls) == 2


# ── 3. 生产装配接线验证（reload + spy，避免只测副本）──────────


def test_production_supervisor_wires_forward_hook(monkeypatch):
    """生产 create_supervisor 必须传入 pre_model_hook 与干净的 handoff 配置。

    add_handoff_messages / output_mode 在 create_supervisor 内部消费，
    不会出现在 create_react_agent 的 kwargs 里，因此 spy 其外层入口。
    """
    import langgraph_supervisor as lgs_pkg

    import agents.supervisor as supervisor_module

    captured: dict = {}
    original = lgs_pkg.create_supervisor

    def spy(agents, **kwargs):
        captured.update(kwargs)
        return original(agents, **kwargs)

    monkeypatch.setattr(lgs_pkg, "create_supervisor", spy)
    try:
        importlib.reload(supervisor_module)

        assert captured.get("pre_model_hook") is supervisor_module.forward_after_agent
        assert captured.get("add_handoff_messages") is False
        assert captured.get("add_handoff_back_messages") is False
        assert captured.get("output_mode") == "last_message"
    finally:
        # reload 会重新执行模块级代码，生成**全新的类对象**（如
        # UnclosedSpecialistOutput）。若不复原，其他测试在收集期 from-import
        # 拿到的旧类与生产代码实际抛出的新类不再是同一个对象，isinstance /
        # pytest.raises 会全数失效（表现为「单独跑过、全量跑挂」）。
        # spy 由 monkeypatch 负责撤销，这里只把模块重载回干净状态；
        # reload 后 module 的属性会指向新对象，故需再 reload 一次。
        importlib.reload(supervisor_module)
