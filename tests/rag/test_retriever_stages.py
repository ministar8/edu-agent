"""`aretrieve_documents` 拆分出的阶段函数测试（拆分后新增）。

**这些测试本身就是拆分的目的**：428 行的单体编排无法单独测，拆成阶段函数后
每个都有明确输入输出，才第一次能针对单条分支写断言。

覆盖三段（确定性最强的三段，不依赖 Chroma 的近似检索）：

- `_stage_classify_query`：归一化 → 词项 → 分类（分类可复用传入值）
- `_stage_resolve_plan`：策略推导 + k / 重排 / 阈值调整
- `_stage_decompose_query`：三条分支的**优先级**（预计算 > 跳过 > 真分解）

`depth` 用 `SimpleNamespace` 冒充：函数只读属性，不做类型校验，
用轻量桩能让每个用例只声明它关心的字段。
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from rag import retriever as R


def _depth(**overrides):
    base = {"depth": "standard", "k": 5, "skip_rerank": False, "skip_decompose": False}
    base.update(overrides)
    return SimpleNamespace(**base)


class TestStageClassifyQuery:
    @pytest.mark.asyncio
    async def test_returns_terms_and_reuses_given_category(self, monkeypatch):
        called = []

        async def fake_classify(*a, **k):
            called.append(a)
            return "SHOULD-NOT-BE-USED"

        monkeypatch.setattr(R, "aclassify_query", fake_classify)
        given = "GIVEN-CAT"
        terms, cat = await R._stage_classify_query("什么是进程？", given)

        assert cat == "GIVEN-CAT", "传入分类时必须复用，不能再分类一次"
        assert called == [], "传入分类时不应调用分类器"
        assert isinstance(terms, list) and terms

    @pytest.mark.asyncio
    async def test_classifies_when_category_absent(self, monkeypatch):
        async def fake_classify(query, terms):
            return "COMPUTED-CAT"

        monkeypatch.setattr(R, "aclassify_query", fake_classify)
        _terms, cat = await R._stage_classify_query("什么是进程？", None)
        assert cat == "COMPUTED-CAT"

    @pytest.mark.asyncio
    async def test_terms_derive_from_normalized_text(self, monkeypatch):
        seen = {}

        async def fake_classify(query, terms):
            seen["terms"] = terms
            return "C"

        monkeypatch.setattr(R, "aclassify_query", fake_classify)
        monkeypatch.setattr(R, "normalize_query_text", lambda q: "NORMALIZED")
        monkeypatch.setattr(R, "extract_query_terms", lambda t: ["从归一化文本抽的词"])
        terms, _cat = await R._stage_classify_query("原始", None)

        assert terms == ["从归一化文本抽的词"]
        assert seen["terms"] == ["从归一化文本抽的词"], "分类器应收到归一化后抽的词"


class TestStageResolvePlan:
    def test_derives_depth_when_absent(self, monkeypatch):
        derived = _depth(k=7)
        monkeypatch.setattr(
            R,
            "resolve_retrieval_strategy",
            lambda cat: SimpleNamespace(depth=derived, layer="L", route_type="T"),
        )
        monkeypatch.setattr(R, "_resolve_retrieval_policy", lambda *a, **k: (0.1, 9))

        plan = R._stage_resolve_plan("q", "cat", 5, 0.06, True, None)

        assert plan.depth is derived
        assert plan.retrieval_layer == "L"
        assert plan.route_type == "T"

    def test_uses_given_depth_without_calling_strategy(self, monkeypatch):
        def boom(*a, **k):
            raise AssertionError("显式传入 depth 时不应推导策略")

        monkeypatch.setattr(R, "resolve_retrieval_strategy", boom)
        monkeypatch.setattr(
            R,
            "strategy_from_depth",
            lambda d: SimpleNamespace(depth=d, layer="L2", route_type="T2"),
        )
        monkeypatch.setattr(R, "_resolve_retrieval_policy", lambda *a, **k: (0.1, 9))

        plan = R._stage_resolve_plan("q", "cat", 5, 0.06, True, _depth())
        assert plan.retrieval_layer == "L2"

    def test_k_is_overridden_only_for_default_k(self, monkeypatch):
        """`k == 5` 是"调用方没指定"的哨兵值 —— 只有这种情况才用策略里的 k。"""
        monkeypatch.setattr(
            R,
            "resolve_retrieval_strategy",
            lambda cat: SimpleNamespace(depth=_depth(k=8), layer="L", route_type="T"),
        )
        monkeypatch.setattr(R, "_resolve_retrieval_policy", lambda *a, **k: (0.1, 9))

        assert R._stage_resolve_plan("q", "c", 5, 0.06, True, None).k == 8
        assert R._stage_resolve_plan("q", "c", 3, 0.06, True, None).k == 3, "显式 k 不应被覆盖"

    def test_rerank_disabled_when_depth_requires(self, monkeypatch):
        monkeypatch.setattr(
            R,
            "resolve_retrieval_strategy",
            lambda cat: SimpleNamespace(depth=_depth(skip_rerank=True), layer="L", route_type="T"),
        )
        monkeypatch.setattr(R, "_resolve_retrieval_policy", lambda *a, **k: (0.1, 9))

        assert R._stage_resolve_plan("q", "c", 5, 0.06, True, None).use_rerank is False

    def test_rerank_not_re_enabled_when_already_off(self, monkeypatch):
        """已经关掉的重排不应被"打开" —— 单向往 false 收敛。"""
        monkeypatch.setattr(
            R,
            "resolve_retrieval_strategy",
            lambda cat: SimpleNamespace(depth=_depth(skip_rerank=True), layer="L", route_type="T"),
        )
        monkeypatch.setattr(R, "_resolve_retrieval_policy", lambda *a, **k: (0.1, 9))

        assert R._stage_resolve_plan("q", "c", 5, 0.06, False, None).use_rerank is False

    def test_policy_receives_adjusted_k_and_rerank(self, monkeypatch):
        """阈值解析必须拿到**调整后**的 k 与 use_rerank，否则阈值算错。"""
        seen = {}

        def fake_policy(query, k, threshold, use_rerank, cat=None):
            seen.update(k=k, threshold=threshold, use_rerank=use_rerank, cat=cat)
            return 0.2, 11

        monkeypatch.setattr(
            R,
            "resolve_retrieval_strategy",
            lambda cat: SimpleNamespace(
                depth=_depth(k=8, skip_rerank=True), layer="L", route_type="T"
            ),
        )
        monkeypatch.setattr(R, "_resolve_retrieval_policy", fake_policy)

        plan = R._stage_resolve_plan("q", "CAT", 5, 0.06, True, None)

        assert seen["k"] == 8
        assert seen["use_rerank"] is False
        assert seen["threshold"] == 0.06
        assert seen["cat"] == "CAT"
        assert (plan.effective_threshold, plan.coarse_k) == (0.2, 11)


class TestStageDecomposeQuery:
    @pytest.mark.asyncio
    async def test_precomputed_wins_over_everything(self, monkeypatch):
        async def boom(*a, **k):
            raise AssertionError("有预计算结果时不应再分解")

        monkeypatch.setattr(R, "decompose", boom)
        subs, decomposed = await R._stage_decompose_query(
            "q", "c", _depth(skip_decompose=True), ["a", "b"]
        )
        assert subs == ["a", "b"]
        assert decomposed is True

    @pytest.mark.asyncio
    async def test_skip_decompose_returns_single_query(self, monkeypatch):
        async def boom(*a, **k):
            raise AssertionError("策略要求跳过时不应再分解")

        monkeypatch.setattr(R, "decompose", boom)
        subs, decomposed = await R._stage_decompose_query(
            "q", "c", _depth(skip_decompose=True), None
        )
        assert subs == ["q"]
        assert decomposed is False

    @pytest.mark.asyncio
    async def test_calls_decompose_otherwise(self, monkeypatch):
        seen = {}

        async def fake_decompose(query, cat=None):
            seen.update(query=query, cat=cat)
            return ["s1", "s2"]

        monkeypatch.setattr(R, "decompose", fake_decompose)
        subs, decomposed = await R._stage_decompose_query("q", "CAT", _depth(), None)

        assert subs == ["s1", "s2"]
        assert decomposed is True
        assert seen == {"query": "q", "cat": "CAT"}

    @pytest.mark.asyncio
    async def test_single_result_is_not_decomposed(self, monkeypatch):
        async def fake_decompose(query, cat=None):
            return [query]

        monkeypatch.setattr(R, "decompose", fake_decompose)
        _subs, decomposed = await R._stage_decompose_query("q", "c", _depth(), None)
        assert decomposed is False

    @pytest.mark.asyncio
    async def test_empty_result_is_not_decomposed(self, monkeypatch):
        async def fake_decompose(query, cat=None):
            return []

        monkeypatch.setattr(R, "decompose", fake_decompose)
        _subs, decomposed = await R._stage_decompose_query("q", "c", _depth(), None)
        assert decomposed is False, "空列表不算分解成功"

    @pytest.mark.asyncio
    async def test_precomputed_empty_list_is_respected(self, monkeypatch):
        """空列表是**显式传入**的值，不能被当成"没传"而回退去分解。"""

        async def boom(*a, **k):
            raise AssertionError("显式传入空列表时不应回退分解")

        monkeypatch.setattr(R, "decompose", boom)
        subs, decomposed = await R._stage_decompose_query("q", "c", _depth(), [])
        assert subs == []
        assert decomposed is False


class TestPlanIsImmutable:
    def test_plan_rejects_mutation(self):
        """计划对象是 frozen —— 防止下游"顺手改一下"，那会让阶段边界失去意义。"""
        plan = R._RetrievalPlan(
            depth=_depth(),
            k=5,
            use_rerank=True,
            effective_threshold=0.1,
            coarse_k=5,
            retrieval_layer="L",
            route_type="T",
        )
        with pytest.raises(Exception):
            plan.k = 99  # type: ignore[misc]
