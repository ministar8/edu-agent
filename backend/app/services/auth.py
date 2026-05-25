from __future__ import annotations

import hmac
import hashlib
import os
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import HTTPException, status

from app.config import settings

JWT_SECRET = settings.JWT_SECRET
if not JWT_SECRET:
    raise RuntimeError("JWT_SECRET must be set in .env or environment variables")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_HOURS = 2
PASSWORD_ALGORITHM = "pbkdf2_sha256"
PASSWORD_ITERATIONS = 260_000
PASSWORD_SALT_BYTES = 16


def hash_password(password: str) -> str:
    salt = os.urandom(PASSWORD_SALT_BYTES).hex()
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode(),
        bytes.fromhex(salt),
        PASSWORD_ITERATIONS,
    ).hex()
    return f"{PASSWORD_ALGORITHM}${PASSWORD_ITERATIONS}${salt}${digest}"


def is_legacy_hash(hashed: str) -> bool:
    """判断是否为旧版 SHA256 哈希（需迁移）"""
    return not hashed.startswith(f"{PASSWORD_ALGORITHM}$")


def verify_password(plain: str, hashed: str) -> tuple[bool, bool]:
    """验证密码

    Returns:
        (verified, needs_migration): 验证是否通过 + 是否需要迁移到新哈希
    """
    if not is_legacy_hash(hashed):
        try:
            _, iterations, salt, expected = hashed.split("$", 3)
            digest = hashlib.pbkdf2_hmac(
                "sha256",
                plain.encode(),
                bytes.fromhex(salt),
                int(iterations),
            ).hex()
            return hmac.compare_digest(digest, expected), False
        except (ValueError, TypeError):
            return False, False

    legacy = hashlib.sha256(f"{plain}edu-agent-salt".encode()).hexdigest()
    return hmac.compare_digest(legacy, hashed), True


def create_access_token(user_id: int, username: str, role: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "username": username,
        "role": role,
        "exp": now + timedelta(hours=JWT_EXPIRE_HOURS),
        "iat": now,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> dict:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token 已过期") from exc
    except jwt.InvalidTokenError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="无效 Token") from exc
