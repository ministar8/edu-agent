"""rag/fusion.py 测试：内容去重键、按 token 截断，以及**证据融合主逻辑**。

**主逻辑为什么必须测**：`fuse_evidence` 179 行，此前覆盖率 21% —— 未覆盖的正是它。
它决定**最终送给 LLM 的上下文长什么样**：证据顺序、来源配额、KG 插入位置、
token 预算裁剪。这些全都是静默的 —— 顺序错了、预算算错了，LLM 照样能回答，
只是质量悄悄下降。
"""

import pytest
from langchain_core.documents import Document

from core.settings import settings
from rag.evidence import AgentEvidence, KGEvidence, TextEvidence
from rag.fusion import (
    _content_key,
    _extract_kg_terms,
    _score_text_evidence,
    _truncate_profile,
    _truncate_to_tokens,
    afuse_documents,
    fuse_documents,
    fuse_evidence,
)
from rag.rag_utils import estimate_tokens


def _ev(content: str, collection: str = "os", source: str = "s.md", **metadata) -> TextEvidence:
    return TextEvidence(
        evidence_id="e1",
        content=content,
        collection=collection,
        source=source,
        metadata=metadata,
    )


class TestContentKey:
    def test_prefers_content_hash(self):
        assert _content_key(_ev("内容", collection="os", content_hash="abc")) == "os:abc"

    def test_falls_back_to_source_and_prefix(self):
        assert _content_key(_ev("内容片段", collection="ds", source="a.md")) == "ds:a.md:内容片段"

    def test_blank_hash_falls_back(self):
        assert _content_key(_ev("内容", collection="ds", content_hash="   ")).startswith("ds:")

    def test_stable_for_same_hash(self):
        a = _content_key(_ev("内容A", collection="os", content_hash="h"))
        b = _content_key(_ev("内容B", collection="os", content_hash="h"))
        assert a == b


class TestTruncateToTokens:
    def test_short_text_untouched(self):
        assert _truncate_to_tokens("短文本", 100) == "短文本"

    def test_non_positive_budget_returns_empty(self):
        text = "一段很长的中文内容" * 50
        assert _truncate_to_tokens(text, 0) == ""
        assert _truncate_to_tokens(text, -1) == ""

    def test_long_text_truncated_with_marker(self):
        out = _truncate_to_tokens("中" * 2000, 100)
        assert out.endswith("\n[...truncated]")
        assert len(out) < 2000

    def test_truncated_result_respects_budget(self):
        out = _truncate_to_tokens("中" * 2000, 100)
        # 截断标记本身有少量 token 开销，留出余量
        assert estimate_tokens(out) <= 200


class TestTruncateProfile:
    """覆盖 settings.MAX_STUDENT_PROFILE_TOKENS 缺失导致的休眠 AttributeError。"""

    def test_empty_returns_empty(self):
        assert _truncate_profile("") == ""

    def test_under_budget_untouched(self):
        profile = "该生数据结构基础较弱，需加强练习。"
        assert _truncate_profile(profile) == profile

    def test_over_budget_is_truncated(self):
        profile = "该生数据结构与算法基础较弱，需要加强练习。" * 200
        out = _truncate_profile(profile)

        assert out.endswith("\n[...truncated]")
        assert len(out) < len(profile)
        assert estimate_tokens(out) <= settings.MAX_STUDENT_PROFILE_TOKENS + 50


# ══════════════════════════════════════════════════════
# _extract_kg_terms
# ══════════════════════════════════════════════════════


def _tev(
    content, *, source="s.md", collection="os", knowledge_points=None, **fields
) -> TextEvidence:
    """构造"字段与 metadata 同步"的证据。

    **为什么不能直接用 `_ev`**：`_ev` 把 kwargs 全塞进 `metadata`，字段保持默认 0。
    而 `_score_text_evidence` 是**用 metadata 的键决定取哪个字段**、
    **值却取自字段本身**：

    ```python
    if "rerank_score" in ev.metadata:
        score = float(ev.rerank_score or 0.0)   # ← 字段是 0 就拿到 0
    ```

    生产路径 `text_evidence_from_document` 两者是同步的（metadata 有键才赋给字段），
    所以这不是缺陷；但**测试若只设 metadata，分数会全是 0.01**，断言就失去意义。
    """
    meta = dict(fields)
    return TextEvidence(
        evidence_id="e1",
        content=content,
        source=source,
        collection=collection,
        score=float(fields.get("score") or 0.0),
        rerank_score=float(fields.get("rerank_score") or 0.0),
        recall_score=float(fields.get("recall_score") or 0.0),
        knowledge_points=list(knowledge_points or []),
        metadata=meta,
    )


