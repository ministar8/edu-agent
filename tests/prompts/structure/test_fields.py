"""测试 src/prompts/structure/fields.py：5 字段骨架与统一组装函数。"""

from prompts.structure.fields import (
    FIELD_ORDER,
    FIELD_SCHEMA,
    assemble_prompt,
)


def test_field_schema_contains_all_five_fields():
    """FIELD_SCHEMA 必须包含全部 5 个字段。"""
    expected = {"角色", "工具", "规则", "输出", "示例"}
    assert set(FIELD_SCHEMA.keys()) == expected


def test_field_order_matches_schema_keys():
    """FIELD_ORDER 必须与 FIELD_SCHEMA 的 keys 严格一致，避免重复维护。"""
    assert FIELD_ORDER == tuple(FIELD_SCHEMA.keys())


def test_assemble_prompt_missing_required_field_raises():
    """缺少任何必填字段，assemble_prompt 必须抛出 ValueError。"""
    try:
        assemble_prompt(role="", tools="工具", rules="规则", output="输出")
        assert False, "应当抛出 ValueError"
    except ValueError as e:
        assert "角色" in str(e)


def test_assemble_prompt_full_assembly():
    """完整调用时，所有 5 个字段都应出现在结果中。"""
    result = assemble_prompt(
        role="测试角色",
        tools="测试工具",
        rules="测试规则",
        output="测试输出",
        examples="测试示例",
    )
    assert "[角色]\n测试角色" in result
    assert "[工具]\n测试工具" in result
    assert "[规则]\n测试规则" in result
    assert "[输出]\n测试输出" in result
    assert "[示例]\n测试示例" in result


def test_assemble_prompt_field_order_correct():
    """拼接结果必须严格按照 FIELD_ORDER 的顺序。"""
    result = assemble_prompt(role="R", tools="T", rules="Ru", output="O", examples="E")
    positions = {name: result.index(f"[{name}]") for name in FIELD_ORDER}
    assert list(positions.values()) == sorted(positions.values())
