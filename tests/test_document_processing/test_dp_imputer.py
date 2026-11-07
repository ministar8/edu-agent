"""document_processing.imputer 的三级填充单测。

确定性保障：`_resource_guard` 与 `_heading_cache` 是模块级单例，配额会跨测试累积、
缓存会跨测试命中——autouse fixture 在每个测试前 reset + clear，保证测试互不依赖。

行为锁定要点：
- heading 推断"已有不覆盖"（返回 None）；低置信度结果加 [推测] 前缀；[未命名文档] 兜底不加；
- `min_confidence` 截断：medium 时 low 级方法（首行/关键词/兜底）全部跳过 → None；
- `impute_documents` 每次调用重置配额并清缓存 → 幂等（同输入同输出，无跨调用状态）；
- 空文档被标记 content_status=empty 并从返回集中**丢弃**。
"""

from __future__ import annotations

import pytest
from langchain_core.documents import Document

import document_processing.imputer._heading as heading_mod
from document_processing.imputer._heading import (
    _extract_chapter_heading,
    _extract_md_heading,
    _extract_pdf_heading_by_features,
    _impute_category,
    _impute_heading,
    _impute_heading_path,
    _validate_heading_candidate,
)
from document_processing.imputer._pipeline import (
    _detect_content_status,
    _impute_content_layer,
    impute_documents,
)
from document_processing.imputer._resources import _resource_guard, _with_timeout
from document_processing.imputer._segmentation import (
    _detect_pdf_title_lines,
    _find_split_word_indices,
    _merge_short_segments,
    _resolve_segment_profile,
    _section_headings_by_paragraphs,
    _section_headings_fixed,
    _segments_from_split_indices,
    _split_long_segments,
    _window_jaccard_distances,
)


@pytest.fixture(autouse=True)
def _reset_imputer_state() -> None:
    _resource_guard.reset()
    heading_mod._heading_cache.clear()


def doc(text: str, source: str, **meta: object) -> Document:
    return Document(page_content=text, metadata={"source_path": source, **meta})


# ── 内容层状态检测 ───────────────────────────────────────────────────


def test_content_status_empty() -> None:
    assert _detect_content_status(doc("太短", "a.md")) == "empty"
    assert _detect_content_status(doc("       ", "a.md")) == "empty"


def test_content_status_placeholder() -> None:
    assert _detect_content_status(doc("正文之前的内容。此处插入图示。正文之后的内容。", "a.md")) == "placeholder"


def test_content_status_truncated_odd_fences() -> None:
    text = "代码段开始说明。\n```python\nprint(1)\n```\n代码段结束。\n```\n"
    assert _detect_content_status(doc(text, "a.md")) == "truncated"


def test_content_status_truncated_imbalanced_parens() -> None:
    assert _detect_content_status(doc("说明文字（嵌套（未闭合的讨论", "a.md")) == "truncated"


def test_content_status_truncated_imbalanced_brackets() -> None:
    assert _detect_content_status(doc("数组定义[{【未收拢", "a.md")) == "truncated"


def test_content_status_normal_balanced() -> None:
    text = "说明（含括号的正常叙述）。代码块如下：\n```\ncode\n```\n数组[{合法}]平衡。"
    assert _detect_content_status(doc(text, "a.md")) == "normal"


def test_content_layer_marks_and_logs() -> None:
    d = doc("此处插入表格。正文说明超过十字。", "b.md")
    log, is_empty = _impute_content_layer(d, "b.md")
    assert is_empty is False
    assert d.metadata["content_status"] == "placeholder"
    assert d.metadata["has_placeholder"] is True
    assert log[0]["field"] == "has_placeholder"

    e = doc("嵌入式内容很短", "c.md")  # 6 字 <10 → empty
    log2, is_empty2 = _impute_content_layer(e, "c.md")
    assert is_empty2 is True
    assert e.metadata["content_status"] == "empty"
    assert log2[0]["method"] == "mark_empty"

    n = doc("这是一段完全正常且超出十个字符的文本。", "d.md")
    log3, is_empty3 = _impute_content_layer(n, "d.md")
    assert is_empty3 is False and log3 == []
    assert n.metadata["content_status"] == "normal"


