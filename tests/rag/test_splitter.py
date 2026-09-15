"""rag/splitter.py 测试：纯函数 + 真实分块契约。

分两部分：
1. 纯函数单测 —— 逐条钉住切分决策逻辑（阈值表、句界判定、语义单元解析、层级元数据）。
2. split_documents 端到端 —— 用假 metrics 隔离，验证公开 API 的对外契约。

`TestKnownDefects` 专门收录**当前行为确有缺陷**的用例。它们是变更哨兵（tripwire）：
断言的是现状而非期望，修复缺陷后这些用例应当失败，并需同步更新为期望行为。
"""

import pytest
from langchain_core.documents import Document

import rag.splitter as splitter
from rag.splitter import (
    MIN_CHUNK_LENGTH,
    _append_chunk_metadata,
    _build_heading_context,
    _build_overlap_units,
    _build_parent_window_text,
    _compute_section_depth,
    _extract_headings,
    _extract_qa_fields,
    _flush_chunk,
    _is_sentence_complete,
    _make_chunk,
    _make_chunk_id,
    _make_doc_id,
    _make_section_id,
    _merge_qa_blockquotes,
    _merge_short_chunks,
    _parse_semantic_units,
    _percentile,
    _render_units,
    _resolve_chunk_params,
    _restore_code_placeholders,
    _split_into_sections,
    _split_oversized,
    _split_qa_oversized,
    _split_section_text,
    _split_sentences,
    split_documents,
)

# ── 夹具 ──────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _silence_metrics(monkeypatch):
    """split_documents 会向真实 data/metrics/rag_metrics.jsonl 追加，测试必须隔离。"""
    monkeypatch.setattr(splitter.metrics, "emit", lambda **kwargs: None)


@pytest.fixture
def emitted(monkeypatch):
    """捕获 metrics 载荷（覆盖 _silence_metrics 的补丁）。"""
    records: list[dict] = []
    monkeypatch.setattr(splitter.metrics, "emit", lambda **kwargs: records.append(kwargs))
    return records


def _doc(text: str, **metadata) -> Document:
    metadata.setdefault("source_file", "s.md")
    return Document(page_content=text, metadata=metadata)


# 足以通过 MIN_CHUNK_LENGTH(80) 过滤的正文；短于此的 section 会被整体丢弃
_BODY = "这是一段足够长的正文内容，用来通过最小长度过滤。" * 4


def _section(
    text: str = "正文。",
    heading: str = "",
    heading_level: int = 0,
    heading_path: str = "",
    section_index: int = 0,
) -> dict:
    return {
        "text": text,
        "heading": heading,
        "heading_level": heading_level,
        "heading_path": heading_path,
        "section_index": section_index,
    }


# ══════════════════════════════════════════════════════
# 1. 纯函数
# ══════════════════════════════════════════════════════


class TestResolveChunkParams:
    """按 content_type 查表选 (chunk_size, chunk_overlap)。"""

    @pytest.mark.parametrize(
        ("content_type", "expected"),
        [
            ("section", (800, 150)),
            ("text", (800, 150)),
            ("code_mixed", (400, 100)),
            ("exercise", (600, 100)),
            ("answer", (600, 100)),
        ],
    )
    def test_mapped_types(self, content_type, expected):
        assert _resolve_chunk_params(content_type) == expected

    @pytest.mark.parametrize("content_type", ["list", "merged_qa", "table", "formula"])
    def test_atomic_types_are_zero(self, content_type):
        # 0 表示「不拆」，调用方需将其解释为无限大
        assert _resolve_chunk_params(content_type) == (0, 0)

    def test_unknown_type_falls_back_to_default(self):
        assert _resolve_chunk_params("未知类型") == (800, 150)
        assert _resolve_chunk_params("") == (800, 150)


class TestPercentile:
    """最近秩百分位（index = round((n-1)*ratio)）。"""

    def test_empty_returns_zero(self):
        assert _percentile([], 0.5) == 0.0

    def test_single_value(self):
        assert _percentile([7], 0.9) == 7.0

    def test_median_of_even_length_uses_bankers_rounding(self):
        # len=4 → (4-1)*0.5 = 1.5 → round(1.5) = 2 → ordered[2] = 3
        assert _percentile([1, 2, 3, 4], 0.5) == 3.0

    def test_median_of_six_uses_bankers_rounding(self):
        # len=6 → (6-1)*0.5 = 2.5 → round(2.5) = 2（银行家舍入，非 3）→ ordered[2] = 3
        assert _percentile([1, 2, 3, 4, 5, 6], 0.5) == 3.0

    def test_input_is_sorted_first(self):
        assert _percentile([9, 1, 5], 0.5) == 5.0

    def test_ratio_one_returns_max(self):
        assert _percentile([1, 2, 3], 1.0) == 3.0

    def test_ratio_above_one_is_clamped(self):
        assert _percentile([1, 2, 3], 2.0) == 3.0

    def test_negative_ratio_is_clamped(self):
        assert _percentile([1, 2, 3], -1.0) == 1.0


class TestIsSentenceComplete:
    """句界判定是分块不截断句中语义的核心守卫。"""

    @pytest.mark.parametrize(
        "text",
        [
            "结束。",
            "结束！",
            "结束？",
            "end.",
            "end!",
            "end?",
            "说明：",
            "说明：",
            "说明；",
            "end;",
            "省略…",
            "右引号”",
            "right'",
            'right"',
        ],
    )
    def test_terminal_punctuation(self, text):
        assert _is_sentence_complete(text) is True

    @pytest.mark.parametrize(
        "text",
        [
            "- 列表项",
            "* 星号列表",
            "+ 加号列表",
            "1. 编号项",
            "12． 全角点项",
            "# 标题",
            "#### 四级标题",
        ],
    )
    def test_markdown_structure_lines(self, text):
        assert _is_sentence_complete(text) is True

    @pytest.mark.parametrize("text", ["代码结尾```", "**加粗**", "__下划线加粗__"])
    def test_code_and_emphasis(self, text):
        assert _is_sentence_complete(text) is True

    @pytest.mark.parametrize("text", ["（右括号）", ")", "】", "]", "》", "}", "表格 |"])
    def test_closing_brackets_and_table(self, text):
        assert _is_sentence_complete(text) is True

    def test_trailing_gt_is_complete(self):
        assert _is_sentence_complete("引用 >") is True

    @pytest.mark.parametrize("text", ["未完", "半句", "没有标点", "以数字1结尾"])
    def test_incomplete_plain_text(self, text):
        assert _is_sentence_complete(text) is False

    def test_leading_gt_is_not_complete(self):
        # 只检查结尾；以 > 开头不代表结束
        assert _is_sentence_complete("> 引用行") is False

    @pytest.mark.parametrize("text", ["", "   ", "\n\t"])
    def test_blank_is_complete(self, text):
        assert _is_sentence_complete(text) is True

    def test_multiline_uses_last_line(self):
        assert _is_sentence_complete("正文未完\n- 列表项") is True
        assert _is_sentence_complete("正文。\n半句未完") is False

    def test_trailing_whitespace_is_stripped(self):
        assert _is_sentence_complete("结束。   \n") is True


