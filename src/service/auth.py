"""JWT 认证：密码哈希、Token 签发/校验，以及注册/登录/me/logout 路由。"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
from datetime import UTC, datetime, timedelta
from typing import cast

import jwt
from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Response, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from core.settings import settings
from db import User, get_db
from schema import LoginRequest, RegisterRequest, TokenResponse, UserResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

JWT_ALGORITHM = "HS256"
JWT_EXPIRE_HOURS = 2
PASSWORD_ALGORITHM = "pbkdf2_sha256"
PASSWORD_ITERATIONS = 260_000
PASSWORD_SALT_BYTES = 16
AUTH_COOKIE_NAME = "edu_agent_token"


class AuthTokenError(ValueError):
    detail = "无效 Token"


class AuthTokenExpiredError(AuthTokenError):
    detail = "Token 已过期"


class AuthServiceConfigError(RuntimeError):
    detail = "认证服务未正确配置"


def _jwt_secret() -> str:
    if settings.JWT_SECRET:
        return settings.JWT_SECRET.get_secret_value()
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


def _is_legacy_hash(hashed: str) -> bool:
    return not hashed.startswith(f"{PASSWORD_ALGORITHM}$")


def verify_password(plain: str, hashed: str) -> tuple[bool, bool]:
    """验证密码，返回 (verified, needs_migration)。"""
    if not _is_legacy_hash(hashed):
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
    now = datetime.now(UTC)
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


def _set_auth_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        AUTH_COOKIE_NAME,
        token,
        max_age=JWT_EXPIRE_HOURS * 60 * 60,
        httponly=True,
        secure=settings.AUTH_COOKIE_SECURE,
        samesite=settings.AUTH_COOKIE_SAMESITE,
        path="/",
    )


def _clear_auth_cookie(response: Response) -> None:
    response.delete_cookie(
        AUTH_COOKIE_NAME,
        path="/",
        secure=settings.AUTH_COOKIE_SECURE,
        samesite=settings.AUTH_COOKIE_SAMESITE,
    )


def _issue_access_token(user: User) -> str:
    try:
        return create_access_token(
            cast(int, user.id), cast(str, user.username), cast(str, user.role)
        )
    except AuthServiceConfigError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=exc.detail
        ) from exc


def get_current_user(
    authorization: str = Header(""),
    access_token: str | None = Cookie(default=None, alias=AUTH_COOKIE_NAME),
    db: Session = Depends(get_db),
) -> User:
    """从 JWT 中解析当前用户（支持 Bearer 头或 Cookie）。

    刻意用同步 def：内部是阻塞的 SQLAlchemy 调用，FastAPI 会把同步依赖放进线程池执行，
    避免阻塞事件循环。
    """
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        token = access_token or ""
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="无效 Token")
    try:
        payload = decode_access_token(token)
    except AuthTokenError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=exc.detail) from exc
    try:
        user_id = int(cast(str, payload.get("sub")))
    except (TypeError, ValueError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="无效 Token") from None
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户不存在")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="账号已禁用")
    return user


def _user_response(user: User) -> UserResponse:
    return UserResponse(
        id=cast(int, user.id),
        username=cast(str, user.username),
        display_name=cast(str, user.display_name),
        role=cast(str, user.role),
        created_at=cast("datetime | None", user.created_at),
    )


@router.post("/register", response_model=TokenResponse)
def register(req: RegisterRequest, response: Response, db: Session = Depends(get_db)):
    """用户注册（同步 def，DB 调用走线程池）。"""
    existing = db.query(User).filter(User.username == req.username).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="用户名已存在")

    # 公开注册一律为学生；teacher/admin 只能由既有管理员授予，避免自助提权
    user = User(
        username=req.username,
        hashed_password=hash_password(req.password),
        display_name=req.display_name or req.username,
        role="student",
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        # 并发注册同名用户时靠唯一索引兜底，返回 400 而非 500
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="用户名已存在"
        ) from None
    db.refresh(user)

    token = _issue_access_token(user)
    _set_auth_cookie(response, token)
    logger.info("User registered: %s (role=%s)", user.username, user.role)
    return TokenResponse(access_token=token, user=_user_response(user))


@router.post("/login", response_model=TokenResponse)
def login(req: LoginRequest, response: Response, db: Session = Depends(get_db)):
    """用户登录（同步 def，PBKDF2 与 DB 调用走线程池）。"""
    user = db.query(User).filter(User.username == req.username).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误")

    verified, needs_migration = verify_password(req.password, cast(str, user.hashed_password))
    if not verified:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="账号已禁用")

    if needs_migration:
        user.hashed_password = hash_password(req.password)
        logger.info("Password migrated for user: %s", user.username)

    user.last_login = datetime.now(UTC)
    db.commit()

    token = _issue_access_token(user)
    _set_auth_cookie(response, token)
    logger.info("User logged in: %s", user.username)
    return TokenResponse(access_token=token, user=_user_response(user))


@router.get("/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user)):
    """获取当前用户信息。"""
    return _user_response(current_user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response):
    _clear_auth_cookie(response)
    return None
