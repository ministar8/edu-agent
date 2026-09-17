"""配置接线自检：挡住「配置存在但不生效」这类静默故障。

**为什么需要这个测试**

本项目已三次遇到同一类坑，它们比明显 bug 更难查，因为代码看起来完全正常：

1. `settings.py` 里曾有 8 个超时字段（GLOBAL_DEADLINE / ROUTER_TIMEOUT /
   AGENT_PRIMARY_TIMEOUT …）从未被任何代码引用 —— 看着像有超时保护，实际没有；
2. `service.py` 的 `_HANDOFF_BACK_PREFIXES`（P3）在当前配置下**没有任何活路径**，
   属「有备无患」的防御性代码，容易被误认为系统依赖它；
3. `AGENT_RECURSION_LIMIT` 的前身：service 层从未设置 `recursion_limit`，于是
   落到 LangGraph 默认的 10007，异常循环要跑上万步才终止。

共同特征：**读代码看不出来，跑正常请求也看不出来，只在异常路径上暴露。**
因此用测试把「配置 → 运行时对象」这条线锁住，让断线在启动/CI 阶段就变红。

**三层检查**

- 第一层 `TestNoDeadSettings`：全量扫描 settings 字段，任何一个在 `src/` 内
  （含 settings 自身）完全没有读取点即为死配置。
- 第二层 `TestCriticalSettingsReachRuntimeObjects`：对声明了安全/行为语义的配置，
  实测它是否真的进入运行时对象（不是「代码里有引用」就算数）。采用**注册表**
  组织：每条检查是一个 `WiringProbe`，新增检查只需加一条记录。
- 第三层 `TestGuardSettingsAreNotSilentlyReverted`：把关键安全项的**有效取值**
  也钉死，防止被改回「看起来一样但不生效」的状态。

**如何新增一条第二层检查**：在 `_WIRING_PROBES` 里追加一个 `WiringProbe`，
其中 `read_runtime` 必须真的从一个运行时对象里把**当前生效的值**读出来
（构造客户端、捕获调用实参、读 config 字段等），而不是再次引用 settings。
新增后请务必按 skill `regression-test-validity-check` 做反向验证。
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = PROJECT_ROOT / "src"
SETTINGS_FILE = SRC_DIR / "core" / "settings.py"


def _settings_field_names() -> list[str]:
    """从 settings.py 源码取所有大写开头的字段名。

    用源码正则而非 `Settings.model_fields`：后者会包含 Pydantic 内部字段，
    且无法区分「本类定义」与「继承而来」。
    """
    text = SETTINGS_FILE.read_text(encoding="utf-8")
    return sorted(set(re.findall(r"^\s{4}([A-Z_][A-Z0-9_]*)\s*:", text, re.M)))


def _src_python_files() -> list[Path]:
    return sorted(p for p in SRC_DIR.rglob("*.py") if "__pycache__" not in p.parts)


class TestNoDeadSettings:
    """第一层：settings 里的字段必须至少被引用一次（定义之外）。

    扫描范围包含 settings.py 自身 —— validator、`model_post_init`、派生属性
    都会在那里消费字段（例如 `DASHSCOPE_API_KEY` 供网关构造，
    `USE_FAKE_MODEL` 供模型解析），不能只扫 settings.py 之外的文件。

    **本层的能力边界（务必知晓）**：

    - 判定方式是**源码文本匹配**，属近似手段。它能抓住「字段从未被提到」这种最
      直白的死配置，但**抓不住**「被提到了、却只在死分支里」的情形（P3 的
      `_HANDOFF_BACK_PREFIXES` 就是后者）。那类问题要靠第二层或人工审查。
    - 因此本层定位是「便宜的守门员」，不是「完备的证明」。
    - 若某个字段确实无需引用（如纯声明式的元信息），请登记进 `_KNOWN_UNUSED`
      并写明理由，而不是删掉本测试。
    """

    # 显式登记的「确实无需在 src/ 内引用」的字段。新增条目必须附理由。
    _KNOWN_UNUSED: dict[str, str] = {}

    def test_no_undocumented_dead_settings(self):
        field_names = _settings_field_names()
        assert field_names, "未解析到任何配置字段 —— settings.py 结构可能已变，请检查本测试"

        contents = {p: p.read_text(encoding="utf-8", errors="replace") for p in _src_python_files()}

        dead: list[str] = []
        for name in field_names:
            if name in self._KNOWN_UNUSED:
                continue
            # 定义处本身算 1 次出现；再有任何引用即视为有消费者
            occurrences = sum(
                len(re.findall(rf"\b{re.escape(name)}\b", text)) for text in contents.values()
            )
            if occurrences <= 1:
                dead.append(name)

        assert not dead, (
            f"以下配置项在 src/ 中从未被读取，属于死配置（看着有保护、实际不生效）："
            f"{dead}。请补上接线；若确实无需引用，请登记进 _KNOWN_UNUSED 并写明理由。"
        )

    def test_exemption_list_entries_are_real_and_still_unused(self):
        """元测试：豁免清单不能变成「垃圾桶」。

        每条豁免必须 (1) 是真实存在的字段，(2) 理由非空，(3) 当前确实仍无引用。
        一旦某条被接上了线，就该从清单里移除 —— 否则清单会慢慢失真。
        """
        field_names = set(_settings_field_names())
        contents = {p: p.read_text(encoding="utf-8", errors="replace") for p in _src_python_files()}

        for name, reason in self._KNOWN_UNUSED.items():
            assert name in field_names, f"豁免清单里的 {name} 已不存在于 settings，请移除"
            assert reason.strip(), f"豁免 {name} 缺理由"
            occurrences = sum(
                len(re.findall(rf"\b{re.escape(name)}\b", text)) for text in contents.values()
            )
            assert occurrences <= 1, (
                f"{name} 已获得引用，请从 _KNOWN_UNUSED 移除（清单需保持与现状一致）"
            )

    def test_scan_actually_covers_the_source_tree(self):
        """自检的元测试：确保扫描器不会因为路径写错而「空跑通过」。

        若 SRC_DIR 不存在或没有 py 文件，上面的测试会「零个死配置」而假绿。
        """
        files = _src_python_files()
        assert len(files) > 50, f"仅扫到 {len(files)} 个文件，源码路径可能不对"
        assert SETTINGS_FILE.exists()


# ── 第二层探针 ────────────────────────────────────────────────
#
# 每个探针返回「当前实际生效的值」。约定：
#   - 不联网、不依赖外部服务（用测试环境的假 key 构造客户端即可）；
#   - 不返回 None（None 视为探针失效，会被上面的测试判为失败）；
#   - 探针内部临时替换的东西必须用 try/finally 还原。


async def _probe_recursion_limit() -> Any:
    """读 `RunnableConfig.recursion_limit` —— 真正决定图执行上界的字段。

    本项目踩过的坑：字段可以存在、甚至被别处引用，但只有写进传给 `ainvoke`
    的 config 才生效；否则 LangGraph 会用默认值 10007。
    """
    from schema import UserInput
    from service.service import _handle_input

    class _State:
        values: dict = {}
        metadata = None
        tasks: list = []

    class _Agent:
        async def aget_state(self, config=None):  # noqa: ARG002
            return _State()

    kwargs, _ = await _handle_input(UserInput(message="你好"), _Agent(), "edu-assistant", "user-1")
    return kwargs["config"].get("recursion_limit")


async def _probe_llm_timeout() -> Any:
    """读构造出的 ChatOpenAI 的 `request_timeout`。

    超时保护必须落在真实客户端上；只在调用处写 `timeout=settings.LLM_TIMEOUT`
    而客户端不接收，等于没有超时。
    """
    from core.llm import _build_client

    client = _build_client("dashscope:qwen3.8-max", "qwen3.8-max", 0.3, streaming=False)
    return client.request_timeout


async def _probe_history_trim() -> Any:
    """捕获 `run_supervisor` 传给 `trim_conversation` 的 `max_messages` 实参。

    这是「短期限流」真正生效的位置：值必须从 settings 流到调用点，否则长 thread
    会把完整历史塞进模型上下文。用桩替换 inner_supervisor，避免真实调用模型。
    """
    from langchain_core.messages import HumanMessage

    import agents.teaching_graph as teaching_graph

    captured: dict = {}
    original_trim = teaching_graph.trim_conversation
    original_supervisor = teaching_graph.inner_supervisor

    def spy_trim(messages, *, max_messages):  # noqa: ANN001
        captured["max_messages"] = max_messages
        return original_trim(messages, max_messages=max_messages)

    class _StubSupervisor:
        async def ainvoke(self, payload, config=None):  # noqa: ANN001, ARG002
            return {"messages": payload.get("messages") or []}

    teaching_graph.trim_conversation = spy_trim
    teaching_graph.inner_supervisor = _StubSupervisor()
    try:
        await teaching_graph.run_supervisor({"messages": [HumanMessage(content="你好")]})
    finally:
        teaching_graph.trim_conversation = original_trim
        teaching_graph.inner_supervisor = original_supervisor

    return captured.get("max_messages")


async def _probe_retrieval_score_threshold() -> Any:
    """读 `aretrieve_documents` 的**签名默认值** —— 调用方不传时真正生效的那个值。

    只断言 `retriever.SCORE_THRESHOLD` 是不够的：那只是模块常量，
    真正决定行为的是**函数签名里的默认值**。两者可以脱钩
    （比如常量改了但签名写死了字面量），而脱钩后门禁指标才会变 ——
    那时已经晚了。这里直接读签名，把「配置 → 实际生效值」锁死。
    """
    import inspect

    from rag.retriever import aretrieve_documents

    return inspect.signature(aretrieve_documents).parameters["score_threshold"].default


async def _probe_rerank_expand_factor() -> Any:
    """读 `retriever._RERANK_EXPAND_FACTOR` —— 重排候选池倍数的运行时取值。

    该值决定 `coarse_k = min(k * factor, 50)`，直接关系到重排的召回与耗时。
    """
    from rag import retriever as R

    return R._RERANK_EXPAND_FACTOR


@dataclass(frozen=True)
class WiringProbe:
    """一条「配置 → 运行时对象」接线检查。"""

    setting: str
    describe: str
    read_runtime: Callable[[], Awaitable[Any]]


_WIRING_PROBES: tuple[WiringProbe, ...] = (
    WiringProbe(
        setting="RETRIEVAL_SCORE_THRESHOLD",
        describe="RRF 融合分数阈值，需成为检索入口的签名默认值（backlog #14）",
        read_runtime=_probe_retrieval_score_threshold,
    ),
    WiringProbe(
        setting="RERANK_EXPAND_FACTOR",
        describe="重排候选池倍数，需被 retriever 真正读取（backlog #14）",
        read_runtime=_probe_rerank_expand_factor,
    ),
    WiringProbe(
        setting="AGENT_RECURSION_LIMIT",
        describe="图执行上界，需写进传给 ainvoke 的 RunnableConfig.recursion_limit",
        read_runtime=_probe_recursion_limit,
    ),
    WiringProbe(
        setting="LLM_TIMEOUT",
        describe="单次 LLM 调用超时，需落在 ChatOpenAI 的 request_timeout 上",
        read_runtime=_probe_llm_timeout,
    ),
    WiringProbe(
        setting="MEMORY_HISTORY_MAX_MESSAGES",
        describe="送入模型的历史消息条数上限，需传到 trim_conversation 的 max_messages",
        read_runtime=_probe_history_trim,
    ),
)


class TestCriticalSettingsReachRuntimeObjects:
    """第二层：关键配置必须真的进入运行时对象，而非只是「代码里提到了」。

    每条检查由 `WiringProbe.read_runtime` 从**运行时对象**读出当前生效值
    （构造出来的客户端字段、调用点实际收到的实参、传给 `ainvoke` 的 config 等），
    再与 `settings` 里的声明值比对。这样即使代码里写了 `settings.XXX`，
    只要它没流到真正生效的地方，测试就会红。
    """

    @pytest.mark.asyncio
    @pytest.mark.parametrize("probe", _WIRING_PROBES, ids=lambda p: p.setting)
    async def test_setting_reaches_runtime_object(self, probe: WiringProbe):
        from core import settings

        expected = getattr(settings, probe.setting)
        actual = await probe.read_runtime()

        assert actual is not None, (
            f"{probe.setting} 的探针没有读到任何运行时值（返回 None）——"
            f"探针本身可能已失效，请检查 {probe.describe}"
        )
        assert actual == expected, (
            f"{probe.setting} 未接线：声明值={expected!r}，但运行时实际生效值={actual!r}。\n"
            f"该接线点的作用：{probe.describe}\n"
            "请检查读取点是否仍把 settings 值传到了真正生效的位置。"
        )

    def test_registry_is_not_empty_and_covers_real_fields(self):
        """元测试：清单不能为空，且每条都必须指向真实存在的 settings 字段。"""
        from core import settings

        assert _WIRING_PROBES, "接线清单为空 —— 第二层等于没有检查"
        for probe in _WIRING_PROBES:
            assert hasattr(settings, probe.setting), (
                f"清单里的 {probe.setting} 已不存在于 settings，请移除该条"
            )
            assert probe.describe.strip(), f"{probe.setting} 缺作用说明"

    def test_no_duplicate_probes(self):
        """元测试：同一配置不必重复登记，重复通常意味着有人加了冗余检查。"""
        names = [p.setting for p in _WIRING_PROBES]
        duplicates = {n for n in names if names.count(n) > 1}
        assert not duplicates, f"接线清单存在重复项：{sorted(duplicates)}"


class TestGuardSettingsAreNotSilentlyReverted:
    """第三层：安全项的有效取值被钉死，防止改回「看似相同、实则无效」的状态。"""

    def test_recursion_limit_is_below_framework_default(self):
        """必须显著低于 LangGraph 默认值，否则等于没有护栏。"""
        from core import settings

        try:
            from langgraph._internal._config import DEFAULT_RECURSION_LIMIT
        except ImportError:  # pragma: no cover - 依赖内部路径，缺失时跳过而非误报
            pytest.skip("无法导入 LangGraph 默认递归上限常量")

        assert settings.AGENT_RECURSION_LIMIT < DEFAULT_RECURSION_LIMIT, (
            f"AGENT_RECURSION_LIMIT={settings.AGENT_RECURSION_LIMIT} "
            f"未低于框架默认值 {DEFAULT_RECURSION_LIMIT}，护栏形同虚设。"
        )

    def test_recursion_limit_has_headroom_for_real_work(self):
        """同时不能勒得太紧，要容得下正常的多轮工具调用。"""
        from core import settings

        assert settings.AGENT_RECURSION_LIMIT >= 40, (
            "上界过低会截断正常请求（实测专家每轮工具调用约耗 2-3 step）。"
        )

    def test_recursion_limit_is_env_overridable(self, monkeypatch):
        """必须是可配置项：运维需要在不改代码的前提下调整上界。"""
        from core.settings import Settings

        monkeypatch.setenv("AGENT_RECURSION_LIMIT", "123")
        assert Settings().AGENT_RECURSION_LIMIT == 123


class TestFeatureFlagsActuallyGate:
    """特性开关必须真的改变行为，而不只是「读了一下标志」。

    这是「配置存在但不生效」的另一种形态：开关被读到了，但分支里没有真正跳过
    对应的工作。典型症状是关掉开关后系统照旧联网 / 照旧耗时，而代码看着没问题。

    与第二层注册表的区别：注册表断言的是「值透传到运行时对象」，形态是
    `实际值 == 声明值`；这里断言的是「行为门控」，形态是「关闭后不应发生某事」。
    断言形状不同，故单独成类，不进 `_WIRING_PROBES`。
    """

    def test_rerank_disabled_skips_network_call(self, monkeypatch):
        """`RERANK_ENABLED=False` 时 `rerank` 必须直接截断返回，不构造 HTTP 客户端。

        **探针设计上的坑（实测踩过）**：不能靠「在假客户端里抛异常」来检测 ——
        `rerank` 末尾有一个兜底的 `except Exception`，会把异常吞掉并降级返回
        `documents[:top_k]`，于是「守卫被删掉」与「守卫正常工作」表现完全一样，
        测试会永远绿。故改为**记录客户端是否被构造**这一副作用。

        另需用唯一 query 规避重排缓存，否则缓存命中同样会掩盖守卫缺失。
        """
        from langchain_core.documents import Document

        from core import settings
        from rag import reranker

        monkeypatch.setattr(settings, "RERANK_ENABLED", False)

        constructed: list[int] = []

        class _RecordingClient:
            def __init__(self, *args, **kwargs):  # noqa: ANN002, ANN003
                constructed.append(1)
                raise RuntimeError("测试探针：不应构造 HTTP 客户端")

        monkeypatch.setattr(reranker.httpx, "Client", _RecordingClient)

        documents = [Document(page_content=f"doc-{i}") for i in range(10)]
        result = reranker.rerank(f"查询-{uuid.uuid4().hex}", documents, top_k=3)

        assert not constructed, "RERANK_ENABLED=False 时不应构造 HTTP 客户端 —— 特性开关未生效"
        assert [d.page_content for d in result] == ["doc-0", "doc-1", "doc-2"], (
            "关闭重排后应原序截断返回前 top_k 条"
        )
