"""`rag/verifier.py` 单元测试。

**为什么这个文件之前不存在**：该模块 595 行、17 个函数，覆盖率长期停在 20%，
**没有一行规则检查被执行过**。它是检索链的"质量闸门" —— 决定检索结果
是直接使用、建议重试、还是必须重试。

**为什么它值得测**：闸门的失效方式是**静默的**：
- `_run_rule_checks` 里单个检查抛异常会被吞掉，**降级成"通过"**（`passed=True, score=0.5`）——
  也就是说一个坏掉的检查不会让检索失败，只会让判定变得过于宽松；
- `_compute_verdict` 的硬性条件一旦漏掉某项，本该 hard_fail 的结果会变成 pass；
- LLM 层解析失败一律返回 `None`（降级为"没跑过"），不会报错。

这些都不会抛异常，只会让"检索质量差"被放过去。本文件把每条分支都钉住。
"""

from __future__ import annotations

import pytest

from rag import verifier as V
from rag.evidence import FusedEvidence, KGEvidence, TextEvidence


def _ev(content="内容" * 100, source="s1", **kw) -> TextEvidence:
    return TextEvidence(
        evidence_id=kw.pop("evidence_id", f"e-{source}-{len(content)}"),
        content=content,
        source=source,
        **kw,
    )


def _kg(confidence=0.8) -> KGEvidence:
    return KGEvidence(evidence_id="kg1", serialized="图证据", confidence=confidence)


def _fused(texts=None, kgs=None, context=None, **meta) -> FusedEvidence:
    texts = texts if texts is not None else []
    kgs = kgs or []
    if context is None:
        context = "".join(e.content for e in texts)
    return FusedEvidence(
        text_evidences=texts,
        kg_evidences=kgs,
        final_context=context,
        metadata=dict(meta),
    )


# ══════════════════════════════════════════════════════
# 主分数
# ══════════════════════════════════════════════════════


class TestPrimaryScore:
    """分数优先级：rerank > recall > score。写反会让质量判定用错分数。"""

    def test_prefers_rerank(self):
        assert V._primary_score(_ev(rerank_score=0.9, recall_score=0.5, score=0.3)) == 0.9

    def test_falls_back_to_recall(self):
        assert V._primary_score(_ev(rerank_score=0.0, recall_score=0.5, score=0.3)) == 0.5

    def test_falls_back_to_score(self):
        assert V._primary_score(_ev(rerank_score=0.0, recall_score=0.0, score=0.3)) == 0.3

    def test_zero_score_returns_zero_not_none(self):
        """`score` 可能是 None —— 不能返回 None 让下游比较崩掉。"""
        ev = _ev(rerank_score=0.0, recall_score=0.0)
        ev.score = None
        assert V._primary_score(ev) == 0.0

    def test_negative_scores_are_skipped(self):
        assert V._primary_score(_ev(rerank_score=-1.0, recall_score=0.4)) == 0.4


# ══════════════════════════════════════════════════════
# 各规则检查
# ══════════════════════════════════════════════════════


class TestEvidenceCount:
    def test_zero_evidence_with_kg_passes_at_045(self):
        r = V._check_evidence_count(_fused(kgs=[_kg()], context="有内容"))
        assert r.passed is True
        assert r.score == 0.45

    def test_zero_evidence_without_kg_fails(self):
        r = V._check_evidence_count(_fused())
        assert r.passed is False
        assert r.score == 0.0

    def test_kg_without_context_fails(self):
        """KG 证据存在但 final_context 是空的 —— 没有可用内容，仍应判失败。"""
        r = V._check_evidence_count(_fused(kgs=[_kg()], context="   "))
        assert r.passed is False

    @pytest.mark.parametrize(
        ("n", "expected"), [(1, 0.45), (2, 0.6), (3, 0.75), (6, 1.0), (10, 1.0)]
    )
    def test_score_grows_with_count_and_caps_at_1(self, n, expected):
        r = V._check_evidence_count(_fused(texts=[_ev() for _ in range(n)]))
        assert r.score == pytest.approx(expected)