def _kg(nodes=None, paths=None, edges=None, serialized="图证据") -> KGEvidence:
    return KGEvidence(
        evidence_id="kg1",
        serialized=serialized,
        nodes=nodes or [],
        paths=paths or [],
        edges=edges or [],
    )


class TestExtractKgTerms:
    def test_empty(self):
        assert _extract_kg_terms([]) == set()

    def test_collects_nodes(self):
        assert _extract_kg_terms([_kg(nodes=["进程", "线程"])]) == {"进程", "线程"}

    def test_collects_path_items(self):
        assert _extract_kg_terms([_kg(paths=[["A", "B"], ["C"]])]) == {"A", "B", "C"}

    def test_collects_edge_fields(self):
        edges = [{"source": "S", "target": "T", "name": "N"}]
        assert _extract_kg_terms([_kg(edges=edges)]) == {"S", "T", "N"}

    def test_ignores_blank_and_missing(self):
        edges = [{"source": "  ", "target": "T"}, {"other": "x"}]
        assert _extract_kg_terms([_kg(nodes=["  ", "好"], edges=edges)]) == {"好", "T"}

    def test_dedupes_across_evidences(self):
        assert _extract_kg_terms([_kg(nodes=["A"]), _kg(nodes=["A", "B"])]) == {"A", "B"}


# ══════════════════════════════════════════════════════
# _score_text_evidence
# ══════════════════════════════════════════════════════


class TestScoreTextEvidence:
    """分数选择 + 四种加权。写错不会报错，只会让排序悄悄变样。"""

    def test_metadata_key_decides_which_score(self):
        """是 `metadata` 里**有没有这个键**决定用哪个分数，不是值是否 >0。"""
        ev = _ev("内容", rerank_score=0.0, recall_score=0.9)
        assert _score_text_evidence(ev, set()) == pytest.approx(0.01), "有 rerank_score 键就用它"

    def test_uses_recall_when_no_rerank_key(self):
        ev = _tev("内容", recall_score=0.9)
        assert _score_text_evidence(ev, set()) == pytest.approx(0.9)

    def test_uses_plain_score_as_last_resort(self):
        ev = _ev("内容")
        ev.score = 0.7
        assert _score_text_evidence(ev, set()) == pytest.approx(0.7)

    def test_zero_score_becomes_001(self):
        """0 分会被抬到 0.01 —— 保证"有证据"永远优于"没证据"。"""
        ev = _ev("内容", rerank_score=0.0)
        assert _score_text_evidence(ev, set()) == pytest.approx(0.01)

    def test_parent_window_bonus(self):
        base = _score_text_evidence(_ev("内容", rerank_score=1.0), set())
        boosted = _score_text_evidence(_ev("内容", rerank_score=1.0, _parent_expanded=True), set())
        assert boosted > base

    def test_parent_window_bonus_via_chunk_role(self):
        base = _score_text_evidence(_ev("内容", rerank_score=1.0), set())
        boosted = _score_text_evidence(
            _ev("内容", rerank_score=1.0, **{"section.chunk_role": "parent_window"}), set()
        )
        assert boosted > base

    def test_hyde_penalty(self):
        base = _score_text_evidence(_ev("内容", rerank_score=1.0), set())
        penalised = _score_text_evidence(_ev("内容", rerank_score=1.0, _hyde_fallback=True), set())
        assert penalised < base

    def test_noise_downgrade_penalty(self):
        base = _score_text_evidence(_ev("内容", rerank_score=1.0), set())
        penalised = _score_text_evidence(
            _ev("内容", rerank_score=1.0, _noise_downgraded=True), set()
        )
        assert penalised == pytest.approx(base * 0.5)

    def test_noise_downgrade_uses_explicit_factor(self):
        penalised = _score_text_evidence(
            _tev("内容", rerank_score=1.0, _noise_downgraded=True, _noise_downgrade_factor=0.2),
            set(),
        )
        assert penalised == pytest.approx(0.2)

    def test_kg_boost_via_knowledge_points(self):
        base = _score_text_evidence(_tev("内容", rerank_score=1.0), set())
        boosted = _score_text_evidence(
            _tev("内容", rerank_score=1.0, knowledge_points=["进程"]), {"进程"}
        )
        assert boosted > base

    def test_kg_boost_via_content_match(self):
        """知识点没命中，但正文里出现了 KG 词（长度 >=2）也应加权。"""
        base = _score_text_evidence(_ev("讲的是进程调度", rerank_score=1.0), set())
        boosted = _score_text_evidence(_ev("讲的是进程调度", rerank_score=1.0), {"进程"})
        assert boosted > base

    def test_short_kg_term_does_not_content_match(self):
        """长度 <2 的 KG 词不做正文匹配 —— 单字匹配噪声太大。"""
        base = _score_text_evidence(_ev("讲的是甲", rerank_score=1.0), set())
        boosted = _score_text_evidence(_ev("讲的是甲", rerank_score=1.0), {"甲"})
        assert boosted == pytest.approx(base)

    def test_penalties_stack_multiplicatively(self):
        ev = _tev("内容", rerank_score=1.0, _hyde_fallback=True, _noise_downgraded=True)
        assert _score_text_evidence(ev, set()) == pytest.approx(1.0 * 0.95 * 0.5)


