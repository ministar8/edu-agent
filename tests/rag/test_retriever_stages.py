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


class TestStageRerank:
    """阶段 7：重排（可选）+ 重排后阈值过滤。

    **这段在端到端链路上跑不到**：门禁与阶段追踪都用 `use_rerank=False`
    （需要本地 TEI reranker 才能开），所以它只能靠单元测试覆盖 ——
    这也正是拆分的价值：拆之前这段分支没有任何测试能碰到。

    要钉住的契约：
    1. 分解路径候选池是单路的**两倍**（top_k=k*2），未启用重排时同样按两倍截断；
    2. `use_rerank=True` 但候选为空时**既不重排也不截断**；
    3. 重排耗时只在真的执行重排时产生，否则为 0。
    """

    @staticmethod
    def _docs(n=3):
        return [Document(page_content=str(i), metadata={}) for i in range(n)]

    def _patch(self, monkeypatch, *, rerank_out=None):
        calls = {"rerank": None, "log": [], "threshold": []}

        async def fake_thread(name, fn, *args, timeout=None, default=None, **kwargs):
            calls["rerank"] = {
                "name": name,
                "args": args,
                "timeout": timeout,
                "default": default,
                **kwargs,
            }
            return rerank_out if rerank_out is not None else args[1]

        def fake_threshold(docs, min_keep=0):
            calls["threshold"].append(min_keep)
            return docs

        monkeypatch.setattr(R, "_safe_to_thread", fake_thread)
        monkeypatch.setattr(R, "_apply_rerank_threshold", fake_threshold)
        monkeypatch.setattr(
            R, "_log_final_retrieval_summary", lambda label, q, d: calls["log"].append(label)
        )
        return calls

    @pytest.mark.asyncio
    async def test_no_rerank_truncates_to_k(self, monkeypatch):
        calls = self._patch(monkeypatch)
        docs = self._docs(10)

        out, used, ms = await R._stage_rerank(docs, "q", 3, False, decomposed=False)

        assert out == docs[:3]
        assert used is False
        assert ms == 0.0, "没重排就不该有耗时"
        assert calls["rerank"] is None

    @pytest.mark.asyncio
    async def test_no_rerank_decomposed_truncates_to_double_k(self, monkeypatch):
        """分解路径候选池是两倍 —— 截断口径必须跟着走。"""
        self._patch(monkeypatch)
        docs = self._docs(10)

        out, _used, _ms = await R._stage_rerank(docs, "q", 3, False, decomposed=True)

        assert out == docs[:6]

    @pytest.mark.asyncio
    async def test_rerank_uses_k_for_single_path(self, monkeypatch):
        calls = self._patch(monkeypatch)
        docs = self._docs(5)

        out, used, ms = await R._stage_rerank(docs, "q", 3, True, decomposed=False)

        assert calls["rerank"]["top_k"] == 3
        assert calls["rerank"]["name"] == "async_rerank"
        assert used is True
        assert ms >= 0.0
        assert calls["log"] == ["async-post-rerank"]
        assert calls["threshold"] == [2], "重排后兜底保留 top-2"
        assert out == docs

    @pytest.mark.asyncio
    async def test_rerank_uses_double_k_for_decomposed(self, monkeypatch):
        calls = self._patch(monkeypatch)

        _out, _used, _ms = await R._stage_rerank(self._docs(5), "q", 3, True, decomposed=True)

        assert calls["rerank"]["top_k"] == 6, "分解路径候选池应为 k*2"
        assert calls["rerank"]["name"] == "async_rerank_decomposed"
        assert calls["log"] == ["async-post-rerank-decomposed"]

    @pytest.mark.asyncio
    async def test_empty_candidates_skip_rerank_without_truncating(self, monkeypatch):
        """没有候选时既不重排也不截断 —— 截断空列表没有意义，但会掩盖"空"这个事实。"""
        calls = self._patch(monkeypatch)

        out, used, ms = await R._stage_rerank([], "q", 3, True, decomposed=False)

        assert out == []
        assert used is False
        assert ms == 0.0
        assert calls["rerank"] is None, "空候选不应调用重排"

    @pytest.mark.asyncio
    async def test_rerank_fallback_matches_candidate_pool_when_decomposed(self, monkeypatch):
        """**重排失败兜底必须与候选池口径一致**（backlog #33）。

        原实现两条分支都写 `filtered[:k]`，而候选池是 `top_k = k*2 if decomposed else k`：
        非分解路径 `top_k == k` 恰好等价；**分解路径重排失败时只兜住一半候选**。
        重排失败本就是降级场景，此时再把候选砍半，等于**在降级上再降一级**。
        """
        calls = self._patch(monkeypatch)
        docs = self._docs(10)

        await R._stage_rerank(docs, "q", 3, True, decomposed=True)

        assert calls["rerank"]["default"] == docs[:6], "兜底应为 filtered[:k*2]，与候选池一致"

    @pytest.mark.asyncio
    async def test_rerank_fallback_matches_candidate_pool_when_single(self, monkeypatch):
        """非分解路径 `top_k == k`，兜底仍是 `filtered[:k]` —— 与原来一致，未被本次修复改变。"""
        calls = self._patch(monkeypatch)
        docs = self._docs(10)

        await R._stage_rerank(docs, "q", 3, True, decomposed=False)

        assert calls["rerank"]["default"] == docs[:3]

    @pytest.mark.asyncio
    async def test_rerank_fallback_agrees_with_no_rerank_truncation(self, monkeypatch):
        """**两条路径的口径一致性**：重排失败时的兜底条数，
        必须等于「未启用重排」时的截断条数 —— 两者都是"没有重排结果可用"的情形，
        不应该给出不同数量的候选。
        """
        calls = self._patch(monkeypatch)
        docs = self._docs(10)

        for decomposed in (True, False):
            calls = self._patch(monkeypatch)
            no_rerank_out, _u, _m = await R._stage_rerank(
                docs, "q", 3, False, decomposed=decomposed
            )
            fallback_len = len(calls["rerank"]["default"]) if calls["rerank"] else None

            calls = self._patch(monkeypatch)
            await R._stage_rerank(docs, "q", 3, True, decomposed=decomposed)
            fallback_len = len(calls["rerank"]["default"])

            assert fallback_len == len(no_rerank_out), (
                f"decomposed={decomposed}: 重排失败兜底 {fallback_len} 条 "
                f"vs 未启用重排 {len(no_rerank_out)} 条 —— 口径不一致"
            )

    @pytest.mark.asyncio
    async def test_rerank_timeout_comes_from_settings(self, monkeypatch):
        calls = self._patch(monkeypatch)
        monkeypatch.setattr(R.settings, "RERANK_TIMEOUT", 17)

        await R._stage_rerank(self._docs(3), "q", 3, True, decomposed=False)

        assert calls["rerank"]["timeout"] == 17.0


