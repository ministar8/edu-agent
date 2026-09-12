"""统一 API 错误体。

所有业务 HTTP 错误的 `detail` 为 `{"code": str, "message": str}`，
便于前端/SDK 按 code 分支，同时 message 可直接展示。
"""

from __future__ import annotations

from fastapi import HTTPException
from fastapi import status as http_status

# 稳定错误码（新增只加不改，避免客户端写死旧码）
CODE_UNKNOWN_AGENT = "unknown_agent"
CODE_THREAD_NOT_FOUND = "thread_not_found"
CODE_INVALID_CONFIG = "invalid_agent_config"
CODE_MODEL_UNAVAILABLE = "model_unavailable"
CODE_UNAUTHORIZED = "unauthorized"
CODE_FORBIDDEN = "forbidden"
CODE_BAD_REQUEST = "bad_request"
CODE_USERNAME_TAKEN = "username_taken"
CODE_INTERNAL = "internal_error"
CODE_GENERATE_FAILED = "generate_failed"
CODE_GRADE_FAILED = "grade_failed"
CODE_AUTH_CONFIG = "auth_config_error"


def http_error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})


def not_found(code: str, message: str) -> HTTPException:
    return http_error(http_status.HTTP_404_NOT_FOUND, code, message)


def bad_request(code: str, message: str) -> HTTPException:
    return http_error(http_status.HTTP_400_BAD_REQUEST, code, message)


def unauthorized(message: str = "未授权", code: str = CODE_UNAUTHORIZED) -> HTTPException:
    return http_error(http_status.HTTP_401_UNAUTHORIZED, code, message)


def forbidden(message: str = "禁止访问", code: str = CODE_FORBIDDEN) -> HTTPException:
    return http_error(http_status.HTTP_403_FORBIDDEN, code, message)


def internal_error(message: str = "服务内部错误", code: str = CODE_INTERNAL) -> HTTPException:
    return http_error(http_status.HTTP_500_INTERNAL_SERVER_ERROR, code, message)
