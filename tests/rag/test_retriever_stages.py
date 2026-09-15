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
from langchain_core.documents import Document

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


class TestStageDedupAndThreshold:
    """阶段 5+6：同章节去重 → 阈值过滤。

    两条容易写错的契约：
    1. 每章节保留数随**查询类别**浮动（练习/答案放宽到 4，对比/长查询 3，其余 2）——
       类别判断写错不会报错，只会静默改变保留条数；
    2. 两个计数（去重后 / 过阈值后）供指标使用，必须分别是**去重后**与**过滤后**的
       长度，不能混用（曾经把过滤后的长度填进"去重后"字段，指标就再也对不上了）。
    """

    @staticmethod
    def _cat(**flags):
        base = {
            "is_exercise": False,
            "is_answer": False,
            "is_comparison": False,
            "is_long": False,
        }
        base.update(flags)
        return SimpleNamespace(**base)

    def _patch(self, monkeypatch, deduped):
        seen = {}

        async def fake_thread(name, fn, results, timeout=None, default=None, max_per_section=None):
            seen["name"] = name
            seen["max_per_section"] = max_per_section
            seen["default_is_input"] = default is results
            return deduped

        monkeypatch.setattr(R, "_safe_to_thread", fake_thread)
        monkeypatch.setattr(R, "_log_final_retrieval_summary", lambda *a, **k: None)
        return seen

    @pytest.mark.asyncio
    async def test_max_per_section_follows_category(self, monkeypatch):
        seen = self._patch(monkeypatch, [])
        cases = [
            (self._cat(is_exercise=True), 4),
            (self._cat(is_answer=True), 4),
            (self._cat(is_comparison=True), 3),
            (self._cat(is_long=True), 3),
            (self._cat(), 2),
        ]
        for cat, expected in cases:
            await R._stage_dedup_and_threshold([], "q", cat, 0.0)
            assert seen["max_per_section"] == expected, f"类别 {cat} 应保留 {expected} 条"

    @pytest.mark.asyncio
    async def test_threshold_filters_by_score(self, monkeypatch):
        docs = [
            (Document(page_content="低分", metadata={}), 0.01),
            (Document(page_content="边界", metadata={}), 0.5),
            (Document(page_content="高分", metadata={}), 0.9),
        ]
        self._patch(monkeypatch, docs)
        filtered, deduped_count, passed_count = await R._stage_dedup_and_threshold(
            docs, "q", self._cat(), 0.5
        )
        assert [d.page_content for d in filtered] == ["边界", "高分"], "阈值是 >=，边界值应保留"
        assert deduped_count == 3, "去重后计数应是**去重结果**的长度"
        assert passed_count == 2, "过阈值计数应是**过滤后**的长度"

    @pytest.mark.asyncio
    async def test_counts_are_not_swapped(self, monkeypatch):
        """两个计数的语义不能互换 —— 混用会让指标永久对不上。"""
        docs = [(Document(page_content=str(i), metadata={}), float(i)) for i in range(5)]
        self._patch(monkeypatch, docs)
        _filtered, deduped_count, passed_count = await R._stage_dedup_and_threshold(
            docs, "q", self._cat(), 3.0
        )
        assert deduped_count == 5
        assert passed_count == 2
        assert deduped_count > passed_count, "本例去重后应多于过阈值后"

    @pytest.mark.asyncio
    async def test_dedup_failure_falls_back_to_input(self, monkeypatch):
        """去重超时/异常时必须回退原结果，不能把证据清空。"""
        seen = self._patch(monkeypatch, [])
        docs = [(Document(page_content="x", metadata={}), 0.9)]
        await R._stage_dedup_and_threshold(docs, "q", self._cat(), 0.0)
        assert seen["default_is_input"] is True, "default 必须是入参本身，作为失败兜底"
        assert seen["name"] == "async_section_dedup"

    @pytest.mark.asyncio
    async def test_empty_input_is_safe(self, monkeypatch):
        self._patch(monkeypatch, [])
        filtered, deduped_count, passed_count = await R._stage_dedup_and_threshold(
            [], "q", self._cat(), 0.5
        )
        assert (filtered, deduped_count, passed_count) == ([], 0, 0)