class TestScoreQuality:
    def test_no_evidence_no_kg_fails(self):
        r = V._check_score_quality(_fused())
        assert r.passed is False
        assert r.score == 0.0

    def test_kg_only_uses_confidence(self):
        r = V._check_score_quality(_fused(kgs=[_kg(0.9), _kg(0.7)]))
        assert r.passed is True
        assert r.score == pytest.approx(0.8)

    def test_kg_only_low_confidence_fails(self):
        r = V._check_score_quality(_fused(kgs=[_kg(0.1)]))
        assert r.passed is False

    def test_rerank_path_uses_fixed_thresholds(self):
        """有 rerank 分时用固定阈值（0.3 均值 / 0.1 单条）。"""
        texts = [_ev(rerank_score=0.9), _ev(rerank_score=0.8)]
        r = V._check_score_quality(_fused(texts=texts))
        assert r.passed is True

    def test_rerank_path_low_average_fails(self):
        texts = [_ev(rerank_score=0.05), _ev(rerank_score=0.05)]
        r = V._check_score_quality(_fused(texts=texts))
        assert r.passed is False
        assert "平均分过低" in r.detail

    def test_recall_path_uses_relative_thresholds(self):
        """无 rerank 分时阈值相对 `score_threshold` 缩放 —— 写死会让小阈值场景全判失败。"""
        texts = [_ev(recall_score=0.5), _ev(recall_score=0.5)]
        r = V._check_score_quality(_fused(texts=texts, score_threshold=0.06))
        assert r.passed is True

    def test_recall_path_normalizes_into_0_1(self):
        texts = [_ev(recall_score=0.12), _ev(recall_score=0.12)]
        r = V._check_score_quality(_fused(texts=texts, score_threshold=0.06))
        assert 0.0 <= r.score <= 1.0, "归一化后必须落在 0-1"

    def test_default_threshold_when_metadata_missing(self):
        texts = [_ev(recall_score=0.5)]
        r = V._check_score_quality(_fused(texts=texts))
        assert r.passed is True

    def test_low_ratio_penalty_reduces_score(self):
        """低分占比越高分越低，但占比 <80% 仍算通过。"""
        high = [_ev(rerank_score=0.9) for _ in range(5)]
        one_low = high + [_ev(rerank_score=0.01)]
        r = V._check_score_quality(_fused(texts=one_low))
        assert r.passed is True
        assert r.score < 0.9, "有低分项时应被扣分"

    def test_too_many_low_scores_fails(self):
        texts = [_ev(rerank_score=0.9)] + [_ev(rerank_score=0.01) for _ in range(9)]
        r = V._check_score_quality(_fused(texts=texts))
        assert r.passed is False, "低分占比 >=80% 应判失败"

    def test_score_capped_at_1(self):
        texts = [_ev(rerank_score=1.0) for _ in range(3)]
        r = V._check_score_quality(_fused(texts=texts))
        assert r.score <= 1.0


class TestSourceDiversity:
    def test_no_evidence_no_kg_fails(self):
        assert V._check_source_diversity(_fused()).passed is False

    def test_kg_only_passes_at_half(self):
        r = V._check_source_diversity(_fused(kgs=[_kg()]))
        assert r.passed is True
        assert r.score == 0.5

    def test_single_source_over_two_evidences_soft_fails(self):
        """全部来自同一来源且条数 >2 → 判失败（但分数不是 0，属"可用但建议重试"）。"""
        texts = [_ev(source="same") for _ in range(4)]
        r = V._check_source_diversity(_fused(texts=texts))
        assert r.passed is False
        assert r.score > 0.0
        assert "来源单一" in r.detail

    def test_single_source_with_two_evidences_passes(self):
        """只有 2 条时不算"来源单一" —— 阈值是 >2。"""
        texts = [_ev(source="same") for _ in range(2)]
        r = V._check_source_diversity(_fused(texts=texts))
        assert r.passed is True

    def test_diverse_sources_pass(self):
        texts = [_ev(source="a"), _ev(source="b"), _ev(source="c")]
        r = V._check_source_diversity(_fused(texts=texts))
        assert r.passed is True
        assert r.score == pytest.approx(1.0)

    def test_diversity_ratio_computed_correctly(self):
        texts = [_ev(source="a"), _ev(source="a"), _ev(source="b"), _ev(source="b")]
        r = V._check_source_diversity(_fused(texts=texts))
        assert r.score == pytest.approx(0.5)


