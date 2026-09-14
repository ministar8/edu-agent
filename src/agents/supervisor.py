"""多 Agent 编排：supervisor 路由到 knowledge / question / grading 三个专业 agent。

专家答案即终答：专家完成后由 ``forward_after_agent``（pre_model_hook）零 LLM
调用直接结束本轮，最终消息就是专家原文 —— supervisor 只做分派与寒暄直答，
不再对专家回答做二次复述（省一次完整生成，也避免改写破坏专家的输出格式）。

**专家输出契约**：专家必须以「带自身 name、无 tool_calls」的 AIMessage 收尾
（即一次完整的最终回答）。若专家以未闭环的 tool_calls 收尾，说明它中途断了
（撞步数上限 / 工具异常被吞 / ``last_message`` 切片把配对切坏）—— 此时**不能**
放行给 supervisor LLM：末条带 tool_calls 的 AI 留在 state 里，下一次模型调用会被
``_validate_chat_history`` 判定为「tool_call 没有对应 ToolMessage」而直接失败，
或陷入反复分派同一专家的递归。两种表现都指向不了真正的病因，故 fail fast。

**循环终止条件**（四条出口，均已实测）：

1. 寒暄直答 —— supervisor 输出无 tool_calls 的 AIMessage，react 子图自然结束；
2. 专家终答 —— ``forward_after_agent`` 以 ``Command(PARENT, goto=END)`` 短路，
   不再进入 supervisor LLM（这是常态路径，专家答案即终答）；
3. 专家未闭环 —— 抛 ``UnclosedSpecialistOutput``（见上）；
4. 兜底上限 —— ``settings.AGENT_RECURSION_LIMIT``，由 service 层写入
   ``RunnableConfig.recursion_limit``。**不设它会落到 LangGraph 默认的 10007**，
   异常循环要跑上万步才终止（每步至少一次 LLM 调用），故必须显式收紧。

注意专家子图与外层图**共享** recursion 预算：专家内部若陷入工具循环，同样会被
这条上限截断（实测确认）。因此它是一个全局护栏，而非只管 supervisor 往返。
"""

from dataclasses import dataclass

from langchain_core.messages import AIMessage, ToolMessage
from langgraph.graph import END
from langgraph.types import Command
from langgraph_supervisor import create_supervisor

from agents.grading_agent import grading_agent
from agents.knowledge_agent import knowledge_agent
from agents.question_agent import question_agent
from agents.temperature import TEMPERATURE_SUPERVISOR
from core import get_model, settings
from prompts import SUPERVISOR_PROMPT

_SPECIALISTS = (knowledge_agent, question_agent, grading_agent)


class UnclosedSpecialistOutput(RuntimeError):
    """专家以未闭环 tool_calls 收尾：合约被破坏，拒绝放行给 supervisor LLM。"""


@dataclass(frozen=True)
class _TailInspection:
    """尾部消息的归属判断结果。"""

    is_final_answer: bool  # 专家终答（带 name、无 tool_calls）
    unclosed_name: str | None  # 专家未闭环的 name；None 表示无此情况


_HANDOFF_BACK_FLAG = "__is_handoff_back"
"""``langgraph_supervisor`` 给回传控制消息打的 response_metadata 标记。

值为 ``True`` 的消息是库自己生成的「交还控制权」消息对
（``AIMessage(transfer_back_to_supervisor, tool_calls=[...])`` + 配套 ``ToolMessage``），
不是专家的业务输出。``_inspect_tail`` 必须跳过它们，否则会把这条带 tool_calls 的
AI 消息误认成「专家未闭环」而 fail-fast 误伤正常终答。"""


def _is_handoff_back(message) -> bool:
    """判断是否为库生成的「交还控制权」控制消息。"""
    metadata = getattr(message, "response_metadata", None) or {}
    return bool(metadata.get(_HANDOFF_BACK_FLAG))


def _inspect_tail(messages: list, names: frozenset[str]) -> _TailInspection:
    """判断消息尾部是「专家终答」还是「专家未闭环输出」。

    从尾部回溯，跨过连续的 ToolMessage 与库回传控制消息，找到最后一条实质消息：

    - 是某专家的 AIMessage 且无 tool_calls → 终答；
    - 是某专家的 AIMessage 且有 tool_calls → 未闭环（请求了工具但没拿到全部结果）；
    - 其他（Human / 非专家 AI / supervisor 自己的消息）→ 两种都不是。

    只跨过尾部的一段连续消息，不扫描整段历史，避免误伤正常的多轮记录。
    """
    i = len(messages) - 1
    while i >= 0:
        message = messages[i]
        # ToolMessage 与回传控制消息都不是专家的实质输出，继续向前找
        if isinstance(message, ToolMessage) or _is_handoff_back(message):
            i -= 1
            continue
        break
    if i < 0:
        return _TailInspection(False, None)

    tail = messages[i]
    if not isinstance(tail, AIMessage) or tail.name not in names:
        return _TailInspection(False, None)
    if tail.tool_calls:
        return _TailInspection(False, tail.name)
    return _TailInspection(True, None)


