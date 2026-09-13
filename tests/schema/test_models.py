"""模型标识与网关的解析测试。

关键约定：标识形如 ``<gateway>:<model_id>``，网关（走哪家）与模型 ID（哪个模型）分离，
因此同一个模型 ID 可以显式选择走不同网关。
"""

import pytest

from schema.models import (
    GATEWAY_DEFAULT_MODEL,
    GATEWAY_MODELS,
    Gateway,
    make_model_ref,
    model_refs_for,
    parse_model_ref,
)


class TestParseModelRef:
    def test_parses_gateway_and_model_id(self):
        assert parse_model_ref("dashscope:qwen3.8-max") == (Gateway.DASHSCOPE, "qwen3.8-max")

    def test_same_model_id_can_choose_either_gateway(self):
        """同一 DeepSeek 模型，既可走官方也可走阿里云 —— 这正是分离网关的意义。"""
        assert parse_model_ref("deepseek:deepseek-v4-flash") == (
            Gateway.DEEPSEEK,
            "deepseek-v4-flash",
        )
        assert parse_model_ref("dashscope:deepseek-v4-flash") == (
            Gateway.DASHSCOPE,
            "deepseek-v4-flash",
        )

    def test_model_id_may_itself_contain_separator(self):
        gateway, model_id = parse_model_ref("dashscope:vendor:model")
        assert gateway is Gateway.DASHSCOPE
        assert model_id == "vendor:model"

    @pytest.mark.parametrize("bad", ["", "qwen3.8-max", "dashscope:", ":qwen3.8-max"])
    def test_rejects_malformed_ref(self, bad):
        with pytest.raises(ValueError):
            parse_model_ref(bad)

    def test_rejects_unknown_gateway(self):
        """未知网关直接报错，绝不静默兜底到某一家。"""
        with pytest.raises(ValueError):
            parse_model_ref("openai:gpt-5")


class TestGatewayModels:
    def test_every_gateway_has_models_and_a_matching_default(self):
        for gateway in Gateway:
            assert GATEWAY_MODELS[gateway], f"{gateway} 未声明任何模型"
            assert GATEWAY_DEFAULT_MODEL[gateway] in GATEWAY_MODELS[gateway]

    def test_dashscope_also_serves_deepseek_models(self):
        """阿里云百炼代理 DeepSeek 模型，所以同一 ID 会出现在两个网关下。"""
        assert "deepseek-v4-flash" in GATEWAY_MODELS[Gateway.DASHSCOPE]
        assert "deepseek-v4-flash" in GATEWAY_MODELS[Gateway.DEEPSEEK]
        assert {"qwen3.8-max", "qwen3.8-flash", "qwen3.8-27b"} <= GATEWAY_MODELS[Gateway.DASHSCOPE]

    def test_deepseek_gateway_only_serves_own_models(self):
        assert all(model.startswith("deepseek") for model in GATEWAY_MODELS[Gateway.DEEPSEEK])

    def test_model_refs_are_prefixed_with_gateway(self):
        refs = model_refs_for(Gateway.DASHSCOPE)
        assert refs
        assert all(ref.startswith("dashscope:") for ref in refs)
        assert f"dashscope:{GATEWAY_DEFAULT_MODEL[Gateway.DASHSCOPE]}" in refs


class TestMakeModelRef:
    def test_round_trips_with_parse(self):
        ref = make_model_ref(Gateway.DEEPSEEK, "deepseek-v4-pro")
        assert ref == "deepseek:deepseek-v4-pro"
        assert parse_model_ref(ref) == (Gateway.DEEPSEEK, "deepseek-v4-pro")