# ══════════════════════════════════════════════════════
# fuse_evidence
# ══════════════════════════════════════════════════════


class TestFuseEvidenceDedupAndRank:
    def test_empty_inputs_produce_empty_result(self):
        fused = fuse_evidence(max_tokens=2000)
        assert fused.text_evidences == []
        assert fused.final_context == ""
        assert fused.sources == []

    def test_none_inputs_tolerated(self):
        fused = fuse_evidence(None, None, None, max_tokens=2000)
        assert fused.text_evidences == []

    def test_dedup_keeps_higher_scored_copy(self):
        low = _tev("同样内容", collection="os", rerank_score=0.1)
        high = _tev("同样内容", collection="os", rerank_score=0.9)
        fused = fuse_evidence([low, high], max_tokens=5000)
        assert len(fused.text_evidences) == 1
        assert fused.text_evidences[0].rerank_score == 0.9

    def test_ranking_is_descending_by_score(self):
        evs = [
            _ev("甲" * 50, source="a", rerank_score=0.2),
            _ev("乙" * 50, source="b", rerank_score=0.9),
            _ev("丙" * 50, source="c", rerank_score=0.5),
        ]
        fused = fuse_evidence(evs, max_tokens=5000)
        scores = [e.rerank_score for e in fused.text_evidences]
        assert scores == sorted(scores, reverse=True)

    def test_zero_token_budget_falls_back_to_setting(self):
        fused = fuse_evidence([_ev("内容")], max_tokens=0)
        assert fused.metadata["max_tokens"] == settings.CONTEXT_TOKEN_BUDGET


class TestFuseEvidenceDiversification:
    def test_max_three_per_source(self):
        evs = [_ev(f"内容{i}" * 30, source="same", rerank_score=0.9 - i * 0.01) for i in range(6)]
        fused = fuse_evidence(evs, max_tokens=100000)
        # 选中的前 3 条来自 same，其余进 overflow 但仍在列表里
        assert len(fused.text_evidences) == 6

    def test_overflow_goes_after_diversified(self):
        """超配额的证据排到末尾 —— 保证来源多样性优先于纯分数排序。"""
        evs = [_ev(f"独特{i}" * 40, source="same", rerank_score=0.9 - i * 0.01) for i in range(5)]
        evs.append(_ev("别的来源" * 40, source="other", rerank_score=0.1))
        fused = fuse_evidence(evs, max_tokens=100000)

        sources = [e.source for e in fused.text_evidences]
        assert sources.index("other") < sources.index("same", 3), "新来源应插在溢出项之前"


