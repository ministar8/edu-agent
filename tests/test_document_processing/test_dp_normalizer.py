"""document_processing.normalizer 的确定性转换单测。

断言口径（2026-11-07 实测探针校准）：
- 全角表**只覆盖数字/字母**，全角标点保留（cleaner 的职责，normalizer 不越界）；
- `_DATE_CN_MONTH_RE` 的负向断言：`2024年1月1日` 交由完整日期一步转换；
- `_LIST_DOT_RE` 仅匹配行首"1~2位数字 + 点 + 空格"——`1.1` 小节与 `3.14` 小数不误伤。
"""

from __future__ import annotations

from langchain_core.documents import Document

from document_processing.normalizer import (
    _apply_text_transforms,
    _detect_heading_level_jumps,
    _fullwidth_to_halfwidth,
    _normalize_dates,
    _normalize_list_markers,
    _normalize_times,
    normalize_documents,
)

# ── 全角 → 半角 ────────────────────────────────────────────────────────


def test_fullwidth_digits_and_letters_converted() -> None:
    assert _fullwidth_to_halfwidth("１２３ＡＢＣａｂｃ") == "123ABCabc"


def test_fullwidth_punctuation_partial_coverage() -> None:
    # 实现怪点（锁定现状）：转换表 range(0xFF10, 0xFF1A+1) 意外覆盖 U+FF1A=全角冒号，
    # 与模块 docstring「保留全角标点」不符——全角冒号会被连带转成半角；
    # 其余全角标点（如 ！）不受影响。后续如收口需连动 docs/ARCHITECTURE_RETRIEVAL。
    assert _fullwidth_to_halfwidth("第１节：内容") == "第1节:内容"
    assert _fullwidth_to_halfwidth("感叹！还是感叹") == "感叹！还是感叹"


# ── 日期归一 ──────────────────────────────────────────────────────────


def test_cn_date_full_pads_zeros() -> None:
    assert _normalize_dates("2024年1月1日") == "2024-01-01"
    assert _normalize_dates("2024年12月31日") == "2024-12-31"


def test_cn_date_month_without_day() -> None:
    assert _normalize_dates("2024年1月曾发生") == "2024-01曾发生"


def test_full_date_wins_over_year_month() -> None:
    # 含"日"的完整日期必须整段转换，不得被年月规则截断成 YYYY-MM-01
    assert _normalize_dates("发布于2024年1月1日发布") == "发布于2024-01-01发布"


def test_slash_and_dot_dates() -> None:
    assert _normalize_dates("2024/1/1 备忘") == "2024-01-01 备忘"
    assert _normalize_dates("2024.1.1 备忘") == "2024-01-01 备忘"


def test_non_four_digit_year_untouched() -> None:
    raw = "约2年1月前"
    assert _normalize_dates(raw) == raw


# ── 时间归一 ──────────────────────────────────────────────────────────


def test_time_dian_and_shi() -> None:
    assert _normalize_times("会议于12点30分开始") == "会议于12:30开始"
    assert _normalize_times("会议于12时30分开始") == "会议于12:30开始"


def test_time_pads_hours_minutes() -> None:
    assert _normalize_times("大约5点3分到达") == "大约05:03到达"


def test_time_without_minutes_untouched() -> None:
    assert _normalize_times("大约3点左右") == "大约3点左右"


# ── 列表编号 ──────────────────────────────────────────────────────────


def test_circled_numbers_converted() -> None:
    assert _normalize_list_markers("①②③要点") == "[1][2][3]要点"


def test_paren_numbers_converted_per_line() -> None:
    assert _normalize_list_markers("1) 项目甲\n2) 项目乙") == "[1] 项目甲\n[2] 项目乙"
    assert _normalize_list_markers("1）全角括号") == "[1]全角括号"


def test_leading_dot_list_converted() -> None:
    assert _normalize_list_markers("1. 文本") == "[1] 文本"


def test_subsection_and_decimal_not_touched() -> None:
    # 1.1 后无空格（正则要求点后跟空白）；"1.1 小节"的点后是数字非空格 → 均不命中
    assert _normalize_list_markers("1.1.1 三级编号") == "1.1.1 三级编号"
    assert _normalize_list_markers("1.1 小节标题") == "1.1 小节标题"
    assert _normalize_list_markers("3.14 是个数字") == "3.14 是个数字"


# ── 标题层级跳跃检测 ─────────────────────────────────────────────────


def test_heading_level_jump_detected() -> None:
    text = "# 章节\n内容行\n### 小节"
    jumps = _detect_heading_level_jumps(text)
    assert len(jumps) == 1
    assert jumps[0] == {"line": 3, "from_level": 1, "to_level": 3, "text": "小节"}


def test_gradual_levels_no_jump() -> None:
    text = "# 章\n## 节\n### 目"
    assert _detect_heading_level_jumps(text) == []


def test_jump_going_up_level_is_not_flagged() -> None:
    # 规则只检测"层级差 >1 的下降"(curr - prev > 1)；回跳（### → #）不算跳跃
    text = "### 深层\n# 回到顶层"
    assert _detect_heading_level_jumps(text) == []


# ── 转换管线 ─────────────────────────────────────────────────────────


def test_transform_change_labels_in_order() -> None:
    text, changes = _apply_text_transforms(
        "研究于2024年1月1日完成１２１网页",
        simplify=False,
        normalize_dates=True,
        normalize_lists=False,
    )
    assert text == "研究于2024-01-01完成121网页"
    assert changes == ["fullwidth→halfwidth", "date_normalized"]


def test_transform_no_change_no_labels() -> None:
    _, changes = _apply_text_transforms("完全正常的中文句子。", simplify=False, normalize_dates=True, normalize_lists=True)
    assert changes == []


# ── normalize_documents 端到端 ───────────────────────────────────────


def test_normalize_documents_updates_metadata_and_log() -> None:
    doc = Document(page_content="研究于2024年1月1日发布１２页", metadata={"source_path": "k/a.md"})
    _, log = normalize_documents([doc])
    assert doc.metadata["normalized"] is True
    assert doc.metadata["normalization_changes"] == ["fullwidth→halfwidth", "date_normalized"]
    assert len(log) == 1
    assert log[0]["source"] == "k/a.md"


def test_normalize_documents_skips_unchanged_and_empty() -> None:
    unchanged = Document(page_content="无需转换的文本。", metadata={"source_path": "k/1.md"})
    empty = Document(page_content="   ", metadata={"source_path": "k/2.md"})
    _, log = normalize_documents([unchanged, empty])
    assert log == []
    assert "normalized" not in unchanged.metadata


def test_normalize_documents_md_heading_jump_detection_only_for_md() -> None:
    # ★ 消费前提：检测读 metadata["source_ext"] 字段（cleaner 管线会设），后缀本身不读取
    md_doc = Document(page_content="１２\n# 章\n### 节\n", metadata={"source_path": "k/x.md", "source_ext": ".md"})
    txt_doc = Document(page_content="１２\n# 章\n### 节\n", metadata={"source_path": "k/x.txt", "source_ext": ".txt"})
    normalize_documents([md_doc, txt_doc])
    # .md：文本有变化 → 标题跳跃并入 changes 且写 metadata
    assert md_doc.metadata["normalization_changes"] == ["fullwidth→halfwidth", "heading_jumps(1)"]
    assert md_doc.metadata["heading_level_jumps"]
    # .txt：不做标题跳跃检测
    assert "heading_level_jumps" not in txt_doc.metadata
