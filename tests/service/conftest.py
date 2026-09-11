import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage
from langgraph.types import StateSnapshot

from service.service import app


@pytest.fixture
def test_client():
    """FastAPI 测试客户端（进入 lifespan，确保建表与 checkpointer 就绪）。"""
    with TestClient(app) as client:
        yield client


@pytest.fixture
def mock_agent():
    """可配置的假 agent，用于不触碰真实图的用例。"""
    agent_mock = AsyncMock()
    agent_mock.ainvoke = AsyncMock(
        return_value=[("values", {"messages": [AIMessage(content="Test response")]})]
    )
    agent_mock.aget_state = AsyncMock(
        return_value=StateSnapshot(
            values={},
            next=(),
            config={},
            metadata=None,
            created_at=None,
            parent_config=None,
            tasks=(),
            interrupts=(),
        )
    )
    # 需要读 checkpointer 的用例会显式覆盖；否则 AsyncMock 会自动造出一个看起来可用的属性
    agent_mock.checkpointer = None
    with patch("service.service.get_agent", Mock(return_value=agent_mock)):
        yield agent_mock


@pytest.fixture
def auth_user(test_client):
    """注册一个随机用户，返回 (Bearer 头, 用户 id)。

    edu-agent 的业务路由都挂了 Depends(get_current_user)，且 /api/threads
    只按 token 里的用户 id 过滤，因此测试必须拿到真实注册的用户 id。
    """
    username = f"test_{uuid.uuid4().hex[:8]}"
    resp = test_client.post(
        "/api/auth/register",
        json={"username": username, "password": "secret123"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    return SimpleNamespace(
        headers={"Authorization": f"Bearer {body['access_token']}"},
        user_id=body["user"]["id"],
    )
