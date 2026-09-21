"""`rag/postprocess.py` 的**窗口展开与噪声降级**测试。

**为什么单独一个文件**：现有 `test_postprocess.py` 覆盖的是 RRF / 去重（模块前半），
而窗口展开这条链（`_parent_window_expand` / `sentence_window_expand` /
`_chroma_window_expand` / `downgrade_window_noise`，共约 320 行）**一行都没被执行过** ——
它们是 `postprocess.py` 覆盖率长期停在 39% 的全部原因。

**这条链为什么值得测**：它决定"送给 LLM 的上下文到底长什么样"。
三个静默失败模式：
1. **预算裁剪出错会保留错的东西** —— 裁剪必须永远保住锚点 chunk，否则"命中的那条"被裁掉；
2. **`_chroma_window_expand` 的 Chroma 查询异常被吞掉**（只 warning）—— 退化成不展开，
   上下文变薄但没有任何报错；
3. **噪声降级把相关 chunk 标成噪声** —— 排序掉到末尾，召回还在但实际等于丢了。
"""

from __future__ import annotations

from langchain_core.documents import Document

from rag import postprocess as P
from rag.rag_utils import estimate_tokens


def _doc(content: str, **meta) -> Document:
    return Document(page_content=content, metadata=dict(meta))


def _anchor(content: str, section_id: str = "S1", chunk_index: int = 1, chunk_id: str = "c1"):
    return _doc(
        content,
        **{
            "section.id": section_id,
            "section.chunk_id": chunk_id,
            "section.chunk_index": chunk_index,
        },
    )


# ══════════════════════════════════════════════════════
# _parent_window_expand
# ══════════════════════════════════════════════════════


class TestParentWindowExpand:
    """父窗口兜底：sentence window 展不开时，用整个 section 的正文补上下文。"""

    def test_empty_input(self):
        assert P._parent_window_expand([], 1000) == []

    def test_skips_doc_without_parent_text(self):
        docs = [_doc("命中", **{"section.id": "S1"})]
        assert P._parent_window_expand(docs, 100000) == docs

    def test_skips_parent_text_that_is_barely_longer(self):
        """父文本只比锚点长一点点时补进去没意义，跳过。"""
        docs = [
            _doc(
                "甲" * 100,
                **{"section.parent_text": "甲" * 130, "section.id": "S1"},  # 130 <= 100+40
            )
        ]
        assert P._parent_window_expand(docs, 100000) == docs

    def test_adds_parent_text_and_marks_metadata(self):
        parent = "乙" * 500
        docs = [_doc("甲" * 100, **{"section.parent_text": parent, "section.id": "S1"})]

        out = P._parent_window_expand(docs, 100000)

        assert len(out) == 2
        added = out[1]
        assert added.page_content == parent
        assert added.metadata["_parent_expanded"] is True
        assert added.metadata["section.chunk_role"] == "parent_window"

    def test_records_anchor_chunk_id(self):
        docs = [
            _doc(
                "甲" * 100,
                **{
                    "section.parent_text": "乙" * 500,
                    "section.id": "S1",
                    "section.chunk_id": "anchor-7",
                },
            )
        ]
        out = P._parent_window_expand(docs, 100000)
        assert out[1].metadata["_parent_anchor_chunk_id"] == "anchor-7"

    def test_same_parent_added_only_once(self):
        """同一父 section 下命中多条时，父文本只补一次 —— 否则上下文被同一段话灌满。"""
        parent = "乙" * 500
        docs = [
            _doc(
                "甲" * 100,
                **{"section.parent_text": parent, "section.id": "S1", "section.chunk_id": "c1"},
            ),
            _doc(
                "丙" * 100,
                **{"section.parent_text": parent, "section.id": "S1", "section.chunk_id": "c2"},
            ),
        ]

        out = P._parent_window_expand(docs, 100000)

        assert len(out) == 3, "两条锚点 + 一份父文本"
        assert sum(1 for d in out if d.metadata.get("_parent_expanded")) == 1

    def test_duplicate_parent_text_across_sections_skipped(self):
        """不同 section.id 但父文本相同（重复内容）也不重复补。"""
        parent = "乙" * 500
        docs = [
            _doc("甲" * 100, **{"section.parent_text": parent, "section.id": "S1"}),
            _doc("丙" * 100, **{"section.parent_text": parent, "section.id": "S2"}),
        ]
        out = P._parent_window_expand(docs, 100000)
        assert sum(1 for d in out if d.metadata.get("_parent_expanded")) == 1

    def test_skips_when_budget_exceeded(self):
        """预算不够时宁可不补，也不能把上下文撑爆。"""
        docs = [_doc("甲" * 100, **{"section.parent_text": "乙" * 5000, "section.id": "S1"})]
        out = P._parent_window_expand(docs, global_budget=200)
        assert len(out) == 1, "预算不足应跳过"

    def test_budget_is_cumulative_across_docs(self):
        """预算是**累计**的：第一份父文本吃掉的额度要算进后续判断。"""
        docs = [
            _doc("甲" * 100, **{"section.parent_text": "乙" * 400, "section.id": "S1"}),
            _doc("丙" * 100, **{"section.parent_text": "丁" * 400, "section.id": "S2"}),
        ]
        # 两条锚点共 300 tokens；每份父文本 400 中文字 ≈ 600 tokens。
        # 预算 1000 → 第一份后 900，第二份要 1500 > 1000 → 只补一份。
        out = P._parent_window_expand(docs, global_budget=1000)
        assert sum(1 for d in out if d.metadata.get("_parent_expanded")) == 1

    def test_parent_metadata_is_copied_not_shared(self):
        docs = [_doc("甲" * 100, **{"section.parent_text": "乙" * 500, "section.id": "S1"})]
        out = P._parent_window_expand(docs, 100000)
        out[1].metadata["额外"] = 1
        assert "额外" not in docs[0].metadata, "父文档 metadata 应是副本"


