"""Typed HTTP client for the edu-agent service.

Paths are rooted at ``/api``; auth is JWT (login/register or an injected token).
Mirrors agent-service-toolkit's AgentClient surface, adapted for this service.
"""

from __future__ import annotations

import json
import os
from collections.abc import AsyncGenerator, Generator
from typing import Any

import httpx

from schema import (
    ChatHistory,
    ChatHistoryInput,
    ChatMessage,
    GradeRequest,
    GradeResponse,
    LoginRequest,
    QuestionRequest,
    QuestionResponse,
    RegisterRequest,
    ServiceMetadata,
    StreamInput,
    TokenResponse,
    UserInput,
    UserResponse,
    UserThreads,
    UserThreadsInput,
)

DEFAULT_BASE_URL = "http://127.0.0.1:8000"


class AgentClientError(Exception):
    pass


class AgentClient:
    """Client for interacting with the edu-agent service."""

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        agent: str | None = None,
        timeout: float | None = None,
        get_info: bool = True,
        token: str | None = None,
    ) -> None:
        """
        Args:
            base_url: Service origin (no trailing path). API lives under ``/api``.
            agent: Default agent key; filled from ``/info`` when omitted.
            timeout: Optional httpx timeout seconds.
            get_info: Fetch ``/api/info`` on init (needs a reachable service).
            token: JWT bearer token. Falls back to env ``AGENT_TOKEN``.
        """
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.token = token if token is not None else os.getenv("AGENT_TOKEN")
        self.info: ServiceMetadata | None = None
        self.user: UserResponse | None = None
        self.agent: str | None = None
        if get_info:
            self.retrieve_info()
        if agent:
            self.update_agent(agent)

    @property
    def api_root(self) -> str:
        return f"{self.base_url}/api"

    @property
    def _headers(self) -> dict[str, str]:
        if not self.token:
            return {}
        return {"Authorization": f"Bearer {self.token}"}

    def set_token(self, token: str | None) -> None:
        """Set or clear the JWT used for subsequent requests."""
        self.token = token

    def _agent_url(self, suffix: str, agent: str | None = None) -> str:
        """Build ``/api/{agent}/suffix`` when an agent is selected, else ``/api/suffix``."""
        agent_id = agent if agent is not None else self.agent
        if agent_id:
            return f"{self.api_root}/{agent_id}/{suffix.lstrip('/')}"
        return f"{self.api_root}/{suffix.lstrip('/')}"

    def _raise_http(self, response: httpx.Response, context: str) -> None:
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            detail = ""
            code = ""
            try:
                body = response.json()
                if isinstance(body, dict):
                    raw = body.get("detail", "")
                    if isinstance(raw, dict):
                        code = str(raw.get("code") or "")
                        detail = str(raw.get("message") or raw)
                    else:
                        detail = str(raw)
            except Exception:
                detail = response.text
            message = f"{context}: {response.status_code}"
            if code:
                message = f"{message} [{code}]"
            if detail:
                message = f"{message} {detail}"
            raise AgentClientError(message) from e
        except httpx.HTTPError as e:
            raise AgentClientError(f"{context}: {e}") from e

    # ── Auth ─────────────────────────────────────────────────────────────

    def register(self, username: str, password: str, display_name: str = "") -> TokenResponse:
        request = RegisterRequest(username=username, password=password, display_name=display_name)
        try:
            response = httpx.post(
                f"{self.api_root}/auth/register",
                json=request.model_dump(),
                timeout=self.timeout,
            )
        except httpx.HTTPError as e:
            raise AgentClientError(f"Error registering: {e}") from e
        self._raise_http(response, "Error registering")
        data = TokenResponse.model_validate(response.json())
        self.token = data.access_token
        self.user = data.user
        return data

    def login(self, username: str, password: str) -> TokenResponse:
        request = LoginRequest(username=username, password=password)
        try:
            response = httpx.post(
                f"{self.api_root}/auth/login",
                json=request.model_dump(),
                timeout=self.timeout,
            )
        except httpx.HTTPError as e:
            raise AgentClientError(f"Error logging in: {e}") from e
        self._raise_http(response, "Error logging in")
        data = TokenResponse.model_validate(response.json())
        self.token = data.access_token
        self.user = data.user
        return data

    def logout(self) -> None:
        if not self.token:
            self.user = None
            return
        try:
            response = httpx.post(
                f"{self.api_root}/auth/logout",
                headers=self._headers,
                timeout=self.timeout,
            )
        except httpx.HTTPError as e:
            raise AgentClientError(f"Error logging out: {e}") from e
        # 204 or 200 both fine; 401 means token already invalid — still clear locally
        if response.status_code not in (200, 204, 401):
            self._raise_http(response, "Error logging out")
        self.token = None
        self.user = None

    def me(self) -> UserResponse:
        try:
            response = httpx.get(
                f"{self.api_root}/auth/me",
                headers=self._headers,
                timeout=self.timeout,
            )
        except httpx.HTTPError as e:
            raise AgentClientError(f"Error fetching current user: {e}") from e
        self._raise_http(response, "Error fetching current user")
        self.user = UserResponse.model_validate(response.json())
        return self.user

    # ── Service metadata ─────────────────────────────────────────────────

    def retrieve_info(self) -> None:
        try:
            response = httpx.get(
                f"{self.api_root}/info",
                headers=self._headers,
                timeout=self.timeout,
            )
        except httpx.HTTPError as e:
            raise AgentClientError(f"Error getting service info: {e}") from e
        self._raise_http(response, "Error getting service info")
        self.info = ServiceMetadata.model_validate(response.json())
        if not self.agent or self.agent not in [a.key for a in self.info.agents]:
            self.agent = self.info.default_agent

    def update_agent(self, agent: str, verify: bool = True) -> None:
        if verify:
            if not self.info:
                self.retrieve_info()
            agent_keys = [a.key for a in self.info.agents]  # type: ignore[union-attr]
            if agent not in agent_keys:
                raise AgentClientError(
                    f"Agent {agent} not found in available agents: {', '.join(agent_keys)}"
                )
        self.agent = agent

    # ── Invoke / stream ──────────────────────────────────────────────────

    def _build_user_input(
        self,
        message: str,
        model: str | None,
        thread_id: str | None,
        user_id: str | None,
        agent_config: dict[str, Any] | None,
    ) -> UserInput:
        request = UserInput(message=message)
        if thread_id:
            request.thread_id = thread_id
        if model:
            request.model = model  # type: ignore[assignment]
        if agent_config:
            request.agent_config = agent_config
        if user_id:
            request.user_id = user_id
        return request

    def invoke(
        self,
        message: str,
        model: str | None = None,
        thread_id: str | None = None,
        user_id: str | None = None,
        agent_config: dict[str, Any] | None = None,
    ) -> ChatMessage:
        if not self.agent:
            raise AgentClientError("No agent selected. Use update_agent() to select an agent.")
        request = self._build_user_input(message, model, thread_id, user_id, agent_config)
        try:
            response = httpx.post(
                self._agent_url("invoke"),
                json=request.model_dump(),
                headers=self._headers,
                timeout=self.timeout,
            )
        except httpx.HTTPError as e:
            raise AgentClientError(f"Error: {e}") from e
        self._raise_http(response, "Error invoking agent")
        return ChatMessage.model_validate(response.json())

    async def ainvoke(
        self,
        message: str,
        model: str | None = None,
        thread_id: str | None = None,
        user_id: str | None = None,
        agent_config: dict[str, Any] | None = None,
    ) -> ChatMessage:
        if not self.agent:
            raise AgentClientError("No agent selected. Use update_agent() to select an agent.")
        request = self._build_user_input(message, model, thread_id, user_id, agent_config)
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    self._agent_url("invoke"),
                    json=request.model_dump(),
                    headers=self._headers,
                    timeout=self.timeout,
                )
            except httpx.HTTPError as e:
                raise AgentClientError(f"Error: {e}") from e
        self._raise_http(response, "Error invoking agent")
        return ChatMessage.model_validate(response.json())

    def _parse_stream_line(self, line: str) -> ChatMessage | str | None:
        line = line.strip()
        if line.startswith("data: "):
            data = line[6:]
            if data == "[DONE]":
                return None
            try:
                parsed = json.loads(data)
            except Exception as e:
                raise AgentClientError(f"Error JSON parsing message from server: {e}") from e
            match parsed.get("type"):
                case "message":
                    try:
                        return ChatMessage.model_validate(parsed["content"])
                    except Exception as e:
                        raise AgentClientError(f"Server returned invalid message: {e}") from e
                case "token":
                    return parsed["content"]
                case "error":
                    return ChatMessage(type="ai", content="Error: " + parsed["content"])
        return None

    def stream(
        self,
        message: str,
        model: str | None = None,
        thread_id: str | None = None,
        user_id: str | None = None,
        agent_config: dict[str, Any] | None = None,
        stream_tokens: bool = True,
    ) -> Generator[ChatMessage | str, None, None]:
        if not self.agent:
            raise AgentClientError("No agent selected. Use update_agent() to select an agent.")
        request = StreamInput(
            message=message,
            stream_tokens=stream_tokens,
            model=model,
            thread_id=thread_id,
            user_id=user_id,
            agent_config=agent_config or {},
        )
        try:
            with httpx.stream(
                "POST",
                self._agent_url("stream"),
                json=request.model_dump(),
                headers=self._headers,
                timeout=self.timeout,
            ) as response:
                self._raise_http(response, "Error streaming agent")
                for line in response.iter_lines():
                    if line.strip():
                        parsed = self._parse_stream_line(line)
                        if parsed is None:
                            break
                        yield parsed
        except httpx.HTTPError as e:
            raise AgentClientError(f"Error: {e}") from e

    async def astream(
        self,
        message: str,
        model: str | None = None,
        thread_id: str | None = None,
        user_id: str | None = None,
        agent_config: dict[str, Any] | None = None,
        stream_tokens: bool = True,
    ) -> AsyncGenerator[ChatMessage | str, None]:
        if not self.agent:
            raise AgentClientError("No agent selected. Use update_agent() to select an agent.")
        request = StreamInput(
            message=message,
            stream_tokens=stream_tokens,
            model=model,
            thread_id=thread_id,
            user_id=user_id,
            agent_config=agent_config or {},
        )
        async with httpx.AsyncClient() as client:
            try:
                async with client.stream(
                    "POST",
                    self._agent_url("stream"),
                    json=request.model_dump(),
                    headers=self._headers,
                    timeout=self.timeout,
                ) as response:
                    self._raise_http(response, "Error streaming agent")
                    async for line in response.aiter_lines():
                        if line.strip():
                            parsed = self._parse_stream_line(line)
                            if parsed is None:
                                break
                            if parsed != "":
                                yield parsed
            except httpx.HTTPError as e:
                raise AgentClientError(f"Error: {e}") from e

    # ── History / threads ────────────────────────────────────────────────

    def get_history(self, thread_id: str, agent: str | None = None) -> ChatHistory:
        request = ChatHistoryInput(thread_id=thread_id)
        try:
            response = httpx.post(
                self._agent_url("history", agent=agent),
                json=request.model_dump(),
                headers=self._headers,
                timeout=self.timeout,
            )
        except httpx.HTTPError as e:
            raise AgentClientError(f"Error: {e}") from e
        self._raise_http(response, "Error getting history")
        return ChatHistory.model_validate(response.json())

    def _user_threads_request(
        self, user_id: str, agent: str | None, limit: int
    ) -> tuple[str, dict[str, Any]]:
        return (
            self._agent_url("threads", agent=agent),
            UserThreadsInput(user_id=user_id, limit=limit).model_dump(),
        )

    def get_user_threads(
        self, user_id: str, agent: str | None = None, limit: int = 20
    ) -> UserThreads:
        url, params = self._user_threads_request(user_id, agent, limit)
        try:
            response = httpx.get(
                url,
                params=params,
                headers=self._headers,
                timeout=self.timeout,
            )
        except httpx.HTTPError as e:
            raise AgentClientError(f"Error: {e}") from e
        self._raise_http(response, "Error listing threads")
        return UserThreads.model_validate(response.json())

    async def aget_user_threads(
        self, user_id: str, agent: str | None = None, limit: int = 20
    ) -> UserThreads:
        url, params = self._user_threads_request(user_id, agent, limit)
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(
                    url,
                    params=params,
                    headers=self._headers,
                    timeout=self.timeout,
                )
            except httpx.HTTPError as e:
                raise AgentClientError(f"Error: {e}") from e
        self._raise_http(response, "Error listing threads")
        return UserThreads.model_validate(response.json())

    # ── Questions (domain) ───────────────────────────────────────────────

    def generate_questions(
        self,
        topic: str,
        count: int = 1,
        difficulty: str = "mixed",
    ) -> QuestionResponse:
        request = QuestionRequest(topic=topic, count=count, difficulty=difficulty)  # type: ignore[arg-type]
        try:
            response = httpx.post(
                f"{self.api_root}/questions/generate",
                json=request.model_dump(),
                headers=self._headers,
                timeout=self.timeout,
            )
        except httpx.HTTPError as e:
            raise AgentClientError(f"Error generating questions: {e}") from e
        self._raise_http(response, "Error generating questions")
        return QuestionResponse.model_validate(response.json())

    def grade_question(
        self,
        stem: str,
        user_answer: str,
        standard_answer: str = "",
    ) -> GradeResponse:
        request = GradeRequest(stem=stem, user_answer=user_answer, standard_answer=standard_answer)
        try:
            response = httpx.post(
                f"{self.api_root}/questions/grade",
                json=request.model_dump(),
                headers=self._headers,
                timeout=self.timeout,
            )
        except httpx.HTTPError as e:
            raise AgentClientError(f"Error grading question: {e}") from e
        self._raise_http(response, "Error grading question")
        return GradeResponse.model_validate(response.json())