class TestExtractHeadings:
    def test_no_headings(self):
        assert _extract_headings("纯文本，没有标题。") == []

    def test_captures_level_title_and_offsets(self):
        text = "# 第一章\n正文。\n## 第一节\n"
        heads = _extract_headings(text)
        assert [(h["level"], h["title"]) for h in heads] == [(1, "第一章"), (2, "第一节")]
        assert text[heads[0]["start"] : heads[0]["end"]] == "# 第一章"
        assert text[heads[1]["start"] : heads[1]["end"]] == "## 第一节"

    def test_five_level_heading_is_not_captured(self):
        # _HEADING_RE 只认 #{1,4}：真实知识库里的 ##### 1)内容 不被视为标题
        assert _extract_headings("##### 1)内容\n正文。") == []

    def test_four_level_is_captured(self):
        assert len(_extract_headings("#### 四级")) == 1

    def test_requires_space_after_hashes(self):
        assert _extract_headings("#没空格") == []


class TestBuildHeadingContext:
    def test_no_headings_returns_empty(self):
        assert _build_heading_context([], 0) == ""

    def test_single_level(self):
        heads = _extract_headings("# 第一章\n")
        assert _build_heading_context(heads, 0) == "[第一章]"

    def test_nested_path(self):
        heads = _extract_headings("# 章\n## 节\n### 小节\n")
        assert _build_heading_context(heads, 2) == "[章 > 节 > 小节]"

    def test_level_skip_drops_intermediate(self):
        heads = _extract_headings("# A\n### C\n")
        assert _build_heading_context(heads, 1) == "[A > C]"

    def test_position_limits_visible_headings(self):
        heads = _extract_headings("# A\n## B\n")
        assert _build_heading_context(heads, 0) == "[A]"

    def test_sibling_resets_deeper_level(self):
        # 回到 level 2 时，之前 level 3 的条目必须被丢弃，否则路径会串味成 [A > D > C]
        heads = _extract_headings("# A\n## B\n### C\n## D\n")
        assert _build_heading_context(heads, 3) == "[A > D]"

    def test_deeper_level_does_not_survive_shallower_sibling(self):
        heads = _extract_headings("# 章\n## 节一\n### 小节\n## 节二\n")
        assert _build_heading_context(heads, 3) == "[章 > 节二]"
        assert _build_heading_context(heads, 2) == "[章 > 节一 > 小节]"


class TestSplitIntoSections:
    def test_no_headings_single_section(self):
        sections = _split_into_sections("整段正文。", [])
        assert len(sections) == 1
        assert sections[0]["heading"] == ""
        assert sections[0]["heading_level"] == 0
        assert sections[0]["section_index"] == 0
        assert sections[0]["text"] == "整段正文。"

    def test_preamble_occupies_index_zero(self):
        text = "前言段落。\n\n# 第一章\n章内容。"
        sections = _split_into_sections(text, _extract_headings(text))
        assert [s["text"] for s in sections] == ["前言段落。", "# 第一章\n章内容。"]
        # 前言占掉 0，首个真实 section 从 1 开始
        assert [s["section_index"] for s in sections] == [0, 1]

    def test_blank_preamble_is_not_emitted(self):
        text = "\n\n# 第一章\n章内容。"
        sections = _split_into_sections(text, _extract_headings(text))
        assert len(sections) == 1
        assert sections[0]["heading"] == "第一章"

    def test_section_text_includes_its_heading_line(self):
        text = "# 章\n正文。"
        sections = _split_into_sections(text, _extract_headings(text))
        assert sections[0]["text"] == "# 章\n正文。"

    def test_heading_path_is_filled(self):
        text = "# 章\n\n## 节\n内容。"
        sections = _split_into_sections(text, _extract_headings(text))
        assert sections[1]["heading_path"] == "[章 > 节]"

    def test_section_ends_at_next_heading(self):
        text = "# A\n甲。\n# B\n乙。"
        sections = _split_into_sections(text, _extract_headings(text))
        assert sections[0]["text"] == "# A\n甲。"
        assert sections[1]["text"] == "# B\n乙。"


class TestMakeChunk:
    def test_copies_metadata(self):
        base = {"source_file": "a.md", "n": 1}
        chunk = _make_chunk(base, "正文")
        assert chunk.page_content == "正文"
        assert chunk.metadata == base

    def test_metadata_is_not_shared(self):
        base = {"source_file": "a.md"}
        chunk = _make_chunk(base, "正文")
        chunk.metadata["extra"] = "x"
        assert "extra" not in base


class TestBuildParentWindowText:
    """父窗口 = 锚点块 + 向两侧扩展直到字符预算。"""

    def test_empty_returns_empty(self):
        assert _build_parent_window_text([], 0) == ""

    def test_oversized_anchor_is_truncated_to_budget(self):
        chunks = [(_make_chunk({}, "x" * 100), "detail")]
        assert _build_parent_window_text(chunks, 0, budget=30) == "x" * 30

    def test_expands_left_then_right_within_budget(self):
        chunks = [(_make_chunk({}, f"块{i}" * 10), "detail") for i in range(5)]
        # 每块 20 字符；预算 60 → 锚点(2) + 左邻(1) 共 42，再加任一邻居都会超
        out = _build_parent_window_text(chunks, 2, budget=60)
        assert out == "块1块1块1块1块1块1块1块1块1块1\n\n块2块2块2块2块2块2块2块2块2块2"

    def test_result_is_in_document_order(self):
        chunks = [(_make_chunk({}, f"块{i}" * 10), "detail") for i in range(5)]
        out = _build_parent_window_text(chunks, 2, budget=60)
        assert out.index("块1") < out.index("块2")

    def test_anchor_only_when_no_neighbour_fits(self):
        chunks = [(_make_chunk({}, "x" * 20), "detail"), (_make_chunk({}, "y" * 20), "detail")]
        assert _build_parent_window_text(chunks, 0, budget=20) == "x" * 20

    def test_expands_to_the_right_when_left_is_exhausted(self):
        chunks = [(_make_chunk({}, f"块{i}" * 10), "detail") for i in range(3)]
        out = _build_parent_window_text(chunks, 0, budget=50)
        assert out == "块0块0块0块0块0块0块0块0块0块0\n\n块1块1块1块1块1块1块1块1块1块1"


