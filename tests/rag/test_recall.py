"""`rag/recall.py` 直接测试。

这个模块此前**没有任何专门测试**（覆盖率 21.4%，是运行时检索链里最低的），
只有被上层检索用例顺带覆盖到。本文件先覆盖「纯函数 + 学科收窄」这一层。

**为什么优先测学科收窄**（`_infer_subject_collections` / `resolve_collection_routes`）：
它决定「这次检索去哪些集合里找」。一旦它退化，检索范围会从"某个学科"变成
"全 4 科"，错学科的文档就有机会挤进首条 —— 而且**不会报错**。
门禁上表现为 `hit@1` 掉，但看不出原因在关键词表里。
"""

from __future__ import annotations

from rag.query_classifier import QueryCategory
from rag.recall import (
    ALL_ROUTES,
    SUBJECT_COLLECTIONS,
    _contains_collection_keyword,
    _infer_subject_collections,
    _rank_terms_by_specificity,
    combine_filters,
    get_route_weight,
    resolve_collection_routes,
)


class TestContainsCollectionKeyword:
    def test_chinese_keyword_is_substring_match(self):
        assert _contains_collection_keyword("操作系统的进程调度", "进程") is True

    def test_alnum_keyword_needs_word_boundary(self):
        """纯字母数字关键词要按词边界匹配，避免 `io` 命中 `ratio` 这类误伤。"""
        assert _contains_collection_keyword("tcp 三次握手", "tcp") is True
        assert _contains_collection_keyword("ratio 分析", "io") is False

    def test_alnum_keyword_matches_with_punctuation_boundary(self):
        assert _contains_collection_keyword("使用 tcp/ip 协议", "tcp") is True

    def test_empty_keyword_is_false(self):
        assert _contains_collection_keyword("任意文本", "") is False

    def test_missing_keyword_is_false(self):
        assert _contains_collection_keyword("进程调度", "死锁") is False


class TestInferSubjectCollections:
    def test_obvious_keyword_maps_to_one_subject(self):
        assert _infer_subject_collections("进程调度的基本概念") == ["operating_system"]

    def test_returns_empty_when_no_keyword_matches(self):
        assert _infer_subject_collections("完全无关的一句话") == []

    # ── 回归：空格盲区（2026-09-22）──────────────────────
    #
    # 关键词表里写的是 `ip地址` / `mac地址`（无空格），而查询常写成
    # `IP 地址` / `MAC 地址`（有空格）。修复前这类写法**一个关键词都匹配不上**，
    # 于是 `resolve_collection_routes` 退化成「全 4 科检索」——
    # 实测后果：`IP 地址与 MAC 地址有什么区别？` 的首条证据来自 operating_system，
    # 而知识库里 MAC 地址**只存在于 computer_network**。

    def test_space_in_alnum_keyword_does_not_break_matching(self):
        matched = _infer_subject_collections("IP 地址与 MAC 地址有什么区别？")
        assert "computer_network" in matched, "带空格的 `IP 地址` / `MAC 地址` 必须能匹配到计网"

    def test_space_free_writing_still_matches(self):
        assert "computer_network" in _infer_subject_collections("ip地址是什么")

    # ── 回归：关键词表缺词（2026-09-22）──────────────────

    def test_instruction_cycle_maps_to_computer_organization(self):
        """`指令周期` 是计组概念；修复前关键词表只有 `指令系统`，于是退化成全 4 科。"""
        assert _infer_subject_collections("指令周期包括哪些阶段？") == ["computer_organization"]

    def test_segmented_paging_covers_both_subjects(self):
        """段页式在知识库里两科都有（CO 讲虚拟存储器、OS 讲存储管理），两边都该收录。"""
        matched = _infer_subject_collections("什么是段页式存储管理？")
        assert set(matched) == {"computer_organization", "operating_system"}