class TestFuseEvidenceBudget:
    def test_respects_max_tokens(self):
        evs = [_ev("甲" * 2000, source=f"s{i}", rerank_score=0.9) for i in range(10)]
        fused = fuse_evidence(evs, max_tokens=1500)
        assert estimate_tokens(fused.final_context) <= 1500 * 1.05

    def test_doc_budget_has_floor_of_1000(self):
        """预算被 KG / profile 吃掉后仍保留 1000 —— 否则正文会被挤空。"""
        fused = fuse_evidence(
            [_ev("内容" * 50)], kg_evidences=[_kg(serialized="图" * 5000)], max_tokens=1000
        )
        assert fused.metadata["doc_token_budget"] >= 1000

    def test_doc_budget_subtracts_kg_and_profile(self):
        fused = fuse_evidence(
            [_ev("内容" * 50)],
            kg_evidences=[_kg(serialized="图" * 400)],
            student_profile="画像" * 100,
            max_tokens=20000,
        )
        assert fused.metadata["doc_token_budget"] < 20000

    def test_partial_evidence_truncated_when_remaining_budget_meaningful(self):
        evs = [
            _ev("甲" * 4000, source="a", rerank_score=0.9),
            _ev("乙" * 4000, source="b", rerank_score=0.8),
        ]
        fused = fuse_evidence(evs, max_tokens=3000)
        assert "[...truncated]" in fused.final_context

    def test_metadata_records_counts(self):
        evs = [_ev("甲" * 100, source="a"), _ev("乙" * 100, source="b")]
        fused = fuse_evidence(evs, max_tokens=5000, depth="deep")
        m = fused.metadata
        assert m["input_text_evidence_count"] == 2
        assert m["deduped_text_evidence_count"] == 2
        assert m["retrieval_depth"] == "deep"
        assert m["max_tokens"] == 5000


class TestFuseEvidenceOrdering:
    """交叉排列：LLM 对首尾关注度更高，故把最相关的放首尾、次相关的放中间。"""

    def test_five_items_are_interleaved(self):
        evs = [
            _ev(f"标记{i}" + "甲" * 200, source=f"s{i}", rerank_score=1.0 - i * 0.01)
            for i in range(5)
        ]
        fused = fuse_evidence(evs, max_tokens=100000)

        ctx = fused.final_context
        positions = [ctx.index(f"标记{i}") for i in range(5)]
        # 期望顺序 [0,2,4,3,1]
        assert positions[0] < positions[2] < positions[4] < positions[3] < positions[1]

    def test_fewer_than_four_keeps_original_order(self):
        evs = [
            _ev(f"标记{i}" + "甲" * 200, source=f"s{i}", rerank_score=1.0 - i * 0.01)
            for i in range(3)
        ]
        fused = fuse_evidence(evs, max_tokens=100000)
        ctx = fused.final_context
        assert ctx.index("标记0") < ctx.index("标记1") < ctx.index("标记2")

    def test_kg_text_inserted_after_first_evidence(self):
        """KG 放在首条证据之后 —— 既不被埋没，也不抢首位。"""
        evs = [
            _ev("标记0" + "甲" * 200, source="a", rerank_score=0.9),
            _ev("标记1" + "甲" * 200, source="b", rerank_score=0.8),
        ]
        fused = fuse_evidence(evs, kg_evidences=[_kg(serialized="KG独特标记")], max_tokens=100000)

        ctx = fused.final_context
        assert ctx.index("标记0") < ctx.index("KG独特标记") < ctx.index("标记1")

    def test_kg_only_context(self):
        fused = fuse_evidence(kg_evidences=[_kg(serialized="只有图证据")], max_tokens=5000)
        assert "只有图证据" in fused.final_context
        assert fused.text_evidences == []

    def test_profile_appended_last(self):
        fused = fuse_evidence(
            [_ev("证据" * 50, source="a")],
            student_profile="画像独特标记",
            max_tokens=100000,
        )
        assert fused.final_context.rstrip().endswith("画像独特标记")

    def test_empty_kg_serialized_is_skipped(self):
        fused = fuse_evidence(
            [_ev("内容" * 50)], kg_evidences=[_kg(serialized="   ")], max_tokens=5000
        )
        assert fused.metadata["kg_tokens"] == 0


