import uuid
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

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


def test_info_requires_auth():
    """未认证不应暴露部署结构（agent 清单 / 模型清单 / 默认模型）。"""
    with TestClient(app) as client:
        r = client.get("/api/info")
        assert r.status_code == 401


def test_info(auth_user, test_client):
    r = test_client.get("/api/info", headers=auth_user.headers)
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
    detail = r.json()["detail"]
    assert detail["code"] == "username_taken"
    assert detail["message"] == "用户名已存在"


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


class TestAgentIdRoutes:
    """/{agent_id}/… 与默认路径并存；未知 agent 应 404 而非 500。"""

    def test_unknown_agent_invoke_returns_404(self, test_client, auth_user):
        r = test_client.post(
            "/api/no-such-agent/invoke",
            json={"message": "hi"},
            headers=auth_user.headers,
        )
        assert r.status_code == 404
        detail = r.json()["detail"]
        assert detail["code"] == "unknown_agent"
        assert "Unknown agent" in detail["message"]

    def test_unknown_agent_stream_returns_404(self, test_client, auth_user):
        r = test_client.post(
            "/api/no-such-agent/stream",
            json={"message": "hi"},
            headers=auth_user.headers,
        )
        assert r.status_code == 404

    def test_unknown_agent_history_returns_404(self, test_client, auth_user):
        r = test_client.post(
            "/api/no-such-agent/history",
            json={"thread_id": "t-1"},
            headers=auth_user.headers,
        )
        assert r.status_code == 404

    def test_unknown_agent_threads_returns_404(self, test_client, auth_user):
        r = test_client.get(
            "/api/no-such-agent/threads",
            params={"user_id": auth_user.user_id},
            headers=auth_user.headers,
        )
        assert r.status_code == 404

    def test_default_path_still_works(self, test_client, auth_user):
        r = test_client.get(
            "/api/threads",
            params={"user_id": auth_user.user_id},
            headers=auth_user.headers,
        )
        assert r.status_code == 200
        assert "threads" in r.json()

    def test_explicit_default_agent_path(self, test_client, auth_user):
        r = test_client.get(
            "/api/edu-assistant/threads",
            params={"user_id": auth_user.user_id},
            headers=auth_user.headers,
        )
        assert r.status_code == 200

    def test_explicit_path_requires_auth(self, test_client):
        r = test_client.post("/api/edu-assistant/invoke", json={"message": "hi"})
        assert r.status_code == 401

    def test_openapi_lists_agent_id_operations(self, test_client):
        r = test_client.get("/openapi.json")
        assert r.status_code == 200
        ops = r.json()["paths"]
        assert "/api/{agent_id}/invoke" in ops
        assert "/api/{agent_id}/stream" in ops
        assert "/api/{agent_id}/history" in ops
        assert "/api/{agent_id}/threads" in ops
        # 默认路径仍保留
        assert "/api/invoke" in ops
        assert "/api/stream" in ops


class TestInvokeFinalMessageSelection:
    """P2-b：/invoke 应返回最后一条「用户可见」消息，而非盲取 messages[-1]。

    专家可能以空 content 或带 tool_calls 的中间步骤收尾；直接取末条会给前端
    一个空气泡。这里与 SSE 侧共用 _is_user_visible_message 判定口径。
    """

    def _invoke(self, test_client, auth_user, mock_agent, messages):
        mock_agent.ainvoke = AsyncMock(return_value=[("values", {"messages": messages})])
        return test_client.post(
            "/api/invoke",
            json={"message": "什么是快表？"},
            headers=auth_user.headers,
        )

    def test_blank_trailing_ai_falls_back_to_prior_visible(
        self, test_client, auth_user, mock_agent
    ):
        """末条是空 content AI → 回溯到上一条有内容的专家回答。"""
        r = self._invoke(
            test_client,
            auth_user,
            mock_agent,
            [
                HumanMessage(content="什么是快表？"),
                AIMessage(content="快表（TLB）是页表的高速缓存。", name="knowledge_agent"),
                AIMessage(content="", name="knowledge_agent"),
            ],
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["content"].strip() == "快表（TLB）是页表的高速缓存。"
        assert body["name"] == "knowledge_agent"

    def test_normal_trailing_ai_is_untouched(self, test_client, auth_user, mock_agent):
        """反例守卫：末条本身可见时，不得改动选取结果。"""
        r = self._invoke(
            test_client,
            auth_user,
            mock_agent,
            [
                HumanMessage(content="什么是快表？"),
                AIMessage(content="快表是 TLB。", name="knowledge_agent"),
            ],
        )
        assert r.status_code == 200, r.text
        assert r.json()["content"] == "快表是 TLB。"

    def test_tool_message_tail_is_skipped(self, test_client, auth_user, mock_agent):
        """末条是 ToolMessage（工具结果不是对话气泡）→ 回溯到专家回答。"""
        r = self._invoke(
            test_client,
            auth_user,
            mock_agent,
            [
                HumanMessage(content="什么是快表？"),
                AIMessage(content="快表是 TLB。", name="knowledge_agent"),
                ToolMessage(content="检索结果：...", tool_call_id="c1"),
            ],
        )
        assert r.status_code == 200, r.text
        assert r.json()["content"] == "快表是 TLB。"

    def test_all_invisible_falls_back_to_last(self, test_client, auth_user, mock_agent):
        """全部不可见时仍返回一条消息（不抛错、不返回 None）。"""
        r = self._invoke(
            test_client,
            auth_user,
            mock_agent,
            [AIMessage(content="", name="knowledge_agent")],
        )
        assert r.status_code == 200, r.text
        assert r.json()["type"] == "ai"


class TestRecursionLimitGuard:
    """图执行必须有显式上界：LangGraph 默认 recursion_limit=10007。

    不设置时，supervisor 若因模型异常陷入反复分派，会一直跑到上万步才终止
    （每一步至少一次 LLM 调用），表现为「请求长时间不返回 + 狂烧 token」。
    这里锁住「显式设置且值合理」这条契约。
    """

    def test_configured_limit_is_sane(self):
        from core import settings

        limit = settings.AGENT_RECURSION_LIMIT
        assert limit > 0
        # 需容纳「多轮工具调用 + 一次分派」的正常步数，又不至于放任长循环
        assert 20 <= limit <= 200, f"AGENT_RECURSION_LIMIT={limit} 不在合理区间"

    @pytest.mark.asyncio
    async def test_handle_input_attaches_recursion_limit(self):
        """_handle_input 产出的 config 必须带 recursion_limit。"""
        from schema import UserInput
        from service.service import _handle_input

        class _State:
            values: dict = {}
            metadata = None
            tasks: list = []

        class _Agent:
            async def aget_state(self, config=None):  # noqa: ARG002
                return _State()

        kwargs, _run_id = await _handle_input(
            UserInput(message="你好"), _Agent(), "edu-assistant", "user-1"
        )

        from core import settings

        assert kwargs["config"]["recursion_limit"] == settings.AGENT_RECURSION_LIMIT