# ── 分段配置解析 ─────────────────────────────────────────────────────


def test_resolve_segment_profile_by_category() -> None:
    profile = _resolve_segment_profile(doc("", "a.md", category="Law"))
    assert profile.window_size == 80  # law 档案（大小写统一后命中）
    assert profile.min_chunk == 800


def test_resolve_segment_profile_by_source_ext() -> None:
    # ★ 消费前提：解析读 metadata["source_ext"] 字段（清洗管线会设），不解析 source_path 后缀
    assert _resolve_segment_profile(doc("", "a.md", source_ext=".md")).window_size == 30  # .md → tech
    assert _resolve_segment_profile(doc("", "b.pdf", source_ext=".pdf")).diff_threshold == 0.55  # .pdf → paper
    assert _resolve_segment_profile(doc("", "c.txt", source_ext=".txt")).min_chunk == 500  # .txt → default


# ── PDF 标题行检测 ──────────────────────────────────────────────────


def test_pdf_title_lines_rules() -> None:
    text = "\n".join(
        [
            "第一章 概述",  # 章节编号行 ✓
            "",  # 空行 → prev_blank
            "12",  # 页码行 ✗（跳过）
            "",  # 空行
            "SECTION OVERVIEW",  # 全大写行 ✓
            "",
            "段落标题占位",  # 前后空行 + 无终结标点 ✓
            "",
            "正文句子。",  # 终结标点 ✗
        ]
    )
    titles = _detect_pdf_title_lines(text)
    texts = {t["text"] for t in titles}
    assert texts == {"第一章 概述", "SECTION OVERVIEW", "段落标题占位"}


# ── 语义分段六步纯函数 ──────────────────────────────────────────────


def test_window_jaccard_distances_symmetrical_blocks() -> None:
    # ★ 实测校准：distances 是 frozenset 词袋的 Jaccard——重复词会被折叠成单元素，
    # 用互异词才能得到多重集语义；相邻窗口重叠 25 词、并集 75 词 → 距离 = 1 - 25/75 = 2/3
    words = [f"w{i}" for i in range(100)]
    distances = dict(_window_jaccard_distances(words, window_size=50, stride=25))
    assert set(distances) == {25, 50}
    assert all(abs(d - 2 / 3) < 1e-9 for d in distances.values())


def test_find_split_word_indices_threshold_and_tie_peaks() -> None:
    distances = [(0, 0.8), (25, 0.2), (50, 0.9)]
    assert _find_split_word_indices(distances, 0.55) == [0, 50]


def test_find_split_word_indices_equal_neighbor_is_peak() -> None:
    # 与邻居相等时仍算峰值（实现用严格大于比较）
    assert _find_split_word_indices([(0, 0.6), (25, 0.6)], 0.55) == [0, 25]


def test_segments_from_split_indices_maps_and_filters() -> None:
    text = "AAABBBCCC"
    # 词位置: 0/3/6
    segs = _segments_from_split_indices(text, [1], [0, 3, 6], min_chunk=2)
    # split@词1 → char 3；段[0,3) len3 ≥2 → 保留；余段[3,9) 6 字符
    assert segs == [{"position": 0, "label": "", "char_count": 3}, {"position": 3, "label": "", "char_count": 6}]


def test_segments_from_split_indices_out_of_range_falls_to_end() -> None:
    segs = _segments_from_split_indices("文字", [5], [0, 1], min_chunk=1)
    # 越界兜底 → char_pos = len(text)=2 → 尾段
    assert segs[-1]["char_count"] == 2


def test_merge_short_segments_into_previous() -> None:
    segs = [
        {"position": 0, "label": "", "char_count": 5},
        {"position": 5, "label": "", "char_count": 1},
        {"position": 6, "label": "", "char_count": 200},
    ]
    merged = _merge_short_segments(segs, min_chunk=2)
    assert merged == [
        {"position": 0, "label": "", "char_count": 6},
        {"position": 6, "label": "", "char_count": 200},
    ]


