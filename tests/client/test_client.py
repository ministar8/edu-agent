"""AgentClient 单元测试：路径前缀、JWT 头、SSE 解析与领域端点。"""

from unittest.mock import AsyncMock, patch

import pytest
from httpx import Request, Response

from client import AgentClient, AgentClientError
from schema import (
    ChatMessage,
    GradeResponse,
    QuestionResponse,
    ServiceMetadata,
    TokenResponse,
    UserThreads,
)


def _response(status: int, url: str, json_body: dict | None = None) -> Response:
    return Response(status, json=json_body, request=Request("POST", url))


class TestInitAndHeaders:
    def test_defaults(self):
        client = AgentClient(get_info=False)
        assert client.base_url == "http://127.0.0.1:8000"
        assert client.api_root == "http://127.0.0.1:8000/api"
        assert client.token is None
        assert client._headers == {}

    def test_token_header(self):
        client = AgentClient(get_info=False, token="jwt-abc")
        assert client._headers == {"Authorization": "Bearer jwt-abc"}

    def test_env_token(self, monkeypatch):
        monkeypatch.setenv("AGENT_TOKEN", "env-token")
        client = AgentClient(get_info=False)
        assert client.token == "env-token"

    def test_set_token_clears(self):
        client = AgentClient(get_info=False, token="t")
        client.set_token(None)
        assert client._headers == {}


class TestAuth:
    def test_register_sets_token(self, agent_client):
        body = {
            "access_token": "tok",
            "token_type": "bearer",
            "user": {
                "id": 1,
                "username": "u1",
                "display_name": "",
                "role": "student",
            },
        }
        mock = _response(200, "http://test/api/auth/register", body)
        with patch("httpx.post", return_value=mock) as post:
            result = agent_client.register("user1", "secret12")
        assert isinstance(result, TokenResponse)
        assert agent_client.token == "tok"
        assert post.call_args.args[0] == "http://test/api/auth/register"

    def test_login_sets_token_and_user(self, agent_client):
        body = {
            "access_token": "tok2",
            "token_type": "bearer",
            "user": {
                "id": 2,
                "username": "u2",
                "display_name": "U",
                "role": "student",
            },
        }
        mock = _response(200, "http://test/api/auth/login", body)
        with patch("httpx.post", return_value=mock):
            agent_client.login("u2", "secret12")
        assert agent_client.token == "tok2"
        assert agent_client.user is not None
        assert agent_client.user.username == "u2"

    def test_login_failure_raises(self, agent_client):
        mock = _response(401, "http://test/api/auth/login", {"detail": "密码错误"})
        with patch("httpx.post", return_value=mock):
            with pytest.raises(AgentClientError, match="401"):
                agent_client.login("u", "bad")

    def test_me(self, agent_client):
        agent_client.set_token("tok")
        body = {"id": 3, "username": "u3", "display_name": "", "role": "student"}
        mock = Response(200, json=body, request=Request("GET", "http://test/api/auth/me"))
        with patch("httpx.get", return_value=mock) as get:
            user = agent_client.me()
        assert user.username == "u3"
        assert get.call_args.kwargs["headers"]["Authorization"] == "Bearer tok"

    def test_logout_clears_local_token(self, agent_client):
        agent_client.set_token("tok")
        mock = Response(204, request=Request("POST", "http://test/api/auth/logout"))
        with patch("httpx.post", return_value=mock):
            agent_client.logout()
        assert agent_client.token is None


class TestInfoAndAgent:
    def test_retrieve_info_uses_api_prefix(self):
        body = {
            "agents": [{"key": "edu-assistant", "description": "d"}],
            "models": ["dashscope:qwen3.8-max"],
            "default_agent": "edu-assistant",
            "default_model": "dashscope:qwen3.8-max",
        }
        mock = Response(200, json=body, request=Request("GET", "http://test/api/info"))
        # /info 需要认证，构造期拉取必须带 token
        with patch("httpx.get", return_value=mock) as get:
            client = AgentClient(base_url="http://test", get_info=True, token="tok")
        assert get.call_args.args[0] == "http://test/api/info"
        assert get.call_args.kwargs["headers"]["Authorization"] == "Bearer tok"
        assert client.agent == "edu-assistant"
        assert isinstance(client.info, ServiceMetadata)

    def test_info_not_fetched_without_token(self):
        """`/info` 需要认证：构造期无凭证时**不应发请求**，留待登录后补。"""
        mock = Response(200, json={}, request=Request("GET", "http://test/api/info"))
        with patch("httpx.get", return_value=mock) as get:
            client = AgentClient(base_url="http://test", get_info=True)
        assert client.info is None
        assert not get.called

    def test_login_backfills_info(self):
        """登录成功后自动补齐 `/info`。

        这是 `/info` 加鉴权后仍能保持 `AgentClient(base_url=...)` → `login()`
        老用法的关键：构造期拉不到，登录后补上。
        """
        info_body = {
            "agents": [{"key": "edu-assistant", "description": "d"}],
            "models": ["dashscope:qwen3.8-max"],
            "default_agent": "edu-assistant",
            "default_model": "dashscope:qwen3.8-max",
        }
        token_body = {
            "access_token": "tok",
            "token_type": "bearer",
            "user": {"id": 1, "username": "u", "display_name": "", "role": "student"},
        }
        info_mock = Response(200, json=info_body, request=Request("GET", "http://test/api/info"))
        with (
            patch("httpx.get", return_value=info_mock) as get,
            patch(
                "httpx.post", return_value=_response(200, "http://test/api/auth/login", token_body)
            ),
        ):
            client = AgentClient(base_url="http://test", get_info=True)
            assert client.info is None
            assert not get.called
            client.login("u", "p")
        assert isinstance(client.info, ServiceMetadata)
        assert client.agent == "edu-assistant"

    def test_update_agent_unknown_raises(self, agent_client):
        agent_client.info = ServiceMetadata(
            agents=[{"key": "edu-assistant", "description": "d"}],
            models=["m"],
            default_agent="edu-assistant",
            default_model="m",
        )
        with pytest.raises(AgentClientError, match="not found"):
            agent_client.update_agent("nope", verify=True)


