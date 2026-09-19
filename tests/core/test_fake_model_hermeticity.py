"""假模型开关的封闭性（hermeticity）测试。

背景：`USE_FAKE_MODEL=true` 的文档承诺是"保证测试环境不被真实模型污染"，
但实测它只对 agent 层的 `get_model()` 生效，RAG 检索链的 `get_llm()` **完全没有 fake 分支**。
后果分两种环境，都很难察觉：

- **本地**（`.env` 配了真实 key 与 `LLM_MODEL`）→ 检索链真的调用线上模型。
  检索链的 decompose / HyDE 用温度 0.3，于是"评测"结果每次不同、基线不可复现、
  还产生费用。**没有任何报错**，看起来一切正常。
- **CI**（无 key）→ `openai.OpenAIError: Missing credentials` 直接抛出。
  实测 40 条检索门禁 query 里有 6 条因此崩溃，且异常会穿透
  `aretrieve_evidence_with_retry` 之外，让门禁只留下 traceback。

本文件把"开关必须真的封闭"钉成契约。这类缺陷的共性是**默认路径看起来是好的**，
所以断言必须落在"拿到的客户端类型"和"模型引用"上，而不是"没抛错"。
"""

from __future__ import annotations

from core.llm import FakeToolModel, get_llm
from core.settings import (
    GATEWAY_DEFAULT_MODEL,
    Gateway,
    Settings,
    make_model_ref,
    settings,
)

FAKE_REF = make_model_ref(Gateway.FAKE, GATEWAY_DEFAULT_MODEL[Gateway.FAKE])


def _cfg(**overrides) -> Settings:
    """构造一个**完全由测试决定**的 Settings，不受本机 `.env` 影响。

    `Settings.model_config` 里配了 `env_file=find_dotenv()`，所以裸调 `Settings(...)`
    会**悄悄读走本机的 `.env`** —— 本地有 `.env` 的机器上测试通过，CI（无 `.env`）上却失败。
    显式传 `_env_file=None` 关掉这条来源。
    """
    base = {
        "USE_FAKE_MODEL": False,
        "DASHSCOPE_API_KEY": "sk-test",
        "DEEPSEEK_API_KEY": None,
    }
    base.update(overrides)
    return Settings(_env_file=None, **base)


class TestGetLlmHonoursFakeGateway:
    def test_returns_fake_model_when_ref_is_fake(self, monkeypatch):
        monkeypatch.setattr(settings, "LLM_MODEL", FAKE_REF)
        assert isinstance(get_llm(streaming=False, temperature=0.3), FakeToolModel)

    def test_fake_model_is_not_shared_between_calls(self, monkeypatch):
        """FakeToolModel 有状态（responses 队列会被消费），共享会让响应互相穿插。"""
        monkeypatch.setattr(settings, "LLM_MODEL", FAKE_REF)
        assert get_llm() is not get_llm()

    def test_real_ref_does_not_get_fake_model(self, monkeypatch):
        """反向断言：非 fake 引用必须走真实客户端，不能一律返回假模型。"""
        sentinel = object()
        monkeypatch.setattr(settings, "LLM_MODEL", "dashscope:qwen3.8-27b")
        monkeypatch.setattr("core.llm._cached_client", lambda *a, **k: sentinel)
        assert get_llm() is sentinel

    def test_fake_ref_is_not_passed_to_client_builder(self, monkeypatch):
        """fake 引用绝不能被送进 _cached_client —— 那正是崩溃的来源。"""
        called: list[tuple] = []
        monkeypatch.setattr(settings, "LLM_MODEL", FAKE_REF)
        monkeypatch.setattr("core.llm._cached_client", lambda *a, **k: called.append((a, k)))
        get_llm()
        assert called == []


