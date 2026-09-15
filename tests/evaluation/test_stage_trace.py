"""阶段级行为追踪的纯函数测试。

`stage_trace` 是拆分 `aretrieve_documents` 的安全网：它记录每个阶段函数的入参与返回值，
把"最终输出一致"细化为"每一步都一致"。它自己必须先可信，否则"比对通过"没有意义。

这里只测**纯函数**部分（签名、归一化、比对），不建索引 —— 端到端部分需要真索引，
由 `evaluation.stage_trace` 的 CLI 承担。

一处刻意的设计约束：`signature` 对 callable 必须用 `__qualname__` 而不是 `repr`。
`repr(function)` 含内存地址，会让基线每次运行都不同 —— 这类"看起来在比对、其实永远不等"
的缺陷最难发现，所以单独有一条测试。
"""

from __future__ import annotations

import math

from langchain_core.documents import Document

from evaluation.stage_trace import (
    StageStep,
    StageTrace,
    _deep_equal,
    diff_traces,
    signature,
    trace_stages,
)


def _doc(content: str = "正文", *, src: str = "a.md", score: float = 0.5) -> Document:
    return Document(
        page_content=content,
        metadata={"source_file": src, "section.id": "s1", "recall_score": score},
    )


class TestSignature:
    def test_document_reduces_to_identity_fields(self):
        sig = signature(_doc("正文内容", src="x.md", score=0.25))
        assert sig["src"] == "x.md"
        assert sig["sec"] == "s1"
        assert sig["score"] == 0.25
        assert isinstance(sig["hash"], str) and len(sig["hash"]) == 12

    def test_document_hash_is_content_addressed(self):
        assert signature(_doc("甲"))["hash"] != signature(_doc("乙"))["hash"]
        assert signature(_doc("甲"))["hash"] == signature(_doc("甲"))["hash"]

    def test_document_does_not_embed_full_text(self):
        """正文不进基线 —— 否则基线文件会被正文撑爆，正文改动也会淹没真正的行为变化。"""
        sig = signature(_doc("很长的正文" * 500))
        assert len(str(sig)) < 400

    def test_primitives_pass_through(self):
        assert signature(None) is None
        assert signature(7) == 7
        assert signature("s") == "s"
        assert signature(True) is True

    def test_float_keeps_full_precision(self):
        """不做 round：round 到 1e-6 会在边界上产生随机差异。"""
        assert signature(0.1234567891) == 0.1234567891

    def test_callable_uses_qualname_not_repr(self):
        """repr(function) 含内存地址 → 基线每次运行都不同。"""
        sig = signature(signature)
        assert "0x" not in sig
        assert "signature" in sig

    def test_dict_is_sorted_by_key(self):
        assert signature({"b": 1, "a": 2}) == {"a": 2, "b": 1}

    def test_set_is_sorted(self):
        assert signature({"b", "a", "c"}) == ["a", "b", "c"]

    def test_nested_structures(self):
        sig = signature([(_doc("x", src="m.md"), 0.9)])
        assert sig[0][1] == 0.9
        assert sig[0][0]["src"] == "m.md"

    def test_unknown_type_falls_back_to_type_name(self):
        class Weird:
            pass

        assert signature(Weird()) == "<Weird>"


class TestStageTraceNormalized:
    def test_sorts_by_stage_then_inputs(self):
        trace = StageTrace(
            query="q",
            steps=[
                StageStep("b", "in2", "out"),
                StageStep("a", "in1", "out"),
                StageStep("a", "in0", "out"),
            ],
            final=[],
        )
        assert [s["stage"] for s in trace.normalized()] == ["a", "a", "b"]
        assert [s["in"] for s in trace.normalized()] == ["in0", "in1", "in2"]

    def test_normalization_makes_concurrent_order_irrelevant(self):
        """阶段内部可能并发调用，完成次序不定；归一化后两份记录必须等价。"""
        one = StageTrace("q", [StageStep("r", "a", 1), StageStep("r", "b", 2)], [])
        two = StageTrace("q", [StageStep("r", "b", 2), StageStep("r", "a", 1)], [])
        assert one.normalized() == two.normalized()

    def test_as_dict_keeps_stage_call_sequence_unmodified(self):
        trace = StageTrace("q", [StageStep("b", 1, 1), StageStep("a", 2, 2)], [])
        assert trace.as_dict()["stages_called"] == ["b", "a"]


