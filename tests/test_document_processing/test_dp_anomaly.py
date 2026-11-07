"""document_processing.anomaly 的两阶段异常单测。

invariants（模块自述）：宁可误报不可漏报；标记优先于删除；保留可追溯性。
阈值行为按代码实现锁定：全乱码 ratio > 0.6（严格大于）、语言混杂 min_ratio > 0.3、
IQR 需要 ≥4 篇文档且 IQR ≠ 0。
"""

from __future__ import annotations

from langchain_core.documents import Document

from document_processing.anomaly import (
    AnomalyRecord,
    _clean_repetitions,
    _detect_full_garbage,
    _detect_garbled_paragraphs,
    _detect_language_mixing,
    _detect_length_outliers,
    _detect_word_freq_anomaly,
    _isolate_garbled_paragraphs,
    _suggest_length_action,
    detect_content_anomalies,
    detect_statistical_anomalies,
)


def doc(text: str, source: str) -> Document:
    return Document(page_content=text, metadata={"source_path": source})


# ── 全乱码 ───────────────────────────────────────────────────────────


def test_full_garbage_detected() -> None:
    assert _detect_full_garbage("★" * 30) is True


def test_full_garbage_ratio_is_strictly_above_threshold() -> None:
    # 11 字符里 7 个乱码 ≈ 0.636 > 0.6 → True；6/10 = 0.6 不严格大于 → False
    assert _detect_full_garbage("★" * 7 + "字" * 4) is True
    assert _detect_full_garbage("★" * 6 + "字" * 4) is False


def test_clean_text_not_full_garbage() -> None:
    assert _detect_full_garbage("数据结构的图与树是重要章节。" * 3) is False


def test_short_text_skipped() -> None:
    assert _detect_full_garbage("★★★") is False  # <10 字符不判
    assert _detect_full_garbage("") is False


# ── 词频异常 ─────────────────────────────────────────────────────────


def test_word_freq_short_text_not_flagged() -> None:
    assert _detect_word_freq_anomaly("的" * 10) == (False, [])


def test_word_freq_repetition_and_char_dominance() -> None:
    text = "的" * 20
    flagged, words = _detect_word_freq_anomaly(text)
    assert flagged is True
    # 重复模式与单字符高占比两类信号都会出现
    assert any("的(" in w for w in words)


def test_word_freq_capped_at_five_entries() -> None:
    text = ("甲乙丙丁" + "五种" + "的" * 4) * 6
    flagged, words = _detect_word_freq_anomaly(text)
    assert len(words) <= 5


def test_word_freq_clean_text_not_flagged() -> None:
    # ★ 阈值口径实测校准：5% 指"单字符占**内容字符**(去空白/标点)的占比"，
    # 中文短句的字复用率天然高（的/是/了 极易超 5%）→ 正例必须用全互异汉字
    text = "美好时光总在闲暇中度过每年富有诗意的人生风景如画"
    assert _detect_word_freq_anomaly(text) == (False, [])


# ── 乱码段落 ─────────────────────────────────────────────────────────


def test_garbled_paragraph_located_with_ratio() -> None:
    text = "第一段正常内容。\n\n★★★★★★★★★"
    garbled = _detect_garbled_paragraphs(text)
    assert len(garbled) == 1
    gp = garbled[0]
    assert gp["index"] == 1
    assert gp["garbage_ratio"] > 0.3


def test_clean_paragraphs_not_flagged() -> None:
    text = "第一段内容完整。\n\n第二段同样正常且丰富。"
    assert _detect_garbled_paragraphs(text) == []


def test_garbled_preview_truncated_beyond_hundred() -> None:
    long_garbage = "★" * 150
    garbled = _detect_garbled_paragraphs("前文正常。\n\n" + long_garbage)
    assert len(garbled[0]["text"]) == 101  # 100 字 + "…"
    assert garbled[0]["text"].endswith("…")


def test_isolate_garbled_paragraphs_replaces_only_flagged() -> None:
    text = "第一段正常内容。\n\n★★★★★★★★★"
    gps = _detect_garbled_paragraphs(text)
    out = _isolate_garbled_paragraphs(text, gps)
    assert out == "第一段正常内容。\n\n[乱码段落，已隔离，原文9字符]"


def test_isolate_without_garbled_unchanged() -> None:
    text = "全正常的文本。"
    assert _isolate_garbled_paragraphs(text, []) == text


# ── 重复词清理 ───────────────────────────────────────────────────────


def test_clean_repetitions_collapses_repeats() -> None:
    assert _clean_repetitions("abcabcabc") == "abc"


def test_clean_repetitions_needs_four_or_more_runs() -> None:
    # 实测：正则要求重复组 ≥2 次 ⇒ 3 连重复不动、8 连缩到 2（20021107 行为校准）
    assert _clean_repetitions("的的的") == "的的的"
    assert _clean_repetitions("的" * 8) == "的的"
    assert _clean_repetitions("abcdabc") == "abcdabc"


def test_clean_repetitions_plain_text_ident() -> None:
    raw = "不断重复词汇的教学要点总结。"
    assert _clean_repetitions(raw) == raw


# ── 长度离群（IQR）──────────────────────────────────────────────────


def test_length_outliers_flags_both_ends() -> None:
    docs = [
        doc("字" * 50, "s0.txt"),
        doc("字" * 120, "s1.txt"),
        doc("字" * 130, "s2.txt"),
        doc("字" * 140, "s3.txt"),
        doc("字" * 5000, "s4_long.txt"),
    ]
    results = _detect_length_outliers(docs)
    assert results["s4_long.txt"][0] == "too_long"
    assert results["s0.txt"][0] == "too_short"


