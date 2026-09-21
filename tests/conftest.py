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


# ── 供 tests/test_collection_health.py 使用 ──────────────────────
# 记录本次运行**真实被收集到**的测试 node id。
#
# 为什么需要：pytest 对某些写法会**静默跳过**整个类/函数 —— 最典型的是
# `class TestX:` 里定义了 `__init__`（pytest 认为它不是测试类，直接不收集）。
# 这种丢失只发一条容易被忽略的 warning，不计入测试数、套件看起来还是绿的。
# 收集期把真实 node id 存下来，让那个元测试与源码里声明的做比对。
#
# ⚠️ **只能通过下面的 fixture 取，不要在测试里 `from conftest import ...`** ——
# 本目录下有 3 个 conftest.py（tests/、tests/service/、tests/client/），
# 它们**共用 `conftest` 这个模块名**，全量运行时谁先进 sys.modules 就取到谁。
# 实测：`from conftest import COLLECTED_NODEIDS` 在全量运行时会解析到
# `tests/service/conftest.py` 并抛 ImportError（单独跑却正常，极难察觉）。
COLLECTED_NODEIDS: list[str] = []


def pytest_collection_modifyitems(config, items) -> None:
    COLLECTED_NODEIDS.clear()
    COLLECTED_NODEIDS.extend(item.nodeid for item in items)


@pytest.fixture
def collected_nodeids() -> list[str]:
    """本次运行真实被收集到的测试 node id（供元测试比对）。

    走 fixture 而不是模块导入，绕开「多个 conftest 共用模块名」的坑。
    """
    return list(COLLECTED_NODEIDS)


@pytest.fixture
def is_full_test_run(request) -> bool:
    """本次是否跑了完整测试套件（没有显式指定路径）。

    给「只有全量运行才有意义」的元测试用。

    ⚠️ **判据只能是 pytest 收到的路径参数，不能用「收集到的文件集合 == 磁盘文件集合」** ——
    后者有个致命的自我矛盾：**某个文件的测试若全部被静默丢弃，
    它就不会出现在收集结果里**，于是两个集合不等、判据判定为「部分运行」而**跳过** ——
    恰恰在最该报警的时候沉默。（这个坑是反向验证时实测发现的。）
    """
    return list(request.config.args) == ["tests"]