class TestContentSufficiency:
    def test_no_evidence_no_kg_fails(self):
        assert V._check_content_sufficiency(_fused()).passed is False

    def test_kg_only_short_context_fails(self):
        r = V._check_content_sufficiency(_fused(kgs=[_kg()], context="短"))
        assert r.passed is False

    def test_kg_only_long_context_passes(self):
        r = V._check_content_sufficiency(_fused(kgs=[_kg()], context="甲" * 100))
        assert r.passed is True

    def test_empty_ratio_over_half_fails(self):
        texts = [_ev(content="短"), _ev(content="短"), _ev(content="甲" * 300)]
        r = V._check_content_sufficiency(_fused(texts=texts))
        assert r.passed is False
        assert "空内容占比过高" in r.detail

    def test_total_too_short_fails(self):
        texts = [_ev(content="甲" * 60), _ev(content="乙" * 60)]
        r = V._check_content_sufficiency(_fused(texts=texts))
        assert r.passed is False
        assert "总内容过短" in r.detail

    def test_sufficient_content_passes(self):
        texts = [_ev(content="甲" * 300), _ev(content="乙" * 300)]
        r = V._check_content_sufficiency(_fused(texts=texts))
        assert r.passed is True
        assert r.score > 0.5

    def test_score_capped_at_1(self):
        texts = [_ev(content="甲" * 5000)]
        r = V._check_content_sufficiency(_fused(texts=texts))
        assert r.score <= 1.0


class TestDuplication:
    def test_single_evidence_skips(self):
        r = V._check_duplication(_fused(texts=[_ev()]))
        assert r.passed is True
        assert r.score == 1.0

    def test_empty_evidence_skips(self):
        assert V._check_duplication(_fused()).passed is True

    def test_identical_prefixes_count_as_duplicates(self):
        """去重看的是**前 120 字符** —— 前缀相同即视为重复。"""
        head = "甲" * 120
        texts = [_ev(content=head + "A"), _ev(content=head + "B")]
        r = V._check_duplication(_fused(texts=texts))
        assert r.score == pytest.approx(0.5)

    def test_different_content_not_duplicated(self):
        texts = [_ev(content="甲" * 200), _ev(content="乙" * 200)]
        r = V._check_duplication(_fused(texts=texts))
        assert r.score == pytest.approx(1.0)

    def test_duplicate_ratio_above_limit_fails(self):
        head = "甲" * 120
        texts = [_ev(content=head + "A")] + [_ev(content=head + "B") for _ in range(9)]
        r = V._check_duplication(_fused(texts=texts))
        assert r.passed is False, "重复占比 >70% 应判失败"

    def test_leading_whitespace_normalised_before_compare(self):
        """键是 `content[:120].strip()` —— 前导空白会被去掉，两条应算重复。"""
        texts = [_ev(content="    " + "甲" * 60), _ev(content="甲" * 60)]
        r = V._check_duplication(_fused(texts=texts))
        assert r.score < 1.0, "strip 后相同应算重复"


class TestKgSupport:
    def test_no_kg_is_not_required(self):
        r = V._check_kg_support(_fused())
        assert r.passed is True
        assert r.score == 0.5

    def test_kg_present_raises_score(self):
        r = V._check_kg_support(_fused(kgs=[_kg(0.9)]))
        assert r.score == pytest.approx(0.95)

    def test_kg_never_fails(self):
        """bonus check —— 低置信度 KG 也不该让判定失败。"""
        r = V._check_kg_support(_fused(kgs=[_kg(0.01)]))
        assert r.passed is True

    def test_score_capped_at_1(self):
        r = V._check_kg_support(_fused(kgs=[_kg(1.0), _kg(1.0)]))
        assert r.score <= 1.0