class TestUseFakeModelForcesBothRefs:
    """`USE_FAKE_MODEL` 必须同时拉回两个模型引用，否则"封闭"只是半封闭。"""

    def test_forces_llm_model_even_when_explicitly_set(self):
        cfg = _cfg(USE_FAKE_MODEL=True, LLM_MODEL="dashscope:qwen3.8-27b")
        assert cfg.LLM_MODEL == FAKE_REF

    def test_forces_default_model_even_when_explicitly_set(self):
        cfg = _cfg(USE_FAKE_MODEL=True, DEFAULT_MODEL="dashscope:qwen3.8-max")
        assert cfg.DEFAULT_MODEL == FAKE_REF

    def test_forces_llm_model_when_it_keeps_the_real_default(self):
        """LLM_MODEL 的**默认值本身就是真实模型**，不显式配也一样要拉回。"""
        cfg = _cfg(USE_FAKE_MODEL=True)
        assert cfg.LLM_MODEL == FAKE_REF

    def test_disabled_keeps_explicit_refs_untouched(self):
        cfg = _cfg(
            USE_FAKE_MODEL=False,
            LLM_MODEL="dashscope:qwen3.8-27b",
            DEFAULT_MODEL="dashscope:qwen3.8-max",
        )
        assert cfg.LLM_MODEL == "dashscope:qwen3.8-27b"
        assert cfg.DEFAULT_MODEL == "dashscope:qwen3.8-max"

    def test_disabled_still_fills_default_from_active_gateway(self):
        """关掉 fake 时，空的 DEFAULT_MODEL 要按**已启用网关**推导出来。

        **必须显式给 `LLM_MODEL`**：它的字段默认值是 `deepseek:deepseek-v4-flash`，
        而这里只启用了 dashscope —— 不显式覆盖的话，settings 会在**校验阶段**直接抛
        `ValidationError: LLM_MODEL 需要网关 deepseek，但该网关未启用`。
        本机 `.env` 里恰好配了 `LLM_MODEL=dashscope:...` 会把这个坑盖住，
        所以此测试过去**只在有 `.env` 的机器上通过**（CI 一直红）。
        """
        cfg = _cfg(
            USE_FAKE_MODEL=False,
            DASHSCOPE_API_KEY="sk-test",
            LLM_MODEL="dashscope:qwen3.8-max",
            DEFAULT_MODEL="",
        )
        assert cfg.DEFAULT_MODEL.startswith("dashscope:")

    def test_fake_mode_needs_no_credentials(self):
        cfg = Settings(USE_FAKE_MODEL=True, DASHSCOPE_API_KEY=None, DEEPSEEK_API_KEY=None)
        assert cfg.LLM_MODEL == FAKE_REF
        assert cfg.DEFAULT_MODEL == FAKE_REF

    def test_fake_mode_is_reachable_end_to_end(self, monkeypatch):
        """两个引用都是 fake 时，get_llm 必须真的返回假模型（而不是崩溃）。"""
        cfg = Settings(USE_FAKE_MODEL=True, DASHSCOPE_API_KEY=None, DEEPSEEK_API_KEY=None)
        monkeypatch.setattr(settings, "LLM_MODEL", cfg.LLM_MODEL)
        assert isinstance(get_llm(), FakeToolModel)


class TestGateHarnessIsHermetic:
    """门禁必须自带封闭性，不依赖外部环境或 settings 的默认推导。"""

    def test_configure_for_gate_forces_fake_llm(self, tmp_path):
        from evaluation.retrieval_gate import configure_for_gate

        before = settings.LLM_MODEL
        try:
            configure_for_gate(str(tmp_path))
            assert settings.USE_FAKE_MODEL is True
            assert settings.LLM_MODEL == FAKE_REF
            assert settings.DEFAULT_MODEL == FAKE_REF
            assert isinstance(get_llm(), FakeToolModel)
        finally:
            settings.LLM_MODEL = before

    def test_configure_for_gate_also_disables_external_services(self, tmp_path):
        from evaluation.retrieval_gate import configure_for_gate

        configure_for_gate(str(tmp_path))
        assert settings.USE_FAKE_EMBEDDING is True
        assert settings.RERANK_ENABLED is False
        assert settings.SEMANTIC_CACHE_ENABLED is False
        assert settings.CHROMA_PORT == 1

    def test_ci_workflow_enables_fake_model(self):
        """CI 里没有 .env，不设 USE_FAKE_MODEL 会在 settings 构造阶段就抛错。"""
        from pathlib import Path

        workflow = Path(".github/workflows/test.yml").read_text(encoding="utf-8")
        gate_job = workflow.split("retrieval-quality-gate", 1)[1]
        assert "USE_FAKE_MODEL" in gate_job, (
            "retrieval-quality-gate job 必须显式开启 USE_FAKE_MODEL，"
            "否则 settings 会因『未配置任何 LLM 网关』直接失败"
        )
