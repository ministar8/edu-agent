import uuid

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from service.service import _check_thread_owner, app


def test_health():
    with TestClient(app) as client:
        r = client.get("/health")
        assert r.status_code == 200
        body = r.json()
        # 依赖可用与否都返回 200，整体状态体现在 status 字段
        assert body["status"] in ("ok", "degraded")
        assert set(body["dependencies"]) == {"embedding", "reranker", "chromadb", "langsmith"}
        assert set(body["degraded"]) <= set(body["dependencies"])


def test_info():
    with TestClient(app) as client:
        r = client.get("/api/info")
        assert r.status_code == 200
        body = r.json()
        assert body["default_agent"] == "edu-assistant"
        assert len(body["models"]) > 0


def test_static_index_served():
    with TestClient(app) as client:
        r = client.get("/")
        assert r.status_code == 200
        assert "EduAgent" in r.text


def test_stream_requires_auth():
    with TestClient(app) as client:
        r = client.post("/api/stream", json={"message": "hi"})
        assert r.status_code == 401


def test_register_login_me_flow():
    with TestClient(app) as client:
        username = f"test_{uuid.uuid4().hex[:8]}"
        r = client.post(
            "/api/auth/register",
            json={"username": username, "password": "secret123"},
        )
        assert r.status_code == 200
        token = r.json()["access_token"]
        assert token

        r2 = client.post(
            "/api/auth/login",
            json={"username": username, "password": "secret123"},
        )
        assert r2.status_code == 200

        r3 = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert r3.status_code == 200
        assert r3.json()["username"] == username


def test_duplicate_register_rejected():
    with TestClient(app) as client:
        username = f"dup_{uuid.uuid4().hex[:8]}"
        payload = {"username": username, "password": "secret123"}
        assert client.post("/api/auth/register", json=payload).status_code == 200
        assert client.post("/api/auth/register", json=payload).status_code == 400


def test_login_wrong_password_rejected():
    with TestClient(app) as client:
        r = client.post(
            "/api/auth/login",
            json={"username": "nonexistent_user", "password": "wrong"},
        )
        assert r.status_code == 401


def test_register_cannot_self_assign_admin_role():
    """公开注册不接受客户端指定角色，一律建为 student（防自助提权）。"""
    with TestClient(app) as client:
        username = f"priv_{uuid.uuid4().hex[:8]}"
        r = client.post(
            "/api/auth/register",
            json={"username": username, "password": "secret123", "role": "admin"},
        )
        assert r.status_code == 200
        assert r.json()["user"]["role"] == "student"

        me = client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {r.json()['access_token']}"},
        )
        assert me.json()["role"] == "student"


def test_register_concurrent_duplicate_returns_400_not_500(monkeypatch):
    """并发注册同名用户：唯一索引兜底应转成 400，而不是 500。"""
    import service.auth as auth_mod
    from db import SessionLocal, User

    username = f"race_{uuid.uuid4().hex[:8]}"
    original_hash = auth_mod.hash_password

    def hash_then_sneak(password: str) -> str:
        # 模拟并发写入者：在本次 commit 之前，用独立会话抢先插入同名用户，
        # 使后面的 db.commit() 触发唯一约束冲突（绕过 register 的前置存在性检查）
        with SessionLocal() as other:
            other.add(User(username=username, hashed_password="x", display_name="", role="student"))
            other.commit()
        return original_hash(password)

    monkeypatch.setattr(auth_mod, "hash_password", hash_then_sneak)

    with TestClient(app) as client:
        r = client.post(
            "/api/auth/register",
            json={"username": username, "password": "secret123"},
        )

    assert r.status_code == 400
    assert r.json()["detail"] == "用户名已存在"


class TestCheckThreadOwner:
    """thread_id 由客户端提供，等同 bearer capability，必须校验归属。"""

    def test_allows_new_thread_without_metadata(self):
        _check_thread_owner(None, "1", "edu-assistant")  # 不应抛异常

    def test_allows_owner(self):
        _check_thread_owner({"user_id": "1", "agent_id": "edu-assistant"}, "1", "edu-assistant")

    def test_rejects_other_user(self):
        with pytest.raises(HTTPException) as exc:
            _check_thread_owner({"user_id": "2", "agent_id": "edu-assistant"}, "1", "edu-assistant")
        assert exc.value.status_code == 404

    def test_rejects_other_agent(self):
        with pytest.raises(HTTPException) as exc:
            _check_thread_owner({"user_id": "1", "agent_id": "other"}, "1", "edu-assistant")
        assert exc.value.status_code == 404