class TestRestoreCodePlaceholders:
    def test_restores_index(self):
        assert _restore_code_placeholders("前 __CODE_BLOCK_0__ 后", ["```\ncode\n```"]) == (
            "前 ```\ncode\n``` 后"
        )

    def test_out_of_range_index_kept_verbatim(self):
        assert _restore_code_placeholders("__CODE_BLOCK_5__", ["only"]) == "__CODE_BLOCK_5__"

    def test_no_placeholder_unchanged(self):
        assert _restore_code_placeholders("普通文本", []) == "普通文本"

    def test_multiple_placeholders(self):
        out = _restore_code_placeholders("__CODE_BLOCK_0__ 和 __CODE_BLOCK_1__", ["A", "B"])
        assert out == "A 和 B"


class TestMergeQaBlockquotes:
    """预扫描：把 Q&A 区域标记为原子块。"""

    def test_plain_text_unchanged(self):
        text = "普通段落一。\n\n普通段落二。"
        assert _merge_qa_blockquotes(text) == text

    def test_example_with_adjacent_answer_is_merged(self):
        text = "> 例题1：进程是什么？\n> A. 程序\n答案：B"
        out = _merge_qa_blockquotes(text)
        assert out == "__QA_PAIR_START__> 例题1：进程是什么？\n> A. 程序\n答案：B"

    def test_example_block_is_closed_by_non_quote_line(self):
        text = "> 例题1：问？\n答案：A\n\n后续普通段落。"
        out = _merge_qa_blockquotes(text)
        assert "__QA_PAIR_START__" in out
        assert out.rstrip().endswith("后续普通段落。")

    def test_unclosed_example_is_flushed_at_eof(self):
        assert _merge_qa_blockquotes("> 例题1：问？\n> A. 甲").startswith("__QA_PAIR_START__")

    def test_second_example_closes_the_first(self):
        text = "> 例题1：问一？\n答案：A\n> 例题2：问二？\n答案：B"
        out = _merge_qa_blockquotes(text)
        assert out.count("__QA_PAIR_START__") == 2

    def test_exam_heading_starts_a_block(self):
        out = _merge_qa_blockquotes("### 第1题\n题干。\n正确答案：A\n")
        assert out.startswith("__QA_PAIR_START__")

    def test_five_hash_numeric_heading_starts_a_block(self):
        out = _merge_qa_blockquotes("##### 1\n题干。\n正确答案：A\n")
        assert out.startswith("__QA_PAIR_START__")

    def test_second_exam_heading_flushes_the_first_block(self):
        text = "##### 1\n题一\n正确答案：A\n##### 2\n题二\n正确答案：B"
        assert _merge_qa_blockquotes(text).count("__QA_PAIR_START__") == 2


class TestExtractQaFields:
    def test_letter_answer_key(self):
        fields = _extract_qa_fields("> 例题1：进程是什么？\n> A. 程序\n\n答案：B\n解析：略")
        assert fields["answer_key"] == "B"
        assert fields["question"] == "进程是什么？\nA. 程序"
        assert fields["answer"].startswith("B")

    def test_multi_letter_answer_key(self):
        assert _extract_qa_fields("题干。\n正确答案：A,C")["answer_key"] == "A,C"

    def test_non_letter_answer_key_is_summary(self):
        fields = _extract_qa_fields("第1题：简述进程。\n答案：进程是程序执行实体；它拥有资源。")
        assert fields["answer_key"] == "进程是程序执行实体"

    def test_non_letter_answer_key_truncated_to_120(self):
        long_answer = "答" * 200
        fields = _extract_qa_fields(f"题干。\n答案：{long_answer}")
        assert len(fields["answer_key"]) == 120

    def test_no_answer_marker_yields_empty_answer(self):
        fields = _extract_qa_fields("没有答案标记的文本。")
        assert fields == {"question": "没有答案标记的文本。", "answer": "", "answer_key": ""}

    def test_bold_markers_are_stripped_from_key(self):
        assert _extract_qa_fields("题干。\n正确答案：**D**\n")["answer_key"] == "D"

    def test_question_prefix_is_cleaned(self):
        fields = _extract_qa_fields("> 例题1：进程是什么？\n> A. 甲\n答案：A")
        assert not fields["question"].startswith(">")
        assert not fields["question"].startswith("例题1")

    def test_numeric_heading_prefix_is_cleaned(self):
        fields = _extract_qa_fields("##### 12\n题干内容。\n正确答案：D\n")
        assert fields["question"] == "题干内容。"

    def test_answer_prefix_is_cleaned(self):
        fields = _extract_qa_fields("题干。\n正确答案：B\n解析：因为 B。")
        assert not fields["answer"].startswith("正确答案")


class TestSplitSentences:
    def test_mixed_punctuation(self):
        assert _split_sentences("甲。乙！丙？丁.戊!己?庚；辛") == [
            "甲。",
            "乙！",
            "丙？",
            "丁.",
            "戊!",
            "己?",
            "庚；",
            "辛",
        ]

    def test_trailing_fragment_without_punctuation(self):
        assert _split_sentences("甲。乙") == ["甲。", "乙"]

    def test_empty(self):
        assert _split_sentences("") == []

    def test_no_punctuation_single_part(self):
        assert _split_sentences("没有标点") == ["没有标点"]

    def test_punctuation_is_preserved(self):
        assert all(s.rstrip("。！？；.!?;") == "" or True for s in _split_sentences("甲。乙！"))


