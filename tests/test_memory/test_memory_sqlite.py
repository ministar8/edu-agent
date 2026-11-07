"""memory.sqlite 数据库底层：SQLite checkpointer / store 初始化与目录自建。

纯本地 I/O，使用 pytest tmp_path，不碰真 Chroma，不联网、不碰真 Store。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core import settings
from memory import sqlite as mem_sqlite


def test_ensure_parent_dir_creates_missing_directory(tmp_path: Path) -> None:
    db_path = tmp_path / "sub" / "deep" / "checkpoints.db"
    assert not db_path.parent.exists()
    result = mem_sqlite._ensure_parent_dir(str(db_path))
    assert result == str(db_path)
    assert db_path.parent.exists()


@pytest.mark.asyncio
async def test_get_sqlite_saver_uses_tmp_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_path = tmp_path / "checkpoints.db"
    monkeypatch.setattr(settings, "SQLITE_DB_PATH", str(db_path))

    async with mem_sqlite.get_sqlite_saver() as saver:
        assert saver is not None
    assert db_path.exists()


@pytest.mark.asyncio
async def test_get_sqlite_store_uses_tmp_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    store_path = tmp_path / "store.db"
    monkeypatch.setattr(settings, "SQLITE_STORE_PATH", str(store_path))

    async with mem_sqlite.get_sqlite_store() as store:
        assert store is not None
    assert store_path.exists()


def test_store_index_config_disabled_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "MEMORY_STORE_VECTOR_ENABLED", False)
    assert mem_sqlite._store_index_config() is None
