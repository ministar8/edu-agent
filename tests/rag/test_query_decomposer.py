"""rag/query_decomposer.py 直接测试。

覆盖检索链**第一跳**：触发判断 → 规则分解 → LLM 分解（结构化 / 文本兜底）→ 后处理 → 缓存。
LLM 调用一律 monkeypatch，不触网、不依赖假模型。

写这些用例的直接原因：`retriever.py` 在 881 / 1649 两处调用 `decompose`，
但此前**没有任何测试直接针对这个模块** —— 它只有被上层检索用例顺带覆盖到的 29.5%。
"""

from __future__ import annotations

import hashlib

import pytest
from pydantic import ValidationError

from rag import query_decomposer as qd
from rag.query_classifier import QueryCategory
from rag.schemas import DecomposeResult


@pytest.fixture(autouse=True)
def _isolate_cache():
    """`_DECOMPOSE_CACHE` 是模块级的，跨用例存活。

    不清掉的话，后面的用例会命中前面用例写进去的结果，
    「到底走了哪条分支」就完全测不准了 —— 缓存命中会掩盖真实路径。
    """
    qd._DECOMPOSE_CACHE.clear()
    yield
    qd._DECOMPOSE_CACHE.clear()


class TestShouldDecompose:
    def test_short_never_decomposes(self):
        assert qd.should_decompose("短查询", QueryCategory(is_short=True)) is False

    def test_short_wins_over_comparison(self):
        # is_short 的判定排在最前，优先级高于其它一切标志
        cat = QueryCategory(is_short=True, is_comparison=True)
        assert qd.should_decompose("A和B的区别", cat) is False

    def test_comparison_triggers(self):
        assert qd.should_decompose("A", QueryCategory(is_comparison=True)) is True

    def test_long_triggers(self):
        assert qd.should_decompose("A", QueryCategory(is_long=True)) is True

    def test_over_30_chars_triggers(self):
        assert qd.should_decompose("x" * 31, QueryCategory()) is True

    def test_exactly_30_chars_does_not_trigger(self):
        # 边界：条件是 `len(query) > 30`，正好 30 字不触发
        assert qd.should_decompose("x" * 30, QueryCategory()) is False

    def test_plain_query_does_not_trigger(self):
        assert qd.should_decompose("进程调度", QueryCategory()) is False

    def test_pure_concept_never_decomposes_even_when_long(self):
        """纯概念查询的目标是直答，不该为长度或 is_long 标记再调一次 LLM。

        这里故意同时给出三种会触发分解的信号（长度、is_long），证明
        is_concept 的豁免优先级高于它们；但 comparison 例外仍可分解（见下条）。
        """
        cat = QueryCategory(is_concept=True, is_long=True)
        assert qd.should_decompose("x" * 31, cat) is False

    def test_comparison_overrides_concept_exemption(self):
        cat = QueryCategory(is_concept=True, is_comparison=True)
        assert qd.should_decompose("进程和线程的区别", cat) is True


class TestRuleDecompose:
    def test_non_comparison_returns_empty(self):
        assert qd._rule_decompose("进程调度算法", QueryCategory(is_long=True)) == []

    def test_over_80_chars_returns_empty(self):
        long_q = "进程和线程的区别" + "啊" * 80
        assert qd._rule_decompose(long_q, QueryCategory(is_comparison=True)) == []

    def test_comparison_without_literal_marker_returns_empty(self):
        # is_comparison 为真，但字面没有比较词 → 规则不敢拆（拆了也是错的）
        assert qd._rule_decompose("进程 线程", QueryCategory(is_comparison=True)) == []

    def test_splits_on_he(self):
        subs = qd._rule_decompose("进程和线程的区别", QueryCategory(is_comparison=True))
        assert subs == ["进程和线程的区别", "进程的核心概念", "线程的核心概念"]

    def test_splits_on_spaced_vs_and_comma(self):
        subs = qd._rule_decompose("TCP 和 UDP 的区别", QueryCategory(is_comparison=True))
        assert subs == ["TCP 和 UDP 的区别", "TCP的核心概念", "UDP的核心概念"]

    def test_original_query_is_first(self):
        subs = qd._rule_decompose("死锁与饥饿的关系", QueryCategory(is_comparison=True))
        assert subs[0] == "死锁与饥饿的关系"

    def test_more_than_three_parts_returns_empty(self):
        q = "死锁和饥饿和活锁和资源分配的区别"
        assert qd._rule_decompose(q, QueryCategory(is_comparison=True)) == []

    def test_single_part_returns_empty(self):
        # 拆完只剩 1 段（比较词被 _clean_rule_part 剥掉）→ 不拆
        assert qd._rule_decompose("区别", QueryCategory(is_comparison=True)) == []


