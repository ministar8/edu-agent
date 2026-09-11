"""提示词包的结构性测试。

变量一致性**已在 import 期由 `prompts._validate` 校验**（见 `src/prompts/__init__.py`
的集中登记），所以这里**不重复登记变量表**，只覆盖校验器覆盖不到的部分：

- 指令/数据是否真的分到了不同消息角色（校验器不管这个）
- 漏参是否报错（不能静默产出残缺提示词）
- 统一导出是否完整
- 校验器自身的正/负用例（它是生产 import 期唯一的防线）
"""

import re

import pytest
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.prompts import ChatPromptTemplate

import prompts
from prompts._validate import validate_static_prompt, validate_template

# 模板名 → 是否要求「指令(System) + 数据(Human)」分离
SEPARATED: dict[str, bool] = {
    "HYDE_PROMPT": True,
    "CLASSIFY_PROMPT": True,
    "DECOMPOSE_PROMPT": True,
    "RELEVANCE_PROMPT": True,
    "GRADE_PROMPT": True,
    # 出题走 question_agent（它自带 system prompt），故只有 human
    "QUESTION_GEN_PROMPT": False,
}


def _template(name: str) -> ChatPromptTemplate:
    return getattr(prompts, name)


def test_all_templates_are_exported():
    """__all__ 应完整覆盖包内的 ChatPromptTemplate。"""
    exported = {
        name for name in prompts.__all__ if isinstance(getattr(prompts, name), ChatPromptTemplate)
    }
    assert exported == set(SEPARATED)


@pytest.mark.parametrize("name", sorted(SEPARATED))
def test_formats_into_non_empty_messages(name):
    template = _template(name)
    messages = template.format_messages(**dict.fromkeys(template.input_variables, "x"))
    assert messages


@pytest.mark.parametrize("name", sorted(SEPARATED))
def test_missing_variable_raises(name):
    """漏传任一变量都必须报错，不能静默产出残缺提示词。"""
    template = _template(name)
    variables = set(template.input_variables)
    assert variables, f"{name} 没有任何变量，用例失去意义"
    for missing in variables:
        with pytest.raises(KeyError, match=missing):
            template.format_messages(**dict.fromkeys(variables - {missing}, "x"))


@pytest.mark.parametrize("name", sorted(SEPARATED))
def test_instruction_and_data_role_separation(name):
    """批改/检索类模板必须把「指令」与「不可信数据」分到不同消息角色。"""
    template = _template(name)
    messages = template.format_messages(**dict.fromkeys(template.input_variables, "x"))

    assert any(isinstance(m, HumanMessage) for m in messages)
    has_system = any(isinstance(m, SystemMessage) for m in messages)
    assert has_system is SEPARATED[name], f"{name} 的 System/Human 分离与预期不符"


class TestValidator:
    """校验器自身行为 —— 它是生产 import 期唯一的防线。"""

    def test_passes_when_variables_match(self):
        template = ChatPromptTemplate.from_messages([("human", "{a}")])
        validate_template(template, name="t", variables={"a"})  # 不应抛

    def test_raises_on_mismatch(self):
        template = ChatPromptTemplate.from_messages([("human", "{a}")])
        with pytest.raises(ValueError, match="变量与登记不一致"):
            validate_template(template, name="t", variables={"a", "b"})

    def test_escaped_braces_are_not_treated_as_variables(self):
        """JSON 示例写 `{{ }}` 才不会被当成变量（写错会被本校验拦下）。"""
        template = ChatPromptTemplate.from_messages([("human", '{{"k": 1}}')])
        assert template.input_variables == []
        validate_template(template, name="t", variables=set())  # 不应抛

    def test_static_prompt_rejects_braces(self):
        """纯字符串提示词里的花括号不会被填充，是静默 bug —— 必须拦下。"""
        with pytest.raises(ValueError, match="含花括号"):
            validate_static_prompt("角色：{student_profile}", name="t")

    def test_static_prompt_accepts_plain_text(self):
        validate_static_prompt("角色：无变量", name="t")  # 不应抛


