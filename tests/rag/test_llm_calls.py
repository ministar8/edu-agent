"""RAG 层统一 LLM 调用入口的测试。

核心约定：**超时 / 异常 / 结构不符一律返回 None**，由调用方决定降级方向 ——
不再由被调方替调用方决定"失败就该给空串"。
"""

import asyncio
import time

import pytest
from pydantic import BaseModel

from rag import llm_calls


class _Schema(BaseModel):
    value: str = ""


class _Msg:
    def __init__(self, content: str) -> None:
        self.content = content


class _FakeLLM:
    """可控假件：按配置抛错 / 返回文本 / 返回结构化结果 / 延迟，并记录传入的 config。"""

    def __init__(self, *, raises=None, content="hello", structured=None, delay=0.0):
        self._raises = raises
        self._content = content
        self._structured = structured
        self._delay = delay
        self.configs: list[dict | None] = []
        self.last_structured_method: str | None = None

    def _result(self):
        return self._structured if self._structured is not None else _Msg(self._content)

    def invoke(self, _prompt, config=None):
        self.configs.append(config)
        if self._raises is not None:
            raise self._raises
        return self._result()

    async def ainvoke(self, _prompt, config=None):
        if self._delay:
            await asyncio.sleep(self._delay)
        return self.invoke(_prompt, config)

    def with_structured_output(self, _schema, method=None):
        self.last_structured_method = method
        return self


@pytest.fixture
def install_llm(monkeypatch):
    def _install(fake: _FakeLLM) -> _FakeLLM:
        monkeypatch.setattr(llm_calls, "get_llm", lambda **_kwargs: fake)
        return fake

    return _install


class TestCallText:
    @pytest.mark.asyncio
    async def test_returns_stripped_text(self, install_llm):
        install_llm(_FakeLLM(content="  结果  "))
        result = await llm_calls.call_text("p", temperature=0.0, timeout=1, stage="t")
        assert result == "结果"

    @pytest.mark.asyncio
    async def test_exception_returns_none(self, install_llm):
        install_llm(_FakeLLM(raises=RuntimeError("boom")))
        assert await llm_calls.call_text("p", temperature=0.0, timeout=1, stage="t") is None

    @pytest.mark.asyncio
    async def test_timeout_returns_none_and_is_enforced(self, install_llm):
        """超时必须真的施加 —— 这是本次统一化的核心收益。"""
        install_llm(_FakeLLM(content="late", delay=0.3))
        start = time.monotonic()
        result = await llm_calls.call_text("p", temperature=0.0, timeout=0.02, stage="t")
        assert result is None
        assert time.monotonic() - start < 0.2


class TestCallTextSync:
    def test_returns_text(self, install_llm):
        install_llm(_FakeLLM(content="ok"))
        assert llm_calls.call_text_sync("p", temperature=0.0, stage="t") == "ok"

    def test_exception_returns_none(self, install_llm):
        install_llm(_FakeLLM(raises=RuntimeError("boom")))
        assert llm_calls.call_text_sync("p", temperature=0.0, stage="t") is None


class TestCallStructured:
    @pytest.mark.asyncio
    async def test_returns_schema_instance(self, install_llm):
        expected = _Schema(value="v")
        install_llm(_FakeLLM(structured=expected))
        result = await llm_calls.call_structured(
            "p", _Schema, temperature=0.0, timeout=1, stage="t"
        )
        assert result is expected

    @pytest.mark.asyncio
    async def test_exception_returns_none(self, install_llm):
        install_llm(_FakeLLM(raises=RuntimeError("boom")))
        assert (
            await llm_calls.call_structured("p", _Schema, temperature=0.0, timeout=1, stage="t")
            is None
        )

    @pytest.mark.asyncio
    async def test_wrong_type_returns_none(self, install_llm):
        """结构化解析返回非目标类型时，不能把脏数据交给调用方。"""
        install_llm(_FakeLLM(structured={"value": "dict"}))
        assert (
            await llm_calls.call_structured("p", _Schema, temperature=0.0, timeout=1, stage="t")
            is None
        )

    @pytest.mark.asyncio
    async def test_timeout_returns_none(self, install_llm):
        install_llm(_FakeLLM(structured=_Schema(), delay=0.3))
        assert (
            await llm_calls.call_structured("p", _Schema, temperature=0.0, timeout=0.02, stage="t")
            is None
        )

    @pytest.mark.asyncio
    async def test_passes_configured_method(self, install_llm):
        from core import settings as settings_singleton

        fake = install_llm(_FakeLLM(structured=_Schema(value="x")))
        await llm_calls.call_structured("p", _Schema, temperature=0.0, timeout=1, stage="t")
        assert fake.last_structured_method == settings_singleton.STRUCTURED_OUTPUT_METHOD

    @pytest.mark.asyncio
    async def test_method_fallback_on_bind_error(self, install_llm):
        class _StrictFake(_FakeLLM):
            def with_structured_output(self, _schema, method=None):
                if method is not None:
                    raise ValueError("method unsupported")
                return super().with_structured_output(_schema, method=None)

        fake = install_llm(_StrictFake(structured=_Schema(value="ok")))
        result = await llm_calls.call_structured(
            "p", _Schema, temperature=0.0, timeout=1, stage="t"
        )
        assert result is not None
        assert fake.last_structured_method is None


class TestTracingMetadata:
    """提示词阶段与提示词集版本必须随每次调用上报，否则质量变化无法归因。"""

    @pytest.mark.asyncio
    async def test_text_call_carries_stage_and_version(self, install_llm):
        fake = install_llm(_FakeLLM(content="ok"))
        await llm_calls.call_text("p", temperature=0.0, timeout=1, stage="hyde")

        metadata = fake.configs[0]["metadata"]
        assert metadata["prompt_stage"] == "hyde"
        assert metadata["prompt_set_version"]

    @pytest.mark.asyncio
    async def test_structured_call_carries_stage(self, install_llm):
        fake = install_llm(_FakeLLM(structured=_Schema()))
        await llm_calls.call_structured("p", _Schema, temperature=0.0, timeout=1, stage="grades")

        assert fake.configs[0]["metadata"]["prompt_stage"] == "grades"

    def test_sync_call_carries_stage(self, install_llm):
        fake = install_llm(_FakeLLM(content="ok"))
        llm_calls.call_text_sync("p", temperature=0.0, stage="decompose")

        assert fake.configs[0]["metadata"]["prompt_stage"] == "decompose"