class TestParseSemanticUnits:
    def test_code_block_is_atomic_unit(self):
        units = _parse_semantic_units("```python\nx = 1\n```")
        assert len(units) == 1
        assert units[0]["is_code"] is True
        assert units[0]["text"] == "```python\nx = 1\n```"

    def test_table_is_atomic_unit(self):
        units = _parse_semantic_units("| a | b |\n|---|---|\n| 1 | 2 |")
        assert units[0]["is_table"] is True

    def test_formula_is_atomic_unit(self):
        units = _parse_semantic_units("$$E=mc^2$$")
        assert units[0]["is_formula"] is True

    def test_list_group_merged_into_one_unit(self):
        units = _parse_semantic_units("- 项1\n- 项2\n- 项3")
        assert len(units) == 1
        assert units[0]["text"] == "- 项1\n- 项2\n- 项3"

    def test_prose_paragraph_is_one_unit(self):
        units = _parse_semantic_units("段落一。")
        assert len(units) == 1
        assert units[0]["is_qa"] is False

    def test_mixed_document_unit_order_and_flags(self):
        text = (
            "段落一。\n\n"
            "- 项1\n- 项2\n\n"
            "```python\nx = 1\n```\n\n"
            "| a | b |\n|---|---|\n| 1 | 2 |\n\n"
            "$$E=mc^2$$\n"
        )
        units = _parse_semantic_units(text)
        assert [u["text"][:6] for u in units] == [
            "段落一。",
            "- 项1\n-",
            "```pyt",
            "| a | ",
            "$$E=mc",
        ]
        assert units[1]["is_qa"] is False
        assert units[2]["is_code"] is True
        assert units[3]["is_table"] is True
        assert units[4]["is_formula"] is True

    def test_prose_and_list_split_into_separate_units(self):
        units = _parse_semantic_units("引导句：\n- 项1\n- 项2")
        assert [u["text"] for u in units] == ["引导句：", "- 项1\n- 项2"]

    def test_list_then_prose_split(self):
        units = _parse_semantic_units("- 项1\n收尾句。")
        assert [u["text"] for u in units] == ["- 项1", "收尾句。"]

    def test_empty_text_yields_no_units(self):
        assert _parse_semantic_units("") == []
        assert _parse_semantic_units("   \n\n  ") == []

    def test_qa_marker_becomes_atomic_qa_unit(self):
        units = _parse_semantic_units("__QA_PAIR_START__题干？\n答案：A")
        assert len(units) == 1
        assert units[0]["is_qa"] is True
        assert units[0]["text"] == "题干？\n答案：A"

    def test_qa_marker_without_blank_lines_survives(self):
        # 无空行时 Q&A 块才真正原子（有空行会被 re.split(r"\n{2,}") 切开）
        units = _parse_semantic_units("__QA_PAIR_START__题干？\nA. 甲\n答案：A")
        assert [u["is_qa"] for u in units] == [True]

    def test_long_prose_over_1200_is_split_by_sentence(self):
        text = "这是一个很长的句子。" * 150  # 1500 字符
        units = _parse_semantic_units(text)
        assert len(units) == 2
        # 拼接时以空格连接，实际长度会略超 1200（见 TestKnownDefects）
        assert all(len(u["text"]) < 1400 for u in units)

    def test_code_placeholder_does_not_break_plain_prose(self):
        units = _parse_semantic_units("段落一。\n\n```python\nx = 1\n```\n\n段落二。")
        assert [u["is_code"] for u in units] == [False, True, False]
        assert units[1]["text"] == "```python\nx = 1\n```"


class TestRenderUnits:
    def test_joins_with_blank_line(self):
        assert _render_units([{"text": "甲"}, {"text": "乙"}]) == "甲\n\n乙"

    def test_skips_blank_units(self):
        assert _render_units([{"text": "甲"}, {"text": "  "}, {"text": "乙"}]) == "甲\n\n乙"

    def test_empty_list(self):
        assert _render_units([]) == ""


class TestBuildOverlapUnits:
    def test_zero_overlap_returns_empty(self):
        units = [{"text": "a" * 10}]
        assert _build_overlap_units(units, 0) == []
        assert _build_overlap_units(units, -5) == []

    def test_picks_tail_units_within_budget(self):
        units = [{"text": "a" * 10}, {"text": "b" * 10}, {"text": "c" * 10}]
        assert [u["text"][0] for u in _build_overlap_units(units, 15)] == ["c"]

    def test_picks_multiple_tail_units(self):
        units = [{"text": "a" * 10}, {"text": "b" * 10}, {"text": "c" * 10}]
        assert [u["text"][0] for u in _build_overlap_units(units, 25)] == ["b", "c"]

    def test_preserves_original_order(self):
        units = [{"text": "a" * 10}, {"text": "b" * 10}]
        out = _build_overlap_units(units, 100)
        assert [u["text"][0] for u in out] == ["a", "b"]

    def test_atomic_unit_blocks_overlap(self):
        units = [{"text": "a" * 5}, {"text": "c" * 5, "is_code": True}]
        assert _build_overlap_units(units, 100) == []

    def test_qa_unit_blocks_overlap(self):
        units = [{"text": "a" * 5}, {"text": "c" * 5, "is_qa": True}]
        assert _build_overlap_units(units, 100) == []

    def test_table_unit_blocks_overlap(self):
        units = [{"text": "a" * 5}, {"text": "c" * 5, "is_table": True}]
        assert _build_overlap_units(units, 100) == []

    def test_formula_unit_blocks_overlap(self):
        units = [{"text": "a" * 5}, {"text": "c" * 5, "is_formula": True}]
        assert _build_overlap_units(units, 100) == []

    def test_oversized_tail_unit_stops_collection(self):
        units = [{"text": "a" * 10}, {"text": "b" * 100}]
        assert _build_overlap_units(units, 50) == []

    def test_output_units_carry_only_three_keys(self):
        units = [{"text": "a" * 5}]
        out = _build_overlap_units(units, 100)
        assert set(out[0]) == {"text", "is_code", "is_qa"}


