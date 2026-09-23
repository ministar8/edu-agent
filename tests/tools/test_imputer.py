"""`tools/imputer.py` 的表征测试（characterization tests）。

为什么先写这个再重构（backlog #36）
------------------------------------
`_semantic_segment` 是全项目**复杂度最高**的函数（mccabe **30**）、183 行，正钉住
`max-complexity` 棘轮；`imputer.py` 整体 1348 行、**单测覆盖基线很低**。
重构它之前必须先有安全网 —— 没有安全网的重构正是 §1 P0 警告的陷阱。

★ 这些测试**钉住当前行为**，不判断它是否「正确」。两处「看起来可疑但照实钉住」的观察：

1. **同主题的重复文本也会被切成 2 段** —— 分段并不只在「主题切换」处触发。
   可能是潜在问题，但**不是本次重构的目标**：重构必须保持行为不变。
2. **`max_chunk` 拆分会留下小于 `min_chunk` 的尾巴**（如 `char_count=9`）——
   因为 `n_parts = ceil(char_count / max_chunk)`，余数不参与再合并。

★ 位置/字符数依赖 **jieba 的分词结果**，在固定 jieba 版本下是确定性的。
若将来 jieba 升级导致这些用例变红，**先确认是「分词变了」而不是「逻辑变了」**，
再决定是更新用例还是修 bug。

覆盖率基线：本文件写成前 `imputer.py` 为 **35.6%**（187/525）——
来源是 `tests/rag/test_cleaner.py::test_clean_documents_reaches_anomaly_detector`，
它只 spy 了 `detect_content_anomalies`，**真跑了** `impute_documents`。
（`docs/ENGINEERING.md` 里写的「0%」是那条测试加入之前的旧数据。）
"""

from __future__ import annotations

import pytest
from langchain_core.documents import Document

from tools.imputer import (
    _detect_content_status,
    _impute_category,
    _impute_heading,
    _impute_heading_path,
    _impute_single_doc,
    _non_stopword_ratio,
    _resolve_segment_profile,
    _resource_guard,
    _semantic_segment,
    _tokenize_text,
    _validate_heading_candidate,
    get_heading_cache_stats,
    impute_documents,
)

# 三个词面互不相交的「主题」片段，用来构造主题切换。
_TOPIC_A = "二叉树的中序遍历先访问左子树再访问根节点最后访问右子树递归实现简洁。" * 4
_TOPIC_B = "死锁产生需要互斥条件请求与保持条件不可剥夺条件和循环等待条件同时满足。" * 4
_TOPIC_C = "哈希表的冲突解决方法有开放定址法和链地址法两种前者需要探测后者用链表。"

# 小参数档：默认 min_chunk=500 会让短文本直接返回 []，不便构造用例。
_SMALL: dict = {"min_chunk": 100, "max_chunk": 300, "window_size": 10, "stride": 5}


def _doc(text: str, **meta) -> Document:
    return Document(page_content=text, metadata=dict(meta))


@pytest.fixture(autouse=True)
def _reset_resource_guard():
    """`_resource_guard` 是模块级单例，配额会被前一个用例消耗掉。

    不重置的话，「配额耗尽 → 降级」这类分支会在用例间串味，产生**顺序相关**的偶发红。
    """
    _resource_guard.reset()
    yield
    _resource_guard.reset()


@pytest.fixture(autouse=True)
def _clear_heading_cache():
    """`_heading_cache` 也是模块级全局，键是 `f"{ext}:{source_path}"`（#37 修复后）。

    ★ 必须清 —— 否则前一个用例的推断结果会被后一个用例**当作缓存命中**返回，
    产生顺序相关的假绿/假红。
    """
    import tools.imputer as imputer_mod

    imputer_mod._heading_cache.clear()
    yield
    imputer_mod._heading_cache.clear()


# ── `_tokenize_text` ────────────────────────────────