def test_split_long_segments_even_split_with_remainder() -> None:
    # 130 / 60 → 3 片：60+60+10（余数段允许 < min_chunk，由调用方权衡）
    parts = _split_long_segments([{"position": 0, "label": "", "char_count": 130}], max_chunk=60)
    assert [(p["position"], p["char_count"]) for p in parts] == [(0, 60), (60, 60), (120, 10)]


# ── 空行/定长降级 ───────────────────────────────────────────────────


def test_sections_by_paragraphs_and_none_for_single() -> None:
    sections = _section_headings_by_paragraphs("甲段落。\n\n\n乙段落。\n\n\n丙段落。")
    assert sections is not None  # 收窄 list | None
    assert [s["label"] for s in sections] == ["[第1段]", "[第2段]", "[第3段]"]
    assert _section_headings_by_paragraphs("唯一一段没有边界。") is None


def test_sections_fixed_positions() -> None:
    sections = _section_headings_fixed("字" * 3100, chunk_size=1500)
    assert [s["position"] for s in sections] == [0, 1500, 3000]
    assert sections[0]["label"] == "[第1段]"


# ── heading 推断 ────────────────────────────────────────────────────


def test_extract_md_heading_prefers_low_levels() -> None:
    assert _extract_md_heading("# 主标题\n\n## 副标题") == "主标题"
    assert _extract_md_heading("### 只有三级标题") is None


def test_extract_chapter_heading() -> None:
    assert _extract_chapter_heading("正文铺垫\n第一章 绪论") == "第一章 绪论"
    assert _extract_chapter_heading("1. 简介说明") == "1. 简介说明"
    assert _extract_chapter_heading("这是正文首行以句号结尾。") is None


def test_extract_pdf_heading_by_features_skips_page_numbers_and_lists() -> None:
    text = "12\n- 项目符号行\n\nSYSTEM OVERVIEW\n"
    assert _extract_pdf_heading_by_features(text) == "SYSTEM OVERVIEW"


def test_validate_heading_candidate_rejects_hallucination() -> None:
    body = "死锁的必要条件包括互斥、持有并等待、不可剥夺与循环等待。"
    assert _validate_heading_candidate("死锁", body) is True
    assert _validate_heading_candidate("万有引力场", body) is False
    assert _validate_heading_candidate("12", body) is False
    assert _validate_heading_candidate("的", body) is False  # 纯停用词


def test_impute_heading_existing_not_overwritten() -> None:
    d = doc("正文", "a.md", heading="已有标题")
    assert _impute_heading(d) is None


def test_impute_heading_md_content_high_confidence() -> None:
    d = doc("# 学习路线\n导语正文。", "p.md")
    result = _impute_heading(d)
    assert result == ("学习路线", "md_heading", "high")


def test_impute_heading_filename_medium_no_prefix() -> None:
    d = doc("这是 Ordinary 讲义正文，不含任何标题标记与章节编号。", "操作系统/ch3内存管理.md")
    result = _impute_heading(d)
    assert result is not None  # 收窄 tuple | None
    heading, method, conf = result
    assert heading == "ch3内存管理"
    assert method == "filename"
    assert conf == "medium"
    # medium 不加 [推测] 前缀
    assert not heading.startswith("[推测]")


def test_impute_heading_fallback_unnamed_low_confidence() -> None:
    # docstring 只写"兜底"，但无文件名 + 无标题标记时实际走 jieba 关键词路径（keyword/low）。
    # 实测校准：显式降级 jieba_keyword 配额 → 才落到 [未命名文档] fallback。
    _resource_guard.degrade("jieba_keyword")
    d = doc("第一行太长超过三十个字符的限制条件无法作为标题候选的文件。", "")
    assert _impute_heading(d) == ("[未命名文档]", "fallback", "low")