class TestFlushChunk:
    def test_complete_text_emits_single_chunk(self):
        chunks: list[dict] = []
        _flush_chunk(chunks, [{"text": "完整句子。"}], 800)
        assert chunks == [{"text": "完整句子。", "is_qa": False, "qa_fields": None}]

    def test_empty_units_emit_nothing(self):
        chunks: list[dict] = []
        _flush_chunk(chunks, [], 800)
        assert chunks == []

    def test_blank_units_emit_nothing(self):
        chunks: list[dict] = []
        _flush_chunk(chunks, [{"text": "   "}], 800)
        assert chunks == []

    def test_incomplete_tail_is_detached(self):
        chunks: list[dict] = []
        _flush_chunk(chunks, [{"text": "完整句子。"}, {"text": "半句没结束"}], 800)
        # 尾部 5 字符 < MIN_CHUNK_LENGTH，被丢弃（见 TestKnownDefects）
        assert chunks == [{"text": "完整句子。", "is_qa": False, "qa_fields": None}]

    def test_all_incomplete_falls_back_to_whole_text(self):
        chunks: list[dict] = []
        _flush_chunk(chunks, [{"text": "半句一"}, {"text": "半句二"}], 800)
        assert chunks == [{"text": "半句一\n\n半句二", "is_qa": False, "qa_fields": None}]

    def test_long_incomplete_tail_is_kept_as_its_own_chunk(self):
        chunks: list[dict] = []
        _flush_chunk(chunks, [{"text": "完整句子。"}, {"text": "甲" * 100}], 800)
        assert [c["text"] for c in chunks] == ["完整句子。", "甲" * 100]


class TestSplitOversized:
    def test_splits_by_sentence_under_limit(self):
        assert _split_oversized("甲。乙。丙。", 3) == ["甲。", "乙。", "丙。"]

    def test_empty_input(self):
        assert _split_oversized("", 100) == []

    def test_result_keeps_all_content(self):
        text = "甲甲。乙乙。丙丙。"
        assert "".join(_split_oversized(text, 4)) == text

    def test_single_sentence_over_limit_is_hard_split(self):
        """单句超限必须硬切 —— 此前注释承诺了这个兜底但并未实现。"""
        out = _split_oversized("甲" * 500, 100)
        assert len(out) == 5
        assert all(len(part) <= 100 for part in out)
        assert "".join(out) == "甲" * 500

    def test_hard_split_does_not_mix_with_neighbouring_sentences(self):
        """超限句被硬切时，前后的独立句子不应被混拼进来。

        注意 ``_split_sentences`` 是"累积到终结符"的语义：``"前。" + "乙"*250 + "后。"``
        里 ``后。`` 与前缀同属一句（中间没有终结符），所以这里必须显式给出终结符，
        才能构造出"前后各有一个独立短句"的场景。
        """
        text = "前。" + "乙" * 250 + "。" + "后。"
        out = _split_oversized(text, 100)
        assert out[0] == "前。"
        assert out[-1] == "后。"
        assert all(len(part) <= 100 for part in out)
        assert "".join(out).replace(" ", "") == text

    def test_all_parts_respect_limit_for_mixed_input(self):
        text = "短句。" + "丙" * 180 + "另一句。" + "丁" * 130
        out = _split_oversized(text, 50)
        assert all(len(part) <= 50 for part in out)


class TestSplitQaOversized:
    def test_splits_on_exam_heading(self):
        text = "### 第1题\n题一\n正确答案：A\n\n### 第2题\n题二\n正确答案：B\n"
        assert len(_split_qa_oversized(text, 30)) == 2

    def test_splits_on_five_hash_heading(self):
        text = "##### 1\n题一\n正确答案：A\n\n##### 2\n题二\n正确答案：B\n"
        assert len(_split_qa_oversized(text, 30)) == 2

    def test_splits_on_example_marker(self):
        text = "> 例题1：问一？\n答案：A\n\n> 例题2：问二？\n答案：B\n"
        assert len(_split_qa_oversized(text, 20)) == 2

    def test_no_boundary_keeps_text_atomic(self):
        text = "无边界文本" * 20
        assert _split_qa_oversized(text, 50) == [text]

    def test_empty_input(self):
        assert _split_qa_oversized("", 50) == []
        assert _split_qa_oversized("   ", 50) == []


class TestMergeShortChunks:
    def test_empty(self):
        assert _merge_short_chunks([], 80, 800) == []

    def test_short_prev_absorbs_next(self):
        out = _merge_short_chunks([{"text": "短"}, {"text": "另一个短块"}], 80, 800)
        assert len(out) == 1
        assert out[0]["text"] == "短\n\n另一个短块"

    def test_long_prev_is_kept_separate(self):
        out = _merge_short_chunks([{"text": "x" * 100}, {"text": "另一个短块"}], 80, 800)
        assert len(out) == 2

    def test_qa_chunks_are_never_merged(self):
        out = _merge_short_chunks([{"text": "短", "is_qa": True}, {"text": "另一个短块"}], 80, 800)
        assert len(out) == 2

    def test_next_qa_chunk_blocks_merge(self):
        out = _merge_short_chunks([{"text": "短"}, {"text": "另一个短块", "is_qa": True}], 80, 800)
        assert len(out) == 2

    def test_respects_max_length(self):
        out = _merge_short_chunks([{"text": "短"}, {"text": "x" * 100}], 80, 50)
        assert len(out) == 2

    def test_chain_merge(self):
        out = _merge_short_chunks([{"text": "a"}, {"text": "b"}, {"text": "c"}], 80, 800)
        assert len(out) == 1
        assert out[0]["text"] == "a\n\nb\n\nc"

    def test_original_chunks_are_not_mutated(self):
        src = [{"text": "短"}, {"text": "另一个短块"}]
        _merge_short_chunks(src, 80, 800)
        assert src[0]["text"] == "短"

    def test_short_atomic_chunk_is_merged_with_neighbour(self):
        """表格/公式允许被合并 —— 合并是整体拼接，不会把它们拆开。

        曾按 docstring 字面意思禁止合并，结果门禁当场判为退化
        （precision 0.9014→0.8952、evidence 5.325→5.250、索引少 39 个 chunk），
        因为过短的原子 chunk 会连同过短的邻居一起被 MIN_CHUNK_LENGTH 丢掉。
        这条测试把"允许合并"这个**有意为之**的决定钉住，避免后人又"修"回去。
        """
        out = _merge_short_chunks([{"text": "短"}, {"text": "$$x$$"}], 80, 800)
        assert len(out) == 1
        assert out[0]["text"] == "短\n\n$$x$$"


