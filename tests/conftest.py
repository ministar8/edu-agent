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


@pytest.fixture(autouse=True)
def _isolated_metrics(tmp_path, monkeypatch):
    """把 metrics 单例的输出重定向到临时文件，杜绝测试污染运行时指标。

    `rag.metrics.metrics` 是模块级单例，`MetricsWriter.__init__` 在 import 期就把
    `_output_path` 固定为真实的 `data/metrics/rag_metrics.jsonl`。任何测试只要
    走到 emit 路径（检索 / 入库 / 切分），都会往这个真实文件追加行 ——
    实测全量跑一轮会让它增长约 2.6 KB。`data/` 虽被 gitignore，不会脏化仓库，
    但它会持续污染本地的运行时指标数据，且失败时很难定位来源。

    与 `semantic_cache._DATA_DIR` 属同一类"模块级常量在 import 期固化"的陷阱。
    """
    from rag.metrics import metrics

    monkeypatch.setattr(metrics, "_output_path", tmp_path / "rag_metrics.jsonl")