class TestInvoke:
    def test_invoke_hits_agent_path(self, agent_client):
        mock = _response(
            200,
            "http://test/api/edu-assistant/invoke",
            {"type": "ai", "content": "ok"},
        )
        with patch("httpx.post", return_value=mock) as post:
            msg = agent_client.invoke("hi", thread_id="t1", model="dashscope:qwen3.8-max")
        assert isinstance(msg, ChatMessage)
        assert msg.content == "ok"
        url = post.call_args.args[0]
        assert url == "http://test/api/edu-assistant/invoke"
        assert post.call_args.kwargs["json"]["thread_id"] == "t1"

    def test_invoke_requires_agent(self):
        client = AgentClient(get_info=False)
        with pytest.raises(AgentClientError, match="No agent"):
            client.invoke("hi")

    @pytest.mark.asyncio
    async def test_ainvoke(self, agent_client):
        mock = _response(
            200,
            "http://test/api/edu-assistant/invoke",
            {"type": "ai", "content": "async-ok"},
        )
        with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=mock)):
            msg = await agent_client.ainvoke("hi")
        assert msg.content == "async-ok"


class TestStreamParse:
    def test_parse_message_token_done_error(self, agent_client):
        line_msg = 'data: {"type": "message", "content": {"type": "ai", "content": "hello"}}'
        assert isinstance(agent_client._parse_stream_line(line_msg), ChatMessage)
        line_tok = 'data: {"type": "token", "content": "he"}'
        assert agent_client._parse_stream_line(line_tok) == "he"
        assert agent_client._parse_stream_line("data: [DONE]") is None
        line_err = 'data: {"type": "error", "content": "boom"}'
        parsed = agent_client._parse_stream_line(line_err)
        assert isinstance(parsed, ChatMessage)
        assert "boom" in parsed.content
        assert agent_client._parse_stream_line("") is None


class TestHistoryThreads:
    def test_get_history_path(self, agent_client):
        mock = _response(
            200,
            "http://test/api/edu-assistant/history",
            {"messages": []},
        )
        with patch("httpx.post", return_value=mock) as post:
            history = agent_client.get_history("t-1")
        assert post.call_args.args[0] == "http://test/api/edu-assistant/history"
        assert history.messages == []

    def test_get_user_threads_params(self, agent_client):
        mock = Response(
            200,
            json={"threads": []},
            request=Request("GET", "http://test/api/edu-assistant/threads"),
        )
        with patch("httpx.get", return_value=mock) as get:
            threads = agent_client.get_user_threads("7", limit=5)
        assert isinstance(threads, UserThreads)
        assert get.call_args.args[0] == "http://test/api/edu-assistant/threads"
        assert get.call_args.kwargs["params"]["user_id"] == "7"
        assert get.call_args.kwargs["params"]["limit"] == 5


class TestQuestions:
    def test_generate_questions(self, agent_client):
        body = {
            "questions": [
                {
                    "question_type": "choice",
                    "difficulty": "basic",
                    "stem": "S",
                    "standard_answer": "A",
                    "explanation": "E",
                }
            ],
            "batch_id": "b1",
        }
        mock = _response(200, "http://test/api/questions/generate", body)
        with patch("httpx.post", return_value=mock) as post:
            result = agent_client.generate_questions("死锁", count=1, difficulty="basic")
        assert isinstance(result, QuestionResponse)
        assert result.questions[0].stem == "S"
        assert post.call_args.args[0] == "http://test/api/questions/generate"

    def test_grade_question(self, agent_client):
        body = {"score": 8.5, "feedback": "还行", "error_analysis": "概念偏差"}
        mock = _response(200, "http://test/api/questions/grade", body)
        with patch("httpx.post", return_value=mock) as post:
            result = agent_client.grade_question("题干", "作答", "标答")
        assert isinstance(result, GradeResponse)
        assert result.score == 8.5
        assert post.call_args.args[0] == "http://test/api/questions/grade"

    def test_error_includes_detail(self, agent_client):
        mock = _response(400, "http://test/api/questions/generate", {"detail": "topic 过长"})
        with patch("httpx.post", return_value=mock):
            with pytest.raises(AgentClientError, match="topic"):
                agent_client.generate_questions("死锁")