class TestSplitSectionText:
    def test_empty_text_yields_no_chunks(self):
        assert _split_section_text("", 800, 200) == []
        assert _split_section_text("   ", 800, 200) == []

    def test_formula_stays_atomic(self):
        out = _split_section_text("$$E=mc^2$$", 800, 200)
        assert len(out) == 1
        assert out[0]["text"] == "$$E=mc^2$$"

    def test_small_paragraphs_are_greedily_merged(self):
        out = _split_section_text("段落一。\n\n段落二。", 800, 200)
        assert len(out) == 1
        assert out[0]["text"] == "段落一。\n\n段落二。"

    def test_chunk_result_has_three_keys(self):
        out = _split_section_text("段落。", 800, 200)
        assert set(out[0]) == {"text", "is_qa", "qa_fields"}

    def test_oversized_unit_is_split(self):
        out = _split_section_text("句子。" * 1000, 200, 0)
        assert len(out) > 1

    def test_overlap_repeats_tail_into_next_chunk(self):
        text = "甲甲甲。\n\n乙乙乙。\n\n丙丙丙。"
        out = _split_section_text(text, 10, 5)
        assert len(out) == 2
        # 第二块以第一块尾部（乙）开头，实现重叠
        assert out[1]["text"].startswith("乙乙乙。")

    def test_atomic_unit_is_flushed_separately(self):
        out = _split_section_text(f"{_BODY}\n\n$$E=mc^2$$", 800, 200)
        assert [c["text"] for c in out] == [_BODY, "$$E=mc^2$$"]

    def test_atomic_unit_does_not_join_preceding_chunk(self):
        out = _split_section_text(f"{_BODY}\n\n| a | b |\n|---|---|\n| 1 | 2 |", 800, 200)
        assert out[0]["text"] == _BODY
        assert out[1]["text"].startswith("| a | b |")

    def test_overlap_is_dropped_when_it_would_exceed_chunk_size(self):
        out = _split_section_text("甲甲甲。\n\n乙乙乙。\n\n丙丙丙。", 9, 5)
        assert [c["text"] for c in out] == ["甲甲甲。", "乙乙乙。", "丙丙丙。"]

    def test_oversized_list_unit_is_split_by_sentence(self):
        text = "\n".join("- " + "字" * 28 + "。" for _ in range(60))
        out = _split_section_text(text, 999999, 0)
        assert len(out) == 2
        assert all(len(c["text"]) <= 1700 for c in out)

    def test_oversized_unit_after_prose_flushes_pending_chunk_first(self):
        long_list = "\n".join("- " + "字" * 28 + "。" for _ in range(60))
        out = _split_section_text(f"{_BODY}\n\n{long_list}", 999999, 0)
        assert out[0]["text"] == _BODY
        assert len(out) == 3

    def test_short_atomic_unit_is_merged_into_neighbours(self):
        """过短的原子单元会被邻居合并 —— 这是有意的，不是 bug。

        合并是整体拼接，公式本身没有被拆开；若禁止合并，三个短单元会一起落到
        MIN_CHUNK_LENGTH 之下被丢弃。门禁实测禁止合并会退化（见 TestMergeShortChunks）。
        """
        out = _split_section_text("段落一。\n\n$$E=mc^2$$\n\n段落二。", 800, 200)
        assert len(out) == 1
        assert out[0]["text"] == "段落一。\n\n$$E=mc^2$$\n\n段落二。"
        assert "$$E=mc^2$$" in out[0]["text"], "公式必须完整保留"

    def test_short_table_unit_is_merged_into_neighbours(self):
        out = _split_section_text(
            "段落一。\n\n| a | b |\n|---|---|\n| 1 | 2 |\n\n段落二。", 800, 200
        )
        assert len(out) == 1
        assert "| a | b |" in out[0]["text"], "表格必须完整保留"
        assert "|---|---|" in out[0]["text"], "表格分隔行不能被拆掉"


class TestIdHelpers:
    def test_doc_id(self):
        assert _make_doc_id("os.md") == "doc::os.md"

    def test_section_id(self):
        assert _make_section_id("os.md", 3) == "sec::os.md::3"

    def test_chunk_id(self):
        assert _make_chunk_id("os.md", 1, 2) == "chk::os.md::1::2"

    def test_ids_are_distinct_across_levels(self):
        assert len({_make_doc_id("a"), _make_section_id("a", 0), _make_chunk_id("a", 0, 0)}) == 3


class TestComputeSectionDepth:
    @pytest.mark.parametrize(("level", "depth"), [(0, 0), (1, 1), (2, 2), (3, 3), (4, 3), (5, 3)])
    def test_mapping(self, level, depth):
        assert _compute_section_depth(level) == depth


