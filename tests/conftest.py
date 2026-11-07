"""tests 根目录共享 fixture 与环境设置。

- 强制离线/假模型环境，单测不联网、不碰真 Store/Chroma、不碰真密钥；
- 提供跨测试文件的基础 fixture，避免各文件重复造轮子。
"""

from __future__ import annotations

import os

import pytest


@pytest.fixture(autouse=True, scope="session")
def _offline_env() -> None:
    """会话级：强制离线/假模型环境，单测不触碰任何真实网络或密钥。"""
    os.environ.setdefault("USE_FAKE_MODEL", "true")
    os.environ.setdefault("USE_FAKE_EMBEDDING", "true")
    os.environ.setdefault("USE_FAKE_RERANK", "true")