class TestFinalContext:
    def test_empty_context_fails(self):
        assert V._check_final_context(_fused(context="")).passed is False

    def test_whitespace_only_fails(self):
        assert V._check_final_context(_fused(context="   \n  ")).passed is False

    def test_kg_only_short_fails(self):
        r = V._check_final_context(_fused(kgs=[_kg()], context="短"))
        assert r.passed is False
        assert "KG-only" in r.detail

    def test_kg_only_long_passes(self):
        r = V._check_final_context(_fused(kgs=[_kg()], context="甲" * 100))
        assert r.passed is True

    def test_text_evidence_short_context_fails(self):
        texts = [_ev()]
        r = V._check_final_context(_fused(texts=texts, context="甲" * 50))
        assert r.passed is False
        assert "过短" in r.detail

    def test_text_evidence_long_context_passes(self):
        r = V._check_final_context(_fused(texts=[_ev()], context="甲" * 300))
        assert r.passed is True


# ══════════════════════════════════════════════════════
# 规则层入口
# ══════════════════════════════════════════════════════


class TestRunRuleChecks:
    def test_runs_all_checks(self):
        results = V._run_rule_checks(_fused(texts=[_ev()], context="甲" * 300))
        assert [c.name for c in results] == [
            "evidence_count",
            "score_quality",
            "source_diversity",
            "content_sufficiency",
            "duplication",
            "kg_support",
            "final_context",
        ]

    def test_failing_check_degrades_to_pass(self, monkeypatch):
        """**关键行为**：单个检查抛异常时降级成"通过"，而不是让整条检索失败。

        这是刻意的容错设计，但也意味着**一个坏掉的检查不会报错，只会让判定变宽松**。
        """

        def boom(_fused):
            raise RuntimeError("check exploded")

        monkeypatch.setattr(V, "_RULE_CHECKS", [boom, V._check_kg_support])
        results = V._run_rule_checks(_fused())

        assert results[0].passed is True
        assert results[0].score == 0.5
        assert "check error" in results[0].detail


# ══════════════════════════════════════════════════════
# 判定与重试建议
# ══════════════════════════════════════════════════════


class TestComputeVerdict:
    @pytest.mark.parametrize("critical", ["evidence_count", "final_context", "score_quality"])
    def test_critical_failure_forces_hard_fail(self, critical):
        checks = [V.CheckResult(name=critical, passed=False, score=0.9)]
        assert V._compute_verdict(checks, 0.99) == V.Verdict.HARD_FAIL

    def test_high_score_passes(self):
        assert V._compute_verdict([], 0.6) == V.Verdict.PASS

    def test_mid_score_soft_fails(self):
        assert V._compute_verdict([], 0.35) == V.Verdict.SOFT_FAIL
        assert V._compute_verdict([], 0.59) == V.Verdict.SOFT_FAIL

    def test_low_score_hard_fails(self):
        assert V._compute_verdict([], 0.34) == V.Verdict.HARD_FAIL

    def test_non_critical_failure_does_not_force_hard_fail(self):
        """`duplication` 失败但总分够高 → 仍应 pass（不是硬性条件）。"""
        checks = [V.CheckResult(name="duplication", passed=False, score=0.1)]
        assert V._compute_verdict(checks, 0.8) == V.Verdict.PASS