class TestContentKey:
    """HyDE 追加时的去重键。

    原实现在同一段里内联了两次这个表达式，抽出来是为了避免两处走样 ——
    一旦两处不一致，去重就会失效（同一文档被追加两次）。
    """

    def test_prefers_content_hash(self):
        doc = Document(page_content="正文", metadata={"content_hash": "H1", "source": "s.md"})
        assert R._content_key(doc) == "H1"

    def test_falls_back_to_source_plus_prefix(self):
        doc = Document(page_content="正文内容", metadata={"source": "s.md"})
        assert R._content_key(doc) == "s.md:正文内容"

    def test_falls_back_to_source_file_when_source_absent(self):
        doc = Document(page_content="正文内容", metadata={"source_file": "f.md"})
        assert R._content_key(doc) == "f.md:正文内容"

    def test_only_first_80_chars_participate(self):
        head = "甲" * 80
        a = Document(page_content=head + "A", metadata={"source": "s"})
        b = Document(page_content=head + "B", metadata={"source": "s"})
        assert R._content_key(a) == R._content_key(b), "第 80 字之后不参与去重键"

    def test_empty_metadata_still_produces_a_key(self):
        doc = Document(page_content="x", metadata={})
        assert R._content_key(doc) == ":x"


class TestStageHyde:
    """阶段 8：HyDE 兜底召回。

    三处容易写错且**不会报错**的地方：
    1. 阈值放宽到 `*0.8`（用同一把尺子会把 HyDE 召回几乎全滤掉）；
    2. 追加时按内容键去重，已存在的文档不重复计入 `added_count`；
    3. 兜底机制失败**只记 hyde_error 不抛出**（不该影响已拿到的正常结果）。
    """

    @staticmethod
    def _cat(**flags):
        base = {"is_comparison": False}
        base.update(flags)
        return SimpleNamespace(**base)

    @staticmethod
    def _depth(**flags):
        base = {
            "skip_hyde": False,
            "skip_bm25": False,
            "skip_metadata_routes": False,
            "skip_kg": False,
            "depth": "standard",
        }
        base.update(flags)
        return SimpleNamespace(**base)

    def _patch(
        self, monkeypatch, *, should=True, hyde_query="假设答案", hyde_results=None, rerank_out=None
    ):
        calls = {"search": [], "rerank": None}

        monkeypatch.setattr(R, "should_trigger_hyde", lambda *a: should)
        monkeypatch.setattr(R, "generate_hyde_query", lambda q: hyde_query)

        async def fake_search(query, collection_name, k, **kwargs):
            calls["search"].append({"query": query, **kwargs})
            return list(hyde_results or [])

        async def fake_thread(name, fn, *args, timeout=None, default=None, **kwargs):
            if name == "async_hyde_rerank":
                calls["rerank"] = {"args": args, "default": default, **kwargs}
                return rerank_out if rerank_out is not None else args[1]
            if name == "async_hyde_generate":
                return fn(*args) if args else hyde_query
            return default if default is not None else (args[1] if len(args) > 1 else [])

        monkeypatch.setattr(R, "_amulti_route_search", fake_search)
        monkeypatch.setattr(R, "_safe_to_thread", fake_thread)
        monkeypatch.setattr(R, "_log_final_retrieval_summary", lambda *a: None)
        return calls

    def _call(self, filtered, **overrides):
        kwargs = {
            "query": "q",
            "collection_name": "coll",
            "coarse_k": 10,
            "filter": None,
            "cat": self._cat(),
            "use_rerank": False,
            "depth": self._depth(),
            "k": 3,
            "effective_threshold": 0.5,
            "rerank_used": False,
        }
        kwargs.update(overrides)
        return R._stage_hyde(filtered, **kwargs)

    @pytest.mark.asyncio
    async def test_not_triggered_returns_input_untouched(self, monkeypatch):
        self._patch(monkeypatch, should=False)
        docs = [Document(page_content="a", metadata={})]

        out = await self._call(docs)

        assert out.docs is docs
        assert out.triggered is False
        assert out.elapsed_ms == 0.0
        assert out.error == ""

    @pytest.mark.asyncio
    async def test_skip_hyde_depth_never_calls_llm(self, monkeypatch):
        calls = self._patch(monkeypatch, should=True)
        await self._call([], depth=self._depth(skip_hyde=True))
        assert calls["search"] == []

    @pytest.mark.asyncio
    async def test_empty_hyde_query_does_not_trigger(self, monkeypatch):
        self._patch(monkeypatch, should=True, hyde_query="")
        out = await self._call([Document(page_content="a", metadata={})])
        assert out.triggered is False

    @pytest.mark.asyncio
    async def test_identical_hyde_query_does_not_trigger(self, monkeypatch):
        """LLM 原样返回查询串时不算触发 —— 否则等于把同一查询再召回一次。"""
        self._patch(monkeypatch, should=True, hyde_query="q")
        out = await self._call([Document(page_content="a", metadata={})])
        assert out.triggered is False

    @pytest.mark.asyncio
    async def test_relaxed_threshold_is_used(self, monkeypatch):
        """阈值必须放宽到 0.8 倍，否则 HyDE 召回会被自己的阈值全滤掉。"""
        docs = [
            (Document(page_content="保留", metadata={}), 0.45),
            (Document(page_content="滤掉", metadata={}), 0.35),
        ]
        self._patch(monkeypatch, should=True, hyde_results=docs)

        out = await self._call([Document(page_content="原", metadata={})], effective_threshold=0.5)

        added = [d.page_content for d in out.docs if d.metadata.get("_hyde_fallback")]
        assert added == ["保留"], "0.45 >= 0.5*0.8=0.4 应保留；0.35 < 0.4 应滤掉"

    @pytest.mark.asyncio
    async def test_existing_docs_are_not_duplicated(self, monkeypatch):
        existing = Document(page_content="已有", metadata={"content_hash": "H1"})
        dup = Document(page_content="已有", metadata={"content_hash": "H1"})
        self._patch(monkeypatch, should=True, hyde_results=[(dup, 0.9)])

        out = await self._call([existing])

        assert out.added_count == 0, "同一文档不应被追加第二次"
        assert len(out.docs) == 1

    @pytest.mark.asyncio
    async def test_new_docs_are_appended_and_counted(self, monkeypatch):
        new_doc = Document(page_content="新证据", metadata={"content_hash": "H2"})
        self._patch(monkeypatch, should=True, hyde_results=[(new_doc, 0.9)])

        out = await self._call([Document(page_content="原", metadata={"content_hash": "H1"})])

        assert out.added_count == 1
        assert len(out.docs) == 2
        assert new_doc.metadata["_hyde_fallback"] is True
        assert "_hyde_query" in new_doc.metadata

    @pytest.mark.asyncio
    async def test_failure_records_error_without_raising(self, monkeypatch):
        """兜底失败不能影响已经拿到的正常结果。"""
        docs = [Document(page_content="正常结果", metadata={})]
        self._patch(monkeypatch, should=True)

        async def boom(*a, **k):
            raise RuntimeError("hyde exploded")

        monkeypatch.setattr(R, "_amulti_route_search", boom)

        out = await self._call(docs)

        assert out.docs == docs, "异常时原结果必须原样保留"
        assert out.error == "RuntimeError"
        assert out.triggered is True, "已开始尝试，触发标记应为 True"

    @pytest.mark.asyncio
    async def test_rerank_inside_hyde_flips_rerank_used(self, monkeypatch):
        """HyDE 内走了重排，整条链路的 rerank_used 要跟着翻 —— 漏了会让指标少记。"""
        new_doc = Document(page_content="新", metadata={"content_hash": "H2"})
        calls = self._patch(
            monkeypatch, should=True, hyde_results=[(new_doc, 0.9)], rerank_out=[new_doc]
        )

        out = await self._call([], use_rerank=True, rerank_used=False)

        assert calls["rerank"] is not None
        assert calls["rerank"]["top_k"] == 3
        assert out.rerank_used is True

    @pytest.mark.asyncio
    async def test_rerank_not_called_when_disabled(self, monkeypatch):
        new_doc = Document(page_content="新", metadata={"content_hash": "H2"})
        calls = self._patch(monkeypatch, should=True, hyde_results=[(new_doc, 0.9)])

        out = await self._call([], use_rerank=False)

        assert calls["rerank"] is None
        assert out.rerank_used is False


