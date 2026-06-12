from __future__ import annotations

from types import SimpleNamespace
from unittest import TestCase

from app.services.visualization_service import build_rag_process_error, build_rag_process_steps


class VisualizationServiceTests(TestCase):
    def test_build_rag_process_error_preserves_legacy_shape(self) -> None:
        result = build_rag_process_error("栈是什么", RuntimeError("boom"))

        self.assertEqual(result["trace"], {})
        self.assertEqual(result["result_text"], "")
        self.assertEqual(result["steps"][0]["type"], "input")
        self.assertEqual(result["steps"][1]["data"], "boom")

    def test_build_rag_process_steps_includes_source_nodes(self) -> None:
        docs = [
            SimpleNamespace(
                page_content="abcdef",
                metadata={"rerank_score": 0.8, "source": "a.md"},
            )
        ]
        trace = {
            "collections": ["data_structure"],
            "policy": {"coarse_k": 5, "threshold": 0.2, "retrieval_depth": "standard"},
            "routes": [{"route": "vector"}],
            "route_summary": {"hits_by_route": {"vector": 1}},
            "kg": {"used": False},
            "hyde": {"triggered": False},
            "counts": {"raw": 1, "after_dedup": 1, "after_threshold": 1, "after_rerank": 1, "final": 1},
        }

        steps = build_rag_process_steps(
            query="栈是什么",
            docs=docs,
            trace=trace,
            result_text="融合上下文",
        )

        self.assertEqual(len(steps), 4)
        self.assertEqual(steps[2]["data"][0]["content"], "abcdef")
        self.assertIn("实际搜索集合: data_structure", steps[1]["data"])
        self.assertIn("融合上下文", steps[3]["data"])