class TestTokenizeText:
    def test_empty_and_whitespace_return_empty(self):
        assert _tokenize_text("") == []
        assert _tokenize_text("   \n\t ") == []

    def test_returns_words_without_stopwords(self):
        words = _tokenize_text("二叉树的中序遍历")
        assert words, "非空文本必须产出词"
        assert all(w.strip() for w in words), "不得包含纯空白 token"

    def test_stopwords_are_filtered(self):
        """`的` 在停用词表里 —— 它不该出现在结果中。"""
        from tools.imputer import _STOPWORDS

        if "的" not in _STOPWORDS:  # pragma: no cover - 表变了就跳过这条
            pytest.skip("`的` 已不在停用词表，本用例的前提失效")
        assert "的" not in _tokenize_text("二叉树的中序遍历")


# ── `_semantic_segment`：五条提前返回 ────────────────


class TestSemanticSegmentGuards:
    def test_empty_text_returns_empty(self):
        assert _semantic_segment("") == []

    def test_text_not_longer_than_min_chunk_returns_empty(self):
        assert _semantic_segment("短", min_chunk=10) == []
        # 恰好等于 min_chunk 也返回 []（条件是 `<=`，不是 `<`）
        assert _semantic_segment("字" * 10, min_chunk=10) == []

    def test_too_few_words_returns_empty(self):
        """`len(words) < window_size * 2` → []（词数不足无法做窗口比较）。"""
        assert _semantic_segment(_TOPIC_A + _TOPIC_B, min_chunk=10, window_size=500) == []

    def test_no_distance_peaks_returns_empty(self):
        """`diff_threshold=1.0` 时没有任何 Jaccard 距离能达标 → []。"""
        assert _semantic_segment(_TOPIC_A + _TOPIC_B, diff_threshold=1.0, **_SMALL) == []

    def test_single_segment_returns_empty(self):
        """`len(final) <= 1` 也返回 [] —— 只有 1 段时等于「没分段」。

        构造方式：把 `min_chunk` 提到超过所有候选分割点的字符位置，于是每个候选都被
        「分段达到最小长度」那道过滤掉，只剩最后那一段尾巴 → `len(final) == 1` → []。

        ★ 我最初以为「`max_chunk` 放大到超过全文」能达到同样效果 —— **错了**，
        那样反而得到 14 段（`min_chunk=10` 时几乎每个候选峰都能成段）。
        """
        text = _TOPIC_A + _TOPIC_B
        assert len(text) == 276
        assert _semantic_segment(text, min_chunk=200, window_size=10, stride=5) == []
        # 对照：min_chunk 降到 150 以下就又开始分段了
        assert _semantic_segment(text, min_chunk=100, window_size=10, stride=5) != []


# ── `_semantic_segment`：结构不变量（重构的安全网）──


class TestSemanticSegmentInvariants:
    """这些不变量是**重构必须保住的东西** —— 比逐个断言位置更抗改动。"""

    @pytest.mark.parametrize(
        ("text", "kwargs"),
        [
            (_TOPIC_A + _TOPIC_B, _SMALL),
            (_TOPIC_A + _TOPIC_B + _TOPIC_C, _SMALL),
            (_TOPIC_A + _TOPIC_A, _SMALL),
            (_TOPIC_A + _TOPIC_B, {**_SMALL, "diff_threshold": 0.0}),
            (
                _TOPIC_A + _TOPIC_B,
                {"min_chunk": 50, "max_chunk": 60, "window_size": 10, "stride": 5},
            ),
        ],
    )
    def test_invariants_hold(self, text, kwargs):
        segs = _semantic_segment(text, **kwargs)
        if not segs:
            pytest.skip("该参数下未产出分段，不变量无对象可验")

        # 1. 分段覆盖全文且无重叠
        assert sum(s["char_count"] for s in segs) == len(text)
        # 2. position 连续：下一段的 position == 上一段 position + char_count
        assert segs[0]["position"] == 0
        for prev, cur in zip(segs, segs[1:]):
            assert cur["position"] == prev["position"] + prev["char_count"]
        # 3. 每段不超过 max_chunk
        assert all(s["char_count"] <= kwargs["max_chunk"] for s in segs)
        # 4. 编号从 1 连续递增
        assert [s["label"] for s in segs] == [f"[第{i}段]" for i in range(1, len(segs) + 1)]
        # 5. 只有 ≥2 段才会返回（`len(final) > 1` 是最后的闸门）
        assert len(segs) >= 2

    def test_position_and_char_count_are_ints(self):
        segs = _semantic_segment(_TOPIC_A + _TOPIC_B, **_SMALL)
        assert segs
        for s in segs:
            assert isinstance(s["position"], int)
            assert isinstance(s["char_count"], int)
            assert isinstance(s["label"], str)