def test_impute_heading_medium_cutoff_skips_low_methods() -> None:
    d = doc("无标题标记的普通正文文本没有文件名可依。", "")
    assert _impute_heading(d, min_confidence="medium") is None


def test_impute_heading_low_confidence_gets_speculative_prefix() -> None:
    body = "死锁的必要条件包括互斥、持有并等待、不可剥夺与循环等待这四点。"
    d = Document(page_content="死锁的必要条件\n" + body, metadata={"source_path": ""})
    result = _impute_heading(d)
    assert result is not None  # 收窄 tuple | None
    heading, method, conf = result
    assert heading == "[推测]死锁的必要条件"
    assert method == "first_line_filtered"
    assert conf == "low"


def test_impute_heading_cache_hits_same_result() -> None:
    d = doc("# 学习路线\n导语正文。", "p.md")
    first = _impute_heading(d)
    second = _impute_heading(doc("# 学习路线\n导语正文。", "p.md"))
    assert first == second
    assert heading_mod.get_heading_cache_stats() == {"size": 1}


# ── heading_path / category ─────────────────────────────────────────


def test_impute_heading_path_sources() -> None:
    d = doc("", "x.md")
    assert _impute_heading_path(d, "标题") == "[标题]"
    d2 = doc("", "y.md", heading="旧标题")
    assert _impute_heading_path(d2, None) == "[旧标题]"
    d3 = doc("", "目录/文件.md")
    assert _impute_heading_path(d3, None) == "[文件]"


def test_impute_category_from_path_and_exclusions() -> None:
    assert _impute_category(doc("", "operating_system/ch1.md")) == "operating_system"
    assert _impute_category(doc("", "docs/manual.md")) is None
    assert _impute_category(doc("", "a.md", category="已有")) is None
    assert _impute_category(doc("", "")) is None


# ── 端到端 ──────────────────────────────────────────────────────────


def test_impute_documents_drops_empty_and_fills_metadata() -> None:
    empty = doc("过于短", "sys/empty.md")
    md_doc = doc("# 学习路线\n这是正文介绍。", "path/roadmap.md")
    plain = doc("这是一段没有标题标记的讲义正文介绍语句。", "operating_system/ch2进程.md")
    filled, impute_log = impute_documents([empty, md_doc, plain], parallel=False)

    assert all(d is not empty for d in filled)
    assert empty.metadata["content_status"] == "empty"
    assert any(e["field"] == "content_status" and e["method"] == "mark_empty" for e in impute_log)

    # md 文档从原文提取 heading（high，不加前缀）
    md_result = filled[0]
    assert md_result.metadata["heading"] == "学习路线"
    assert md_result.metadata["heading_source"] == "md_heading"
    assert md_result.metadata["has_heading"] is True
    assert md_result.metadata["heading_path"] == "[学习路线]"

    # plain：heading 从文件名推断，category 从路径推断
    plain_result = filled[1]
    assert plain_result.metadata["heading"] == "ch2进程"
    assert plain_result.metadata["category"] == "operating_system"
    assert plain_result.metadata["_impute_log"]


def test_impute_documents_is_idempotent_across_calls() -> None:
    # 每次调用用全新 doc 实例：第一次调用会往 doc 上写 heading/_impute_log 等 metadata，
    # 复用同一实例会让第二次结果"长得像增量"而非幂等
    def build() -> list[Document]:
        return [doc("# 学习路线\n正文介绍部分。", "sys/r.md")]

    first_docs, first_log = impute_documents(build(), parallel=False)
    second_docs, second_log = impute_documents(build(), parallel=False)
    assert first_log == second_log
    assert first_docs[0].metadata["heading"] == second_docs[0].metadata["heading"]
    assert second_docs[0].metadata["heading_confidence"]


def test_with_timeout_swallows_exceptions_and_returns_none() -> None:
    @_with_timeout(5.0)
    def boom() -> object:
        raise RuntimeError("boom")

    @_with_timeout(5.0)
    def fine() -> int:
        return 42

    assert boom() is None  # 操作抛错 → 静默降级为 None
    assert fine() == 42