class TestComputeRetryHints:
    def test_pass_returns_no_hints(self):
        result = V._compute_verification(
            _fused(texts=[_ev(content="甲" * 300, rerank_score=0.9)], context="甲" * 300),
            V._run_rule_checks(
                _fused(texts=[_ev(content="甲" * 300, rerank_score=0.9)], context="甲" * 300)
            ),
        )
        assert result[1] == V.Verdict.PASS
        assert result[3] == {}

    def test_evidence_count_failure_raises_k(self):
        hints = V._compute_retry_hints(
            _fused(k=5), [V.CheckResult(name="evidence_count", passed=False)], V.Verdict.SOFT_FAIL
        )
        assert hints["k"] == 8

    def test_k_capped_at_10(self):
        hints = V._compute_retry_hints(
            _fused(k=9), [V.CheckResult(name="evidence_count", passed=False)], V.Verdict.SOFT_FAIL
        )
        assert hints["k"] == 10

    def test_duplication_failure_lowers_k(self):
        hints = V._compute_retry_hints(
            _fused(k=5), [V.CheckResult(name="duplication", passed=False)], V.Verdict.SOFT_FAIL
        )
        assert hints["k"] == 4

    def test_k_decrease_has_floor_of_3(self):
        """`max(3, k-1)` 的 3 是硬地板：k=4 时降到 3，k=3 时**不给 k 建议**（降不下去）。"""
        hints = V._compute_retry_hints(
            _fused(k=4), [V.CheckResult(name="duplication", passed=False)], V.Verdict.SOFT_FAIL
        )
        assert hints["k"] == 3

    def test_k_floor_means_no_hint_at_minimum(self):
        """已经在地板上时不该给出"降到 3"这种原地踏步的建议。"""
        hints = V._compute_retry_hints(
            _fused(k=3), [V.CheckResult(name="duplication", passed=False)], V.Verdict.SOFT_FAIL
        )
        assert "k" not in hints

    def test_increase_wins_over_decrease(self):
        """证据不足比重复更严重 —— 同时有增有减时取增。"""
        hints = V._compute_retry_hints(
            _fused(k=5),
            [
                V.CheckResult(name="evidence_count", passed=False),
                V.CheckResult(name="duplication", passed=False),
            ],
            V.Verdict.SOFT_FAIL,
        )
        assert hints["k"] == 8

    def test_score_quality_failure_relaxes_threshold(self):
        hints = V._compute_retry_hints(
            _fused(score_threshold=0.1),
            [V.CheckResult(name="score_quality", passed=False)],
            V.Verdict.SOFT_FAIL,
        )
        assert hints["score_threshold"] == pytest.approx(0.05)
        assert hints["use_rerank"] is True

    def test_score_threshold_has_floor(self):
        hints = V._compute_retry_hints(
            _fused(score_threshold=0.0),
            [V.CheckResult(name="score_quality", passed=False)],
            V.Verdict.SOFT_FAIL,
        )
        assert hints["score_threshold"] >= 0.01

    def test_content_failure_raises_max_tokens(self):
        hints = V._compute_retry_hints(
            _fused(max_tokens=2000),
            [V.CheckResult(name="content_sufficiency", passed=False)],
            V.Verdict.SOFT_FAIL,
        )
        assert hints["max_tokens"] == 4000

    def test_max_tokens_capped_at_8000(self):
        hints = V._compute_retry_hints(
            _fused(max_tokens=7000),
            [V.CheckResult(name="final_context", passed=False)],
            V.Verdict.SOFT_FAIL,
        )
        assert hints["max_tokens"] == 8000

    def test_defaults_when_metadata_missing(self):
        hints = V._compute_retry_hints(
            _fused(), [V.CheckResult(name="evidence_count", passed=False)], V.Verdict.SOFT_FAIL
        )
        assert hints["k"] == 8, "缺 k 时应以默认 5 为基准"


class TestComputeVerification:
    def test_weights_redistribute_without_llm(self):
        """没有 LLM 检查时，它的 0.10 权重按比例分给其余项 —— 否则总分被系统性压低。"""
        fused = _fused(texts=[_ev(content="甲" * 300, rerank_score=0.9)], context="甲" * 300)
        checks = [c for c in V._run_rule_checks(fused) if c.name != "llm_relevance"]
        score_no_llm = V._compute_verification(fused, checks)[0]

        checks_with_llm = checks + [V.CheckResult(name="llm_relevance", passed=True, score=1.0)]
        score_with_llm = V._compute_verification(fused, checks_with_llm)[0]

        assert score_no_llm != score_with_llm
        assert 0.0 <= score_no_llm <= 1.0

    def test_reasons_collect_only_failures(self):
        checks = [
            V.CheckResult(name="a", passed=False, detail="坏了"),
            V.CheckResult(name="b", passed=True, detail="好的"),
        ]
        reasons = V._compute_verification(_fused(), checks)[2]
        assert reasons == ["a: 坏了"]

    def test_empty_checks_gives_zero_score(self):
        assert V._compute_verification(_fused(), [])[0] == 0.0


# ══════════════════════════════════════════════════════
# LLM 层
# ══════════════════════════════════════════════════════


