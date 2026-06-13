from __future__ import annotations

import hashlib
import hmac
import logging
import os
from datetime import datetime, timedelta, timezone

import jwt

from app.config import settings

logger = logging.getLogger(__name__)

JWT_ALGORITHM = "HS256"
JWT_EXPIRE_HOURS = 2
PASSWORD_ALGORITHM = "pbkdf2_sha256"
PASSWORD_ITERATIONS = 260_000
PASSWORD_SALT_BYTES = 16


class AuthTokenError(ValueError):
    detail = "无效 Token"


class AuthTokenExpiredError(AuthTokenError):
    detail = "Token 已过期"


class AuthServiceConfigError(RuntimeError):
    detail = "认证服务未正确配置"


def _jwt_secret() -> str:
    if settings.JWT_SECRET:
        return settings.JWT_SECRET
    logger.error("JWT_SECRET is not configured")
    raise AuthServiceConfigError(AuthServiceConfigError.detail)

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
    return jwt.encode(payload, _jwt_secret(), algorithm=JWT_ALGORITHM)

def decode_access_token(token: str) -> dict:
    try:
        return jwt.decode(token, _jwt_secret(), algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError as exc:
        raise AuthTokenExpiredError(AuthTokenExpiredError.detail) from exc
    except jwt.InvalidTokenError as exc:
        raise AuthTokenError(AuthTokenError.detail) from exc
