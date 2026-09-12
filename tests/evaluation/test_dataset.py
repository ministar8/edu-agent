"""评估包：数据集加载与配置（不依赖 ragas 运行时）。"""

from pathlib import Path

import pytest

from evaluation.config import EvaluationConfig
from evaluation.dataset import EvalSample, load_dataset


def test_load_dataset_sample_file():
    path = Path(__file__).resolve().parents[2] / "evals" / "sample_408.jsonl"
    samples = load_dataset(str(path))
    assert len(samples) >= 3
    assert samples[0].query
    assert samples[0].reference


def test_load_dataset_limit_and_missing(tmp_path):
    p = tmp_path / "empty.jsonl"
    p.write_text("# comment only\n", encoding="utf-8")
    assert load_dataset(str(p)) == []
    assert load_dataset(str(tmp_path / "nope.jsonl")) == []


def test_to_ragas_dict_fields():
    s = EvalSample(query="q", reference="r", contexts=["c1"], answer="a")
    d = s.to_ragas_dict()
    assert d["user_input"] == "q"
    assert d["retrieved_contexts"] == ["c1"]
    assert d["response"] == "a"
    assert d["reference"] == "r"


def test_eval_config_defaults():
    cfg = EvaluationConfig()
    assert "faithfulness" in cfg.ragas_metrics
    assert cfg.retrieval_k == 5


@pytest.mark.asyncio
async def test_prepare_samples_mocked(monkeypatch):
    from evaluation import adapters
    from evaluation.ragas_eval import prepare_samples

    async def fake_fill(sample, **kwargs):
        sample.contexts = ["ctx"]
        sample.answer = "ans"
        return sample

    monkeypatch.setattr(adapters, "fill_sample", fake_fill)
    # ragas_eval imported fill_sample by name — patch module reference
    import evaluation.ragas_eval as re_mod

    monkeypatch.setattr(re_mod, "fill_sample", fake_fill)
    samples = [EvalSample(query="q1", reference="r1")]
    filled = await prepare_samples(samples, EvaluationConfig())
    assert filled[0].answer == "ans"