# ── `_semantic_segment`：钉住具体输出 ───────────────


class TestSemanticSegmentConcreteBehavior:
    def test_two_topic_text_is_split(self):
        """两个主题拼接 → 切在字符 110 处。

        ★ 具体数字依赖 jieba 分词结果（固定版本下确定）。这条用例的价值是：
        **重构后位置若发生变化，它立刻变红** —— 那正是我们要知道的。
        """
        segs = _semantic_segment(_TOPIC_A + _TOPIC_B, **_SMALL)
        assert segs == [
            {"position": 0, "label": "[第1段]", "char_count": 110},
            {"position": 110, "label": "[第2段]", "char_count": 166},
        ]

    def test_repeated_same_topic_also_splits(self):
        """★ 观察到的行为：**同主题重复文本也会被切成 2 段**。

        分段不只由「主题切换」触发。照实钉住 —— 重构不得改变它。
        """
        segs = _semantic_segment(_TOPIC_A + _TOPIC_A, **_SMALL)
        assert len(segs) == 2

    def test_small_max_chunk_leaves_remainder_below_min_chunk(self):
        """★ 观察到的行为：`ceil` 拆分会让余数段小于 `min_chunk`（这里出现 9 字符的段）。

        照实钉住。若将来要修，应作为独立改动（会改变行为），不要夹在重构里。
        """
        kwargs = {"min_chunk": 50, "max_chunk": 60, "window_size": 10, "stride": 5}
        segs = _semantic_segment(_TOPIC_A + _TOPIC_B, **kwargs)
        assert [s["char_count"] for s in segs] == [54, 56, 60, 9, 60, 37]
        assert min(s["char_count"] for s in segs) < kwargs["min_chunk"]

    def test_threshold_zero_still_respects_min_chunk(self):
        """`diff_threshold=0` 时处处是候选峰，但 `min_chunk` 仍会滤掉过短的段。"""
        segs = _semantic_segment(_TOPIC_A + _TOPIC_B, **{**_SMALL, "diff_threshold": 0.0})
        assert len(segs) == 2, "受 min_chunk 约束，不会碎成很多段"

    def test_tiny_min_chunk_fragments_the_text(self):
        """★ 观察到的行为：`min_chunk` 降到 10 时同一段文本碎成 **14 段**（每段 16~20 字符）。

        说明**分段数量对 `min_chunk` 高度敏感** —— 它不是「只影响下限」的温和参数。
        重构 `_semantic_segment` 时必须保住这一点。
        """
        segs = _semantic_segment(
            _TOPIC_A + _TOPIC_B, min_chunk=10, max_chunk=10_000, window_size=10, stride=5
        )
        assert len(segs) == 14
        assert [s["char_count"] for s in segs[:6]] == [18, 20, 16, 20, 16, 20]


# ── `_detect_content_status` ────────────────────────


