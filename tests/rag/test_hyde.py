"""`rag/hyde.py` 直接测试。

HyDE 的触发判断决定「**要不要多花一次 LLM 调用**」，两个方向都有代价：

- 该触发却没触发 → 召回不足（长尾概念题答不上来）
- 不该触发却触发 → 白花钱，还把一段可能跑偏的假想文本塞进检索

所以本文件把 `should_trigger_hyde` 的**真值表**逐条钉住，而不是只求"跑通"。
"""

from __future__ import annotations

import pytest

from rag import hyde as H
from rag.query_classifier import QueryCategory


@pytest.fixture(autouse=True)
def _clear_hyde_cache():
    """`_hyde_cache` 是模块级、**无 TTL** 的有界缓存 —— 跨用例必须清，
    否则"缓存命中"会掩盖后续用例真正要走的分支。"""
    H._hyde_cache.clear()
    yield
    H._hyde_cache.clear()


class TestCacheKey:
    def test_is_deterministic(self):
        assert H._cache_key("进程调度") == H._cache_key("进程调度")

    def test_ignores_surrounding_whitespace(self):
        assert H._cache_key("  进程调度  ") == H._cache_key("进程调度")

    def test_is_16_hex_chars(self):
        key = H._cache_key("任意查询")
        assert len(key) == 16
        assert all(c in "0123456789abcdef" for c in key)

    def test_differs_per_query(self):
        assert H._cache_key("进程调度") != H._cache_key("死锁")


class TestShouldTriggerHyde:
    """触发条件的真值表。默认配置：`HYDE_MIN_DOCS=2`、分数阈值 0.25。"""

    def test_disabled_never_triggers(self, monkeypatch):
        monkeypatch.setattr(H.settings, "HYDE_ENABLED", False)
        assert H.should_trigger_hyde("进程调度", 0, 0.0, QueryCategory()) is False

    @pytest.mark.parametrize("flag", ["is_answer", "is_exercise", "is_code"])
    def test_excluded_categories_never_trigger(self, flag):
        """答案 / 习题 / 代码查询不走 HyDE —— 它们的召回依赖精确措辞，
        假想文本只会把检索带偏。"""
        cat = QueryCategory(**{flag: True})
        assert H.should_trigger_hyde("进程调度", 0, 0.0, cat) is False

    def test_blank_query_never_triggers(self):
        assert H.should_trigger_hyde("   ", 0, 0.0, QueryCategory()) is False

    def test_few_docs_triggers(self):
        assert H.should_trigger_hyde("进程调度", 0, 0.9, QueryCategory()) is True
        assert H.should_trigger_hyde("进程调度", 1, 0.9, QueryCategory()) is True

    def test_enough_docs_does_not_trigger(self):
        """召回已经够了就不该再花钱 —— 即使首条重排分很低。"""
        assert H.should_trigger_hyde("进程调度", 2, 0.1, QueryCategory()) is False
        assert H.should_trigger_hyde("进程调度", 5, 0.0, QueryCategory()) is False

    def test_boundary_follows_min_docs_setting(self, monkeypatch):
        monkeypatch.setattr(H.settings, "HYDE_MIN_DOCS", 3)
        assert H.should_trigger_hyde("查询", 2, 0.9, QueryCategory()) is True
        assert H.should_trigger_hyde("查询", 3, 0.9, QueryCategory()) is False


class TestConditionRedundancy:
    """★ 实测发现：默认 `HYDE_MIN_DOCS=2` 下，`low_score` 与 `short_concept`
    **永远不可能改变结果** —— 两者都要求 `docs_count == 0`，而 0 已经满足
    `low_docs = docs_count < 2`。

    这不是缺陷（属防御性冗余），但结论很实际：**要调 HyDE 的灵敏度，
    真正该动的是 `HYDE_MIN_DOCS`**；改 `HYDE_RERANK_SCORE_THRESHOLD`、
    或改 short_concept 那条规则，在当前配置下**没有任何效果**。

    下面同时验证「设成 0 之后它们确实生效」—— 否则这段冗余就是纯粹的误导。
    """

    def test_high_score_still_triggers_when_docs_are_zero(self):
        # 分数很高（0.99 > 0.25），但 low_docs 已经为真 → 触发
        assert H.should_trigger_hyde("查询", 0, 0.99, QueryCategory()) is True

    def test_low_score_becomes_live_when_min_docs_is_zero(self, monkeypatch):
        monkeypatch.setattr(H.settings, "HYDE_MIN_DOCS", 0)
        cat = QueryCategory()
        assert H.should_trigger_hyde("普通查询", 0, 0.10, cat) is True
        assert H.should_trigger_hyde("普通查询", 0, 0.90, cat) is False

    def test_short_concept_becomes_live_when_min_docs_is_zero(self, monkeypatch):
        monkeypatch.setattr(H.settings, "HYDE_MIN_DOCS", 0)
        cat = QueryCategory(is_concept=True, is_short=True)
        assert H.should_trigger_hyde("概念", 0, 0.90, cat) is True
        # 有文档时这条不看 —— 它不是"短概念查询一律触发"
        assert H.should_trigger_hyde("概念", 1, 0.90, cat) is False


class TestBuildHydeText:
    def test_truncates_to_max_chars(self, monkeypatch):
        monkeypatch.setattr(H.settings, "HYDE_MAX_CHARS", 10)
        monkeypatch.setattr(H, "call_text_sync", lambda *_a, **_kw: "x" * 50)
        assert H._build_hyde_text("查询") == "x" * 10

    def test_none_from_llm_becomes_empty_string(self, monkeypatch):
        """LLM 失败返回空串 —— 由调用方跳过 HyDE 分支，而不是抛异常把检索搞崩。"""
        monkeypatch.setattr(H, "call_text_sync", lambda *_a, **_kw: None)
        assert H._build_hyde_text("查询") == ""

    def test_passes_stage_and_temperature(self, monkeypatch):
        seen: dict = {}

        def fake(prompt, *, temperature, stage):
            seen["temperature"] = temperature
            seen["stage"] = stage
            seen["prompt"] = prompt
            return "假想文本"

        monkeypatch.setattr(H, "call_text_sync", fake)
        assert H._build_hyde_text("查询") == "假想文本"
        assert seen["stage"] == "hyde", "指标按 stage 归集，写错就查不到 HyDE 的开销"
        assert seen["temperature"] == H.settings.TEMP_DEFAULT
        assert seen["prompt"], "提示词不该为空"


class TestGenerateHydeQuery:
    def test_blank_returns_empty_without_calling_llm(self, monkeypatch):
        def boom(*_a, **_kw):
            raise AssertionError("空查询不该调用 LLM")

        monkeypatch.setattr(H, "call_text_sync", boom)
        assert H.generate_hyde_query("   ") == ""

    def test_whitespace_variants_share_one_cache_entry(self, monkeypatch):
        calls: list[int] = []
        monkeypatch.setattr(H, "call_text_sync", lambda *_a, **_kw: calls.append(1) or "假想")

        assert H.generate_hyde_query("  进程调度  ") == "假想"
        assert H.generate_hyde_query("进程调度") == "假想"

        assert len(calls) == 1, "首尾空白不该产生两个缓存条目"

    def test_second_identical_call_hits_cache(self, monkeypatch):
        calls: list[int] = []
        monkeypatch.setattr(H, "call_text_sync", lambda *_a, **_kw: calls.append(1) or "假想")

        H.generate_hyde_query("进程调度")
        H.generate_hyde_query("进程调度")

        assert len(calls) == 1