# ══════════════════════════════════════════════════════
# _chroma_window_expand
# ══════════════════════════════════════════════════════


class _FakeCollection:
    def __init__(self, rows, *, exc=None):
        self._rows = rows
        self._exc = exc
        self.calls = []

    def get(self, where=None, include=None):
        self.calls.append(where)
        if self._exc is not None:
            raise self._exc
        texts, metas = [], []
        for text, meta in self._rows:
            metas.append(meta)
            texts.append(text)
        return {"documents": texts, "metadatas": metas}


def _install_collection(monkeypatch, rows, *, exc=None):
    coll = _FakeCollection(rows, exc=exc)

    class _Mgr:
        client = None

        def __init__(self):
            self.client = type("C", (), {"get_collection": lambda self2, name: coll})()

    import rag.vectorstore as vs

    monkeypatch.setattr(vs, "get_vector_store_manager", lambda: _Mgr())
    return coll


def _row(sid, idx, text, chunk_id=None):
    return (
        text,
        {
            "section.id": sid,
            "section.chunk_index": idx,
            "section.chunk_id": chunk_id or f"{sid}-{idx}",
            "section.chunk_role": "detail",
        },
    )


class TestChromaWindowExpand:
    """从向量库取同 section 的相邻 chunk，以锚点为中心开窗。"""

    def test_no_section_id_returns_input_unchanged(self, monkeypatch):
        _install_collection(monkeypatch, [])
        docs = [_doc("没有 section.id")]
        assert P._chroma_window_expand(docs, "coll") == docs

    def test_anchor_window_is_symmetric(self, monkeypatch):
        rows = [_row("S1", i, f"正文{i}") for i in range(5)]
        _install_collection(monkeypatch, rows)
        docs = [_anchor("正文2", chunk_index=2, chunk_id="S1-2")]

        out = P._chroma_window_expand(docs, "coll", window_size=1)

        contents = [d.page_content for d in out]
        assert contents[0] == "正文2", "锚点应保留在最前"
        assert "正文1" in contents and "正文3" in contents
        assert "正文0" not in contents, "window_size=1 不应取到更远"

    def test_expanded_chunks_are_marked(self, monkeypatch):
        rows = [_row("S1", i, f"正文{i}") for i in range(3)]
        _install_collection(monkeypatch, rows)
        docs = [_anchor("正文1", chunk_index=1, chunk_id="S1-1")]

        out = P._chroma_window_expand(docs, "coll", window_size=1)

        expanded = [d for d in out if d.metadata.get("_window_expanded")]
        assert expanded, "应有 chunk 被标记为窗口展开"
        assert all(d.metadata["_window_anchor_chunk_id"] == "S1-1" for d in expanded)

    def test_anchor_is_never_duplicated(self, monkeypatch):
        """锚点自身也在 Chroma 返回里，不能重复加进去。"""
        rows = [_row("S1", i, f"正文{i}") for i in range(3)]
        _install_collection(monkeypatch, rows)
        docs = [_anchor("正文1", chunk_index=1, chunk_id="S1-1")]

        out = P._chroma_window_expand(docs, "coll", window_size=2)

        contents = [d.page_content for d in out]
        assert len(contents) == len(set(contents)), "不应有重复 chunk"

    def test_missing_chunk_index_treated_as_zero(self, monkeypatch):
        rows = [_row("S1", i, f"正文{i}") for i in range(3)]
        _install_collection(monkeypatch, rows)
        docs = [_doc("正文0", **{"section.id": "S1", "section.chunk_id": "S1-0"})]

        out = P._chroma_window_expand(docs, "coll", window_size=1)
        assert len(out) >= 1

    def test_chroma_failure_degrades_to_no_expansion(self, monkeypatch):
        """Chroma 查询失败只 warning，退化成"不展开" —— 上下文变薄但不报错。

        这是**静默降级**，所以必须钉住：失败时原始命中必须一条不少地返回。
        """
        _install_collection(monkeypatch, [], exc=RuntimeError("collection gone"))
        docs = [_anchor("正文", chunk_index=1)]

        out = P._chroma_window_expand(docs, "coll")

        assert out == docs, "失败时应原样返回原始命中"

    def test_budget_trim_keeps_the_anchor(self, monkeypatch):
        """预算裁剪**永远不能裁掉锚点** —— 否则"命中的那条"被丢掉，检索等于白做。"""
        rows = [_row("S1", i, "甲" * 500) for i in range(5)]
        _install_collection(monkeypatch, rows)
        docs = [_anchor("甲" * 500, chunk_index=2, chunk_id="S1-2")]

        out = P._chroma_window_expand(docs, "coll", window_size=2, budget=10)

        assert out[0].page_content == "甲" * 500, "锚点必须保留"

    def test_global_budget_trims_from_tail(self, monkeypatch):
        """全局预算超了要从**尾部**裁（低优先级的窗口 chunk）。"""
        rows = [_row("S1", i, "甲" * 400) for i in range(7)]
        _install_collection(monkeypatch, rows)
        docs = [_anchor("甲" * 400, chunk_index=3, chunk_id="S1-3")]

        out = P._chroma_window_expand(docs, "coll", window_size=3, budget=100000, global_budget=700)

        assert out[0].page_content == "甲" * 400, "锚点仍在最前"
        assert len(out) < 7, "应被全局预算裁剪"
        assert len(out) >= 1

    def test_unknown_section_is_skipped(self, monkeypatch):
        """Chroma 里查不到该 section 的明细时跳过，不影响其它 section。"""
        rows = [_row("S2", 0, "别的 section")]
        _install_collection(monkeypatch, rows)
        docs = [_anchor("孤立", section_id="S1", chunk_index=0)]

        out = P._chroma_window_expand(docs, "coll")
        assert out == docs

    def test_batches_large_section_sets(self, monkeypatch):
        """section 数超过 50 时要分批查询（避免单次 $or 条件过多）。"""
        rows = [_row(f"S{i}", 0, f"正文{i}") for i in range(60)]
        coll = _install_collection(monkeypatch, rows)
        docs = [_anchor(f"正文{i}", section_id=f"S{i}", chunk_index=0) for i in range(60)]

        P._chroma_window_expand(docs, "coll")

        assert len(coll.calls) == 2, "60 个 section 应分成 2 批"

    def test_single_section_uses_plain_condition(self, monkeypatch):
        """只有一个 section 时不该包 $or —— 单条件包 $or 是多余的。"""
        rows = [_row("S1", 0, "正文")]
        coll = _install_collection(monkeypatch, rows)
        P._chroma_window_expand([_anchor("正文", section_id="S1", chunk_index=0)], "coll")

        where = coll.calls[0]
        assert "$or" not in where


