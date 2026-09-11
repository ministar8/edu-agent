"""网关路由测试。

本项目同时使用阿里云百炼与 DeepSeek 官方，且**同一个模型 ID 可以走不同网关**
（如 `dashscope:deepseek-v4-flash` 与 `deepseek:deepseek-v4-flash`）。
这里覆盖「标识 → 网关 → base/key → 客户端」整条链路，因为切网关时最容易踩的
不是逻辑错，而是「配了 A 家的 key 却取了 B 家的模型」以及两家客户端被缓存串用。
"""

import pytest
from pydantic import SecretStr

from core.llm import get_model, reset_llm_cache
from core.settings import Gateway, settings

DASHSCOPE_QWEN = "dashscope:qwen3.7-max"
DEEPSEEK_OFFICIAL = "deepseek:deepseek-v4-flash"
DASHSCOPE_DEEPSEEK = "dashscope:deepseek-v4-flash"


@pytest.fixture
def both_gateways(monkeypatch):
    """两家 key 都配上，并清空缓存以强制重新构造。"""
    monkeypatch.setattr(settings, "DASHSCOPE_API_KEY", SecretStr("sk-dashscope"))
    monkeypatch.setattr(settings, "DEEPSEEK_API_KEY", SecretStr("sk-deepseek"))
    reset_llm_cache()
    yield


class TestGatewayFor:
    @pytest.mark.parametrize(
        ("ref", "expected"),
        [
            (DASHSCOPE_QWEN, Gateway.DASHSCOPE),
            (DEEPSEEK_OFFICIAL, Gateway.DEEPSEEK),
            (DASHSCOPE_DEEPSEEK, Gateway.DASHSCOPE),
        ],
    )
    def test_parses_gateway_from_ref(self, ref, expected):
        assert settings.gateway_for(ref) is expected

    def test_unknown_gateway_raises(self):
        """不再「猜」—— 未知网关直接报错，而不是静默走某一家。"""
        with pytest.raises(ValueError):
            settings.gateway_for("openai:gpt-5")


class TestBaseRouting:
    def test_dashscope_ref_uses_dashscope_base(self):
        assert settings.api_base_for_model(DASHSCOPE_QWEN) == settings.DASHSCOPE_API_BASE

    def test_deepseek_ref_uses_deepseek_base(self):
        assert settings.api_base_for_model(DEEPSEEK_OFFICIAL) == settings.DEEPSEEK_API_BASE

    def test_same_model_id_routes_by_gateway_not_by_name(self):
        """同一个 deepseek 模型 ID，前缀不同 → base 不同。这是本次重构的核心。"""
        assert settings.api_base_for_model(DASHSCOPE_DEEPSEEK) != settings.api_base_for_model(
            DEEPSEEK_OFFICIAL
        )
        assert settings.api_base_for_model(DASHSCOPE_DEEPSEEK) == settings.DASHSCOPE_API_BASE


class TestKeyRouting:
    def test_each_gateway_gets_its_own_key(self, both_gateways):
        assert settings.api_key_for_model(DASHSCOPE_QWEN) == "sk-dashscope"
        assert settings.api_key_for_model(DEEPSEEK_OFFICIAL) == "sk-deepseek"

    def test_missing_deepseek_key_raises_actionable_error(self, monkeypatch):
        """只配了 DashScope 的 key 时取 DeepSeek 官方模型，必须明确告诉缺哪个变量。"""
        monkeypatch.setattr(settings, "DEEPSEEK_API_KEY", None)
        with pytest.raises(RuntimeError, match="DEEPSEEK_API_KEY"):
            settings.api_key_for_model(DEEPSEEK_OFFICIAL)

    def test_missing_dashscope_key_raises_actionable_error(self, monkeypatch):
        monkeypatch.setattr(settings, "DASHSCOPE_API_KEY", None)
        with pytest.raises(RuntimeError, match="DASHSCOPE_API_KEY"):
            settings.api_key_for_model(DASHSCOPE_QWEN)


class TestClientConstruction:
    def test_dashscope_client_uses_dashscope_base(self):
        assert get_model(DASHSCOPE_QWEN).openai_api_base == settings.DASHSCOPE_API_BASE

    def test_deepseek_client_uses_deepseek_base(self, both_gateways):
        assert get_model(DEEPSEEK_OFFICIAL).openai_api_base == settings.DEEPSEEK_API_BASE

    def test_same_model_on_two_gateways_gets_two_distinct_clients(self, both_gateways):
        """同一模型 ID 走不同网关时，客户端必须分开 —— 缓存键含网关就是为了防串用。"""
        official = get_model(DEEPSEEK_OFFICIAL)
        via_dashscope = get_model(DASHSCOPE_DEEPSEEK)

        assert official is not via_dashscope
        assert official.openai_api_base != via_dashscope.openai_api_base
        assert official.model_name == via_dashscope.model_name  # 模型 ID 相同

    def test_two_gateways_coexist_independently(self, both_gateways):
        qwen = get_model(DASHSCOPE_QWEN)
        deepseek = get_model(DEEPSEEK_OFFICIAL)
        assert qwen is not deepseek
        assert qwen.openai_api_base != deepseek.openai_api_base

    def test_thinking_mode_injected_per_vendor(self, both_gateways):
        """思考模式参数按**厂商**注入（两家都是 OpenAI 兼容，但私有参数不同）。"""
        assert get_model(DEEPSEEK_OFFICIAL).extra_body == {"thinking": {"type": "disabled"}}
        # DashScope 的 qwen3-max 是思考模型，必须显式开启
        assert get_model(DASHSCOPE_QWEN).extra_body == {"enable_thinking": True}