class TestCleanRulePart:
    def test_strips_leading_request_verbs(self):
        assert qd._clean_rule_part("请解释TCP") == "TCP"

    def test_strips_trailing_comparison_nouns(self):
        assert qd._clean_rule_part("进程的区别") == "进程"

    def test_strips_surrounding_punctuation(self):
        assert qd._clean_rule_part("，进程：") == "进程"

    def test_leaves_plain_term_untouched(self):
        assert qd._clean_rule_part("虚拟内存") == "虚拟内存"


class TestPostprocessSubs:
    def test_empty_becomes_original_only(self):
        assert qd._postprocess_subs("原查询", []) == ["原查询"]

    def test_original_already_present_is_not_duplicated(self):
        assert qd._postprocess_subs("原查询", ["原查询", "子1"]) == ["原查询", "子1"]

    def test_original_is_first_when_missing(self):
        # 原查询是主问题，子查询只是补充；固定其顺序，避免未来又追加到末尾后被截掉。
        assert qd._postprocess_subs("原查询", ["子1", "子2"]) == ["原查询", "子1", "子2"]

    def test_capped_at_original_plus_three_subs(self):
        assert qd._postprocess_subs("原查询", ["a", "b", "c"]) == ["原查询", "a", "b", "c"]

    def test_overflow_keeps_original_and_first_three_subs(self):
        """LLM 即使违规多返回，也必须保住主问题；截掉的是多余子查询。"""
        assert qd._postprocess_subs("原查询", ["a", "b", "c", "d"]) == ["原查询", "a", "b", "c"]

    def test_duplicate_original_is_removed_before_cap(self):
        assert qd._postprocess_subs("原查询", ["子1", "原查询", "子2"]) == ["原查询", "子1", "子2"]


class TestDecomposeResultSchema:
    def test_accepts_at_most_three_supplementary_sub_queries(self):
        result = DecomposeResult(sub_queries=["a", "b", "c"])
        assert result.sub_queries == ["a", "b", "c"]

    def test_rejects_four_sub_queries_before_they_can_displace_original(self):
        """schema 与 `_MAX_SUB_QUERIES` 同步，不能再让上游制造那个溢出形态。"""
        with pytest.raises(ValidationError):
            DecomposeResult(sub_queries=["a", "b", "c", "d"])


class TestParseSubQueries:
    def test_parses_plain_json_list(self):
        assert qd._parse_sub_queries('["a", "b"]') == ["a", "b"]

    def test_parses_markdown_fenced_json(self):
        assert qd._parse_sub_queries('```json\n["a", "b"]\n```') == ["a", "b"]

    def test_non_list_payload_returns_empty(self):
        # 合法 JSON 但不是数组 → 视为解析失败
        assert qd._parse_sub_queries('{"sub_queries": ["a"]}') == []

    def test_unparseable_text_returns_empty(self):
        assert qd._parse_sub_queries("模型今天不太对劲") == []

    def test_strips_blank_entries(self):
        assert qd._parse_sub_queries('["a", "  ", "", "b"]') == ["a", "b"]

    def test_truncates_to_max_sub_queries(self):
        assert qd._parse_sub_queries('["a", "b", "c", "d", "e"]') == ["a", "b", "c"]