class TestDiffTraces:
    def _base(self) -> dict:
        return {
            "query": "q",
            "stages_called": ["a", "b"],
            "steps": [
                {"stage": "a", "in": [1], "out": [2]},
                {"stage": "b", "in": "x", "out": "y"},
            ],
            "final": [{"src": "a.md", "score": 0.5}],
        }

    def test_identical_has_no_problems(self):
        assert diff_traces(self._base(), self._base()) == []

    def test_stage_sequence_change_short_circuits(self):
        actual = self._base()
        actual["stages_called"] = ["a"]
        problems = diff_traces(self._base(), actual)
        assert len(problems) == 1
        assert "阶段序列不同" in problems[0]

    def test_call_count_change_reported(self):
        actual = self._base()
        actual["steps"] = actual["steps"][:1]
        problems = diff_traces(self._base(), actual)
        assert any("调用次数不同" in p for p in problems)

    def test_input_change_localizes_stage_and_index(self):
        actual = self._base()
        actual["steps"][1]["in"] = "changed"
        problems = diff_traces(self._base(), actual)
        assert len(problems) == 1
        assert "[1]" in problems[0]
        assert "阶段 b" in problems[0]
        assert "入参" in problems[0]

    def test_output_change_detected(self):
        actual = self._base()
        actual["steps"][0]["out"] = [999]
        problems = diff_traces(self._base(), actual)
        assert any("返回值" in p for p in problems)

    def test_final_change_detected(self):
        actual = self._base()
        actual["final"] = [{"src": "b.md", "score": 0.5}]
        assert any("最终返回" in p for p in diff_traces(self._base(), actual))

    def test_float_within_tolerance_is_not_a_difference(self):
        """浮点加法次序变化只影响最后几位，不应判为行为变化。"""
        expected, actual = self._base(), self._base()
        expected["final"] = [{"src": "a.md", "score": 0.5}]
        actual["final"] = [{"src": "a.md", "score": 0.5 + 1e-15}]
        assert diff_traces(expected, actual) == []

    def test_float_beyond_tolerance_is_a_difference(self):
        expected, actual = self._base(), self._base()
        expected["final"] = [{"src": "a.md", "score": 0.5}]
        actual["final"] = [{"src": "a.md", "score": 0.6}]
        assert diff_traces(expected, actual) != []


class TestDeepEqual:
    def test_floats_close(self):
        assert _deep_equal(0.1 + 0.2, 0.3, rel_tol=1e-9)
        assert not _deep_equal(0.1, 0.2, rel_tol=1e-9)

    def test_int_and_float_are_compatible(self):
        """JSON 往返会把 int 变成 float，比对不能因此失败。"""
        assert _deep_equal(1, 1.0, rel_tol=1e-9)

    def test_dict_key_mismatch(self):
        assert not _deep_equal({"a": 1}, {"b": 1}, rel_tol=1e-9)

    def test_list_length_mismatch(self):
        assert not _deep_equal([1, 2], [1], rel_tol=1e-9)

    def test_nested(self):
        assert _deep_equal({"a": [1, {"b": 2.0}]}, {"a": [1.0, {"b": 2}]}, rel_tol=1e-9)

    def test_type_mismatch_not_swallowed(self):
        assert not _deep_equal("1", 1, rel_tol=1e-9)
        assert not _deep_equal(None, 0, rel_tol=1e-9)

    def test_nan_never_equal(self):
        assert not _deep_equal(math.nan, math.nan, rel_tol=1e-9)


class TestTraceStagesInstallsAndRestores:
    def test_patches_then_restores(self):
        """拦截器必须原样还原 —— 漏还原会污染同进程后续所有测试。"""
        from rag import retriever as R

        before = {
            attr: getattr(R, attr, None)
            for _, attr in __import__(
                "evaluation.stage_trace", fromlist=["STAGE_TARGETS"]
            ).STAGE_TARGETS
        }

        with trace_stages():
            from evaluation.stage_trace import STAGE_TARGETS

            for _stage, attr in STAGE_TARGETS:
                if before[attr] is not None:
                    assert getattr(R, attr) is not before[attr], f"{attr} 未被拦截"

        for attr, original in before.items():
            assert getattr(R, attr) is original, f"{attr} 未还原"

    def test_records_a_sync_stage_call(self):
        from rag import retriever as R

        with trace_stages() as steps:
            R._resolve_retrieval_policy("什么是进程？", 5, 0.06, False)

        assert len(steps) == 1
        assert steps[0].stage == "resolve_policy"
        assert isinstance(steps[0].outputs, (list, tuple))

    def test_restores_even_on_exception(self):
        from rag import retriever as R

        original = R._resolve_retrieval_policy
        try:
            with trace_stages():
                raise ValueError("boom")
        except ValueError:
            pass
        assert R._resolve_retrieval_policy is original
