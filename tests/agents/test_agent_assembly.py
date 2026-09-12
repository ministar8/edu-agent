"""Agent 装配一致性：工具集、温度槽、与 supervisor 目标对齐。"""

# 导入以触发 build_agent 登记
from agents import (  # noqa: F401
    grading_agent,
    knowledge_agent,
    question_agent,
)
from agents.factory import all_assemblies, get_assembly
from agents.question_core import question_gen_agent  # noqa: F401
from agents.temperature import (
    TEMPERATURE_GRADING,
    TEMPERATURE_KNOWLEDGE,
    TEMPERATURE_QUESTION,
)
from prompts import SUPERVISOR_PROMPT

SPECIALIST_NAMES = ("knowledge_agent", "question_agent", "grading_agent")


def test_specialist_assemblies_registered():
    for name in SPECIALIST_NAMES:
        assert name in all_assemblies()


def test_knowledge_tools_and_temperature():
    a = get_assembly("knowledge_agent")
    assert set(a.tool_names) == {"knowledge_search", "text_search"}
    assert a.temperature == TEMPERATURE_KNOWLEDGE
    assert a.has_response_format is False


def test_question_tools_and_temperature():
    a = get_assembly("question_agent")
    assert a.tool_names == ("generate_practice_questions",)
    assert a.temperature == TEMPERATURE_QUESTION
    assert a.has_response_format is False


def test_grading_tools_and_temperature():
    a = get_assembly("grading_agent")
    assert set(a.tool_names) == {"grade_student_answer", "search_standard_answer"}
    assert a.temperature == TEMPERATURE_GRADING
    assert a.has_response_format is False


def test_question_gen_is_only_structured_assembly():
    structured = [n for n, a in all_assemblies().items() if a.has_response_format]
    assert structured == ["question_gen_agent"]
    assert get_assembly("question_gen_agent").tool_names == ("search_question_templates",)


def test_supervisor_prompt_lists_specialists():
    for name in SPECIALIST_NAMES:
        assert name in SUPERVISOR_PROMPT


def test_supervisor_graph_contains_specialist_nodes():
    from agents.supervisor import inner_supervisor

    node_names = set(inner_supervisor.get_graph().nodes.keys())
    for name in SPECIALIST_NAMES:
        assert name in node_names, f"supervisor 缺少节点 {name}: {node_names}"


def test_teaching_graph_has_load_memory():
    from agents.agents import get_agent

    graph = get_agent("edu-assistant")
    nodes = set(graph.get_graph().nodes.keys())
    assert "load_memory" in nodes
    assert "supervisor" in nodes