class TestDetectContentStatus:
    @pytest.mark.parametrize("text", ["", "   ", "短文本", "九个字符都不到"])
    def test_short_or_empty_is_empty(self, text):
        assert _detect_content_status(_doc(text)) == "empty"

    def test_normal_text(self):
        assert _detect_content_status(_doc("这是一段足够长的正常正文内容，用于测试。")) == "normal"

    @pytest.mark.parametrize(
        "text",
        ["此处为图片，请参考原书。", "详见附表 3-1 的说明。", "参见下图所示的结构。"],
    )
    def test_placeholder_detected(self, text):
        assert _detect_content_status(_doc(text)) == "placeholder"

    def test_odd_code_fence_is_truncated(self):
        assert (
            _detect_content_status(_doc("正文内容足够长。\n```python\nprint(1)\n")) == "truncated"
        )

    def test_balanced_code_fences_are_normal(self):
        text = "正文内容足够长。\n```python\nprint(1)\n```\n结束。"
        assert _detect_content_status(_doc(text)) == "normal"

    def test_unclosed_paren_is_truncated(self):
        assert _detect_content_status(_doc("这是一段足够长的正文（但是没有闭合。")) == "truncated"

    def test_unclosed_bracket_is_truncated(self):
        assert _detect_content_status(_doc("这是一段足够长的正文【但是没有闭合。")) == "truncated"

    def test_more_closing_than_opening_is_normal(self):
        """闭括号多于开括号 → 不算截断（条件要求 `open > close`）。"""
        assert _detect_content_status(_doc("这是一段足够长的正文））没有开括号。")) == "normal"

    def test_placeholder_takes_precedence_over_fence(self):
        """占位符检测在围栏检测**之前** —— 两者同时命中时返回 placeholder。"""
        text = "此处为图片。\n```python\nprint(1)\n"
        assert _detect_content_status(_doc(text)) == "placeholder"


# ── `_validate_heading_candidate` ───────────────────


class TestValidateHeadingCandidate:
    def test_too_short_rejected(self):
        assert _validate_heading_candidate("", "任意正文") is False
        assert _validate_heading_candidate("短", "任意正文") is False

    @pytest.mark.parametrize("candidate", ["123", "1.2", "1-2_3", "007"])
    def test_numeric_candidates_rejected(self, candidate):
        assert _validate_heading_candidate(candidate, "任意正文") is False

    def test_unnamed_placeholder_accepted(self):
        """兜底标记 `[未命名文档]` 不走内容相关性检查。"""
        assert _validate_heading_candidate("[未命名文档]", "完全无关的正文") is True

    def test_all_stopwords_rejected(self):
        assert _validate_heading_candidate("的的的", "任意正文") is False

    def test_hallucinated_candidate_rejected(self):
        """候选词一个都不在正文里 → 覆盖率 0 → 拒绝。"""
        assert _validate_heading_candidate("量子纠缠", "二叉树的中序遍历") is False

    def test_grounded_candidate_accepted(self):
        assert _validate_heading_candidate("二叉树遍历", "二叉树的中序遍历与后序遍历") is True

    def test_half_coverage_is_the_boundary(self):
        """阈值是 `>= 0.5`：正好一半命中 → 通过。"""
        assert _validate_heading_candidate("二叉树 量子", "二叉树的中序遍历") is True


# ── `_non_stopword_ratio` ───────────────────────────


class TestNonStopwordRatio:
    def test_normal_text_returns_ratio_in_unit_interval(self, monkeypatch):
        _resource_guard.reset()
        ratio = _non_stopword_ratio("二叉树的中序遍历算法")
        assert 0.0 <= ratio <= 1.0

    def test_whitespace_only_returns_zero(self, monkeypatch):
        """无词 → `_compute()` 返回 0.0（**不是** 1.0，两者语义不同）。"""
        monkeypatch.setattr(_resource_guard, "check_and_record", lambda _name: True)
        assert _non_stopword_ratio("   \n\t ") == 0.0

    def test_quota_exhausted_degrades_to_one(self, monkeypatch):
        """配额耗尽 → 直接返回 1.0 放行（降级为字符级、不做停用词过滤）。"""
        monkeypatch.setattr(_resource_guard, "check_and_record", lambda _name: False)
        assert _non_stopword_ratio("的的的") == 1.0


# ── `_resolve_segment_profile` ──────────────────────


