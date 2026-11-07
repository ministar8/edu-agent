"""memory.working 的程序侧聚合单测（记忆卡拼装 + weak 行锚点，无 LLM）。

invariants：
- 无内容 → 空串（调用方不得注入空卡污染注意力）；
- weak 最多展示 3 条；整卡 ≤ 200 字符（硬切 + 省略号）；
- 锚点格式「名称（最近N分，「题干」）」，score 缺失显示 ?。
"""

from __future__ import annotations

from memory.schemas import Episode
from memory.working import build_weak_lines_from_grades, format_memory_card

MAX_CARD = 200
MAX_WEAK = 3


def test_empty_card_returns_empty_string() -> None:
    assert format_memory_card(weak_lines=[], preferred_style="") == ""


def test_weak_lines_rendered_with_prefix() -> None:
    card = format_memory_card(weak_lines=["图（最近40分，「题」）"], preferred_style="")
    assert card.startswith("【学生记忆】")
    assert "薄弱：图（最近40分，「题」）" in card


def test_preferred_style_rendered() -> None:
    card = format_memory_card(weak_lines=[], preferred_style="极简要点")
    assert card == "【学生记忆】\n风格：极简要点"


def test_weak_display_capped_at_three() -> None:
    lines = [f"主题{i}" for i in range(5)]
    card = format_memory_card(weak_lines=lines, preferred_style="")
    assert "薄弱：主题0；主题1；主题2" in card
    assert "主题3" not in card
    assert "主题4" not in card


def test_card_hard_cut_at_max_chars() -> None:
    long_line = "很" * 150
    card = format_memory_card(weak_lines=[long_line] * MAX_WEAK, preferred_style="")
    assert len(card) <= MAX_CARD
    assert card.endswith("…")


ANALYSIS_STEM = "题干锚点" * 10  # 恰 40 字符：走 excerpt 的"不截断"路径，断言不再依赖省略号


def grade_ep(score: float | None, topic: str = "图", stem: str = ANALYSIS_STEM) -> Episode:
    return Episode(type="grade", topic=topic, score=score, stem_excerpt=stem, at="2026-01-01T00:00:00+00:00")


def test_weak_lines_embed_score_and_anchor() -> None:
    ep = grade_ep(score=7.5)
    lines = build_weak_lines_from_grades(["图"], {"图": [ep]})
    assert lines == [f"图（最近7分，「{ANALYSIS_STEM}」）"]


def test_weak_lines_score_none_shows_question_mark() -> None:
    ep = grade_ep(score=None)
    lines = build_weak_lines_from_grades(["图"], {"图": [ep]})
    assert lines == [f"图（最近?分，「{ANALYSIS_STEM}」）"]


def test_weak_lines_without_episodes_fall_back_to_bare_topic() -> None:
    lines = build_weak_lines_from_grades(["AVL树"], {})
    assert lines == ["AVL树"]


def test_anchor_excerpt_capped_at_40_chars() -> None:
    stem = "字" * 100
    lines = build_weak_lines_from_grades(["图"], {"图": [grade_ep(50, stem=stem)]})
    anchor = lines[0].split("「", 1)[1].rsplit("」", 1)[0]
    assert len(anchor) == 40
    assert anchor.endswith("…")