class TestStageExpandWindows:
    """阶段 9：句子窗口展开 + 噪声软降级。

    最容易写错的是**跨集合分组**：未指定集合时要按 `_collection` 逐集合展开，
    因为窗口要在各自集合内取相邻 chunk —— 混在一起会取到别的集合的邻居。
    """

    @staticmethod
    def _cat():
        return SimpleNamespace(is_comparison=False)

    @staticmethod
    def _depth(label="standard"):
        return SimpleNamespace(depth=label)

    def _patch(self, monkeypatch, expand_out=None):
        calls = {"groups": [], "window_sizes": []}

        def fake_expand(docs, collection, window_size=0):
            calls["groups"].append(collection)
            calls["window_sizes"].append(window_size)
            return expand_out if expand_out is not None else list(docs)

        async def fake_thread(name, fn, *args, timeout=None, default=None, **kwargs):
            return fn()

        monkeypatch.setattr(R, "sentence_window_expand", fake_expand)
        monkeypatch.setattr(R, "_safe_to_thread", fake_thread)
        monkeypatch.setattr(R, "downgrade_window_noise", lambda docs, q, is_comparison=False: docs)
        monkeypatch.setattr(R, "_log_final_retrieval_summary", lambda *a: None)
        return calls

    @pytest.mark.asyncio
    async def test_empty_input_short_circuits(self, monkeypatch):
        calls = self._patch(monkeypatch)
        out = await R._stage_expand_windows(
            [], query="q", collection_name="c", cat=self._cat(), depth=self._depth()
        )
        assert out.docs == []
        assert out.elapsed_ms == 0.0
        assert calls["groups"] == []

    @pytest.mark.asyncio
    async def test_single_collection_expands_once(self, monkeypatch):
        calls = self._patch(monkeypatch)
        docs = [Document(page_content="a", metadata={})]

        await R._stage_expand_windows(
            docs, query="q", collection_name="coll", cat=self._cat(), depth=self._depth()
        )

        assert calls["groups"] == ["coll"]

    @pytest.mark.asyncio
    async def test_multi_collection_expands_per_collection(self, monkeypatch):
        """未指定集合时按 `_collection` 分组逐集合展开 —— 不能混在一起。"""
        calls = self._patch(monkeypatch)
        docs = [
            Document(page_content="a", metadata={"_collection": "c1"}),
            Document(page_content="b", metadata={"_collection": "c2"}),
            Document(page_content="c", metadata={"_collection": "c1"}),
        ]

        await R._stage_expand_windows(
            docs, query="q", collection_name="", cat=self._cat(), depth=self._depth()
        )

        assert sorted(calls["groups"]) == ["c1", "c2"], "每个集合各展开一次"

    @pytest.mark.asyncio
    async def test_docs_without_collection_are_returned_as_is(self, monkeypatch):
        calls = self._patch(monkeypatch)
        docs = [Document(page_content="a", metadata={})]

        out = await R._stage_expand_windows(
            docs, query="q", collection_name="", cat=self._cat(), depth=self._depth()
        )

        assert out.docs == docs
        assert calls["groups"] == [], "没有 _collection 时不做展开，原样返回"

    @pytest.mark.asyncio
    async def test_window_size_follows_depth(self, monkeypatch):
        """shallow=0（不展开）、standard=1、deep=2。"""
        calls = self._patch(monkeypatch)
        docs = [Document(page_content="a", metadata={})]

        for label, expected in (("shallow", 0), ("standard", 1), ("deep", 2)):
            calls["window_sizes"].clear()
            await R._stage_expand_windows(
                docs, query="q", collection_name="coll", cat=self._cat(), depth=self._depth(label)
            )
            assert calls["window_sizes"] == [expected], f"{label} 的窗口应为 {expected}"

    @pytest.mark.asyncio
    async def test_noise_downgrade_is_applied(self, monkeypatch):
        seen = {}
        self._patch(monkeypatch)
        monkeypatch.setattr(
            R,
            "downgrade_window_noise",
            lambda docs, q, is_comparison=False: seen.update(cmp=is_comparison) or docs,
        )
        await R._stage_expand_windows(
            [Document(page_content="a", metadata={})],
            query="q",
            collection_name="coll",
            cat=SimpleNamespace(is_comparison=True),
            depth=self._depth(),
        )
        assert seen["cmp"] is True, "对比类查询要传给降级逻辑"