class TestResolveSegmentProfile:
    def test_category_exact_match_wins(self):
        profile = _resolve_segment_profile(_doc("正文", category="law", source_ext=".md"))
        assert profile.min_chunk == 800, "law 档案：min_chunk=800（大窗口、少分割）"

    def test_category_is_lowercased_and_stripped(self):
        profile = _resolve_segment_profile(_doc("正文", category="  LAW  "))
        assert profile.min_chunk == 800

    @pytest.mark.parametrize(
        ("ext", "expected_min"),
        [(".pdf", 500), (".md", 300), (".txt", 500), (".docx", 500), (".html", 500)],
    )
    def test_source_ext_fallback(self, ext, expected_min):
        profile = _resolve_segment_profile(_doc("正文", source_ext=ext))
        assert profile.min_chunk == expected_min

    def test_unknown_ext_falls_back_to_default(self):
        profile = _resolve_segment_profile(_doc("正文", source_ext=".xyz"))
        assert profile.min_chunk == 500

    def test_no_metadata_falls_back_to_default(self):
        profile = _resolve_segment_profile(Document(page_content="正文"))
        assert (profile.min_chunk, profile.max_chunk) == (500, 2000)

    def test_unknown_category_falls_through_to_ext(self):
        """category 不在档案表里 → 落到 `source_ext` 分支，而不是直接用 default。"""
        profile = _resolve_segment_profile(_doc("正文", category="不存在", source_ext=".md"))
        assert profile.min_chunk == 300, ".md → tech 档案"


# ── `_impute_heading`：优先级链 ─────────────────────


class TestImputeHeadingPriority:
    def test_existing_heading_returns_none(self):
        assert _impute_heading(_doc("正文", heading="已有标题")) is None

    def test_md_file_uses_markdown_heading(self):
        doc = _doc("# 第一章 绪论\n\n正文内容。", source_ext=".md")
        assert _impute_heading(doc) == ("第一章 绪论", "md_heading", "high")

    def test_non_md_file_does_not_use_markdown_heading(self):
        """`#` 标题只在 `.md` 文件上解析 —— 其他扩展名会落到后面的方法。"""
        doc = _doc("# 第一章 绪论\n\n正文内容。", source_ext=".txt")
        result = _impute_heading(doc)
        assert result is not None
        assert result[1] != "md_heading"

    def test_chapter_mark(self):
        doc = _doc("第3章 存储系统\n\n正文内容。", source_ext=".txt")
        assert _impute_heading(doc) == ("第3章 存储系统", "chapter_mark", "high")

    def test_filename_strips_numeric_prefix_and_separators(self):
        """`03_存储系统.md` → `存储系统`（去掉前导编号、`_` 换成空格）。"""
        doc = _doc("没有标题的正文内容。", source_path="cat/03_存储系统.md")
        assert _impute_heading(doc) == ("存储系统", "filename", "medium")

    def test_first_line_filtered_is_low_confidence_with_prefix(self):
        """首行提取命中 → low 置信度 → 加 `[推测]` 前缀。"""
        text = "存储系统概述\n\n这里是足够长的正文内容，讲存储系统。"
        doc = _doc(text, source_ext=".txt")
        heading, method, confidence = _impute_heading(doc)
        assert method == "first_line_filtered"
        assert confidence == "low"
        assert heading == "[推测]存储系统概述"

    def test_fallback_when_nothing_available(self):
        """正文里没有任何可提取的信号 → 兜底标记（**不加** `[推测]` 前缀）。"""
        doc = _doc("嗯嗯啊啊。", source_ext=".txt")
        heading, method, confidence = _impute_heading(doc)
        assert (method, confidence) == ("fallback", "low")
        assert heading == "[未命名文档]"

    def test_result_is_written_to_cache(self):
        import tools.imputer as imputer_mod

        doc = _doc("# 缓存标题\n\n正文内容。", source_ext=".md")
        _impute_heading(doc)
        # 无 `source_path` → 键退到「扩展名 + 内容前缀」
        assert imputer_mod._heading_cache == {
            f".md:{doc.page_content.strip()[:64]}": ("缓存标题", "high")
        }

    def test_same_source_path_shares_one_cache_entry(self):
        """★ 缓存的**本意**：同一份文件（如同一 PDF 拆出的多个 Document）复用推断结果。

        修 #37 时改的是「键的唯一性」，不能把这条本意一起改掉。
        """
        import tools.imputer as imputer_mod

        _impute_heading(_doc("# 缓存标题\n\n正文内容。", source_path="cat/x.md"))
        assert list(imputer_mod._heading_cache) == [".md:cat/x.md"]

    def test_second_call_hits_cache(self):
        import tools.imputer as imputer_mod

        doc = _doc("# 缓存标题\n\n正文内容。", source_ext=".md")
        first = _impute_heading(doc)
        # 篡改缓存，确认第二次真的读缓存而不是重新推断
        key = f".md:{doc.page_content.strip()[:64]}"
        imputer_mod._heading_cache[key] = ("被篡改", "medium")
        assert _impute_heading(doc) == ("被篡改", "filename", "medium")
        assert first == ("缓存标题", "md_heading", "high")


