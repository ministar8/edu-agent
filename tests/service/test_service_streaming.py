import pytest
from langchain_core.messages import AIMessage
from pydantic_core import ValidationError

from service.service import _create_ai_message


@pytest.mark.parametrize(
    "parts, expected",
    [
        # 1) 基础内容 + tool_calls
        (
            {"content": "Hello", "tool_calls": []},
            {"content": "Hello", "tool_calls": []},
        ),
        # 2) 未知键被丢弃
        (
            {"content": "Test", "foobar": 123, "tool_calls": []},
            {"content": "Test", "tool_calls": []},
        ),
        # 3) AIMessage 的其它合法参数（id / type）透传
        (
            {
                "content": "Hey",
                "id": "abc-123",
                "type": "ai",
                "tool_calls": [],
            },
            {"content": "Hey", "id": "abc-123", "type": "ai", "tool_calls": []},
        ),
    ],
)
def test_create_ai_message_filters_and_passes_through(parts, expected):
    """_create_ai_message 应丢弃未知键，保留 AIMessage 签名内的键。"""
    msg: AIMessage = _create_ai_message(parts)
    for key, val in expected.items():
        assert getattr(msg, key) == val


def test_create_ai_message_missing_required_content_raises():
    """缺少必需字段 content 时应抛出 pydantic ValidationError。"""
    with pytest.raises(ValidationError):
        _create_ai_message({"tool_calls": []})


def test_create_ai_message_empty_dict_raises():
    """空 dict 同样应构造失败。"""
    with pytest.raises(ValidationError):
        _create_ai_message({})
