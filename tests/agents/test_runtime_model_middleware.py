"""RuntimeModelMiddleware：config 指定 model 时应替换请求中的客户端。"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from langchain.agents.middleware.types import ModelRequest
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.messages import HumanMessage

from agents.runtime_model import RuntimeModelMiddleware, _temperature_of


class _FakeRequest:
    def __init__(self, model):
        self.model = model
        self.overrode = None

    def override(self, **kwargs):
        clone = _FakeRequest(kwargs.get("model", self.model))
        clone.overrode = kwargs
        return clone


def test_temperature_of_reads_chat_openai_attr():
    assert _temperature_of(SimpleNamespace(temperature=0.0)) == 0.0
    assert _temperature_of(SimpleNamespace()) is not None


def test_wrap_without_config_model_keeps_default(monkeypatch):
    mw = RuntimeModelMiddleware()
    default_model = MagicMock(name="default")
    request = _FakeRequest(default_model)
    handler = MagicMock(return_value="ok")

    monkeypatch.setattr("agents.runtime_model.get_config", lambda: {})
    result = mw.wrap_model_call(request, handler)

    assert result == "ok"
    handler.assert_called_once_with(request)
    assert request.overrode is None


def test_wrap_with_config_model_overrides(monkeypatch):
    mw = RuntimeModelMiddleware()
    default_model = MagicMock(name="default", temperature=0.3)
    selected = MagicMock(name="selected")
    request = _FakeRequest(default_model)
    captured = {}

    def handler(req):
        captured["model"] = req.model
        return "ok"

    monkeypatch.setattr(
        "agents.runtime_model.get_config",
        lambda: {"configurable": {"model": "dashscope:qwen3.8-27b"}},
    )
    monkeypatch.setattr(
        "agents.runtime_model.get_model",
        lambda ref, temperature=None: selected if ref == "dashscope:qwen3.8-27b" else None,
    )

    result = mw.wrap_model_call(request, handler)
    assert result == "ok"
    assert captured["model"] is selected


@pytest.mark.asyncio
async def test_awrap_with_config_model_overrides(monkeypatch):
    mw = RuntimeModelMiddleware()
    default_model = MagicMock(name="default", temperature=0.0)
    selected = MagicMock(name="selected")
    request = _FakeRequest(default_model)
    captured = {}

    async def handler(req):
        captured["model"] = req.model
        return "ok"

    monkeypatch.setattr(
        "agents.runtime_model.get_config",
        lambda: {"configurable": {"model": "fake:fake"}},
    )
    monkeypatch.setattr(
        "agents.runtime_model.get_model",
        lambda ref, temperature=None: selected,
    )

    result = await mw.awrap_model_call(request, handler)
    assert result == "ok"
    assert captured["model"] is selected


def test_real_model_request_override_contract(monkeypatch):
    """对齐 LangChain ModelRequest.override 的不可变克隆约定，而非只测 mock。"""
    mw = RuntimeModelMiddleware()
    default_model = FakeListChatModel(responses=["default"])
    selected = FakeListChatModel(responses=["selected"])
    request = ModelRequest(model=default_model, messages=[HumanMessage("hi")])

    monkeypatch.setattr(
        "agents.runtime_model.get_config",
        lambda: {"configurable": {"model": "fake:fake"}},
    )
    monkeypatch.setattr("agents.runtime_model.get_model", lambda ref, temperature=None: selected)

    captured = {}

    def handler(req: ModelRequest):
        captured["request"] = req
        return "ok"

    assert mw.wrap_model_call(request, handler) == "ok"
    assert captured["request"] is not request
    assert captured["request"].model is selected
    assert request.model is default_model
