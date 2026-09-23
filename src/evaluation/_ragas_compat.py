"""ragas 0.4.3 的导入兼容层（上游 bug 的受控绕行）。

## 问题

`ragas 0.4.3`（截至 2026-09-23 的**最新版**）在 `ragas/llms/base.py:12` 有一句
**无守卫的顶层 import**：

```python
from langchain_community.chat_models.vertexai import ChatVertexAI
```

但 `langchain-community >= 0.4` 已经把 `chat_models/vertexai.py` 移除了
（该目录下只剩 `google_palm.py`）。于是 `import ragas` 直接抛：

    ModuleNotFoundError: No module named 'langchain_community.chat_models.vertexai'

**根因是 ragas 的打包缺陷**：它在 `METADATA` 里对 `langchain-community` **完全没有版本约束**
（`Requires-Dist: langchain-community`，无 `<`/`>=`），却依赖一个只在 `<0.4` 存在的模块。
本项目钉的是 `langchain-community ~=0.4.2`（生产依赖，不能为评测工具降级），
而 PyPI 上 ragas 最新就是 0.4.3 —— **既无升级路径，也不该为它降级核心依赖**。

## 绕行为什么安全

全包内 `ChatVertexAI` **只有两处**引用（已 grep 核实）：

1. 那句 import；
2. `MULTIPLE_COMPLETION_SUPPORTED` 列表 —— 仅用于 `is_multiple_completion_supported()`
   里的 `isinstance(llm, llm_type)` 判断。

所以给它一个**占位类**即可：我们从不使用 VertexAI，`isinstance(我们的 LLM, 占位类)`
恒为 `False`，**正是正确结果**。

★ 占位类**故意在实例化时抛错**：万一将来真有人想用 VertexAI，应当拿到一条明确的
「这里是个桩，请装真正的 langchain-google-vertexai」错误，而不是一个能构造却行为诡异的空对象。
—— 桩必须让人**知道**它是桩。
"""

from __future__ import annotations

import logging
import sys
import types

logger = logging.getLogger(__name__)

_MISSING_MODULE = "langchain_community.chat_models.vertexai"
_MISSING_SYMBOL = "ChatVertexAI"

_installed = False


def ensure_ragas_importable() -> bool:
    """让 `import ragas` 能跑通。返回 True 表示打了兼容桩。

    幂等：重复调用只生效一次。**必须在任何 `import ragas` 之前调用。**
    """
    global _installed
    if _installed:
        return False

    # 先看真实模块在不在；在就什么都不做（将来 langchain-community 恢复了也自动适配）
    try:
        import importlib

        importlib.import_module(_MISSING_MODULE)
        _installed = True
        return False
    except ModuleNotFoundError:
        pass
    except Exception:
        # 模块存在但自身导入失败（依赖缺失等）—— 那是另一类问题，不该被桩掩盖
        logger.warning("模块 %s 存在但导入失败，不用桩掩盖", _MISSING_MODULE, exc_info=True)
        _installed = True
        return False

    class ChatVertexAI:  # noqa: N801 — 名字必须与被替代的类一致
        """占位类：仅为满足 ragas 的 `isinstance` 列表，不具备任何真实能力。"""

        def __init__(self, *args: object, **kwargs: object) -> None:
            raise NotImplementedError(
                "这是 edu-agent 为绕开 ragas 0.4.3 导入缺陷而打的**占位类**，"
                "不是真正的 VertexAI。若确实需要 VertexAI，请安装 "
                "`langchain-google-vertexai` 并改用其官方类。"
            )

    stub = types.ModuleType(_MISSING_MODULE)
    stub.__doc__ = "占位模块，见 evaluation._ragas_compat 的说明。"
    stub.ChatVertexAI = ChatVertexAI  # type: ignore[attr-defined]
    sys.modules[_MISSING_MODULE] = stub
    # 让 `from langchain_community.chat_models.vertexai import ChatVertexAI` 生效，
    # 还要把中间包的属性挂上（否则 import 机制找不到子模块）
    try:
        import langchain_community.chat_models as _cm

        _cm.vertexai = stub  # type: ignore[attr-defined]
    except Exception:
        logger.debug("无法把桩挂到 langchain_community.chat_models 上", exc_info=True)

    logger.warning(
        "已为 ragas 打兼容桩：%s.%s（langchain-community>=0.4 已移除该模块，"
        "而 ragas 0.4.3 未声明版本约束）",
        _MISSING_MODULE,
        _MISSING_SYMBOL,
    )
    _installed = True
    return True
