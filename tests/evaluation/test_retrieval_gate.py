"""检索质量黄金集门禁的测试。

分两层：
1. **纯函数层**（默认运行，毫秒级）：指标聚合与基线对比逻辑。这层必须能抓住"算错了"，
   而不是只跑通 —— 所以每条断言都配了会失败的边界输入。
2. **端到端层**（需显式开启 `RUN_RETRIEVAL_GATE=1`）：真的建索引、真的跑 40 条查询。
   耗时约 35s，且需要一个可写的临时目录，故默认跳过；CI 里由独立 job 跑 CLI。

另外有一组**元测试**（``TestGoldenSetIntegrity`` / ``TestBaselineFile``），
用于堵住"门禁假绿"：路径写错导致 0 条查询、基线陈旧导致对比失效等。
没有这组测试，门禁可能永远报"通过"而无人察觉。
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

import pytest

from evaluation.retrieval_gate import (
    DEFAULT_BASELINE_PATH,
    DEFAULT_GOLDEN_PATH,
    SUBJECT_TO_CATEGORY,
    QueryOutcome,
    compare_to_baseline,
    compute_metrics,
    load_golden_queries,
)

GOLDEN_PATH = Path(DEFAULT_GOLDEN_PATH)
BASELINE_PATH = Path(DEFAULT_BASELINE_PATH)

_skip_gate = pytest.mark.skipif(
    os.environ.get("RUN_RETRIEVAL_GATE") != "1",
    reason="端到端门禁需显式开启：设置 RUN_RETRIEVAL_GATE=1（耗时约 35s）",
)


def _outcome(expected: str, hits: list[str], query: str = "q") -> QueryOutcome:
    return QueryOutcome(query=query, expected_category=expected, hit_categories=hits)


# ══════════════════════════════════════════════════════
# 1. 纯函数：指标聚合
# ══════════════════════════════════════════════════════


class TestComputeMetrics:
    def test_empty_input_is_all_zero(self):
        m = compute_metrics([])
        assert m.n_queries == 0
        assert m.category_hit_at_1 == 0.0
        assert m.category_hit_at_k == 0.0
        assert m.category_mrr == 0.0
        assert m.category_precision == 0.0
        assert m.empty_result_rate == 0.0
        assert m.mean_evidence_count == 0.0

    def test_perfect_run(self):
        m = compute_metrics([_outcome("os", ["os", "os"]), _outcome("ds", ["ds"])])
        assert m.category_hit_at_1 == 1.0
        assert m.category_hit_at_k == 1.0
        assert m.category_mrr == 1.0
        assert m.category_precision == 1.0
        assert m.empty_result_rate == 0.0

    def test_correct_at_rank_two_loses_hit_at_1_but_keeps_mrr_half(self):
        m = compute_metrics([_outcome("os", ["ds", "os"])])
        assert m.category_hit_at_1 == 0.0
        assert m.category_hit_at_k == 1.0
        assert m.category_mrr == 0.5

    def test_correct_at_rank_three(self):
        m = compute_metrics([_outcome("os", ["ds", "co", "os"])])
        assert m.category_hit_at_k == 1.0
        assert m.category_mrr == pytest.approx(1 / 3)

    def test_no_correct_hit_scores_zero(self):
        m = compute_metrics([_outcome("os", ["ds", "co"])])
        assert m.category_hit_at_1 == 0.0
        assert m.category_hit_at_k == 0.0
        assert m.category_mrr == 0.0
        assert m.category_precision == 0.0

    def test_empty_hits_count_as_empty_result_and_do_not_divide_by_zero(self):
        m = compute_metrics([_outcome("os", []), _outcome("ds", ["ds"])])
        assert m.empty_result_rate == 0.5
        # 分母为 0 时精确率必须是 0，不能是 1.0（否则"返回空"会被算成完美）
        assert m.category_precision == 1.0  # 唯一一条命中是对的
        assert m.mean_evidence_count == 0.5

    def test_all_empty_gives_zero_precision_not_perfect(self):
        """这是最关键的一条：全部返回空时，精确率必须是 0 而不是 1。"""
        m = compute_metrics([_outcome("os", []), _outcome("ds", [])])
        assert m.empty_result_rate == 1.0
        assert m.category_precision == 0.0
        assert m.mean_evidence_count == 0.0

    def test_precision_counts_off_category_hits_against(self):
        # 1 条对 + 3 条错 → 0.25
        m = compute_metrics([_outcome("os", ["os", "ds", "co", "network"])])
        assert m.category_precision == 0.25

    def test_mean_evidence_count(self):
        m = compute_metrics([_outcome("os", ["os"] * 2), _outcome("os", ["os"] * 4)])
        assert m.mean_evidence_count == 3.0

    def test_mixed_run_aggregates_correctly(self):
        outcomes = [
            _outcome("os", ["os", "os"]),  # hit@1, rr=1
            _outcome("ds", ["co", "ds"]),  # hit@k, rr=0.5
            _outcome("network", ["os"]),  # miss
            _outcome("co", []),  # empty
        ]
        m = compute_metrics(outcomes)
        assert m.n_queries == 4
        assert m.category_hit_at_1 == 0.25
        assert m.category_hit_at_k == 0.5
        assert m.category_mrr == pytest.approx((1.0 + 0.5) / 4)
        assert m.empty_result_rate == 0.25
        assert m.mean_evidence_count == pytest.approx(5 / 4)

    def test_as_dict_rounds_and_keeps_all_metric_keys(self):
        d = compute_metrics([_outcome("os", ["os"])]).as_dict()
        assert set(d) == {
            "n_queries",
            "category_hit_at_1",
            "category_hit_at_k",
            "category_mrr",
            "category_precision",
            "empty_result_rate",
            "mean_evidence_count",
        }
        assert d["n_queries"] == 1

    def test_first_correct_rank_helper(self):
        assert _outcome("os", ["ds", "co", "os"]).first_correct_rank == 3
        assert _outcome("os", ["ds"]).first_correct_rank is None
        assert _outcome("os", []).first_correct_rank is None


# ══════════════════════════════════════════════════════
# 2. 纯函数：基线对比
# ══════════════════════════════════════════════════════


def _baseline(**overrides) -> dict:
    base = {
        "n_queries": 40,
        "category_hit_at_1": 0.90,
        "category_hit_at_k": 1.00,
        "category_mrr": 0.9458,
        "category_precision": 0.9014,
        "empty_result_rate": 0.0,
        "mean_evidence_count": 5.325,
    }
    base.update(overrides)
    return base


class TestCompareToBaseline:
    def test_identical_passes(self):
        assert compare_to_baseline(_baseline(), _baseline()) == []

    def test_improvement_passes(self):
        assert compare_to_baseline(_baseline(category_hit_at_1=0.95), _baseline()) == []

    def test_single_query_regression_is_caught(self):
        # 1/40 = 0.025 > 容差 0.02 → 单条退化必须失败
        regressions = compare_to_baseline(_baseline(category_hit_at_1=0.875), _baseline())
        assert len(regressions) == 1
        assert "category_hit_at_1" in regressions[0]

    def test_drop_within_tolerance_passes(self):
        assert compare_to_baseline(_baseline(category_hit_at_1=0.89), _baseline()) == []

    def test_hit_at_k_ceiling_regression_is_caught(self):
        regressions = compare_to_baseline(_baseline(category_hit_at_k=0.975), _baseline())
        assert any("category_hit_at_k" in r for r in regressions)

    def test_empty_result_rate_increase_is_caught(self):
        regressions = compare_to_baseline(_baseline(empty_result_rate=0.025), _baseline())
        assert any("empty_result_rate" in r for r in regressions)

    def test_empty_result_rate_decrease_passes(self):
        assert compare_to_baseline(_baseline(empty_result_rate=0.0), _baseline()) == []

    def test_mean_evidence_count_drop_is_caught(self):
        regressions = compare_to_baseline(_baseline(mean_evidence_count=4.0), _baseline())
        assert any("mean_evidence_count" in r for r in regressions)

    def test_multiple_regressions_all_reported(self):
        regressions = compare_to_baseline(
            _baseline(category_hit_at_1=0.5, category_mrr=0.5, empty_result_rate=0.2),
            _baseline(),
        )
        assert len(regressions) == 3

    def test_query_count_mismatch_reports_stale_baseline(self):
        regressions = compare_to_baseline(_baseline(n_queries=12), _baseline())
        assert len(regressions) == 1
        assert "查询条数不一致" in regressions[0]

    def test_query_count_mismatch_short_circuits_other_checks(self):
        # 条数不一致时不应再报一堆指标退化，否则掩盖真正原因
        regressions = compare_to_baseline(
            _baseline(n_queries=12, category_hit_at_1=0.0), _baseline()
        )
        assert len(regressions) == 1

    def test_missing_metric_key_treated_as_zero(self):
        current = _baseline()
        del current["category_mrr"]
        regressions = compare_to_baseline(current, _baseline())
        assert any("category_mrr" in r for r in regressions)


# ══════════════════════════════════════════════════════
# 3. 黄金集加载
# ══════════════════════════════════════════════════════


class TestLoadGoldenQueries:
    def _write(self, tmp_path, lines: list[str]) -> Path:
        p = tmp_path / "golden.jsonl"
        p.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return p

    def test_maps_subject_to_category(self, tmp_path):
        p = self._write(
            tmp_path,
            [
                json.dumps({"query": "什么是进程？", "metadata": {"subject": "os"}}),
                json.dumps({"query": "什么是树？", "metadata": {"subject": "ds"}}),
            ],
        )
        assert load_golden_queries(p) == [
            ("什么是进程？", "operating_system"),
            ("什么是树？", "data_structure"),
        ]

    def test_skips_comment_and_blank_lines(self, tmp_path):
        p = self._write(
            tmp_path,
            [
                "# 这是注释",
                "",
                json.dumps({"query": "q1", "metadata": {"subject": "os"}}),
                "   ",
            ],
        )
        assert len(load_golden_queries(p)) == 1

    def test_skips_unknown_subject(self, tmp_path):
        p = self._write(
            tmp_path,
            [
                json.dumps({"query": "q1", "metadata": {"subject": "os"}}),
                json.dumps({"query": "q2", "metadata": {"subject": "unknown"}}),
                json.dumps({"query": "q3", "metadata": {}}),
            ],
        )
        assert len(load_golden_queries(p)) == 1

    def test_skips_blank_query(self, tmp_path):
        p = self._write(tmp_path, [json.dumps({"query": "   ", "metadata": {"subject": "os"}})])
        assert load_golden_queries(p) == []

    def test_skips_broken_json_line(self, tmp_path):
        p = self._write(
            tmp_path,
            ["{不是合法 json", json.dumps({"query": "q", "metadata": {"subject": "os"}})],
        )
        assert len(load_golden_queries(p)) == 1

    def test_limit(self, tmp_path):
        p = self._write(
            tmp_path,
            [json.dumps({"query": f"q{i}", "metadata": {"subject": "os"}}) for i in range(10)],
        )
        assert len(load_golden_queries(p, limit=3)) == 3

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_golden_queries(tmp_path / "nope.jsonl")


# ══════════════════════════════════════════════════════
# 4. 元测试：堵住"门禁假绿"
# ══════════════════════════════════════════════════════


class TestGoldenSetIntegrity:
    """没有这组断言，路径写错会让门禁"0 条查询 → 全部通过"。"""

    def test_golden_file_exists(self):
        assert GOLDEN_PATH.exists(), f"黄金集缺失: {GOLDEN_PATH}"

    def test_has_enough_queries(self):
        queries = load_golden_queries(GOLDEN_PATH)
        assert len(queries) >= 30, f"仅加载到 {len(queries)} 条，黄金集可能被截断"

    def test_covers_all_four_subjects(self):
        categories = {cat for _, cat in load_golden_queries(GOLDEN_PATH)}
        assert categories == set(SUBJECT_TO_CATEGORY.values())

    def test_every_query_is_non_empty_and_unique(self):
        queries = load_golden_queries(GOLDEN_PATH)
        texts = [q for q, _ in queries]
        assert all(t.strip() for t in texts)
        assert len(set(texts)) == len(texts), "黄金集存在重复 query"

    def test_subject_mapping_targets_real_collections(self):
        # 映射目标必须是 ingest 的默认分类目录名，否则门禁会永远查不中
        from rag.ingest import DEFAULT_CATEGORIES

        assert set(SUBJECT_TO_CATEGORY.values()) <= set(DEFAULT_CATEGORIES)


class TestBaselineFile:
    """基线文件必须与黄金集、与环境配置保持一致，否则对比没有意义。"""

    def test_baseline_exists(self):
        assert BASELINE_PATH.exists(), f"基线缺失: {BASELINE_PATH}"

    def test_metric_keys_match_golden_count(self):
        baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
        n_golden = len(load_golden_queries(GOLDEN_PATH))
        assert baseline["metrics"]["n_queries"] == n_golden, (
            "基线条数与黄金集不一致 —— 黄金集改动后必须用 --update-baseline 重录"
        )

    def test_meta_records_environment(self):
        meta = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))["_meta"]
        for key in ("embedding", "rerank_enabled", "k", "golden_path"):
            assert key in meta, f"基线 _meta 缺少 {key}，无法判断数字的适用环境"

    def test_baseline_is_not_vacuous(self):
        metrics = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))["metrics"]
        assert metrics["category_hit_at_k"] > 0.5, "基线本身太差，门禁失去意义"
        assert metrics["mean_evidence_count"] > 0, "基线平均证据数为 0，门禁形同虚设"

    def test_baseline_passes_against_itself(self):
        metrics = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))["metrics"]
        assert compare_to_baseline(metrics, metrics) == []


# ══════════════════════════════════════════════════════
# 5. 端到端（默认跳过）
# ══════════════════════════════════════════════════════


@_skip_gate
class TestGateEndToEnd:
    def test_gate_does_not_regress_against_baseline(self):
        import asyncio
        import shutil
        import tempfile

        from evaluation.retrieval_gate import (
            build_index,
            configure_for_gate,
            run_gate,
            wait_for_index_ready,
        )

        tmp_dir = tempfile.mkdtemp(prefix="gate_test_")
        try:
            configure_for_gate(tmp_dir)
            counts = build_index()
            assert sum(counts.values()) > 0, "索引为空 —— knowledge/ 缺失或解析全失败"
            wait_for_index_ready(sorted(counts))

            metrics, _outcomes, errors = asyncio.run(run_gate())
            assert errors == [], f"有 query 抛异常：{errors}"
            baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))["metrics"]
            regressions = compare_to_baseline(metrics.as_dict(), baseline)
            assert regressions == [], f"检索质量退化：{regressions}"
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)


class TestRunGateErrorHandling:
    """单条 query 抛异常不能中断整轮 —— 否则门禁只给 traceback，拿不到任何指标。

    这条路径是真实存在的：CI 无 LLM 凭据时 40 条里有 6 条抛
    `openai.OpenAIError: Missing credentials`（见 core.llm.get_llm 的说明）。
    """

    def _patch_retriever(self, monkeypatch, behaviour):
        from rag import retriever

        async def fake(query, **kwargs):
            return behaviour(query)

        monkeypatch.setattr(retriever, "aretrieve_evidence_with_retry", fake)

    def test_exception_is_recorded_and_loop_continues(self, monkeypatch, tmp_path):
        from evaluation import retrieval_gate as gate

        golden = tmp_path / "g.jsonl"
        golden.write_text(
            "\n".join(
                json.dumps({"query": f"q{i}", "metadata": {"subject": "os"}}) for i in range(4)
            ),
            encoding="utf-8",
        )

        class _Ev:
            metadata = {"category": "operating_system"}

        class _Fused:
            text_evidences = [_Ev()]

        def behaviour(query):
            if query == "q1":
                raise RuntimeError("Missing credentials")
            return _Fused(), None

        self._patch_retriever(monkeypatch, behaviour)
        metrics, outcomes, errors = asyncio.run(gate.run_gate(golden))

        assert len(outcomes) == 4, "抛异常也要占一条 outcome，否则分母会变小"
        assert metrics.n_queries == 4
        assert len(errors) == 1
        assert errors[0][0] == "q1"
        assert "Missing credentials" in errors[0][1]
        # 抛异常的 q1 记为"空结果"，不能算命中
        assert metrics.category_hit_at_k == 0.75
        assert metrics.empty_result_rate == 0.25

    def test_all_queries_failing_is_visible_not_silent(self, monkeypatch, tmp_path):
        from evaluation import retrieval_gate as gate

        golden = tmp_path / "g.jsonl"
        golden.write_text(
            json.dumps({"query": "q", "metadata": {"subject": "os"}}) + "\n", encoding="utf-8"
        )

        def behaviour(query):
            raise RuntimeError("boom")

        self._patch_retriever(monkeypatch, behaviour)
        metrics, _outcomes, errors = asyncio.run(gate.run_gate(golden))

        assert len(errors) == 1
        # 全部失败时精确率必须是 0，而不是"无命中所以无定义"被算成完美
        assert metrics.category_precision == 0.0
        assert metrics.empty_result_rate == 1.0

    def test_clean_run_reports_no_errors(self, monkeypatch, tmp_path):
        from evaluation import retrieval_gate as gate

        golden = tmp_path / "g.jsonl"
        golden.write_text(
            json.dumps({"query": "q", "metadata": {"subject": "os"}}) + "\n", encoding="utf-8"
        )

        class _Ev:
            metadata = {"category": "operating_system"}

        class _Fused:
            text_evidences = [_Ev()]

        self._patch_retriever(monkeypatch, lambda q: (_Fused(), None))
        _metrics, _outcomes, errors = asyncio.run(gate.run_gate(golden))
        assert errors == []