def make_forward_after_agent(agent_names: set[str]):
    """构造 pre_model_hook：专家已给出最终回答时，进入 supervisor LLM 前直接结束。

    langgraph-supervisor 中专家节点完成后固定回流 supervisor 节点；本 hook 检查
    末条消息是否为某位专家的最终回答（带专家 name、无 tool_calls 的 AIMessage）：

    - 是 → ``Command(graph=PARENT, goto=END)``：supervisor react 子图立即终止，
      外层流程结束，专家原文成为最终消息；
    - 专家以未闭环 tool_calls 收尾 → 抛 ``UnclosedSpecialistOutput``（fail fast）：
      放行会让残缺 tool_call 留在 state，下次模型调用必失败或陷入递归，
      且报错信息指向不了真凶；显式抛出可让日志一眼看到是哪位专家断了；
    - 否（首轮路由 / 寒暄直答）→ ``{}``，照常调用 LLM。

    **必须用 PARENT 作用域**：langgraph 1.x 中节点返回本地 ``Command(goto=END)``
    无法覆盖 ``pre_model_hook → agent`` 的静态边（实测仍会进入 LLM 节点）；
    ``graph=PARENT`` 与库内 handoff 工具同机制，直接终止子图并结束外层流程。
    专家的最终消息在专家节点完成时已写入外层 state，无需在 update 里重复携带。

    白名单挂在函数属性 ``agent_names`` 上，供装配期一致性校验读取。
    """
    names = frozenset(agent_names)

    def forward_after_agent(state: dict) -> dict | Command:
        messages = state.get("messages") or []
        if not messages:
            return {}
        inspection = _inspect_tail(messages, names)
        if inspection.unclosed_name is not None:
            raise UnclosedSpecialistOutput(
                f"专家 {inspection.unclosed_name!r} 以未闭环 tool_calls 收尾，"
                "拒绝放行给 supervisor（否则残留 tool_call 会导致模型调用失败或递归分派）。"
            )
        if inspection.is_final_answer:
            return Command(graph=Command.PARENT, goto=END)
        return {}

    forward_after_agent.agent_names = names  # type: ignore[attr-defined]
    return forward_after_agent


def _specialist_names(specialists: tuple) -> frozenset[str]:
    """取专家 name 集合并校验：name 必须存在且互不重复。

    hook 白名单按字符串匹配 name，一旦与实际 name 脱节（改名漏配）会**静默失效**——
    专家终答不再短路，supervisor 会二次介入复述。故在装配期就暴露问题。
    """
    names = []
    for a in specialists:
        name = getattr(a, "name", None)
        if not name:
            raise ValueError(f"专家 {a!r} 缺少 name，supervisor handoff 与短路均依赖它")
        names.append(name)
    duplicates = {n for n in names if names.count(n) > 1}
    if duplicates:
        raise ValueError(f"专家 name 重复：{sorted(duplicates)}，create_supervisor 也会拒绝")
    return frozenset(names)


def _assert_hook_covers_specialists(hook, specialists: tuple) -> None:
    """装配期校验：hook 白名单必须与真实挂载的专家集合严格一致。

    ``forward_after_agent`` 用 name 字符串匹配，若白名单与 ``_SPECIALISTS`` 脱节
    （新增专家忘加、改名等），短路会静默失效 —— 专家终答被 supervisor 二次复述，
    既不报错也无告警。这里在装配前直接断言，把静默失效变成启动期崩溃。
    """
    registered = _specialist_names(specialists)
    hooked = getattr(hook, "agent_names", frozenset())
    if set(hooked) != set(registered):
        raise ValueError(
            f"forward_after_agent 白名单 {sorted(hooked)} 与专家集合 {sorted(registered)} "
            "不一致；请用 make_forward_after_agent(_specialist_names(_SPECIALISTS)) 构造 hook。"
        )


forward_after_agent = make_forward_after_agent(_specialist_names(_SPECIALISTS))
_assert_hook_covers_specialists(forward_after_agent, _SPECIALISTS)

workflow = create_supervisor(
    list(_SPECIALISTS),
    model=get_model(settings.DEFAULT_MODEL, temperature=TEMPERATURE_SUPERVISOR),
    prompt=SUPERVISOR_PROMPT,
    # 只保留子 agent 最后一条回答，避免 full_history 把中间检索/重复内容透传给前端
    output_mode="last_message",
    # transfer_to_* 的分派控制消息（AI tool_call + ToolMessage 对）不写入消息历史：
    # 否则会泄漏进 /history，并在后续轮次混入送入模型的上下文
    add_handoff_messages=False,
    # 子 agent 完成后不再回插 "Transferring back to supervisor" 这类控制消息
    add_handoff_back_messages=False,
    pre_model_hook=forward_after_agent,
)

# 内层 supervisor（仅分派）。对外图见 teaching_graph.edu_supervisor（含 load_memory）
inner_supervisor = workflow.compile()