class TestCacheHelpers:
    def test_key_is_md5_of_query(self):
        assert qd._cache_key("进程调度") == hashlib.md5("进程调度".encode()).hexdigest()

    def test_key_is_stable_and_query_specific(self):
        assert qd._cache_key("a") == qd._cache_key("a")
        assert qd._cache_key("a") != qd._cache_key("b")

    def test_set_then_get_roundtrips(self):
        qd._set_cached("q", ["子1"])
        assert qd._get_cached("q") == ["子1"]

    def test_get_missing_returns_none(self):
        assert qd._get_cached("从未写入过") is None


class TestEnsureCat:
    def test_passed_category_is_used_as_is(self):
        cat = QueryCategory(is_long=True)
        assert qd._ensure_cat("任意文本", cat) is cat

    def test_classifies_when_category_is_none(self):
        cat = qd._ensure_cat("进程和线程的区别")
        assert isinstance(cat, QueryCategory)
        assert cat.is_comparison is True


class TestDecomposeAsync:
    @pytest.mark.asyncio
    async def test_short_query_short_circuits_without_llm(self, monkeypatch):
        calls = {"structured": 0, "text": 0}

        async def fake_structured(*_a, **_kw):
            calls["structured"] += 1
            return None

        async def fake_text(*_a, **_kw):
            calls["text"] += 1
            return "[]"

        monkeypatch.setattr(qd, "call_structured", fake_structured)
        monkeypatch.setattr(qd, "call_text", fake_text)

        out = await qd.decompose("短查询", cat=QueryCategory(is_short=True))

        assert out == ["短查询"]
        assert calls == {"structured": 0, "text": 0}

    @pytest.mark.asyncio
    async def test_short_circuit_result_is_not_cached(self):
        # 提前 return 的分支绕过了缓存写入 —— 固定这个行为，避免有人误以为它缓存了
        await qd.decompose("短查询", cat=QueryCategory(is_short=True))
        assert qd._get_cached("短查询") is None

    @pytest.mark.asyncio
    async def test_pure_concept_short_circuits_without_llm(self, monkeypatch):
        """概念豁免的收益是省掉一次 LLM 调用；只测返回值无法证明这一点。"""

        async def boom(*_a, **_kw):
            raise AssertionError("纯概念查询不该调用分解 LLM")

        monkeypatch.setattr(qd, "call_structured", boom)
        monkeypatch.setattr(qd, "call_text", boom)

        query = "虚拟内存的工作原理是什么，它如何通过页表和缺页中断实现地址转换"
        out = await qd.decompose(query, cat=QueryCategory(is_concept=True, is_long=True))

        assert out == [query]

    @pytest.mark.asyncio
    async def test_rule_path_avoids_llm_and_caches(self, monkeypatch):
        calls = {"n": 0}

        async def boom(*_a, **_kw):
            calls["n"] += 1
            raise AssertionError("规则路径不该调用 LLM")

        monkeypatch.setattr(qd, "call_structured", boom)
        monkeypatch.setattr(qd, "call_text", boom)

        out = await qd.decompose("进程和线程的区别", cat=QueryCategory(is_comparison=True))

        assert out == ["进程和线程的区别", "进程的核心概念", "线程的核心概念"]
        assert calls["n"] == 0
        assert qd._get_cached("进程和线程的区别") == out

    @pytest.mark.asyncio
    async def test_structured_path_returns_subs_plus_original(self, monkeypatch):
        captured: dict = {}

        async def fake_structured(prompt, schema, **kwargs):
            captured["schema"] = schema
            captured["kwargs"] = kwargs
            captured["prompt"] = prompt
            return DecomposeResult(sub_queries=["子1", "子2"])

        async def boom(*_a, **_kw):
            raise AssertionError("结构化输出成功时不该走文本兜底")

        monkeypatch.setattr(qd, "call_structured", fake_structured)
        monkeypatch.setattr(qd, "call_text", boom)

        out = await qd.decompose("x" * 40, cat=QueryCategory(is_long=True))

        assert out == ["x" * 40, "子1", "子2"]
        assert captured["schema"] is DecomposeResult
        assert captured["kwargs"]["stage"] == "decompose"
        assert captured["kwargs"]["timeout"] > 0
        assert captured["prompt"]

    @pytest.mark.asyncio
    async def test_text_fallback_when_structured_returns_none(self, monkeypatch):
        seen: dict = {}

        async def fake_structured(*_a, **_kw):
            return None

        async def fake_text(_prompt, **kwargs):
            seen["stage"] = kwargs["stage"]
            return '```json\n["子A", "子B"]\n```'

        monkeypatch.setattr(qd, "call_structured", fake_structured)
        monkeypatch.setattr(qd, "call_text", fake_text)

        out = await qd.decompose("y" * 40, cat=QueryCategory(is_long=True))

        assert out == ["y" * 40, "子A", "子B"]
        assert seen["stage"] == "decompose_fallback"

    @pytest.mark.asyncio
    async def test_both_paths_failing_degrades_to_no_decompose(self, monkeypatch):
        async def fake_structured(*_a, **_kw):
            return None

        async def fake_text(*_a, **_kw):
            return "模型抽风了，返回了一段完全不是 JSON 的文本"

        monkeypatch.setattr(qd, "call_structured", fake_structured)
        monkeypatch.setattr(qd, "call_text", fake_text)

        out = await qd.decompose("z" * 40, cat=QueryCategory(is_long=True))

        # 降级为「不分解」而不是抛异常 —— 检索链不能因为分解失败而断掉
        assert out == ["z" * 40]

    @pytest.mark.asyncio
    async def test_cache_hit_skips_llm(self, monkeypatch):
        calls = {"n": 0}

        async def fake_structured(*_a, **_kw):
            calls["n"] += 1
            return DecomposeResult(sub_queries=["子1"])

        monkeypatch.setattr(qd, "call_structured", fake_structured)

        first = await qd.decompose("q" * 40, cat=QueryCategory(is_long=True))
        second = await qd.decompose("q" * 40, cat=QueryCategory(is_long=True))

        assert first == second == ["q" * 40, "子1"]
        assert calls["n"] == 1

    @pytest.mark.asyncio
    async def test_cache_is_checked_before_trigger_judgement(self):
        """缓存查找在 `should_decompose` **之前** —— 命中就直接返回。

        这条固定的是「缓存优先级最高」这个顺序，不是分类逻辑。
        """
        qd._set_cached("短查询", ["预置子查询"])
        out = await qd.decompose("短查询", cat=QueryCategory(is_short=True))
        assert out == ["预置子查询"]

    @pytest.mark.asyncio
    async def test_infers_category_without_llm(self, monkeypatch):
        """不传 cat 时走 `_ensure_cat` → 规则分类，**不触发任何 LLM 调用**。

        不断言具体的分解结果：那取决于分类结果，而分类是另一个模块的契约。
        这里只锁「不调 LLM」这个关键性质。
        """

        async def boom(*_a, **_kw):
            raise AssertionError("_ensure_cat 不该触发 LLM")

        monkeypatch.setattr(qd, "call_structured", boom)
        monkeypatch.setattr(qd, "call_text", boom)

        out = await qd.decompose("进程和线程的区别")

        assert isinstance(out, list)
        assert out[0] == "进程和线程的区别"

    @pytest.mark.asyncio
    async def test_result_is_always_non_empty_list_of_str(self, monkeypatch):
        async def fake_structured(*_a, **_kw):
            return None

        async def fake_text(*_a, **_kw):
            return "[]"

        monkeypatch.setattr(qd, "call_structured", fake_structured)
        monkeypatch.setattr(qd, "call_text", fake_text)

        for query, cat in [
            ("短", QueryCategory(is_short=True)),
            ("普通查询", QueryCategory()),
            ("进程和线程的区别", QueryCategory(is_comparison=True)),
            ("w" * 40, QueryCategory(is_long=True)),
        ]:
            out = await qd.decompose(query, cat=cat)
            assert isinstance(out, list)
            assert out, f"{query!r} 分解出了空列表 —— 检索链会拿不到任何查询"
            assert all(isinstance(s, str) for s in out)
            assert query in out, f"{query!r} 的原查询不在结果里"