def test_length_outliers_needs_four_docs() -> None:
    docs = [doc("字" * 10, "s0.txt"), doc("字" * 20, "s1.txt"), doc("字" * 9000, "s2.txt")]
    assert _detect_length_outliers(docs) == {}


def test_length_outliers_zero_iqr_skipped() -> None:
    docs = [doc("字" * 100 + str(i), f"s{i}.txt") for i in range(6)]
    assert _detect_length_outliers(docs) == {}


# ── 语言混杂 ─────────────────────────────────────────────────────────


def test_language_mix_balanced_detected() -> None:
    text = "计算机computer" * 12  # 中英各 ≈50%
    mixed, ratio = _detect_language_mixing(text)
    assert mixed is True
    assert 0 < ratio <= 1.0


def test_language_pure_single_not_mixed() -> None:
    text = "数据结构与算法之间的联系非常密切值得深入学习与研究反复推敲理解"  # 32... 凑 ≥50
    text = text + text
    assert _detect_language_mixing(text) == (False, 0.0)


def test_language_short_text_skipped() -> None:
    assert _detect_language_mixing("混合mixed内容") == (False, 0.0)


def test_language_digits_only_zero_total() -> None:
    assert _detect_language_mixing("1234567890" * 8) == (False, 0.0)


# ── 建议生成 ─────────────────────────────────────────────────────────


def test_suggest_length_action_branches() -> None:
    assert "极短" in (_suggest_length_action("too_short", -2.5) or "")
    assert "偏短" in (_suggest_length_action("too_short", -1.0) or "")
    assert "拆分" in (_suggest_length_action("too_long", 3.5) or "")
    assert "偏长" in (_suggest_length_action("too_long", 1.0) or "")
    assert _suggest_length_action(None, 0.0) is None


# ── 阶段1端到端 ─────────────────────────────────────────────────────


def test_stage_one_end_to_end() -> None:
    docs = [
        # doc0：全互异汉字（最高字频 1/24 ≈ 4.2% ≤ 5%）→ 不触发任何异常
        doc("美好时光总在闲暇中度过每年富有诗意的人生风景如画。", "clean.md"),
        # doc1：段1 为互异汉字正文（共48内容字符，最高字频 2/48 ≈ 4.2%），
        #       段2 为 10 个互异乱码字符（各占 1/48 ≈ 2.1%）
        #       最高字频 4.2% ≤ 5%，不触发 word-freq 清理；隔离结果保留，不被覆写。
        doc("美好时光总在闲暇中度过每年富有诗意的人生风景如画。热爱学习让知识积累产生成就感。\n\n★☆◆◇■□▲△●", "mixed.garb"),
        doc("★" * 30, "garbage.sym"),
    ]
    processed, records = detect_content_anomalies(docs)
    assert len(processed) == 3  # 全乱码只标记不过滤，处理交由调用方
    # doc0：无异常
    assert processed[0].metadata.get("has_content_anomaly", False) is False
    assert "word_freq_anomaly" not in processed[0].metadata
    # doc1：乱码段落被隔离（且因未触发词频清理，隔离结果未被覆写）
    mixed = processed[1]
    assert mixed.metadata.get("garbled_isolated") is True
    assert "★" not in mixed.page_content
    assert "[乱码段落" in mixed.page_content
    assert records[1].garbled_paragraphs
    assert records[1].word_freq_anomaly is False
    # doc2：全乱码
    garbage = processed[2]
    assert garbage.metadata["content_status"] == "full_garbage"
    assert records[2].full_garbage is True
    assert "不入库" in records[2].actions_taken[0]


def test_stage_one_empty_input() -> None:
    docs: list[Document] = []
    processed, records = detect_content_anomalies(docs)
    assert processed == [] and records == []


# ── 阶段2端到端 ─────────────────────────────────────────────────────


def test_stage_two_flags_and_merges_prev_records() -> None:
    docs = [
        doc("字" * 50, "s0.txt"),
        doc("字" * 120, "s1.txt"),
        doc("字" * 130, "s2.txt"),
        doc("字" * 140, "s3.txt"),
        doc("字" * 5000, "s4_long.txt"),
        doc("计算机computer" * 12, "s5_mixed.txt"),
    ]
    prev = AnomalyRecord(source="s4_long.txt", garbled_paragraphs=[{"index": 0}])
    processed, records = detect_statistical_anomalies(docs, [prev])
    assert len(records) == 6
    # 离群标记进 metadata
    long_doc = next(d for d in processed if d.metadata["source_path"] == "s4_long.txt")
    assert long_doc.metadata["length_outlier"] == "too_long"
    assert long_doc.metadata["length_suggestion"]
    # prev record 合并：阶段1字段保留
    rec_long = next(r for r in records if r.source == "s4_long.txt")
    assert rec_long.garbled_paragraphs == [{"index": 0}]
    assert rec_long.length_outlier == "too_long"
    # 语言混杂
    mixed_rec = next(r for r in records if r.source == "s5_mixed.txt")
    assert mixed_rec.language_mixed is True
    assert mixed_rec.language_mix_ratio > 0


def test_stage_two_empty_documents_passthrough() -> None:
    docs: list[Document] = []
    prev = [AnomalyRecord(source="x")]
    processed, records = detect_statistical_anomalies(docs, prev)
    assert processed == [] and records == prev