class TestToolNameConsistency:
    """agent prompt 里声明的工具名必须与 `agents/tools.py` 注册的一致。

    工具改名而 prompt 没改 → agent 会去调用一个**不存在的工具**，而且不会报错，
    只会表现成"检索没结果"。这类漂移很难从日志发现，所以钉在测试里。
    """

    # prompt 约定用 `- <tool_name> → <说明>` 的列表格式声明工具
    _TOOL_BULLET = re.compile(r"^-\s*([a-z][a-z0-9_]*)\s*→")

    def _declared_tools(self) -> set[str]:
        declared: set[str] = set()
        for name in (
            "KNOWLEDGE_AGENT_SYSTEM_PROMPT",
            "GRADING_AGENT_SYSTEM_PROMPT",
            "QUESTION_AGENT_SYSTEM_PROMPT",
        ):
            for line in getattr(prompts, name).splitlines():
                if match := self._TOOL_BULLET.match(line.strip()):
                    declared.add(match.group(1))
        return declared

    def _registered_tools(self) -> set[str]:
        from langchain_core.tools import BaseTool

        import agents.tools as tools_module

        return {obj.name for obj in vars(tools_module).values() if isinstance(obj, BaseTool)}

    def test_extraction_finds_the_tools(self):
        """先证明提取器有效 —— 否则下面两条断言会永远通过（空集比空集）。"""
        assert len(self._declared_tools()) >= 4
        assert len(self._registered_tools()) >= 4

    def test_prompt_declared_tools_are_registered(self):
        unknown = self._declared_tools() - self._registered_tools()
        assert not unknown, f"prompt 声明的工具未注册: {sorted(unknown)}"

    def test_registered_tools_are_declared_in_prompt(self):
        """注册了但没写进 prompt 的工具，模型不知道何时用。"""
        undocumented = self._registered_tools() - self._declared_tools()
        assert not undocumented, f"已注册但 prompt 未声明: {sorted(undocumented)}"


class TestAgentPromptStructure:
    """`prompts/agents.py` 声明的结构规范：前 4 段必填，`[示例]` 可选。"""

    AGENT_PROMPTS = (
        "KNOWLEDGE_AGENT_SYSTEM_PROMPT",
        "GRADING_AGENT_SYSTEM_PROMPT",
        "QUESTION_AGENT_SYSTEM_PROMPT",
        "QUESTION_GEN_STRUCTURED_SYSTEM_PROMPT",
    )
    REQUIRED_SECTIONS = ("[角色]", "[工具]", "[规则]", "[输出]")

    @pytest.mark.parametrize("name", AGENT_PROMPTS)
    def test_required_sections_present(self, name):
        text = getattr(prompts, name)
        missing = [section for section in self.REQUIRED_SECTIONS if section not in text]
        assert not missing, f"{name} 缺少段落: {missing}"

    @pytest.mark.parametrize("name", AGENT_PROMPTS)
    def test_rules_are_not_numeric_numbered(self, name):
        """规则必须用无编号列表。

        早期用 `1. 2. 3.` 编号，共享规则占 1–6、各 agent 的专属规则从 7 接着排 ——
        往共享规则加一条，所有 agent 的编号整体错位，而且不会报错。改用列表后耦合消失。
        """
        text = getattr(prompts, name)
        rules = text.split("[规则]", 1)[1].split("[输出]", 1)[0]
        assert not re.search(r"^\s*\d+\.\s", rules, re.M), f"{name} 的规则仍在用数字编号"


class TestToolCallRuleWording:
    """工具调用约定的措辞约束（来自一次真实的提示词问题）。

    历史问题：
      a) `不要输出思考` —— 思考模式应由 API 层的 extra_body 控制（core/llm.py
         `_build_client`），用提示词禁 CoT 会拖累复杂问题的工具选择与参数质量。
      b) `首轮必须直接调用工具` —— 无需检索的输入（寒暄）会被迫触发一次无意义检索。
      c) supervisor 写「不要自己回答具体问题」—— 堵死了它本来就有的
         `destinations + (END,)` 出口，寒暄会被强派给专家。

    **局限（须知情）**：这类断言只能守住「旧措辞不复现」，同一语义换个说法它拦不住。
    真正的保障是 `prompts/agents.py` 里那段解释性注释 —— 改措辞前先读它。
    """

    def test_no_thinking_suppression_wording(self):
        for name in TestAgentPromptStructure.AGENT_PROMPTS:
            assert "不要输出思考" not in getattr(prompts, name), name

    def test_no_mandatory_tool_call_wording(self):
        for name in TestAgentPromptStructure.AGENT_PROMPTS:
            assert "首轮必须直接调用工具" not in getattr(prompts, name), name

    def test_supervisor_keeps_direct_reply_escape_hatch(self):
        text = prompts.SUPERVISOR_PROMPT
        assert "不要自己回答具体问题" not in text, "旧措辞会把寒暄强派给专家"
        assert "不必分派" in text, "supervisor 需要保留「可直接回应」的出口"
