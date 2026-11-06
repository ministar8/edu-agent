"""守护 templates/ 的运行时接线：每个模板必须有真实调用者。

冻结后的规则（新增模板不得绕过）：
- `prompts.templates.__all__` 中每个模板都必须在 EXPECTED_CALLERS 登记；
- 登记的文件必须真的引用该模板符号；
- 批改 / 出题模板必须经 prompt_service 组装，Supervisor 模板必须传给 create_supervisor。
"""

from pathlib import Path

import pytest

import prompts.templates as templates

_SRC = Path(__file__).resolve().parents[2] / "src"

# 模板符号 → 必须出现该符号的运行时文件（相对 src/）
EXPECTED_CALLERS = {
    "SUPERVISOR_PROMPT_TEMPLATE": "agents/orchestration/supervisor.py",
    "GRADE_PROMPT": "prompts/service/prompt_service.py",
    "QUESTION_GEN_PROMPT": "prompts/service/prompt_service.py",
}


def test_no_unregistered_templates():
    """templates/ 里不允许存在没有登记调用者的模板。"""
    assert set(templates.__all__) == set(EXPECTED_CALLERS)


@pytest.mark.parametrize("symbol,caller", sorted(EXPECTED_CALLERS.items()))
def test_template_has_runtime_caller(symbol, caller):
    caller_path = _SRC / caller
    assert caller_path.exists(), f"调用方文件不存在：{caller}"
    assert symbol in caller_path.read_text(encoding="utf-8"), (
        f"{symbol} 未在 {caller} 中被引用 —— 模板定义了却没有运行时路径"
    )


def test_grading_and_question_are_reached_via_prompt_service():
    service = (_SRC / "prompts/service/prompt_service.py").read_text(encoding="utf-8")
    assert "GRADE_PROMPT.format_messages" in service
    assert "QUESTION_GEN_PROMPT.format_messages" in service

    grading_core = (_SRC / "agents/specialists/grading.py").read_text(encoding="utf-8")
    question_core = (_SRC / "agents/specialists/question.py").read_text(encoding="utf-8")
    assert "build_grade_messages" in grading_core
    assert "build_question_gen_messages" in question_core


def test_supervisor_template_passed_to_create_supervisor():
    supervisor = (_SRC / "agents/orchestration/supervisor.py").read_text(encoding="utf-8")
    assert "prompt=SUPERVISOR_PROMPT" in supervisor
