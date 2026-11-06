"""验证统一结构规范在真实 Agent Prompt 中的使用方式。

覆盖两件事：
1. 组装结果符合五字段规范：每个 Agent Prompt 必须包含
   [角色]、[工具]、[规则]、[输出]、[示例] 五个字段标记。
2. 现有 _validate.py 能通过最终 Prompt 的校验：
   纯字符串提示词不得含花括号（由 validate_static_prompt 强制）。
"""

from prompts import (
    GRADING_AGENT_SYSTEM_PROMPT,
    KNOWLEDGE_AGENT_SYSTEM_PROMPT,
    QUESTION_AGENT_SYSTEM_PROMPT,
    SUPERVISOR_PROMPT,
)

# 待验证的 Agent Prompt 列表（名称，Prompt 文本）
AGENT_PROMPTS = [
    ("supervisor", SUPERVISOR_PROMPT),
    ("knowledge_agent", KNOWLEDGE_AGENT_SYSTEM_PROMPT),
    ("question_agent", QUESTION_AGENT_SYSTEM_PROMPT),
    ("grading_agent", GRADING_AGENT_SYSTEM_PROMPT),
]

REQUIRED_FIELDS = ["[角色]", "[工具]", "[规则]", "[输出]", "[示例]"]


def test_each_agent_prompt_contains_all_five_fields():
    """每个 Agent Prompt 的组装结果必须包含全部五个字段标记。"""
    for name, prompt in AGENT_PROMPTS:
        missing = [f for f in REQUIRED_FIELDS if f not in prompt]
        assert not missing, f"{name} 缺少字段：{missing}，当前 Prompt 长度 {len(prompt)}"


def test_each_agent_prompt_has_no_braces():
    """纯字符串提示词不得含花括号，否则会被当成字面文本发给模型。

    这等价于 _validate.validate_static_prompt 的校验逻辑。
    """
    for name, prompt in AGENT_PROMPTS:
        assert "{" not in prompt, f"{name} 含左花括号 {{"
        assert "}" not in prompt, f"{name} 含右花括号 }}"


def test_agent_prompt_field_order_follows_schema():
    """五个字段在 Prompt 中的出现顺序应与 FIELD_ORDER 一致。"""
    from prompts.structure.fields import FIELD_ORDER

    field_markers = [f"[{name}]" for name in FIELD_ORDER]
    for name, prompt in AGENT_PROMPTS:
        positions = {marker: prompt.index(marker) for marker in field_markers}
        assert list(positions.values()) == sorted(positions.values()), (
            f"{name} 字段顺序不符合 {FIELD_ORDER}"
        )


def test_supervisor_only_imports_safety_rule():
    """Supervisor 作为路由主管，不输出面向用户文本，
    不应引入 OUTPUT_FORMAT_RULES 或 LENGTH_LIMIT_RULE。
    这里通过检查 Supervisor Prompt 中是否出现了长度限制的
    特征性文案来间接验证（Supervisor 的 [规则] 只应包含 SAFETY_RULES）。"""
    assert "单条回答总长度不超过 800 字" not in SUPERVISOR_PROMPT
    assert "解析/反馈控制在 100-200 字以内" not in SUPERVISOR_PROMPT