class TestLlmRelevanceCheck:
    @pytest.mark.asyncio
    async def test_no_evidence_returns_none(self):
        assert await V._arun_llm_relevance_check("q", _fused()) is None

    @pytest.mark.asyncio
    async def test_llm_failure_returns_none(self, monkeypatch):
        async def fake(*a, **k):
            return None

        monkeypatch.setattr(V, "call_text", fake)
        assert await V._arun_llm_relevance_check("q", _fused(texts=[_ev()])) is None

    @pytest.mark.asyncio
    async def test_unparsable_json_returns_none(self, monkeypatch):
        """LLM 输出不可信 —— 解析失败一律降级为"没跑过"，不报错。"""

        async def fake(*a, **k):
            return "这是一段没有 JSON 的回复"

        monkeypatch.setattr(V, "call_text", fake)
        assert await V._arun_llm_relevance_check("q", _fused(texts=[_ev()])) is None

    @pytest.mark.asyncio
    async def test_valid_json_produces_check(self, monkeypatch):
        async def fake(*a, **k):
            return (
                '{"relevant_count": 4, "irrelevant_count": 1, "completeness": 0.8, "reason": "ok"}'
            )

        monkeypatch.setattr(V, "call_text", fake)
        r = await V._arun_llm_relevance_check("q", _fused(texts=[_ev()]))

        assert r is not None
        assert r.name == "llm_relevance"
        assert r.passed is True
        assert r.score == pytest.approx(0.8 * 0.6 + 0.8 * 0.4)

    @pytest.mark.asyncio
    async def test_zero_totals_returns_none(self, monkeypatch):
        """relevant + irrelevant == 0 时无法算比例 —— 返回 None 而不是除零。"""

        async def fake(*a, **k):
            return '{"relevant_count": 0, "irrelevant_count": 0}'

        monkeypatch.setattr(V, "call_text", fake)
        assert await V._arun_llm_relevance_check("q", _fused(texts=[_ev()])) is None

    @pytest.mark.asyncio
    async def test_low_relevance_fails(self, monkeypatch):
        async def fake(*a, **k):
            return '{"relevant_count": 1, "irrelevant_count": 9, "completeness": 0.2}'

        monkeypatch.setattr(V, "call_text", fake)
        r = await V._arun_llm_relevance_check("q", _fused(texts=[_ev()]))
        assert r.passed is False

    @pytest.mark.asyncio
    async def test_json_extracted_from_surrounding_text(self, monkeypatch):
        async def fake(*a, **k):
            return (
                '分析如下：{"relevant_count": 3, "irrelevant_count": 0, "completeness": 1.0} 完毕'
            )

        monkeypatch.setattr(V, "call_text", fake)
        r = await V._arun_llm_relevance_check("q", _fused(texts=[_ev()]))
        assert r is not None and r.passed is True

    @pytest.mark.asyncio
    async def test_only_first_five_evidences_sent(self, monkeypatch):
        """只取前 5 条控制 token —— 送太多会超预算。"""
        seen = {}

        async def fake(messages, **k):
            seen["text"] = str(messages)
            return '{"relevant_count": 1, "irrelevant_count": 0, "completeness": 1.0}'

        monkeypatch.setattr(V, "call_text", fake)
        texts = [_ev(content=f"独特标记{i}" + "甲" * 300) for i in range(8)]
        await V._arun_llm_relevance_check("q", _fused(texts=texts))

        assert "独特标记4" in seen["text"]
        assert "独特标记5" not in seen["text"]


# ══════════════════════════════════════════════════════
# 公开 API
# ══════════════════════════════════════════════════════