class TestImputeHeadingMinConfidence:
    def test_medium_skips_low_confidence_methods(self):
        doc = _doc("没有标题的正文内容。", source_path="cat/x.txt")
        heading, method, confidence = _impute_heading(doc, min_confidence="medium")
        assert (heading, method, confidence) == ("x", "filename", "medium")

    def test_medium_still_allows_filename(self):
        doc = _doc("正文内容足够长。", source_path="cat/存储系统.txt")
        assert _impute_heading(doc, min_confidence="medium")[1] == "filename"


# ── `_impute_heading`：已修的两个缺陷（钉住修好后的行为）──────


class TestImputeHeadingFixedDefects:
    """★ backlog **#37 / #38 已修**（09-23）。这里钉住**修好之后**的行为，防回归。

    修之前它们由 `TestImputeHeadingKnownDefects` 照实钉住「缺陷行为」——
    修完把断言翻转为「正确行为」，而不是删掉测试。
    """

    # ── #38：`min_confidence` 高于 low 且无适用方法时，不再拼出 `"[推测]None"` ──

    def test_no_none_string_when_min_confidence_skips_everything(self):
        """`min_confidence` 高于 low 且所有适用方法都失败 → 返回 `None`（= 无需填充）。

        修之前：`heading` 保持 `None`，末尾判据 `heading != "[未命名文档]"` 对 `None` 为真，
        于是 `f"{前缀}{None}"` 生成字符串 `"[推测]None"` **并写进缓存**。
        """
        doc = _doc("正文内容。", source_ext=".txt")
        assert _impute_heading(doc, min_confidence="medium") is None
        assert _impute_heading(doc, min_confidence="high") is None

    def test_nothing_is_cached_when_no_heading_could_be_inferred(self):
        """修之前那个垃圾值会被缓存；现在**不写缓存**（下次仍会重新推断）。"""
        import tools.imputer as imputer_mod

        _impute_heading(_doc("正文内容。", source_ext=".txt"), min_confidence="medium")
        assert imputer_mod._heading_cache == {}

    def test_default_low_path_still_uses_fallback(self):
        """★ 默认 `low` 路径**不受影响** —— 兜底照旧生效（生产链路走的就是这条）。"""
        doc = _doc("嗯嗯啊啊。", source_ext=".txt")
        heading, method, confidence = _impute_heading(doc)
        assert (heading, method, confidence) == ("[未命名文档]", "fallback", "low")

    # ── #37：缓存键能唯一标识来源文件 ──

    def test_cache_key_distinguishes_documents_without_source_path(self):
        """无 `source_path` 时不再退化成 `".md:"` —— 两个不同文档各拿各的标题。"""
        doc_a = _doc("# 二叉树遍历\n\nA 的正文。", source_ext=".md")
        doc_b = _doc("# 死锁条件\n\nB 的正文。", source_ext=".md")

        assert _impute_heading(doc_a)[0] == "二叉树遍历"
        assert _impute_heading(doc_b)[0] == "死锁条件"

    def test_cache_key_includes_directory(self):
        """同名 stem、不同目录不再互相串标题。

        真实知识库里就有这样一对：`computer_network/07_常考题型.md` 与
        `operating_system/07_常考题型.md` —— 它们**恰好**一级标题相同，
        所以修之前也没暴露（是运气，不是正确性）。
        """
        doc_c = _doc("# 二叉树遍历\n\nC 的正文。", source_path="ds/ch1.md")
        doc_d = _doc("# 死锁条件\n\nD 的正文。", source_path="os/ch1.md")

        assert _impute_heading(doc_c)[0] == "二叉树遍历"
        assert _impute_heading(doc_d)[0] == "死锁条件"


