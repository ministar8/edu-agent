"""验证提示词服务层的变量准备与模板调用。"""

import pytest
from langchain_core.messages import HumanMessage, SystemMessage

from prompts.service import (
    MAX_QUESTION_COUNT,
    NO_STANDARD_ANSWER,
    build_grade_messages,
    build_question_gen_messages,
)


def test_build_grade_messages_fills_missing_standard_answer():
    messages = build_grade_messages(
        stem="  什么是进程？ ",
        user_answer=" 进程是程序的一次执行过程。 ",
        standard_answer="   ",
    )

    assert isinstance(messages[0], SystemMessage)
    human = messages[1]
    assert isinstance(human, HumanMessage)
    assert NO_STANDARD_ANSWER in human.content
    assert "什么是进程？" in human.content
    assert "进程是程序的一次执行过程。" in human.content


def test_build_grade_messages_keeps_provided_standard_answer():
    messages = build_grade_messages(
        stem="题干",
        user_answer="学生答案",
        standard_answer="标准答案",
    )

    assert "标准答案：标准答案" in messages[1].content


@pytest.mark.parametrize(
    "kwargs",
    [
        {"stem": "  ", "user_answer": "答案"},
        {"stem": "题干", "user_answer": "  "},
    ],
)
def test_build_grade_messages_rejects_empty_required_fields(kwargs):
    with pytest.raises(ValueError):
        build_grade_messages(**kwargs)


def test_build_question_gen_messages_clamps_count_and_difficulty():
    messages = build_question_gen_messages(
        topic="进程",
        count=999,
        difficulty="unknown",
    )

    text = messages[0].content
    assert f"生成 {MAX_QUESTION_COUNT} 道" in text
    assert "难度：mixed" in text


def test_build_question_gen_messages_normalizes_count_string():
    messages = build_question_gen_messages(topic="进程", count="3", difficulty="basic")

    text = messages[0].content
    assert "生成 3 道" in text
    assert "难度：basic" in text


def test_build_question_gen_messages_rejects_empty_topic():
    with pytest.raises(ValueError):
        build_question_gen_messages(topic="   ")