class TestFinalizeRetrieval:
    """阶段 10：溯源标记 + 指标写入。

    标记会随证据流向生成阶段，用于回答"这条证据是怎么来的" ——
    写错不会报错，只会让下游拿不到溯源信息。
    """

    def _ctx(self, **overrides):
        base = {
            "query": "q",
            "collection_name": "coll",
            "k": 5,
            "coarse_k": 10,
            "effective_threshold": 0.5,
            # 指标里会读 depth 的这几个开关，桩必须给全 —— 缺字段会直接 AttributeError
            "depth": SimpleNamespace(
                depth="standard",
                skip_bm25=False,
                skip_metadata_routes=False,
                skip_kg=False,
            ),
            "retrieval_layer": "L",
            "route_type": "R",
            "cat": SimpleNamespace(source="rule"),
            "decomposed": False,
            "sub_queries": ["q"],
            "use_rerank": True,
            "rerank_used": True,
            "hyde_triggered": False,
            "hyde_added_count": 0,
            "hyde_error": "",
            "counters": R._RetrievalCounters(
                raw_results=40,
                after_dedup=30,
                after_threshold=20,
                after_rerank=10,
                after_window=12,
                window_added=2,
            ),
        }
        base.update(overrides)
        return R._RetrievalContext(**base)

    def _patch(self, monkeypatch):
        seen = {}
        monkeypatch.setattr(
            R.metrics,
            "emit_retrieve_summary",
            lambda query, collection, duration_ms, values: seen.update(
                query=query, collection=collection, values=values
            ),
        )
        return seen

    def test_stamps_provenance_metadata(self, monkeypatch):
        self._patch(monkeypatch)
        docs = [Document(page_content="a", metadata={})]

        R._finalize_retrieval(docs, ctx=self._ctx(), started_at=0.0, stage_ms={})

        meta = docs[0].metadata
        assert meta["_retrieval_depth"] == "standard"
        assert meta["_retrieval_layer"] == "L"
        assert meta["_route_type"] == "R"
        assert meta["_effective_k"] == 5
        assert meta["_coarse_k"] == 10

    def test_returns_the_same_docs(self, monkeypatch):
        self._patch(monkeypatch)
        docs = [Document(page_content="a", metadata={})]
        assert R._finalize_retrieval(docs, ctx=self._ctx(), started_at=0.0, stage_ms={}) is docs

    def test_stage_counters_reach_the_metric(self, monkeypatch):
        """各阶段计数必须都写进指标 —— 只看最终条数无法判断是哪一层滤掉的。"""
        seen = self._patch(monkeypatch)
        R._finalize_retrieval([], ctx=self._ctx(), started_at=0.0, stage_ms={})

        values = seen["values"]
        assert values["before_threshold"] == 40
        assert values["after_section_dedup"] == 30
        assert values["after_threshold"] == 20
        assert values["after_rerank"] == 10
        assert values["after_window"] == 12
        assert values["window_added"] == 2

    def test_stage_ms_is_merged_into_values(self, monkeypatch):
        seen = self._patch(monkeypatch)
        R._finalize_retrieval(
            [], ctx=self._ctx(), started_at=0.0, stage_ms={"classification_ms": 1.5, "hyde_ms": 0.0}
        )
        assert seen["values"]["classification_ms"] == 1.5
        assert seen["values"]["hyde_ms"] == 0.0

    def test_derived_counts_computed_from_final_docs(self, monkeypatch):
        seen = self._patch(monkeypatch)
        docs = [
            Document(page_content="abc", metadata={"_window_expanded": True, "rerank_score": 0.9}),
            Document(page_content="de", metadata={"section.chunk_role": "detail"}),
        ]
        R._finalize_retrieval(docs, ctx=self._ctx(), started_at=0.0, stage_ms={})

        values = seen["values"]
        assert values["window_expanded_count"] == 1
        assert values["context_chars"] == 5
        assert values["detail_hits"] == 1
        assert values["top_rerank_score"] == 0.9
        assert values["hit"] is True

    def test_empty_result_reports_miss(self, monkeypatch):
        seen = self._patch(monkeypatch)
        R._finalize_retrieval([], ctx=self._ctx(), started_at=0.0, stage_ms={})
        values = seen["values"]
        assert values["hit"] is False
        assert values["context_chars"] == 0
        assert values["top_rerank_score"] == 0.0
        assert values["avg_rerank_score"] == 0.0

    def test_depth_none_is_tolerated(self, monkeypatch):
        """`depth` 理论上不会为 None，但指标里对它有 `if depth else` 兜底，别让它崩。"""
        seen = self._patch(monkeypatch)
        R._finalize_retrieval([], ctx=self._ctx(depth=None), started_at=0.0, stage_ms={})
        values = seen["values"]
        assert values["retrieval_depth"] == ""
        assert values["skip_bm25"] is False


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