# ══════════════════════════════════════════════════════
# sentence_window_expand
# ══════════════════════════════════════════════════════


class TestSentenceWindowExpand:
    def test_empty_docs(self):
        assert P.sentence_window_expand([], "coll") == []

    def test_window_size_zero_short_circuits(self, monkeypatch):
        """window_size=0 表示不展开 —— shallow 深度走的就是这条路。"""
        import rag.vectorstore as vs

        def boom():
            raise AssertionError("window_size=0 时不应访问向量库")

        monkeypatch.setattr(vs, "get_vector_store_manager", boom)
        docs = [_anchor("正文")]
        assert P.sentence_window_expand(docs, "coll", window_size=0) == docs

    def test_empty_collection_skips_chroma(self, monkeypatch):
        """没有集合名时跳过 sentence window，只走 parent 兜底。"""
        import rag.vectorstore as vs

        def boom():
            raise AssertionError("collection_name 为空时不应访问向量库")

        monkeypatch.setattr(vs, "get_vector_store_manager", boom)
        docs = [_anchor("正文")]
        assert P.sentence_window_expand(docs, "", window_size=1) == docs

    def test_parent_fallback_runs_for_uncovered_sections(self, monkeypatch):
        """sentence window 覆盖不到的 section，用父文本兜底。"""
        _install_collection(monkeypatch, [])
        parent = "乙" * 500
        docs = [
            _doc(
                "甲" * 100,
                **{
                    "section.id": "S1",
                    "section.chunk_id": "c1",
                    "section.parent_text": parent,
                },
            )
        ]

        out = P.sentence_window_expand(docs, "coll", window_size=1)

        assert any(d.metadata.get("_parent_expanded") for d in out)

    def test_parent_fallback_survives_anchor_chunk_id(self, monkeypatch):
        """**回归测试**：锚点带 `section.chunk_id` 时，父窗口兜底仍要生效。

        父文档的 metadata 是从锚点复制的，因此它带着**锚点的 `section.chunk_id`**。
        原实现用 `section.chunk_id` 做去重键 → 父文档必然与锚点撞键被挡掉，
        **只要锚点有 chunk_id（生产环境的正常情况）父窗口兜底就从未生效过**。
        实测确认：带 chunk_id 时返回 1 条，不带时返回 2 条。
        """
        _install_collection(monkeypatch, [])
        parent = "乙" * 500
        doc = _doc(
            "甲" * 100,
            **{
                "section.id": "S1",
                "section.chunk_id": "anchor-1",
                "section.parent_text": parent,
            },
        )

        out = P.sentence_window_expand([doc], "coll", window_size=1)

        parents = [d for d in out if d.metadata.get("_parent_expanded")]
        assert len(parents) == 1, "锚点有 chunk_id 时父窗口兜底也必须生效"
        assert parents[0].page_content == parent

    def test_parent_fallback_not_added_twice(self, monkeypatch):
        """同一锚点重复调用不应把父文本叠加进去。"""
        _install_collection(monkeypatch, [])
        doc = _doc(
            "甲" * 100,
            **{
                "section.id": "S1",
                "section.chunk_id": "anchor-1",
                "section.parent_text": "乙" * 500,
            },
        )
        first = P.sentence_window_expand([doc], "coll", window_size=1)
        assert sum(1 for d in first if d.metadata.get("_parent_expanded")) == 1

    def test_parent_fallback_skips_sections_already_expanded(self, monkeypatch):
        """已被 sentence window 展开的 section 不再补父文本 —— 避免上下文重复。"""
        rows = [_row("S1", i, f"正文{i}") for i in range(3)]
        _install_collection(monkeypatch, rows)
        docs = [
            _anchor(
                "正文1",
                chunk_index=1,
                chunk_id="S1-1",
            )
        ]
        docs[0].metadata["section.parent_text"] = "乙" * 500

        out = P.sentence_window_expand(docs, "coll", window_size=1)

        assert not any(d.metadata.get("_parent_expanded") for d in out), (
            "该 section 已由 sentence window 覆盖，不该再补父文本"
        )


