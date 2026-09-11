"""依赖健康探针单元测试。"""

import httpx
import pytest

from core.settings import settings
from service import health


def _mock_client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def _up_with_client(client) -> dict:
    """_probe_embedding / _probe_reranker 的替身（收一个 client 参数）。"""
    return {"status": "up", "latency_ms": 0.0}


async def _up_no_args() -> dict:
    """_probe_chromadb 的替身（无参数）。"""
    return {"status": "up", "latency_ms": 0.0}


class TestProbeHttp:
    @pytest.mark.asyncio
    async def test_2xx_is_up(self):
        async with _mock_client(lambda request: httpx.Response(200)) as client:
            result = await health._probe_http(client, "http://dep/health")
        assert result["status"] == "up"
        assert "latency_ms" in result

    @pytest.mark.asyncio
    async def test_404_is_up(self):
        """端点可达但无 /health 路由（如非 TEI 的 OpenAI 兼容服务）不应误报为故障。"""
        async with _mock_client(lambda request: httpx.Response(404)) as client:
            result = await health._probe_http(client, "http://dep/health")
        assert result["status"] == "up"

    @pytest.mark.asyncio
    async def test_401_is_up(self):
        async with _mock_client(lambda request: httpx.Response(401)) as client:
            result = await health._probe_http(client, "http://dep/health")
        assert result["status"] == "up"

    @pytest.mark.asyncio
    async def test_5xx_is_down(self):
        async with _mock_client(lambda request: httpx.Response(503)) as client:
            result = await health._probe_http(client, "http://dep/health")
        assert result["status"] == "down"
        assert result["error"] == "HTTP 503"

    @pytest.mark.asyncio
    async def test_connection_error_is_down(self):
        def boom(request):
            raise httpx.ConnectError("refused")

        async with _mock_client(boom) as client:
            result = await health._probe_http(client, "http://dep/health")
        assert result["status"] == "down"
        assert result["error"] == "ConnectError"


class TestProbeReranker:
    @pytest.mark.asyncio
    async def test_disabled_when_rerank_off(self, monkeypatch):
        monkeypatch.setattr(settings, "RERANK_ENABLED", False)
        async with _mock_client(lambda request: httpx.Response(500)) as client:
            result = await health._probe_reranker(client)
        assert result == {"status": "disabled"}

    @pytest.mark.asyncio
    async def test_probes_when_enabled(self, monkeypatch):
        monkeypatch.setattr(settings, "RERANK_ENABLED", True)
        async with _mock_client(lambda request: httpx.Response(200)) as client:
            result = await health._probe_reranker(client)
        assert result["status"] == "up"


class TestProbeLangsmith:
    def test_disabled_by_default(self):
        assert health._probe_langsmith() == {"status": "disabled"}

    def test_misconfigured_without_key(self, monkeypatch):
        monkeypatch.setattr(settings, "LANGCHAIN_TRACING_V2", True)
        monkeypatch.setattr(settings, "LANGCHAIN_API_KEY", None)
        assert health._probe_langsmith() == {
            "status": "misconfigured",
            "error": "缺少 LANGCHAIN_API_KEY",
        }

    def test_enabled_reports_project(self, monkeypatch):
        monkeypatch.setattr(settings, "LANGCHAIN_TRACING_V2", True)
        monkeypatch.setattr(settings, "LANGCHAIN_API_KEY", "lsv2-x")
        monkeypatch.setattr(settings, "LANGCHAIN_PROJECT", "edu-test")
        assert health._probe_langsmith() == {"status": "enabled", "project": "edu-test"}


class TestProbeChromaDb:
    @pytest.mark.asyncio
    async def test_http_mode_when_reachable(self, monkeypatch):
        monkeypatch.setattr(health, "_is_tcp_reachable", lambda host, port: True)
        result = await health._probe_chromadb()
        assert result["status"] == "up"
        assert result["mode"] == "http"

    @pytest.mark.asyncio
    async def test_falls_back_to_existing_persist_dir(self, monkeypatch, tmp_path):
        monkeypatch.setattr(health, "_is_tcp_reachable", lambda host, port: False)
        monkeypatch.setattr(settings, "CHROMA_PERSIST_DIR", str(tmp_path))
        result = await health._probe_chromadb()
        assert result["status"] == "up"
        assert result["mode"] == "persistent"

    @pytest.mark.asyncio
    async def test_down_when_nothing_available(self, monkeypatch, tmp_path):
        monkeypatch.setattr(health, "_is_tcp_reachable", lambda host, port: False)
        monkeypatch.setattr(settings, "CHROMA_PERSIST_DIR", str(tmp_path / "missing"))
        result = await health._probe_chromadb()
        assert result["status"] == "down"
        assert result["error"] == "持久化目录不存在"


class TestCollectHealth:
    @pytest.fixture(autouse=True)
    def _stub_probes(self, monkeypatch):
        """默认全部健康，逐个用例再按需覆盖。"""
        monkeypatch.setattr(health, "_probe_embedding", _up_with_client)
        monkeypatch.setattr(health, "_probe_reranker", _up_with_client)
        monkeypatch.setattr(health, "_probe_chromadb", _up_no_args)

    @pytest.mark.asyncio
    async def test_all_up(self, monkeypatch):
        monkeypatch.setattr(health, "_probe_langsmith", lambda: {"status": "disabled"})
        body = await health.collect_health()
        assert body["status"] == "ok"
        assert body["degraded"] == []
        assert set(body["dependencies"]) == {"embedding", "reranker", "chromadb", "langsmith"}

    @pytest.mark.asyncio
    async def test_reports_degraded_dependencies(self, monkeypatch):
        monkeypatch.setattr(health, "_probe_langsmith", lambda: {"status": "disabled"})

        async def down(client):
            return {"status": "down", "error": "ConnectError"}

        monkeypatch.setattr(health, "_probe_embedding", down)
        body = await health.collect_health()
        assert body["status"] == "degraded"
        assert body["degraded"] == ["embedding"]

    @pytest.mark.asyncio
    async def test_langsmith_misconfigured_is_not_degraded(self, monkeypatch):
        """追踪配置不完整不算依赖故障，不应拉低整体状态。"""
        monkeypatch.setattr(health, "_probe_langsmith", lambda: {"status": "misconfigured"})
        body = await health.collect_health()
        assert body["status"] == "ok"
