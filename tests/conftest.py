import asyncio
import sys

import pytest


def pytest_configure(config) -> None:
    """Windows 下默认 ProactorEventLoop 与异步 DB 驱动不兼容，统一切到 Selector。

    与 src/run_service.py 的处理保持一致。
    """
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


@pytest.fixture(autouse=True)
def _fresh_llm_cache():
    """每个测试从干净的 LLM 缓存开始，杜绝跨测试串扰。

    缓存键含 base/模型/温度/streaming，测试若用 monkeypatch 改了 settings，
    不清理就会命中上一次测试构造出来的客户端。
    """
    from core.llm import reset_llm_cache

    reset_llm_cache()
    yield
    reset_llm_cache()
