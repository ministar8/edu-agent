"""批改兜底解析 + 通用 salvage 钩子的行为锁。

来源：2026-11-07 基础设施迁移（`llm_calls` → `core`，批改 KV 解析 →
`agents.specialists.grading_salvage`）。原注释声称「gate `⑨g` 断言覆盖
schema 全部字段」——全仓不存在该 gate，本文件用真实测试替代。

覆盖点：
1. `GradingResult` **全部 5 个字段**都能从「工具标记污染 + 行式裸文本」救回；
2. 历史缺陷 `is_wrong` 语义反转（续行污染）不复现；
3. 多行字段（feedback / error_analysis）保留续行；
4. 无标记污染时不触发兜底（与原行为一致）；
5. 通用 JSON 兜底仍对任意 schema 生效；
6. `call_structured(salvage=...)` 钩子按「通用 JSON → 领域专用」顺序执行。
"""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from agents.specialists.grading_salvage import salvage_grading
from core import llm_calls
from core.llm_calls import salvage_json_from_raw
from schema.grading import GradingResult

# 模拟实测见过的形态：前言 + 行式字段 + 泄漏的工具标记
_GRADING_RAW = """好的，批改如下：
score: 42
feedback: 中序遍历理解有误
error_analysis: 混淆了升序与降序
is_wrong: true
knowledge_points: 二叉排序树、平衡二叉树
<parameter=score>"""


class _Item(BaseModel):
    name: str
    count: int


def test_grading_salvage_recovers_all_schema_fields() -> None:
    result = salvage_grading(_GRADING_RAW, GradingResult)
    assert result is not None
    # 5 个字段逐一断言 —— 任何字段从 KV 协议里掉队都会失败
    assert result.score == 42
    assert result.feedback == "中序遍历理解有误"
    assert result.error_analysis == "混淆了升序与降序"
    assert result.is_wrong is True
    assert result.knowledge_points == ["二叉排序树", "平衡二叉树"]


def test_is_wrong_not_inverted_by_following_key_lines() -> None:
    # 历史缺陷：knowledge_points 行被拼进 is_wrong ⇒ True 变 False
    raw = "score: 10\nis_wrong: true\nknowledge_points: 哈夫曼编码\n<tool_call>"
    result = salvage_grading(raw, GradingResult)
    assert result is not None
    assert result.is_wrong is True
    assert result.knowledge_points == ["哈夫曼编码"]


def test_multiline_fields_keep_continuation_lines() -> None:
    raw = (
        "score: 10\n"
        "feedback: 第一行\n"
        "第二行\n"
        "is_wrong: 是\n"
        "error_analysis: 概念混淆\n"
        "需要复习定义\n"
        "<tool_call>"
    )
    result = salvage_grading(raw, GradingResult)
    assert result is not None
    assert result.feedback == "第一行\n第二行"
    assert result.error_analysis == "概念混淆\n需要复习定义"
    assert result.is_wrong is True


def test_no_markup_pollution_skips_salvage() -> None:
    # 没有被清洗掉的标记 ⇒ 不属于本兜底能治的情形（保持原实现语义）
    assert salvage_grading("score: 40\nfeedback: 旁注", GradingResult) is None


def test_generic_json_salvage_works_for_any_schema() -> None:
    raw = '<parameter=name>{"name": "x", "count": 3}</parameter>'
    item = salvage_json_from_raw(raw, _Item)
    assert item is not None
    assert (item.name, item.count) == ("x", 3)


def test_generic_json_salvage_requires_pollution() -> None:
    assert salvage_json_from_raw('{"name": "x", "count": 3}', _Item) is None


@pytest.mark.asyncio
async def test_call_structured_hook_order_generic_then_custom(monkeypatch) -> None:
    """通用 JSON 先试；救不回再交给领域专用 salvage。"""

    async def fake_attempts(llm, prompt, schema, timeout, stage, attempts, version):
        return None, None, _GRADING_RAW

    monkeypatch.setattr(llm_calls, "_structured_attempts", fake_attempts)
    monkeypatch.setattr(llm_calls, "get_llm", lambda **kwargs: object())

    with_hook = await llm_calls.call_structured(
        "prompt",
        GradingResult,
        temperature=0.0,
        timeout=1.0,
        stage="test",
        salvage=salvage_grading,
    )
    assert with_hook is not None and with_hook.score == 42

    without_hook = await llm_calls.call_structured(
        "prompt",
        GradingResult,
        temperature=0.0,
        timeout=1.0,
        stage="test",
    )
    assert without_hook is None
