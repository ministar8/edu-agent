"""service.auth JWT 认证纯函数单测。

纯本地 I/O，不联网、不碰真数据库、不依赖外部服务。
通过 monkeypatch 设置 settings.JWT_SECRET，避免真实密钥泄露。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import jwt
import pytest
from pydantic import SecretStr

from service.auth import (
    AuthTokenError,
    AuthTokenExpiredError,
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


def _set_secret(monkeypatch: pytest.MonkeyPatch, secret: str = "test-secret-key") -> None:
    monkeypatch.setattr("service.auth.settings.JWT_SECRET", SecretStr(secret))


def test_create_and_decode_access_token_roundtrip(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_secret(monkeypatch)
    token = create_access_token(user_id=42, username="alice", role="student")
    payload = decode_access_token(token)
    assert payload["sub"] == "42"
    assert payload["username"] == "alice"
    assert payload["role"] == "student"
    assert "exp" in payload and "iat" in payload
    assert payload["exp"] > payload["iat"]


def test_create_access_token_expires_after_configured_hours(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_secret(monkeypatch)
    token = create_access_token(user_id=1, username="bob", role="teacher")
    payload = decode_access_token(token)
    # 默认 2 小时过期
    assert timedelta(seconds=payload["exp"] - payload["iat"]) == timedelta(hours=2)


def test_decode_expired_token_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_secret(monkeypatch)
    # 直接构造一个已过期的 JWT（使用与创建时相同的密钥，exp 设为过去）
    expired = jwt.encode(
        {
            "sub": "1",
            "username": "bob",
            "role": "student",
            "exp": datetime.now(UTC) - timedelta(hours=1),
            "iat": datetime.now(UTC) - timedelta(hours=3),
        },
        "test-secret-key",
        algorithm="HS256",
    )
    with pytest.raises(AuthTokenExpiredError):
        decode_access_token(expired)


def test_decode_invalid_token_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_secret(monkeypatch)
    with pytest.raises(AuthTokenError):
        decode_access_token("not.a.valid.token")


def test_decode_wrong_secret_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_secret(monkeypatch, secret="real-secret")
    # 用另一个密钥签发的 token，用真密钥解码应失败
    token = jwt.encode(
        {"sub": "1", "username": "bob", "role": "student"},
        "wrong-secret",
        algorithm="HS256",
    )
    with pytest.raises(AuthTokenError):
        decode_access_token(token)


def test_hash_password_produces_legacy_format() -> None:
    hashed = hash_password("secret123")
    assert hashed.startswith("pbkdf2_sha256$260000$")
    parts = hashed.split("$")
    assert len(parts) == 4  # algorithm$iterations$salt$digest
    assert len(parts[2]) == 32  # 16 字节 salt 的 hex


def test_verify_password_correct() -> None:
    hashed = hash_password("secret123")
    verified, needs_migration = verify_password("secret123", hashed)
    assert verified is True
    assert needs_migration is False


def test_verify_password_wrong() -> None:
    hashed = hash_password("secret123")
    verified, _ = verify_password("wrong-password", hashed)
    assert verified is False


def test_verify_password_legacy_hash_migration() -> None:
    # 旧格式：sha256(password + "edu-agent-salt")
    import hashlib

    legacy = hashlib.sha256(b"legacy123edu-agent-salt").hexdigest()
    verified, needs_migration = verify_password("legacy123", legacy)
    assert verified is True
    assert needs_migration is True