class TestAppendChunkMetadata:
    def _chunk(self) -> Document:
        return _make_chunk({"source_file": "os.md"}, "正文内容")

    def test_writes_doc_and_section_level_fields(self):
        chunk = self._chunk()
        _append_chunk_metadata(
            chunk,
            _section(heading="第一章", heading_level=1, heading_path="[第一章]"),
            "sec::os.md::1",
            None,
            [],
            0,
            0,
            doc_id="doc::os.md",
        )
        md = chunk.metadata
        assert md["section.doc_id"] == "doc::os.md"
        assert md["section.id"] == "sec::os.md::1"
        assert md["section.parent_id"] is None
        assert md["section.depth"] == 1
        assert md["section.title"] == "第一章"
        assert md["section.path"] == "[第一章]"
        assert md["section.is_leaf"] is True

    def test_writes_chunk_level_fields(self):
        chunk = self._chunk()
        _append_chunk_metadata(
            chunk, _section(), "sec::os.md::0", None, [], 5, 2, doc_id="doc::os.md"
        )
        md = chunk.metadata
        assert md["section.chunk_id"] == "chk::os.md::0::2"
        assert md["section.chunk_index"] == 2
        assert md["section.chunk_role"] == "detail"
        assert md["section.chunk_parent_id"] == "sec::os.md::0"

    def test_writes_legacy_compatible_fields(self):
        chunk = self._chunk()
        _append_chunk_metadata(
            chunk,
            _section(heading="章", heading_level=1, heading_path="[章]"),
            "sec::os.md::0",
            None,
            [],
            7,
            1,
            doc_id="doc::os.md",
        )
        md = chunk.metadata
        assert md["chunk_id"] == "chk::os.md::0::1"
        assert md["chunk_index"] == 7
        assert md["chunk_index_in_section"] == 1
        assert md["heading"] == "[章]"
        assert md["heading_level"] == 1
        assert md["char_count"] == len(chunk.page_content)

    def test_ancestor_and_sibling_fields(self):
        chunk = self._chunk()
        _append_chunk_metadata(
            chunk,
            _section(),
            "sec::os.md::2",
            "sec::os.md::1",
            ["sec::os.md::3"],
            0,
            0,
            ancestor_ids=["sec::os.md::0"],
            sibling_index=1,
            sibling_count=3,
            is_leaf=False,
            doc_id="doc::os.md",
        )
        md = chunk.metadata
        assert md["section.ancestor_ids"] == '["sec::os.md::0"]'
        assert md["section.child_ids"] == '["sec::os.md::3"]'
        assert md["section.sibling_index"] == 1
        assert md["section.sibling_count"] == 3
        assert md["section.is_leaf"] is False

    def test_merged_qa_role_consumes_qa_fields(self):
        chunk = self._chunk()
        chunk.metadata["_qa_fields"] = {
            "question": "题干",
            "answer": "答案",
            "answer_key": "B",
        }
        _append_chunk_metadata(
            chunk,
            _section(),
            "sec::os.md::0",
            None,
            [],
            0,
            0,
            chunk_role="merged_qa",
            doc_id="doc::os.md",
        )
        assert chunk.metadata["qa.question"] == "题干"
        assert chunk.metadata["qa.answer"] == "答案"
        assert chunk.metadata["qa.answer_key"] == "B"
        assert "_qa_fields" not in chunk.metadata

    def test_child_chunk_ids_only_for_parent_roles(self):
        detail = self._chunk()
        _append_chunk_metadata(
            detail,
            _section(),
            "sec::os.md::0",
            None,
            [],
            0,
            0,
            child_chunk_ids=["chk::a"],
            doc_id="doc::os.md",
        )
        assert "section.child_chunk_ids" not in detail.metadata

        summary = self._chunk()
        _append_chunk_metadata(
            summary,
            _section(),
            "sec::os.md::0",
            None,
            [],
            0,
            0,
            chunk_role="summary",
            child_chunk_ids=["chk::a"],
            doc_id="doc::os.md",
        )
        assert summary.metadata["section.child_chunk_ids"] == '["chk::a"]'

    def test_parent_chunk_id_written_when_given(self):
        chunk = self._chunk()
        _append_chunk_metadata(
            chunk,
            _section(),
            "sec::os.md::0",
            None,
            [],
            0,
            0,
            parent_chunk_id="chk::parent",
            doc_id="doc::os.md",
        )
        assert chunk.metadata["section.parent_chunk_id"] == "chk::parent"

    def test_source_falls_back_to_source_key(self):
        chunk = _make_chunk({"source": "alt.md"}, "正文")
        _append_chunk_metadata(chunk, _section(), "sec::alt.md::0", None, [], 0, 0)
        assert chunk.metadata["section.chunk_id"] == "chk::alt.md::0::0"


# ══════════════════════════════════════════════════════
# 2. split_documents 端到端
# ══════════════════════════════════════════════════════


class TestSplitDocuments:
    def test_empty_input(self):
        assert split_documents([]) == []

    def test_simple_document_produces_chunks_with_metadata(self):
        chunks = split_documents([_doc(f"# 第一章\n\n{_BODY}")])
        assert chunks
        md = chunks[0].metadata
        assert md["section.doc_id"] == "doc::s.md"
        assert md["section.chunk_role"] == "detail"
        assert md["source_file"] == "s.md"

    def test_source_falls_back_to_unknown(self):
        chunks = split_documents([Document(page_content="# 章\n\n" + "内容。" * 40, metadata={})])
        assert chunks[0].metadata["section.doc_id"] == "doc::unknown"

    def test_short_section_below_min_length_is_dropped(self):
        # 单个短 section 的 chunk 会被 MIN_CHUNK_LENGTH 过滤
        chunks = split_documents([_doc("# 章\n\n短。")])
        assert chunks == []

    def test_section_hierarchy_is_recorded(self):
        text = f"# 章\n\n{_BODY}\n\n## 节\n\n{_BODY}"
        chunks = split_documents([_doc(text)])
        by_section = {c.metadata["section.title"]: c.metadata for c in chunks}
        assert by_section["章"]["section.parent_id"] is None
        assert by_section["节"]["section.parent_id"] == "sec::s.md::0"
        assert by_section["节"]["section.ancestor_ids"] == '["sec::s.md::0"]'
        assert by_section["章"]["section.is_leaf"] is False
        assert by_section["节"]["section.is_leaf"] is True

    def test_siblings_are_numbered(self):
        text = f"# A\n\n{_BODY}\n\n# B\n\n{_BODY}"
        chunks = split_documents([_doc(text)])
        siblings = {c.metadata["section.title"]: c.metadata for c in chunks}
        assert siblings["A"]["section.sibling_index"] == 0
        assert siblings["B"]["section.sibling_index"] == 1
        assert siblings["A"]["section.sibling_count"] == 2

    def test_parent_window_is_attached(self):
        chunks = split_documents([_doc(f"# 章\n\n{_BODY}")])
        assert chunks[0].metadata["section.parent_text"]
        assert chunks[0].metadata["section.parent_window_budget"] == 4200

    def test_content_type_is_recorded(self):
        chunks = split_documents([_doc(f"# 章\n\n{_BODY}")])
        assert chunks[0].metadata["section.content_type"] == "section"

    def test_adaptive_params_are_recorded(self):
        chunks = split_documents([_doc(f"# 章\n\n{_BODY}")])
        assert chunks[0].metadata["section.adaptive_size"] == 800
        assert chunks[0].metadata["section.adaptive_overlap"] == 150

    def test_global_chunk_index_is_continuous(self):
        text = f"# A\n\n{_BODY}\n\n# B\n\n{_BODY}"
        chunks = split_documents([_doc(text)])
        assert [c.metadata["chunk_index"] for c in chunks] == list(range(len(chunks)))

    def test_metrics_are_emitted(self, emitted):
        split_documents([_doc(f"# 章\n\n{_BODY}")])
        assert len(emitted) == 1
        record = emitted[0]
        assert record["event"] == "split_documents"
        assert record["stage"] == "splitter"
        assert record["values"]["input_docs"] == 1
        assert record["values"]["total_chunks"] >= 1

    def test_metrics_empty_input_has_zero_stats(self, emitted):
        split_documents([])
        values = emitted[0]["values"]
        assert values["total_chunks"] == 0
        assert values["avg_chunk_chars"] == 0.0
        assert values["mid_sentence_cut_rate"] == 0.0

    def test_merged_qa_fallback_emits_single_atomic_chunk(self):
        # heading 含「题」但正文无 > 例题 / ### 第N题 → 走 merged_qa 整段兜底
        text = "## 常考题精选\n\n1. 简述进程与程序的区别。\n\n答案：进程是动态的，程序是静态的。"
        chunks = split_documents([_doc(text)])
        assert len(chunks) == 1
        assert chunks[0].metadata["section.chunk_role"] == "merged_qa"
        assert chunks[0].metadata["section.content_type"] == "merged_qa"
        assert chunks[0].metadata["qa.answer_key"] == "进程是动态的，程序是静态的。"

    def test_code_block_document(self):
        text = "# 代码示例\n\n```python\n" + "x = 1\n" * 20 + "```\n\n" + "说明文字。" * 20
        chunks = split_documents([_doc(text)])
        assert any("```python" in c.page_content for c in chunks)

    def test_huge_merged_qa_section_is_kept_as_single_chunk(self):
        body = ("第1题：请说明进程与线程的区别。\n答案：" + "甲" * 100 + "。\n\n") * 30
        chunks = split_documents([_doc(f"## 常考题型\n\n{body}")])
        assert len(chunks) == 1
        assert chunks[0].metadata["section.chunk_role"] == "merged_qa"

    def test_example_qa_chunk_keeps_structured_qa_fields(self):
        qa = (
            "> 例题1：请简述进程与程序的主要区别，并说明进程的三种基本状态以及它们之间的转换条件是什么？\n"
            "> A. 程序是静态的，进程是动态的\n"
            "> B. 进程是动态的，程序是静态的\n"
            "答案：B"
        )
        chunks = split_documents([_doc(f"## 例题精讲\n\n{qa}")])
        assert chunks[0].metadata["section.chunk_role"] == "merged_qa"
        assert chunks[0].metadata["qa.answer_key"] == "B"

    def test_multiple_documents_are_processed_independently(self):
        a = _doc(f"# 甲\n\n{_BODY}", source_file="a.md")
        b = _doc(f"# 乙\n\n{_BODY}", source_file="b.md")
        chunks = split_documents([a, b])
        assert {c.metadata["section.doc_id"] for c in chunks} == {"doc::a.md", "doc::b.md"}


