import pytest

from core.llm import get_llm, get_model, reset_llm_cache
from core.settings import settings

DASHSCOPE_REF = "dashscope:qwen3.7-max"
FAKE_REF = "fake:fake"


@pytest.fixture
def dashscope_as_rag_model(monkeypatch):
    """把 RAG 链使用的模型指向已配置凭据的网关（测试环境只配了 DASHSCOPE_API_KEY）。"""
    monkeypatch.setattr(settings, "LLM_MODEL", DASHSCOPE_REF)


def test_get_model_fake():
    assert get_model(FAKE_REF) is not None


def test_get_model_none_defaults_to_default():
    assert get_model(None) is not None


def test_get_model_cached_by_ref_and_temp():
    assert get_model(DASHSCOPE_REF) is get_model(DASHSCOPE_REF)


def test_fake_model_is_never_cached():
    """FakeToolModel 有状态（响应队列会被消费，耗尽后静默循环复用），必须每次新建。

    缓存共享会让多个 agent 的响应互相穿插，且不会报错，只会给出错误答案。
    """
    assert get_model(FAKE_REF) is not get_model(FAKE_REF)


def test_two_entrypoints_share_one_instance(dashscope_as_rag_model):
    """get_model 与 get_llm 指向同一标识时应共享同一实例（两条入口已合并为一个缓存）。"""
    assert get_model(DASHSCOPE_REF, temperature=0.3) is get_llm(streaming=True, temperature=0.3)


def test_temperature_part_of_cache_key():
    assert get_model(DASHSCOPE_REF, temperature=0.3) is not get_model(
        DASHSCOPE_REF, temperature=0.0
    )


def test_streaming_part_of_cache_key(dashscope_as_rag_model):
    assert get_llm(streaming=True) is not get_llm(streaming=False)


def test_get_llm_default_is_non_streaming(dashscope_as_rag_model):
    """RAG 调用点全部显式 streaming=False；默认值须与之一致，避免误导。"""
    assert get_llm() is get_llm(streaming=False)
    assert get_llm() is not get_llm(streaming=True)


def test_reset_llm_cache_forces_rebuild():
    first = get_model(DASHSCOPE_REF)
    reset_llm_cache()
    assert get_model(DASHSCOPE_REF) is not first


def test_use_fast_removed():
    import inspect

    from core import llm as llm_mod

    assert "use_fast" not in inspect.signature(llm_mod.get_llm).parameters
