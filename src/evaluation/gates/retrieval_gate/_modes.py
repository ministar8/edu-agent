"""门禁路由口径：rerank 三态 × embedding 两态（embedding_mode / rerank_mode / …）。"""

from __future__ import annotations

import os

from ._constants import (
    DEFAULT_BASELINE_PATH,
    REAL_EMBED_BASELINE_PATH,
    REAL_EMBED_RERANK_BASELINE_PATH,
    REAL_EMBED_RERANK_DISABLED_BASELINE_PATH,
    RERANK_BASELINE_PATH,
    RERANK_DISABLED_BASELINE_PATH,
    _env_flag,
)

RERANK_MODES: tuple[str, ...] = ("off", "on", "disabled")


def _resolve_rerank_mode() -> tuple[str, str]:
    """解析 ``GATE_RERANK_MODE``；返回 ``(mode, error)``，``error`` 非空表示配置非法。

    非法值**不静默回退** —— 门禁最怕"看起来跑通了，其实跑的是另一条路由"。
    错误留给 ``main()`` 报出并返回退出码 2（配置错误，非指标退化）。
    """
    raw = os.environ.get("GATE_RERANK_MODE", "").strip().lower()
    if raw:
        if raw in RERANK_MODES:
            return raw, ""
        return "off", f"GATE_RERANK_MODE={raw!r} 非法 —— 可选值：{', '.join(RERANK_MODES)}"
    # 兼容旧写法：GATE_USE_RERANK=1 等价于 mode=on
    if _env_flag("GATE_USE_RERANK"):
        return "on", ""
    return "off", ""


GATE_RERANK_MODE, GATE_RERANK_MODE_ERROR = _resolve_rerank_mode()


GATE_USE_REAL_RERANK = _env_flag("GATE_USE_REAL_RERANK")


_MODE_SETTINGS: dict[str, tuple[bool, bool]] = {
    "off": (False, False),
    "on": (True, True),
    "disabled": (False, False),
}


GATE_USE_REAL_EMBEDDING = _env_flag("GATE_USE_REAL_EMBEDDING")


SUPPORTED_ROUTES: dict[tuple[str, str], str] = {
    ("fake", "off"): DEFAULT_BASELINE_PATH,
    ("fake", "on"): RERANK_BASELINE_PATH,
    ("fake", "disabled"): RERANK_DISABLED_BASELINE_PATH,
    ("real", "off"): REAL_EMBED_BASELINE_PATH,
    ("real", "on"): REAL_EMBED_RERANK_BASELINE_PATH,
    ("real", "disabled"): REAL_EMBED_RERANK_DISABLED_BASELINE_PATH,
}


def embedding_mode() -> str:
    """当前运行的 embedding 口径：``"real"`` | ``"fake"``。"""
    return "real" if GATE_USE_REAL_EMBEDDING else "fake"


def rerank_mode() -> str:
    """当前运行的 rerank 口径：``"off"`` | ``"on"`` | ``"disabled"``。"""
    return GATE_RERANK_MODE


def rerank_backend() -> str:
    """当前 rerank 实现：``"real"``（TEI）或 ``"fake"``（确定性本地打分）。"""
    return "real" if GATE_USE_REAL_RERANK else "fake"


def rerank_requested() -> bool:
    """检索链的 ``use_rerank`` 入参 —— 「调用方是否**要求**重排」。

    ``off`` → False；``on`` / ``disabled`` → True。
    注意它**不等于**「是否真的会重排」：``disabled`` 下调用方要求了，但部署开关
    （``settings.RERANK_ENABLED``）会在重排阶段把它短路掉。
    """
    return GATE_RERANK_MODE != "off"