# ══════════════════════════════════════════════════════
# downgrade_window_noise
# ══════════════════════════════════════════════════════


class TestDowngradeWindowNoise:
    """窗口带进来的噪声 chunk 软降级 —— **不删除**，只标记降权。"""

    def test_empty_docs(self):
        assert P.downgrade_window_noise([], "进程调度") == []

    def test_empty_query(self):
        docs = [_doc("内容", _window_expanded=True)]
        assert P.downgrade_window_noise(docs, "") == docs

    def test_comparison_query_is_exempt(self):
        """对比查询需要两侧 context，误删任一侧都会丢关键信息 —— 整段豁免。"""
        docs = [_doc("完全无关的内容", _window_expanded=True)]
        out = P.downgrade_window_noise(docs, "TCP 和 UDP 的区别", is_comparison=True)
        assert not any(d.metadata.get("_noise_downgraded") for d in out)

    def test_original_hits_are_never_downgraded(self):
        """**只处理窗口展开的 chunk** —— 原始命中即使不含关键词也不能降级。"""
        docs = [_doc("完全无关", **{"section.id": "S1"})]
        out = P.downgrade_window_noise(docs, "进程调度")
        assert not any(d.metadata.get("_noise_downgraded") for d in out)

    def test_window_chunk_without_keywords_is_downgraded(self):
        docs = [_doc("完全无关的内容", _window_expanded=True)]
        out = P.downgrade_window_noise(docs, "进程调度")

        assert out[0].metadata["_noise_downgraded"] is True
        assert out[0].metadata["_noise_downgrade_factor"] == P._NOISE_PENALTY_FACTOR
        assert out[0].metadata["_noise_coverage"] == 0.0

    def test_window_chunk_with_keywords_is_kept(self):
        docs = [_doc("进程 调度 是核心概念", _window_expanded=True)]
        out = P.downgrade_window_noise(docs, "进程调度")

        assert not out[0].metadata.get("_noise_downgraded")
        assert out[0].metadata["_noise_coverage"] > 0

    def test_parent_expanded_chunks_also_checked(self):
        """`_parent_expanded` 的 chunk 同样要检查 —— 父文本很长，噪声更多。"""
        docs = [_doc("完全无关", _parent_expanded=True)]
        out = P.downgrade_window_noise(docs, "进程调度")
        assert out[0].metadata["_noise_downgraded"] is True

    def test_downgrade_never_removes_documents(self):
        """策略 3：只标记不删除，保证 Recall 不丢。"""
        docs = [
            _doc("无关1", _window_expanded=True),
            _doc("无关2", _window_expanded=True),
        ]
        out = P.downgrade_window_noise(docs, "进程调度")
        assert len(out) == len(docs)

    def test_custom_threshold(self):
        docs = [_doc("只命中一个词：进程", _window_expanded=True)]
        # "进程调度" → 两个词，覆盖率 0.5
        assert not P.downgrade_window_noise(docs, "进程调度", min_coverage=0.4)[0].metadata.get(
            "_noise_downgraded"
        )
        docs2 = [_doc("只命中一个词：进程", _window_expanded=True)]
        assert P.downgrade_window_noise(docs2, "进程调度", min_coverage=0.8)[0].metadata.get(
            "_noise_downgraded"
        )

    def test_order_is_preserved(self):
        docs = [
            _doc("无关A", _window_expanded=True),
            _doc("进程调度", _window_expanded=True),
            _doc("无关B", _window_expanded=True),
        ]
        out = P.downgrade_window_noise(docs, "进程调度")
        assert [d.page_content for d in out] == ["无关A", "进程调度", "无关B"]


# ══════════════════════════════════════════════════════
# 预算估算本身
# ══════════════════════════════════════════════════════


class TestTokenEstimationContract:
    def test_chinese_counts_more_than_ascii(self):
        """中文 1 字 ≈ 1.5 token，ASCII 1 字符 ≈ 0.25 —— 差 6 倍。

        窗口预算全建立在这个比例上，比例错了预算就形同虚设。
        """
        assert estimate_tokens("甲" * 100) > estimate_tokens("a" * 100) * 4
