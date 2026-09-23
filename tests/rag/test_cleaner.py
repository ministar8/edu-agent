"""rag/cleaner.py 纯文本清洗函数测试（不依赖 TEI / Chroma）。"""

from rag.cleaner import _clean_markdown_text, _normalize_text, clean_text


class TestCleanText:
    def test_blank_returns_empty(self):
        assert clean_text("") == ""
        assert clean_text("   \n  ") == ""

    def test_removes_control_chars(self):
        assert clean_text("进\x00程") == "进程"

    def test_fullwidth_normalized_to_halfwidth(self):
        assert clean_text("ａｂｃ１２３") == "abc123"

    def test_collapses_excess_blank_lines(self):
        out = clean_text("第一段\n\n\n\n\n第二段")
        assert "第一段" in out
        assert "第二段" in out
        assert "\n\n\n" not in out

    def test_strips_surrounding_whitespace(self):
        assert clean_text("  正文  ") == "正文"


class TestNormalizeText:
    def test_blank_returns_empty(self):
        assert _normalize_text("") == ""
        assert _normalize_text("  \n ") == ""

    def test_nfkc_normalization(self):
        assert _normalize_text("ＡＢ") == "AB"

    def test_does_not_trim_content(self):
        assert _normalize_text("  a  ") == "  a  "

    def test_removes_control_chars(self):
        assert _normalize_text("a\x01b") == "ab"


class TestCleanMarkdownText:
    def test_blank_returns_empty(self):
        assert _clean_markdown_text("") == ""

    def test_caps_blank_runs_at_two(self):
        # _collapse_blank_lines 保留最多 2 个空行（即 "a\n\n\nb"），多余被丢弃
        assert _clean_markdown_text("a\n\n\n\n\nb") == "a\n\n\nb"
        assert _clean_markdown_text("a" + "\n" * 20 + "b") == "a\n\n\nb"

    def test_preserves_code_fence_body(self):
        out = _clean_markdown_text("```python\nprint(1)\n```")
        assert "print(1)" in out
        assert "```" in out

    def test_normalizes_fullwidth(self):
        assert "AB" in _clean_markdown_text("ＡＢ")


class TestIngestionChainReachesTools:
    """入库链必须真的执行 `tools/` 下的模块。

    `scripts/check_coverage_by_module.py` 用 `EXCLUDED = {"tools"}` 把整个 `tools/`
    排除出覆盖率门槛。这个排除**只有在「门禁端到端跑真实入库链」成立时才是对的** ——
    但门禁跑在**独立进程**里，pytest 的覆盖率测不到它
    （实测 `tools/imputer.py` 单测覆盖 **0%**，0/525 语句）。
    ★ **09-23 更正这个数字**：本文件新增 `test_clean_documents_reaches_anomaly_detector`
    之后，它已升到 **35.6%**（那条测试只 spy 了 anomaly、**真跑了** imputer）；
    补完 **106** 条表征测试后为 **77.4%**。**但这不削弱本测试的价值** —— 它守的是
    「`clean_documents` 还调不调 tools」，那是覆盖率数字答不了的问题。

    所以这个前提必须由测试守着：一旦 `clean_documents` 不再调用它们，
    排除照旧、门槛照旧绿，而 `tools/imputer.py`（**1336 行**、曾含全项目复杂度最高的
    `_semantic_segment` = 30，09-23 已降到 ≤24）会静默变成既无单测、也无门禁覆盖的死代码。
    这正是「保护机制存在 ≠ 生效」。

    ★ 与 `TestBuildIndexUsesRealPipeline` 的分工：那个测试把 `clean_documents` **整体 spy 掉**，
    只证明它"被调用"；这里跑**真实** `clean_documents`，只 spy 最底层的 tools 函数 ——
    补上"函数内部链路还在不在"这一段。
    """

    @staticmethod
    def _doc():
        from langchain_core.documents import Document

        return Document(
            page_content="# 进程管理\n\n进程是资源分配的基本单位，也是调度的基本单位。\n\n" * 20,
            metadata={"source_file": "knowledge/operating_system/01.md"},
        )

    def test_clean_documents_reaches_imputer(self, monkeypatch):
        import tools.imputer as imputer_mod
        from rag.cleaner import clean_documents

        calls: list[int] = []
        real = imputer_mod.impute_documents

        def spy(docs):
            calls.append(len(docs))
            return real(docs)

        monkeypatch.setattr(imputer_mod, "impute_documents", spy)
        clean_documents([self._doc()], fuzzy_dedup=False)

        assert calls, "clean_documents 必须到达 tools.imputer.impute_documents"

    def test_clean_documents_reaches_anomaly_detector(self, monkeypatch):
        import tools.anomaly as anomaly_mod
        from rag.cleaner import clean_documents

        calls: list[int] = []
        real = anomaly_mod.detect_content_anomalies

        def spy(docs):
            calls.append(len(docs))
            return real(docs)

        monkeypatch.setattr(anomaly_mod, "detect_content_anomalies", spy)
        clean_documents([self._doc()], fuzzy_dedup=False)

        assert calls, "clean_documents 必须到达 tools.anomaly.detect_content_anomalies"
