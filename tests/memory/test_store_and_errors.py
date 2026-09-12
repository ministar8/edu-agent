"""SQLite store 持久化与统一错误体。"""

from pathlib import Path

import pytest
from fastapi import HTTPException

from memory.sqlite import get_sqlite_store
from service.errors import CODE_UNKNOWN_AGENT, http_error, not_found


@pytest.mark.asyncio
async def test_sqlite_store_setup_and_put(tmp_path, monkeypatch):
    from core import settings as settings_singleton

    monkeypatch.setattr(settings_singleton, "SQLITE_STORE_PATH", str(tmp_path / "s.db"))
    async with get_sqlite_store() as store:
        await store.aput(("user", "1"), "profile", {"name": "t"})
        got = await store.aget(("user", "1"), "profile")
    assert got is not None
    assert got.value["name"] == "t"
    assert Path(tmp_path / "s.db").exists()


def test_http_error_shape():
    exc = not_found(CODE_UNKNOWN_AGENT, "Unknown agent: x")
    assert isinstance(exc, HTTPException)
    assert exc.status_code == 404
    assert exc.detail == {"code": "unknown_agent", "message": "Unknown agent: x"}


def test_http_error_custom_status():
    exc = http_error(500, "internal_error", "boom")
    assert exc.status_code == 500
    assert exc.detail["message"] == "boom"