# ── `_impute_heading_path` / `_impute_category` ─────


class TestImputeHeadingPath:
    def test_existing_path_is_not_overwritten(self):
        doc = _doc("正文", heading_path="[已有]")
        assert _impute_heading_path(doc, "新标题") is None

    def test_built_from_heading_argument(self):
        assert _impute_heading_path(_doc("正文"), "第三章") == "[第三章]"

    def test_built_from_metadata_heading(self):
        assert _impute_heading_path(_doc("正文", heading="第二章"), None) == "[第二章]"

    def test_built_from_source_stem(self):
        doc = _doc("正文", source_path="operating_system/chapter1.md")
        assert _impute_heading_path(doc, None) == "[chapter1]"

    def test_nothing_available_returns_none(self):
        assert _impute_heading_path(_doc("正文"), None) is None

    def test_heading_takes_precedence_over_source(self):
        doc = _doc("正文", heading="标题", source_path="cat/file.md")
        assert _impute_heading_path(doc, None) == "[标题]"


class TestImputeCategory:
    def test_existing_category_is_not_overwritten(self):
        assert _impute_category(_doc("正文", category="已存在")) is None

    def test_inferred_from_first_path_part(self):
        doc = _doc("正文", source_path="operating_system/chapter1.md")
        assert _impute_category(doc) == "operating_system"

    @pytest.mark.parametrize("excluded", ["docs", "files", "data", "resources"])
    def test_excluded_directory_names_return_none(self, excluded):
        doc = _doc("正文", source_path=f"{excluded}/chapter1.md")
        assert _impute_category(doc) is None

    def test_single_part_path_returns_none(self):
        """`Path("chapter1.md").parts` 只有 1 段 → 不推断。"""
        assert _impute_category(_doc("正文", source_path="chapter1.md")) is None

    def test_no_source_returns_none(self):
        assert _impute_category(_doc("正文")) is None


# ── `_impute_single_doc` ────────────────────────────


class TestImputeSingleDoc:
    def test_empty_content_returns_early_with_only_content_status(self):
        doc, log = _impute_single_doc(_doc("", source_path="cat/x.md"))
        assert doc.metadata["content_status"] == "empty"
        assert [e["field"] for e in log] == ["content_status"]
        assert log[0]["method"] == "mark_empty"
        assert "heading" not in doc.metadata, "空内容必须提前返回，不进入元数据层"

    def test_normal_content_sets_normal_status(self):
        doc, _log = _impute_single_doc(_doc("这是一段足够长的正常正文内容。"))
        assert doc.metadata["content_status"] == "normal"

    def test_placeholder_sets_flag_and_logs(self):
        doc, log = _impute_single_doc(_doc("此处为图片，请参考原书。"))
        assert doc.metadata["content_status"] == "placeholder"
        assert doc.metadata["has_placeholder"] is True
        assert "has_placeholder" in [e["field"] for e in log]

    def test_truncated_sets_flag_and_logs(self):
        doc, log = _impute_single_doc(_doc("正文内容足够长（但没有闭合。"))
        assert doc.metadata["content_status"] == "truncated"
        assert doc.metadata["truncated"] is True
        assert "truncated" in [e["field"] for e in log]

    def test_fills_heading_path_and_category_from_path(self):
        doc, log = _impute_single_doc(
            _doc("这是一段足够长的正常正文内容。", source_path="operating_system/ch1.md")
        )
        assert doc.metadata["heading_path"] == "[ch1]"
        assert doc.metadata["category"] == "operating_system"
        fields = {e["field"] for e in log}
        assert {"heading_path", "category"} <= fields

    def test_mutates_the_same_document_object(self):
        """**原地修改**，不复制 —— 调用方拿到的就是同一个对象。"""
        doc = _doc("这是一段足够长的正常正文内容。", source_path="cat/x.md")
        out, _log = _impute_single_doc(doc)
        assert out is doc

    def test_impute_log_is_mirrored_into_metadata(self):
        doc, log = _impute_single_doc(_doc("这是一段足够长的正常正文。", source_path="cat/x.md"))
        assert doc.metadata["_impute_log"] == log

    def test_no_log_when_nothing_imputed(self):
        """已有全部元数据且内容正常 → 不产生日志、也不写 `_impute_log`。"""
        doc = _doc(
            "这是一段足够长的正常正文内容。",
            heading="已有标题",
            heading_path="[已有]",
            category="已存在",
        )
        out, log = _impute_single_doc(doc)
        assert log == []
        assert "_impute_log" not in out.metadata