class TestFuseEvidenceSources:
    def test_sources_deduped_and_ordered(self):
        evs = [
            _ev("甲" * 100, source="a", rerank_score=0.9),
            _ev("乙" * 100, source="a", rerank_score=0.8),
            _ev("丙" * 100, source="b", rerank_score=0.7),
        ]
        fused = fuse_evidence(evs, max_tokens=100000)
        assert fused.sources == ["a", "b"]

    def test_kg_source_used_when_no_text(self):
        fused = fuse_evidence(kg_evidences=[_kg()], max_tokens=5000)
        assert fused.sources == ["knowledge_graph"]

    def test_diversity_score_computed(self):
        evs = [_ev("甲" * 100, source="a"), _ev("乙" * 100, source="b")]
        fused = fuse_evidence(evs, max_tokens=100000)
        assert fused.diversity_score == pytest.approx(1.0)

    def test_diversity_score_zero_without_text(self):
        assert fuse_evidence(max_tokens=5000).diversity_score == 0.0

    def test_agent_evidences_passed_through(self):
        agent = AgentEvidence(evidence_id="a1", agent_name="tutor", content="建议")
        fused = fuse_evidence([_ev("内容" * 50)], agent_evidences=[agent], max_tokens=5000)
        assert fused.agent_evidences == [agent]


# ══════════════════════════════════════════════════════
# fuse_documents / afuse_documents
# ══════════════════════════════════════════════════════


class TestFuseDocuments:
    def test_documents_converted_to_evidence(self):
        docs = [Document(page_content="内容" * 100, metadata={"source": "s.md"})]
        fused = fuse_documents(docs, max_tokens=5000)
        assert len(fused.text_evidences) == 1

    def test_structured_kg_takes_priority(self):
        """传了结构化 KG 就不再解析 `kg_supplement` —— 后者是兼容用的旧参数。"""
        docs = [Document(page_content="内容" * 100, metadata={})]
        structured = [_kg(nodes=["结构化标记"])]
        fused = fuse_documents(
            docs, kg_supplement="纯文本 KG", kg_evidences=structured, max_tokens=5000
        )
        assert fused.metadata["kg_nodes_count"] == 1
        assert "结构化标记" in fused.metadata["kg_text_boost_terms"]

    def test_plain_text_kg_used_when_structured_absent(self):
        docs = [Document(page_content="内容" * 100, metadata={})]
        fused = fuse_documents(docs, kg_supplement="纯文本补充", max_tokens=5000)
        assert fused.metadata["kg_evidence_count"] == 1

    def test_blank_kg_supplement_produces_no_kg(self):
        docs = [Document(page_content="内容" * 100, metadata={})]
        fused = fuse_documents(docs, kg_supplement="   ", max_tokens=5000)
        assert fused.metadata["kg_evidence_count"] == 0

    def test_empty_structured_list_is_respected(self):
        """显式传空列表 = "没有 KG"，不该回退去解析文本。"""
        docs = [Document(page_content="内容" * 100, metadata={})]
        fused = fuse_documents(docs, kg_supplement="纯文本", kg_evidences=[], max_tokens=5000)
        assert fused.metadata["kg_evidence_count"] == 0

    @pytest.mark.asyncio
    async def test_async_version_matches_sync(self):
        docs = [Document(page_content="内容" * 100, metadata={"source": "s.md"})]
        sync = fuse_documents(docs, max_tokens=5000)
        aout = await afuse_documents(docs, max_tokens=5000)
        assert sync.final_context == aout.final_context

    @pytest.mark.asyncio
    async def test_async_structured_kg_priority(self):
        docs = [Document(page_content="内容" * 100, metadata={})]
        aout = await afuse_documents(
            docs, kg_supplement="纯文本", kg_evidences=[_kg(nodes=["标记"])], max_tokens=5000
        )
        assert aout.metadata["kg_nodes_count"] == 1
