import os

from core.settings import DatabaseType, Settings, settings


def test_default_model_set():
    # 形如 <gateway>:<model_id>，构造期必定推导出来
    assert settings.DEFAULT_MODEL
    assert ":" in settings.DEFAULT_MODEL


def test_available_models_nonempty():
    assert len(settings.AVAILABLE_MODELS) > 0


def test_default_model_in_available():
    assert settings.DEFAULT_MODEL in settings.AVAILABLE_MODELS


def test_database_type_default_sqlite():
    assert settings.DATABASE_TYPE == DatabaseType.SQLITE


def test_base_url():
    assert settings.BASE_URL == f"http://{settings.HOST}:{settings.PORT}"


class TestLangSmithSettings:
    def test_defaults_tracing_disabled(self):
        assert settings.LANGCHAIN_TRACING_V2 is False
        assert settings.LANGCHAIN_PROJECT
        assert settings.LANGCHAIN_ENDPOINT.startswith("http")

    def test_endpoint_is_url_validated(self, monkeypatch):
        monkeypatch.setenv("LANGCHAIN_ENDPOINT", "https://api.smith.langchain.com/")
        # 校验器会去掉尾部斜杠，避免拼接路径出现 //
        assert Settings().LANGCHAIN_ENDPOINT == "https://api.smith.langchain.com"

    def test_api_key_is_masked(self, monkeypatch):
        monkeypatch.setenv("LANGCHAIN_API_KEY", "lsv2-very-secret")
        key = Settings().LANGCHAIN_API_KEY
        assert key is not None
        assert "lsv2-very-secret" not in repr(key)
        assert key.get_secret_value() == "lsv2-very-secret"


class TestExportLangsmithEnv:
    """LangChain 从 os.environ 读取追踪配置，因此必须写入进程环境。"""

    # 占位值必须能通过各自的字段校验（bool / URL / str）
    _PLACEHOLDER = {
        "LANGCHAIN_TRACING_V2": "false",
        "LANGCHAIN_PROJECT": "placeholder",
        "LANGCHAIN_ENDPOINT": "https://placeholder.invalid",
        "LANGCHAIN_API_KEY": "placeholder",
    }

    def _isolate(self, monkeypatch) -> None:
        # 先写占位值，让 monkeypatch 在测试结束后负责还原被 export 覆盖的变量
        for name, value in self._PLACEHOLDER.items():
            monkeypatch.setenv(name, value)

    def test_disabled_exports_false(self, monkeypatch):
        self._isolate(monkeypatch)
        cfg = Settings(LANGCHAIN_TRACING_V2=False)

        assert cfg.export_langsmith_env() is False
        assert os.environ["LANGCHAIN_TRACING_V2"] == "false"

    def test_enabled_exports_full_config(self, monkeypatch):
        self._isolate(monkeypatch)
        cfg = Settings(
            LANGCHAIN_TRACING_V2=True,
            LANGCHAIN_PROJECT="edu-test",
            LANGCHAIN_ENDPOINT="https://api.smith.langchain.com",
            LANGCHAIN_API_KEY="lsv2-abc",
        )

        assert cfg.export_langsmith_env() is True
        assert os.environ["LANGCHAIN_TRACING_V2"] == "true"
        assert os.environ["LANGCHAIN_PROJECT"] == "edu-test"
        assert os.environ["LANGCHAIN_ENDPOINT"] == "https://api.smith.langchain.com"
        assert os.environ["LANGCHAIN_API_KEY"] == "lsv2-abc"

    def test_missing_key_is_not_exported(self, monkeypatch):
        self._isolate(monkeypatch)
        monkeypatch.delenv("LANGCHAIN_API_KEY")
        cfg = Settings(LANGCHAIN_TRACING_V2=True, LANGCHAIN_API_KEY=None)

        assert cfg.export_langsmith_env() is True
        # 不能写入空串，否则 LangChain 会误以为已配置密钥
        assert "LANGCHAIN_API_KEY" not in os.environ