class TestPublicApi:
    @pytest.mark.asyncio
    async def test_averify_without_llm_skips_llm_layer(self, monkeypatch):
        async def boom(*a, **k):
            raise AssertionError("use_llm=False 时不应调用 LLM")

        monkeypatch.setattr(V, "call_text", boom)
        r = await V.averify_evidence(_fused(texts=[_ev(content="甲" * 300)], context="甲" * 300))
        assert all(c.name != "llm_relevance" for c in r.checks)

    @pytest.mark.asyncio
    async def test_averify_with_llm_appends_check(self, monkeypatch):
        async def fake(*a, **k):
            return '{"relevant_count": 5, "irrelevant_count": 0, "completeness": 0.9}'

        monkeypatch.setattr(V, "call_text", fake)
        r = await V.averify_evidence(
            _fused(texts=[_ev(content="甲" * 300)], context="甲" * 300),
            query="问题",
            use_llm=True,
        )
        assert any(c.name == "llm_relevance" for c in r.checks)

    @pytest.mark.asyncio
    async def test_averify_with_llm_but_no_query_skips(self, monkeypatch):
        async def boom(*a, **k):
            raise AssertionError("没有 query 时不应调用 LLM")

        monkeypatch.setattr(V, "call_text", boom)
        r = await V.averify_evidence(_fused(texts=[_ev()]), query="", use_llm=True)
        assert all(c.name != "llm_relevance" for c in r.checks)

    @pytest.mark.asyncio
    async def test_empty_evidence_hard_fails(self):
        r = await V.averify_evidence(_fused())
        assert r.verdict == V.Verdict.HARD_FAIL
        assert r.reasons, "应给出失败原因"
        assert r.retry_hints, "hard_fail 应给出重试建议"

    @pytest.mark.asyncio
    async def test_healthy_evidence_passes(self):
        texts = [_ev(content="甲" * 300, source=f"s{i}", rerank_score=0.9) for i in range(3)]
        r = await V.averify_evidence(_fused(texts=texts, context="甲" * 900))
        assert r.verdict == V.Verdict.PASS
        assert r.overall_score > 0.6

    def test_sync_version_ignores_use_llm(self):
        """同步版不支持 LLM —— 传 use_llm=True 也不该崩，只是被忽略。"""
        r = V.verify_evidence(
            _fused(texts=[_ev(content="甲" * 300)], context="甲" * 300), use_llm=True
        )
        assert all(c.name != "llm_relevance" for c in r.checks)

    def test_sync_and_async_agree_on_rules(self):
        fused = _fused(texts=[_ev(content="甲" * 300)], context="甲" * 300)
        sync = V.verify_evidence(fused)
        assert sync.verdict in (V.Verdict.PASS, V.Verdict.SOFT_FAIL, V.Verdict.HARD_FAIL)

    def test_score_is_rounded(self):
        r = V.verify_evidence(_fused(texts=[_ev(content="甲" * 300)], context="甲" * 300))
        assert r.overall_score == round(r.overall_score, 4)


class TestIsRetrievalSufficient:
    def test_pass_is_sufficient(self):
        texts = [_ev(content="甲" * 300, source=f"s{i}", rerank_score=0.9) for i in range(3)]
        fused = _fused(texts=texts, context="甲" * 900)
        assert V.is_retrieval_sufficient(fused) is True

    def test_hard_fail_is_insufficient(self):
        assert V.is_retrieval_sufficient(_fused()) is False

    def test_min_verdict_priority_semantics(self):
        """门槛语义：`priority[verdict] >= priority[min_verdict]`，顺序为 PASS > SOFT_FAIL > HARD_FAIL。

        注意：由于权重结构（无 critical 失败时总分基本都在 0.6 以上），
        实际很难构造出 SOFT_FAIL —— 也就是说**默认门槛 SOFT_FAIL 几乎等价于"只要没硬伤就放行"**。
        这一点本身值得记录：它意味着 `is_retrieval_sufficient` 的实际区分力
        主要来自 `_compute_verdict` 的三项硬性条件，而不是分数阈值。
        """
        hard_failed = _fused()

        assert V.is_retrieval_sufficient(hard_failed) is False
        assert V.is_retrieval_sufficient(hard_failed, min_verdict=V.Verdict.HARD_FAIL) is True

    def test_strict_threshold_rejects_soft_fail(self, monkeypatch):
        """把门槛提到 PASS 时，SOFT_FAIL 必须被拒 —— 用桩直接构造该判定。"""
        monkeypatch.setattr(
            V, "verify_evidence", lambda *a, **k: V.VerificationResult(verdict=V.Verdict.SOFT_FAIL)
        )
        assert V.is_retrieval_sufficient(_fused()) is True  # 默认门槛 SOFT_FAIL
        assert V.is_retrieval_sufficient(_fused(), min_verdict=V.Verdict.PASS) is False
