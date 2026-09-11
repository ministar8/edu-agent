import logging
from contextlib import asynccontextmanager

import pytest
from fastapi import FastAPI

from schema import AgentInfo


@pytest.mark.asyncio
async def test_lifespan(monkeypatch, caplog) -> None:
    """lifespan 应建表、初始化 checkpointer 与 store，并把两者挂到每个 agent。"""
    from service import service

    fake_saver_setup = False
    init_db_called = False

    class FakeSaver:
        async def setup(self) -> None:
            nonlocal fake_saver_setup
            fake_saver_setup = True

    fake_saver = FakeSaver()
    fake_store = object()

    @asynccontextmanager
    async def fake_initialize_database():
        yield fake_saver

    @asynccontextmanager
    async def fake_initialize_store():
        yield fake_store

    def fake_init_db() -> None:
        nonlocal init_db_called
        init_db_called = True

    agents = {
        "good": type("Agent", (), {"checkpointer": None, "store": None})(),
        "bad": type("Agent", (), {"checkpointer": None, "store": None})(),
    }

    monkeypatch.setattr(service, "initialize_database", fake_initialize_database)
    monkeypatch.setattr(service, "initialize_store", fake_initialize_store)
    monkeypatch.setattr(service, "init_db", fake_init_db)
    monkeypatch.setattr(service, "get_agent", lambda agent_key: agents[agent_key])
    monkeypatch.setattr(
        service,
        "get_all_agent_info",
        lambda: [
            AgentInfo(key="good", description=""),
            AgentInfo(key="bad", description=""),
        ],
    )

    caplog.set_level(logging.INFO, logger=service.logger.name)

    async with service.lifespan(FastAPI()):
        pass

    assert init_db_called
    assert fake_saver_setup
    for key in ("good", "bad"):
        assert agents[key].checkpointer is fake_saver
        assert agents[key].store is fake_store
    assert "Agent configured with checkpointer: good" in caplog.text
    assert "Agent configured with checkpointer: bad" in caplog.text


@pytest.mark.asyncio
async def test_lifespan_exports_langsmith_env(monkeypatch) -> None:
    """lifespan 启动时应把 LangSmith 追踪配置同步到进程环境变量。"""
    from service import service

    calls = {"count": 0}

    class FakeSettings:
        LANGCHAIN_TRACING_V2 = False
        LANGCHAIN_PROJECT = "edu-test"
        LANGCHAIN_ENDPOINT = "https://api.smith.langchain.com"
        LANGCHAIN_API_KEY = None

        def export_langsmith_env(self) -> bool:
            calls["count"] += 1
            return self.LANGCHAIN_TRACING_V2

    @asynccontextmanager
    async def fake_cm():
        yield object()

    monkeypatch.setattr(service, "settings", FakeSettings())
    monkeypatch.setattr(service, "initialize_database", fake_cm)
    monkeypatch.setattr(service, "initialize_store", fake_cm)
    monkeypatch.setattr(service, "init_db", lambda: None)
    monkeypatch.setattr(service, "get_all_agent_info", lambda: [])

    async with service.lifespan(FastAPI()):
        pass

    assert calls["count"] == 1