# ── `impute_documents` ──────────────────────────────


class TestImputeDocuments:
    def test_empty_input(self):
        filled, log = impute_documents([], parallel=False)
        assert (filled, log) == ([], [])

    def test_empty_content_docs_are_excluded_from_output(self):
        docs = [
            _doc("", source_path="cat/a.md"),
            _doc("这是一段足够长的正常正文内容。", source_path="cat/b.md"),
        ]
        filled, log = impute_documents(docs, parallel=False)
        assert len(filled) == 1, "content_status=empty 的文档必须被剔除"
        assert filled[0].metadata["source_path"] == "cat/b.md"
        assert log, "被剔除的文档仍要留下日志"

    def test_serial_path_keeps_order(self):
        docs = [
            _doc(f"第{i}段足够长的正常正文内容。", source_path=f"cat/f{i}.md") for i in range(5)
        ]
        filled, _log = impute_documents(docs, parallel=False)
        assert [d.metadata["source_path"] for d in filled] == [f"cat/f{i}.md" for i in range(5)]

    def test_parallel_path_keeps_order(self):
        """>10 个文档会走并行分支 —— 结果必须按**原始顺序**排列。"""
        docs = [
            _doc(f"第{i}段足够长的正常正文内容。", source_path=f"cat/f{i:02d}.md")
            for i in range(12)
        ]
        filled, _log = impute_documents(docs, parallel=True, max_workers=4)
        assert [d.metadata["source_path"] for d in filled] == [
            f"cat/f{i:02d}.md" for i in range(12)
        ]

    def test_parallel_and_serial_agree(self):
        docs = [
            _doc(f"第{i}段足够长的正常正文内容。", source_path=f"cat/f{i:02d}.md")
            for i in range(12)
        ]
        serial, _ = impute_documents(list(docs), parallel=False)
        parallel, _ = impute_documents(list(docs), parallel=True, max_workers=4)
        assert [d.metadata for d in serial] == [d.metadata for d in parallel]

    def test_parallel_below_threshold_uses_serial(self):
        """`len(documents) > 10` 才并行 —— 10 个走串行（边界）。"""
        docs = [_doc(f"第{i}段足够长的正常正文。", source_path=f"cat/f{i}.md") for i in range(10)]
        filled, _log = impute_documents(docs, parallel=True)
        assert len(filled) == 10

    def test_log_entries_have_required_keys(self):
        docs = [_doc("这是一段足够长的正常正文内容。", source_path="cat/x.md")]
        _filled, log = impute_documents(docs, parallel=False)
        assert log
        for entry in log:
            assert {"field", "method", "source", "value"} <= set(entry)


# ── 资源守卫 ────────────────────────────────────────


class TestResourceGuard:
    def test_summary_is_a_human_readable_string(self):
        """★ `summary()` 返回**字符串**（不是 dict）—— 它直接拼进日志行。

        我最初断言它是 dict，实测是 `'calls() degraded(none)'`。
        """
        _resource_guard.reset()
        assert _resource_guard.summary() == "calls() degraded(none)"

    def test_recorded_call_shows_up_in_summary(self):
        _resource_guard.reset()
        _resource_guard.check_and_record("jieba_stopword")
        assert "jieba_stopword:1" in _resource_guard.summary()

    def test_reset_clears_counters(self):
        _resource_guard.reset()
        _resource_guard.check_and_record("jieba_stopword")
        assert _resource_guard.summary() != "calls() degraded(none)"
        _resource_guard.reset()
        assert _resource_guard.summary() == "calls() degraded(none)"

    def test_heading_cache_stats_shape(self):
        assert set(get_heading_cache_stats()) == {"size"}