class TestStageRecallAndMerge:
    """阶段 4：多路召回 + 跨分支融合。

    这是拆分里最大也最危险的一段（含 `asyncio.gather` 并发与跨分支 RRF）。
    重点钉住四条契约：
    1. 单路只召回一次，不做融合；
    2. 分解时**原查询与子查询各成一路**，且子查询列表里等于原查询的项要剔除；
    3. 某一路失败只记 warning，**不能让整条检索失败**（少一路好过全失败）；
    4. 对比类查询只给**子查询**加精简路由白名单，原查询不加。
    """

    @staticmethod
    def _req(**overrides):
        base = {
            "query": "原查询",
            "collection_name": "coll",
            "coarse_k": 10,
            "filter": None,
            "cat": SimpleNamespace(is_comparison=False),
            "terms": ["原查询"],
            "use_rerank": True,
            "depth": SimpleNamespace(),
            "sub_queries": ["原查询"],
            "decomposed": False,
            "effective_threshold": 0.5,
        }
        base.update(overrides)
        return R._RecallRequest(**base)

    def _patch(self, monkeypatch, *, search_results=None, merge_result=None, fail_labels=()):
        calls = {"search": [], "merge": None, "dedup": []}

        async def fake_search(query, collection_name, k, **kwargs):
            calls["search"].append({"query": query, "k": k, **kwargs})
            if query in fail_labels:
                raise RuntimeError(f"branch failed: {query}")
            return list(search_results or [])

        async def fake_thread(name, fn, data, weights=None, timeout=None, default=None, **kwargs):
            # 融合调用的第 4 个位置参数是 RRF 权重；分支去重那次没有位置参数，
            # 权重保持 None —— 靠 name 区分，别把两者混在一起断言。
            if name == "async_weighted_rrf_merge":
                calls["merge"] = {
                    "data": data,
                    "weights": weights,
                    "timeout": timeout,
                    "kwargs": kwargs,
                }
                return merge_result
            calls["dedup"].append(name)
            return data

        monkeypatch.setattr(R, "_amulti_route_search", fake_search)
        monkeypatch.setattr(R, "_safe_to_thread", fake_thread)
        return calls

    @pytest.mark.asyncio
    async def test_single_path_recalls_once_without_merging(self, monkeypatch):
        sentinel = [(Document(page_content="x", metadata={}), 0.9)]
        calls = self._patch(monkeypatch, search_results=sentinel)

        out = await R._stage_recall_and_merge(self._req(decomposed=False))

        assert out == sentinel
        assert len(calls["search"]) == 1
        assert calls["search"][0]["query"] == "原查询"
        assert calls["search"][0]["k"] == 10
        assert calls["merge"] is None, "单路不应做 RRF 融合"
        assert calls["dedup"] == [], "单路不应在分支内去重"

    @pytest.mark.asyncio
    async def test_decomposed_creates_one_branch_per_unique_query(self, monkeypatch):
        calls = self._patch(monkeypatch, merge_result=[])

        await R._stage_recall_and_merge(
            self._req(decomposed=True, sub_queries=["原查询", "子A", "子B"])
        )

        queries = [c["query"] for c in calls["search"]]
        assert queries == ["原查询", "子A", "子B"], "等于原查询的子项应被剔除，不重复召回"
        assert calls["dedup"] == ["async_original_dedup", "async_sub_dedup", "async_sub_dedup"]
        assert calls["merge"] is not None

    @pytest.mark.asyncio
    async def test_merge_uses_original_over_sub_weights(self, monkeypatch):
        """原查询权重必须高于子查询 —— 写反会让子查询盖过用户原意。"""
        calls = self._patch(monkeypatch, merge_result=[])

        await R._stage_recall_and_merge(self._req(decomposed=True, sub_queries=["原查询", "子A"]))

        assert calls["merge"]["weights"] == {"original": 1.5, "sub": 1.0}
        assert calls["merge"]["timeout"] is not None, "融合也必须带超时，否则会挂死"

    @pytest.mark.asyncio
    async def test_branch_failure_does_not_abort(self, monkeypatch):
        """少一路召回好过整条检索失败 —— 这是刻意的容错设计。"""
        calls = self._patch(monkeypatch, merge_result=[], fail_labels=("子A",))

        out = await R._stage_recall_and_merge(
            self._req(decomposed=True, sub_queries=["原查询", "子A", "子B"])
        )

        assert out == []
        assert calls["merge"] is not None, "有分支失败时仍应继续融合"
        labels = [d[0] for d in calls["merge"]["data"]]
        assert "sub" in labels, "存活的分支仍要进入融合"

    @pytest.mark.asyncio
    async def test_all_branches_failing_still_merges_empty(self, monkeypatch):
        calls = self._patch(monkeypatch, merge_result=None, fail_labels=("原查询", "子A"))

        out = await R._stage_recall_and_merge(
            self._req(decomposed=True, sub_queries=["原查询", "子A"])
        )

        assert out == [], "融合返回 None 时必须兜底成空列表"
        assert calls["merge"]["data"] == []

    @pytest.mark.asyncio
    async def test_comparison_restricts_subquery_routes_only(self, monkeypatch):
        """对比类查询只给子查询加白名单 —— 原查询仍走全路由。"""
        calls = self._patch(monkeypatch, merge_result=[])

        await R._stage_recall_and_merge(
            self._req(
                decomposed=True,
                sub_queries=["原查询", "子A"],
                cat=SimpleNamespace(is_comparison=True),
            )
        )

        by_query = {c["query"]: c for c in calls["search"]}
        assert by_query["原查询"]["route_allowlist"] is None, "原查询不应被限制路由"
        assert by_query["子A"]["route_allowlist"] == R._COMPACT_SUBQUERY_ROUTES

    @pytest.mark.asyncio
    async def test_branches_pass_threshold_filtered_results_to_merge(self, monkeypatch):
        docs = [
            (Document(page_content="低", metadata={}), 0.1),
            (Document(page_content="高", metadata={}), 0.9),
        ]
        calls = self._patch(monkeypatch, search_results=docs, merge_result=[])

        await R._stage_recall_and_merge(
            self._req(decomposed=True, sub_queries=["原查询", "子A"], effective_threshold=0.5)
        )

        for _label, branch_docs in calls["merge"]["data"]:
            assert [d.page_content for d, _s in branch_docs] == ["高"], (
                "分支内应先过阈值，低分文档不应进入融合"
            )


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