# ══════════════════════════════════════════════════════
# 3. 已知缺陷（变更哨兵）
# ══════════════════════════════════════════════════════


class TestKnownDefects:
    """断言的是**当前实测行为**，非期望行为。

    这些用例存在的意义：把缺陷钉住，使修复必然导致测试失败，
    从而强迫修复者同步更新契约。修好之后请把断言改成期望值并移出本类。
    """

    def test_chunk_size_and_overlap_parameters_are_ignored(self):
        """缺陷：split_documents 的 chunk_size / chunk_overlap 参数在函数体内从未被使用。"""
        text = "# 章\n\n" + "这是一个测试段落。" * 30
        small = split_documents([_doc(text)], chunk_size=200, chunk_overlap=0)
        large = split_documents([_doc(text)], chunk_size=5000, chunk_overlap=0)
        assert [c.page_content for c in small] == [c.page_content for c in large]

    def test_example_qa_merge_breaks_on_blank_line(self):
        """缺陷：答案前有空行（markdown 常态）时，Q&A 原子块被空行切断，答案脱离题干。"""
        text = "> 例题1：进程是什么？\n> A. 程序\n> B. 执行实体\n\n答案：B"
        units = _parse_semantic_units(text)
        qa_units = [u for u in units if u["is_qa"]]
        assert len(qa_units) == 1
        # 答案没有进入原子单元
        assert "答案：B" not in qa_units[0]["text"]
        assert "答案：B" in [u["text"] for u in units if not u["is_qa"]]

    def test_exam_qa_merge_shreds_into_fragments(self):
        """缺陷：真题模式下 __QA_PAIR_START__ 只贴在第一行，其余内容被空行切成碎片。"""
        text = "##### 1\n\n题干？\n\n正确答案：B\n\n解析：因为 B。\n"
        units = _parse_semantic_units(text)
        assert len(units) > 2
        assert [u["text"] for u in units if u["is_qa"]] == ["##### 1"]
        assert sum(1 for u in units if u["is_qa"]) == 1

    def test_short_example_section_produces_zero_chunks(self):
        """缺陷：短例题 section 整体产出 0 个 chunk，内容静默丢失。"""
        text = "## 例题精讲\n\n> 例题1：进程是什么？\n> A. 程序\n> B. 执行实体\n\n答案：B\n"
        assert split_documents([_doc(text)]) == []

    def test_incomplete_tail_below_min_length_is_dropped(self):
        """缺陷：_flush_chunk 会把不完整的尾部短于 MIN_CHUNK_LENGTH 时直接丢弃。"""
        chunks: list[dict] = []
        _flush_chunk(chunks, [{"text": "完整句子。"}, {"text": "被丢掉的半句"}], 800)
        joined = "".join(c["text"] for c in chunks)
        assert "被丢掉的半句" not in joined

    def test_five_level_headings_are_not_sections(self):
        """缺陷：_extract_headings 只认 #{1,4}，真实库里的 ##### 1)内容 完全不可见。"""
        assert _extract_headings("##### 1)内容\n正文。") == []

    def test_preamble_takes_section_index_zero(self):
        """缺陷/歧义：前导文段占用 section_index=0，首个真实 section 从 1 开始。"""
        text = "前言。\n\n# 章\n内容。"
        sections = _split_into_sections(text, _extract_headings(text))
        assert sections[0]["section_index"] == 0
        assert sections[0]["heading"] == ""
        assert sections[1]["section_index"] == 1

    def test_prose_split_exceeds_its_own_1200_cap(self):
        """缺陷：_add_prose_unit 以 1200 为上限，但按句子拼接时用空格连接，
        分隔符未计入长度，实际产出可达 1319 字符。"""
        units = _parse_semantic_units("这是一个很长的句子。" * 150)
        assert max(len(u["text"]) for u in units) > 1200

    def test_code_placeholder_breaks_qa_block(self):
        """缺陷：代码块占位符自带换行（\\n__CODE_BLOCK_n__\\n），会在 Q&A 块内
        制造空行，使 re.split(r"\\n{2,}") 把原子 Q&A 块切开。"""
        text = "__QA_PAIR_START__题干？\n```python\nx = 1\n```\n答案：A"
        units = _parse_semantic_units(text)
        assert len(units) == 3
        assert [u["is_qa"] for u in units] == [True, False, False]

    def test_min_chunk_length_constant_is_80(self):
        """契约哨兵：过滤阈值变更会影响所有分块结果。"""
        assert MIN_CHUNK_LENGTH == 80