class TestResolveCollectionRoutes:
    def test_explicit_collection_wins(self):
        assert resolve_collection_routes("任意查询", "operating_system") == ["operating_system"]

    def test_empty_collection_uses_inference(self):
        assert resolve_collection_routes("进程调度的基本概念", "") == ["operating_system"]

    def test_falls_back_to_all_subjects_when_nothing_matches(self):
        assert resolve_collection_routes("完全无关的一句话", "") == SUBJECT_COLLECTIONS

    def test_exercise_appends_questions(self):
        cat = QueryCategory(is_exercise=True)
        routes = resolve_collection_routes("进程调度", "", cat=cat)
        assert "questions" in routes

    def test_answer_appends_answers(self):
        cat = QueryCategory(is_answer=True)
        routes = resolve_collection_routes("进程调度", "", cat=cat)
        assert "answers" in routes

    def test_learning_path_marker_appends_learning_paths(self):
        cat = QueryCategory(is_structured=True)
        routes = resolve_collection_routes("操作系统应该怎么学", "", cat=cat)
        assert "learning_paths" in routes

    def test_structured_without_path_marker_does_not_append_learning_paths(self):
        cat = QueryCategory(is_structured=True)
        routes = resolve_collection_routes("进程调度的步骤", "", cat=cat)
        assert "learning_paths" not in routes

    def test_result_is_deduplicated(self):
        cat = QueryCategory(is_answer=True, is_code=True)
        routes = resolve_collection_routes("进程调度", "", cat=cat)
        assert len(routes) == len(set(routes)), "answers 可能被追加两次，必须去重"

    def test_all_returned_names_are_real_collections(self):
        known = set(SUBJECT_COLLECTIONS) | {"questions", "answers", "learning_paths"}
        routes = resolve_collection_routes("进程调度 习题 答案", "")
        assert set(routes) <= known


class TestCombineFilters:
    def test_both_none(self):
        assert combine_filters(None, None) is None

    def test_only_base(self):
        assert combine_filters({"a": 1}, None) == {"a": 1}

    def test_only_extra(self):
        assert combine_filters(None, {"b": 2}) == {"b": 2}

    def test_both_are_anded(self):
        assert combine_filters({"a": 1}, {"b": 2}) == {"$and": [{"a": 1}, {"b": 2}]}


class TestRankTermsBySpecificity:
    def test_two_or_fewer_terms_are_returned_as_is(self):
        """≤2 个词时**直接原样返回、不排序** —— 这是有意的提前返回。

        focus 路由只取前 3 个词，2 个词时排序对结果没有影响，省一次计算。
        （写测试时我在这里栽过一次：传了 2 个词，误以为排序没生效。）
        """
        assert _rank_terms_by_specificity(["算法", "死锁"]) == ["算法", "死锁"]

    def test_term_matching_no_collection_sinks_to_the_end(self):
        """需要 ≥3 个词才会真正进入排序分支。"""
        ranked = _rank_terms_by_specificity(["死锁", "完全自造的词", "进程"])
        assert ranked[-1] == "完全自造的词", "不匹配任何学科的词最没区分度，应排最后"

    def test_specific_term_ranks_before_generic_one(self):
        ranked = _rank_terms_by_specificity(["完全自造的词", "死锁", "进程"])
        assert ranked.index("死锁") < ranked.index("完全自造的词")

    def test_no_term_is_lost_or_duplicated(self):
        terms = ["死锁", "完全自造的词", "进程", "调度"]
        assert sorted(_rank_terms_by_specificity(terms)) == sorted(terms)

    def test_empty_input(self):
        assert _rank_terms_by_specificity([]) == []


class TestAllRoutesSingleSource:
    def test_defined_exactly_once_in_source(self):
        """**回归测试**：`ALL_ROUTES` 曾被整块重复定义两次（第一份被第二份遮蔽）。

        重复定义不会报错、值也相同，所以功能上看不出来 —— 但它意味着
        有人改了一处、另一处没改，或者一次脚本插入重复执行过。
        按项目既有约定（提交前做唯一性 grep），这里用测试钉住。
        """
        import pathlib

        src = pathlib.Path(__file__).resolve().parents[2] / "src" / "rag" / "recall.py"
        text = src.read_text(encoding="utf-8")
        assert text.count("\nALL_ROUTES: tuple[str, ...] =") == 1

    def test_derives_from_weight_table(self):
        from rag.recall import _ROUTE_WEIGHTS

        assert set(ALL_ROUTES) == {route for route, _cat in _ROUTE_WEIGHTS}

    def test_has_no_duplicates(self):
        assert len(ALL_ROUTES) == len(set(ALL_ROUTES))

    def test_is_non_trivial(self):
        assert len(ALL_ROUTES) >= 10, f"只推导出 {len(ALL_ROUTES)} 条路由，权重表可能被改坏了"


class TestGetRouteWeight:
    def test_collection_prefix_is_stripped(self):
        assert get_route_weight("os:semantic") == get_route_weight("semantic")

    def test_unknown_route_gets_default_one(self):
        assert get_route_weight("完全不存在的路由") == 1.0

    def test_category_specific_weight_takes_precedence(self):
        """同一路由在不同查询类别下可以有权重差异，类别命中时优先。"""
        from rag.recall import _ROUTE_WEIGHTS

        has_specific = any(cat != "default" for _route, cat in _ROUTE_WEIGHTS)
        assert has_specific, "权重表里没有任何类别专属权重，本测试失去意义"
