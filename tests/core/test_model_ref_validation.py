"""启动期模型引用校验与已删除字段的回归保护。"""

import pytest
from pydantic import SecretStr

from core.settings import Settings


def _base_env(**overrides) -> dict:
    env = {
        "DASHSCOPE_API_KEY": SecretStr("sk-dash"),
        "DEEPSEEK_API_KEY": None,
        "USE_FAKE_MODEL": False,
        "LLM_MODEL": "dashscope:qwen3.8-27b",
        "DEFAULT_MODEL": "",
    }
    env.update(overrides)
    return env


def test_valid_llm_model_constructs():
    cfg = Settings(**_base_env())
    assert cfg.LLM_MODEL == "dashscope:qwen3.8-27b"
    assert cfg.DEFAULT_MODEL


def test_llm_model_requires_active_gateway():
    with pytest.raises(ValueError, match="LLM_MODEL"):
        Settings(**_base_env(LLM_MODEL="deepseek:deepseek-v4-flash", DEEPSEEK_API_KEY=None))


def test_llm_model_unknown_model_id():
    with pytest.raises(ValueError, match="model_id"):
        Settings(**_base_env(LLM_MODEL="dashscope:not-a-real-model"))


def test_llm_model_bad_format():
    with pytest.raises(ValueError, match="LLM_MODEL"):
        Settings(**_base_env(LLM_MODEL="qwen3.8-27b"))


def test_explicit_default_model_validated():
    with pytest.raises(ValueError, match="DEFAULT_MODEL"):
        Settings(**_base_env(DEFAULT_MODEL="deepseek:deepseek-v4-flash", DEEPSEEK_API_KEY=None))


def test_llm_model_fast_field_removed():
    assert "LLM_MODEL_FAST" not in Settings.model_fields


def test_temp_synthesis_field_removed():
    assert "TEMP_SYNTHESIS" not in Settings.model_fields


def test_fake_mode_skips_gateway_requirement_for_default(monkeypatch):
    cfg = Settings(
        USE_FAKE_MODEL=True,
        DASHSCOPE_API_KEY=None,
        DEEPSEEK_API_KEY=None,
        LLM_MODEL="fake:fake",
        DEFAULT_MODEL="",
    )
    assert cfg.DEFAULT_MODEL == "fake:fake"
