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
- 第二层 `TestCriticalSettingsReachRuntimeObjects`：对声明了安全语义的配置，
  实测它是否真的进入运行时对象（不是「代码里有引用」就算数）。
- 第三层 `TestGuardSettingsAreNotSilentlyReverted`：把关键安全项的**有效取值**
  也钉死，防止被改回「看起来一样但不生效」的状态。
"""

from __future__ import annotations

import re
from pathlib import Path

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


class TestCriticalSettingsReachRuntimeObjects:
    """第二层：关键配置必须真的进入运行时对象，而非只是「代码里提到了」。"""

    @pytest.mark.asyncio
    async def test_recursion_limit_reaches_runnable_config(self):
        """安全上界必须写进 `RunnableConfig.recursion_limit`。

        这是本项目踩过的坑：字段可以存在、甚至被别处引用，但真正决定图执行上界的
        是传给 `ainvoke` 的 config。不写进去，LangGraph 会用默认值 10007。
        """
        from core import settings
        from schema import UserInput
        from service.service import _handle_input

        class _State:
            values: dict = {}
            metadata = None
            tasks: list = []

        class _Agent:
            async def aget_state(self, config=None):  # noqa: ARG002
                return _State()

        kwargs, _ = await _handle_input(
            UserInput(message="你好"), _Agent(), "edu-assistant", "user-1"
        )

        config = kwargs["config"]
        assert config.get("recursion_limit") == settings.AGENT_RECURSION_LIMIT, (
            f"config.recursion_limit={config.get('recursion_limit')!r} "
            f"与 settings.AGENT_RECURSION_LIMIT={settings.AGENT_RECURSION_LIMIT!r} 不一致；"
            "上界未接线，异常循环将跑到 LangGraph 默认值。"
        )


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
